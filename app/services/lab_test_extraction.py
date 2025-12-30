"""
Unified lab test extraction service.
Extracts only required serology and culture tests as specified in acceptance criteria.
"""
import json
import os
import logging
from typing import Dict, Any
from sqlalchemy.orm import Session
from app.models.laboratory_result import LaboratoryResult, TestType
from app.services.processing.utils.llm_wrapper import call_llm_with_retry
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
        # Use multiple queries to ensure we capture all culture results
        queries = [
            "blood culture results positive negative no growth",
            "culture results CULTURE RESULTS final result",
            "tissue culture recovery culture pre-processing post-processing",
            "staphylococcus coagulase gram positive cocci microorganisms"
        ]
        
        all_retrieved_docs = []
        retriever = vectordb.as_retriever(search_type='similarity', search_kwargs={'k': 15})
        
        for query in queries:
            retrieved_docs = retriever.invoke(query)
            all_retrieved_docs.extend(retrieved_docs)
        
        # Deduplicate by page and content
        seen = set()
        unique_docs = []
        for doc in all_retrieved_docs:
            doc_key = (doc.metadata.get('page'), doc.page_content[:100])  # Use first 100 chars as key
            if doc_key not in seen:
                seen.add(doc_key)
                unique_docs.append(doc)
        
        retrieved_docs = unique_docs[:20]  # Limit to top 20 unique chunks
        
        if not retrieved_docs:
            logger.warning(f"No relevant chunks found for culture extraction in document {document_id}")
            return 0
        
        logger.info(f"Retrieved {len(retrieved_docs)} unique chunks for culture extraction in document {document_id}")
        
        # Build donor info context
        donor_info = "\n".join([
            f"Page {doc.metadata.get('page', '?')}: {doc.page_content}"
            for doc in retrieved_docs
        ])
        
        # Get role and reminder for culture
        role = role_dict.get('Culture test', '')
        reminder_instructions = reminder_dict.get('Culture test', '')
        
        # Create focused instruction for required culture tests
        required_tests_list = ", ".join([test['test_name'] for test in required_tests])
        focused_instruction = f"""Extract culture test results for donor eligibility assessment.

REQUIRED TESTS TO EXTRACT:
{required_tests_list}

EXTRACTION GUIDELINES:

1. BLOOD CULTURE (REQUIRED):
   - Extract ALL Blood Culture results from the document
   - Extract the result: "No growth", "No Growth", "Positive", or specific microorganisms found (e.g., "Staphylococcus coagulase negative", "Gram positive cocci")
   - Extract specimen type: "Blood"
   - Extract specimen date if available
   - Extract accession number if available
   - Include ALL Blood Culture results, even if there are multiple entries

2. TISSUE CULTURE (REQUIRED):
   - Extract Recovery Culture, Pre-Processing Culture, Post-Processing Culture, Processing Filter Culture results
   - Extract the FULL, EXACT name of each sub-tissue as it appears (e.g., 'Left Femur Recovery Culture', 'Right Semitendinosus Pre-Processing Culture')
   - For each sub-tissue, extract ALL microorganisms found, including genus/species names, generic descriptions, and qualifiers
   - If no microorganisms are found or result is "No Growth", indicate "No growth"

3. DO NOT EXTRACT:
   - Urine culture results
   - Sputum culture results
   - Stool culture results
   - Bronchial culture results
   - Any other culture types not listed in REQUIRED TESTS above

IMPORTANT: Blood Culture IS a required test and MUST be extracted. The instruction to "not extract blood cultures" in the base instruction does NOT apply here - Blood Culture is explicitly required for donor eligibility assessment."""
        
        # Call LLM for extraction
        prompt = f"""{role}
Instruction: {focused_instruction}

CRITICAL: Extract information ONLY from the provided donor document.

Relevant donor information:
{donor_info}

OUTPUT FORMAT:
Return a JSON object with the following structure:

For Blood Culture:
{{
  "Blood Culture": {{
    "result": "Positive Blood Culture" or "No Growth" or "No Growth after 18 hours" or specific organism,
    "specimen_type": "Blood",
    "specimen_date": "05/09/2025" (if available),
    "accession_number": "MCLAR" (if available),
    "final_result_details": "Gram positive Cocci in clusters, Staphylococcus coagulase negative" (if available)
  }}
}}

OR if multiple Blood Culture results exist:
{{
  "Blood Culture 1": {{
    "result": "...",
    "specimen_type": "Blood",
    ...
  }},
  "Blood Culture 2": {{
    "result": "...",
    "specimen_type": "Blood",
    ...
  }}
}}

For Tissue Culture:
{{
  "Left Femur Recovery Culture": ["organism1", "organism2"] or [],
  "Right Semitendinosus Recovery Culture": []
}}

IMPORTANT: 
- Extract ALL Blood Culture results found in the document, even if there are multiple entries
- Include the exact result text as it appears (e.g., "Positive Blood Culture", "No Growth after 18 hours", "Staphylococcus coagulase negative")
- If a Blood Culture shows "Positive" or "Positive Blood Culture", include the full details from "Final Result" field

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
            # Initialize variables
            test_name = test_key
            result = ""
            microorganisms = []
            specimen_type = None
            specimen_date = None
            accession_number = None
            base_test_name = test_key  # For matching against required tests
            
            # Handle different response formats
            if isinstance(test_data, list):
                # Format: {"Blood Culture": ["organism1", "organism2"]} or {"Blood Culture": []}
                # This is typically for tissue cultures
                result = ", ".join(test_data) if test_data else "No growth"
                microorganisms = test_data
            elif isinstance(test_data, dict):
                # Format: {"Blood Culture": {"result": "...", "specimen_type": "...", ...}}
                # Or: {"Blood Culture 1": {...}, "Blood Culture 2": {...}}
                # Normalize test name - remove numbers for matching
                if "blood culture" in test_key.lower():
                    base_test_name = "Blood Culture"
                elif "tissue" in test_key.lower() or "recovery" in test_key.lower():
                    base_test_name = test_key  # Keep full name for tissue cultures
                
                result = test_data.get('result', '')
                if not result:
                    # Fallback: try to construct from other fields
                    final_details = test_data.get('final_result_details', '')
                    if final_details:
                        result = final_details
                    else:
                        result = "No result specified"
                
                microorganisms = test_data.get('microorganisms', [])
                # If result contains organism names, extract them
                if not microorganisms and result and result.lower() not in ['no growth', 'negative', 'positive', 'no growth after 18 hours']:
                    # Try to extract organism names from result text
                    result_lower = result.lower()
                    if any(org in result_lower for org in ['staphylococcus', 'candida', 'gram positive', 'gram negative']):
                        microorganisms.append(result)
                
                specimen_type = test_data.get('specimen_type', None)
                specimen_date = test_data.get('specimen_date', None)
                accession_number = test_data.get('accession_number', None)
            else:
                # Format: {"Blood Culture": "result string"}
                result = str(test_data)
            
            # Check if this is a required test
            is_required = False
            canonical_test_name = None
            for required_test in required_tests:
                # Check against base_test_name for matching
                if (base_test_name.lower() in [t.lower() for t in [required_test['test_name']] + required_test.get('aliases', [])] or
                    any(alias.lower() in base_test_name.lower() for alias in required_test.get('aliases', []))):
                    is_required = True
                    # Use canonical test name
                    canonical_test_name = required_test['test_name']
                    break
            
            if not is_required:
                logger.debug(f"Skipping non-required test: {test_key} (base: {base_test_name})")
                continue
            
            # Use canonical name if available, otherwise keep original
            if canonical_test_name:
                test_name = canonical_test_name
            
            # Get source page
            source_page = None
            for doc in retrieved_docs:
                if test_name.lower() in doc.page_content.lower() or test_key.lower() in doc.page_content.lower():
                    source_page = doc.metadata.get('page')
                    break
            
            # Determine specimen type if not already set
            if not specimen_type:
                if "blood" in test_name.lower() or "blood" in base_test_name.lower():
                    specimen_type = "Blood"
                elif "tissue" in test_name.lower() or "recovery" in test_name.lower() or "tissue" in base_test_name.lower():
                    specimen_type = "Tissue"
            
            # Build comments field with additional info
            comments_parts = []
            if accession_number:
                comments_parts.append(f"Accession: {accession_number}")
            if microorganisms and isinstance(microorganisms, list) and len(microorganisms) > 0:
                if "blood" in test_name.lower():
                    comments_parts.append(f"Microorganisms: {', '.join(microorganisms)}")
            
            # Store in database
            lab_result = LaboratoryResult(
                document_id=document_id,
                test_type=TestType.CULTURE,
                test_name=test_name,
                result=result,
                specimen_type=specimen_type,
                specimen_date=specimen_date,
                source_page=source_page,
                comments="; ".join(comments_parts) if comments_parts else None
            )
            
            # For tissue cultures, also store in legacy fields if needed
            if "tissue" in test_name.lower() or "recovery" in test_name.lower():
                if microorganisms:
                    lab_result.microorganism = ", ".join(microorganisms) if isinstance(microorganisms, list) else str(microorganisms)
                    lab_result.tissue_location = test_key  # Original location name
            elif "blood" in test_name.lower() and microorganisms:
                # Store microorganisms in comments for blood cultures
                if not lab_result.comments:
                    lab_result.comments = f"Microorganisms: {', '.join(microorganisms) if isinstance(microorganisms, list) else str(microorganisms)}"
            
            db.add(lab_result)
            count += 1
        
        db.commit()
        logger.info(f"Stored {count} culture test results for document {document_id}")
        return count
        
    except Exception as e:
        logger.error(f"Error extracting culture tests for document {document_id}: {e}", exc_info=True)
        db.rollback()
        return 0

