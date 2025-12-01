"""
Input validation utilities for document processing.
Validates file types, sizes, and LLM response structures.
"""
import os
import logging
from typing import Dict, Any, Optional, List
from pathlib import Path

logger = logging.getLogger(__name__)


class ValidationError(Exception):
    """Base exception for validation errors."""
    pass


class FileTypeError(ValidationError):
    """Exception raised when file type is invalid."""
    pass


class FileSizeError(ValidationError):
    """Exception raised when file size exceeds limit."""
    pass


class ResponseStructureError(ValidationError):
    """Exception raised when LLM response structure is invalid."""
    pass


# Allowed file types and their MIME types
ALLOWED_FILE_TYPES = {
    '.pdf': 'application/pdf',
}

# Maximum file size (50MB)
MAX_FILE_SIZE = 50 * 1024 * 1024  # 50MB in bytes


def validate_file_type(file_path: str, allowed_extensions: Optional[List[str]] = None) -> bool:
    """
    Validate that file has an allowed extension.
    
    Args:
        file_path: Path to the file
        allowed_extensions: List of allowed extensions (defaults to ALLOWED_FILE_TYPES keys)
        
    Returns:
        True if valid
        
    Raises:
        FileTypeError: If file type is not allowed
    """
    if allowed_extensions is None:
        allowed_extensions = list(ALLOWED_FILE_TYPES.keys())
    
    file_ext = Path(file_path).suffix.lower()
    
    if file_ext not in allowed_extensions:
        raise FileTypeError(
            f"File type '{file_ext}' is not allowed. "
            f"Allowed types: {', '.join(allowed_extensions)}"
        )
    
    return True


def validate_file_size(file_path: str, max_size: int = MAX_FILE_SIZE) -> bool:
    """
    Validate that file size is within limits.
    
    Args:
        file_path: Path to the file
        max_size: Maximum file size in bytes
        
    Returns:
        True if valid
        
    Raises:
        FileSizeError: If file size exceeds limit
    """
    if not os.path.exists(file_path):
        raise FileNotFoundError(f"File not found: {file_path}")
    
    file_size = os.path.getsize(file_path)
    
    if file_size > max_size:
        size_mb = file_size / (1024 * 1024)
        max_size_mb = max_size / (1024 * 1024)
        raise FileSizeError(
            f"File size ({size_mb:.2f}MB) exceeds maximum allowed size ({max_size_mb:.2f}MB). "
            f"File: {file_path}"
        )
    
    if file_size == 0:
        raise FileSizeError(f"File is empty: {file_path}")
    
    return True


def validate_document_file(file_path: str) -> Dict[str, Any]:
    """
    Comprehensive validation of a document file.
    
    Args:
        file_path: Path to the file
        
    Returns:
        Dictionary with validation results
        
    Raises:
        ValidationError: If validation fails
    """
    validation_result = {
        "valid": True,
        "file_path": file_path,
        "file_size": 0,
        "file_type": None,
        "errors": [],
        "warnings": []
    }
    
    try:
        # Check file exists
        if not os.path.exists(file_path):
            raise FileNotFoundError(f"File not found: {file_path}")
        
        # Validate file type
        try:
            validate_file_type(file_path)
            validation_result["file_type"] = Path(file_path).suffix.lower()
        except FileTypeError as e:
            validation_result["errors"].append(str(e))
            validation_result["valid"] = False
        
        # Validate file size
        try:
            validate_file_size(file_path)
            validation_result["file_size"] = os.path.getsize(file_path)
        except FileSizeError as e:
            validation_result["errors"].append(str(e))
            validation_result["valid"] = False
        
        # Check if file is readable
        try:
            with open(file_path, 'rb') as f:
                f.read(1)  # Try to read first byte
        except IOError as e:
            validation_result["errors"].append(f"Cannot read file: {str(e)}")
            validation_result["valid"] = False
        
        if validation_result["errors"]:
            raise ValidationError(
                f"File validation failed: {', '.join(validation_result['errors'])}"
            )
        
        return validation_result
        
    except Exception as e:
        logger.error(f"Error validating file {file_path}: {e}", exc_info=True)
        validation_result["valid"] = False
        validation_result["errors"].append(str(e))
        raise ValidationError(f"File validation failed: {str(e)}") from e


