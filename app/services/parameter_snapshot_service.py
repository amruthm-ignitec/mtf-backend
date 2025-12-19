"""
Service for creating parameter snapshots from donor extraction data.
Extracts all parameters needed for anchor database and similarity matching.
"""
import logging
import json
from typing import Dict, Any, Optional, List
from datetime import datetime
from sqlalchemy.orm import Session
from app.models.donor import Donor
from app.models.document import Document, DocumentStatus
from app.models.serology_result import SerologyResult
from app.models.culture_result import CultureResult
from app.models.topic_result import TopicResult
from app.models.component_result import ComponentResult
from app.models.donor_extraction import DonorExtraction
from app.services.critical_findings_service import critical_findings_service
from app.services.tissue_eligibility_service import tissue_eligibility_service
from app.services.processing.result_parser import result_parser

logger = logging.getLogger(__name__)


class ParameterSnapshotService:
    """Service for creating comprehensive parameter snapshots from donor data."""
    
    @staticmethod
    def create_parameter_snapshot(donor_id: int, db: Session) -> Dict[str, Any]:
        """
        Create a comprehensive parameter snapshot for a donor.
        
        Args:
            donor_id: ID of the donor
            db: Database session
            
        Returns:
            Dictionary containing all extracted parameters in the snapshot format
        """
        try:
            # Get donor
            donor = db.query(Donor).filter(Donor.id == donor_id).first()
            if not donor:
                logger.error(f"Donor {donor_id} not found")
                return {}
            
            # Get all completed documents
            documents = db.query(Document).filter(
                Document.donor_id == donor_id,
                Document.status == DocumentStatus.COMPLETED
            ).all()
            
            if not documents:
                logger.warning(f"No completed documents found for donor {donor_id}")
                return {}
            
            # Initialize snapshot structure
            snapshot = {
                "donor_demographics": {
                    "age": donor.age,
                    "gender": donor.gender,
                    "date_of_birth": donor.date_of_birth.isoformat() if donor.date_of_birth else None,
                    "unique_donor_id": donor.unique_donor_id
                },
                "cause_of_death": None,
                "tissue_types": [],
                "medical_history_categories": {
                    "past_medical_history": [],
                    "surgery_history": [],
                    "medications": [],
                    "allergies": [],
                    "family_history": [],
                    "social_history": []
                },
                "lab_results": {
                    "serology_results": [],
                    "culture_results": [],
                    "other_lab_tests": []
                },
                "critical_findings": [],
                "topic_results": [],
                "component_results": [],
                "extraction_summary": None,
                "snapshot_timestamp": datetime.utcnow().isoformat()
            }
            
            # Extract serology results
            serology_results = []
            for document in documents:
                doc_serology = db.query(SerologyResult).filter(
                    SerologyResult.document_id == document.id
                ).all()
                for result in doc_serology:
                    serology_results.append({
                        "test_name": result.test_name,
                        "test_method": result.test_method,
                        "result": result.result,
                        "source_page": result.source_page,
                        "confidence": result.confidence,
                        "document_id": document.id
                    })
            snapshot["lab_results"]["serology_results"] = serology_results
            
            # Extract culture results
            culture_results = []
            for document in documents:
                doc_culture = db.query(CultureResult).filter(
                    CultureResult.document_id == document.id
                ).all()
                for result in doc_culture:
                    culture_results.append({
                        "test_name": result.test_name,
                        "test_method": result.test_method,
                        "specimen_type": result.specimen_type,
                        "specimen_date": result.specimen_date,
                        "result": result.result,
                        "tissue_location": result.tissue_location,
                        "microorganism": result.microorganism,
                        "comments": result.comments,
                        "source_page": result.source_page,
                        "confidence": result.confidence,
                        "document_id": document.id
                    })
            snapshot["lab_results"]["culture_results"] = culture_results
            
            # Extract topic results
            topic_results = []
            cause_of_death = None
            for document in documents:
                doc_topics = db.query(TopicResult).filter(
                    TopicResult.document_id == document.id
                ).all()
                for topic in doc_topics:
                    topic_data = {
                        "topic_name": topic.topic_name,
                        "summary": topic.summary,
                        "citations": topic.citations,
                        "source_pages": topic.source_pages,
                        "document_id": document.id
                    }
                    topic_results.append(topic_data)
                    
                    # Extract cause of death from "Cause of Death" topic
                    if topic.topic_name == "Cause of Death" and not cause_of_death:
                        try:
                            if isinstance(topic.summary, str):
                                summary_dict = json.loads(topic.summary)
                            else:
                                summary_dict = topic.summary
                            
                            if isinstance(summary_dict, dict):
                                # Try various keys for cause of death
                                for key in ["Cause of Death", "Apparent Cause of Death", 
                                          "UNOS Cause of Death", "OPO Cause of Death"]:
                                    if key in summary_dict and summary_dict[key]:
                                        cause_of_death = str(summary_dict[key])
                                        break
                                
                                # If not found, try to extract from any string value
                                if not cause_of_death:
                                    for value in summary_dict.values():
                                        if isinstance(value, str) and len(value) > 5:
                                            cause_of_death = value
                                            break
                        except (json.JSONDecodeError, ValueError, TypeError):
                            # If summary is not JSON, try to use it directly
                            if isinstance(topic.summary, str) and len(topic.summary) > 5:
                                cause_of_death = topic.summary
            
            snapshot["topic_results"] = topic_results
            snapshot["cause_of_death"] = cause_of_death
            
            # Extract component results
            component_results = []
            for document in documents:
                doc_components = db.query(ComponentResult).filter(
                    ComponentResult.document_id == document.id
                ).all()
                for component in doc_components:
                    component_data = {
                        "component_name": component.component_name,
                        "present": component.present,
                        "pages": component.pages,
                        "summary": component.summary,
                        "extracted_data": component.extracted_data,
                        "confidence": component.confidence,
                        "document_id": document.id
                    }
                    component_results.append(component_data)
                    
                    # Extract medical history categories from component results
                    extracted_data = component.extracted_data or {}
                    if isinstance(extracted_data, dict):
                        # Map component names to medical history categories
                        component_name_lower = component.component_name.lower()
                        
                        if "medical history" in component_name_lower or "past medical" in component_name_lower:
                            if component.summary:
                                snapshot["medical_history_categories"]["past_medical_history"].append({
                                    "component": component.component_name,
                                    "summary": component.summary,
                                    "extracted_data": extracted_data
                                })
                        
                        if "surgery" in component_name_lower:
                            if component.summary:
                                snapshot["medical_history_categories"]["surgery_history"].append({
                                    "component": component.component_name,
                                    "summary": component.summary,
                                    "extracted_data": extracted_data
                                })
                        
                        if "medication" in component_name_lower:
                            if component.summary or extracted_data:
                                snapshot["medical_history_categories"]["medications"].append({
                                    "component": component.component_name,
                                    "summary": component.summary,
                                    "extracted_data": extracted_data
                                })
                        
                        if "allerg" in component_name_lower:
                            if component.summary or extracted_data:
                                snapshot["medical_history_categories"]["allergies"].append({
                                    "component": component.component_name,
                                    "summary": component.summary,
                                    "extracted_data": extracted_data
                                })
                        
                        if "family" in component_name_lower:
                            if component.summary:
                                snapshot["medical_history_categories"]["family_history"].append({
                                    "component": component.component_name,
                                    "summary": component.summary,
                                    "extracted_data": extracted_data
                                })
                        
                        if "social" in component_name_lower or "drai" in component_name_lower:
                            if component.summary:
                                snapshot["medical_history_categories"]["social_history"].append({
                                    "component": component.component_name,
                                    "summary": component.summary,
                                    "extracted_data": extracted_data
                                })
            
            snapshot["component_results"] = component_results
            
            # Get critical findings
            critical_findings = critical_findings_service.detect_critical_findings(donor_id, db)
            snapshot["critical_findings"] = critical_findings
            
            # Get tissue eligibility (if available from donor extraction)
            donor_extraction = db.query(DonorExtraction).filter(
                DonorExtraction.donor_id == donor_id
            ).first()
            
            if donor_extraction and donor_extraction.extraction_data:
                extraction_data = donor_extraction.extraction_data
                if isinstance(extraction_data, dict):
                    # Try to get tissue eligibility from extraction data
                    tissue_eligibility = extraction_data.get("tissue_eligibility", [])
                    if tissue_eligibility:
                        snapshot["tissue_types"] = tissue_eligibility
                    else:
                        # Try to get from extracted_data structure
                        extracted_data_inner = extraction_data.get("extracted_data", {})
                        if extracted_data_inner:
                            # Look for tissue eligibility in various places
                            for key, value in extracted_data_inner.items():
                                if "tissue" in key.lower() and isinstance(value, list):
                                    snapshot["tissue_types"] = value
                                    break
                    
                    # Get extraction summary
                    snapshot["extraction_summary"] = extraction_data.get("document_summary", {})
            
            # If tissue eligibility not found, try to get it from tissue eligibility service
            if not snapshot["tissue_types"] and donor_extraction and donor_extraction.extraction_data:
                try:
                    extraction_data = donor_extraction.extraction_data
                    if isinstance(extraction_data, dict):
                        extracted_data_inner = extraction_data.get("extracted_data", {})
                        if extracted_data_inner:
                            tissue_eligibility = tissue_eligibility_service.analyze_tissue_eligibility(
                                extracted_data_inner,
                                donor_age=donor.age
                            )
                            if tissue_eligibility:
                                snapshot["tissue_types"] = tissue_eligibility
                except Exception as e:
                    logger.warning(f"Could not get tissue eligibility for donor {donor_id}: {e}")
            
            logger.info(f"Created parameter snapshot for donor {donor_id}")
            return snapshot
            
        except Exception as e:
            logger.error(f"Error creating parameter snapshot for donor {donor_id}: {e}", exc_info=True)
            return {}


# Global instance
parameter_snapshot_service = ParameterSnapshotService()

