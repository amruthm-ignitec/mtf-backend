"""
Unified lab test extraction service.
Extracts only required serology and culture tests as specified in acceptance criteria.
"""
import json
import os
import logging
import re
from typing import Dict, Any, Tuple
from sqlalchemy.orm import Session
from app.models.laboratory_result import LaboratoryResult, TestType
from app.services.processing.utils.llm_wrapper import call_llm_with_retry
from app.services.processing.utils.json_parser import safe_parse_llm_json, LLMResponseParseError
from app.services.processing.serology import parse_test_name_and_method

logger = logging.getLogger(__name__)

# Get config directory
_CONFIG_DIR = os.path.join(os.path.dirname(__file__), 'processing', 'config')


def normalize_culture_test_name(test_name: str, culture_dictionary: Dict[str, Any] = None) -> str:
    """Normalize culture test name using dictionary."""
    if not culture_dictionary:
        return test_name
    
    test_names_dict = culture_dictionary.get('test_names', {})
    test_name_lower = test_name.lower().strip()
    
    # Direct match
    if test_name_lower in test_names_dict:
        return test_names_dict[test_name_lower]
    
    # Partial match (check if any key contains the test name or vice versa)
    for key, value in test_names_dict.items():
        if key in test_name_lower or test_name_lower in key:
            return value
    
    return test_name


def normalize_specimen_type(specimen_type: str, culture_dictionary: Dict[str, Any] = None) -> str:
    """Normalize specimen type using dictionary."""
    if not specimen_type or not culture_dictionary:
        return specimen_type
    
    specimen_types_dict = culture_dictionary.get('specimen_types', {})
    specimen_lower = specimen_type.lower().strip()
    
    # Direct match
    if specimen_lower in specimen_types_dict:
        return specimen_types_dict[specimen_lower]
    
    # Partial match
    for key, value in specimen_types_dict.items():
        if key in specimen_lower or specimen_lower in key:
            return value
    
    return specimen_type


def normalize_microorganism(microorganism: str, culture_dictionary: Dict[str, Any] = None) -> str:
    """Normalize microorganism name using dictionary."""
    if not microorganism or not culture_dictionary:
        return microorganism
    
    microorganisms_dict = culture_dictionary.get('microorganisms', {})
    micro_lower = microorganism.lower().strip()
    
    # Direct match
    if micro_lower in microorganisms_dict:
        return microorganisms_dict[micro_lower]
    
    # Partial match (check if any key is contained in the microorganism name)
    for key, value in microorganisms_dict.items():
        if key in micro_lower or micro_lower in key:
            return value
    
    return microorganism


