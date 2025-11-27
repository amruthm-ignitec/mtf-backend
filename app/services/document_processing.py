"""
Document processing service for extracting medical information from PDFs.
Replaces simulated processing with real AI-powered extraction.
"""
import asyncio
import logging
import os
import tempfile
from typing import Optional
from sqlalchemy.orm import Session
from app.models.document import Document, DocumentStatus
from app.services.pdf_service import pdf_service
from app.services.db_storage import db_storage_service
from app.services.processing.utils.llm_config import llm_setup
from app.services.processing.utils.helper_functions import get_prompt_components, processing_dc
from app.services.processing.serology import get_qa_results
from app.services.processing.topic_summarization import get_topic_summary_results
from app.services.processing.document_components import get_document_components

logger = logging.getLogger(__name__)


class DocumentProcessingService:
    """Service for processing documents and extracting medical information."""
    
    def __init__(self):
        self.llm = None
        self.embeddings = None
        self._initialized = False
    
    async def _ensure_initialized(self):
        """Initialize LLM and embeddings if not already done."""
        if not self._initialized:
            try:
                logger.info("Initializing LLM and embeddings...")
                # Run synchronous llm_setup in executor
                loop = asyncio.get_event_loop()
                self.llm, self.embeddings = await loop.run_in_executor(None, llm_setup)
                self._initialized = True
                logger.info("LLM and embeddings initialized successfully")
            except Exception as e:
                logger.error(f"Failed to initialize LLM and embeddings: {e}")
                raise
    
    async def process_document(self, document_id: int, db: Session):
        """
        Process a document: download, extract, and store results.
        
        Args:
            document_id: ID of the document to process
            db: Database session
        """
        document = None
        temp_pdf_path = None
        
        try:
            # Get document
            document = db.query(Document).filter(Document.id == document_id).first()
            if not document:
                logger.error(f"Document {document_id} not found")
                return
            
            # Ensure document is in correct status
            if document.status != DocumentStatus.PROCESSING:
                logger.warning(f"Document {document_id} is not in PROCESSING status (current: {document.status})")
                return
            
            logger.info(f"Processing document {document_id}: {document.original_filename}")
            
            # Update progress: 0-10% - Initialization
            document.progress = 5.0
            db.commit()
            
            # Initialize LLM and embeddings
            await self._ensure_initialized()
            
            # Update progress: 10-20% - Download
            document.progress = 15.0
            db.commit()
            
            # Download PDF from Azure Blob Storage
            if not document.azure_blob_url:
                raise ValueError(f"Document {document_id} has no Azure blob URL")
            
            logger.info(f"Downloading PDF from Azure Blob: {document.azure_blob_url}")
            # Pass the filename from database for more reliable blob name resolution
            temp_pdf_path = await pdf_service.download_from_blob(
                document.azure_blob_url, 
                blob_filename=document.filename
            )
            
            if not temp_pdf_path or not os.path.exists(temp_pdf_path):
                raise FileNotFoundError(f"Failed to download PDF for document {document_id}")
            
            # Update progress: 20-30% - PDF Processing
            document.status = DocumentStatus.ANALYZING
            document.progress = 25.0
            db.commit()
            
            # Process PDF: load, chunk, and create embeddings
            logger.info(f"Processing PDF and creating embeddings...")
            loop = asyncio.get_event_loop()
            page_doc_list, doc_list, vectordb = await loop.run_in_executor(
                None,
                processing_dc,
                temp_pdf_path,
                self.embeddings,
                False,  # save_embeddings
                False   # delete_after
            )
            
            # Store document chunks in pgvector
            logger.info("Storing document chunks in database...")
            chunks_data = []
            for idx, chunk_doc in enumerate(doc_list):
                # Generate embedding for chunk
                chunk_text = chunk_doc.page_content
                chunk_embedding = await loop.run_in_executor(
                    None,
                    lambda: self.embeddings.embed_query(chunk_text)
                )
                
                chunk_data = {
                    'text': chunk_text,
                    'index': idx,
                    'page': chunk_doc.metadata.get('page', None) if hasattr(chunk_doc, 'metadata') else None,
                    'embedding': chunk_embedding,  # Store embedding for pgvector
                    'metadata': chunk_doc.metadata if hasattr(chunk_doc, 'metadata') else {}
                }
                chunks_data.append(chunk_data)
            
            db_storage_service.store_document_chunks(document_id, chunks_data, db)
            
            # Update progress: 30-40% - Load prompts
            document.progress = 35.0
            db.commit()
            
            # Get prompt components
            logger.info("Loading prompt components...")
            role, disease_context, basic_instruction, reminder_instructions, \
            serology_dictionary, t1_context, t1_tips, t1_fewshot, topic_df, \
            t3_context, t3_instruction, t3_fewshot, subtissue_map, MS_MO_category_map = await loop.run_in_executor(
                None,
                get_prompt_components
            )
            
            # Update progress: 40-60% - Extraction
            document.progress = 45.0
            db.commit()
            
            # Run Culture and Serology extraction
            logger.info("Running Culture and Serology extraction...")
            culture_res, serology_res = await loop.run_in_executor(
                None,
                get_qa_results,
                self.llm, vectordb, disease_context, role, basic_instruction,
                reminder_instructions, serology_dictionary, subtissue_map,
                MS_MO_category_map
            )
            
            # Store culture and serology results
            db_storage_service.store_culture_results(document_id, culture_res, db)
            db_storage_service.store_serology_results(document_id, serology_res, db)
            
            document.progress = 55.0
            db.commit()
            
            # Run Topic Summarization
            logger.info("Running Topic Summarization...")
            topics_results = await loop.run_in_executor(
                None,
                get_topic_summary_results,
                vectordb, topic_df, t1_context, t1_tips, t1_fewshot,
                t3_context, t3_instruction, t3_fewshot, self.llm, page_doc_list
            )
            
            # Store topic results
            db_storage_service.store_topic_results(document_id, topics_results, db)
            
            document.progress = 70.0
            db.commit()
            
            # Run Document Components extraction
            logger.info("Running Document Components extraction...")
            components_results = await loop.run_in_executor(
                None,
                get_document_components,
                self.llm, page_doc_list, vectordb, topics_results
            )
            
            # Store component results
            db_storage_service.store_component_results(document_id, components_results, db)
            
            # Update progress: 80-100% - Completion
            document.progress = 90.0
            db.commit()
            
            # Store summary JSON in processing_result field (for backward compatibility)
            import json
            summary_result = {
                "culture": culture_res,
                "serology": serology_res,
                "topics": topics_results,
                "components": components_results
            }
            document.processing_result = json.dumps(summary_result)
            
            # Mark as completed
            document.status = DocumentStatus.COMPLETED
            document.progress = 100.0
            db.commit()
            db.refresh(document)
            
            logger.info(f"Document {document_id} processing completed successfully")
            
            # Trigger aggregation service
            from app.services.extraction_aggregation import extraction_aggregation_service
            await extraction_aggregation_service.aggregate_donor_results(document.donor_id, db)
            
        except Exception as e:
            logger.error(f"Error processing document {document_id}: {e}", exc_info=True)
            
            # Update document status to failed
            if document:
                document.status = DocumentStatus.FAILED
                document.error_message = f"Processing failed: {str(e)}"
                document.progress = 100.0
                db.commit()
                db.refresh(document)
        
        finally:
            # Clean up temporary file
            if temp_pdf_path and os.path.exists(temp_pdf_path):
                pdf_service.cleanup_temp_file(temp_pdf_path)
                logger.debug(f"Cleaned up temporary PDF file: {temp_pdf_path}")


# Global instance
document_processing_service = DocumentProcessingService()
