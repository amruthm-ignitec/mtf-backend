"""
Service for predicting donor outcomes based on similar cases in anchor database.
"""
import logging
from typing import Dict, Any, Optional, List
from sqlalchemy.orm import Session
from app.models.donor_anchor_decision import AnchorOutcome
from app.services.parameter_snapshot_service import parameter_snapshot_service
from app.services.anchor_database_service import anchor_database_service
from app.services.vector_conversion import vector_conversion_service

logger = logging.getLogger(__name__)


class DonorPredictionService:
    """Service for predicting donor outcomes."""
    
    @staticmethod
    async def predict_donor_outcome(
        donor_id: int,
        db: Session,
        similarity_threshold: float = 0.85,
        max_similar_cases: int = 10
    ) -> Dict[str, Any]:
        """
        Predict donor outcome based on similar cases in anchor database.
        
        Args:
            donor_id: ID of the donor to predict for
            similarity_threshold: Minimum similarity threshold (0-1)
            max_similar_cases: Maximum number of similar cases to consider
            db: Database session
            
        Returns:
            Dictionary with prediction results:
                - predicted_outcome: ACCEPTED or REJECTED
                - confidence: Confidence score (0-1)
                - similar_cases: List of similar cases
                - reasoning: Explanation of the prediction
        """
        try:
            # Get parameter snapshot for donor
            snapshot = parameter_snapshot_service.create_parameter_snapshot(donor_id, db)
            if not snapshot:
                logger.warning(f"Could not create parameter snapshot for donor {donor_id}")
                return {
                    "predicted_outcome": None,
                    "confidence": 0.0,
                    "similar_cases": [],
                    "reasoning": "Could not create parameter snapshot for prediction"
                }
            
            # Convert snapshot to text and generate embedding
            from app.services.anchor_database_service import _snapshot_to_text
            snapshot_text = _snapshot_to_text(snapshot)
            embedding = await vector_conversion_service._generate_embedding(snapshot_text)
            
            if not embedding:
                logger.warning(f"Could not generate embedding for donor {donor_id}")
                return {
                    "predicted_outcome": None,
                    "confidence": 0.0,
                    "similar_cases": [],
                    "reasoning": "Could not generate embedding for prediction"
                }
            
            # Find similar cases
            similar_cases = anchor_database_service.get_similar_cases(
                parameter_embedding=embedding,
                limit=max_similar_cases,
                threshold=similarity_threshold,
                db=db
            )
            
            if not similar_cases:
                logger.info(f"No similar cases found for donor {donor_id} with threshold {similarity_threshold}")
                return {
                    "predicted_outcome": None,
                    "confidence": 0.0,
                    "similar_cases": [],
                    "reasoning": f"No similar cases found with similarity >= {similarity_threshold}"
                }
            
            # Weighted voting based on similarity scores
            accepted_weight = 0.0
            rejected_weight = 0.0
            accepted_count = 0
            rejected_count = 0
            
            for case in similar_cases:
                similarity = case.get("similarity", 0.0)
                outcome = case.get("outcome", "").upper()
                
                if outcome == "ACCEPTED":
                    accepted_weight += similarity
                    accepted_count += 1
                elif outcome == "REJECTED":
                    rejected_weight += similarity
                    rejected_count += 1
            
            total_weight = accepted_weight + rejected_weight
            
            if total_weight == 0:
                logger.warning(f"Total weight is 0 for donor {donor_id}")
                return {
                    "predicted_outcome": None,
                    "confidence": 0.0,
                    "similar_cases": similar_cases,
                    "reasoning": "Could not determine prediction from similar cases"
                }
            
            # Predict based on weighted votes
            if accepted_weight > rejected_weight:
                predicted_outcome = AnchorOutcome.ACCEPTED
            else:
                predicted_outcome = AnchorOutcome.REJECTED
            
            # Calculate confidence as difference in weighted votes / total weight
            weight_difference = abs(accepted_weight - rejected_weight)
            confidence = weight_difference / total_weight if total_weight > 0 else 0.0
            
            # Create reasoning
            reasoning = (
                f"Based on {len(similar_cases)} similar cases: "
                f"{accepted_count} were accepted, {rejected_count} were rejected. "
                f"Weighted votes: Accepted={accepted_weight:.2f}, Rejected={rejected_weight:.2f}. "
                f"Confidence: {confidence:.1%}"
            )
            
            logger.info(
                f"Prediction for donor {donor_id}: {predicted_outcome.value} "
                f"(confidence: {confidence:.1%}, {len(similar_cases)} similar cases)"
            )
            
            return {
                "predicted_outcome": predicted_outcome.value,
                "confidence": confidence,
                "similar_cases": similar_cases,
                "reasoning": reasoning,
                "similarity_threshold_used": similarity_threshold
            }
            
        except Exception as e:
            logger.error(f"Error predicting outcome for donor {donor_id}: {e}", exc_info=True)
            return {
                "predicted_outcome": None,
                "confidence": 0.0,
                "similar_cases": [],
                "reasoning": f"Error during prediction: {str(e)}"
            }
    
    @staticmethod
    def find_similar_donors_by_criteria(
        donor_id: int,
        criteria_weights: Dict[str, float],
        db: Session,
        limit: int = 10
    ) -> List[Dict[str, Any]]:
        """
        Find similar donors using structured criteria matching (for future MTF scoring algorithm).
        
        Args:
            donor_id: ID of the donor to find similar cases for
            criteria_weights: Dictionary with criteria and their weights:
                - age_range: (min_age, max_age)
                - gender: str
                - tissue_type: str
                - cause_of_death: str
                - medical_history_categories: List[str]
                - lab_results: Dict
            db: Database session
            limit: Maximum number of results to return
            
        Returns:
            List of similar cases with scores and breakdown
        """
        try:
            # Get donor snapshot to extract criteria
            snapshot = parameter_snapshot_service.create_parameter_snapshot(donor_id, db)
            if not snapshot:
                logger.warning(f"Could not create parameter snapshot for donor {donor_id}")
                return []
            
            # Build criteria from snapshot
            demographics = snapshot.get("donor_demographics", {})
            criteria = {}
            
            if demographics.get("age"):
                age = demographics["age"]
                # Create age range (±5 years)
                criteria["age_range"] = (max(0, age - 5), age + 5)
            
            if demographics.get("gender"):
                criteria["gender"] = demographics["gender"]
            
            if snapshot.get("cause_of_death"):
                criteria["cause_of_death"] = snapshot["cause_of_death"]
            
            # Get first tissue type if available
            tissue_types = snapshot.get("tissue_types", [])
            if tissue_types and isinstance(tissue_types[0], dict):
                criteria["tissue_type"] = tissue_types[0].get("name", "")
            
            # Find similar cases using criteria
            similar_cases = anchor_database_service.get_similar_cases_by_criteria(
                criteria=criteria,
                db=db,
                limit=limit
            )
            
            logger.debug(f"Found {len(similar_cases)} similar cases for donor {donor_id} using criteria matching")
            return similar_cases
            
        except Exception as e:
            logger.error(f"Error finding similar donors by criteria for donor {donor_id}: {e}", exc_info=True)
            return []


# Global instance
donor_prediction_service = DonorPredictionService()

