"""
Comprehensive DRAI (Donor Risk Assessment Interview) extraction service.
Processes ALL pages and chunks to ensure complete extraction of all questions and answers.
"""
import logging
import re
from typing import Dict, Any, List, Optional, Tuple
from sqlalchemy.orm import Session
from collections import defaultdict
from app.models.document_chunk import DocumentChunk
from app.services.processing.utils.llm_wrapper import call_llm_with_retry
from app.services.processing.utils.json_parser import safe_parse_llm_json, LLMResponseParseError

logger = logging.getLogger(__name__)


def identify_drai_pages(chunks_by_page: Dict[int, List[DocumentChunk]]) -> List[int]:
    """
    Identify which pages contain DRAI content.
    
    Detection criteria:
    - Contains keywords: "DRAI", "donor risk assessment", "UDRAI"
    - Contains numbered questions (1., 2., 3., etc.)
    - Contains Yes/No answer patterns
    - Contains question-answer pairs
    
    Args:
        chunks_by_page: Dictionary mapping page numbers to lists of DocumentChunk objects
        
    Returns:
        List of page numbers that contain DRAI content
    """
    drai_pages = []
    drai_keywords = [
        'drai', 'donor risk assessment', 'udrai', 'donor risk interview',
        'risk assessment interview', 'donor interview', 'donor questionnaire'
    ]
    
    question_patterns = [
        r'^\d+\.',  # Numbered questions like "1.", "2."
        r'^\d+[a-z]\.',  # Sub-questions like "3a.", "4b."
        r'^\d+[a-z]\([i-v]+\)',  # Follow-up questions like "4a(i)", "4a(ii)"
    ]
    
    for page_num, chunks in chunks_by_page.items():
        # Combine all chunks on this page
        page_text = " ".join([chunk.chunk_text for chunk in chunks if chunk.chunk_text])
        page_text_lower = page_text.lower()
        
        # Check for DRAI keywords
        has_drai_keyword = any(keyword in page_text_lower for keyword in drai_keywords)
        
        # Check for numbered questions
        has_numbered_questions = any(re.search(pattern, line, re.MULTILINE) 
                                   for pattern in question_patterns 
                                   for line in page_text.split('\n')[:20])  # Check first 20 lines
        
        # Check for Yes/No answer patterns
        has_yes_no = bool(re.search(r'\b(yes|no)\b', page_text_lower))
        
        # Check for question-answer patterns (question mark followed by answer)
        has_qa_pattern = bool(re.search(r'\?[^\?]*\b(yes|no|flint|michigan|unemployed)', page_text_lower))
        
        # If page has DRAI indicators, include it
        if has_drai_keyword or (has_numbered_questions and (has_yes_no or has_qa_pattern)):
            drai_pages.append(page_num)
            logger.debug(f"Identified page {page_num} as DRAI page (keywords: {has_drai_keyword}, questions: {has_numbered_questions}, Q&A: {has_qa_pattern})")
    
    logger.info(f"Identified {len(drai_pages)} DRAI pages: {sorted(drai_pages)}")
    return sorted(drai_pages)


