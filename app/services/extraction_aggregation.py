"""
Simplified aggregation service that triggers criteria evaluation after all documents are processed.
"""
import json
import logging
import asyncio
from typing import Dict, Any
from sqlalchemy.orm import Session
from sqlalchemy import func
from app.models.document import Document, DocumentStatus
from app.services.criteria_evaluator import criteria_evaluator

logger = logging.getLogger(__name__)


class ExtractionAggregationService:
    """Service for triggering criteria evaluation after document processing."""
    
    @staticmethod
    async def aggregate_donor_results(donor_id: int, db: Session) -> bool:
        """
        Trigger criteria evaluation after all documents for a donor are completed.
        Uses PostgreSQL advisory locks to prevent concurrent evaluation for the same donor.
        
        Args:
            donor_id: ID of the donor
            db: Database session
            
        Returns:
            True if successful, False otherwise
        """
        # Acquire advisory lock to prevent concurrent evaluation for same donor
        lock_acquired = False
        for attempt in range(3):
            try:
                db.execute(func.pg_advisory_xact_lock(donor_id))
                lock_acquired = True
                logger.debug(f"Acquired advisory lock for donor {donor_id} evaluation (attempt {attempt + 1})")
                break
            except Exception as e:
                if attempt < 2:
                    delay = 0.5 * (2 ** attempt)
                    logger.debug(f"Could not acquire lock for donor {donor_id} (attempt {attempt + 1}/3), retrying in {delay}s...")
                    await asyncio.sleep(delay)
                else:
                    logger.warning(f"Could not acquire advisory lock for donor {donor_id} after 3 attempts: {e}")
                    return False
        
        if not lock_acquired:
            logger.warning(f"Failed to acquire advisory lock for donor {donor_id}, skipping evaluation")
            return False
        
        try:
            # Get all completed documents for this donor
            documents = db.query(Document).filter(
                Document.donor_id == donor_id,
                Document.status == DocumentStatus.COMPLETED
            ).all()
            
            if not documents:
                logger.info(f"No completed documents found for donor {donor_id}")
                return False
            
            # Check if all documents are completed
            all_documents = db.query(Document).filter(
                Document.donor_id == donor_id
            ).all()
            
            all_completed = all(doc.status == DocumentStatus.COMPLETED for doc in all_documents)
            has_processing = any(doc.status in [DocumentStatus.PROCESSING, DocumentStatus.ANALYZING] for doc in all_documents)
            
            if has_processing:
                logger.info(f"Donor {donor_id} still has documents processing, waiting for completion")
                return False
            
            if not all_completed:
                logger.info(f"Not all documents completed for donor {donor_id}, skipping evaluation")
                return False
            
            logger.info(f"All documents completed for donor {donor_id}, triggering criteria evaluation")
            
            # Trigger criteria evaluation
            success = await criteria_evaluator.evaluate_donor_criteria(donor_id, db)
            
            if success:
                logger.info(f"Successfully evaluated criteria for donor {donor_id}")
            else:
                logger.error(f"Failed to evaluate criteria for donor {donor_id}")
            
            return success
            
        except Exception as e:
            logger.error(f"Error in aggregation/evaluation for donor {donor_id}: {e}", exc_info=True)
            db.rollback()
            return False
    
    @staticmethod
    def get_aggregated_extracted_data(donor_id: int, db: Session) -> Dict[str, Any]:
        """
        Aggregate extracted_data from all documents for a donor.
        Merges data from multiple documents, with later documents overriding earlier ones.
        
        Args:
            donor_id: ID of the donor
            db: Database session
            
        Returns:
            Dictionary with aggregated extracted_data
        """
        try:
            documents = db.query(Document).filter(
                Document.donor_id == donor_id,
                Document.status == DocumentStatus.COMPLETED
            ).order_by(Document.created_at.asc()).all()  # Order by creation time to merge chronologically
            
            aggregated = {}
            
            for doc in documents:
                # Get extracted_data from processing_result
                if doc.processing_result:
                    try:
                        processing_result = json.loads(doc.processing_result)
                        doc_data = processing_result.get('extracted_data', {})
                        
                        if doc_data:
                            # Merge with later documents overriding earlier ones
                            for key, value in doc_data.items():
                                # Only override if new value is not empty/None
                                if key not in aggregated:
                                    aggregated[key] = value
                                elif value:
                                    # Merge nested structures if they're dictionaries
                                    if isinstance(aggregated[key], dict) and isinstance(value, dict):
                                        # Deep merge for nested dictionaries
                                        merged = aggregated[key].copy()
                                        merged.update(value)
                                        aggregated[key] = merged
                                    elif isinstance(aggregated[key], list) and isinstance(value, list):
                                        # Combine lists, removing duplicates
                                        combined = aggregated[key] + value
                                        # Simple deduplication for list of strings
                                        if combined and isinstance(combined[0], str):
                                            aggregated[key] = list(dict.fromkeys(combined))
                                        else:
                                            aggregated[key] = combined
                                    else:
                                        # Prefer non-empty values
                                        aggregated[key] = value
                    except (json.JSONDecodeError, KeyError) as e:
                        logger.debug(f"Error parsing processing_result for document {doc.id}: {e}")
                        continue
            
            return aggregated
            
        except Exception as e:
            logger.error(f"Error aggregating extracted_data for donor {donor_id}: {e}", exc_info=True)
            return {}


# Global instance
extraction_aggregation_service = ExtractionAggregationService()
