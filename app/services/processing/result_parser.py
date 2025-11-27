"""
Utility to parse and format extraction results from database.
"""
import json
import logging
from typing import Dict, List, Any, Optional
from sqlalchemy.orm import Session
from app.models.culture_result import CultureResult
from app.models.serology_result import SerologyResult
from app.models.topic_result import TopicResult
from app.models.component_result import ComponentResult

logger = logging.getLogger(__name__)


class ResultParser:
    """Utility class for parsing extraction results."""
    
    @staticmethod
    def get_culture_results_for_document(document_id: int, db: Session) -> Dict[str, Any]:
        """
        Get culture results for a document.
        
        Args:
            document_id: ID of the document
            db: Database session
            
        Returns:
            Dictionary with culture results formatted for frontend
        """
        try:
            results = db.query(CultureResult).filter(
                CultureResult.document_id == document_id
            ).all()
            
            formatted_results = []
            for result in results:
                formatted_results.append({
                    "tissue_location": result.tissue_location,
                    "microorganism": result.microorganism,
                    "source_page": result.source_page,
                    "confidence": result.confidence
                })
            
            return {
                "result": formatted_results,
                "citations": sorted(list(set([r.source_page for r in results if r.source_page])))
            }
        except Exception as e:
            logger.error(f"Error getting culture results for document {document_id}: {e}")
            return {"result": [], "citations": []}
    
    @staticmethod
    def get_serology_results_for_document(document_id: int, db: Session) -> Dict[str, Any]:
        """
        Get serology results for a document.
        
        Args:
            document_id: ID of the document
            db: Database session
            
        Returns:
            Dictionary with serology results formatted for frontend
        """
        try:
            results = db.query(SerologyResult).filter(
                SerologyResult.document_id == document_id
            ).all()
            
            formatted_results = {}
            citations = []
            for result in results:
                formatted_results[result.test_name] = result.result
                if result.source_page:
                    citations.append(result.source_page)
            
            return {
                "result": formatted_results,
                "citations": sorted(list(set(citations)))
            }
        except Exception as e:
            logger.error(f"Error getting serology results for document {document_id}: {e}")
            return {"result": {}, "citations": []}
    
    @staticmethod
    def get_topic_results_for_document(document_id: int, db: Session) -> Dict[str, Any]:
        """
        Get topic results for a document.
        
        Args:
            document_id: ID of the document
            db: Database session
            
        Returns:
            Dictionary with topic results formatted for frontend
        """
        try:
            results = db.query(TopicResult).filter(
                TopicResult.document_id == document_id
            ).all()
            
            formatted_results = {}
            for result in results:
                # Parse summary if it's a JSON string (stored as string in DB)
                summary = result.summary
                if isinstance(summary, str) and summary.strip().startswith('{'):
                    try:
                        import json
                        summary = json.loads(summary)
                    except (json.JSONDecodeError, ValueError):
                        # If parsing fails, keep as string
                        pass
                
                formatted_results[result.topic_name] = {
                    "summary": summary,
                    "citations": result.citations or [],
                    "source_pages": result.source_pages or []
                }
            
            return formatted_results
        except Exception as e:
            logger.error(f"Error getting topic results for document {document_id}: {e}")
            return {}
    
    @staticmethod
    def get_component_results_for_document(document_id: int, db: Session) -> Dict[str, Any]:
        """
        Get component results for a document.
        
        Args:
            document_id: ID of the document
            db: Database session
            
        Returns:
            Dictionary with component results formatted for frontend
        """
        try:
            results = db.query(ComponentResult).filter(
                ComponentResult.document_id == document_id
            ).all()
            
            initial_components = {}
            conditional_components = {}
            
            for result in results:
                # Parse summary if it's a JSON string (stored as string in DB)
                summary = result.summary
                if isinstance(summary, str) and summary.strip().startswith('{'):
                    try:
                        import json
                        summary = json.loads(summary)
                    except (json.JSONDecodeError, ValueError):
                        # If parsing fails, keep as string
                        pass
                
                component_data = {
                    "present": result.present,
                    "pages": result.pages or [],
                    "summary": summary,
                    "extracted_data": result.extracted_data or {},
                    "confidence": result.confidence if hasattr(result, 'confidence') else None
                }
                
                # Determine if it's initial or conditional based on component name
                # This is a heuristic - you may need to adjust based on your component names
                conditional_names = ['Autopsy Report', 'Toxicology Report', 'Skin Dermal Cultures', 'Bioburden Results']
                if result.component_name in conditional_names:
                    conditional_components[result.component_name] = component_data
                else:
                    initial_components[result.component_name] = component_data
            
            return {
                "initial_components": initial_components,
                "conditional_components": conditional_components
            }
        except Exception as e:
            logger.error(f"Error getting component results for document {document_id}: {e}")
            return {"initial_components": {}, "conditional_components": {}}
    
    @staticmethod
    def get_all_extraction_results_for_document(document_id: int, db: Session) -> Dict[str, Any]:
        """
        Get all extraction results for a document.
        
        Args:
            document_id: ID of the document
            db: Database session
            
        Returns:
            Dictionary with all extraction results
        """
        return {
            "culture": ResultParser.get_culture_results_for_document(document_id, db),
            "serology": ResultParser.get_serology_results_for_document(document_id, db),
            "topics": ResultParser.get_topic_results_for_document(document_id, db),
            "components": ResultParser.get_component_results_for_document(document_id, db)
        }


# Global instance
result_parser = ResultParser()