def normalize_culture_result(result: str, culture_dictionary: Dict[str, Any] = None) -> str:
    """Normalize culture result using dictionary."""
    if not result or not culture_dictionary:
        return result
    
    results_dict = culture_dictionary.get('results', {})
    result_lower = result.lower().strip()
    
    # Direct match
    if result_lower in results_dict:
        return results_dict[result_lower]
    
    # Partial match
    for key, value in results_dict.items():
        if key in result_lower or result_lower in key:
            return value
    
    return result


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
        
        # Retrieve relevant chunks using multiple targeted queries
        # This ensures we capture all serology results even if they're formatted differently
        queries = [
            "serology test results SEROLOGY RESULTS infectious disease screening",
            "HIV test results HIV-1 HIV-2 antibody NAT",
            "Hepatitis B HBsAg HBV test results",
            "Hepatitis C HCV antibody NAT test results",
            "Syphilis RPR VDRL TPPA test results",
            "HTLV West Nile Virus WNV test results",
            "blood typing ABO Rh blood group"
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
        
        retrieved_docs = unique_docs[:25]  # Limit to top 25 unique chunks
        
        if not retrieved_docs:
            logger.warning(f"No relevant chunks found for serology extraction in document {document_id}")
            return 0
        
        logger.info(f"Retrieved {len(retrieved_docs)} unique chunks for serology extraction in document {document_id}")
        
        # Build donor info context from retrieved chunks
        donor_info = "\n".join([
            f"Page {doc.metadata.get('page', '?')}: {doc.page_content}"
            for doc in retrieved_docs
        ])
        
        # Get role and reminder for serology
        role = role_dict.get('Serology test', '')
        reminder_instructions = reminder_dict.get('Serology test', '')
        
        # Build detailed test list with aliases for better context
        test_details = []
        for test in required_tests:
            aliases_str = ", ".join(test.get('aliases', [])[:3])  # Show first 3 aliases
            test_details.append(f"- {test['test_name']} (also known as: {aliases_str})")
        
        test_details_str = "\n".join(test_details)
        
        # Create comprehensive focused instruction
        focused_instruction = f"""Extract serology test results for donor eligibility assessment.

REQUIRED TESTS TO EXTRACT:
{test_details_str}

EXTRACTION GUIDELINES:

1. TEST NAME EXTRACTION:
   - Extract test names EXACTLY as they appear in the document
   - Include abbreviations, manufacturer names, and method designations (e.g., "HIV-1/HIV-2 Plus O", "HBsAg (Alinity)", "CMV IgG (EIA)")
   - Match test names to the required tests above, even if they use different aliases

2. RESULT EXTRACTION:
   - Extract results EXACTLY as they appear, including:
     * Standard results: Positive, Negative, Non-Reactive, Reactive, Equivocal, Indeterminate, Borderline
     * Blood type results: O Positive, A Negative, B Positive, AB Negative, etc.
     * Status indicators: Complete, Cancelled, Pending, Not Tested
     * Any quantitative values if present (e.g., titers, ratios, S/CO values)

3. MULTIPLE OCCURRENCES:
   - If a test appears multiple times with different results, include ALL instances
   - Use the format: "{{"Test Name 1": "Result 1", "Test Name 2": "Result 2"}}"
   - If the same test appears multiple times, number them (e.g., "HIV-1/HIV-2", "HIV-1/HIV-2 (2)")

4. TEST MATCHING:
   - Match tests to required tests even if names vary slightly
   - For example: "HBsAg" should be matched to "Hepatitis B Surface Antigen"
   - "RPR" or "VDRL" should be matched to "Syphilis"
   - "anti-HCV" should be matched to "Hepatitis C Antibody"

5. DO NOT EXTRACT:
   - Tests not in the REQUIRED TESTS list above
   - If a test name appears but no result is visible or unclear, do NOT include it

IMPORTANT: Extract ALL occurrences of required tests found in the document. Be thorough and check all pages."""
        
        # Call LLM for extraction
        prompt = f"""{role}
Instruction: {focused_instruction}

CRITICAL: Extract information ONLY from the provided donor document. Do not use information from other donors, documents, or your training data.

Relevant donor information:
{donor_info}

OUTPUT FORMAT:
Return a JSON object with test names as keys and results as values:
{{
  "HIV-1/HIV-2 Plus O": "Non-Reactive",
  "Hepatitis B Surface Antigen (HBsAg)": "Negative",
  "Hepatitis C Antibody (anti-HCV)": "Non-Reactive",
  "Syphilis (RPR)": "Non-Reactive",
  "HTLV I/II": "Non-Reactive",
  "West Nile Virus": "Not Detected"
}}

If a test appears multiple times:
{{
  "HIV-1/HIV-2 Plus O": "Non-Reactive",
  "HIV-1/HIV-2 Plus O (2)": "Non-Reactive"
}}

IMPORTANT:
- Extract test names EXACTLY as they appear in the document
- Extract results EXACTLY as they appear (do not normalize or change them)
- Include ALL occurrences of required tests
- If a test is not found, do NOT include it in the output

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
                logger.debug(f"Skipping test {test_name} with empty result")
                continue
            
            # Remove numbering from test name for matching (e.g., "HIV-1/HIV-2 (2)" -> "HIV-1/HIV-2")
            original_test_name = test_name
            test_name_for_matching = test_name
            if " (" in test_name_for_matching and test_name_for_matching.endswith(")"):
                # Remove trailing "(2)", "(3)", etc.
                test_name_for_matching = test_name_for_matching.rsplit(" (", 1)[0]
            
            # Parse test name and method
            clean_test_name, test_method = parse_test_name_and_method(test_name_for_matching)
            
            # Check if this test is in our required list (by matching against aliases)
            is_required = False
            canonical_test_name = None
            for required_test in required_tests:
                # Check against cleaned test name
                test_variants = [required_test['test_name']] + required_test.get('aliases', [])
                if (clean_test_name.lower() in [t.lower() for t in test_variants] or
                    any(alias.lower() in test_name_for_matching.lower() for alias in test_variants) or
                    any(alias.lower() in clean_test_name.lower() for alias in test_variants)):
                    is_required = True
                    # Use the canonical test name
                    canonical_test_name = required_test['test_name']
                    break
            
            if not is_required:
                # Try fuzzy matching - check if any part of the test name matches
                for required_test in required_tests:
                    test_variants = [required_test['test_name']] + required_test.get('aliases', [])
                    # Check if any key term from required test appears in the extracted test name
                    for variant in test_variants:
                        # Extract key terms (e.g., "HIV", "Hepatitis B", "HBsAg")
                        key_terms = variant.lower().split()
                        # Remove common words
                        key_terms = [t for t in key_terms if t not in ['test', 'antibody', 'antigen', 'surface', 'core', 'virus']]
                        # Check if any key term appears in the test name
                        if any(term in test_name_for_matching.lower() or term in clean_test_name.lower() for term in key_terms if len(term) > 3):
                            is_required = True
                            canonical_test_name = required_test['test_name']
                            logger.info(f"Fuzzy matched '{original_test_name}' to required test '{canonical_test_name}'")
                            break
                    if is_required:
                        break
            
            if not is_required:
                logger.debug(f"Skipping non-required test: {original_test_name} (cleaned: {clean_test_name})")
                continue
            
            # Use canonical name if available
            if canonical_test_name:
                clean_test_name = canonical_test_name
            
            # Get source page from citations if available
            source_page = None
            search_terms = [test_name_for_matching.lower(), clean_test_name.lower(), str(result_value).lower()]
            for doc in retrieved_docs:
                doc_content_lower = doc.page_content.lower()
                if any(term in doc_content_lower for term in search_terms if term):
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
            logger.debug(f"Stored serology test: {clean_test_name} = {result_value} (from: {original_test_name})")
        
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


def extract_all_lab_tests(
    document_id: int,
    vectordb: Any,
    llm: Any,
    db: Session,
    role_dict: Dict[str, str],
    instruction_dict: Dict[str, str],
    reminder_dict: Dict[str, str],
    serology_dictionary: Dict[str, Any],
    culture_dictionary: Dict[str, Any] = None
) -> Tuple[int, int]:
    """
    Extract both required serology and culture tests in a single LLM call.
    This reduces LLM calls from 2 to 1 for lab test extraction.
    
    Returns:
        Tuple of (serology_count, culture_count) - number of test results stored for each type
    """
    try:
        # Load required tests config
        config = load_required_tests_config()
        required_serology_tests = config['serology']['required_tests']
        required_culture_tests = config['culture']['required_tests']
        
        # Ensure culture_dictionary is initialized
        if culture_dictionary is None:
            culture_dictionary = {}
        
        # Build comprehensive semantic search queries for both test types
        queries = [
            # Serology queries
            "serology test results SEROLOGY RESULTS infectious disease screening",
            "HIV test results HIV-1 HIV-2 antibody NAT",
            "Hepatitis B HBsAg HBV test results",
            "Hepatitis C HCV antibody NAT test results",
            "Syphilis RPR VDRL TPPA test results",
            "HTLV West Nile Virus WNV test results",
            "blood typing ABO Rh blood group",
            # Culture queries
            "blood culture results positive negative no growth",
            "culture results CULTURE RESULTS final result",
            "tissue culture recovery culture pre-processing post-processing",
            "staphylococcus coagulase gram positive cocci microorganisms"
        ]
        
        # Retrieve relevant chunks using multiple targeted queries
        all_retrieved_docs = []
        retriever = vectordb.as_retriever(search_type='similarity', search_kwargs={'k': 15})
        
        for query in queries:
            retrieved_docs = retriever.invoke(query)
            all_retrieved_docs.extend(retrieved_docs)
        
        # Deduplicate by page and content
        seen = set()
        unique_docs = []
        for doc in all_retrieved_docs:
            doc_key = (doc.metadata.get('page'), doc.page_content[:100])
            if doc_key not in seen:
                seen.add(doc_key)
                unique_docs.append(doc)
        
        retrieved_docs = unique_docs[:30]  # Limit to top 30 unique chunks
        
        if not retrieved_docs:
            logger.warning(f"No relevant chunks found for lab test extraction in document {document_id}")
            return 0, 0
        
        logger.info(f"Retrieved {len(retrieved_docs)} unique chunks for combined lab test extraction in document {document_id}")
        
        # Build donor info context
        donor_info = "\n".join([
            f"Page {doc.metadata.get('page', '?')}: {doc.page_content}"
            for doc in retrieved_docs
        ])
        
        # Build detailed serology test list with aliases
        serology_test_details = []
        for test in required_serology_tests:
            aliases_str = ", ".join(test.get('aliases', [])[:3])
            serology_test_details.append(f"- {test['test_name']} (also known as: {aliases_str})")
        serology_test_details_str = "\n".join(serology_test_details)
        
        # Build culture test list
        culture_test_names = [test['test_name'] for test in required_culture_tests]
        culture_test_details_str = ", ".join(culture_test_names)
        
        # Get combined role (use serology role as base, add culture expertise)
        serology_role = role_dict.get('Serology test', '')
        culture_role = role_dict.get('Culture test', '')
        combined_role = f"""You are an expert medical data extractor specializing in laboratory reports for donor eligibility assessment. You have expertise in both serological infectious disease screening and microbiological culture interpretation. {serology_role} {culture_role}"""
        
        # Create comprehensive focused instruction
        focused_instruction = f"""Extract serology and culture test results for donor eligibility assessment.

REQUIRED SEROLOGY TESTS TO EXTRACT (ONLY these):
{serology_test_details_str}

REQUIRED CULTURE TESTS TO EXTRACT (ONLY these):
{culture_test_details_str}

EXTRACTION GUIDELINES:

1. SEROLOGY TEST EXTRACTION:
   - Extract test names EXACTLY as they appear in the document
   - Include abbreviations, manufacturer names, and method designations (e.g., "HIV-1/HIV-2 Plus O", "HBsAg (Alinity)")
   - Match test names to the required tests above, even if they use different aliases
   - Extract results EXACTLY as they appear: Positive, Negative, Non-Reactive, Reactive, Equivocal, Indeterminate, Borderline
   - Include ALL occurrences of required tests, even if they appear multiple times
   - If a test appears multiple times, number them (e.g., "HIV-1/HIV-2", "HIV-1/HIV-2 (2)")
   - If a test name appears but no result is visible or unclear, do NOT include it

2. CULTURE TEST EXTRACTION:
   - BLOOD CULTURE (REQUIRED): Extract ALL Blood Culture results from the document
     * Extract result: "No growth", "No Growth", "Positive", or specific microorganisms found
     * Extract specimen type: "Blood"
     * Extract specimen date if available
     * Extract accession number if available
     * Include ALL Blood Culture results, even if there are multiple entries
   - TISSUE CULTURE (REQUIRED): Extract Recovery Culture, Pre-Processing Culture, Post-Processing Culture, Processing Filter Culture results
     * Extract the FULL, EXACT name of each sub-tissue as it appears (e.g., 'Left Femur Recovery Culture')
     * For each sub-tissue, extract ALL microorganisms found, including genus/species names
     * If no microorganisms are found or result is "No Growth", indicate "No growth"

3. DO NOT EXTRACT:
   - Tests not in the REQUIRED TESTS lists above
   - Urine culture, Sputum culture, Stool culture, Bronchial culture results
   - If a test name appears but no result is visible, do NOT include it

IMPORTANT: Extract ALL occurrences of required tests found in the document. Be thorough and check all pages."""
        
        # Get reminder instructions
        serology_reminder = reminder_dict.get('Serology test', '')
        culture_reminder = reminder_dict.get('Culture test', '')
        combined_reminder = f"{serology_reminder}\n\n{culture_reminder}"
        
        # Call LLM for extraction
        prompt = f"""{combined_role}
Instruction: {focused_instruction}

CRITICAL ANTI-HALLUCINATION RULES:
1. Extract information ONLY from the provided donor document text below
2. DO NOT infer, assume, or guess test results based on document type or your training data
3. DO NOT add test results that are not explicitly present in the document
4. If a required test is NOT mentioned in the document, DO NOT include it in the output
5. If you see test names but NO results, DO NOT include those tests
6. If the document only contains partial information (e.g., only a date or header), return empty arrays
7. DO NOT use "normal" or "expected" values - only extract what is actually written in the document

Relevant donor information:
{donor_info}

OUTPUT FORMAT:
Return a JSON object with the following structure:

If tests are found in the document:
{{
  "serology_tests": {{
    "HIV-1/HIV-2 Plus O": "Non-Reactive",
    "Hepatitis B Surface Antigen (HBsAg)": "Negative"
  }},
  "culture_tests": {{
    "Blood Culture": {{
      "result": "No Growth",
      "specimen_type": "Blood",
      "specimen_date": "05/09/2025"
    }}
  }}
}}

If NO tests are found in the document, return:
{{
  "serology_tests": {{}},
  "culture_tests": {{}}
}}

IMPORTANT:
- Extract test names EXACTLY as they appear in the document
- Extract results EXACTLY as they appear (do not normalize or change them)
- If a test is NOT found in the document, DO NOT include it - return empty object {{}}
- For serology: extract ONLY when BOTH test name AND result are explicitly visible together in the document
- For culture: extract ONLY when test name AND result are explicitly visible together in the document
- DO NOT infer results from document type, headers, or context
- DO NOT add default or "normal" values
- If the document text is too short or unclear, return empty objects

{combined_reminder} DO NOT return any other character or word (like ``` or 'json') but the required result JSON.
AI Response: """
        
        response = call_llm_with_retry(
            llm=llm,
            prompt=prompt,
            max_retries=3,
            base_delay=1.0,
            timeout=90,  # Slightly longer timeout for combined extraction
            context="combined lab test extraction"
        )
        
        # Parse JSON response
        try:
            result_dict = safe_parse_llm_json(response.content)
        except LLMResponseParseError as e:
            logger.error(f"Failed to parse combined lab test LLM response for document {document_id}: {e}")
            return 0, 0
        
        # Validate extracted results against source document to prevent hallucination
        # Build a searchable text from all retrieved chunks for validation
        source_text_lower = " ".join([doc.page_content.lower() for doc in retrieved_docs])
        
        # Check if source text is too short - if so, reject all extractions to prevent hallucination
        if len(source_text_lower.strip()) < 50:
            logger.warning(
                f"Source document text is too short ({len(source_text_lower)} chars) for document {document_id}. "
                f"Rejecting all extractions to prevent hallucination. Text: {source_text_lower[:100]}"
            )
            return 0, 0
        
        # Process serology tests
        serology_count = 0
        serology_tests = result_dict.get('serology_tests', {})
        if isinstance(serology_tests, dict):
            for test_name, result_value in serology_tests.items():
                if not result_value:
                    logger.debug(f"Skipping serology test {test_name} with empty result")
                    continue
                
                # Remove numbering from test name for matching
                original_test_name = test_name
                test_name_for_matching = test_name
                if " (" in test_name_for_matching and test_name_for_matching.endswith(")"):
                    test_name_for_matching = test_name_for_matching.rsplit(" (", 1)[0]
                
                # Parse test name and method
                clean_test_name, test_method = parse_test_name_and_method(test_name_for_matching)
                
                # VALIDATION: Check if test name or result actually appears in source document
                # This prevents hallucination when LLM infers results not in the document
                test_name_found = False
                result_found = False
                
                # Check for test name variants in source
                for required_test in required_serology_tests:
                    test_variants = [required_test['test_name']] + required_test.get('aliases', [])
                    for variant in test_variants:
                        if variant.lower() in source_text_lower or any(part in source_text_lower for part in variant.lower().split() if len(part) > 3):
                            test_name_found = True
                            break
                    if test_name_found:
                        break
                
                # Also check the extracted test name itself
                if not test_name_found:
                    test_name_parts = [part for part in test_name_for_matching.lower().split() if len(part) > 3]
                    if any(part in source_text_lower for part in test_name_parts):
                        test_name_found = True
                
                # Check if result value appears in source (allowing for case variations)
                result_lower = str(result_value).lower()
                result_variants = [
                    result_lower,
                    result_lower.replace("-", " "),
                    result_lower.replace(" ", ""),
                ]
                result_found = any(variant in source_text_lower for variant in result_variants if variant)
                
                # If neither test name nor result found in source, skip to prevent hallucination
                if not test_name_found and not result_found:
                    logger.warning(
                        f"Rejecting serology test '{original_test_name}' = '{result_value}' for document {document_id}: "
                        f"Neither test name nor result found in source document. This may be hallucination."
                    )
                    continue
                
                # Check if this test is in our required list
                is_required = False
                canonical_test_name = None
                for required_test in required_serology_tests:
                    test_variants = [required_test['test_name']] + required_test.get('aliases', [])
                    if (clean_test_name.lower() in [t.lower() for t in test_variants] or
                        any(alias.lower() in test_name_for_matching.lower() for alias in test_variants) or
                        any(alias.lower() in clean_test_name.lower() for alias in test_variants)):
                        is_required = True
                        canonical_test_name = required_test['test_name']
                        break
                
                if not is_required:
                    # Try fuzzy matching
                    for required_test in required_serology_tests:
                        test_variants = [required_test['test_name']] + required_test.get('aliases', [])
                        for variant in test_variants:
                            key_terms = variant.lower().split()
                            key_terms = [t for t in key_terms if t not in ['test', 'antibody', 'antigen', 'surface', 'core', 'virus']]
                            if any(term in test_name_for_matching.lower() or term in clean_test_name.lower() for term in key_terms if len(term) > 3):
                                is_required = True
                                canonical_test_name = required_test['test_name']
                                logger.info(f"Fuzzy matched '{original_test_name}' to required test '{canonical_test_name}'")
                                break
                        if is_required:
                            break
                
                if not is_required:
                    logger.debug(f"Skipping non-required serology test: {original_test_name}")
                    continue
                
                # Use canonical name if available
                if canonical_test_name:
                    clean_test_name = canonical_test_name
                
                # Get source page - try to find the page where this test result appears
                source_page = None
                search_terms = [test_name_for_matching.lower(), clean_test_name.lower(), str(result_value).lower()]
                for doc in retrieved_docs:
                    doc_content_lower = doc.page_content.lower()
                    if any(term in doc_content_lower for term in search_terms if term):
                        # Try to get page from metadata
                        page = doc.metadata.get('page') if hasattr(doc, 'metadata') and doc.metadata else None
                        if page is not None:
                            source_page = int(page) if isinstance(page, (int, str)) and str(page).isdigit() else None
                        if source_page:
                            break
                
                # If still no page found, try to get from first matching doc
                if not source_page and retrieved_docs:
                    for doc in retrieved_docs:
                        if hasattr(doc, 'metadata') and doc.metadata:
                            page = doc.metadata.get('page')
                            if page is not None:
                                try:
                                    source_page = int(page) if isinstance(page, (int, str)) and str(page).isdigit() else None
                                    if source_page:
                                        break
                                except (ValueError, TypeError):
                                    pass
                
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
                serology_count += 1
                logger.debug(f"Stored serology test: {clean_test_name} = {result_value} (from: {original_test_name})")
        
        # Process culture tests
        culture_count = 0
        culture_tests = result_dict.get('culture_tests', {})
        if isinstance(culture_tests, dict):
            for test_key, test_data in culture_tests.items():
                # Initialize variables
                test_name = test_key
                result = ""
                microorganisms = []
                specimen_type = None
                specimen_date = None
                accession_number = None
                base_test_name = test_key
                
                # Handle different response formats
                if isinstance(test_data, list):
                    # Format: {"Left Femur Recovery Culture": ["organism1", "organism2"]} or []
                    result = ", ".join(test_data) if test_data else "No growth"
                    microorganisms = test_data
                elif isinstance(test_data, dict):
                    # Format: {"Blood Culture": {"result": "...", "specimen_type": "...", ...}}
                    # Normalize test name using culture dictionary
                    base_test_name = normalize_culture_test_name(test_key, culture_dictionary)
                    if not base_test_name or base_test_name == test_key:
                        # Fallback to original logic if dictionary didn't match
                        if "blood culture" in test_key.lower():
                            base_test_name = "Blood Culture"
                        elif "urine culture" in test_key.lower() or "urine cx" in test_key.lower() or "u/c" in test_key.lower():
                            base_test_name = "Urine Culture"
                        elif "sputum culture" in test_key.lower() or "sputum cx" in test_key.lower() or "s/c" in test_key.lower():
                            base_test_name = "Sputum Culture"
                        elif "tissue" in test_key.lower() or "recovery" in test_key.lower():
                            base_test_name = test_key
                        else:
                            base_test_name = test_key
                    
                    result = test_data.get('result', '')
                    if not result:
                        final_details = test_data.get('final_result_details', '')
                        if final_details:
                            result = final_details
                        else:
                            result = "No result specified"
                    
                    microorganisms = test_data.get('microorganisms', [])
                    # Normalize microorganism names using dictionary
                    if microorganisms and isinstance(microorganisms, list):
                        microorganisms = [normalize_microorganism(org, culture_dictionary) for org in microorganisms]
                    elif not microorganisms and result and result.lower() not in ['no growth', 'negative', 'positive', 'no growth after 18 hours']:
                        result_lower = result.lower()
                        if any(org in result_lower for org in ['staphylococcus', 'candida', 'gram positive', 'gram negative']):
                            microorganisms.append(normalize_microorganism(result, culture_dictionary))
                    
                    specimen_type = test_data.get('specimen_type', None)
                    # Normalize specimen type using dictionary
                    if specimen_type:
                        specimen_type = normalize_specimen_type(specimen_type, culture_dictionary)
                    specimen_date = test_data.get('specimen_date', None)
                    accession_number = test_data.get('accession_number', None)
                    
                    # Normalize result using dictionary
                    if result:
                        result = normalize_culture_result(result, culture_dictionary)
                else:
                    # Format: {"Blood Culture": "result string"}
                    result = str(test_data)
                
                # VALIDATION: Check if test name or result actually appears in source document
                # This prevents hallucination when LLM infers results not in the document
                test_name_found = False
                result_found = False
                
                # Check for culture test name variants in source
                for required_test in required_culture_tests:
                    test_variants = [required_test['test_name']] + required_test.get('aliases', [])
                    for variant in test_variants:
                        if variant.lower() in source_text_lower or any(part in source_text_lower for part in variant.lower().split() if len(part) > 3):
                            test_name_found = True
                            break
                    if test_name_found:
                        break
                
                # Also check the extracted test name itself
                if not test_name_found:
                    test_name_parts = [part for part in base_test_name.lower().split() if len(part) > 3]
                    if any(part in source_text_lower for part in test_name_parts):
                        test_name_found = True
                
                # Check if result value appears in source (allowing for case variations)
                if result:
                    result_lower = str(result).lower()
                    result_variants = [
                        result_lower,
                        result_lower.replace("-", " "),
                        result_lower.replace(" ", ""),
                        "no growth" if "no growth" in result_lower else None,
                        "positive" if "positive" in result_lower else None,
                    ]
                    result_variants = [v for v in result_variants if v]
                    result_found = any(variant in source_text_lower for variant in result_variants)
                
                # If neither test name nor result found in source, skip to prevent hallucination
                if not test_name_found and not result_found:
                    logger.warning(
                        f"Rejecting culture test '{test_key}' = '{result}' for document {document_id}: "
                        f"Neither test name nor result found in source document. This may be hallucination."
                    )
                    continue
                
                # Check if this is a required test
                is_required = False
                canonical_test_name = None
                for required_test in required_culture_tests:
                    if (base_test_name.lower() in [t.lower() for t in [required_test['test_name']] + required_test.get('aliases', [])] or
                        any(alias.lower() in base_test_name.lower() for alias in required_test.get('aliases', []))):
                        is_required = True
                        canonical_test_name = required_test['test_name']
                        break
                
                if not is_required:
                    logger.debug(f"Skipping non-required culture test: {test_key} (base: {base_test_name})")
                    continue
                
                # Use canonical name if available, otherwise keep original
                if canonical_test_name:
                    test_name = canonical_test_name
                
                # Get source page - try to find the page where this culture test appears
                source_page = None
                for doc in retrieved_docs:
                    if test_name.lower() in doc.page_content.lower() or test_key.lower() in doc.page_content.lower():
                        # Try to get page from metadata
                        if hasattr(doc, 'metadata') and doc.metadata:
                            page = doc.metadata.get('page')
                            if page is not None:
                                try:
                                    source_page = int(page) if isinstance(page, (int, str)) and str(page).isdigit() else None
                                    if source_page:
                                        break
                                except (ValueError, TypeError):
                                    pass
                
                # If still no page found, try to get from first matching doc
                if not source_page and retrieved_docs:
                    for doc in retrieved_docs:
                        if hasattr(doc, 'metadata') and doc.metadata:
                            page = doc.metadata.get('page')
                            if page is not None:
                                try:
                                    source_page = int(page) if isinstance(page, (int, str)) and str(page).isdigit() else None
                                    if source_page:
                                        break
                                except (ValueError, TypeError):
                                    pass
                
                # Determine specimen type if not already set
                if not specimen_type:
                    if "blood" in test_name.lower() or "blood" in base_test_name.lower():
                        specimen_type = normalize_specimen_type("Blood", culture_dictionary)
                    elif "urine" in test_name.lower() or "urine" in base_test_name.lower():
                        specimen_type = normalize_specimen_type("Urine", culture_dictionary)
                    elif "sputum" in test_name.lower() or "sputum" in base_test_name.lower():
                        specimen_type = normalize_specimen_type("Sputum", culture_dictionary)
                    elif "tissue" in test_name.lower() or "recovery" in test_name.lower() or "tissue" in base_test_name.lower():
                        specimen_type = normalize_specimen_type("Tissue", culture_dictionary)
                
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
                        # Normalize microorganisms before storing
                        normalized_micros = [normalize_microorganism(org, culture_dictionary) if isinstance(org, str) else str(org) for org in microorganisms]
                        lab_result.microorganism = ", ".join(normalized_micros) if isinstance(normalized_micros, list) else str(normalized_micros)
                        lab_result.tissue_location = test_key
                elif ("blood" in test_name.lower() or "urine" in test_name.lower() or "sputum" in test_name.lower()) and microorganisms:
                    if not lab_result.comments:
                        # Normalize microorganisms before storing
                        normalized_micros = [normalize_microorganism(org, culture_dictionary) if isinstance(org, str) else str(org) for org in microorganisms]
                        lab_result.comments = f"Microorganisms: {', '.join(normalized_micros) if isinstance(normalized_micros, list) else str(normalized_micros)}"
                
                db.add(lab_result)
                culture_count += 1
        
        db.commit()
        logger.info(f"Stored {serology_count} serology and {culture_count} culture test results for document {document_id}")
        return serology_count, culture_count
        
    except Exception as e:
        logger.error(f"Error extracting combined lab tests for document {document_id}: {e}", exc_info=True)
        db.rollback()
        return 0, 0

