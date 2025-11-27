"""
Service for detecting critical findings from extraction results.
Analyzes serology results and topic summarization to identify critical conditions.
"""
import logging
from typing import Dict, List, Any, Optional
from sqlalchemy.orm import Session
from app.models.serology_result import SerologyResult
from app.models.topic_result import TopicResult
from app.models.document import Document, DocumentStatus

logger = logging.getLogger(__name__)


class CriticalFindingsService:
    """Service for detecting critical findings that may lead to donor rejection."""
    
    # Critical serology tests that if Reactive/Positive would cause rejection
    CRITICAL_SEROLOGY_TESTS = {
        'HIV': ['hiv', 'hiv-1', 'hiv-2', 'hiv 1/2', 'hiv-1/hiv-2', 'aids'],
        'Hepatitis B': ['hepatitis b', 'hbv', 'hbsag', 'hbv nat', 'hepatitis b surface antigen'],
        'Hepatitis C': ['hepatitis c', 'hcv', 'hcv ab', 'hepatitis c antibody'],
        'HTLV': ['htlv', 'htlv i/ii', 'htlv i', 'htlv ii'],
        'Syphilis': ['syphilis', 'treponema', 'treponema pallidum', 'rpr', 'vdrl']
    }
    
    # Critical topic conditions
    CRITICAL_TOPIC_CONDITIONS = ['HIV', 'Hepatitis']
    
    # Reactive/Positive result patterns
    POSITIVE_PATTERNS = ['reactive', 'positive', 'detected', 'confirmed']
    
    @staticmethod
    def detect_critical_findings(donor_id: int, db: Session) -> List[Dict[str, Any]]:
        """
        Detect critical findings from serology results and topic summarization.
        
        Args:
            donor_id: ID of the donor
            db: Database session
            
        Returns:
            List of critical findings with type, severity, and source information
        """
        critical_findings = []
        
        try:
            # Get all documents for this donor
            documents = db.query(Document).filter(
                Document.donor_id == donor_id,
                Document.status == DocumentStatus.COMPLETED
            ).all()
            
            if not documents:
                return critical_findings
            
            # Check serology results for critical findings
            for document in documents:
                serology_results = db.query(SerologyResult).filter(
                    SerologyResult.document_id == document.id
                ).all()
                
                for serology_result in serology_results:
                    test_name_lower = serology_result.test_name.lower()
                    result_lower = serology_result.result.lower() if serology_result.result else ""
                    
                    # Check if this is a critical test and if result is positive/reactive
                    for critical_type, test_keywords in CriticalFindingsService.CRITICAL_SEROLOGY_TESTS.items():
                        if any(keyword in test_name_lower for keyword in test_keywords):
                            if any(pattern in result_lower for pattern in CriticalFindingsService.POSITIVE_PATTERNS):
                                critical_findings.append({
                                    "type": critical_type,
                                    "severity": "CRITICAL",
                                    "automaticRejection": True,
                                    "detectedAt": serology_result.created_at.isoformat() if serology_result.created_at else None,
                                    "source": {
                                        "documentId": str(document.id),
                                        "pageNumber": str(serology_result.source_page) if serology_result.source_page else "Unknown",
                                        "confidence": serology_result.confidence if serology_result.confidence else 0.95
                                    },
                                    "testName": serology_result.test_name,
                                    "result": serology_result.result
                                })
                                break  # Only add once per test type
            
            # Check topic results for critical conditions
            for document in documents:
                topic_results = db.query(TopicResult).filter(
                    TopicResult.document_id == document.id,
                    TopicResult.topic_name.in_(CriticalFindingsService.CRITICAL_TOPIC_CONDITIONS)
                ).all()
                
                for topic_result in topic_results:
                    # Parse summary to check for positive condition
                    summary = topic_result.summary
                    if isinstance(summary, str):
                        try:
                            import json
                            summary = json.loads(summary)
                        except (json.JSONDecodeError, ValueError):
                            pass
                    
                    # Check if condition result is positive
                    if isinstance(summary, dict):
                        condition_result = summary.get('condition result', '').lower()
                        decision = summary.get('decision', '').lower()
                        classifier = summary.get('classifier', {})
                        category = classifier.get('category', '').lower() if isinstance(classifier, dict) else ''
                        
                        # Check if condition is positive
                        if (condition_result == 'positive' or 
                            decision == 'positive' or 
                            category == 'positive'):
                            
                            # Check if we already have this finding from serology
                            existing = any(
                                f.get('type') == topic_result.topic_name 
                                for f in critical_findings
                            )
                            
                            if not existing:
                                critical_findings.append({
                                    "type": topic_result.topic_name,
                                    "severity": "CRITICAL",
                                    "automaticRejection": True,
                                    "detectedAt": topic_result.created_at.isoformat() if topic_result.created_at else None,
                                    "source": {
                                        "documentId": str(document.id),
                                        "pageNumber": str(topic_result.source_pages[0]) if topic_result.source_pages else "Unknown",
                                        "confidence": 0.90
                                    },
                                    "summary": summary
                                })
            
            # Remove duplicates based on type
            seen_types = set()
            unique_findings = []
            for finding in critical_findings:
                finding_type = finding.get('type')
                if finding_type and finding_type not in seen_types:
                    seen_types.add(finding_type)
                    unique_findings.append(finding)
            
            return unique_findings
            
        except Exception as e:
            logger.error(f"Error detecting critical findings for donor {donor_id}: {e}", exc_info=True)
            return []


# Global instance
critical_findings_service = CriticalFindingsService()

