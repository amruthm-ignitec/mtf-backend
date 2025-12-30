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

logger = logging.getLogger(__name__)


class ResultParser:
    """Utility class for parsing extraction results."""
    
    @staticmethod
    def get_laboratory_results_for_document(document_id: int, db: Session) -> Dict[str, Any]:
        """
        Get all laboratory results (serology and culture) for a document.
        
        Args:
            document_id: ID of the document
            db: Database session
            
        Returns:
            Dictionary with serology_results and culture_results
        """
        try:
            results = db.query(LaboratoryResult).filter(
                LaboratoryResult.document_id == document_id
            ).all()
            
            serology_results = {}
            culture_results = []
            serology_citations = []
            culture_citations = []
            
            for result in results:
                citation = {
                    "document_id": result.document_id,
                    "page": result.source_page
                } if result.source_page else None
                
                if result.test_type == TestType.SEROLOGY:
                    serology_results[result.test_name] = result.result
                    if citation:
                        serology_citations.append(citation)
                elif result.test_type == TestType.CULTURE:
                    culture_item = {
                        "test_name": result.test_name,
                        "result": result.result,
                        "document_id": result.document_id
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
                    
                    culture_results.append(culture_item)
                    if citation:
                        culture_citations.append(citation)
            
            # Deduplicate citations
            def deduplicate_citations(citations):
                unique = []
                seen = set()
                for citation in citations:
                    if citation:
                        key = (citation["document_id"], citation["page"])
                        if key not in seen:
                            seen.add(key)
                            unique.append(citation)
                unique.sort(key=lambda x: (x["document_id"], x["page"]))
                return unique
            
            return {
                "serology_results": {
                    "result": serology_results,
                    "citations": deduplicate_citations(serology_citations)
                },
                "culture_results": {
                    "result": culture_results,
                    "citations": deduplicate_citations(culture_citations)
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
    def get_criteria_evaluations_for_donor(donor_id: int, db: Session) -> Dict[str, Any]:
        """
        Get all criteria evaluations for a donor.
        
        Returns:
            Dictionary with criteria evaluations grouped by criterion name
        """
        try:
            evaluations = db.query(CriteriaEvaluation).filter(
                CriteriaEvaluation.donor_id == donor_id
            ).all()
            
            criteria_data = {}
            for eval_obj in evaluations:
                criterion_name = eval_obj.criterion_name
                if criterion_name not in criteria_data:
                    criteria_data[criterion_name] = {
                        "extracted_data": eval_obj.extracted_data or {},
                        "evaluation_result": eval_obj.evaluation_result.value,
                        "evaluation_reasoning": eval_obj.evaluation_reasoning,
                        "tissue_types": []
                    }
                
                criteria_data[criterion_name]["tissue_types"].append(eval_obj.tissue_type.value)
            
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


# Global instance
result_parser = ResultParser()
