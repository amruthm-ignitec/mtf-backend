"""
File citation service for generating file citations from document IDs.
Uses existing document relationships to get file names.
"""
import logging
from typing import Optional, Dict, Any
from sqlalchemy.orm import Session
from app.models.document import Document

logger = logging.getLogger(__name__)


def get_file_citation(document_id: int, page_number: Optional[int] = None, db: Session = None) -> str:
    """
    Get file citation string from document ID.
    
    Args:
        document_id: ID of the document
        page_number: Optional page number
        db: Database session (optional, will query if provided)
    
    Returns:
        Formatted citation string like "filename.pdf (Page X)" or "filename.pdf"
    """
    if db is None:
        return f"Document {document_id}" + (f" (Page {page_number})" if page_number else "")
    
    try:
        document = db.query(Document).filter(Document.id == document_id).first()
        if document:
            filename = document.original_filename or document.filename
            if page_number is not None:
                return f"{filename} (Page {page_number})"
            return filename
        return f"Document {document_id}" + (f" (Page {page_number})" if page_number else "")
    except Exception as e:
        logger.error(f"Error getting file citation for document {document_id}: {e}")
        return f"Document {document_id}" + (f" (Page {page_number})" if page_number else "")


def get_file_citation_dict(document_id: int, page_number: Optional[int] = None, db: Session = None) -> Dict[str, Any]:
    """
    Get file citation as a dictionary with structured data.
    
    Args:
        document_id: ID of the document
        page_number: Optional page number
        db: Database session (optional, will query if provided)
    
    Returns:
        Dictionary with document_id, file_name, and page fields
    """
    citation = {
        "document_id": document_id,
        "file_name": None,
        "page": page_number
    }
    
    if db is None:
        return citation
    
    try:
        document = db.query(Document).filter(Document.id == document_id).first()
        if document:
            citation["file_name"] = document.original_filename or document.filename
    except Exception as e:
        logger.error(f"Error getting file citation dict for document {document_id}: {e}")
    
    return citation


def get_file_citations_batch(document_ids: list[int], db: Session) -> Dict[int, str]:
    """
    Get file citations for multiple documents in a single query (more efficient).
    
    Args:
        document_ids: List of document IDs
        db: Database session
    
    Returns:
        Dictionary mapping document_id to filename
    """
    if not document_ids:
        return {}
    
    try:
        documents = db.query(Document).filter(Document.id.in_(document_ids)).all()
        return {
            doc.id: doc.original_filename or doc.filename
            for doc in documents
        }
    except Exception as e:
        logger.error(f"Error getting batch file citations: {e}")
        return {doc_id: f"Document {doc_id}" for doc_id in document_ids}

