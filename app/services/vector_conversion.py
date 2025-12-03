"""
Service for converting extracted data to text and storing as vectors in pgvector.
"""
import json
import logging
from typing import Dict, List, Any
from sqlalchemy.orm import Session
from app.models.donor_extraction_vector import DonorExtractionVector
from app.models.culture_result import CultureResult
from app.models.serology_result import SerologyResult
from app.models.topic_result import TopicResult
from app.models.component_result import ComponentResult

logger = logging.getLogger(__name__)


class VectorConversionService:
    """Service for converting extracted data to searchable vectors."""
    
    def __init__(self):
        self.embeddings = None
        self.consecutive_failures = 0  # Track consecutive failures for circuit breaker
        self.circuit_breaker_threshold = 1  # Skip vector conversion after 1 consecutive failure (very aggressive)
    
    async def _ensure_embeddings(self, max_retries: int = 1, base_delay: float = 1.0):
        """
        Initialize embeddings if not already done, with exponential backoff retry on timeout.
        
        Args:
            max_retries: Maximum number of retry attempts (default: 1 - very aggressive to prevent hanging)
            base_delay: Base delay in seconds for exponential backoff (default: 1.0)
        """
        if self.embeddings is None:
            import asyncio
            from app.services.processing.utils.llm_config import llm_setup
            
            logger.info("Initializing embeddings (llm_setup)...")
            last_exception = None
            
            for attempt in range(max_retries + 1):  # +1 because first attempt is not a retry
                try:
                    loop = asyncio.get_event_loop()
                    # Wrap llm_setup with timeout (15 seconds for initialization - more aggressive)
                    _, self.embeddings = await asyncio.wait_for(
                        loop.run_in_executor(None, llm_setup),
                        timeout=15.0  # Reduced from 30s to 15s
                    )
                    logger.info("Successfully initialized embeddings")
                    return  # Success - exit retry loop
                    
                except asyncio.TimeoutError as e:
                    last_exception = e
                    if attempt < max_retries:
                        # Calculate exponential backoff delay: base_delay * 2^attempt
                        delay = base_delay * (2 ** attempt)
                        logger.warning(
                            f"Embeddings initialization timed out after 15 seconds. "
                            f"Retrying in {delay:.1f}s (attempt {attempt + 1}/{max_retries + 1})"
                        )
                        await asyncio.sleep(delay)
                    else:
                        logger.error(
                            f"Embeddings initialization timed out after {max_retries + 1} attempts - aborting"
                        )
                        raise
                        
                except Exception as e:
                    last_exception = e
                    if attempt < max_retries:
                        delay = base_delay * (2 ** attempt)
                        logger.warning(
                            f"Error initializing embeddings: {e}. "
                            f"Retrying in {delay:.1f}s (attempt {attempt + 1}/{max_retries + 1})"
                        )
                        await asyncio.sleep(delay)
                    else:
                        logger.error(f"Error initializing embeddings after {max_retries + 1} attempts: {e}", exc_info=True)
                        raise
    
    def _culture_to_text(self, culture_results: List[Dict]) -> str:
        """Convert culture results to searchable text."""
        texts = []
        for result in culture_results:
            tissue = result.get('tissue_location', '')
            microorganism = result.get('microorganism', '')
            if tissue and microorganism:
                texts.append(f"Donor has {microorganism} in {tissue}")
        return ". ".join(texts)
    
    def _serology_to_text(self, serology_results: Dict) -> str:
        """Convert serology results to searchable text."""
        texts = []
        for test_name, result_value in serology_results.items():
            texts.append(f"Test {test_name} = {result_value}")
        return ". ".join(texts)
    
    def _topics_to_text(self, topic_results: Dict) -> List[str]:
        """Convert topic results to searchable text descriptions."""
        texts = []
        for topic_name, topic_info in topic_results.items():
            summary = topic_info.get('summary', '')
            if summary:
                if isinstance(summary, dict):
                    summary_str = json.dumps(summary)
                else:
                    summary_str = str(summary)
                texts.append(f"Medical condition: {topic_name} - {summary_str}")
        return texts
    
    def _components_to_text(self, component_results: Dict) -> str:
        """Convert component results to searchable text."""
        texts = []
        initial = component_results.get('initial_components', {})
        conditional = component_results.get('conditional_components', {})
        
        for comp_name, comp_info in {**initial, **conditional}.items():
            status = "present" if comp_info.get('present', False) else "missing"
            pages = comp_info.get('pages', [])
            pages_str = f", pages: {pages}" if pages else ""
            texts.append(f"{comp_name} status: {status}{pages_str}")
        
        return ". ".join(texts)
    
    async def convert_and_store_donor_vectors(self, donor_id: int, db: Session, max_total_time: float = 60.0) -> bool:
        """
        Convert extracted data to text, generate embeddings, and store in pgvector.
        
        Args:
            donor_id: ID of the donor
            db: Database session
            max_total_time: Maximum total time in seconds for entire vector conversion (default: 60s = 1 minute)
            
        Returns:
            True if successful, False otherwise
        """
        import asyncio
        import time
        
        start_time = time.time()
        
        try:
            logger.info(f"Starting vector conversion for donor {donor_id} (max time: {max_total_time}s)")
            
            # Ensure embeddings are initialized with timeout check
            logger.debug(f"Ensuring embeddings are initialized for donor {donor_id}")
            elapsed = time.time() - start_time
            if elapsed >= max_total_time:
                logger.warning(f"Vector conversion for donor {donor_id} aborted: exceeded max time before starting")
                return False
            
            await self._ensure_embeddings()
            logger.debug(f"Embeddings initialized for donor {donor_id}")
            
            # Check timeout after initialization
            elapsed = time.time() - start_time
            if elapsed >= max_total_time:
                logger.warning(f"Vector conversion for donor {donor_id} aborted: exceeded max time after initialization")
                return False
            
            # Get all extraction results for this donor from database
            from app.models.document import Document, DocumentStatus
            from app.services.processing.result_parser import result_parser
            
            logger.debug(f"Querying completed documents for donor {donor_id}")
            documents = db.query(Document).filter(
                Document.donor_id == donor_id,
                Document.status == DocumentStatus.COMPLETED
            ).all()
            
            if not documents:
                logger.info(f"No completed documents found for donor {donor_id}")
                return False
            
            logger.info(f"Found {len(documents)} completed documents for donor {donor_id}")
            
            # Collect all results
            logger.debug(f"Collecting extraction results for donor {donor_id}")
            all_culture = []
            all_serology = {}
            all_topics = {}
            all_components = {"initial_components": {}, "conditional_components": {}}
            
            for document in documents:
                culture_data = result_parser.get_culture_results_for_document(document.id, db)
                if culture_data.get('result'):
                    all_culture.extend(culture_data['result'])
                
                serology_data = result_parser.get_serology_results_for_document(document.id, db)
                if serology_data.get('result'):
                    all_serology.update(serology_data['result'])
                
                topic_data = result_parser.get_topic_results_for_document(document.id, db)
                if topic_data:
                    all_topics.update(topic_data)
                
                component_data = result_parser.get_component_results_for_document(document.id, db)
                if component_data:
                    # Merge components
                    for key, value in component_data.get('initial_components', {}).items():
                        if key not in all_components['initial_components']:
                            all_components['initial_components'][key] = value
                    for key, value in component_data.get('conditional_components', {}).items():
                        if key not in all_components['conditional_components']:
                            all_components['conditional_components'][key] = value
            
            logger.debug(f"Collected results for donor {donor_id}: "
                        f"culture={len(all_culture)}, serology={len(all_serology)}, "
                        f"topics={len(all_topics)}, components={len(all_components.get('initial_components', {})) + len(all_components.get('conditional_components', {}))}")
            
            # Delete existing vectors for this donor
            logger.debug(f"Deleting existing vectors for donor {donor_id}")
            deleted_count = db.query(DonorExtractionVector).filter(
                DonorExtractionVector.donor_id == donor_id
            ).delete()
            if deleted_count > 0:
                logger.debug(f"Deleted {deleted_count} existing vectors for donor {donor_id}")
            
            vectors_created = 0
            
            # Convert and store culture
            if all_culture:
                elapsed = time.time() - start_time
                if elapsed >= max_total_time:
                    logger.warning(f"Vector conversion for donor {donor_id} aborted: exceeded max time before culture processing")
                    return False
                    
                logger.debug(f"Processing culture results for donor {donor_id}")
                culture_text = self._culture_to_text(all_culture)
                if culture_text:
                    embedding = await self._generate_embedding(culture_text)
                    if embedding:
                        vector = DonorExtractionVector(
                            donor_id=donor_id,
                            extraction_type='culture',
                            extraction_text=culture_text,
                            embedding=embedding,
                            extraction_metadata={"results": all_culture}
                        )
                        db.add(vector)
                        vectors_created += 1
                        logger.debug(f"Created culture vector for donor {donor_id}")
            
            # Convert and store serology
            if all_serology:
                elapsed = time.time() - start_time
                if elapsed >= max_total_time:
                    logger.warning(f"Vector conversion for donor {donor_id} aborted: exceeded max time before serology processing")
                    return False
                    
                logger.debug(f"Processing serology results for donor {donor_id}")
                serology_text = self._serology_to_text(all_serology)
                if serology_text:
                    embedding = await self._generate_embedding(serology_text)
                    if embedding:
                        vector = DonorExtractionVector(
                            donor_id=donor_id,
                            extraction_type='serology',
                            extraction_text=serology_text,
                            embedding=embedding,
                            extraction_metadata={"results": all_serology}
                        )
                        db.add(vector)
                        vectors_created += 1
                        logger.debug(f"Created serology vector for donor {donor_id}")
            
            # Convert and store topics (one per topic)
            import json
            topic_texts = self._topics_to_text(all_topics)
            if topic_texts:
                logger.debug(f"Processing {len(topic_texts)} topic results for donor {donor_id}")
            for idx, topic_text in enumerate(topic_texts):
                elapsed = time.time() - start_time
                if elapsed >= max_total_time:
                    logger.warning(f"Vector conversion for donor {donor_id} aborted: exceeded max time at topic {idx+1}/{len(topic_texts)}")
                    # Commit what we have so far
                    if vectors_created > 0:
                        db.commit()
                        logger.info(f"Partially completed: stored {vectors_created} vectors for donor {donor_id} before timeout")
                    return False
                    
                embedding = await self._generate_embedding(topic_text)
                if embedding:
                    vector = DonorExtractionVector(
                        donor_id=donor_id,
                        extraction_type='topic',
                        extraction_text=topic_text,
                        embedding=embedding,
                        extraction_metadata={"topics": all_topics}
                    )
                    db.add(vector)
                    vectors_created += 1
                    logger.debug(f"Created topic vector for donor {donor_id}")
            
            # Convert and store components
            if all_components.get('initial_components') or all_components.get('conditional_components'):
                elapsed = time.time() - start_time
                if elapsed >= max_total_time:
                    logger.warning(f"Vector conversion for donor {donor_id} aborted: exceeded max time before component processing")
                    # Commit what we have so far
                    if vectors_created > 0:
                        db.commit()
                        logger.info(f"Partially completed: stored {vectors_created} vectors for donor {donor_id} before timeout")
                    return False
                    
                logger.debug(f"Processing component results for donor {donor_id}")
                components_text = self._components_to_text(all_components)
                if components_text:
                    embedding = await self._generate_embedding(components_text)
                    if embedding:
                        vector = DonorExtractionVector(
                            donor_id=donor_id,
                            extraction_type='component',
                            extraction_text=components_text,
                            embedding=embedding,
                            extraction_metadata={"components": all_components}
                        )
                        db.add(vector)
                        vectors_created += 1
                        logger.debug(f"Created component vector for donor {donor_id}")
            
            logger.debug(f"Committing {vectors_created} vectors to database for donor {donor_id}")
            db.commit()
            logger.info(f"Successfully stored {vectors_created} extraction vectors for donor {donor_id}")
            return True
            
        except Exception as e:
            logger.error(f"Error converting and storing vectors for donor {donor_id}: {e}", exc_info=True)
            db.rollback()
            return False
    
    async def _generate_embedding(self, text: str, max_retries: int = 1, base_delay: float = 1.0) -> List[float]:
        """
        Generate embedding for text with timeout protection and exponential backoff retry.
        
        Args:
            text: Text to generate embedding for
            max_retries: Maximum number of retry attempts on timeout (default: 1 - very aggressive to prevent hanging)
            base_delay: Base delay in seconds for exponential backoff (default: 1.0)
            
        Returns:
            Embedding vector or None if all retries fail
        """
        try:
            if not self.embeddings:
                await self._ensure_embeddings()
            
            # Generate embedding with timeout (5 seconds per embedding call - very aggressive)
            import asyncio
            logger.debug(f"Generating embedding for text (length: {len(text)} chars)")
            loop = asyncio.get_event_loop()
            
            last_exception = None
            for attempt in range(max_retries + 1):  # +1 because first attempt is not a retry
                try:
                    embedding = await asyncio.wait_for(
                        loop.run_in_executor(
                            None,
                            lambda: self.embeddings.embed_query(text)
                        ),
                        timeout=5.0  # Reduced from 10s to 5s - more aggressive
                    )
                    logger.debug(f"Successfully generated embedding (dimensions: {len(embedding) if embedding else 0})")
                    
                    # Embeddings are now 3072 dimensions (text-embedding-3-large default)
                    # No truncation needed - database schema supports 3072 dimensions
                    return embedding
                    
                except asyncio.TimeoutError as e:
                    last_exception = e
                    if attempt < max_retries:
                        # Calculate exponential backoff delay: base_delay * 2^attempt
                        delay = base_delay * (2 ** attempt)
                        logger.warning(
                            f"Embedding generation timed out after 5 seconds for text (length: {len(text)} chars). "
                            f"Retrying in {delay:.1f}s (attempt {attempt + 1}/{max_retries + 1})"
                        )
                        await asyncio.sleep(delay)
                    else:
                        logger.error(
                            f"Embedding generation timed out after {max_retries + 1} attempts "
                            f"for text (length: {len(text)} chars) - aborting"
                        )
                        return None
                        
                except Exception as e:
                    last_exception = e
                    if attempt < max_retries:
                        delay = base_delay * (2 ** attempt)
                        logger.warning(
                            f"Error generating embedding: {e}. "
                            f"Retrying in {delay:.1f}s (attempt {attempt + 1}/{max_retries + 1})"
                        )
                        await asyncio.sleep(delay)
                    else:
                        logger.error(f"Error generating embedding after {max_retries + 1} attempts: {e}", exc_info=True)
                        return None
                        
        except Exception as e:
            logger.error(f"Error generating embedding: {e}", exc_info=True)
            return None


# Global instance
vector_conversion_service = VectorConversionService()

