"""
Helper functions for merging extraction results from multiple documents.
Copied from mtf-backend-test/utils/test_helpers.py
"""
import json
import logging
from typing import Dict, List, Any, Optional

logger = logging.getLogger(__name__)


def merge_culture_results(culture_results_list: List[Dict[str, Any]]) -> Dict[str, Any]:
    """
    Merge culture results from multiple PDFs.
    
    Args:
        culture_results_list: List of culture results dictionaries from different PDFs
        
    Returns:
        Dict: Merged culture results in format {"result": [...], "citations": [...]}
    """
    if not culture_results_list:
        return {"result": [], "citations": []}
    
    # Filter out None/empty results
    valid_results = [r for r in culture_results_list if r is not None]
    if not valid_results:
        return {"result": [], "citations": []}
    
    # Culture results structure: {"result": [...], "citations": [...]}
    # Citations are now objects: [{"document_id": int, "page": int}, ...]
    # Combine all results and citations
    all_results = []
    all_citations = []
    
    for result_dict in valid_results:
        if isinstance(result_dict, dict):
            # Extract results
            if 'result' in result_dict and isinstance(result_dict['result'], list):
                all_results.extend(result_dict['result'])
            # Extract citations
            if 'citations' in result_dict and isinstance(result_dict['citations'], list):
                for citation in result_dict['citations']:
                    # Handle both new format (dict with document_id) and legacy format (just page number)
                    if isinstance(citation, dict) and "document_id" in citation:
                        all_citations.append(citation)
                    elif isinstance(citation, (int, str)):
                        # Legacy format - we can't determine document_id here, so skip
                        # This should not happen if result_parser is working correctly
                        logger.warning("Found legacy citation format (page number only) in culture results merge")
                    else:
                        all_citations.append(citation)
    
    # Deduplicate citations by (document_id, page) tuple
    unique_citations = []
    seen = set()
    for citation in all_citations:
        if isinstance(citation, dict) and "document_id" in citation and "page" in citation:
            key = (citation["document_id"], citation["page"])
            if key not in seen:
                seen.add(key)
                unique_citations.append(citation)
        else:
            # Handle non-standard citation formats
            if citation not in seen:
                seen.add(citation)
                unique_citations.append(citation)
    
    # Sort by document_id, then page
    unique_citations.sort(key=lambda x: (x.get("document_id", 0), x.get("page", 0)) if isinstance(x, dict) else (0, 0))
    
    # Merge results - keep unique entries based on content
    merged_result = []
    seen_results = set()
    
    for result_item in all_results:
        # Create a hashable representation for deduplication
        if isinstance(result_item, dict):
            result_str = json.dumps(result_item, sort_keys=True)
            if result_str not in seen_results:
                seen_results.add(result_str)
                merged_result.append(result_item)
        else:
            # If not a dict, just add it
            if result_item not in merged_result:
                merged_result.append(result_item)
    
    return {
        "result": merged_result,
        "citations": unique_citations
    }


