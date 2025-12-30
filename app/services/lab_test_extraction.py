"""
Unified lab test extraction service.
Extracts only required serology and culture tests as specified in acceptance criteria.
"""
import json
import os
import logging
from typing import Dict, Any, List, Optional
from sqlalchemy.orm import Session
from app.models.laboratory_result import LaboratoryResult, TestType
from app.services.processing.utils.llm_wrapper import call_llm_with_retry, LLMCallError
from app.services.processing.utils.json_parser import safe_parse_llm_json, LLMResponseParseError
from app.services.processing.serology import parse_test_name_and_method

logger = logging.getLogger(__name__)

# Get config directory
_CONFIG_DIR = os.path.join(os.path.dirname(__file__), 'processing', 'config')


def load_required_tests_config() -> Dict[str, Any]:
    """Load required test configurations."""
    serology_path = os.path.join(_CONFIG_DIR, 'required_serology_tests.json')
    culture_path = os.path.join(_CONFIG_DIR, 'required_culture_tests.json')
    
    with open(serology_path, 'r') as f:
        serology_config = json.load(f)
    
    with open(culture_path, 'r') as f:
        culture_config = json.load(f)
    
    return {
        'serology': serology_config,
        'culture': culture_config
    }


def extract_required_serology_tests(
    document_id: int,
    vectordb: Any,
    llm: Any,
    db: Session,
    role_dict: Dict[str, str],
    instruction_dict: Dict[str, str],
    reminder_dict: Dict[str, str],
    serology_dictionary: Dict[str, Any]
) -> int:
    """
    Extract only required serology tests and store in laboratory_results table.
    
    Returns:
        Number of test results stored
    """
    try:
        # Load required tests config
        config = load_required_tests_config()
        required_tests = config['serology']['required_tests']
        
        # Build list of test names and aliases to search for
        test_names_to_extract = []
        for test in required_tests:
            test_names_to_extract.append(test['test_name'])
            test_names_to_extract.extend(test.get('aliases', []))
        
        # Retrieve relevant chunks from vector database
        # Use a query that searches for serology-related content
        query = "serology test results infectious disease screening blood typing"
        retriever = vectordb.as_retriever(search_type='similarity', search_kwargs={'k': 10})
        retrieved_docs = retriever.invoke(query)
        
        if not retrieved_docs:
            logger.info(f"No relevant chunks found for serology extraction in document {document_id}")
            return 0
        
        # Build donor info context from retrieved chunks
        donor_info = "\n".join([
            f"Page {doc.metadata.get('page', '?')}: {doc.page_content}"
            for doc in retrieved_docs
        ])
        
        # Get role, instruction, and reminder for serology
        role = role_dict.get('Serology test', '')
        basic_instruction = instruction_dict.get('Serology test', '')
        reminder_instructions = reminder_dict.get('Serology test', '')
        
        # Create focused instruction for required tests only
        required_tests_list = ", ".join([test['test_name'] for test in required_tests])
        focused_instruction = f"""{basic_instruction}

IMPORTANT: Extract ONLY the following serology tests and their results:
{required_tests_list}

For each test, extract the test name EXACTLY as it appears, including any abbreviations or method designations.
Extract results EXACTLY as they appear: Positive, Negative, Non-Reactive, Reactive, Equivocal, etc.

If a test is not found in the document, do NOT include it in the output."""
        
        # Call LLM for extraction
        prompt = f"""{role}
Instruction: {focused_instruction}

CRITICAL: Extract information ONLY from the provided donor document. Do not use information from other donors, documents, or your training data.

Relevant donor information:
{donor_info}

{reminder_instructions} DO NOT return any other character or word (like ``` or 'json') but the required result JSON.
AI Response: """
        
        response = call_llm_with_retry(
            llm=llm,
            prompt=prompt,
            max_retries=3,
            base_delay=1.0,
            timeout=60,
            context="serology extraction"
        )
        
        # Parse JSON response
        try:
            result_dict = safe_parse_llm_json(response.content)
        except LLMResponseParseError as e:
            logger.error(f"Failed to parse serology LLM response for document {document_id}: {e}")
            return 0
        
        # Store results in database
        count = 0
        for test_name, result_value in result_dict.items():
            if not result_value:
                continue
            
            # Parse test name and method
            clean_test_name, test_method = parse_test_name_and_method(test_name)
            
            # Check if this test is in our required list (by matching against aliases)
            is_required = False
            for required_test in required_tests:
                if (clean_test_name.lower() in [t.lower() for t in [required_test['test_name']] + required_test.get('aliases', [])] or
                    any(alias.lower() in test_name.lower() for alias in required_test.get('aliases', []))):
                    is_required = True
                    # Use the canonical test name
                    clean_test_name = required_test['test_name']
                    break
            
            if not is_required:
                # Skip tests not in required list
                continue
            
            # Get source page from citations if available
            source_page = None
            for doc in retrieved_docs:
                if test_name.lower() in doc.page_content.lower() or result_value.lower() in doc.page_content.lower():
                    source_page = doc.metadata.get('page')
                    break
            
            # Store in database
            lab_result = LaboratoryResult(
                document_id=document_id,
                test_type=TestType.SEROLOGY,
                test_name=clean_test_name,
                test_method=test_method,
                result=str(result_value),
                source_page=source_page
            )
            db.add(lab_result)
            count += 1
        
        db.commit()
        logger.info(f"Stored {count} serology test results for document {document_id}")
        return count
        
    except Exception as e:
        logger.error(f"Error extracting serology tests for document {document_id}: {e}", exc_info=True)
        db.rollback()
        return 0


