"""
Utility to parse and format extraction results from database.
Updated for criteria-focused system with unified laboratory_results table.
"""
import json
import logging
from typing import Dict, List, Any, Optional
from sqlalchemy.orm import Session
from app.models.laboratory_result import LaboratoryResult, TestType
from app.models.criteria_evaluation import CriteriaEvaluation
from app.models.donor_eligibility import DonorEligibility
from app.services.file_citation_service import get_file_citations_batch

logger = logging.getLogger(__name__)


class ResultParser:
    """Utility class for parsing extraction results."""
    
    @staticmethod
    def get_laboratory_results_for_document(document_id: int, db: Session) -> Dict[str, Any]:
        """
        Get all laboratory results (serology and culture) for a document.
        Includes file names in citations and attaches citations array to each result.
        
        Args:
            document_id: ID of the document
            db: Database session
            
        Returns:
            Dictionary with serology_results and culture_results, with citations per test
        """
        try:
            results = db.query(LaboratoryResult).filter(
                LaboratoryResult.document_id == document_id
            ).all()
            
            # Get file names for all document IDs in batch
            document_ids = list(set([r.document_id for r in results]))
            file_names = get_file_citations_batch(document_ids, db)
            
            serology_results = {}
            culture_results = []
            
            for result in results:
                # Build citation with file name
                citation = None
                if result.source_page and result.source_page > 0:
                    file_name = file_names.get(result.document_id, f"Document {result.document_id}")
                    citation = {
                        "document_id": result.document_id,
                        "file_name": file_name,
                        "page": result.source_page
                    }
                
                if result.test_type == TestType.SEROLOGY:
                    # For serology, include citations array in each result
                    test_name = result.test_name
                    if test_name not in serology_results:
                        serology_results[test_name] = {
                            "result": result.result,
                            "citations": []
                        }
                        if result.test_method:
                            serology_results[test_name]["method"] = result.test_method
                        serology_results[test_name]["document_id"] = result.document_id
                    
                    # Add citation if available
                    if citation:
                        # Check if citation already exists (deduplicate)
                        existing_citations = serology_results[test_name]["citations"]
                        citation_key = (citation["document_id"], citation["page"])
                        if not any(c.get("document_id") == citation["document_id"] and c.get("page") == citation["page"] 
                                   for c in existing_citations):
                            existing_citations.append(citation)
                            # Sort citations by document_id and page
                            existing_citations.sort(key=lambda x: (x.get("document_id", 0), x.get("page", 0)))
                elif result.test_type == TestType.CULTURE:
                    culture_item = {
                        "test_name": result.test_name,
                        "result": result.result,
                        "document_id": result.document_id,
                        "citations": []
                    }
                    if result.test_method:
                        culture_item["test_method"] = result.test_method
                    if result.specimen_type:
                        culture_item["specimen_type"] = result.specimen_type
                    if result.specimen_date:
                        culture_item["specimen_date"] = result.specimen_date
                    if result.comments:
                        culture_item["comments"] = result.comments
                    # Legacy fields
                    if result.tissue_location:
                        culture_item["tissue_location"] = result.tissue_location
                    if result.microorganism:
                        culture_item["microorganism"] = result.microorganism
                    
                    # Add citation if available
                    if citation:
                        culture_item["citations"].append(citation)
                    
                    culture_results.append(culture_item)
            
            return {
                "serology_results": {
                    "result": serology_results,
                    "citations": []  # Keep for backward compatibility, but citations are now per-test
                },
                "culture_results": {
                    "result": culture_results,
                    "citations": []  # Keep for backward compatibility, but citations are now per-test
                }
            }
        except Exception as e:
            logger.error(f"Error getting laboratory results for document {document_id}: {e}")
            return {
                "serology_results": {"result": {}, "citations": []},
                "culture_results": {"result": [], "citations": []}
            }
    
    @staticmethod
    def get_culture_results_for_document(document_id: int, db: Session) -> Dict[str, Any]:
        """Get culture results for a document (for backward compatibility)."""
        lab_results = ResultParser.get_laboratory_results_for_document(document_id, db)
        return lab_results.get("culture_results", {"result": [], "citations": []})
    
    @staticmethod
    def get_serology_results_for_document(document_id: int, db: Session) -> Dict[str, Any]:
        """Get serology results for a document (for backward compatibility)."""
        lab_results = ResultParser.get_laboratory_results_for_document(document_id, db)
        return lab_results.get("serology_results", {"result": {}, "citations": []})
    
    @staticmethod
    def _has_actual_data(extracted_data: Dict[str, Any]) -> bool:
        """
        Check if extracted_data has any actual data (not all nulls).
        Excludes metadata fields like _criterion_name, _extraction_timestamp.
        """
        if not extracted_data:
            return False
        
        metadata_fields = {'_criterion_name', '_extraction_timestamp'}
        for key, value in extracted_data.items():
            if key not in metadata_fields and value is not None:
                # Check if value is not empty string, empty list, or empty dict
                if isinstance(value, str) and value.strip():
                    return True
                elif isinstance(value, (list, dict)) and len(value) > 0:
                    return True
                elif not isinstance(value, (str, list, dict)):
                    return True
        
        return False
    
    @staticmethod
    def get_criteria_evaluations_for_donor(donor_id: int, db: Session) -> Dict[str, Any]:
        """
        Get all criteria evaluations for a donor.
        Only includes criteria that have actual extracted data (not all nulls).
        
        Returns:
            Dictionary with criteria evaluations grouped by criterion name
        """
        try:
            evaluations = db.query(CriteriaEvaluation).filter(
                CriteriaEvaluation.donor_id == donor_id
            ).all()
            
            criteria_data = {}
            for eval_obj in evaluations:
                # Only include criteria with actual extracted data
                extracted_data = eval_obj.extracted_data or {}
                if not ResultParser._has_actual_data(extracted_data):
                    continue
                
                criterion_name = eval_obj.criterion_name
                if criterion_name not in criteria_data:
                    criteria_data[criterion_name] = {
                        "extracted_data": extracted_data,
                        "evaluation_result": eval_obj.evaluation_result.value,
                        "evaluation_reasoning": eval_obj.evaluation_reasoning,
                        "tissue_types": [],
                        "document_ids": []  # Collect all document IDs for this criterion
                    }
                
                # Only append if not already present (deduplicate)
                tissue_type_value = eval_obj.tissue_type.value
                if tissue_type_value not in criteria_data[criterion_name]["tissue_types"]:
                    criteria_data[criterion_name]["tissue_types"].append(tissue_type_value)
                
                # Add document_id if available and not already present
                if eval_obj.document_id and eval_obj.document_id not in criteria_data[criterion_name]["document_ids"]:
                    criteria_data[criterion_name]["document_ids"].append(eval_obj.document_id)
            
            return criteria_data
        except Exception as e:
            logger.error(f"Error getting criteria evaluations for donor {donor_id}: {e}")
            return {}
    
    @staticmethod
    def get_all_extraction_results_for_document(document_id: int, db: Session) -> Dict[str, Any]:
        """
        Get all extraction results for a document.
        
        Returns:
            Dictionary with all extraction results
        """
        lab_results = ResultParser.get_laboratory_results_for_document(document_id, db)
        return {
            "laboratory_results": lab_results,
            "document_id": document_id
        }
    
    @staticmethod
    def get_topic_results_for_document(document_id: int, db: Session) -> Dict[str, Any]:
        """
        Get topic results for a document (for backward compatibility).
        Topics are no longer extracted in the new system.
        
        Returns:
            Empty dictionary for backward compatibility
        """
        return {"result": {}, "citations": []}
    
    @staticmethod
    def get_component_results_for_document(document_id: int, db: Session) -> Dict[str, Any]:
        """
        Get component results for a document (for backward compatibility).
        Document components are no longer extracted in the new system.
        
        Returns:
            Empty dictionary for backward compatibility
        """
        return {"initial_components": {}, "conditional_components": {}}


# Global instance
result_parser = ResultParser()
