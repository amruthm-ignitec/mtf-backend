"""
Service for aggregating extraction results from multiple documents per donor.
Merges results and stores in DonorExtraction table.
"""
import json
import logging
from typing import Dict, Any
from datetime import datetime
from sqlalchemy.orm import Session
from app.models.document import Document, DocumentStatus
from app.models.donor_extraction import DonorExtraction
from app.models.culture_result import CultureResult
from app.models.serology_result import SerologyResult
from app.models.topic_result import TopicResult
from app.models.component_result import ComponentResult
from app.services.processing.utils.merge_helpers import (
    merge_culture_results,
    merge_serology_results,
    merge_topics_results,
    merge_components_results
)
from app.services.processing.result_parser import result_parser

logger = logging.getLogger(__name__)


class ExtractionAggregationService:
    """Service for aggregating extraction results per donor."""
    
    @staticmethod
    async def aggregate_donor_results(donor_id: int, db: Session) -> bool:
        """
        Aggregate extraction results from all completed documents for a donor.
        
        Args:
            donor_id: ID of the donor
            db: Database session
            
        Returns:
            True if successful, False otherwise
        """
        try:
            # Get all completed documents for this donor
            documents = db.query(Document).filter(
                Document.donor_id == donor_id,
                Document.status == DocumentStatus.COMPLETED
            ).all()
            
            if not documents:
                logger.info(f"No completed documents found for donor {donor_id}")
                return False
            
            logger.info(f"Aggregating results from {len(documents)} documents for donor {donor_id}")
            
            # Collect results from all documents
            all_culture_results = []
            all_serology_results = []
            all_topic_results = []
            all_component_results = []
            
            for document in documents:
                # Get culture results
                culture_data = result_parser.get_culture_results_for_document(document.id, db)
                if culture_data and culture_data.get('result'):
                    all_culture_results.append(culture_data)
                
                # Get serology results
                serology_data = result_parser.get_serology_results_for_document(document.id, db)
                if serology_data and serology_data.get('result'):
                    all_serology_results.append(serology_data)
                
                # Get topic results
                topic_data = result_parser.get_topic_results_for_document(document.id, db)
                if topic_data:
                    all_topic_results.append(topic_data)
                
                # Get component results
                component_data = result_parser.get_component_results_for_document(document.id, db)
                if component_data:
                    all_component_results.append(component_data)
            
            # Merge results
            merged_culture = merge_culture_results(all_culture_results) if all_culture_results else {}
            merged_serology = merge_serology_results(all_serology_results) if all_serology_results else {}
            merged_topics = merge_topics_results(all_topic_results) if all_topic_results else {}
            merged_components = merge_components_results(all_component_results) if all_component_results else {}
            
            # Build ExtractionDataResponse structure
            extraction_data = {
                "donor_id": str(donor_id),  # Will be updated with unique_donor_id
                "case_id": f"{donor_id}81",  # Will be updated
                "processing_timestamp": datetime.now().isoformat(),
                "processing_duration_seconds": 0,  # Can be calculated if needed
                "extracted_data": {
                    # This will be populated based on component results
                    # Structure matches frontend ExtractionDataResponse
                },
                "conditional_documents": merged_components.get("conditional_components", {}),
                "validation": None,  # Can be calculated
                "compliance_status": None,  # Can be calculated
                "document_summary": {
                    "total_documents_processed": len(documents),
                    "total_pages_processed": 0,  # Can be calculated
                    "extraction_methods_used": ["culture", "serology", "topics", "components"]
                }
            }
            
            # Get donor to update donor_id and case_id
            from app.models.donor import Donor
            donor = db.query(Donor).filter(Donor.id == donor_id).first()
            if donor:
                extraction_data["donor_id"] = donor.unique_donor_id
                extraction_data["case_id"] = f"{donor.unique_donor_id}81"
            
            # Build extracted_data from components
            # Map component results to the expected structure
            initial_components = merged_components.get("initial_components", {})
            for component_name, component_info in initial_components.items():
                # Map component names to extraction data keys
                component_key = component_name.lower().replace(' ', '_').replace('-', '_')
                extraction_data["extracted_data"][component_key] = component_info
            
            # Store or update DonorExtraction
            donor_extraction = db.query(DonorExtraction).filter(
                DonorExtraction.donor_id == donor_id
            ).first()
            
            if donor_extraction:
                # Update existing
                donor_extraction.extraction_data = extraction_data
                donor_extraction.documents_processed = len(documents)
                donor_extraction.processing_status = "complete"
                donor_extraction.last_updated_at = datetime.now()
            else:
                # Create new
                donor_extraction = DonorExtraction(
                    donor_id=donor_id,
                    extraction_data=extraction_data,
                    documents_processed=len(documents),
                    processing_status="complete"
                )
                db.add(donor_extraction)
            
            db.commit()
            logger.info(f"Successfully aggregated results for donor {donor_id}")
            
            # Trigger vector conversion
            from app.services.vector_conversion import vector_conversion_service
            await vector_conversion_service.convert_and_store_donor_vectors(donor_id, db)
            
            return True
            
        except Exception as e:
            logger.error(f"Error aggregating results for donor {donor_id}: {e}", exc_info=True)
            db.rollback()
            return False


# Global instance
extraction_aggregation_service = ExtractionAggregationService()

