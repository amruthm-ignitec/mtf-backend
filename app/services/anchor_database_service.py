"""
Service for managing anchor database operations.
Handles creating anchor decisions, finding similar cases, and managing the anchor database.
"""
import logging
import json
from typing import Dict, Any, Optional, List
from sqlalchemy.orm import Session
from sqlalchemy import text
from app.models.donor_anchor_decision import DonorAnchorDecision, AnchorOutcome, OutcomeSource
from app.services.parameter_snapshot_service import parameter_snapshot_service
from app.services.vector_conversion import vector_conversion_service

logger = logging.getLogger(__name__)


class AnchorDatabaseService:
    """Service for managing anchor database operations."""
    
    @staticmethod
    async def create_anchor_decision(
        donor_id: int,
        outcome: AnchorOutcome,
        outcome_source: OutcomeSource,
        db: Session
    ) -> Optional[DonorAnchorDecision]:
        """
        Create an anchor decision entry for a donor.
        
        Args:
            donor_id: ID of the donor
            outcome: ACCEPTED or REJECTED
            outcome_source: Source of the outcome (BATCH_IMPORT, MANUAL_APPROVAL, PREDICTED)
            db: Database session
            
        Returns:
            Created DonorAnchorDecision object or None if failed
        """
        try:
            # Check if anchor decision already exists for this donor
            existing = db.query(DonorAnchorDecision).filter(
                DonorAnchorDecision.donor_id == donor_id
            ).first()
            
            if existing:
                logger.info(f"Anchor decision already exists for donor {donor_id}, updating...")
                # Update existing entry
                existing.outcome = outcome
                existing.outcome_source = outcome_source
            else:
                existing = DonorAnchorDecision(
                    donor_id=donor_id,
                    outcome=outcome,
                    outcome_source=outcome_source
                )
                db.add(existing)
            
            # Create parameter snapshot
            snapshot = parameter_snapshot_service.create_parameter_snapshot(donor_id, db)
            if not snapshot:
                logger.error(f"Failed to create parameter snapshot for donor {donor_id}")
                return None
            
            existing.parameter_snapshot = snapshot
            
            # Generate embedding from snapshot
            # Convert snapshot to text representation for embedding
            snapshot_text = _snapshot_to_text(snapshot)
            embedding = await vector_conversion_service._generate_embedding(snapshot_text)
            
            if embedding:
                existing.parameter_embedding = embedding
                logger.debug(f"Generated embedding for donor {donor_id} anchor decision")
            else:
                logger.warning(f"Failed to generate embedding for donor {donor_id}, storing without embedding")
            
            db.commit()
            db.refresh(existing)
            
            logger.info(f"Created anchor decision for donor {donor_id} with outcome {outcome.value}")
            return existing
            
        except Exception as e:
            logger.error(f"Error creating anchor decision for donor {donor_id}: {e}", exc_info=True)
            db.rollback()
            return None
    
    @staticmethod
    def get_similar_cases(
        parameter_embedding: List[float],
        limit: int = 10,
        threshold: float = 0.85,
        db: Session = None
    ) -> List[Dict[str, Any]]:
        """
        Find similar cases using vector similarity search.
        
        Args:
            parameter_embedding: Vector embedding to search for
            limit: Maximum number of results to return
            threshold: Minimum similarity threshold (0-1)
            db: Database session
            
        Returns:
            List of similar cases with similarity scores
        """
        if not db:
            logger.error("Database session required for get_similar_cases")
            return []
        
        try:
            # Convert embedding list to string format for pgvector
            embedding_str = '[' + ','.join(map(str, parameter_embedding)) + ']'
            
            # Use cosine similarity (1 - distance)
            results = db.execute(
                text("""
                    SELECT 
                        id,
                        donor_id,
                        outcome,
                        parameter_snapshot,
                        1 - (parameter_embedding <=> CAST(:query_embedding AS vector)) as similarity
                    FROM donor_anchor_decisions
                    WHERE parameter_embedding IS NOT NULL
                    AND 1 - (parameter_embedding <=> CAST(:query_embedding AS vector)) >= :threshold
                    ORDER BY parameter_embedding <=> CAST(:query_embedding AS vector)
                    LIMIT :limit
                """),
                {
                    "query_embedding": embedding_str,
                    "threshold": threshold,
                    "limit": limit
                }
            ).fetchall()
            
            similar_cases = []
            for row in results:
                similar_cases.append({
                    "anchor_decision_id": row[0],
                    "donor_id": row[1],
                    "outcome": row[2].value if hasattr(row[2], 'value') else str(row[2]),
                    "parameter_snapshot": row[3],
                    "similarity": float(row[4]) if row[4] is not None else 0.0
                })
            
            logger.debug(f"Found {len(similar_cases)} similar cases with similarity >= {threshold}")
            return similar_cases
            
        except Exception as e:
            logger.error(f"Error finding similar cases: {e}", exc_info=True)
            return []
    
    @staticmethod
    def get_similar_cases_by_criteria(
        criteria: Dict[str, Any],
        db: Session,
        limit: int = 10
    ) -> List[Dict[str, Any]]:
        """
        Find similar cases using structured criteria matching (for future MTF matching logic).
        
        Args:
            criteria: Dictionary with matching criteria:
                - age_range: (min_age, max_age)
                - gender: str
                - tissue_type: str
                - cause_of_death: str
                - medical_history_categories: List[str]
                - lab_results: Dict with test names and results
            db: Database session
            limit: Maximum number of results to return
            
        Returns:
            List of similar cases with scores
        """
        try:
            # Build query based on criteria
            query = db.query(DonorAnchorDecision)
            
            # Filter by criteria (this is a placeholder for future MTF-approved matching logic)
            # For now, we'll do basic filtering on parameter_snapshot JSON fields
            
            results = query.limit(limit).all()
            
            scored_cases = []
            for anchor_decision in results:
                snapshot = anchor_decision.parameter_snapshot
                if not isinstance(snapshot, dict):
                    continue
                
                score = 0.0
                match_details = {}
                
                # Score based on demographics
                demographics = snapshot.get("donor_demographics", {})
                if criteria.get("age_range"):
                    min_age, max_age = criteria["age_range"]
                    age = demographics.get("age")
                    if age and min_age <= age <= max_age:
                        score += 0.2
                        match_details["age_match"] = True
                
                if criteria.get("gender"):
                    if demographics.get("gender", "").lower() == criteria["gender"].lower():
                        score += 0.2
                        match_details["gender_match"] = True
                
                # Score based on cause of death
                if criteria.get("cause_of_death"):
                    snapshot_cod = snapshot.get("cause_of_death", "")
                    if criteria["cause_of_death"].lower() in snapshot_cod.lower():
                        score += 0.2
                        match_details["cause_of_death_match"] = True
                
                # Score based on tissue type
                if criteria.get("tissue_type"):
                    tissue_types = snapshot.get("tissue_types", [])
                    for tissue in tissue_types:
                        if isinstance(tissue, dict) and tissue.get("name") == criteria["tissue_type"]:
                            score += 0.2
                            match_details["tissue_type_match"] = True
                            break
                
                if score > 0:
                    scored_cases.append({
                        "anchor_decision_id": anchor_decision.id,
                        "donor_id": anchor_decision.donor_id,
                        "outcome": anchor_decision.outcome.value,
                        "score": score,
                        "match_details": match_details,
                        "parameter_snapshot": snapshot
                    })
            
            # Sort by score descending
            scored_cases.sort(key=lambda x: x["score"], reverse=True)
            
            logger.debug(f"Found {len(scored_cases)} cases matching criteria")
            return scored_cases[:limit]
            
        except Exception as e:
            logger.error(f"Error finding similar cases by criteria: {e}", exc_info=True)
            return []
    
    @staticmethod
    async def update_from_approval(approval_id: int, db: Session) -> Optional[DonorAnchorDecision]:
        """
        Create or update anchor database entry from a manual approval.
        
        Args:
            approval_id: ID of the donor approval
            db: Database session
            
        Returns:
            Created/updated DonorAnchorDecision or None if failed
        """
        try:
            from app.models.donor_approval import DonorApproval, ApprovalStatus
            
            approval = db.query(DonorApproval).filter(
                DonorApproval.id == approval_id
            ).first()
            
            if not approval:
                logger.error(f"Approval {approval_id} not found")
                return None
            
            # Map approval status to anchor outcome
            if approval.status == ApprovalStatus.APPROVED:
                outcome = AnchorOutcome.ACCEPTED
            elif approval.status == ApprovalStatus.REJECTED:
                outcome = AnchorOutcome.REJECTED
            else:
                logger.warning(f"Approval {approval_id} has status {approval.status}, skipping anchor DB update")
                return None
            
            # Create anchor decision
            anchor_decision = await AnchorDatabaseService.create_anchor_decision(
                donor_id=approval.donor_id,
                outcome=outcome,
                outcome_source=OutcomeSource.MANUAL_APPROVAL,
                db=db
            )
            
            logger.info(f"Updated anchor database from approval {approval_id}")
            return anchor_decision
            
        except Exception as e:
            logger.error(f"Error updating anchor database from approval {approval_id}: {e}", exc_info=True)
            return None


