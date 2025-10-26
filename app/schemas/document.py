from pydantic import BaseModel
from typing import Optional
from datetime import datetime
from app.models.document import DocumentStatus, DocumentType

class DocumentBase(BaseModel):
    filename: str
    document_type: Optional[DocumentType] = None

class DocumentCreate(DocumentBase):
    pass

class DocumentUpdate(BaseModel):
    document_type: Optional[DocumentType] = None
    status: Optional[DocumentStatus] = None
    progress: Optional[float] = None
    processing_result: Optional[str] = None
    error_message: Optional[str] = None

class DocumentResponse(DocumentBase):
    id: int
    original_filename: str
    file_size: int
    file_type: str
    status: DocumentStatus
    progress: float
    azure_blob_url: Optional[str] = None
    processing_result: Optional[str] = None
    error_message: Optional[str] = None
    created_at: datetime
    updated_at: Optional[datetime] = None
    donor_id: int
    uploaded_by: int
    
    class Config:
        from_attributes = True

class DocumentUploadResponse(BaseModel):
    message: str
    document_id: int
    status: DocumentStatus
