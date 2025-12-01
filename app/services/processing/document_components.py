import json
import os
import re
from typing import Dict, List, Tuple, Any
from langchain.schema import Document
from langchain_openai import AzureChatOpenAI
import logging
import ast
import time
from .topic_summarization import search_keywords, ts_llm_call_with_pause
from .utils.json_parser import safe_parse_llm_json, LLMResponseParseError

logger = logging.getLogger(__name__)


def calculate_component_confidence(
    component_info: Dict[str, Any],
    pages: List[int],
    document_created_at: Any = None
) -> float:
    """
    Calculate confidence score for a component extraction result.
    
    Confidence is calculated based on:
    - Data completeness: percentage of expected fields populated in extracted_data
    - Summary length/completeness: longer, more detailed summaries = higher confidence
    - Number of pages found: more pages = higher confidence (up to a limit)
    - Recency: newer documents = slightly higher confidence (optional)
    
    Args:
        component_info: Component information dict with 'extracted_data' and 'summary'
        pages: List of page numbers where component was found
        document_created_at: Optional datetime of document creation (for recency)
        
    Returns:
        float: Confidence score between 0.0 and 1.0 (0-100 scale)
    """
    confidence = 0.0
    
    # Factor 1: Data completeness (40% weight)
    # Check how many fields are populated in extracted_data
    extracted_data = component_info.get('extracted_data', {})
    if isinstance(extracted_data, dict):
        total_fields = len(extracted_data)
        non_empty_fields = sum(1 for v in extracted_data.values() if v not in [None, '', [], {}])
        if total_fields > 0:
            completeness_ratio = non_empty_fields / total_fields
        else:
            # If no fields expected, check if we have any data at all
            completeness_ratio = 1.0 if extracted_data else 0.0
    else:
        completeness_ratio = 0.0
    
    # Factor 2: Summary completeness (30% weight)
    # Longer, more detailed summaries indicate better extraction
    summary = component_info.get('summary', '')
    if isinstance(summary, dict):
        # If summary is a dict, count non-empty values
        summary_str = json.dumps(summary)
    else:
        summary_str = str(summary) if summary else ''
    
    summary_length = len(summary_str)
    # Normalize: summaries > 200 chars are considered complete
    summary_completeness = min(1.0, summary_length / 200.0) if summary_length > 0 else 0.0
    
    # Factor 3: Page count (20% weight)
    # More pages found = higher confidence, but with diminishing returns
    page_count = len(pages) if pages else 0
    if page_count == 0:
        page_confidence = 0.0
    elif page_count == 1:
        page_confidence = 0.5
    elif page_count <= 3:
        page_confidence = 0.7 + (page_count - 1) * 0.1
    else:
        page_confidence = 1.0  # 4+ pages = max confidence
    
    # Factor 4: Present flag (10% weight)
    # If component is marked as present, that's a positive signal
    present_confidence = 1.0 if component_info.get('present', False) else 0.5
    
    # Calculate weighted confidence
    confidence = (
        completeness_ratio * 0.40 +
        summary_completeness * 0.30 +
        page_confidence * 0.20 +
        present_confidence * 0.10
    )
    
    # Ensure confidence is between 0.0 and 1.0
    confidence = max(0.0, min(1.0, confidence))
    
    # Convert to 0-100 scale for storage
    return confidence * 100.0

# Get the base directory for config files (relative to this file)
_CONFIG_DIR = os.path.join(os.path.dirname(__file__), 'config')

def load_component_config(config_path: str = None) -> Dict:
    """
    Load document components configuration.
    
    Args:
        config_path: Path to configuration file (defaults to config/document_components_config.json)
        
    Returns:
        Dict: Configuration dictionary
    """
    if config_path is None:
        config_path = os.path.join(_CONFIG_DIR, "document_components_config.json")
    try:
        with open(config_path, 'r') as f:
            config = json.load(f)
        return config
    except Exception as e:
        logger.error(f"Error loading component config: {e}")
        return {}


def check_conditional_component_condition(
    component_name: str,
    component_config: Dict,
    topics_results: Dict
) -> bool:
    """
    Check if condition is met for a conditional component.
    
    Args:
        component_name: Name of the conditional component
        component_config: Configuration for the component
        topics_results: Results from topic summarization
        
    Returns:
        bool: True if condition is met, False otherwise
    """
    condition_check = component_config.get("condition_check", {})
    if not condition_check:
        return False
    
    topic_name = condition_check.get("topic")
    condition_field = condition_check.get("condition", "decision")
    expected_value = condition_check.get("expected_value", "Yes")
    
    if topic_name and topic_name in topics_results:
        topic_result = topics_results[topic_name]
        if isinstance(topic_result, dict):
            actual_value = topic_result.get(condition_field, "").strip()
            # Check if actual value matches expected (case-insensitive)
            return actual_value.lower() == expected_value.lower()
    
    return False


