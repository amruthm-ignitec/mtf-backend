"""
Service for validating extracted data quality and completeness.
Provides quality assurance checks, confidence scoring, and cross-validation.
"""
import logging
from typing import Dict, List, Any, Optional
from sqlalchemy.orm import Session
from app.models.culture_result import CultureResult
from app.models.serology_result import SerologyResult
from app.models.topic_result import TopicResult
from app.models.component_result import ComponentResult

logger = logging.getLogger(__name__)


class DataValidationService:
    """Service for validating extracted data quality and completeness."""
    
    # Expected critical serology tests for donor screening
    EXPECTED_CRITICAL_TESTS = [
        'hiv', 'hiv-1', 'hiv-2', 'hiv-1/hiv-2', 'hiv antibody',
        'hepatitis b', 'hbv', 'hbsag', 'hepatitis b surface antigen',
        'hepatitis c', 'hcv', 'hcv ab', 'hepatitis c antibody',
        'syphilis', 'rpr', 'vdrl', 'treponema',
        'htlv', 'htlv i/ii'
    ]
    
    # Standard result values for validation
    VALID_RESULT_VALUES = [
        'positive', 'negative', 'reactive', 'non-reactive', 'nonreactive',
        'equivocal', 'indeterminate', 'borderline', 'complete', 'cancelled',
        'pending', 'not tested', 'not performed',
        'o positive', 'o negative', 'a positive', 'a negative',
        'b positive', 'b negative', 'ab positive', 'ab negative'
    ]
    
    @staticmethod
    def validate_extraction_quality(
        document_id: int,
        db: Session,
        extraction_data: Optional[Dict[str, Any]] = None
    ) -> Dict[str, Any]:
        """
        Comprehensive validation of extraction quality for a document.
        
        Args:
            document_id: ID of the document to validate
            db: Database session
            extraction_data: Optional pre-loaded extraction data
            
        Returns:
            Dictionary containing validation results, confidence scores, and issues
        """
        validation_results = {
            "document_id": document_id,
            "overall_confidence": 0.0,
            "completeness_score": 0.0,
            "consistency_score": 0.0,
            "validation_checks": {},
            "issues": [],
            "warnings": [],
            "recommendations": []
        }
        
        try:
            # Validate culture results
            culture_validation = DataValidationService._validate_culture_results(
                document_id, db
            )
            validation_results["validation_checks"]["culture"] = culture_validation
            
            # Validate serology results
            serology_validation = DataValidationService._validate_serology_results(
                document_id, db
            )
            validation_results["validation_checks"]["serology"] = serology_validation
            
            # Validate topic results
            topic_validation = DataValidationService._validate_topic_results(
                document_id, db
            )
            validation_results["validation_checks"]["topics"] = topic_validation
            
            # Validate component results
            component_validation = DataValidationService._validate_component_results(
                document_id, db
            )
            validation_results["validation_checks"]["components"] = component_validation
            
            # Cross-validation between modules
            cross_validation = DataValidationService._cross_validate_extractions(
                document_id, db, extraction_data
            )
            validation_results["validation_checks"]["cross_validation"] = cross_validation
            
            # Calculate overall scores
            validation_results["completeness_score"] = DataValidationService._calculate_completeness_score(
                validation_results["validation_checks"]
            )
            validation_results["consistency_score"] = DataValidationService._calculate_consistency_score(
                validation_results["validation_checks"]
            )
            validation_results["overall_confidence"] = (
                validation_results["completeness_score"] * 0.6 +
                validation_results["consistency_score"] * 0.4
            )
            
            # Collect all issues and warnings
            for check_name, check_result in validation_results["validation_checks"].items():
                if isinstance(check_result, dict):
                    validation_results["issues"].extend(
                        check_result.get("issues", [])
                    )
                    validation_results["warnings"].extend(
                        check_result.get("warnings", [])
                    )
                    validation_results["recommendations"].extend(
                        check_result.get("recommendations", [])
                    )
            
            return validation_results
            
        except Exception as e:
            logger.error(f"Error validating extraction quality for document {document_id}: {e}", exc_info=True)
            validation_results["issues"].append({
                "type": "validation_error",
                "message": f"Error during validation: {str(e)}",
                "severity": "high"
            })
            return validation_results
    
    @staticmethod
    def _validate_culture_results(document_id: int, db: Session) -> Dict[str, Any]:
        """Validate culture result extraction quality."""
        validation = {
            "is_valid": True,
            "confidence": 1.0,
            "issues": [],
            "warnings": [],
            "recommendations": []
        }
        
        try:
            culture_results = db.query(CultureResult).filter(
                CultureResult.document_id == document_id
            ).all()
            
            if not culture_results:
                validation["warnings"].append({
                    "type": "missing_data",
                    "message": "No culture results found for this document",
                    "severity": "medium"
                })
                validation["confidence"] = 0.5
                return validation
            
            # Check for required fields
            missing_fields = []
            for result in culture_results:
                if not result.tissue_location:
                    missing_fields.append("tissue_location")
                if not result.microorganism:
                    missing_fields.append("microorganism")
            
            if missing_fields:
                validation["issues"].append({
                    "type": "missing_fields",
                    "message": f"Culture results missing required fields: {set(missing_fields)}",
                    "severity": "high"
                })
                validation["is_valid"] = False
                validation["confidence"] = 0.7
            
            # Check for invalid microorganism names (too short, suspicious patterns)
            suspicious_mos = []
            for result in culture_results:
                mo = result.microorganism.lower().strip()
                if len(mo) < 2:
                    suspicious_mos.append(result.microorganism)
                elif mo in ["unknown", "n/a", "na", "none", ""]:
                    suspicious_mos.append(result.microorganism)
            
            if suspicious_mos:
                validation["warnings"].append({
                    "type": "suspicious_data",
                    "message": f"Culture results contain suspicious microorganism names: {suspicious_mos[:5]}",
                    "severity": "medium"
                })
                validation["confidence"] = min(validation["confidence"], 0.8)
            
            # Check for duplicate entries
            unique_combinations = set()
            duplicates = []
            for result in culture_results:
                key = (result.tissue_location, result.microorganism)
                if key in unique_combinations:
                    duplicates.append(key)
                else:
                    unique_combinations.add(key)
            
            if duplicates:
                validation["warnings"].append({
                    "type": "duplicate_entries",
                    "message": f"Found {len(duplicates)} duplicate culture result entries",
                    "severity": "low"
                })
            
            return validation
            
        except Exception as e:
            logger.error(f"Error validating culture results: {e}", exc_info=True)
            validation["is_valid"] = False
            validation["issues"].append({
                "type": "validation_error",
                "message": f"Error validating culture results: {str(e)}",
                "severity": "high"
            })
            return validation
    
    @staticmethod
    def _validate_serology_results(document_id: int, db: Session) -> Dict[str, Any]:
        """Validate serology result extraction quality."""
        validation = {
            "is_valid": True,
            "confidence": 1.0,
            "issues": [],
            "warnings": [],
            "recommendations": []
        }
        
        try:
            serology_results = db.query(SerologyResult).filter(
                SerologyResult.document_id == document_id
            ).all()
            
            if not serology_results:
                validation["warnings"].append({
                    "type": "missing_data",
                    "message": "No serology results found for this document",
                    "severity": "high"
                })
                validation["confidence"] = 0.3
                validation["is_valid"] = False
                return validation
            
            # Check for critical tests
            test_names = [r.test_name.lower() for r in serology_results]
            missing_critical = []
            for expected_test in DataValidationService.EXPECTED_CRITICAL_TESTS:
                found = any(expected_test in test_name for test_name in test_names)
                if not found:
                    missing_critical.append(expected_test)
            
            if missing_critical:
                validation["warnings"].append({
                    "type": "missing_critical_tests",
                    "message": f"Expected critical serology tests not found: {missing_critical[:3]}",
                    "severity": "medium"
                })
                validation["confidence"] = min(validation["confidence"], 0.7)
            
            # Validate result values
            invalid_results = []
            for result in serology_results:
                if result.result:
                    result_lower = result.result.lower().strip()
                    # Check if result is in valid list or contains valid patterns
                    is_valid = (
                        result_lower in DataValidationService.VALID_RESULT_VALUES or
                        any(pattern in result_lower for pattern in ['positive', 'negative', 'reactive', 'non-reactive'])
                    )
                    if not is_valid and len(result.result) > 50:  # Suspiciously long result
                        invalid_results.append((result.test_name, result.result[:50]))
            
            if invalid_results:
                validation["warnings"].append({
                    "type": "unusual_results",
                    "message": f"Found {len(invalid_results)} serology results with unusual format",
                    "severity": "low"
                })
            
            # Check for missing test names or results
            missing_data = []
            for result in serology_results:
                if not result.test_name or not result.result:
                    missing_data.append(result.id if result.id else "unknown")
            
            if missing_data:
                validation["issues"].append({
                    "type": "missing_data",
                    "message": f"Serology results missing test names or results: {len(missing_data)} entries",
                    "severity": "high"
                })
                validation["is_valid"] = False
                validation["confidence"] = min(validation["confidence"], 0.6)
            
            return validation
            
        except Exception as e:
            logger.error(f"Error validating serology results: {e}", exc_info=True)
            validation["is_valid"] = False
            validation["issues"].append({
                "type": "validation_error",
                "message": f"Error validating serology results: {str(e)}",
                "severity": "high"
            })
            return validation
    
    @staticmethod
    def _validate_topic_results(document_id: int, db: Session) -> Dict[str, Any]:
        """Validate topic result extraction quality."""
        validation = {
            "is_valid": True,
            "confidence": 1.0,
            "issues": [],
            "warnings": [],
            "recommendations": []
        }
        
        try:
            topic_results = db.query(TopicResult).filter(
                TopicResult.document_id == document_id
            ).all()
            
            if not topic_results:
                validation["warnings"].append({
                    "type": "missing_data",
                    "message": "No topic results found for this document",
                    "severity": "low"
                })
                validation["confidence"] = 0.8
                return validation
            
            # Check for required fields
            missing_fields = []
            for result in topic_results:
                if not result.topic_name:
                    missing_fields.append("topic_name")
                if not result.summary:
                    missing_fields.append("summary")
            
            if missing_fields:
                validation["issues"].append({
                    "type": "missing_fields",
                    "message": f"Topic results missing required fields: {set(missing_fields)}",
                    "severity": "medium"
                })
                validation["confidence"] = min(validation["confidence"], 0.7)
            
            # Check for very short or very long summaries (potential extraction issues)
            suspicious_summaries = []
            for result in topic_results:
                if result.summary:
                    summary_len = len(result.summary)
                    if summary_len < 10 or summary_len > 5000:
                        suspicious_summaries.append(result.topic_name)
            
            if suspicious_summaries:
                validation["warnings"].append({
                    "type": "suspicious_summaries",
                    "message": f"Topic summaries with unusual length: {suspicious_summaries[:5]}",
                    "severity": "low"
                })
            
            return validation
            
        except Exception as e:
            logger.error(f"Error validating topic results: {e}", exc_info=True)
            validation["is_valid"] = False
            validation["issues"].append({
                "type": "validation_error",
                "message": f"Error validating topic results: {str(e)}",
                "severity": "high"
            })
            return validation
    
    @staticmethod
    def _validate_component_results(document_id: int, db: Session) -> Dict[str, Any]:
        """Validate component result extraction quality."""
        validation = {
            "is_valid": True,
            "confidence": 1.0,
            "issues": [],
            "warnings": [],
            "recommendations": []
        }
        
        try:
            component_results = db.query(ComponentResult).filter(
                ComponentResult.document_id == document_id
            ).all()
            
            if not component_results:
                validation["warnings"].append({
                    "type": "missing_data",
                    "message": "No component results found for this document",
                    "severity": "low"
                })
                validation["confidence"] = 0.8
                return validation
            
            # Check for required fields
            missing_fields = []
            for result in component_results:
                if not result.component_name:
                    missing_fields.append("component_name")
                if not result.extracted_data:
                    missing_fields.append("extracted_data")
            
            if missing_fields:
                validation["issues"].append({
                    "type": "missing_fields",
                    "message": f"Component results missing required fields: {set(missing_fields)}",
                    "severity": "medium"
                })
                validation["confidence"] = min(validation["confidence"], 0.7)
            
            return validation
            
        except Exception as e:
            logger.error(f"Error validating component results: {e}", exc_info=True)
            validation["is_valid"] = False
            validation["issues"].append({
                "type": "validation_error",
                "message": f"Error validating component results: {str(e)}",
                "severity": "high"
            })
            return validation
    
    @staticmethod
    def _cross_validate_extractions(
        document_id: int,
        db: Session,
        extraction_data: Optional[Dict[str, Any]] = None
    ) -> Dict[str, Any]:
        """Cross-validate consistency between different extraction modules."""
        validation = {
            "is_valid": True,
            "confidence": 1.0,
            "issues": [],
            "warnings": [],
            "recommendations": []
        }
        
        try:
            # Get results from different modules
            serology_results = db.query(SerologyResult).filter(
                SerologyResult.document_id == document_id
            ).all()
            
            topic_results = db.query(TopicResult).filter(
                TopicResult.document_id == document_id
            ).all()
            
            # Cross-validate HIV findings
            hiv_serology = any(
                'hiv' in r.test_name.lower() and 
                r.result and 
                'reactive' in r.result.lower() or 'positive' in r.result.lower()
                for r in serology_results
            )
            
            hiv_topic = any(
                r.topic_name.lower() == 'hiv' and 
                r.summary and 
                ('positive' in r.summary.lower() or 'reactive' in r.summary.lower())
                for r in topic_results
            )
            
            if hiv_serology and not hiv_topic:
                validation["warnings"].append({
                    "type": "inconsistency",
                    "message": "HIV found in serology but not reflected in topic summaries",
                    "severity": "medium"
                })
                validation["confidence"] = min(validation["confidence"], 0.8)
            
            if hiv_topic and not hiv_serology:
                validation["warnings"].append({
                    "type": "inconsistency",
                    "message": "HIV mentioned in topics but no corresponding serology result found",
                    "severity": "low"
                })
            
            # Similar cross-validation for Hepatitis
            hep_serology = any(
                ('hepatitis' in r.test_name.lower() or 'hcv' in r.test_name.lower() or 'hbv' in r.test_name.lower()) and
                r.result and
                ('reactive' in r.result.lower() or 'positive' in r.result.lower())
                for r in serology_results
            )
            
            hep_topic = any(
                'hepatitis' in r.topic_name.lower() and
                r.summary and
                ('positive' in r.summary.lower() or 'reactive' in r.summary.lower())
                for r in topic_results
            )
            
            if hep_serology and not hep_topic:
                validation["warnings"].append({
                    "type": "inconsistency",
                    "message": "Hepatitis found in serology but not reflected in topic summaries",
                    "severity": "medium"
                })
                validation["confidence"] = min(validation["confidence"], 0.8)
            
            return validation
            
        except Exception as e:
            logger.error(f"Error in cross-validation: {e}", exc_info=True)
            validation["warnings"].append({
                "type": "validation_error",
                "message": f"Error during cross-validation: {str(e)}",
                "severity": "low"
            })
            return validation
    
    @staticmethod
    def _calculate_completeness_score(validation_checks: Dict[str, Any]) -> float:
        """Calculate overall completeness score based on validation checks."""
        scores = []
        
        for check_name, check_result in validation_checks.items():
            if isinstance(check_result, dict) and "confidence" in check_result:
                scores.append(check_result["confidence"])
        
        if not scores:
            return 0.0
        
        return sum(scores) / len(scores)
    
    @staticmethod
    def _calculate_consistency_score(validation_checks: Dict[str, Any]) -> float:
        """Calculate overall consistency score based on cross-validation."""
        cross_val = validation_checks.get("cross_validation", {})
        if isinstance(cross_val, dict) and "confidence" in cross_val:
            return cross_val["confidence"]
        return 1.0






