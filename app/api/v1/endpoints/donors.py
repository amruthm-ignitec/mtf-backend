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

@router.get("/{donor_id}/details")
async def get_donor_details(
    donor_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """Get detailed donor information for summary page."""
    donor = db.query(Donor).filter(Donor.id == donor_id).first()
    if not donor:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Donor not found"
        )
    
    # Return donor data in format expected by frontend
    return {
        "id": donor.id,
        "donorName": donor.name,
        "age": None,  # Add if you have age field
        "gender": donor.gender,
        "causeOfDeath": None,  # Add if you have this field
        "uploadTimestamp": donor.created_at.isoformat() if donor.created_at else None,
        "requiredDocuments": []  # Add if you have documents linked
    }

@router.get("/{donor_id}/extraction-data")
async def get_donor_extraction_data(
    donor_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """Get extraction data for a donor (temporary endpoint for testing)."""
    import json
    import os
    
    donor = db.query(Donor).filter(Donor.id == donor_id).first()
    if not donor:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Donor not found"
        )
    
    # For testing: Try to load test.json if it exists
    # In production, this would come from the database or processing service
    # Try multiple possible paths
    possible_paths = [
        os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(__file__))))), "mtf-backend-test", "test.json"),
        os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(__file__)))), "..", "mtf-backend-test", "test.json"),
        "/Users/amrutmaliye/Desktop/Dev/Github/donoriq/mtf-backend-test/test.json"
    ]
    
    test_json_path = None
    for path in possible_paths:
        if os.path.exists(path):
            test_json_path = path
            break
    
    if test_json_path and os.path.exists(test_json_path):
        try:
            with open(test_json_path, 'r') as f:
                extraction_data = json.load(f)
            # Update donor_id and case_id to match the requested donor
            extraction_data["donor_id"] = donor.unique_donor_id
            extraction_data["case_id"] = f"{donor.unique_donor_id}81"
            return extraction_data
        except Exception as e:
            logger.error(f"Error loading test.json: {e}")
    
    # Return empty structure if test.json not found
    return {
        "donor_id": donor.unique_donor_id,
        "case_id": f"{donor.unique_donor_id}81",
        "processing_timestamp": None,
        "processing_duration_seconds": 0,
        "extracted_data": {},
        "conditional_documents": {},
        "validation": None,
        "compliance_status": None,
        "document_summary": None
    }