def create_component_extraction_prompt(
    component_name: str,
    component_config: Dict,
    context: List[Tuple[str, int]]
) -> str:
    """
    Create a prompt for extracting information from a document component.
    
    Args:
        component_name: Name of the component
        component_config: Configuration for the component
        context: Extracted context with page numbers
        
    Returns:
        str: Formatted prompt for LLM
    """
    description = component_config.get("description", "")
    extraction_prompt = component_config.get("extraction_prompt", "")
    sections = component_config.get("sections", {})
    
    # Format sections
    sections_text = "\n\n".join(
        f"Section: {section_name}\nContext: {section_context}"
        for section_name, section_context in sections.items()
    )
    
    section_summary_template = ",\n        ".join(
        [f'"{section_name}": "Summary of {section_name}"' for section_name in sections.keys()]
    )
    
    # Format extracted context with page numbers
    extracted_context = "\n".join([f"Page {page}: {text}" for text, page in context])
    
    prompt = f"""You are an expert medical director working for LifeNet Health, which is a leading organization in regenerative medicine and life sciences. Your task is to extract and summarize information from the {component_name} section of a donor chart document.

Component Description: {description}

{extraction_prompt}

Instructions:
1. Extract and summarize relevant information (if present) for the following sections:
{sections_text}

2. You must always return the output in the following JSON format with proper formatting. There should be no backticks (```) in the output. Only the JSON output:
{{
    "Summary": {{
        {section_summary_template}
    }},
    "Extracted_Data": {{
        "key1": "value1",
        "key2": "value2"
    }},
    "PRESENT": "Yes/No"
}}

DONOR DOCUMENT:
{extracted_context}

Key Tips:
- Extract all relevant information from the {component_name} section
- If the component is not present or not found, set "PRESENT" to "No" and return empty summaries
- Be thorough in extracting structured data where applicable
- Maintain accuracy of all extracted information

AI Response:"""
    
    return prompt


def extract_component_content(
    llm: AzureChatOpenAI,
    component_name: str,
    component_config: Dict,
    page_doc_list: List[Document],
    vectordb: Any = None
) -> Dict:
    """
    Extract content from a document component.
    
    Args:
        llm: LLM instance
        component_name: Name of the component
        component_config: Configuration for the component
        page_doc_list: List of page documents
        vectordb: Optional vector database for semantic search
        
    Returns:
        Dict: Extracted component information
    """
    keywords = component_config.get("keywords", [])
    description = component_config.get("description", "")
    
    # Try keyword search first
    page_info = []
    for keyword in keywords:
        keyword_results = search_keywords(page_doc_list, keyword)
        page_info.extend(keyword_results)
    
    # Remove duplicates while preserving order
    seen = set()
    unique_page_info = []
    for text, page in page_info:
        if (text, page) not in seen:
            seen.add((text, page))
            unique_page_info.append((text, page))
    
    # If no results from keyword search and vectordb available, try semantic search
    if not unique_page_info and vectordb is not None:
        try:
            retriever = vectordb.as_retriever(search_type='similarity', search_kwargs={'k': 5})
            ret_docs = retriever.invoke(description)
            unique_page_info = [
                (doc.page_content, doc.metadata['page'] + 1)
                for doc in ret_docs
            ]
        except Exception as e:
            logger.warning(f"Semantic search failed for {component_name}: {e}")
    
    # Extract pages
    pages = sorted(list(set([page for _, page in unique_page_info]))) if unique_page_info else []
    
    # If no pages found, return not present
    if not pages:
        return {
            "present": False,
            "pages": [],
            "summary": "",
            "extracted_data": {},
            "citations": [],
            "confidence": 0.0
        }
    
    # Create prompt and extract content
    try:
        prompt = create_component_extraction_prompt(component_name, component_config, unique_page_info)
        response = ts_llm_call_with_pause(llm, component_name, prompt)
        
        # Parse response using robust JSON parser
        try:
            result = safe_parse_llm_json(
                response.content,
                context=f"component extraction for {component_name}"
            )
            
            # Validate structure
            if not isinstance(result, dict):
                raise LLMResponseParseError(
                    f"Expected dictionary but got {type(result)}. "
                    f"Context: component extraction for {component_name}"
                )
            
        except LLMResponseParseError as e:
            logger.error(f"Failed to parse component extraction result for {component_name}: {e}")
            # Return error structure
            return {
                "component_name": component_name,
                "error": True,
                "error_type": "parse_error",
                "error_message": str(e),
                "raw_response_preview": response.content[:500] if hasattr(response, 'content') else str(response)[:500],
                "summary": {},
                "extracted_data": {},
                "present": False,
                "confidence": 0.0
            }
        
        # Extract information
        summary = result.get("Summary", {})
        extracted_data = result.get("Extracted_Data", {})
        present = result.get("PRESENT", "Yes").lower() == "yes"
        
        # Build component info for confidence calculation
        component_info = {
            "present": present,
            "summary": summary,
            "extracted_data": extracted_data
        }
        
        # Calculate confidence score
        confidence = calculate_component_confidence(component_info, pages)
        
        return {
            "present": present,
            "pages": pages,
            "summary": summary,
            "extracted_data": extracted_data,
            "citations": pages,
            "confidence": confidence
        }
    except Exception as e:
        logger.error(f"Error extracting content for {component_name}: {e}")
        # Calculate confidence even for error cases (will be low)
        component_info = {
            "present": len(pages) > 0,
            "summary": f"Error during extraction: {str(e)}",
            "extracted_data": {}
        }
        confidence = calculate_component_confidence(component_info, pages)
        
        return {
            "present": len(pages) > 0,
            "pages": pages,
            "summary": f"Error during extraction: {str(e)}",
            "extracted_data": {},
            "citations": pages,
            "confidence": confidence
        }