def extract_required_culture_tests(
    document_id: int,
    vectordb: Any,
    llm: Any,
    db: Session,
    role_dict: Dict[str, str],
    instruction_dict: Dict[str, str],
    reminder_dict: Dict[str, str]
) -> int:
    """
    Extract only required culture tests (Blood Culture, Tissue Culture) and store in laboratory_results table.
    
    Returns:
        Number of test results stored
    """
    try:
        # Load required tests config
        config = load_required_tests_config()
        required_tests = config['culture']['required_tests']
        
        # Retrieve relevant chunks for culture tests
        query = "culture test results blood culture tissue culture recovery culture"
        retriever = vectordb.as_retriever(search_type='similarity', search_kwargs={'k': 10})
        retrieved_docs = retriever.invoke(query)
        
        if not retrieved_docs:
            logger.info(f"No relevant chunks found for culture extraction in document {document_id}")
            return 0
        
        # Build donor info context
        donor_info = "\n".join([
            f"Page {doc.metadata.get('page', '?')}: {doc.page_content}"
            for doc in retrieved_docs
        ])
        
        # Get role, instruction, and reminder for culture
        role = role_dict.get('Culture test', '')
        basic_instruction = instruction_dict.get('Culture test', '')
        reminder_instructions = reminder_dict.get('Culture test', '')
        
        # Create focused instruction for required culture tests
        required_tests_list = ", ".join([test['test_name'] for test in required_tests])
        focused_instruction = f"""{basic_instruction}

IMPORTANT: Extract ONLY the following culture tests and their results:
{required_tests_list}

For Blood Culture: Extract result (e.g., "No growth", "Staphylococcus epidermidis"), specimen type, specimen date if available.
For Tissue Culture: Extract tissue location, microorganisms found (if any), or "No growth" if negative.

DO NOT extract culture results for blood, sputum, urine, stool, or bronchial samples - only the required tests above."""
        
        # Call LLM for extraction
        prompt = f"""{role}
Instruction: {focused_instruction}

CRITICAL: Extract information ONLY from the provided donor document.

Relevant donor information:
{donor_info}

{reminder_instructions} DO NOT return any other character or word (like ``` or 'json') but the required result JSON.
AI Response: """
        
        response = call_llm_with_retry(
            llm=llm,
            prompt=prompt,
            max_retries=3,
            base_delay=1.0,
            timeout=60,
            context="culture extraction"
        )
        
        # Parse JSON response
        try:
            result_dict = safe_parse_llm_json(response.content)
        except LLMResponseParseError as e:
            logger.error(f"Failed to parse culture LLM response for document {document_id}: {e}")
            return 0
        
        # Store results in database
        count = 0
        for test_key, test_data in result_dict.items():
            # Handle different response formats
            if isinstance(test_data, list):
                # Format: {"Blood Culture": ["organism1", "organism2"]} or {"Blood Culture": []}
                test_name = test_key
                result = ", ".join(test_data) if test_data else "No growth"
                microorganisms = test_data
            elif isinstance(test_data, dict):
                # Format: {"Blood Culture": {"result": "...", "specimen_type": "...", ...}}
                test_name = test_key
                result = test_data.get('result', '')
                microorganisms = test_data.get('microorganisms', [])
            else:
                # Format: {"Blood Culture": "result string"}
                test_name = test_key
                result = str(test_data)
                microorganisms = []
            
            # Check if this is a required test
            is_required = False
            for required_test in required_tests:
                if (test_name.lower() in [t.lower() for t in [required_test['test_name']] + required_test.get('aliases', [])] or
                    any(alias.lower() in test_name.lower() for alias in required_test.get('aliases', []))):
                    is_required = True
                    # Use canonical test name
                    test_name = required_test['test_name']
                    break
            
            if not is_required:
                continue
            
            # Get source page
            source_page = None
            for doc in retrieved_docs:
                if test_name.lower() in doc.page_content.lower():
                    source_page = doc.metadata.get('page')
                    break
            
            # Determine specimen type for blood cultures
            specimen_type = None
            if "blood" in test_name.lower():
                specimen_type = "Blood"
            elif "tissue" in test_name.lower() or "recovery" in test_name.lower():
                specimen_type = "Tissue"
            
            # Store in database
            lab_result = LaboratoryResult(
                document_id=document_id,
                test_type=TestType.CULTURE,
                test_name=test_name,
                result=result,
                specimen_type=specimen_type,
                source_page=source_page
            )
            
            # For tissue cultures, also store in legacy fields if needed
            if "tissue" in test_name.lower() or "recovery" in test_name.lower():
                if microorganisms:
                    lab_result.microorganism = ", ".join(microorganisms) if isinstance(microorganisms, list) else str(microorganisms)
                    lab_result.tissue_location = test_key  # Original location name
            
            db.add(lab_result)
            count += 1
        
        db.commit()
        logger.info(f"Stored {count} culture test results for document {document_id}")
        return count
        
    except Exception as e:
        logger.error(f"Error extracting culture tests for document {document_id}: {e}", exc_info=True)
        db.rollback()
        return 0

