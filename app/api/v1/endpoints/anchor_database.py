from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session
from typing import List
import logging
from app.database.database import get_db
from app.models.donor import Donor
from app.models.donor_anchor_decision import DonorAnchorDecision, AnchorOutcome, OutcomeSource
from app.models.user import User
from app.schemas.donor_anchor_decision import (
    DonorAnchorDecisionResponse,
    AnchorStatsResponse
)
from app.api.v1.endpoints.auth import get_current_user
from app.services.anchor_database_service import anchor_database_service

logger = logging.getLogger(__name__)
router = APIRouter()


@router.get("/{donor_id}", response_model=DonorAnchorDecisionResponse)
async def get_anchor_decision(
    donor_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """Get anchor decision for a specific donor."""
    anchor_decision = db.query(DonorAnchorDecision).filter(
        DonorAnchorDecision.donor_id == donor_id
    ).first()
    
    if not anchor_decision:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Anchor decision not found for this donor"
        )
    
    return anchor_decision


@router.get("/similar/{donor_id}")
async def get_similar_cases(
    donor_id: int,
    limit: int = 10,
    threshold: float = 0.85,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """Get similar past cases for a donor."""
    from app.services.parameter_snapshot_service import parameter_snapshot_service
    from app.services.vector_conversion import vector_conversion_service
    from app.services.anchor_database_service import _snapshot_to_text
    
    # Get parameter snapshot
    snapshot = parameter_snapshot_service.create_parameter_snapshot(donor_id, db)
    if not snapshot:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Could not create parameter snapshot for donor"
        )
    
    # Generate embedding
    snapshot_text = _snapshot_to_text(snapshot)
    embedding = await vector_conversion_service._generate_embedding(snapshot_text)
    
    if not embedding:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Could not generate embedding for similarity search"
        )
    
    # Find similar cases
    similar_cases = anchor_database_service.get_similar_cases(
        parameter_embedding=embedding,
        limit=limit,
        threshold=threshold,
        db=db
    )
    
    return {
        "donor_id": donor_id,
        "similar_cases": similar_cases,
        "threshold_used": threshold
    }


@router.post("/manual-outcome")
async def set_manual_outcome(
    donor_id: int,
    outcome: AnchorOutcome,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """Manually set outcome for anchor database."""
    donor = db.query(Donor).filter(Donor.id == donor_id).first()
    if not donor:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Donor not found"
        )
    
    anchor_decision = await anchor_database_service.create_anchor_decision(
        donor_id=donor_id,
        outcome=outcome,
        outcome_source=OutcomeSource.MANUAL_APPROVAL,
        db=db
    )
    
    if not anchor_decision:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to create anchor decision"
        )
    
    logger.info(f"Manual outcome set for donor {donor_id}: {outcome.value} by {current_user.email}")
    return anchor_decision


@router.get("/stats", response_model=AnchorStatsResponse)
async def get_anchor_stats(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """Get statistics about the anchor database."""
    total = db.query(DonorAnchorDecision).count()
    accepted = db.query(DonorAnchorDecision).filter(
        DonorAnchorDecision.outcome == AnchorOutcome.ACCEPTED
    ).count()
    rejected = db.query(DonorAnchorDecision).filter(
        DonorAnchorDecision.outcome == AnchorOutcome.REJECTED
    ).count()
    batch_import = db.query(DonorAnchorDecision).filter(
        DonorAnchorDecision.outcome_source == OutcomeSource.BATCH_IMPORT
    ).count()
    manual_approval = db.query(DonorAnchorDecision).filter(
        DonorAnchorDecision.outcome_source == OutcomeSource.MANUAL_APPROVAL
    ).count()
    predicted = db.query(DonorAnchorDecision).filter(
        DonorAnchorDecision.outcome_source == OutcomeSource.PREDICTED
    ).count()
    
    return AnchorStatsResponse(
        total_cases=total,
        accepted_count=accepted,
        rejected_count=rejected,
        batch_import_count=batch_import,
        manual_approval_count=manual_approval,
        predicted_count=predicted
    )

