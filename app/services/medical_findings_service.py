"""
Service for generating key medical findings summary from extraction data.
"""
import logging
from typing import Dict, Any, Optional

logger = logging.getLogger(__name__)


class MedicalFindingsService:
    """Service for generating key medical findings summary."""
    
    @staticmethod
    def generate_medical_findings_summary(extracted_data: Dict[str, Any]) -> Dict[str, Any]:
        """
        Generate key medical findings summary from extracted data.
        
        Args:
            extracted_data: Dictionary containing all extracted data components
            
        Returns:
            Dictionary with key medical findings including tissue quality, bone density, etc.
        """
        findings = {
            "tissue_quality": None,
            "bone_density": None,
            "cardiovascular_health": None,
            "medical_history": None
        }
        
        try:
            # Extract from medical records review summary
            medical_records_review = extracted_data.get("medical_records_review_summary", {})
            medical_records = extracted_data.get("medical_records", {})
            physical_assessment = extracted_data.get("physical_assessment", {})
            drai = extracted_data.get("donor_risk_assessment_interview", {})
            
            # Tissue Quality - assess from physical assessment and medical records
            if physical_assessment:
                physical_findings = physical_assessment.get("extracted_data", {}).get("physical_findings", {})
                if physical_findings:
                    abnormalities = physical_findings.get("abnormalities", {})
                    if abnormalities and abnormalities.get("Comments"):
                        findings["tissue_quality"] = {
                            "status": "Review Required",
                            "description": abnormalities.get("Comments", "Abnormalities noted in physical assessment")
                        }
                    else:
                        findings["tissue_quality"] = {
                            "status": "Good",
                            "description": "No significant abnormalities noted in physical assessment"
                        }
                else:
                    findings["tissue_quality"] = {
                        "status": "Unknown",
                        "description": "Physical assessment data not available"
                    }
            
            # Bone Density - extract from medical records if available
            if medical_records:
                extracted_medical = medical_records.get("extracted_data", {})
                lab_results = extracted_medical.get("Laboratory_Results", {})
                
                # Look for DEXA scan or bone density mentions
                if isinstance(lab_results, dict):
                    for key, value in lab_results.items():
                        if "dexa" in str(key).lower() or "bone density" in str(key).lower() or "t-score" in str(value).lower():
                            findings["bone_density"] = {
                                "status": "Available",
                                "description": f"Bone density information found: {value}"
                            }
                            break
                
                # If not found, check medical records review summary
                if not findings["bone_density"] and medical_records_review:
                    summary = medical_records_review.get("summary", {})
                    if isinstance(summary, dict):
                        diagnoses = summary.get("Diagnoses", "")
                        if isinstance(diagnoses, str) and ("osteoporosis" in diagnoses.lower() or "bone" in diagnoses.lower()):
                            findings["bone_density"] = {
                                "status": "Noted in records",
                                "description": "Bone-related conditions mentioned in medical records"
                            }
            
            # Cardiovascular Health - extract from medical records and DRAI
            cardiovascular_info = []
            
            if medical_records_review:
                summary = medical_records_review.get("summary", {})
                if isinstance(summary, dict):
                    diagnoses = summary.get("Diagnoses", "")
                    if isinstance(diagnoses, str):
                        if any(term in diagnoses.lower() for term in ["cardiac", "heart", "cardiovascular", "myocardial", "nstemi"]):
                            cardiovascular_info.append("Cardiovascular conditions noted in medical records")
                        elif "no" in diagnoses.lower() and "cardiovascular" in diagnoses.lower():
                            cardiovascular_info.append("No cardiovascular disease noted")
            
            if drai:
                extracted_drai = drai.get("extracted_data", {})
                medical_history = extracted_drai.get("Medical History", {})
                if isinstance(medical_history, dict):
                    if medical_history.get("Recurrent UTIs") == "Yes":
                        pass  # Not cardiovascular
                    # Check for heart-related conditions
                    if any(term in str(medical_history).lower() for term in ["heart", "cardiac", "cardiovascular"]):
                        cardiovascular_info.append("Heart-related conditions mentioned in DRAI")
            
            if cardiovascular_info:
                findings["cardiovascular_health"] = {
                    "status": "Reviewed",
                    "description": ". ".join(cardiovascular_info)
                }
            else:
                findings["cardiovascular_health"] = {
                    "status": "No significant findings",
                    "description": "No cardiovascular disease history noted"
                }
            
            # Medical History Summary - aggregate from multiple sources
            history_summary = []
            
            if medical_records_review:
                summary = medical_records_review.get("summary", {})
                if isinstance(summary, dict):
                    significant_history = summary.get("Significant History", "")
                    if significant_history:
                        if isinstance(significant_history, list):
                            history_summary.extend(significant_history[:3])  # Limit to first 3
                        elif isinstance(significant_history, str):
                            history_summary.append(significant_history[:200])  # Limit length
            
            if drai:
                extracted_drai = drai.get("extracted_data", {})
                medical_history = extracted_drai.get("Medical History", {})
                if isinstance(medical_history, dict):
                    medications = medical_history.get("medications", [])
                    if medications and isinstance(medications, list):
                        history_summary.append(f"Medications: {', '.join(medications[:3])}")
            
            if history_summary:
                findings["medical_history"] = {
                    "status": "Available",
                    "description": ". ".join(history_summary[:2])  # Limit to 2 items
                }
            else:
                findings["medical_history"] = {
                    "status": "Limited",
                    "description": "Medical history information not fully available"
                }
            
            return findings
            
        except Exception as e:
            logger.error(f"Error generating medical findings summary: {e}", exc_info=True)
            return findings


# Global instance
medical_findings_service = MedicalFindingsService()

