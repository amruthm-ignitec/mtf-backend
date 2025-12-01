"""
Service for analyzing tissue eligibility based on donor data using LLM extraction.
"""
import json
import os
import logging
from typing import Dict, Any, List, Optional, Tuple
from langchain.schema import Document
from langchain_openai import AzureChatOpenAI
from app.services.processing.utils.llm_wrapper import call_llm_with_retry, LLMCallError
from app.services.processing.utils.json_parser import safe_parse_llm_json, LLMResponseParseError

logger = logging.getLogger(__name__)

# Get the base directory for config files (relative to this file)
# tissue_eligibility_service.py is in app/services/
# config is in app/services/processing/config/
_CONFIG_DIR = os.path.join(os.path.dirname(__file__), 'processing', 'config')


def _load_tissue_eligibility_config() -> Dict[str, Any]:
    """Load tissue eligibility configuration."""
    config_path = os.path.join(_CONFIG_DIR, 'tissue_eligibility_config.json')
    try:
        with open(config_path, 'r') as f:
            return json.load(f)
    except Exception as e:
        logger.error(f"Failed to load tissue eligibility config: {e}")
        return {}


def _get_llm_instance() -> Optional[AzureChatOpenAI]:
    """Get LLM instance for tissue eligibility analysis."""
    try:
        from app.services.processing.utils.llm_config import llm_setup
        llm, _ = llm_setup()
        return llm
    except Exception as e:
        logger.error(f"Failed to initialize LLM for tissue eligibility: {e}")
        return None


def _create_tissue_eligibility_prompt(
    tissue_name: str,
    tissue_config: Dict[str, Any],
    extracted_data: Dict[str, Any],
    donor_age: Optional[int] = None
) -> str:
    """
    Create a prompt for analyzing tissue eligibility using LLM.
    
    Args:
        tissue_name: Name of the tissue (e.g., "Femur", "Skin & Soft Tissue")
        tissue_config: Configuration for the tissue from config file
        extracted_data: Already-extracted data from components
        donor_age: Age of the donor if available
        
    Returns:
        Formatted prompt for LLM
    """
    description = tissue_config.get("description", "")
    extraction_prompt = tissue_config.get("extraction_prompt", "")
    sections = tissue_config.get("sections", {})
    
    # Format sections
    sections_text = "\n\n".join(
        f"Section: {section_name}\nContext: {section_context}"
        for section_name, section_context in sections.items()
    )
    
    # Build context from extracted data
    context_parts = []
    
    # Add donor age if available
    if donor_age:
        context_parts.append(f"Donor Age: {donor_age} years")
    
    # Add physical assessment data
    physical_assessment = extracted_data.get("physical_assessment", {})
    if physical_assessment:
        summary = physical_assessment.get("summary", {})
        extracted = physical_assessment.get("extracted_data", {})
        if summary or extracted:
            context_parts.append(f"\nPhysical Assessment:")
            if summary:
                context_parts.append(f"Summary: {json.dumps(summary, indent=2)}")
            if extracted:
                context_parts.append(f"Extracted Data: {json.dumps(extracted, indent=2)}")
    
    # Add medical records review data
    medical_records = extracted_data.get("medical_records_review_summary", {})
    if medical_records:
        summary = medical_records.get("summary", {})
        if summary:
            context_parts.append(f"\nMedical Records Review:")
            context_parts.append(f"Summary: {json.dumps(summary, indent=2)}")
    
    # Add DRAI data
    drai = extracted_data.get("donor_risk_assessment_interview", {}) or extracted_data.get("drai", {})
    if drai:
        summary = drai.get("summary", {})
        extracted = drai.get("extracted_data", {})
        if summary or extracted:
            context_parts.append(f"\nDonor Risk Assessment Interview (DRAI):")
            if summary:
                context_parts.append(f"Summary: {json.dumps(summary, indent=2)}")
            if extracted:
                context_parts.append(f"Extracted Data: {json.dumps(extracted, indent=2)}")
    
    # Add tissue recovery information
    tissue_recovery = extracted_data.get("tissue_recovery_information", {}) or extracted_data.get("tissue_recovery", {})
    if tissue_recovery:
        summary = tissue_recovery.get("summary", {})
        extracted = tissue_recovery.get("extracted_data", {})
        if summary or extracted:
            context_parts.append(f"\nTissue Recovery Information:")
            if summary:
                context_parts.append(f"Summary: {json.dumps(summary, indent=2)}")
            if extracted:
                context_parts.append(f"Extracted Data: {json.dumps(extracted, indent=2)}")
    
    extracted_context = "\n".join(context_parts) if context_parts else "No relevant extracted data available."
    
    # Build factors template - show example format
    if sections:
        factors_example = ',\n        '.join([
            f'{{"name": "{section_name}", "currentValue": "extracted value from data", "requirement": "requirement or standard", "impact": ±number, "positiveImpact": true/false}}'
            for section_name in list(sections.keys())[:3]  # Show first 3 as examples
        ])
        if len(sections) > 3:
            factors_example += ',\n        ... (additional factors as needed)'
    else:
        factors_example = '{"name": "Factor Name", "currentValue": "extracted value", "requirement": "requirement", "impact": ±number, "positiveImpact": true/false}'
    
    prompt = f"""You are an expert medical director and tissue banking specialist working for LifeNet Health, which is a leading organization in regenerative medicine and life sciences. Your task is to analyze the eligibility of {tissue_name} tissue for transplantation based on the provided donor information.

Tissue Description: {description}

{extraction_prompt}

Instructions:
1. Analyze all relevant factors that affect {tissue_name} tissue eligibility for the following sections:
{sections_text}

2. For each section, extract:
   - Current value or finding
   - Requirement or standard
   - Impact on eligibility (positive or negative)
   - Impact score (typically ±10 to ±30 based on importance)

3. Calculate an overall confidence score (0-100) based on all factors:
   - Start with a baseline score
   - Add positive impacts and subtract negative impacts
   - Consider the cumulative effect of all factors

4. Determine eligibility status:
   - "Eligible": Confidence score ≥ 80, all critical factors met
   - "Review Required": Confidence score 60-79, or some factors need medical director review
   - "Ineligible": Confidence score < 60, or critical factors not met

5. Provide a comprehensive description summarizing the analysis.

EXTRACTED DONOR DATA:
{extracted_context}

You must always return the output in the following JSON format with proper formatting. There should be no backticks (```) in the output. Only the JSON output:
{{
    "status": "Eligible/Review Required/Ineligible",
    "confidenceScore": 0-100,
    "factors": [
        {factors_example}
    ],
    "description": "Comprehensive analysis summary explaining the eligibility determination, key factors considered, and any concerns or positive indicators. This should be detailed and professional, suitable for medical director review."
}}

Key Guidelines:
- Extract actual values from the provided data, not assumptions
- If a factor is not mentioned in the data, do not include it or mark it as "Not Available"
- Impact scores should reflect the importance of each factor (critical factors: ±25 to ±30, important factors: ±15 to ±20, minor factors: ±5 to ±10)
- Confidence score should be calculated based on the sum of all factor impacts
- The description should be comprehensive and explain the reasoning behind the eligibility determination

AI Response:"""
    
    return prompt