def _snapshot_to_text(snapshot: Dict[str, Any]) -> str:
    """
    Convert parameter snapshot to text representation for embedding generation.
    
    Args:
        snapshot: Parameter snapshot dictionary
        
    Returns:
        Text representation of the snapshot
    """
    text_parts = []
    
    # Add demographics
    demographics = snapshot.get("donor_demographics", {})
    if demographics.get("age"):
        text_parts.append(f"Age: {demographics['age']}")
    if demographics.get("gender"):
        text_parts.append(f"Gender: {demographics['gender']}")
    
    # Add cause of death
    if snapshot.get("cause_of_death"):
        text_parts.append(f"Cause of Death: {snapshot['cause_of_death']}")
    
    # Add tissue types
    tissue_types = snapshot.get("tissue_types", [])
    if tissue_types:
        tissue_names = [t.get("name", "") if isinstance(t, dict) else str(t) for t in tissue_types]
        text_parts.append(f"Tissue Types: {', '.join(tissue_names)}")
    
    # Add serology results
    serology_results = snapshot.get("lab_results", {}).get("serology_results", [])
    if serology_results:
        serology_text = []
        for result in serology_results:
            if isinstance(result, dict):
                test_name = result.get("test_name", "")
                test_result = result.get("result", "")
                if test_name and test_result:
                    serology_text.append(f"{test_name}: {test_result}")
        if serology_text:
            text_parts.append(f"Serology: {'; '.join(serology_text)}")
    
    # Add culture results
    culture_results = snapshot.get("lab_results", {}).get("culture_results", [])
    if culture_results:
        culture_text = []
        for result in culture_results:
            if isinstance(result, dict):
                test_name = result.get("test_name", "")
                test_result = result.get("result", "")
                if test_name and test_result:
                    culture_text.append(f"{test_name}: {test_result}")
        if culture_text:
            text_parts.append(f"Culture: {'; '.join(culture_text)}")
    
    # Add critical findings
    critical_findings = snapshot.get("critical_findings", [])
    if critical_findings:
        finding_types = [f.get("type", "") for f in critical_findings if isinstance(f, dict)]
        if finding_types:
            text_parts.append(f"Critical Findings: {', '.join(finding_types)}")
    
    # Add medical history summary
    medical_history = snapshot.get("medical_history_categories", {})
    if medical_history:
        history_parts = []
        for category, items in medical_history.items():
            if items:
                history_parts.append(f"{category}: {len(items)} items")
        if history_parts:
            text_parts.append(f"Medical History: {'; '.join(history_parts)}")
    
    return ". ".join(text_parts)


# Global instance
anchor_database_service = AnchorDatabaseService()

