"""
Value standardization utility for consistent status and condition values.
"""
import logging
from typing import Optional

logger = logging.getLogger(__name__)


class ValueStandardization:
    """Utility class for standardizing extracted values to consistent formats."""
    
    # Present/Absent value mappings
    PRESENT_VALUES = ["yes", "present", "y", "true", "1", "positive"]
    ABSENT_VALUES = ["no", "not present", "absent", "n", "false", "0", "none", "negative"]
    
    # Conditional status mappings
    CONDITION_MET_VALUES = ["condition met", "met", "yes", "true", "positive"]
    CONDITION_NOT_MET_VALUES = ["condition not met", "not met", "no", "false", "negative"]
    
    # Quality status mappings
    GOOD_VALUES = ["good", "normal", "acceptable", "suitable", "excellent"]
    REVIEW_REQUIRED_VALUES = ["review required", "review", "questionable", "needs review", "pending review"]
    
    @staticmethod
    def standardize_present_status(value: Optional[str]) -> str:
        """
        Standardize present/absent status values.
        
        Args:
            value: Raw value from extraction
            
        Returns:
            Standardized value: "Present", "None", or "Unknown"
        """
        if not value:
            return "None"
        
        value_lower = str(value).lower().strip()
        
        if value_lower in ValueStandardization.PRESENT_VALUES:
            return "Present"
        elif value_lower in ValueStandardization.ABSENT_VALUES:
            return "None"
        else:
            # Check for partial matches
            if any(pv in value_lower for pv in ValueStandardization.PRESENT_VALUES):
                return "Present"
            elif any(av in value_lower for av in ValueStandardization.ABSENT_VALUES):
                return "None"
            else:
                logger.debug(f"Unknown present status value: {value}, returning 'Unknown'")
                return "Unknown"
    
    @staticmethod
    def standardize_conditional_status(value: Optional[str]) -> str:
        """
        Standardize conditional status values.
        
        Args:
            value: Raw value from extraction
            
        Returns:
            Standardized value: "CONDITION MET", "CONDITION NOT MET", or "UNKNOWN"
        """
        if not value:
            return "UNKNOWN"
        
        value_lower = str(value).lower().strip()
        
        if any(mv in value_lower for mv in ValueStandardization.CONDITION_MET_VALUES):
            return "CONDITION MET"
        elif any(nmv in value_lower for nmv in ValueStandardization.CONDITION_NOT_MET_VALUES):
            return "CONDITION NOT MET"
        else:
            logger.debug(f"Unknown conditional status value: {value}, returning 'UNKNOWN'")
            return "UNKNOWN"
    
    @staticmethod
    def standardize_quality_status(value: Optional[str]) -> str:
        """
        Standardize quality status values.
        
        Args:
            value: Raw value from extraction
            
        Returns:
            Standardized value: "Good", "Review Required", or "Unknown"
        """
        if not value:
            return "Unknown"
        
        value_lower = str(value).lower().strip()
        
        if any(gv in value_lower for gv in ValueStandardization.GOOD_VALUES):
            return "Good"
        elif any(rv in value_lower for rv in ValueStandardization.REVIEW_REQUIRED_VALUES):
            return "Review Required"
        else:
            logger.debug(f"Unknown quality status value: {value}, returning 'Unknown'")
            return "Unknown"
    
    @staticmethod
    def standardize_topic_decision(value: Optional[str]) -> str:
        """
        Standardize topic decision values to consistent format.
        
        Args:
            value: Raw decision value (e.g., "Yes", "No", "Positive", "Negative")
            
        Returns:
            Standardized value: "Yes", "No", or "Unknown"
        """
        if not value:
            return "Unknown"
        
        value_lower = str(value).lower().strip()
        
        # Map positive/yes values
        if value_lower in ["yes", "y", "positive", "true", "1"]:
            return "Yes"
        # Map negative/no values
        elif value_lower in ["no", "n", "negative", "false", "0"]:
            return "No"
        else:
            return "Unknown"
    
    @staticmethod
    def standardize_condition_result(value: Optional[str]) -> str:
        """
        Standardize condition result values (Positive/Negative/Unknown).
        
        Args:
            value: Raw condition result value
            
        Returns:
            Standardized value: "Positive", "Negative", or "Unknown"
        """
        if not value:
            return "Unknown"
        
        value_lower = str(value).lower().strip()
        
        if value_lower in ["positive", "pos", "yes", "y", "true", "1"]:
            return "Positive"
        elif value_lower in ["negative", "neg", "no", "n", "false", "0"]:
            return "Negative"
        else:
            return "Unknown"



