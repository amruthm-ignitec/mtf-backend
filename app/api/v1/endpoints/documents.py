from fastapi import APIRouter, Depends, HTTPException, status, UploadFile, File
from fastapi.responses import StreamingResponse
from sqlalchemy.orm import Session
from typing import List
import os
import uuid
import logging
import asyncio
import io
from app.database.database import get_db
from app.models.document import Document, DocumentStatus, DocumentType
from app.models.user import User
from app.models.donor import Donor
from app.schemas.document import DocumentResponse, DocumentUpdate, DocumentUploadResponse
from app.api.v1.endpoints.auth import get_current_user
from app.core.config import settings
from app.services.azure_service import azure_blob_service
from app.services.processing.result_parser import result_parser

logger = logging.getLogger(__name__)
router = APIRouter()

@router.get("/", response_model=List[DocumentResponse])
async def get_documents(
    skip: int = 0,
    limit: int = 100,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """Get all documents with pagination."""
    documents = db.query(Document).offset(skip).limit(limit).all()
    return documents

@router.get("/{document_id}", response_model=DocumentResponse)
async def get_document(
    document_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """Get a specific document by ID."""
    document = db.query(Document).filter(Document.id == document_id).first()
    if not document:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Document not found"
        )
    return document

@router.post("/upload", response_model=DocumentUploadResponse)
async def upload_document(
    donor_id: int,
    file: UploadFile = File(...),
    document_type: DocumentType = None,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """Upload a document for a donor."""
    # Validate donor exists
    donor = db.query(Donor).filter(Donor.id == donor_id).first()
    if not donor:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Donor with ID {donor_id} not found"
        )
    
    # Validate file size
    file_size_mb = file.size / (1024 * 1024)
    if file_size_mb > settings.MAX_FILE_SIZE_MB:
        raise HTTPException(
            status_code=status.HTTP_413_REQUEST_ENTITY_TOO_LARGE,
            detail=f"File size exceeds maximum allowed size of {settings.MAX_FILE_SIZE_MB}MB"
        )
    
    # Validate file type
    file_extension = file.filename.split('.')[-1].lower()
    if file_extension not in settings.allowed_file_types_list:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"File type not allowed. Allowed types: {', '.join(settings.allowed_file_types_list)}"
        )
    
    # Generate unique filename
    unique_filename = f"{uuid.uuid4()}_{file.filename}"
    
    # Upload file to Azure Blob Storage
    file_content = await file.read()
    azure_blob_url = await azure_blob_service.upload_file(
        file_content=file_content,
        filename=unique_filename,
        content_type=file.content_type
    )
    
    if not azure_blob_url:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to upload file to storage"
        )
    
    # Create document record
    document = Document(
        filename=unique_filename,
        original_filename=file.filename,
        file_size=file.size,
        file_type=file.content_type,
        document_type=document_type,
        status=DocumentStatus.UPLOADED,
        azure_blob_url=azure_blob_url,
        donor_id=donor_id,
        uploaded_by=current_user.id
    )
    
    db.add(document)
    db.commit()
    db.refresh(document)
    
    logger.info(f"Document uploaded: {file.filename} for donor {donor_id} by user: {current_user.email}")
    
    # Document is queued for processing (status = UPLOADED)
    # Background worker will pick it up from the queue
    
    return DocumentUploadResponse(
        message="Document uploaded successfully",
        document_id=document.id,
        status=document.status
    )

@router.put("/{document_id}", response_model=DocumentResponse)
async def update_document(
    document_id: int,
    document_update: DocumentUpdate,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """Update document metadata."""
    document = db.query(Document).filter(Document.id == document_id).first()
    if not document:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Document not found"
        )
    
    update_data = document_update.dict(exclude_unset=True)
    for field, value in update_data.items():
        setattr(document, field, value)
    
    db.commit()
    db.refresh(document)
    
    logger.info(f"Document updated: {document.original_filename} by user: {current_user.email}")
    return document

@router.delete("/{document_id}")
async def delete_document(
    document_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """Delete a document."""
    document = db.query(Document).filter(Document.id == document_id).first()
    if not document:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Document not found"
        )
    
    # Delete file from Azure Blob Storage
    await azure_blob_service.delete_file(document.filename)
    
    filename = document.original_filename
    db.delete(document)
    db.commit()
    
    logger.info(f"Document deleted: {filename} by user: {current_user.email}")
    return {"message": "Document deleted successfully"}

@router.put("/{document_id}/status", response_model=DocumentResponse)
async def update_document_status(
    document_id: int,
    status_update: DocumentUpdate,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """Update document processing status and progress."""
    document = db.query(Document).filter(Document.id == document_id).first()
    if not document:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Document not found"
        )
    
    update_data = status_update.dict(exclude_unset=True)
    for field, value in update_data.items():
        setattr(document, field, value)
    
    db.commit()
    db.refresh(document)
    
    logger.info(f"Document status updated: {document.original_filename} by user: {current_user.email}")
    return document

@router.get("/{document_id}/status", response_model=DocumentResponse)
async def get_document_status(
    document_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """Get real-time document processing status."""
    document = db.query(Document).filter(Document.id == document_id).first()
    if not document:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Document not found"
        )
    
    return document

