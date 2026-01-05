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
from app.services.processing.utils.helper_functions import processing_dc
from app.services.lab_test_extraction import extract_all_lab_tests
from app.services.criteria_extraction import extract_all_criteria_data_batched

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
                
                # Embeddings are now 3072 dimensions (text-embedding-3-large default)
                # No truncation needed - database schema supports 3072 dimensions
                
                # Extract page number from metadata
                page_number = None
                if hasattr(chunk_doc, 'metadata') and chunk_doc.metadata:
                    page_number = chunk_doc.metadata.get('page', None)
                    # Ensure page is an integer if it exists
                    if page_number is not None:
                        try:
                            page_number = int(page_number) if isinstance(page_number, (int, str)) and str(page_number).isdigit() else None
                        except (ValueError, TypeError):
                            page_number = None
                
                # Log if page number is missing (for debugging)
                if page_number is None and idx < 5:  # Log first 5 chunks to avoid spam
                    logger.debug(f"Chunk {idx} has no page number. Metadata: {chunk_doc.metadata if hasattr(chunk_doc, 'metadata') else 'No metadata'}")
                
                chunk_data = {
                    'text': chunk_text,
                    'index': idx,
                    'page': page_number,
                    'embedding': chunk_embedding,  # Store embedding for pgvector
                    'metadata': chunk_doc.metadata if hasattr(chunk_doc, 'metadata') else {}
                }
                chunks_data.append(chunk_data)
            
            db_storage_service.store_document_chunks(document_id, chunks_data, db)
            
            # Update progress: 30-40% - Load prompts
            document.progress = 35.0
            db.commit()
            
            # Load minimal prompt components for lab test extraction
            logger.info("Loading prompt components...")
            import json
            config_dir = os.path.join(os.path.dirname(__file__), 'processing', 'config')
            
            with open(os.path.join(config_dir, 'role.json'), 'r') as f:
                role = json.load(f)
            with open(os.path.join(config_dir, 'instruction.json'), 'r') as f:
                basic_instruction = json.load(f)
            with open(os.path.join(config_dir, 'reminder_instruction.json'), 'r') as f:
                reminder_instructions = json.load(f)
            with open(os.path.join(config_dir, 'new_serology_dictionary.json'), 'r') as f:
                serology_dictionary = json.load(f)
            with open(os.path.join(config_dir, 'new_culture_dictionary.json'), 'r') as f:
                culture_dictionary = json.load(f)
            
            # Update progress: 40-60% - Extraction
            document.progress = 45.0
            db.commit()
            
            # Extract required lab tests (serology and culture) in a single LLM call
            logger.info("Running combined lab test extraction (serology + culture)...")
            serology_count, culture_count = await loop.run_in_executor(
                None,
                extract_all_lab_tests,
                document_id, vectordb, self.llm, db, role,
                basic_instruction, reminder_instructions,
                serology_dictionary, culture_dictionary
            )
            
            logger.info(f"Extracted {serology_count} serology tests and {culture_count} culture tests in one LLM call")
            
            document.progress = 60.0
            db.commit()
            
            # Extract criteria-specific data (all 79 criteria in one LLM call)
            logger.info("Running batched criteria data extraction (all 79 criteria in one call)...")
            criteria_count = await loop.run_in_executor(
                None,
                extract_all_criteria_data_batched,
                document_id, document.donor_id, vectordb, self.llm, db, page_doc_list
            )
            
            logger.info(f"Extracted data for {criteria_count} criteria evaluations in one LLM call")
            
            document.progress = 60.0
            db.commit()
            
            # Update progress: 60-70% - Semantic Extraction
            logger.info("Running semantic extraction (recovery, terminal, document presence)...")
            from app.services.semantic_extraction import (
                extract_recovery_information,
                extract_terminal_information,
                detect_document_presence,
                extract_simple_medical_records,
                extract_critical_lab_values
            )
            
            semantic_data = {}
            try:
                semantic_data['recovery_information'] = await loop.run_in_executor(
                    None,
                    extract_recovery_information,
                    vectordb, page_doc_list
                )
                semantic_data['terminal_information'] = await loop.run_in_executor(
                    None,
                    extract_terminal_information,
                    vectordb, page_doc_list
                )
                document_presence_data = await loop.run_in_executor(
                    None,
                    detect_document_presence,
                    vectordb, page_doc_list, db, document_id
                )
                semantic_data.update(document_presence_data)
                semantic_data['critical_lab_values'] = await loop.run_in_executor(
                    None,
                    extract_critical_lab_values,
                    vectordb, page_doc_list
                )
                # Try simple medical records extraction
                simple_mrr = await loop.run_in_executor(
                    None,
                    extract_simple_medical_records,
                    vectordb, page_doc_list
                )
                if simple_mrr:
                    semantic_data['medical_records_review_summary'] = simple_mrr
            except Exception as e:
                logger.error(f"Error in semantic extraction for document {document_id}: {e}", exc_info=True)
            
            document.progress = 70.0
            db.commit()
            
            # Update progress: 70-80% - Document-Specific Extraction
            logger.info("Running document-specific data extraction (DRAI, MRR, Plasma Dilution)...")
            
            # Extract DRAI using comprehensive extraction (processes ALL pages)
            from app.services.drai_extraction import extract_drai_comprehensive
            from app.services.document_specific_extraction import extract_document_specific_data_batched
            
            drai_data = {}
            try:
                drai_data = await loop.run_in_executor(
                    None,
                    extract_drai_comprehensive,
                    document_id, db, self.llm, page_doc_list
                )
                logger.info(f"DRAI extraction completed for document {document_id}: present={drai_data.get('present', False)}")
            except Exception as e:
                logger.error(f"Error in DRAI extraction for document {document_id}: {e}", exc_info=True)
                drai_data = {'present': False, 'pages': [], 'summary': {}, 'extracted_data': {}}
            
            # Extract other document-specific data (MRR, Plasma Dilution, ID Summary)
            # Note: DRAI is now handled separately, so this call won't extract DRAI
            document_specific_data = {}
            try:
                document_specific_data = await loop.run_in_executor(
                    None,
                    extract_document_specific_data_batched,
                    document_id, vectordb, self.llm, page_doc_list, db
                )
            except Exception as e:
                logger.error(f"Error in document-specific extraction for document {document_id}: {e}", exc_info=True)
            
            # Merge DRAI data with other document-specific data
            # DRAI data structure: {'present': bool, 'pages': [], 'summary': {}, 'extracted_data': {}}
            # Other document-specific data structure: {'donor_risk_assessment_interview': {...}, 'medical_records_review_summary': {...}, ...}
            # Replace the DRAI entry in document_specific_data with our comprehensive extraction
            if drai_data.get('present', False):
                document_specific_data['donor_risk_assessment_interview'] = drai_data
            else:
                # If DRAI not found, ensure empty structure is present
                document_specific_data['donor_risk_assessment_interview'] = drai_data
            
            # Merge semantic and document-specific data
            extracted_data = {**semantic_data, **document_specific_data}
            
            document.progress = 80.0
            db.commit()
            
            # Update progress: 80-100% - Completion
            document.progress = 90.0
            db.commit()
            
            # Store summary JSON in processing_result field (for backward compatibility)
            # Also store extracted_data in processing_result for aggregation
            summary_result = {
                "lab_tests_extracted": serology_count + culture_count,
                "criteria_extracted": criteria_count,
                "extracted_data": extracted_data  # Store extracted_data for aggregation
            }
            document.processing_result = json.dumps(summary_result)
            
            # Mark as completed and commit to release main session early
            document.status = DocumentStatus.COMPLETED
            document.progress = 100.0
            db.commit()
            db.refresh(document)
            
            logger.info(f"Document {document_id} processing completed successfully")
            
            # Store donor_id before closing main session
            donor_id = document.donor_id
            
            # Close main session to release connection back to pool
            # This prevents connection pool exhaustion during aggregation
            db.close()
            
            # Trigger aggregation service with separate session
            # This ensures aggregation doesn't block the main processing flow
            from app.services.extraction_aggregation import extraction_aggregation_service
            from app.database.database import SessionLocal
            
            # Create new session specifically for aggregation
            agg_db = SessionLocal()
            try:
                await extraction_aggregation_service.aggregate_donor_results(donor_id, agg_db)
            except Exception as agg_error:
                # Log aggregation error but don't fail document processing
                # Aggregation can be retried on next document completion
                logger.error(f"Error aggregating results for donor {donor_id}: {agg_error}", exc_info=True)
            finally:
                agg_db.close()
            
        except asyncio.TimeoutError as e:
            logger.error(f"Document {document_id} processing timed out: {e}", exc_info=True)
            # Timeout is handled by worker wrapper, but we should still mark it here if possible
            if document:
                try:
                    if db.is_active:
                        document.status = DocumentStatus.FAILED
                        document.error_message = f"Processing timed out: {str(e)}"
                        document.progress = 100.0
                        db.commit()
                except Exception as update_error:
                    logger.error(f"Failed to update document {document_id} after timeout: {update_error}", exc_info=True)
            raise  # Re-raise so worker can handle it
        except Exception as e:
            logger.error(f"Error processing document {document_id}: {e}", exc_info=True)
            
            # Check if it's an LLM-related error
            error_str = str(e).lower()
            is_llm_error = any(keyword in error_str for keyword in [
                'timeout', 'rate limit', 'api error', 'llm', 'openai', 'connection'
            ])
            
            error_message = f"Processing failed: {str(e)}"
            if is_llm_error:
                error_message = f"LLM/API error during processing: {str(e)}. Document will be retried."
                logger.warning(f"LLM-related error for document {document_id}, will be retried")
            
            # Update document status to failed
            # Only update if db session is still open (exception occurred before we closed it)
            if document:
                try:
                    # Check if session is still active
                    if db.is_active:
                        document.status = DocumentStatus.FAILED
                        document.error_message = error_message
                        document.progress = 100.0
                        db.commit()
                        db.refresh(document)
                    else:
                        # Session was closed, create new one for error update
                        from app.database.database import SessionLocal
                        error_db = SessionLocal()
                        try:
                            error_document = error_db.query(Document).filter(Document.id == document_id).first()
                            if error_document:
                                error_document.status = DocumentStatus.FAILED
                                error_document.error_message = error_message
                                error_document.progress = 100.0
                                error_db.commit()
                        finally:
                            error_db.close()
                except Exception as update_error:
                    logger.error(f"Failed to update document {document_id} status to FAILED: {update_error}", exc_info=True)
        
        finally:
            # Clean up temporary file
            if temp_pdf_path and os.path.exists(temp_pdf_path):
                pdf_service.cleanup_temp_file(temp_pdf_path)
                logger.debug(f"Cleaned up temporary PDF file: {temp_pdf_path}")


# Global instance
document_processing_service = DocumentProcessingService()
