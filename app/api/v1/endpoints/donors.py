from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session
from typing import List
import logging
from app.database.database import get_db
from app.models.donor import Donor
from app.models.user import User, UserRole
from app.schemas.donor import DonorCreate, DonorUpdate, DonorResponse, DonorPriorityUpdate
from app.api.v1.endpoints.auth import get_current_user

logger = logging.getLogger(__name__)
router = APIRouter()

@router.get("/", response_model=List[DonorResponse])
async def get_donors(
    skip: int = 0, 
    limit: int = 100, 
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """Get all donors with pagination."""
    donors = db.query(Donor).offset(skip).limit(limit).all()
    return donors

@router.get("/{donor_id}", response_model=DonorResponse)
async def get_donor(
    donor_id: int, 
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """Get a specific donor by ID."""
    donor = db.query(Donor).filter(Donor.id == donor_id).first()
    if not donor:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Donor not found"
        )
    return donor

@router.post("/", response_model=DonorResponse)
async def create_donor(
    donor: DonorCreate, 
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """Create a new donor."""
    # Check if donor ID already exists
    existing_donor = db.query(Donor).filter(Donor.unique_donor_id == donor.unique_donor_id).first()
    if existing_donor:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Donor with this ID already exists"
        )
    
    db_donor = Donor(**donor.dict())
    db.add(db_donor)
    db.commit()
    db.refresh(db_donor)
    
    logger.info(f"Donor created: {db_donor.unique_donor_id} by user: {current_user.email}")
    return db_donor

@router.put("/{donor_id}", response_model=DonorResponse)
async def update_donor(
    donor_id: int,
    donor_update: DonorUpdate,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """Update a donor."""
    donor = db.query(Donor).filter(Donor.id == donor_id).first()
    if not donor:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Donor not found"
        )
    
    update_data = donor_update.dict(exclude_unset=True)
    for field, value in update_data.items():
        setattr(donor, field, value)
    
    db.commit()
    db.refresh(donor)
    
    logger.info(f"Donor updated: {donor.unique_donor_id} by user: {current_user.email}")
    return donor

@router.put("/{donor_id}/priority", response_model=DonorResponse)
async def update_donor_priority(
    donor_id: int,
    priority_update: DonorPriorityUpdate,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """Update donor priority status."""
    donor = db.query(Donor).filter(Donor.id == donor_id).first()
    if not donor:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Donor not found"
        )
    
    donor.is_priority = priority_update.is_priority
    db.commit()
    db.refresh(donor)
    
    logger.info(f"Donor priority updated: {donor.unique_donor_id} to {priority_update.is_priority} by user: {current_user.email}")
    return donor

@router.delete("/{donor_id}")
async def delete_donor(
    donor_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """Delete a donor (Admin only)."""
    if current_user.role != UserRole.ADMIN:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Not enough permissions"
        )
    
    donor = db.query(Donor).filter(Donor.id == donor_id).first()
    if not donor:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Donor not found"
        )
    
    donor_id_str = donor.unique_donor_id
    db.delete(donor)
    db.commit()
    
    logger.info(f"Donor deleted: {donor_id_str} by admin: {current_user.email}")
    return {"message": "Donor deleted successfully"}