def validate_culture_response(response_data: Dict[str, Any]) -> bool:
    """
    Validate structure of culture extraction response.
    
    Args:
        response_data: Parsed response dictionary
        
    Returns:
        True if valid
        
    Raises:
        ResponseStructureError: If structure is invalid
    """
    if not isinstance(response_data, dict):
        raise ResponseStructureError(
            f"Expected dictionary but got {type(response_data)}"
        )
    
    # Check for error structure
    if response_data.get("error"):
        # Error responses are valid structures
        return True
    
    # Validate that values are lists (microorganisms)
    for tissue_location, microorganisms in response_data.items():
        if not isinstance(microorganisms, list):
            raise ResponseStructureError(
                f"Expected list of microorganisms for '{tissue_location}', "
                f"but got {type(microorganisms)}"
            )
    
    return True


def validate_serology_response(response_data: Dict[str, Any]) -> bool:
    """
    Validate structure of serology extraction response.
    
    Args:
        response_data: Parsed response dictionary
        
    Returns:
        True if valid
        
    Raises:
        ResponseStructureError: If structure is invalid
    """
    if not isinstance(response_data, dict):
        raise ResponseStructureError(
            f"Expected dictionary but got {type(response_data)}"
        )
    
    # Check for error structure
    if response_data.get("error"):
        return True
    
    # Validate that values are strings (test results)
    for test_name, result in response_data.items():
        if not isinstance(result, str):
            raise ResponseStructureError(
                f"Expected string result for test '{test_name}', "
                f"but got {type(result)}"
            )
    
    return True


def validate_component_response(response_data: Dict[str, Any]) -> bool:
    """
    Validate structure of component extraction response.
    
    Args:
        response_data: Parsed response dictionary
        
    Returns:
        True if valid
        
    Raises:
        ResponseStructureError: If structure is invalid
    """
    if not isinstance(response_data, dict):
        raise ResponseStructureError(
            f"Expected dictionary but got {type(response_data)}"
        )
    
    # Check for error structure
    if response_data.get("error"):
        return True
    
    # Required keys
    required_keys = ["Summary", "Extracted_Data", "PRESENT"]
    for key in required_keys:
        if key not in response_data:
            raise ResponseStructureError(
                f"Missing required key '{key}' in component response"
            )
    
    # Validate types
    if not isinstance(response_data.get("Summary"), dict):
        raise ResponseStructureError("'Summary' must be a dictionary")
    
    if not isinstance(response_data.get("Extracted_Data"), dict):
        raise ResponseStructureError("'Extracted_Data' must be a dictionary")
    
    return True


def validate_topic_response(response_data: Dict[str, Any]) -> bool:
    """
    Validate structure of topic summarization response.
    
    Args:
        response_data: Parsed response dictionary
        
    Returns:
        True if valid
        
    Raises:
        ResponseStructureError: If structure is invalid
    """
    if not isinstance(response_data, dict):
        raise ResponseStructureError(
            f"Expected dictionary but got {type(response_data)}"
        )
    
    # Check for error structure
    if "Error" in response_data:
        return True
    
    # Required keys for topic responses
    required_keys = ["presence", "pages"]
    for key in required_keys:
        if key not in response_data:
            raise ResponseStructureError(
                f"Missing required key '{key}' in topic response"
            )
    
    # Validate types
    if not isinstance(response_data.get("presence"), str):
        raise ResponseStructureError("'presence' must be a string")
    
    if not isinstance(response_data.get("pages"), list):
        raise ResponseStructureError("'pages' must be a list")
    
    return True



