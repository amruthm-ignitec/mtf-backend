from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session
from typing import Dict, Any
import logging
from app.database.database import get_db
from app.models.donor import Donor
from app.models.user import User
from app.schemas.donor_anchor_decision import PredictionResponse, SimilarCaseResponse
from app.api.v1.endpoints.auth import get_current_user
from app.services.donor_prediction_service import donor_prediction_service

logger = logging.getLogger(__name__)
router = APIRouter()


@router.get("/{donor_id}", response_model=PredictionResponse)
async def get_donor_prediction(
    donor_id: int,
    similarity_threshold: float = 0.85,
    max_similar_cases: int = 10,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """Get prediction for a donor based on similar cases."""
    donor = db.query(Donor).filter(Donor.id == donor_id).first()
    if not donor:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Donor not found"
        )
    
    prediction = await donor_prediction_service.predict_donor_outcome(
        donor_id=donor_id,
        db=db,
        similarity_threshold=similarity_threshold,
        max_similar_cases=max_similar_cases
    )
    
    # Convert similar cases to response format
    similar_cases_response = [
        SimilarCaseResponse(
            anchor_decision_id=case["anchor_decision_id"],
            donor_id=case["donor_id"],
            outcome=case["outcome"],
            similarity=case["similarity"],
            parameter_snapshot=case["parameter_snapshot"]
        )
        for case in prediction.get("similar_cases", [])
    ]
    
    return PredictionResponse(
        predicted_outcome=prediction.get("predicted_outcome"),
        confidence=prediction.get("confidence", 0.0),
        similar_cases=similar_cases_response,
        reasoning=prediction.get("reasoning", ""),
        similarity_threshold_used=prediction.get("similarity_threshold_used")
    )


@router.get("/{donor_id}/similar-by-criteria")
async def get_similar_donors_by_criteria(
    donor_id: int,
    limit: int = 10,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """Get similar donors using structured criteria matching (for future MTF scoring algorithm)."""
    donor = db.query(Donor).filter(Donor.id == donor_id).first()
    if not donor:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Donor not found"
        )
    
    # For now, use default criteria weights (will be configurable in future)
    criteria_weights = {
        "age_range": 0.2,
        "gender": 0.2,
        "tissue_type": 0.2,
        "cause_of_death": 0.2,
        "lab_results": 0.2
    }
    
    similar_cases = donor_prediction_service.find_similar_donors_by_criteria(
        donor_id=donor_id,
        criteria_weights=criteria_weights,
        db=db,
        limit=limit
    )
    
    return {
        "donor_id": donor_id,
        "similar_cases": similar_cases,
        "criteria_weights_used": criteria_weights
    }