def merge_serology_results(serology_results_list: List[Dict[str, Any]]) -> Dict[str, Any]:
    """
    Merge serology results from multiple PDFs.
    
    Args:
        serology_results_list: List of serology results dictionaries from different PDFs
        Expected format: [{"result": {"HIV": "Negative", ...}, "citations": [...]}, ...]
        
    Returns:
        Dict: Merged serology results in format {"result": {...}, "citations": [...]}
    """
    if not serology_results_list:
        return {"result": {}, "citations": []}
    
    # Filter out None/empty results
    valid_results = [r for r in serology_results_list if r is not None]
    if not valid_results:
        return {"result": {}, "citations": []}
    
    # Serology results structure from result_parser: {"result": {test_name: result_value}, "citations": [...]}
    # Citations are now objects: [{"document_id": int, "page": int}, ...]
    # Combine all test results
    merged_results = {}
    all_citations = []
    
    for result_dict in valid_results:
        if isinstance(result_dict, dict):
            # Handle the format from result_parser: {"result": {...}, "citations": [...]}
            if 'result' in result_dict and isinstance(result_dict['result'], dict):
                # Merge test results - keep first occurrence of each test
                for test_name, test_result in result_dict['result'].items():
                    if test_name not in merged_results:
                        merged_results[test_name] = test_result
            
            # Collect citations
            if 'citations' in result_dict and isinstance(result_dict['citations'], list):
                for citation in result_dict['citations']:
                    # Handle both new format (dict with document_id) and legacy format (just page number)
                    if isinstance(citation, dict) and "document_id" in citation:
                        all_citations.append(citation)
                    elif isinstance(citation, (int, str)):
                        # Legacy format - we can't determine document_id here, so skip
                        logger.warning("Found legacy citation format (page number only) in serology results merge")
                    else:
                        all_citations.append(citation)
    
    # Deduplicate citations by (document_id, page) tuple
    unique_citations = []
    seen = set()
    for citation in all_citations:
        if isinstance(citation, dict) and "document_id" in citation and "page" in citation:
            key = (citation["document_id"], citation["page"])
            if key not in seen:
                seen.add(key)
                unique_citations.append(citation)
        else:
            # Handle non-standard citation formats
            if citation not in seen:
                seen.add(citation)
                unique_citations.append(citation)
    
    # Sort by document_id, then page
    unique_citations.sort(key=lambda x: (x.get("document_id", 0), x.get("page", 0)) if isinstance(x, dict) else (0, 0))
    
    return {
        "result": merged_results,
        "citations": unique_citations
    }


def merge_topics_results(topics_results_list: List[Dict[str, Any]]) -> Dict[str, Any]:
    """
    Merge topic summarization results from multiple PDFs.
    
    Args:
        topics_results_list: List of topics results dictionaries from different PDFs
        
    Returns:
        Dict: Merged topics results
    """
    if not topics_results_list:
        return {}
    
    # Filter out None/empty results
    valid_results = [r for r in topics_results_list if r is not None]
    if not valid_results:
        return {}
    
    # Topics structure: {topic_name: {decision, summary, citation, classifier, ...}, ...}
    merged_topics = {}
    
    # Collect all topics from all PDFs
    all_topics = set()
    for result_dict in valid_results:
        if isinstance(result_dict, dict):
            all_topics.update(result_dict.keys())
    
    # For each topic, merge results from all PDFs
    for topic in all_topics:
        topic_results = []
        all_citations = []
        
        for result_dict in valid_results:
            if topic in result_dict and isinstance(result_dict[topic], dict):
                topic_data = result_dict[topic]
                topic_results.append(topic_data)
                # Collect citations
                if 'citation' in topic_data:
                    citations = topic_data['citation']
                    if isinstance(citations, list):
                        for citation in citations:
                            # Handle both new format (dict with document_id) and legacy format
                            if isinstance(citation, dict) and "document_id" in citation:
                                all_citations.append(citation)
                            elif isinstance(citation, (int, str)):
                                # Legacy format - try to get document_id from topic_data if available
                                doc_id = topic_data.get('document_id')
                                if doc_id:
                                    try:
                                        page_num = int(citation) if isinstance(citation, str) and citation.isdigit() else citation
                                        all_citations.append({"document_id": doc_id, "page": page_num})
                                    except (ValueError, TypeError):
                                        all_citations.append(citation)
                                else:
                                    all_citations.append(citation)
                            else:
                                all_citations.append(citation)
                    elif isinstance(citations, (int, str)):
                        # Legacy format - try to get document_id from topic_data if available
                        doc_id = topic_data.get('document_id')
                        if doc_id:
                            try:
                                page_num = int(citations) if isinstance(citations, str) and citations.isdigit() else citations
                                all_citations.append({"document_id": doc_id, "page": page_num})
                            except (ValueError, TypeError):
                                all_citations.append(citations)
                        else:
                            all_citations.append(citations)
        
        if topic_results:
            # Find the best result (prefer non-empty, non-NA)
            best_result = None
            for result in topic_results:
                decision = result.get('decision', '').lower()
                summary = result.get('summary', {})
                
                # Prefer results that are not NA/empty
                if decision not in ['na', 'n/a', ''] and summary:
                    if best_result is None:
                        best_result = result
                    else:
                        # Prefer more complete summaries
                        if isinstance(summary, dict) and len(summary) > len(best_result.get('summary', {})):
                            best_result = result
                        elif isinstance(summary, str) and len(str(summary)) > len(str(best_result.get('summary', ''))):
                            best_result = result
            
            # If no good result found, use the first one
            if best_result is None:
                best_result = topic_results[0]
            
            # Merge citations - preserve document_id structure
            # Citations should be objects: [{"document_id": int, "page": int}, ...]
            unique_citations = []
            seen = set()
            for citation in all_citations:
                if isinstance(citation, dict) and "document_id" in citation and "page" in citation:
                    key = (citation["document_id"], citation["page"])
                    if key not in seen:
                        seen.add(key)
                        unique_citations.append(citation)
                elif isinstance(citation, (int, str)):
                    # Legacy format - try to normalize but we can't add document_id here
                    # This should be rare if result_parser is working correctly
                    try:
                        if isinstance(citation, str) and citation.isdigit():
                            normalized = int(citation)
                        else:
                            normalized = citation
                        if normalized not in seen:
                            seen.add(normalized)
                            unique_citations.append(normalized)
                    except (ValueError, TypeError):
                        if citation not in seen:
                            seen.add(citation)
                            unique_citations.append(citation)
                else:
                    # Unknown format, keep as is
                    if citation not in seen:
                        seen.add(citation)
                        unique_citations.append(citation)
            
            # Sort: dict citations by (document_id, page), others at end
            dict_citations = [c for c in unique_citations if isinstance(c, dict) and "document_id" in c]
            other_citations = [c for c in unique_citations if not (isinstance(c, dict) and "document_id" in c)]
            dict_citations.sort(key=lambda x: (x.get("document_id", 0), x.get("page", 0)))
            unique_citations = dict_citations + other_citations
            
            # Create merged result
            merged_topic = best_result.copy()
            merged_topic['citation'] = unique_citations
            merged_topics[topic] = merged_topic
    
    return merged_topics


