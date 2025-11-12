from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session
from typing import List
import json
import logging
from app.database.database import get_db
from app.models.donor import Donor
from app.models.donor_approval import DonorApproval, ApprovalStatus, ApprovalType
from app.models.user import User, UserRole
from app.models.document import Document
from app.schemas.donor_approval import (
    DonorApprovalCreate,
    DonorApprovalResponse,
    PastDataResponse
)
from app.api.v1.endpoints.auth import get_current_user

logger = logging.getLogger(__name__)
router = APIRouter()

def require_medical_director(current_user: User = Depends(get_current_user)):
    """Dependency to ensure user is a medical director or admin"""
    if current_user.role not in [UserRole.MEDICAL_DIRECTOR, UserRole.ADMIN]:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Only medical directors can approve/reject donors"
        )
    return current_user

@router.post("/", response_model=DonorApprovalResponse, status_code=status.HTTP_201_CREATED)
async def create_donor_approval(
    approval: DonorApprovalCreate,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_medical_director)
):
    """Approve or reject a donor or document. Requires medical director role."""
    # Verify donor exists
    donor = db.query(Donor).filter(Donor.id == approval.donor_id).first()
    if not donor:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Donor not found"
        )
    
    # If document_id is provided, verify document exists
    if approval.document_id:
        document = db.query(Document).filter(Document.id == approval.document_id).first()
        if not document:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Document not found"
            )
        if document.donor_id != approval.donor_id:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Document does not belong to this donor"
            )
    
    # Serialize checklist_data to JSON string
    checklist_json = None
    if approval.checklist_data:
        checklist_json = json.dumps(approval.checklist_data)
    
    # Create approval record
    db_approval = DonorApproval(
        donor_id=approval.donor_id,
        document_id=approval.document_id,
        approval_type=approval.approval_type,
        status=approval.status,
        comment=approval.comment,
        checklist_data=checklist_json,
        approved_by=current_user.id
    )
    
    db.add(db_approval)
    db.commit()
    db.refresh(db_approval)
    
    # Load approver info for response
    approver = db.query(User).filter(User.id == current_user.id).first()
    
    logger.info(
        f"Donor {approval.donor_id} {'approved' if approval.status == ApprovalStatus.APPROVED else 'rejected'} "
        f"by medical director {current_user.email}"
    )
    
    # Parse checklist_data back to dict for response
    checklist_dict = None
    if db_approval.checklist_data:
        try:
            checklist_dict = json.loads(db_approval.checklist_data)
        except:
            pass
    
    return DonorApprovalResponse(
        id=db_approval.id,
        donor_id=db_approval.donor_id,
        document_id=db_approval.document_id,
        approval_type=db_approval.approval_type,
        status=db_approval.status,
        comment=db_approval.comment,
        checklist_data=checklist_dict,
        approved_by=db_approval.approved_by,
        approver_name=approver.name if approver else None,
        approver_email=approver.email if approver else None,
        created_at=db_approval.created_at,
        updated_at=db_approval.updated_at
    )

@router.get("/donor/{donor_id}", response_model=List[DonorApprovalResponse])
async def get_donor_approvals(
    donor_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """Get all approval/rejection records for a specific donor."""
    # Verify donor exists
    donor = db.query(Donor).filter(Donor.id == donor_id).first()
    if not donor:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Donor not found"
        )
    
    approvals = db.query(DonorApproval).filter(
        DonorApproval.donor_id == donor_id
    ).order_by(DonorApproval.created_at.desc()).all()
    
    result = []
    for approval in approvals:
        approver = db.query(User).filter(User.id == approval.approved_by).first()
        checklist_dict = None
        if approval.checklist_data:
            try:
                checklist_dict = json.loads(approval.checklist_data)
            except:
                pass
        
        result.append(DonorApprovalResponse(
            id=approval.id,
            donor_id=approval.donor_id,
            document_id=approval.document_id,
            approval_type=approval.approval_type,
            status=approval.status,
            comment=approval.comment,
            checklist_data=checklist_dict,
            approved_by=approval.approved_by,
            approver_name=approver.name if approver else None,
            approver_email=approver.email if approver else None,
            created_at=approval.created_at,
            updated_at=approval.updated_at
        ))
    
    return result

@router.get("/donor/{donor_id}/past-data", response_model=PastDataResponse)
async def get_donor_past_data(
    donor_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """Get past approval/rejection data for a donor (Past Data feature)."""
    # Verify donor exists
    donor = db.query(Donor).filter(Donor.id == donor_id).first()
    if not donor:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Donor not found"
        )
    
    approvals = db.query(DonorApproval).filter(
        DonorApproval.donor_id == donor_id
    ).order_by(DonorApproval.created_at.desc()).all()
    
    past_decisions = []
    total_approved = 0
    total_rejected = 0
    total_pending = 0
    
    for approval in approvals:
        approver = db.query(User).filter(User.id == approval.approved_by).first()
        checklist_dict = None
        if approval.checklist_data:
            try:
                checklist_dict = json.loads(approval.checklist_data)
            except:
                pass
        
        past_decisions.append(DonorApprovalResponse(
            id=approval.id,
            donor_id=approval.donor_id,
            document_id=approval.document_id,
            approval_type=approval.approval_type,
            status=approval.status,
            comment=approval.comment,
            checklist_data=checklist_dict,
            approved_by=approval.approved_by,
            approver_name=approver.name if approver else None,
            approver_email=approver.email if approver else None,
            created_at=approval.created_at,
            updated_at=approval.updated_at
        ))
        
        if approval.status == ApprovalStatus.APPROVED:
            total_approved += 1
        elif approval.status == ApprovalStatus.REJECTED:
            total_rejected += 1
        else:
            total_pending += 1
    
    return PastDataResponse(
        donor_id=donor_id,
        past_decisions=past_decisions,
        total_approved=total_approved,
        total_rejected=total_rejected,
        total_pending=total_pending
    )

@router.get("/{approval_id}", response_model=DonorApprovalResponse)
async def get_approval(
    approval_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """Get a specific approval/rejection record."""
    approval = db.query(DonorApproval).filter(DonorApproval.id == approval_id).first()
    if not approval:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Approval record not found"
        )
    
    approver = db.query(User).filter(User.id == approval.approved_by).first()
    checklist_dict = None
    if approval.checklist_data:
        try:
            checklist_dict = json.loads(approval.checklist_data)
        except:
            pass
    
    return DonorApprovalResponse(
        id=approval.id,
        donor_id=approval.donor_id,
        document_id=approval.document_id,
        approval_type=approval.approval_type,
        status=approval.status,
        comment=approval.comment,
        checklist_data=checklist_dict,
        approved_by=approval.approved_by,
        approver_name=approver.name if approver else None,
        approver_email=approver.email if approver else None,
        created_at=approval.created_at,
        updated_at=approval.updated_at
    )


