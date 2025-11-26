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
        """Process a single document."""
        db_gen = get_db()
        db = next(db_gen)
        try:
            logger.info(f"Processing document {document_id}")
            await document_processing_service.process_document(document_id, db)
            logger.info(f"Completed processing document {document_id}")
        except Exception as e:
            logger.error(f"Error processing document {document_id}: {e}", exc_info=True)
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