def extract_questions_answers(
    page_text: str,
    page_numbers: List[int],
    llm: Any
) -> Dict[str, Any]:
    """
    Extract questions and answers from DRAI pages using LLM.
    
    Args:
        page_text: Combined text from pages to process
        page_numbers: List of page numbers being processed
        llm: LLM instance
        
    Returns:
        Dictionary with extracted questions and answers categorized by type
    """
    prompt = f"""You are extracting data from a Donor Risk Assessment Interview (DRAI) form.
The form contains numbered questions (1, 2, 3, 3a, 4a, 4a(i), etc.) with answers.

CRITICAL INSTRUCTIONS:
1. Extract EVERY question and its answer, even if the answer is "No"
2. Preserve the exact question text and answer text as they appear in the document
3. For follow-up questions (marked with letters/numbers like 3a, 4a(i), 4a(ii)), extract them as separate entries
4. Maintain question numbering relationships (e.g., 4a(i) is a follow-up to 4a)
5. Extract all details from follow-up questions (dates, names, phone numbers, addresses, etc.)

CATEGORIZATION RULES:
- Medical_History: Questions about health problems, physicians, specialists, medical facilities, 
  medications, treatments, visits, reasons for visits, provider information, toxic exposures, 
  medical conditions, diagnoses, procedures
- Social_History: Questions about birth place, occupation, lifestyle factors, personal history
- Risk_Factors: Questions about drug use, illegal substances, bleeding disorders, transplants, 
  animal tissue exposure, neurological diseases, high-risk behaviors, exposures, tattoos, 
  sexual history, incarceration, IV drug use
- Additional_Information: Any other information that doesn't fit the above categories, 
  including introductory text, notes, explanations, contact information

OUTPUT FORMAT:
Return a JSON object with the following structure:

{{
  "Medical_History": {{
    "Question_3": "Did she/he* have any health problems due to exposure to toxic substances such as pesticides, lead, mercury, gold, asbestos, agent orange, etc.?",
    "Answer_3": "No",
    "Question_4a": "Did she/he* have a family physician or a specialist?",
    "Answer_4a": "Yes",
    "Question_4a_i": "When was her/his* last visit?",
    "Answer_4a_i": "May 7th",
    "Question_4a_ii": "Why?",
    "Answer_4a_ii": "Pt seen for low sodium",
    "Question_4a_iii": "Provide any contact information (e.g., name, group, facility, phone number, etc.):",
    "Answer_4a_iii": "Harmony Cares medical Group 810-230-9500",
    ...
  }},
  "Social_History": {{
    "Question_1": "Where was she/he* born?",
    "Answer_1": "Flint Michigan",
    "Question_2": "What was her/his* occupation?",
    "Answer_2": "unemployed",
    ...
  }},
  "Risk_Factors": {{
    "Question_20": "In the past 5 years, did she/he* receive medication for a bleeding disorder such as hemophilia?",
    "Answer_20": "No",
    "Question_21": "Did she/he* EVER use or take drugs, such as steroids, cocaine, heroin, amphetamines, or anything NOT prescribed by her/his* doctor?",
    "Answer_21": "No",
    "Question_22a": "Did she/he* EVER have a transplant or medical procedure that involved being exposed to live cells, tissues or organs from an animal?",
    "Answer_22a": "No",
    "Question_23": "Was she/he* EVER told by a physician that she/he* had a disease of the brain or a neurological disease such as Alzheimer's Parkinson's",
    "Answer_23": "No",
    ...
  }},
  "Additional_Information": {{
    "Introductory_Text": "I want to advise you of the sensitive and personal nature of some of these questions...",
    ...
  }}
}}

IMPORTANT:
- Extract ALL questions, including those with "No" answers
- Preserve exact wording from the document
- Include all follow-up questions and their answers
- Extract dates, names, phone numbers, and other specifics mentioned in answers
- If a question has multiple parts or follow-ups, create separate entries for each
- Be thorough - check all pages provided

Document content (Pages {', '.join(map(str, page_numbers))}):
{page_text}

Return only the JSON object, no other text or markdown formatting:"""
    
    try:
        response = call_llm_with_retry(
            llm=llm,
            prompt=prompt,
            max_retries=3,
            base_delay=1.0,
            timeout=180,  # Longer timeout for comprehensive extraction
            context=f"DRAI extraction for pages {page_numbers}"
        )
        
        extracted_data = safe_parse_llm_json(response.content)
        
        # Ensure all categories are present
        result = {
            'Medical_History': extracted_data.get('Medical_History', {}),
            'Social_History': extracted_data.get('Social_History', {}),
            'Risk_Factors': extracted_data.get('Risk_Factors', {}),
            'Additional_Information': extracted_data.get('Additional_Information', {})
        }
        
        logger.info(f"Extracted {sum(len(v) for v in result.values())} question-answer pairs from pages {page_numbers}")
        return result
        
    except LLMResponseParseError as e:
        logger.error(f"Failed to parse DRAI extraction response for pages {page_numbers}: {e}")
        return {
            'Medical_History': {},
            'Social_History': {},
            'Risk_Factors': {},
            'Additional_Information': {}
        }
    except Exception as e:
        logger.error(f"Error extracting DRAI questions/answers for pages {page_numbers}: {e}", exc_info=True)
        return {
            'Medical_History': {},
            'Social_History': {},
            'Risk_Factors': {},
            'Additional_Information': {}
        }


