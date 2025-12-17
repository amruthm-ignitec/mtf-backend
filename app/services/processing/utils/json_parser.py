"""
Robust JSON parsing utility for LLM responses.
Handles various response formats with multiple fallback strategies.
"""
import json
import ast
import re
import logging
from typing import Dict, Any, Optional, Union

logger = logging.getLogger(__name__)


class LLMResponseParseError(Exception):
    """Custom exception for LLM response parsing errors."""
    pass


def safe_parse_llm_json(response_content: str, context: str = "") -> Dict[str, Any]:
    """
    Safely parse LLM JSON response with multiple fallback strategies.
    
    Args:
        response_content: Raw response content from LLM
        context: Optional context string for error messages (e.g., "culture extraction")
        
    Returns:
        Parsed dictionary
        
    Raises:
        LLMResponseParseError: If all parsing strategies fail
    """
    if not response_content or not isinstance(response_content, str):
        raise LLMResponseParseError(
            f"Invalid response content type: {type(response_content)}. "
            f"Context: {context}"
        )
    
    # Strategy 1: Clean and try direct JSON parsing
    cleaned = _clean_response(response_content)
    
    try:
        return json.loads(cleaned)
    except json.JSONDecodeError:
        pass
    
    # Strategy 2: Try extracting JSON from markdown code blocks
    try:
        json_match = re.search(r'```(?:json)?\s*(\{.*?\})\s*```', cleaned, re.DOTALL)
        if json_match:
            return json.loads(json_match.group(1))
    except (json.JSONDecodeError, AttributeError):
        pass
    
    # Strategy 3: Try extracting JSON object using regex (more permissive)
    try:
        json_match = re.search(r'\{[^{}]*(?:\{[^{}]*\}[^{}]*)*\}', cleaned, re.DOTALL)
        if json_match:
            return json.loads(json_match.group(0))
    except (json.JSONDecodeError, AttributeError):
        pass
    
    # Strategy 4: Try ast.literal_eval for Python dict syntax
    try:
        result = ast.literal_eval(cleaned)
        if isinstance(result, dict):
            return result
    except (ValueError, SyntaxError):
        pass
    
    # Strategy 5: Try parsing after removing common LLM artifacts
    try:
        # Remove common prefixes/suffixes
        cleaned_alt = cleaned
        for pattern in [
            r'^AI Response:\s*',
            r'^Response:\s*',
            r'^Output:\s*',
            r'^Result:\s*',
            r'Here is.*?:',
            r'Here\'s.*?:',
        ]:
            cleaned_alt = re.sub(pattern, '', cleaned_alt, flags=re.IGNORECASE)
        
        cleaned_alt = cleaned_alt.strip()
        if cleaned_alt != cleaned:
            return json.loads(cleaned_alt)
    except json.JSONDecodeError:
        pass
    
    # Strategy 6: Try lowercasing keys only (not entire response)
    try:
        # Find JSON-like structure and lowercase only keys
        json_match = re.search(r'\{.*\}', cleaned, re.DOTALL)
        if json_match:
            json_str = json_match.group(0)
            # Replace "key": with "key_lower": but keep values intact
            # This is a last resort - may not work for all cases
            parsed = json.loads(json_str)
            return {k.lower(): v for k, v in parsed.items()}
    except (json.JSONDecodeError, AttributeError, TypeError):
        pass
    
    # All strategies failed
    error_msg = (
        f"Unable to parse LLM response as JSON. "
        f"Context: {context}. "
        f"Response preview: {response_content[:500]}"
    )
    logger.error(error_msg)
    raise LLMResponseParseError(error_msg)


def _clean_response(response_content: str) -> str:
    """
    Clean response content by removing common artifacts.
    
    Args:
        response_content: Raw response content
        
    Returns:
        Cleaned response content
    """
    cleaned = response_content.strip()
    
    # Remove markdown code block markers
    if cleaned.startswith("```"):
        # Extract content from code blocks
        parts = cleaned.split("```")
        if len(parts) >= 3:
            # Take the middle part (content between markers)
            cleaned = parts[1]
            # Remove language identifier if present
            if cleaned.startswith("json"):
                cleaned = cleaned[4:].strip()
            elif cleaned.startswith("python"):
                cleaned = cleaned[6:].strip()
    
    # Remove common prefixes
    prefixes = [
        "AI Response:",
        "Response:",
        "Output:",
        "Result:",
        "Here is the",
        "Here's the",
    ]
    for prefix in prefixes:
        if cleaned.lower().startswith(prefix.lower()):
            cleaned = cleaned[len(prefix):].strip()
            # Remove colon if present
            if cleaned.startswith(":"):
                cleaned = cleaned[1:].strip()
    
    return cleaned.strip()


def validate_json_structure(
    parsed_data: Dict[str, Any],
    expected_keys: Optional[list] = None,
    required_keys: Optional[list] = None
) -> bool:
    """
    Validate that parsed JSON has expected structure.
    
    Args:
        parsed_data: Parsed dictionary
        expected_keys: List of keys that should be present
        required_keys: List of keys that must be present
        
    Returns:
        True if valid, False otherwise
    """
    if not isinstance(parsed_data, dict):
        return False
    
    if required_keys:
        for key in required_keys:
            if key not in parsed_data:
                logger.warning(f"Required key '{key}' missing from parsed data")
                return False
    
    if expected_keys:
        unexpected = set(parsed_data.keys()) - set(expected_keys)
        if unexpected:
            logger.debug(f"Unexpected keys found: {unexpected}")
    
    return True


def parse_with_validation(
    response_content: str,
    context: str = "",
    expected_keys: Optional[list] = None,
    required_keys: Optional[list] = None
) -> Dict[str, Any]:
    """
    Parse LLM response and validate structure.
    
    Args:
        response_content: Raw response content
        context: Context for error messages
        expected_keys: Keys that should be present
        required_keys: Keys that must be present
        
    Returns:
        Parsed and validated dictionary
        
    Raises:
        LLMResponseParseError: If parsing or validation fails
    """
    parsed = safe_parse_llm_json(response_content, context)
    
    if not validate_json_structure(parsed, expected_keys, required_keys):
        error_msg = (
            f"Parsed JSON does not match expected structure. "
            f"Context: {context}. "
            f"Required keys: {required_keys}. "
            f"Expected keys: {expected_keys}"
        )
        logger.error(error_msg)
        raise LLMResponseParseError(error_msg)
    
    return parsed






