"""
Service for storing extraction results directly in PostgreSQL database.
Replaces JSON file creation with direct database inserts.
"""
import logging
from typing import Dict, List, Any, Optional
from sqlalchemy.orm import Session
from app.models.culture_result import CultureResult
from app.models.serology_result import SerologyResult
from app.models.topic_result import TopicResult
from app.models.component_result import ComponentResult
from app.models.document_chunk import DocumentChunk

logger = logging.getLogger(__name__)


class DBStorageService:
    """Service for storing extraction results in database."""
    
    @staticmethod
    def store_culture_results(document_id: int, culture_data: Dict[str, Any], db: Session) -> int:
        """
        Store culture extraction results in database.
        
        Args:
            document_id: ID of the document
            culture_data: Culture results dictionary (from get_qa_results)
            db: Database session
            
        Returns:
            Number of culture results stored
        """
        try:
            count = 0
            # Culture data structure: {"result": [...], "citations": [...]}
            # Each result item contains tissue location and microorganisms
            if isinstance(culture_data, dict) and 'result' in culture_data:
                results = culture_data.get('result', [])
                
                for result_item in results:
                    if isinstance(result_item, dict):
                        # Extract tissue location and microorganisms
                        for tissue_location, microorganisms in result_item.items():
                            if isinstance(microorganisms, list):
                                for microorganism in microorganisms:
                                    if microorganism:  # Skip empty strings
                                        culture_result = CultureResult(
                                            document_id=document_id,
                                            tissue_location=tissue_location,
                                            microorganism=microorganism,
                                            source_page=None,  # Can be extracted from citations if available
                                            confidence=None
                                        )
                                        db.add(culture_result)
                                        count += 1
            
            db.commit()
            logger.info(f"Stored {count} culture results for document {document_id}")
            return count
            
        except Exception as e:
            logger.error(f"Error storing culture results for document {document_id}: {e}")
            db.rollback()
            return 0
    
    @staticmethod
    def store_serology_results(document_id: int, serology_data: Dict[str, Any], db: Session) -> int:
        """
        Store serology extraction results in database.
        
        Args:
            document_id: ID of the document
            serology_data: Serology results dictionary (from get_qa_results)
            db: Database session
            
        Returns:
            Number of serology results stored
        """
        try:
            count = 0
            # Serology data structure: {"result": {...}, "citations": [...]}
            # Result is a dictionary of test_name: result pairs
            if isinstance(serology_data, dict) and 'result' in serology_data:
                results = serology_data.get('result', {})
                
                for test_name, result_value in results.items():
                    if result_value:  # Skip empty/None results
                        serology_result = SerologyResult(
                            document_id=document_id,
                            test_name=test_name,
                            result=str(result_value),
                            source_page=None,  # Can be extracted from citations if available
                            confidence=None
                        )
                        db.add(serology_result)
                        count += 1
            
            db.commit()
            logger.info(f"Stored {count} serology results for document {document_id}")
            return count
            
        except Exception as e:
            logger.error(f"Error storing serology results for document {document_id}: {e}")
            db.rollback()
            return 0
    
    @staticmethod
    def store_topic_results(document_id: int, topics_data: Dict[str, Any], db: Session) -> int:
        """
        Store topic summarization results in database.
        
        Args:
            document_id: ID of the document
            topics_data: Topics results dictionary (from get_topic_summary_results)
            db: Database session
            
        Returns:
            Number of topic results stored
        """
        try:
            count = 0
            # Topics data structure varies, but typically contains topic summaries
            if isinstance(topics_data, dict):
                for topic_name, topic_info in topics_data.items():
                    if isinstance(topic_info, dict):
                        summary = topic_info.get('summary', '')
                        citations = topic_info.get('citations', [])
                        source_pages = topic_info.get('source_pages', [])
                        
                        topic_result = TopicResult(
                            document_id=document_id,
                            topic_name=topic_name,
                            summary=summary,
                            citations=citations if citations else None,
                            source_pages=source_pages if source_pages else None
                        )
                        db.add(topic_result)
                        count += 1
            
            db.commit()
            logger.info(f"Stored {count} topic results for document {document_id}")
            return count
            
        except Exception as e:
            logger.error(f"Error storing topic results for document {document_id}: {e}")
            db.rollback()
            return 0
    
    @staticmethod
    def store_component_results(document_id: int, components_data: Dict[str, Any], db: Session) -> int:
        """
        Store document component extraction results in database.
        
        Args:
            document_id: ID of the document
            components_data: Components results dictionary (from get_document_components)
            db: Database session
            
        Returns:
            Number of component results stored
        """
        try:
            count = 0
            # Components data structure: {"initial_components": {...}, "conditional_components": {...}}
            initial_components = components_data.get('initial_components', {})
            conditional_components = components_data.get('conditional_components', {})
            
            # Store initial components
            for component_name, component_info in initial_components.items():
                if isinstance(component_info, dict):
                    component_result = ComponentResult(
                        document_id=document_id,
                        component_name=component_name,
                        present=component_info.get('present', False),
                        pages=component_info.get('pages', []),
                        summary=component_info.get('summary', ''),
                        extracted_data=component_info.get('extracted_data', {})
                    )
                    db.add(component_result)
                    count += 1
            
            # Store conditional components (only if present)
            for component_name, component_info in conditional_components.items():
                if isinstance(component_info, dict) and component_info.get('present', False):
                    component_result = ComponentResult(
                        document_id=document_id,
                        component_name=component_name,
                        present=True,
                        pages=component_info.get('pages', []),
                        summary=component_info.get('summary', ''),
                        extracted_data=component_info.get('extracted_data', {})
                    )
                    db.add(component_result)
                    count += 1
            
            db.commit()
            logger.info(f"Stored {count} component results for document {document_id}")
            return count
            
        except Exception as e:
            logger.error(f"Error storing component results for document {document_id}: {e}")
            db.rollback()
            return 0
    
    @staticmethod
    def store_document_chunks(document_id: int, chunks_with_embeddings: List[Dict[str, Any]], db: Session) -> int:
        """
        Store document chunks with embeddings in database (pgvector).
        
        Args:
            document_id: ID of the document
            chunks_with_embeddings: List of chunk dictionaries with text, index, page, and embedding
            db: Database session
            
        Returns:
            Number of chunks stored
        """
        try:
            count = 0
            for chunk_data in chunks_with_embeddings:
                chunk_result = DocumentChunk(
                    document_id=document_id,
                    chunk_text=chunk_data.get('text', ''),
                    chunk_index=chunk_data.get('index', 0),
                    page_number=chunk_data.get('page', None),
                    embedding=chunk_data.get('embedding', None),  # Vector embedding
                    chunk_metadata=chunk_data.get('metadata', {})
                )
                db.add(chunk_result)
                count += 1
            
            db.commit()
            logger.info(f"Stored {count} document chunks for document {document_id}")
            return count
            
        except Exception as e:
            logger.error(f"Error storing document chunks for document {document_id}: {e}")
            db.rollback()
            return 0


# Global instance
db_storage_service = DBStorageService()