def process_drai_pages_batch(
    drai_pages: List[int],
    chunks_by_page: Dict[int, List[DocumentChunk]],
    llm: Any,
    batch_size: int = 12
) -> List[Dict[str, Any]]:
    """
    Process DRAI pages in batches to manage context size.
    
    Args:
        drai_pages: List of page numbers containing DRAI content
        chunks_by_page: Dictionary mapping page numbers to chunks
        llm: LLM instance
        batch_size: Number of pages to process in each batch
        
    Returns:
        List of extraction results from each batch
    """
    batch_results = []
    
    # Process pages in batches with overlap to ensure no questions are split
    overlap = 2  # Overlap 2 pages between batches
    
    for i in range(0, len(drai_pages), batch_size - overlap):
        batch_pages = drai_pages[i:i + batch_size]
        
        if not batch_pages:
            continue
        
        # Combine chunks from all pages in this batch
        batch_text_parts = []
        for page_num in batch_pages:
            if page_num in chunks_by_page:
                page_chunks = chunks_by_page[page_num]
                page_text = "\n".join([chunk.chunk_text for chunk in page_chunks if chunk.chunk_text])
                batch_text_parts.append(f"=== PAGE {page_num} ===\n{page_text}")
        
        batch_text = "\n\n".join(batch_text_parts)
        
        if not batch_text.strip():
            logger.warning(f"No text found for batch pages {batch_pages}")
            continue
        
        logger.info(f"Processing DRAI batch: pages {batch_pages} ({len(batch_pages)} pages)")
        
        # Extract questions and answers from this batch
        batch_result = extract_questions_answers(batch_text, batch_pages, llm)
        batch_results.append({
            'pages': batch_pages,
            'extracted_data': batch_result
        })
    
    return batch_results


def merge_drai_results(batch_results: List[Dict[str, Any]]) -> Dict[str, Any]:
    """
    Merge results from multiple batches into a single comprehensive result.
    
    Args:
        batch_results: List of batch extraction results
        
    Returns:
        Merged DRAI data with all questions and answers
    """
    merged = {
        'Medical_History': {},
        'Social_History': {},
        'Risk_Factors': {},
        'Additional_Information': {}
    }
    
    # Track which pages were processed
    processed_pages = []
    
    for batch_result in batch_results:
        processed_pages.extend(batch_result['pages'])
        extracted_data = batch_result['extracted_data']
        
        # Merge each category
        for category in merged.keys():
            if category in extracted_data:
                # Merge dictionaries, with later batches overriding earlier ones for duplicate keys
                merged[category].update(extracted_data[category])
    
    logger.info(f"Merged DRAI results from {len(batch_results)} batches covering pages {sorted(set(processed_pages))}")
    logger.info(f"Total questions extracted: Medical_History={len(merged['Medical_History'])}, "
                f"Social_History={len(merged['Social_History'])}, "
                f"Risk_Factors={len(merged['Risk_Factors'])}, "
                f"Additional_Information={len(merged['Additional_Information'])}")
    
    return merged


def validate_drai_extraction(
    extracted_data: Dict[str, Any],
    total_pages: int,
    drai_pages: List[int]
) -> Dict[str, Any]:
    """
    Validate that DRAI extraction is complete.
    
    Args:
        extracted_data: Extracted DRAI data
        total_pages: Total number of pages in document
        drai_pages: List of pages identified as containing DRAI
        
    Returns:
        Validation result with statistics and any issues found
    """
    validation_result = {
        'is_complete': True,
        'total_questions': 0,
        'questions_by_category': {},
        'pages_processed': len(drai_pages),
        'total_pages_in_document': total_pages,
        'issues': []
    }
    
    # Count questions in each category
    for category, questions in extracted_data.items():
        if isinstance(questions, dict):
            # Count question-answer pairs (each pair has Question_X and Answer_X keys)
            question_count = len([k for k in questions.keys() if k.startswith('Question_')])
            validation_result['questions_by_category'][category] = question_count
            validation_result['total_questions'] += question_count
    
    # Check for potential issues
    if validation_result['total_questions'] == 0:
        validation_result['is_complete'] = False
        validation_result['issues'].append("No questions extracted from DRAI pages")
    
    if len(drai_pages) == 0:
        validation_result['is_complete'] = False
        validation_result['issues'].append("No DRAI pages identified in document")
    
    # Check for gaps in page coverage (if DRAI pages are not consecutive)
    if len(drai_pages) > 1:
        sorted_pages = sorted(drai_pages)
        gaps = []
        for i in range(len(sorted_pages) - 1):
            if sorted_pages[i + 1] - sorted_pages[i] > 1:
                gaps.append(f"Gap between pages {sorted_pages[i]} and {sorted_pages[i + 1]}")
        if gaps:
            validation_result['issues'].extend(gaps)
            logger.warning(f"Found page gaps in DRAI: {gaps}")
    
    logger.info(f"DRAI extraction validation: {validation_result['total_questions']} questions extracted "
                f"from {validation_result['pages_processed']} pages. "
                f"Complete: {validation_result['is_complete']}")
    
    if validation_result['issues']:
        logger.warning(f"DRAI extraction issues: {validation_result['issues']}")
    
    return validation_result


