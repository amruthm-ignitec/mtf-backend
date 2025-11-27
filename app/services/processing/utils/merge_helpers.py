"""
Helper functions for merging extraction results from multiple documents.
Copied from mtf-backend-test/utils/test_helpers.py
"""
import json
import logging
from typing import Dict, List, Any

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
                all_citations.extend(result_dict['citations'])
    
    # Deduplicate citations
    unique_citations = sorted(list(set(all_citations)))
    
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
                all_citations.extend(result_dict['citations'])
    
    # Deduplicate citations
    unique_citations = sorted(list(set(all_citations)))
    
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
                        all_citations.extend(citations)
                    elif isinstance(citations, (int, str)):
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
            
            # Merge citations - normalize to integers for sorting
            normalized_citations = []
            for citation in all_citations:
                if isinstance(citation, int):
                    normalized_citations.append(citation)
                elif isinstance(citation, str):
                    try:
                        if citation.isdigit():
                            normalized_citations.append(int(citation))
                        elif ':' in citation:
                            parts = citation.split(':')
                            for part in parts:
                                part = part.strip()
                                if part.isdigit():
                                    normalized_citations.append(int(part))
                                    break
                        else:
                            normalized_citations.append(citation)
                    except (ValueError, AttributeError):
                        normalized_citations.append(citation)
                else:
                    try:
                        normalized_citations.append(int(citation))
                    except (ValueError, TypeError):
                        normalized_citations.append(citation)
            
            # Remove duplicates and sort
            int_citations = [c for c in normalized_citations if isinstance(c, int)]
            str_citations = [c for c in normalized_citations if isinstance(c, str)]
            
            unique_int_citations = sorted(list(set(int_citations)))
            unique_str_citations = sorted(list(set(str_citations)))
            unique_citations = unique_int_citations + unique_str_citations
            
            # Create merged result
            merged_topic = best_result.copy()
            merged_topic['citation'] = unique_citations
            merged_topics[topic] = merged_topic
    
    return merged_topics


def merge_components_results(components_results_list: List[Dict[str, Any]]) -> Dict[str, Any]:
    """
    Merge document components results from multiple PDFs.
    
    Args:
        components_results_list: List of components results dictionaries from different PDFs
        
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
            # Use the first present component, or merge if needed
            best_component = None
            for comp in component_results:
                if comp.get('present', False):
                    if best_component is None:
                        best_component = comp
                    else:
                        # Merge pages and data
                        best_pages = set(best_component.get('pages', []))
                        comp_pages = set(comp.get('pages', []))
                        best_component['pages'] = sorted(list(best_pages | comp_pages))
            
            if best_component is None:
                best_component = component_results[0]
            
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
            # Use the first present component
            best_component = component_results[0]
            for comp in component_results[1:]:
                # Merge pages
                best_pages = set(best_component.get('pages', []))
                comp_pages = set(comp.get('pages', []))
                best_component['pages'] = sorted(list(best_pages | comp_pages))
            
            merged['conditional_components'][component_name] = best_component
    
    return merged

