"""
Service for formatting recovery and terminal information from extraction data.
"""
import logging
from typing import Dict, Any, Optional
from app.services.value_standardization import ValueStandardization

logger = logging.getLogger(__name__)


class InformationFormatterService:
    """Service for formatting recovery and terminal information."""
    
    @staticmethod
    def format_recovery_information(extracted_data: Dict[str, Any]) -> Dict[str, Any]:
        """
        Format recovery information from extraction data.
        
        Args:
            extracted_data: Dictionary containing all extracted data components
            
        Returns:
            Dictionary with recovery window, location, and consent status
        """
        recovery_info = {
            "recovery_window": None,
            "location": None,
            "consent_status": None
        }
        
        try:
            # Get tissue recovery information
            tissue_recovery = extracted_data.get("tissue_recovery_information", {})
            authorization = extracted_data.get("authorization_for_tissue_donation", {})
            
            # Recovery Window - extract from tissue recovery timing
            if tissue_recovery:
                summary = tissue_recovery.get("summary", {})
                if isinstance(summary, dict):
                    timing = summary.get("Timing", "")
                    if timing:
                        recovery_info["recovery_window"] = timing
                    else:
                        # Default to 24 hours if not specified
                        recovery_info["recovery_window"] = "24 hours"
                else:
                    recovery_info["recovery_window"] = "24 hours"
            else:
                recovery_info["recovery_window"] = "24 hours"  # Default
            
            # Location - extract from tissue recovery
            if tissue_recovery:
                extracted = tissue_recovery.get("extracted_data", {})
                summary = tissue_recovery.get("summary", {})
                
                # Check for Recovery_Location in extracted_data
                recovery_location = extracted.get("Recovery_Location", {})
                if isinstance(recovery_location, dict):
                    recovery_info["location"] = (
                        recovery_location.get("facility_name") or 
                        recovery_location.get("hospital_name") or
                        recovery_location.get("recovery_site") or
                        recovery_location.get("facility_address")
                    )
                
                # Check summary if not found
                if not recovery_info["location"] and isinstance(summary, dict):
                    location_summary = summary.get("Recovery Location", "")
                    if location_summary:
                        recovery_info["location"] = location_summary
                
                # Fallback: search for location keywords in extracted_data
                if not recovery_info["location"]:
                    for key, value in extracted.items():
                        if "location" in key.lower() or "hospital" in key.lower() or "facility" in key.lower():
                            if value:
                                recovery_info["location"] = str(value)
                                break
            
            # If not found, check medical records
            if not recovery_info["location"]:
                medical_records = extracted_data.get("medical_records", {})
                if medical_records:
                    summary = medical_records.get("summary", {})
                    if isinstance(summary, dict):
                        admission = summary.get("Admission Information", "")
                        if isinstance(admission, str) and "hospital" in admission.lower():
                            # Try to extract hospital name
                            words = admission.split()
                            for i, word in enumerate(words):
                                if word.lower() == "hospital" and i > 0:
                                    recovery_info["location"] = " ".join(words[max(0, i-2):i+1])
                                    break
            
            # Consent Status - extract from authorization
            if authorization:
                extracted = authorization.get("extracted_data", {})
                authorized_party = extracted.get("authorized_party", {})
                
                if isinstance(authorized_party, dict):
                    name = authorized_party.get("name", "")
                    relationship = authorized_party.get("relationship", "")
                    
                    if name and relationship:
                        recovery_info["consent_status"] = f"Authorized by {relationship} ({name})"
                    elif relationship:
                        recovery_info["consent_status"] = f"Authorized by {relationship}"
                    elif name:
                        recovery_info["consent_status"] = f"Authorized by {name}"
                
                # If not found in extracted_data, check summary
                if not recovery_info["consent_status"]:
                    summary = authorization.get("summary", {})
                    if isinstance(summary, dict):
                        authorizer = summary.get("Authorizer", "")
                        if authorizer:
                            recovery_info["consent_status"] = f"Authorized by {authorizer}"
            
            return recovery_info
            
        except Exception as e:
            logger.error(f"Error formatting recovery information: {e}", exc_info=True)
            return recovery_info
    
    @staticmethod
    def format_terminal_information(extracted_data: Dict[str, Any], topics: Dict[str, Any]) -> Dict[str, Any]:
        """
        Format terminal information from extraction data.
        
        Args:
            extracted_data: Dictionary containing all extracted data components
            topics: Dictionary containing topic summarization results
            
        Returns:
            Dictionary with cause of death, hypotension, and sepsis status
        """
        terminal_info = {
            "cause_of_death": None,
            "hypotension": None,
            "sepsis": None
        }
        
        try:
            # Cause of Death - from topics
            if topics and "Cause of Death" in topics:
                cause_topic = topics["Cause of Death"]
                summary = cause_topic.get("summary", {})
                
                if isinstance(summary, dict):
                    # Try to extract from summary
                    for key in ["Apparent Cause of Death", "UNOS Cause of Death", "OPO Cause of Death"]:
                        if key in summary:
                            terminal_info["cause_of_death"] = summary[key]
                            break
                    
                    # If not found, try to extract from any string value
                    if not terminal_info["cause_of_death"]:
                        for value in summary.values():
                            if isinstance(value, str) and len(value) > 5:
                                terminal_info["cause_of_death"] = value
                                break
            
            # Sepsis - from topics
            if topics and "Sepsis" in topics:
                sepsis_topic = topics["Sepsis"]
                summary = sepsis_topic.get("summary", {})
                decision = sepsis_topic.get("decision", "").lower()
                classifier = sepsis_topic.get("classifier", {})
                category = classifier.get("category", "").lower() if isinstance(classifier, dict) else ""
                
                # Use standardized value conversion
                decision_str = decision if decision else category
                terminal_info["sepsis"] = ValueStandardization.standardize_present_status(decision_str)
                
                # If still unknown, check if it's explicitly negative
                if terminal_info["sepsis"] == "Unknown":
                    if decision == "negative" or category == "negative":
                        terminal_info["sepsis"] = "None"
            else:
                terminal_info["sepsis"] = "None"
            
            # Hypotension - from topics (preferred) or medical records (fallback)
            if topics and "Hypotension" in topics:
                hypotension_topic = topics["Hypotension"]
                summary = hypotension_topic.get("summary", {})
                decision = hypotension_topic.get("decision", "").lower()
                classifier = hypotension_topic.get("classifier", {})
                category = classifier.get("category", "").lower() if isinstance(classifier, dict) else ""
                
                # Use standardized value conversion
                decision_str = decision if decision else category
                terminal_info["hypotension"] = ValueStandardization.standardize_present_status(decision_str)
                
                # If still unknown, check if it's explicitly negative
                if terminal_info["hypotension"] == "Unknown":
                    if decision == "negative" or category == "negative":
                        terminal_info["hypotension"] = "None"
            else:
                # Fallback: check medical records
                medical_records = extracted_data.get("medical_records", {})
                if medical_records:
                    extracted = medical_records.get("extracted_data", {})
                    
                    # Check for hypotension_status in Vital Signs
                    vital_signs = extracted.get("Vital_Signs", {})
                    if isinstance(vital_signs, dict):
                        hypotension_status = vital_signs.get("hypotension_status", "")
                        if hypotension_status:
                            terminal_info["hypotension"] = ValueStandardization.standardize_present_status(
                                str(hypotension_status)
                            )
                    
                    # Fallback: search in admission diagnoses
                    if not terminal_info["hypotension"]:
                        admission_diagnoses = extracted.get("Admission_Diagnoses", [])
                        if isinstance(admission_diagnoses, list):
                            if any("hypotension" in str(diag).lower() for diag in admission_diagnoses):
                                terminal_info["hypotension"] = "Present"
                            else:
                                terminal_info["hypotension"] = "None"
                        else:
                            # Check summary
                            summary = medical_records.get("summary", {})
                            if isinstance(summary, dict):
                                admission = summary.get("Admission Information", "")
                                if isinstance(admission, str):
                                    if "hypotension" in admission.lower():
                                        terminal_info["hypotension"] = "Present"
                                    else:
                                        terminal_info["hypotension"] = "None"
            
            if not terminal_info["hypotension"]:
                terminal_info["hypotension"] = "None"  # Default
            
            return terminal_info
            
        except Exception as e:
            logger.error(f"Error formatting terminal information: {e}", exc_info=True)
            return terminal_info
    
    @staticmethod
    def extract_critical_lab_values(extracted_data: Dict[str, Any]) -> Dict[str, Any]:
        """
        Extract critical lab values from medical records.
        
        Args:
            extracted_data: Dictionary containing all extracted data components
            
        Returns:
            Dictionary with WBC, Hemoglobin, Platelets, Creatinine
        """
        lab_values = {
            "WBC": None,
            "Hemoglobin": None,
            "Platelets": None,
            "Creatinine": None
        }
        
        try:
            medical_records = extracted_data.get("medical_records", {})
            
            if medical_records:
                extracted = medical_records.get("extracted_data", {})
                lab_results = extracted.get("Laboratory_Results", {})
                
                if isinstance(lab_results, dict):
                    # Look for specific lab values
                    for key, value in lab_results.items():
                        key_lower = str(key).lower()
                        value_str = str(value).lower()
                        
                        # WBC
                        if "wbc" in key_lower or "white blood" in key_lower:
                            if "WBC" not in lab_values or not lab_values["WBC"]:
                                lab_values["WBC"] = {
                                    "value": str(value),
                                    "reference": "3.5-10.5",
                                    "unit": "x 10³/μL"
                                }
                        
                        # Hemoglobin
                        if "hemoglobin" in key_lower or "hgb" in key_lower:
                            if "Hemoglobin" not in lab_values or not lab_values["Hemoglobin"]:
                                lab_values["Hemoglobin"] = {
                                    "value": str(value),
                                    "reference": "12.0-15.5",
                                    "unit": "g/dL"
                                }
                        
                        # Platelets
                        if "platelet" in key_lower:
                            if "Platelets" not in lab_values or not lab_values["Platelets"]:
                                lab_values["Platelets"] = {
                                    "value": str(value),
                                    "reference": "150-450",
                                    "unit": "x 10³/μL"
                                }
                        
                        # Creatinine
                        if "creatinine" in key_lower:
                            if "Creatinine" not in lab_values or not lab_values["Creatinine"]:
                                lab_values["Creatinine"] = {
                                    "value": str(value),
                                    "reference": "0.6-1.2",
                                    "unit": "mg/dL"
                                }
            
            return lab_values
            
        except Exception as e:
            logger.error(f"Error extracting critical lab values: {e}", exc_info=True)
            return lab_values


# Global instance
information_formatter_service = InformationFormatterService()