def extract_drai_comprehensive(
    document_id: int,
    db: Session,
    llm: Any,
    page_doc_list: List[Any]
) -> Dict[str, Any]:
    """
    Comprehensive DRAI extraction that processes ALL pages and chunks.
    
    Strategy:
    1. Get ALL chunks from database (grouped by page)
    2. Identify DRAI pages (pages containing DRAI content)
    3. Extract questions and answers from all DRAI pages
    4. Validate completeness
    
    Args:
        document_id: ID of the document
        db: Database session
        llm: LLM instance
        page_doc_list: List of page documents (for reference, but we use database chunks)
        
    Returns:
        Dictionary with DRAI data in the format expected by the system:
        {
            'present': bool,
            'pages': List[Dict with document_id and page],
            'summary': Dict with summary text,
            'extracted_data': Dict with Medical_History, Social_History, Risk_Factors, Additional_Information
        }
    """
    try:
        logger.info(f"Starting comprehensive DRAI extraction for document {document_id}")
        
        # Step 1: Get ALL chunks from database, ordered by page and chunk index
        all_chunks = db.query(DocumentChunk).filter(
            DocumentChunk.document_id == document_id
        ).order_by(
            DocumentChunk.page_number.asc().nullslast(),
            DocumentChunk.chunk_index.asc()
        ).all()
        
        if not all_chunks:
            logger.warning(f"No chunks found in database for document {document_id}")
            return {
                'present': False,
                'pages': [],
                'summary': {},
                'extracted_data': {}
            }
        
        logger.info(f"Retrieved {len(all_chunks)} chunks from database for document {document_id}")
        
        # Step 2: Group chunks by page number
        chunks_by_page = defaultdict(list)
        for chunk in all_chunks:
            if chunk.page_number is not None:
                chunks_by_page[chunk.page_number].append(chunk)
        
        total_pages = max(chunks_by_page.keys()) if chunks_by_page else 0
        logger.info(f"Document has {total_pages} pages with {len(chunks_by_page)} pages containing chunks")
        
        # Step 3: Identify DRAI pages
        drai_pages = identify_drai_pages(chunks_by_page)
        
        if not drai_pages:
            logger.info(f"No DRAI pages identified in document {document_id}")
            return {
                'present': False,
                'pages': [],
                'summary': {},
                'extracted_data': {}
            }
        
        # Step 4: Process DRAI pages in batches
        batch_results = process_drai_pages_batch(drai_pages, chunks_by_page, llm, batch_size=12)
        
        if not batch_results:
            logger.warning(f"No batch results from DRAI extraction for document {document_id}")
            return {
                'present': False,
                'pages': [{'document_id': document_id, 'page': p} for p in drai_pages],
                'summary': {},
                'extracted_data': {}
            }
        
        # Step 5: Merge results from all batches
        merged_data = merge_drai_results(batch_results)
        
        # Step 6: Validate extraction
        validation = validate_drai_extraction(merged_data, total_pages, drai_pages)
        
        # Step 7: Create summary
        summary = {
            'Medical History': f"Extracted {validation['questions_by_category'].get('Medical_History', 0)} medical history questions",
            'Social History': f"Extracted {validation['questions_by_category'].get('Social_History', 0)} social history questions",
            'Risk Factors': f"Extracted {validation['questions_by_category'].get('Risk_Factors', 0)} risk factor questions",
            'Total Questions': validation['total_questions'],
            'Pages Processed': validation['pages_processed'],
            'Validation Status': 'Complete' if validation['is_complete'] else 'Incomplete'
        }
        
        if validation['issues']:
            summary['Issues'] = '; '.join(validation['issues'])
        
        # Step 8: Build final result
        result = {
            'present': True,
            'pages': [{'document_id': document_id, 'page': p} for p in drai_pages],
            'summary': summary,
            'extracted_data': merged_data
        }
        
        logger.info(f"Successfully completed DRAI extraction for document {document_id}: "
                   f"{validation['total_questions']} questions from {len(drai_pages)} pages")
        
        return result
        
    except Exception as e:
        logger.error(f"Error in comprehensive DRAI extraction for document {document_id}: {e}", exc_info=True)
        return {
            'present': False,
            'pages': [],
            'summary': {'Error': str(e)},
            'extracted_data': {}
        }