@router.get("/donor/{donor_id}")
async def get_donor_documents(
    donor_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """Get all documents for a specific donor."""
    try:
        documents = db.query(Document).filter(Document.donor_id == donor_id).all()
        result = []
        for doc in documents:
            result.append({
                "id": doc.id,
                "filename": doc.filename,
                "original_filename": doc.original_filename,
                "file_size": doc.file_size,
                "file_type": doc.file_type,
                "document_type": doc.document_type.value if doc.document_type else None,
                "status": doc.status.value,
                "progress": doc.progress,
                "azure_blob_url": doc.azure_blob_url,
                "processing_result": doc.processing_result,
                "error_message": doc.error_message,
                "created_at": doc.created_at.isoformat(),
                "updated_at": doc.updated_at.isoformat() if doc.updated_at else None,
                "donor_id": doc.donor_id,
                "uploaded_by": doc.uploaded_by
            })
        return result
    except Exception as e:
        logger.error(f"Error fetching documents for donor {donor_id}: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Error fetching documents: {str(e)}"
        )

@router.get("/{document_id}/extraction")
async def get_document_extraction(
    document_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """Get all extraction results for a specific document."""
    document = db.query(Document).filter(Document.id == document_id).first()
    if not document:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Document not found"
        )
    
    # Get extraction results from database
    extraction_results = result_parser.get_all_extraction_results_for_document(document_id, db)
    
    return {
        "document_id": document_id,
        "extraction_results": extraction_results
    }

@router.get("/{document_id}/culture")
async def get_document_culture(
    document_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """Get culture results for a specific document."""
    document = db.query(Document).filter(Document.id == document_id).first()
    if not document:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Document not found"
        )
    
    return result_parser.get_culture_results_for_document(document_id, db)

@router.get("/{document_id}/serology")
async def get_document_serology(
    document_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """Get serology results for a specific document."""
    document = db.query(Document).filter(Document.id == document_id).first()
    if not document:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Document not found"
        )
    
    return result_parser.get_serology_results_for_document(document_id, db)

@router.get("/{document_id}/topics")
async def get_document_topics(
    document_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """Get topic results for a specific document."""
    document = db.query(Document).filter(Document.id == document_id).first()
    if not document:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Document not found"
        )
    
    return result_parser.get_topic_results_for_document(document_id, db)

@router.get("/{document_id}/components")
async def get_document_components(
    document_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """Get component results for a specific document."""
    document = db.query(Document).filter(Document.id == document_id).first()
    if not document:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Document not found"
        )
    
    return result_parser.get_component_results_for_document(document_id, db)

@router.get("/{document_id}/sas-url")
async def get_document_sas_url(
    document_id: int,
    expiry_minutes: int = 30,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """
    Get a SAS (Shared Access Signature) URL for a document that's valid for a specified duration.
    This allows temporary, secure access to private Azure Blob Storage documents.
    
    Args:
        document_id: ID of the document
        expiry_minutes: Number of minutes the SAS URL should be valid (default: 30, max: 60)
        
    Returns:
        Dictionary with sas_url and expiry information
    """
    document = db.query(Document).filter(Document.id == document_id).first()
    if not document:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Document not found"
        )
    
    # Validate expiry_minutes (max 60 minutes for security)
    if expiry_minutes < 1 or expiry_minutes > 60:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="expiry_minutes must be between 1 and 60"
        )
    
    if not document.filename:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Document has no filename"
        )
    
    # Generate SAS URL
    sas_url = await azure_blob_service.generate_sas_url(
        filename=document.filename,
        expiry_minutes=expiry_minutes
    )
    
    if not sas_url:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to generate SAS URL for document"
        )
    
    logger.info(f"Generated SAS URL for document {document_id} by user: {current_user.email}")
    
    return {
        "document_id": document_id,
        "sas_url": sas_url,
        "expiry_minutes": expiry_minutes,
        "original_filename": document.original_filename
    }

@router.get("/{document_id}/pdf")
async def get_document_pdf(
    document_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """
    Stream a PDF document from Azure Blob Storage with proper CORS headers.
    This endpoint proxies the PDF to avoid CORS issues when loading in PDF.js.
    
    Args:
        document_id: ID of the document
        
    Returns:
        StreamingResponse with PDF content and proper headers
    """
    document = db.query(Document).filter(Document.id == document_id).first()
    if not document:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Document not found"
        )
    
    if not document.filename:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Document has no filename"
        )
    
    if not azure_blob_service.is_enabled():
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Azure Blob Storage is not configured"
        )
    
    try:
        # Get blob client
        blob_client = azure_blob_service.blob_service_client.get_blob_client(
            container=azure_blob_service.container_name,
            blob=document.filename
        )
        
        # Check if blob exists
        if not blob_client.exists():
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="PDF file not found in Azure Blob Storage"
            )
        
        # Download blob content
        blob_data = blob_client.download_blob().readall()
        
        logger.info(f"Streaming PDF for document {document_id} to user: {current_user.email}, size: {len(blob_data)} bytes")
        
        return StreamingResponse(
            io.BytesIO(blob_data),
            media_type="application/pdf",
            headers={
                "Content-Disposition": f'inline; filename="{document.original_filename}"',
                "Content-Length": str(len(blob_data)),
                "Access-Control-Allow-Origin": "*",  # Allow CORS for PDF.js
                "Access-Control-Allow-Methods": "GET",
                "Access-Control-Allow-Headers": "*",
                "Cache-Control": "no-cache",
            }
        )
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error streaming PDF for document {document_id}: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to stream PDF: {str(e)}"
        )
