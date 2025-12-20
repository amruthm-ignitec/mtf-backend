"""
Background worker for processing documents from the queue.
Uses asyncio to poll the database queue and process documents concurrently.
"""
import asyncio
import logging
from typing import Optional
from sqlalchemy.orm import Session
from app.database.database import get_db
from app.services.queue_service import queue_service
from app.services.document_processing import document_processing_service
from app.core.config import settings

logger = logging.getLogger(__name__)


class DocumentWorker:
    """Background worker for processing queued documents."""
    
    def __init__(self):
        self.running = False
        self.tasks = set()
        self.max_concurrent = settings.WORKER_MAX_CONCURRENT
        self.poll_interval = settings.WORKER_POLL_INTERVAL
    
    async def start(self):
        """Start the background worker."""
        if not settings.WORKER_ENABLED:
            logger.info("Worker is disabled in configuration")
            return
        
        self.running = True
        logger.info(f"Starting document worker (max_concurrent={self.max_concurrent}, poll_interval={self.poll_interval}s)")
        
        try:
            while self.running:
                await self._process_queue()
                await asyncio.sleep(self.poll_interval)
        except asyncio.CancelledError:
            logger.info("Worker cancelled, shutting down...")
        except Exception as e:
            logger.error(f"Worker error: {e}", exc_info=True)
        finally:
            await self.stop()
    
    async def stop(self):
        """Stop the background worker gracefully."""
        logger.info("Stopping document worker...")
        self.running = False
        
        # Wait for all tasks to complete
        if self.tasks:
            logger.info(f"Waiting for {len(self.tasks)} active tasks to complete...")
            await asyncio.gather(*self.tasks, return_exceptions=True)
        
        logger.info("Document worker stopped")
    
    async def _process_queue(self):
        """Process documents from the queue."""
        # Check if we have capacity for more tasks
        active_count = len([t for t in self.tasks if not t.done()])
        
        if active_count >= self.max_concurrent:
            return  # At capacity
        
        # Get next document from queue
        db_gen = get_db()
        db = next(db_gen)
        try:
            document = await queue_service.get_next_queued_document(db)
            
            if document:
                # Mark as processing
                marked = await queue_service.mark_document_processing(document.id, db)
                
                if marked:
                    # Create task for processing
                    task = asyncio.create_task(
                        self._process_document(document.id)
                    )
                    self.tasks.add(task)
                    
                    # Clean up completed tasks
                    self.tasks = {t for t in self.tasks if not t.done()}
                    
                    logger.info(f"Started processing document {document.id} (active tasks: {len([t for t in self.tasks if not t.done()])})")
                else:
                    logger.warning(f"Failed to mark document {document.id} as processing")
        except Exception as e:
            logger.error(f"Error processing queue: {e}", exc_info=True)
        finally:
            try:
                db.close()
            except:
                pass
    
    async def _process_document(self, document_id: int):
        """Process a single document with timeout and extensive error handling."""
        db_gen = get_db()
        db = next(db_gen)
        try:
            logger.info(f"Processing document {document_id}")
            
            # Wrap processing in timeout to prevent indefinite hangs
            timeout_seconds = settings.WORKER_DOCUMENT_TIMEOUT_SECONDS
            try:
                await asyncio.wait_for(
                    document_processing_service.process_document(document_id, db),
                    timeout=timeout_seconds
                )
                logger.info(f"Completed processing document {document_id}")
            except asyncio.TimeoutError:
                logger.error(
                    f"Document {document_id} processing timed out after {timeout_seconds} seconds. "
                    f"Marking as FAILED and resetting to UPLOADED for retry."
                )
                # Mark as failed and reset to UPLOADED for retry
                try:
                    from app.models.document import Document, DocumentStatus
                    document = db.query(Document).filter(Document.id == document_id).first()
                    if document:
                        document.status = DocumentStatus.FAILED
                        document.error_message = f"Processing timed out after {timeout_seconds} seconds. Will be retried."
                        document.progress = 100.0
                        db.commit()
                        
                        # Reset to UPLOADED so it can be retried
                        document.status = DocumentStatus.UPLOADED
                        document.progress = 0.0
                        document.error_message = None
                        db.commit()
                        logger.info(f"Reset document {document_id} to UPLOADED for retry after timeout")
                except Exception as reset_error:
                    logger.error(f"Error resetting document {document_id} after timeout: {reset_error}", exc_info=True)
                    db.rollback()
            except Exception as e:
                logger.error(f"Error processing document {document_id}: {e}", exc_info=True)
                # Try to mark as failed
                try:
                    from app.models.document import Document, DocumentStatus
                    document = db.query(Document).filter(Document.id == document_id).first()
                    if document:
                        document.status = DocumentStatus.FAILED
                        document.error_message = f"Processing failed: {str(e)}"
                        document.progress = 100.0
                        db.commit()
                except Exception as update_error:
                    logger.error(f"Error updating document {document_id} status: {update_error}", exc_info=True)
                    db.rollback()
            
            # Add delay after processing to prevent server overload
            delay_seconds = settings.WORKER_DOCUMENT_DELAY_SECONDS
            if delay_seconds > 0:
                logger.info(f"Waiting {delay_seconds} seconds before processing next document...")
                await asyncio.sleep(delay_seconds)
        except Exception as e:
            logger.error(f"Unexpected error in _process_document for document {document_id}: {e}", exc_info=True)
        finally:
            try:
                db.close()
            except:
                pass


# Global worker instance
document_worker = DocumentWorker()


async def start_worker():
    """Start the document worker (called from FastAPI startup)."""
    if settings.WORKER_ENABLED:
        asyncio.create_task(document_worker.start())
        logger.info("Document worker started")
    else:
        logger.info("Document worker is disabled")