def _extract_tissue_eligibility_from_llm(
    llm: AzureChatOpenAI,
    tissue_name: str,
    tissue_config: Dict[str, Any],
    extracted_data: Dict[str, Any],
    donor_age: Optional[int] = None
) -> Dict[str, Any]:
    """
    Extract tissue eligibility information using LLM.
    
    Args:
        llm: LLM instance
        tissue_name: Name of the tissue
        tissue_config: Configuration for the tissue
        extracted_data: Already-extracted data from components
        donor_age: Age of the donor
        
    Returns:
        Dictionary with eligibility analysis
    """
    try:
        # Create prompt
        prompt = _create_tissue_eligibility_prompt(
            tissue_name,
            tissue_config,
            extracted_data,
            donor_age
        )
        
        # Call LLM
        response = call_llm_with_retry(
            llm,
            prompt,
            max_retries=3,
            timeout=60,
            context=f"tissue eligibility analysis for {tissue_name}"
        )
        
        # Parse response
        result = safe_parse_llm_json(
            response.content,
            context=f"tissue eligibility analysis for {tissue_name}"
        )
        
        if not isinstance(result, dict):
            raise LLMResponseParseError(
                f"Expected dictionary but got {type(result)}. "
                f"Context: tissue eligibility analysis for {tissue_name}"
            )
        
        # Validate and structure response
        status = result.get("status", "Review Required")
        confidence_score = result.get("confidenceScore", 0)
        factors = result.get("factors", [])
        description = result.get("description", f"Analysis for {tissue_name} based on donor assessment")
        
        # Ensure confidence score is between 0-100
        confidence_score = max(0, min(100, int(confidence_score) if isinstance(confidence_score, (int, float)) else 0))
        
        # Validate status
        if status not in ["Eligible", "Review Required", "Ineligible"]:
            status = "Review Required"
        
        # Get category based on tissue name
        category = "Musculoskeletal" if tissue_name == "Femur" else "Integumentary"
        
        return {
            "id": f"{tissue_name.lower().replace(' ', '_')}",
            "name": tissue_name,
            "category": category,
            "status": status,
            "confidenceScore": confidence_score,
            "factors": factors if isinstance(factors, list) else [],
            "similarCases": {
                "count": 0,  # Would be calculated from historical data
                "successRate": 0.85,  # Would be calculated from historical data
                "trend": "Stable"
            },
            "description": description
        }
        
    except LLMResponseParseError as e:
        logger.error(f"Failed to parse tissue eligibility result for {tissue_name}: {e}")
        # Return error structure
        category = "Musculoskeletal" if tissue_name == "Femur" else "Integumentary"
        return {
            "id": f"{tissue_name.lower().replace(' ', '_')}",
            "name": tissue_name,
            "category": category,
            "status": "Review Required",
            "confidenceScore": 0,
            "factors": [],
            "similarCases": {
                "count": 0,
                "successRate": 0.85,
                "trend": "Stable"
            },
            "description": f"Error analyzing {tissue_name} eligibility: {str(e)}",
            "error": True,
            "error_type": "parse_error",
            "error_message": str(e)
        }
    except LLMCallError as e:
        logger.error(f"LLM call failed for tissue eligibility analysis ({tissue_name}): {e}")
        # Return error structure
        category = "Musculoskeletal" if tissue_name == "Femur" else "Integumentary"
        return {
            "id": f"{tissue_name.lower().replace(' ', '_')}",
            "name": tissue_name,
            "category": category,
            "status": "Review Required",
            "confidenceScore": 0,
            "factors": [],
            "similarCases": {
                "count": 0,
                "successRate": 0.85,
                "trend": "Stable"
            },
            "description": f"Failed to analyze {tissue_name} eligibility due to LLM error: {str(e)}",
            "error": True,
            "error_type": "llm_error",
            "error_message": str(e)
        }
    except Exception as e:
        logger.error(f"Unexpected error in tissue eligibility analysis for {tissue_name}: {e}", exc_info=True)
        # Return error structure
        category = "Musculoskeletal" if tissue_name == "Femur" else "Integumentary"
        return {
            "id": f"{tissue_name.lower().replace(' ', '_')}",
            "name": tissue_name,
            "category": category,
            "status": "Review Required",
            "confidenceScore": 0,
            "factors": [],
            "similarCases": {
                "count": 0,
                "successRate": 0.85,
                "trend": "Stable"
            },
            "description": f"Unexpected error analyzing {tissue_name} eligibility: {str(e)}",
            "error": True,
            "error_type": "unexpected_error",
            "error_message": str(e)
        }


