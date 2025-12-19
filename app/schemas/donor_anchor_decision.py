from pydantic import BaseModel, Field
from typing import Optional, Dict, Any, List
from datetime import datetime
from app.models.donor_anchor_decision import AnchorOutcome, OutcomeSource


class DonorAnchorDecisionCreate(BaseModel):
    """Schema for creating an anchor decision."""
    donor_id: int
    outcome: AnchorOutcome
    outcome_source: OutcomeSource = OutcomeSource.BATCH_IMPORT


class DonorAnchorDecisionResponse(BaseModel):
    """Schema for anchor decision response."""
    id: int
    donor_id: int
    outcome: str
    outcome_source: str
    parameter_snapshot: Dict[str, Any]
    similarity_threshold_used: Optional[float] = None
    created_at: datetime
    updated_at: Optional[datetime] = None
    
    class Config:
        from_attributes = True


class SimilarCaseResponse(BaseModel):
    """Schema for similar case response."""
    anchor_decision_id: int
    donor_id: int
    outcome: str
    similarity: float
    parameter_snapshot: Dict[str, Any]


class PredictionResponse(BaseModel):
    """Schema for prediction response."""
    predicted_outcome: Optional[str]
    confidence: float
    similar_cases: List[SimilarCaseResponse]
    reasoning: str
    similarity_threshold_used: Optional[float] = None


class AnchorStatsResponse(BaseModel):
    """Schema for anchor database statistics."""
    total_cases: int
    accepted_count: int
    rejected_count: int
    batch_import_count: int
    manual_approval_count: int
    predicted_count: int

