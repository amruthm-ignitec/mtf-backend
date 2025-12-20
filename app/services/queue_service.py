"""
Queue service for managing document processing queue.
Uses database-backed queue with Document.status = UPLOADED as queue indicator.
"""
import logging
from typing import Optional
from sqlalchemy.orm import Session
from sqlalchemy import and_, update
from app.models.document import Document, DocumentStatus
from app.core.config import settings

logger = logging.getLogger(__name__)


class QueueService:
    """Service for managing document processing queue."""
    
    @staticmethod
    async def get_next_queued_document(db: Session) -> Optional[Document]:
        """
        Get the next document from the queue (status = UPLOADED).
        Uses row-level locking to prevent duplicate processing.
        
        Args:
            db: Database session
            
        Returns:
            Document object if found, None otherwise
        """
        try:
            # Query for UPLOADED documents, ordered by creation time (FIFO)
            # Use FOR UPDATE SKIP LOCKED to prevent multiple workers from picking the same document
            document = db.query(Document).filter(
                Document.status == DocumentStatus.UPLOADED
            ).order_by(
                Document.created_at.asc()
            ).with_for_update(skip_locked=True).first()
            
            if document:
                logger.info(f"Found queued document: {document.id} - {document.original_filename}")
                return document
            else:
                return None
                
        except Exception as e:
            logger.error(f"Error getting next queued document: {e}")
            return None
    
    @staticmethod
    async def mark_document_processing(document_id: int, db: Session) -> bool:
        """
        Mark a document as being processed.
        
        Args:
            document_id: ID of the document to mark
            db: Database session
            
        Returns:
            True if successful, False otherwise
        """
        try:
            document = db.query(Document).filter(Document.id == document_id).first()
            if not document:
                logger.error(f"Document {document_id} not found")
                return False
            
            if document.status != DocumentStatus.UPLOADED:
                logger.warning(f"Document {document_id} is not in UPLOADED status (current: {document.status})")
                return False
            
            document.status = DocumentStatus.PROCESSING
            document.progress = 0.0
            db.commit()
            db.refresh(document)
            
            logger.info(f"Marked document {document_id} as PROCESSING")
            return True
            
        except Exception as e:
            logger.error(f"Error marking document {document_id} as processing: {e}")
            db.rollback()
            return False
    
    @staticmethod
    async def get_queue_size(db: Session) -> int:
        """
        Get the number of documents waiting in the queue.
        
        Args:
            db: Database session
            
        Returns:
            Number of queued documents
        """
        try:
            count = db.query(Document).filter(
                Document.status == DocumentStatus.UPLOADED
            ).count()
            return count
        except Exception as e:
            logger.error(f"Error getting queue size: {e}")
            return 0
    
    @staticmethod
    async def get_processing_count(db: Session) -> int:
        """
        Get the number of documents currently being processed.
        
        Args:
            db: Database session
            
        Returns:
            Number of documents in processing
        """
        try:
            count = db.query(Document).filter(
                Document.status.in_([
                    DocumentStatus.PROCESSING,
                    DocumentStatus.ANALYZING,
                    DocumentStatus.REVIEWING
                ])
            ).count()
            return count
        except Exception as e:
            logger.error(f"Error getting processing count: {e}")
            return 0
    
    @staticmethod
    async def reset_stuck_documents(db: Session) -> int:
        """
        Reset documents that are stuck in PROCESSING/ANALYZING/REVIEWING status.
        This happens when the server restarts while documents are being processed.
        Resets them back to UPLOADED so they can be retried.
        
        Args:
            db: Database session
            
        Returns:
            Number of documents reset
        """
        try:
            from datetime import datetime, timedelta
            from sqlalchemy import update
            
            # Reset documents that are in processing states
            # These were likely interrupted by server restart
            result = db.execute(
                update(Document)
                .where(
                    Document.status.in_([
                        DocumentStatus.PROCESSING,
                        DocumentStatus.ANALYZING,
                        DocumentStatus.REVIEWING
                    ])
                )
                .values(
                    status=DocumentStatus.UPLOADED,
                    progress=0.0,
                    error_message=None
                )
            )
            
            count = result.rowcount
            db.commit()
            
            if count > 0:
                logger.info(f"Reset {count} stuck document(s) back to UPLOADED status for retry")
            else:
                logger.info("No stuck documents found to reset")
            
            return count
        except Exception as e:
            logger.error(f"Error resetting stuck documents: {e}")
            db.rollback()
            return 0


# Global instance
queue_service = QueueService()