def get_document_components(
    llm: AzureChatOpenAI,
    page_doc_list: List[Document],
    vectordb: Any,
    topics_results: Dict = None,
    config_path: str = None
) -> Dict:
    """
    Extract all document components (initial and conditional).
    
    Args:
        llm: LLM instance
        page_doc_list: List of page documents
        vectordb: Vector database for semantic search
        topics_results: Results from topic summarization (for conditional components)
        config_path: Path to component configuration file
        
    Returns:
        Dict: Dictionary containing initial_components and conditional_components
    """
    config = load_component_config(config_path)
    if not config:
        return {"initial_components": {}, "conditional_components": {}}
    
    initial_components_config = config.get("initial_components", {})
    conditional_components_config = config.get("conditional_components", {})
    
    results = {
        "initial_components": {},
        "conditional_components": {}
    }
    
    # Process initial components
    logger.info(f"Processing {len(initial_components_config)} initial components...")
    for component_name, component_config in initial_components_config.items():
        logger.info(f"Extracting component: {component_name}")
        component_result = extract_component_content(
            llm, component_name, component_config, page_doc_list, vectordb
        )
        results["initial_components"][component_name] = component_result
    
    # Process conditional components
    logger.info(f"Processing {len(conditional_components_config)} conditional components...")
    for component_name, component_config in conditional_components_config.items():
        # Check if condition is met
        condition_met = False
        if topics_results:
            condition_met = check_conditional_component_condition(
                component_name, component_config, topics_results
            )
        
        if condition_met:
            logger.info(f"Condition met for {component_name}, extracting...")
            component_result = extract_component_content(
                llm, component_name, component_config, page_doc_list, vectordb
            )
            component_result["condition_met"] = True
            results["conditional_components"][component_name] = component_result
        else:
            logger.info(f"Condition not met for {component_name}, skipping...")
            results["conditional_components"][component_name] = {
                "condition_met": False,
                "present": False,
                "pages": [],
                "summary": "",
                "extracted_data": {},
                "citations": []
            }
    
    # Calculate completeness
    initial_present = sum(1 for c in results["initial_components"].values() if c.get("present", False))
    conditional_present = sum(
        1 for c in results["conditional_components"].values()
        if c.get("condition_met", False) and c.get("present", False)
    )
    conditional_expected = sum(
        1 for c in results["conditional_components"].values()
        if c.get("condition_met", False)
    )
    
    results["completeness_check"] = {
        "required_components_present": initial_present,
        "required_components_total": len(initial_components_config),
        "conditional_components_present": conditional_present,
        "conditional_components_expected": conditional_expected
    }
    
    return results

