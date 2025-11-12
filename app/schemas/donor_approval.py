from pydantic import BaseModel, Field
from typing import Optional, Dict, Any
from datetime import datetime
from app.models.donor_approval import ApprovalStatus, ApprovalType

class DonorApprovalCreate(BaseModel):
    donor_id: int
    document_id: Optional[int] = None  # None if approving entire donor summary
    approval_type: ApprovalType = ApprovalType.DONOR_SUMMARY
    status: ApprovalStatus
    comment: str = Field(..., min_length=1, description="Comment explaining the approval/rejection decision")
    checklist_data: Optional[Dict[str, Any]] = None  # Checklist status at time of decision

class DonorApprovalUpdate(BaseModel):
    status: Optional[ApprovalStatus] = None
    comment: Optional[str] = Field(None, min_length=1)

class DonorApprovalResponse(BaseModel):
    id: int
    donor_id: int
    document_id: Optional[int]
    approval_type: ApprovalType
    status: ApprovalStatus
    comment: str
    checklist_data: Optional[Dict[str, Any]]
    approved_by: int
    approver_name: Optional[str] = None
    approver_email: Optional[str] = None
    created_at: datetime
    updated_at: Optional[datetime] = None
    
    class Config:
        from_attributes = True

class PastDataResponse(BaseModel):
    """Response for past approval/rejection data"""
    donor_id: int
    past_decisions: list[DonorApprovalResponse]
    total_approved: int
    total_rejected: int
    total_pending: int
    
    class Config:
        from_attributes = True


