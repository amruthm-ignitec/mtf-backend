"""
Service for storing document chunks in PostgreSQL database with pgvector.
"""
import logging
from typing import List, Dict, Any
from sqlalchemy.orm import Session
from app.models.document_chunk import DocumentChunk

logger = logging.getLogger(__name__)


class DBStorageService:
    """Service for storing document chunks in database."""
    
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
            chunks_with_pages = 0
            chunks_without_pages = 0
            for chunk_data in chunks_with_embeddings:
                page_number = chunk_data.get('page', None)
                if page_number is not None:
                    chunks_with_pages += 1
                else:
                    chunks_without_pages += 1
                
                chunk_result = DocumentChunk(
                    document_id=document_id,
                    chunk_text=chunk_data.get('text', ''),
                    chunk_index=chunk_data.get('index', 0),
                    page_number=page_number,
                    embedding=chunk_data.get('embedding', None),  # Vector embedding
                    chunk_metadata=chunk_data.get('metadata', {})
                )
                db.add(chunk_result)
                count += 1
            
            db.commit()
            logger.info(f"Stored {count} document chunks for document {document_id} ({chunks_with_pages} with page numbers, {chunks_without_pages} without)")
            if chunks_without_pages > 0:
                logger.warning(f"Document {document_id}: {chunks_without_pages} chunks stored without page numbers. This may indicate metadata is not being preserved during chunking.")
            return count
            
        except Exception as e:
            logger.error(f"Error storing document chunks for document {document_id}: {e}")
            db.rollback()
            return 0


# Global instance
db_storage_service = DBStorageService()
