"""
Service for analyzing tissue eligibility based on donor data.
"""
import logging
from typing import Dict, Any, List, Optional

logger = logging.getLogger(__name__)


class TissueEligibilityService:
    """Service for analyzing tissue eligibility."""
    
    @staticmethod
    def analyze_tissue_eligibility(extracted_data: Dict[str, Any], donor_age: Optional[int] = None) -> List[Dict[str, Any]]:
        """
        Analyze tissue eligibility based on extracted data.
        
        Args:
            extracted_data: Dictionary containing all extracted data components
            donor_age: Age of the donor (if available)
            
        Returns:
            List of tissue eligibility analyses
        """
        tissues = []
        
        try:
            # Get relevant data
            physical_assessment = extracted_data.get("physical_assessment", {})
            medical_records_review = extracted_data.get("medical_records_review_summary", {})
            drai = extracted_data.get("donor_risk_assessment_interview", {})
            
            # Common tissue types to analyze
            tissue_types = [
                {"name": "Femur", "category": "Musculoskeletal"},
                {"name": "Achilles Tendon", "category": "Integumentary"},
                {"name": "Patellar Tendon", "category": "Musculoskeletal"},
                {"name": "Skin & Soft Tissue", "category": "Integumentary"}
            ]
            
            for tissue_type in tissue_types:
                eligibility = TissueEligibilityService._analyze_single_tissue(
                    tissue_type["name"],
                    tissue_type["category"],
                    physical_assessment,
                    medical_records_review,
                    drai,
                    donor_age
                )
                tissues.append(eligibility)
            
            return tissues
            
        except Exception as e:
            logger.error(f"Error analyzing tissue eligibility: {e}", exc_info=True)
            return []
    
    @staticmethod
    def _analyze_single_tissue(
        tissue_name: str,
        category: str,
        physical_assessment: Dict[str, Any],
        medical_records_review: Dict[str, Any],
        drai: Dict[str, Any],
        donor_age: Optional[int]
    ) -> Dict[str, Any]:
        """Analyze eligibility for a single tissue type."""
        
        factors = []
        confidence_score = 0
        status = "Review Required"
        
        # Age factor
        if donor_age:
            if donor_age <= 70:
                factors.append({
                    "name": "Donor Age",
                    "currentValue": str(donor_age),
                    "requirement": "≤ 70 years",
                    "impact": 20,
                    "positiveImpact": True
                })
                confidence_score += 20
            else:
                factors.append({
                    "name": "Donor Age",
                    "currentValue": str(donor_age),
                    "requirement": "≤ 70 years",
                    "impact": -20,
                    "positiveImpact": False
                })
                confidence_score -= 20
        
        # Physical assessment factors
        if physical_assessment:
            extracted = physical_assessment.get("extracted_data", {})
            physical_findings = extracted.get("physical_findings", {})
            
            if physical_findings:
                abnormalities = physical_findings.get("abnormalities", {})
                if abnormalities and abnormalities.get("Comments"):
                    factors.append({
                        "name": "Physical Abnormalities",
                        "currentValue": "Present",
                        "requirement": "No significant abnormalities",
                        "impact": -25,
                        "positiveImpact": False
                    })
                    confidence_score -= 25
                else:
                    factors.append({
                        "name": "Physical Condition",
                        "currentValue": "Normal",
                        "requirement": "No significant abnormalities",
                        "impact": 25,
                        "positiveImpact": True
                    })
                    confidence_score += 25
        
        # Medical history factors
        if medical_records_review:
            summary = medical_records_review.get("summary", {})
            if isinstance(summary, dict):
                diagnoses = summary.get("Diagnoses", "")
                if isinstance(diagnoses, str):
                    # Check for bone-related issues
                    if "osteoporosis" in diagnoses.lower() or "bone disease" in diagnoses.lower():
                        factors.append({
                            "name": "Bone Disease",
                            "currentValue": "Present",
                            "requirement": "No bone disease",
                            "impact": -30,
                            "positiveImpact": False
                        })
                        confidence_score -= 30
                    else:
                        factors.append({
                            "name": "No Bone Disease",
                            "currentValue": "Yes",
                            "requirement": "Required",
                            "impact": 30,
                            "positiveImpact": True
                        })
                        confidence_score += 30
        
        # Determine status based on confidence score
        if confidence_score >= 80:
            status = "Eligible"
        elif confidence_score >= 60:
            status = "Review Required"
        else:
            status = "Ineligible"
        
        # Ensure confidence score is between 0-100
        confidence_score = max(0, min(100, confidence_score))
        
        return {
            "id": f"{tissue_name.lower().replace(' ', '_')}",
            "name": tissue_name,
            "category": category,
            "status": status,
            "confidenceScore": confidence_score,
            "factors": factors,
            "similarCases": {
                "count": 0,  # Would be calculated from historical data
                "successRate": 0.85,  # Would be calculated from historical data
                "trend": "Stable"
            },
            "description": f"Analysis for {tissue_name} based on donor assessment"
        }


# Global instance
tissue_eligibility_service = TissueEligibilityService()

