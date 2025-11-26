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

logger = logging.getLogger(__name__)

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
            "citations": []
        }
    
    # Create prompt and extract content
    try:
        prompt = create_component_extraction_prompt(component_name, component_config, unique_page_info)
        response = ts_llm_call_with_pause(llm, component_name, prompt)
        
        # Parse response
        response_content = response.content.replace("`", "").replace("json", "").strip()
        try:
            result = ast.literal_eval(response_content)
        except:
            # Try JSON parsing
            result = json.loads(response_content)
        
        # Extract information
        summary = result.get("Summary", {})
        extracted_data = result.get("Extracted_Data", {})
        present = result.get("PRESENT", "Yes").lower() == "yes"
        
        return {
            "present": present,
            "pages": pages,
            "summary": summary,
            "extracted_data": extracted_data,
            "citations": pages
        }
    except Exception as e:
        logger.error(f"Error extracting content for {component_name}: {e}")
        return {
            "present": len(pages) > 0,
            "pages": pages,
            "summary": f"Error during extraction: {str(e)}",
            "extracted_data": {},
            "citations": pages
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

