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
    
    async def _ensure_embeddings(self):
        """Initialize embeddings if not already done."""
        if self.embeddings is None:
            from app.services.processing.utils.llm_config import llm_setup
            import asyncio
            loop = asyncio.get_event_loop()
            _, self.embeddings = await loop.run_in_executor(None, llm_setup)
    
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
    
    async def convert_and_store_donor_vectors(self, donor_id: int, db: Session) -> bool:
        """
        Convert extracted data to text, generate embeddings, and store in pgvector.
        
        Args:
            donor_id: ID of the donor
            db: Database session
            
        Returns:
            True if successful, False otherwise
        """
        try:
            await self._ensure_embeddings()
            
            # Get all extraction results for this donor from database
            from app.models.document import Document, DocumentStatus
            from app.services.processing.result_parser import result_parser
            
            documents = db.query(Document).filter(
                Document.donor_id == donor_id,
                Document.status == DocumentStatus.COMPLETED
            ).all()
            
            if not documents:
                logger.info(f"No completed documents found for donor {donor_id}")
                return False
            
            # Collect all results
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
            
            # Delete existing vectors for this donor
            db.query(DonorExtractionVector).filter(
                DonorExtractionVector.donor_id == donor_id
            ).delete()
            
            # Convert and store culture
            if all_culture:
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
            
            # Convert and store serology
            if all_serology:
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
            
            # Convert and store topics (one per topic)
            import json
            topic_texts = self._topics_to_text(all_topics)
            for topic_text in topic_texts:
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
            
            # Convert and store components
            if all_components.get('initial_components') or all_components.get('conditional_components'):
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
            
            db.commit()
            logger.info(f"Successfully stored extraction vectors for donor {donor_id}")
            return True
            
        except Exception as e:
            logger.error(f"Error converting and storing vectors for donor {donor_id}: {e}", exc_info=True)
            db.rollback()
            return False
    
    async def _generate_embedding(self, text: str) -> List[float]:
        """Generate embedding for text."""
        try:
            if not self.embeddings:
                await self._ensure_embeddings()
            
            # Generate embedding
            import asyncio
            loop = asyncio.get_event_loop()
            embedding = await loop.run_in_executor(
                None,
                lambda: self.embeddings.embed_query(text)
            )
            
            # Ensure embedding has correct dimensions (1536) for database schema
            # If dimensions parameter didn't work, truncate or pad as needed
            if embedding:
                embedding_len = len(embedding)
                if embedding_len > 1536:
                    # Truncate to 1536 dimensions
                    logger.warning(f"Embedding has {embedding_len} dimensions, truncating to 1536")
                    embedding = embedding[:1536]
                elif embedding_len < 1536:
                    # Pad with zeros (shouldn't happen, but handle it)
                    logger.warning(f"Embedding has {embedding_len} dimensions, padding to 1536")
                    embedding = embedding + [0.0] * (1536 - embedding_len)
            
            return embedding
        except Exception as e:
            logger.error(f"Error generating embedding: {e}")
            return None


# Global instance
vector_conversion_service = VectorConversionService()