def _merge_extracted_data(
    base_data: Dict[str, Any],
    new_data: Dict[str, Any],
    base_confidence: float,
    new_confidence: float
) -> Dict[str, Any]:
    """
    Merge extracted_data from two components, preferring higher confidence values.
    
    Args:
        base_data: Base extracted_data dict
        new_data: New extracted_data dict to merge
        base_confidence: Confidence score of base data
        new_confidence: Confidence score of new data
        
    Returns:
        Dict: Merged extracted_data
    """
    merged = base_data.copy() if base_data else {}
    
    for key, new_value in new_data.items():
        if key not in merged:
            # New key, add it
            merged[key] = new_value
        else:
            base_value = merged[key]
            
            # Handle different data types
            if isinstance(new_value, list) and isinstance(base_value, list):
                # Combine arrays, deduplicate
                combined = base_value + new_value
                # Deduplicate while preserving order
                seen = set()
                merged[key] = []
                for item in combined:
                    item_str = json.dumps(item, sort_keys=True) if isinstance(item, (dict, list)) else str(item)
                    if item_str not in seen:
                        seen.add(item_str)
                        merged[key].append(item)
            elif isinstance(new_value, dict) and isinstance(base_value, dict):
                # Recursively merge nested objects
                merged[key] = _merge_extracted_data(base_value, new_value, base_confidence, new_confidence)
            else:
                # For conflicts, prefer higher confidence value
                if new_confidence > base_confidence:
                    merged[key] = new_value
                # If confidence is equal or base is higher, keep base value
                # (already in merged dict)
    
    return merged