class TissueEligibilityService:
    """Service for analyzing tissue eligibility using LLM extraction."""
    
    @staticmethod
    def analyze_tissue_eligibility(
        extracted_data: Dict[str, Any],
        donor_age: Optional[int] = None,
        llm: Optional[AzureChatOpenAI] = None,
        page_docs: Optional[List[Document]] = None
    ) -> List[Dict[str, Any]]:
        """
        Analyze tissue eligibility based on extracted data using LLM.
        
        Args:
            extracted_data: Dictionary containing all extracted data components
            donor_age: Age of the donor (if available)
            llm: Optional LLM instance (will be initialized if not provided)
            page_docs: Optional page documents (not currently used, but available for future enhancement)
            
        Returns:
            List of tissue eligibility analyses
        """
        tissues = []
        
        try:
            # Load configuration
            config = _load_tissue_eligibility_config()
            if not config:
                logger.warning("Tissue eligibility config not found, using default tissue types")
                config = {}
            
            # Get LLM instance
            if not llm:
                llm = _get_llm_instance()
                if not llm:
                    logger.error("LLM not available for tissue eligibility analysis")
                    # Return error structures instead of empty list for better frontend handling
                    return [
                        {
                            "id": "femur",
                            "name": "Femur",
                            "category": "Musculoskeletal",
                            "status": "Review Required",
                            "confidenceScore": 0,
                            "factors": [],
                            "similarCases": {
                                "count": 0,
                                "successRate": 0.85,
                                "trend": "Stable"
                            },
                            "description": "LLM service not available for tissue eligibility analysis. Please check system configuration.",
                            "error": True,
                            "error_type": "llm_unavailable",
                            "error_message": "LLM instance could not be initialized"
                        },
                        {
                            "id": "skin_soft_tissue",
                            "name": "Skin & Soft Tissue",
                            "category": "Integumentary",
                            "status": "Review Required",
                            "confidenceScore": 0,
                            "factors": [],
                            "similarCases": {
                                "count": 0,
                                "successRate": 0.85,
                                "trend": "Stable"
                            },
                            "description": "LLM service not available for tissue eligibility analysis. Please check system configuration.",
                            "error": True,
                            "error_type": "llm_unavailable",
                            "error_message": "LLM instance could not be initialized"
                        }
                    ]
            
            # POC: Only Femur and Skin & Soft Tissue
            tissue_types = [
                {"name": "Femur", "category": "Musculoskeletal"},
                {"name": "Skin & Soft Tissue", "category": "Integumentary"}
            ]
            
            for tissue_type in tissue_types:
                tissue_name = tissue_type["name"]
                tissue_config = config.get(tissue_name, {})
                
                # If config not found, create default config
                if not tissue_config:
                    logger.warning(f"Config not found for {tissue_name}, using default")
                    tissue_config = {
                        "description": f"Analysis of {tissue_name} tissue eligibility for transplantation",
                        "extraction_prompt": f"Analyze the eligibility of {tissue_name} tissue for transplantation based on donor information.",
                        "sections": {}
                    }
                
                # Extract eligibility using LLM
                eligibility = _extract_tissue_eligibility_from_llm(
                    llm,
                    tissue_name,
                    tissue_config,
                    extracted_data,
                    donor_age
                )
                
                tissues.append(eligibility)
            
            return tissues
            
        except Exception as e:
            logger.error(f"Error analyzing tissue eligibility: {e}", exc_info=True)
            return []


# Global instance
tissue_eligibility_service = TissueEligibilityService()
