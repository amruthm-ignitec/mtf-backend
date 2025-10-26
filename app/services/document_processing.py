import asyncio
import random
import logging
from sqlalchemy.orm import Session
from app.models.document import Document, DocumentStatus
from app.schemas.document import DocumentUpdate

logger = logging.getLogger(__name__)

class DocumentProcessingService:
    async def start_processing(self, document_id: int, db: Session):
        logger.info(f"Starting background processing for document ID: {document_id}")
        asyncio.create_task(self._process_document_workflow(document_id, db))

    async def _process_document_workflow(self, document_id: int, db: Session):
        try:
            # Simulate various processing stages
            stages = [
                (DocumentStatus.PROCESSING, 0.2, 2),  # Initial processing
                (DocumentStatus.ANALYZING, 0.5, 3),   # AI analysis
                (DocumentStatus.REVIEWING, 0.8, 4),   # Human review simulation
                (DocumentStatus.COMPLETED, 1.0, 1)    # Final completion
            ]

            document = db.query(Document).filter(Document.id == document_id).first()
            if not document:
                logger.error(f"Document {document_id} not found for processing.")
                return

            for status, progress_target, delay in stages:
                await asyncio.sleep(delay) # Simulate work being done
                
                # Update document status and progress
                document.status = status
                document.progress = int(progress_target * 100)
                db.add(document)
                db.commit()
                db.refresh(document)
                logger.info(f"Document {document_id} status updated to {status.value} with progress {document.progress}%")

            # Simulate potential failure
            if random.random() < 0.05: # 5% chance of failure
                await asyncio.sleep(1)
                document.status = DocumentStatus.FAILED
                document.error_message = "Simulated processing failure due to unexpected error."
                document.progress = 100
                db.add(document)
                db.commit()
                db.refresh(document)
                logger.error(f"Document {document_id} processing FAILED.")
            else:
                logger.info(f"Document {document_id} processing COMPLETED successfully.")

        except Exception as e:
            logger.error(f"Error during document processing for ID {document_id}: {e}")
            document = db.query(Document).filter(Document.id == document_id).first()
            if document:
                document.status = DocumentStatus.FAILED
                document.error_message = f"An unexpected error occurred during processing: {e}"
                document.progress = 100
                db.add(document)
                db.commit()
                db.refresh(document)

document_processing_service = DocumentProcessingService()