def _merge_summaries(
    base_summary: Any,
    new_summary: Any,
    base_confidence: float,
    new_confidence: float,
    llm: Optional[Any] = None,
    component_name: Optional[str] = None
) -> Any:
    """
    Merge summaries from two components intelligently.
    
    Args:
        base_summary: Base summary (can be dict or string)
        new_summary: New summary (can be dict or string)
        base_confidence: Confidence score of base summary
        new_confidence: Confidence score of new summary
        llm: Optional LLM instance for intelligent deduplication
        component_name: Optional component name for LLM context
        
    Returns:
        Merged summary
    """
    # Handle dict summaries
    if isinstance(base_summary, dict) and isinstance(new_summary, dict):
        merged = base_summary.copy()
        for key, new_value in new_summary.items():
            if key not in merged:
                merged[key] = new_value
            else:
                base_value = merged[key]
                # If both are strings, try intelligent deduplication first
                if isinstance(base_value, str) and isinstance(new_value, str):
                    # Try LLM-based deduplication if enabled and available
                    deduplicated = _try_deduplicate_strings(
                        [base_value, new_value],
                        f"{component_name or 'summary'}.{key}" if component_name else key,
                        llm
                    )
                    if deduplicated is not None:
                        merged[key] = deduplicated
                    else:
                        # Fall back to existing logic
                        if new_value not in base_value:
                            merged[key] = f"{base_value}. {new_value}" if base_value else new_value
                        else:
                            # If new value is already in base, prefer higher confidence
                            if new_confidence > base_confidence:
                                merged[key] = new_value
                else:
                    # For other types, prefer higher confidence
                    if new_confidence > base_confidence:
                        merged[key] = new_value
        return merged
    
    # Handle string summaries
    if isinstance(base_summary, str) and isinstance(new_summary, str):
        if not base_summary:
            return new_summary
        if not new_summary:
            return base_summary
        
        # Try LLM-based deduplication if enabled and available
        deduplicated = _try_deduplicate_strings(
            [base_summary, new_summary],
            component_name or "summary",
            llm
        )
        if deduplicated is not None:
            return deduplicated
        
        # Fall back to existing logic
        if new_summary not in base_summary:
            # Prefer more complete summary if confidence is similar
            if abs(new_confidence - base_confidence) < 10:
                # If confidence is similar, prefer longer/more detailed
                return new_summary if len(new_summary) > len(base_summary) else base_summary
            else:
                # Prefer higher confidence
                return new_summary if new_confidence > base_confidence else base_summary
        else:
            # If new summary is subset of base, keep base
            return base_summary if len(base_summary) >= len(new_summary) else new_summary
    
    # If types don't match, prefer higher confidence
    if new_confidence > base_confidence:
        return new_summary
    return base_summary


def _try_deduplicate_strings(
    summaries: List[str],
    component_name: str,
    llm: Optional[Any]
) -> Optional[str]:
    """
    Try to deduplicate strings using LLM if available and enabled.
    
    Args:
        summaries: List of summary strings to deduplicate
        component_name: Name of the component for context
        llm: Optional LLM instance
        
    Returns:
        Deduplicated string, or None if LLM unavailable or feature disabled
    """
    try:
        from app.core.config import settings
        from app.services.summary_deduplication_service import summary_deduplication_service
        
        # Check if feature is enabled
        if not getattr(settings, 'ENABLE_SUMMARY_DEDUPLICATION', True):
            return None
        
        # Check if we have enough summaries and they're long enough
        valid_summaries = [s for s in summaries if s and s.strip()]
        if len(valid_summaries) < 2:
            return None
        
        # Check combined length threshold (avoid LLM calls for very short summaries)
        combined_length = sum(len(s) for s in valid_summaries)
        if combined_length < 200:
            return None
        
        # Try deduplication if LLM is available
        if llm:
            return summary_deduplication_service.deduplicate_and_summarize(
                valid_summaries,
                component_name,
                llm
            )
        
        return None
    except Exception as e:
        # Log but don't fail - always fall back to existing logic
        logger.debug(f"Failed to deduplicate summaries for {component_name}: {str(e)}")
        return None


