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
            citations = []
            for result in results:
                # Check if it's new format (has test_name or result) or old format (tissue_location + microorganism)
                if result.test_name or result.result:
                    # New format: similar to serology
                    culture_item = {
                        "test_name": result.test_name,
                        "result": result.result,
                        "document_id": result.document_id
                    }
                    # Add optional fields if they exist
                    if result.test_method:
                        culture_item["test_method"] = result.test_method
                    if result.specimen_type:
                        culture_item["specimen_type"] = result.specimen_type
                    if result.specimen_date:
                        culture_item["specimen_date"] = result.specimen_date
                    if result.comments:
                        culture_item["comments"] = result.comments
                    formatted_results.append(culture_item)
                else:
                    # Old format: tissue_location + microorganism
                    formatted_results.append({
                        "tissue_location": result.tissue_location,
                        "microorganism": result.microorganism,
                        "source_page": result.source_page,
                        "confidence": result.confidence,
                        "document_id": result.document_id
                    })
                
                # Build citations with document_id
                if result.source_page:
                    citations.append({
                        "document_id": result.document_id,
                        "page": result.source_page
                    })
            
            # Deduplicate citations (same document_id + page combination)
            unique_citations = []
            seen = set()
            for citation in citations:
                key = (citation["document_id"], citation["page"])
                if key not in seen:
                    seen.add(key)
                    unique_citations.append(citation)
            # Sort by document_id, then page
            unique_citations.sort(key=lambda x: (x["document_id"], x["page"]))
            
            return {
                "result": formatted_results,
                "citations": unique_citations
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
                # Include method if available
                if result.test_method:
                    formatted_results[result.test_name] = {
                        "result": result.result,
                        "method": result.test_method
                    }
                else:
                    # Legacy format: just result string for backward compatibility
                    formatted_results[result.test_name] = result.result
                # Build citations with document_id
                if result.source_page:
                    citations.append({
                        "document_id": result.document_id,
                        "page": result.source_page
                    })
            
            # Deduplicate citations (same document_id + page combination)
            unique_citations = []
            seen = set()
            for citation in citations:
                key = (citation["document_id"], citation["page"])
                if key not in seen:
                    seen.add(key)
                    unique_citations.append(citation)
            # Sort by document_id, then page
            unique_citations.sort(key=lambda x: (x["document_id"], x["page"]))
            
            return {
                "result": formatted_results,
                "citations": unique_citations
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
                
                # Convert citations to include document_id if they're just page numbers
                citations = result.citations or []
                citations_with_doc_id = []
                if citations:
                    for citation in citations:
                        if isinstance(citation, dict) and "document_id" in citation:
                            citations_with_doc_id.append(citation)
                        elif isinstance(citation, (int, str)):
                            # Legacy format: just page number, add document_id
                            try:
                                page_num = int(citation) if isinstance(citation, str) and citation.isdigit() else citation
                                citations_with_doc_id.append({
                                    "document_id": result.document_id,
                                    "page": page_num
                                })
                            except (ValueError, TypeError):
                                # If conversion fails, keep as is
                                citations_with_doc_id.append(citation)
                        else:
                            citations_with_doc_id.append(citation)
                
                formatted_results[result.topic_name] = {
                    "summary": summary,
                    "citations": citations_with_doc_id,
                    "source_pages": result.source_pages or [],
                    "document_id": result.document_id
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
                
                # Convert pages to citations with document_id
                pages = result.pages or []
                pages_with_doc_id = []
                if pages:
                    for page in pages:
                        if isinstance(page, dict) and "document_id" in page:
                            pages_with_doc_id.append(page)
                        elif isinstance(page, (int, str)):
                            # Legacy format: just page number, add document_id
                            try:
                                page_num = int(page) if isinstance(page, str) and page.isdigit() else page
                                pages_with_doc_id.append({
                                    "document_id": result.document_id,
                                    "page": page_num
                                })
                            except (ValueError, TypeError):
                                # If conversion fails, keep as is
                                pages_with_doc_id.append(page)
                        else:
                            pages_with_doc_id.append(page)
                
                component_data = {
                    "present": result.present,
                    "pages": pages_with_doc_id,
                    "summary": summary,
                    "extracted_data": result.extracted_data or {},
                    "confidence": result.confidence if hasattr(result, 'confidence') else None,
                    "document_id": result.document_id
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