def merge_components_results(
    components_results_list: List[Dict[str, Any]],
    llm: Optional[Any] = None
) -> Dict[str, Any]:
    """
    Merge document components results from multiple PDFs.
    
    Args:
        components_results_list: List of components results dictionaries from different PDFs
        llm: Optional LLM instance for intelligent summary deduplication
        
    Returns:
        Dict: Merged components results
    """
    if not components_results_list:
        return {"initial_components": {}, "conditional_components": {}}
    
    # Filter out None/empty results
    valid_results = [r for r in components_results_list if r is not None]
    if not valid_results:
        return {"initial_components": {}, "conditional_components": {}}
    
    merged = {
        "initial_components": {},
        "conditional_components": {}
    }
    
    # Collect all component names
    all_initial_components = set()
    all_conditional_components = set()
    
    for result_dict in valid_results:
        if isinstance(result_dict, dict):
            if 'initial_components' in result_dict:
                all_initial_components.update(result_dict['initial_components'].keys())
            if 'conditional_components' in result_dict:
                all_conditional_components.update(result_dict['conditional_components'].keys())
    
    # Merge initial components
    for component_name in all_initial_components:
        component_results = []
        for result_dict in valid_results:
            if 'initial_components' in result_dict and component_name in result_dict['initial_components']:
                component_results.append(result_dict['initial_components'][component_name])
        
        if component_results:
            # Sort by confidence (higher first), then by present flag
            component_results.sort(
                key=lambda x: (
                    x.get('confidence', 0.0) or 0.0,
                    x.get('present', False)
                ),
                reverse=True
            )
            
            # Use component with highest confidence as base
            best_component = component_results[0].copy()
            best_confidence = best_component.get('confidence', 0.0) or 0.0
            
            # Collect all summaries for batch deduplication if LLM is available
            all_summaries = []
            if best_component.get('summary'):
                all_summaries.append(best_component.get('summary'))
            
            # Merge other components into the best one
            for comp in component_results[1:]:
                comp_confidence = comp.get('confidence', 0.0) or 0.0
                
                # Merge pages - preserve document_id structure
                best_pages = best_component.get('pages', [])
                comp_pages = comp.get('pages', [])
                # Convert to sets of tuples for deduplication if they're dicts with document_id
                if best_pages and isinstance(best_pages[0], dict) and "document_id" in best_pages[0]:
                    seen = set()
                    merged_pages = []
                    for page in best_pages + comp_pages:
                        if isinstance(page, dict) and "document_id" in page and "page" in page:
                            key = (page["document_id"], page["page"])
                            if key not in seen:
                                seen.add(key)
                                merged_pages.append(page)
                        else:
                            if page not in seen:
                                seen.add(page)
                                merged_pages.append(page)
                    merged_pages.sort(key=lambda x: (x.get("document_id", 0), x.get("page", 0)) if isinstance(x, dict) else (0, 0))
                    best_component['pages'] = merged_pages
                else:
                    # Legacy format: just page numbers
                    best_pages_set = set(best_pages)
                    comp_pages_set = set(comp_pages)
                    best_component['pages'] = sorted(list(best_pages_set | comp_pages_set))
                
                # Merge extracted_data intelligently
                if comp.get('extracted_data'):
                    best_component['extracted_data'] = _merge_extracted_data(
                        best_component.get('extracted_data', {}),
                        comp.get('extracted_data', {}),
                        best_confidence,
                        comp_confidence
                    )
                
                # Collect summaries for batch deduplication
                if comp.get('summary'):
                    all_summaries.append(comp.get('summary'))
                
                # Update present flag (if any component is present, mark as present)
                if comp.get('present', False):
                    best_component['present'] = True
            
            # Handle summary merging: try batch deduplication first, then fall back to incremental
            if len(all_summaries) >= 2:
                # Try LLM-based batch deduplication if available
                if llm:
                    deduplicated = _try_deduplicate_strings(
                        all_summaries,
                        component_name,
                        llm
                    )
                    if deduplicated is not None:
                        best_component['summary'] = deduplicated
                    else:
                        # Fall back to incremental merging
                        current_summary = all_summaries[0]
                        for summary in all_summaries[1:]:
                            current_summary = _merge_summaries(
                                current_summary,
                                summary,
                                best_confidence,
                                best_confidence,  # Use same confidence for all
                                llm=None,  # No LLM for fallback
                                component_name=component_name
                            )
                        best_component['summary'] = current_summary
                else:
                    # No LLM available, use incremental merging
                    current_summary = all_summaries[0]
                    for summary in all_summaries[1:]:
                        current_summary = _merge_summaries(
                            current_summary,
                            summary,
                            best_confidence,
                            best_confidence,  # Use same confidence for all
                            llm=None,  # No LLM
                            component_name=component_name
                        )
                    best_component['summary'] = current_summary
            elif len(all_summaries) == 1:
                best_component['summary'] = all_summaries[0]
            
            merged['initial_components'][component_name] = best_component
    
    # Merge conditional components
    for component_name in all_conditional_components:
        component_results = []
        for result_dict in valid_results:
            if 'conditional_components' in result_dict and component_name in result_dict['conditional_components']:
                comp = result_dict['conditional_components'][component_name]
                if comp.get('condition_met', False) and comp.get('present', False):
                    component_results.append(comp)
        
        if component_results:
            # Sort by confidence (higher first)
            component_results.sort(
                key=lambda x: x.get('confidence', 0.0) or 0.0,
                reverse=True
            )
            
            # Use component with highest confidence as base
            best_component = component_results[0].copy()
            best_confidence = best_component.get('confidence', 0.0) or 0.0
            
            # Collect all summaries for batch deduplication
            all_summaries = []
            if best_component.get('summary'):
                all_summaries.append(best_component.get('summary'))
            
            # Merge other components into the best one
            for comp in component_results[1:]:
                comp_confidence = comp.get('confidence', 0.0) or 0.0
                
                # Merge pages - preserve document_id structure
                best_pages = best_component.get('pages', [])
                comp_pages = comp.get('pages', [])
                # Convert to sets of tuples for deduplication if they're dicts with document_id
                if best_pages and isinstance(best_pages[0], dict) and "document_id" in best_pages[0]:
                    seen = set()
                    merged_pages = []
                    for page in best_pages + comp_pages:
                        if isinstance(page, dict) and "document_id" in page and "page" in page:
                            key = (page["document_id"], page["page"])
                            if key not in seen:
                                seen.add(key)
                                merged_pages.append(page)
                        else:
                            if page not in seen:
                                seen.add(page)
                                merged_pages.append(page)
                    merged_pages.sort(key=lambda x: (x.get("document_id", 0), x.get("page", 0)) if isinstance(x, dict) else (0, 0))
                    best_component['pages'] = merged_pages
                else:
                    # Legacy format: just page numbers
                    best_pages_set = set(best_pages)
                    comp_pages_set = set(comp_pages)
                    best_component['pages'] = sorted(list(best_pages_set | comp_pages_set))
                
                # Merge extracted_data intelligently
                if comp.get('extracted_data'):
                    best_component['extracted_data'] = _merge_extracted_data(
                        best_component.get('extracted_data', {}),
                        comp.get('extracted_data', {}),
                        best_confidence,
                        comp_confidence
                    )
                
                # Collect summaries for batch deduplication
                if comp.get('summary'):
                    all_summaries.append(comp.get('summary'))
                
                # Update present flag
                if comp.get('present', False):
                    best_component['present'] = True
            
            # Handle summary merging: try batch deduplication first, then fall back to incremental
            if len(all_summaries) >= 2:
                # Try LLM-based batch deduplication if available
                if llm:
                    deduplicated = _try_deduplicate_strings(
                        all_summaries,
                        component_name,
                        llm
                    )
                    if deduplicated is not None:
                        best_component['summary'] = deduplicated
                    else:
                        # Fall back to incremental merging
                        current_summary = all_summaries[0]
                        for summary in all_summaries[1:]:
                            current_summary = _merge_summaries(
                                current_summary,
                                summary,
                                best_confidence,
                                best_confidence,
                                llm=None,
                                component_name=component_name
                            )
                        best_component['summary'] = current_summary
                else:
                    # No LLM available, use incremental merging
                    current_summary = all_summaries[0]
                    for summary in all_summaries[1:]:
                        current_summary = _merge_summaries(
                            current_summary,
                            summary,
                            best_confidence,
                            best_confidence,
                            llm=None,
                            component_name=component_name
                        )
                    best_component['summary'] = current_summary
            elif len(all_summaries) == 1:
                best_component['summary'] = all_summaries[0]
            
            merged['conditional_components'][component_name] = best_component
    
    return merged

