"""
Criteria-specific data extraction service.
Extracts only data points needed for each criterion in the acceptance criteria table.
"""
import json
import os
import logging
from typing import Dict, Any, List, Optional, Tuple
from sqlalchemy.orm import Session
from app.models.criteria_evaluation import CriteriaEvaluation, EvaluationResult, TissueType
from app.services.processing.utils.llm_wrapper import call_llm_with_retry, LLMCallError
from app.services.processing.utils.json_parser import safe_parse_llm_json, LLMResponseParseError

logger = logging.getLogger(__name__)


def _has_actual_data(extracted_data: Dict[str, Any]) -> bool:
    """
    Check if extracted_data has any actual data (not all nulls).
    Excludes metadata fields like _criterion_name, _extraction_timestamp.
    
    Args:
        extracted_data: Dictionary of extracted data
        
    Returns:
        True if there's actual data, False if all values are null
    """
    if not extracted_data:
        return False
    
    metadata_fields = {'_criterion_name', '_extraction_timestamp'}
    for key, value in extracted_data.items():
        if key not in metadata_fields and value is not None:
            # Check if value is not empty string, empty list, or empty dict
            if isinstance(value, str) and value.strip():
                return True
            elif isinstance(value, (list, dict)) and len(value) > 0:
                return True
            elif not isinstance(value, (str, list, dict)):
                return True
    
    return False

# Get config directory
_CONFIG_DIR = os.path.join(os.path.dirname(__file__), 'processing', 'config')


def load_acceptance_criteria_config() -> Dict[str, Any]:
    """Load acceptance criteria configuration."""
    criteria_path = os.path.join(_CONFIG_DIR, 'acceptance_criteria.json')
    with open(criteria_path, 'r') as f:
        return json.load(f)


def extract_criteria_data(
    document_id: int,
    donor_id: int,
    vectordb: Any,
    llm: Any,
    db: Session,
    page_doc_list: List[Any]
) -> int:
    """
    Extract data for all criteria from acceptance criteria config.
    
    Returns:
        Number of criteria evaluations stored
    """
    try:
        # Load acceptance criteria config
        criteria_config = load_acceptance_criteria_config()
        
        count = 0
        
        # Extract data for each criterion
        for criterion_name, criterion_info in criteria_config.items():
            try:
                # Extract data for this criterion
                extracted_data = extract_single_criterion(
                    criterion_name=criterion_name,
                    criterion_info=criterion_info,
                    document_chunks=page_doc_list,
                    vectordb=vectordb,
                    llm=llm
                )
                
                if not extracted_data:
                    continue
                
                # Add metadata
                extracted_data['_criterion_name'] = criterion_name
                extracted_data['_extraction_timestamp'] = str(os.path.getmtime(__file__))
                
                # Skip storing if there's no actual data (all values are null)
                if not _has_actual_data(extracted_data):
                    logger.debug(f"Skipping criterion {criterion_name} - no actual extracted data")
                    continue
                
                # Determine tissue types to evaluate
                tissue_types = []
                if criterion_info.get('tissue_specific', False):
                    tissue_types = [TissueType.MUSCULOSKELETAL, TissueType.SKIN]
                else:
                    tissue_types = [TissueType.BOTH]
                
                # Store extracted data for each tissue type
                for tissue_type in tissue_types:
                    # Store raw extracted data (evaluation will happen later)
                    criteria_eval = CriteriaEvaluation(
                        donor_id=donor_id,
                        document_id=document_id,
                        criterion_name=criterion_name,
                        tissue_type=tissue_type,
                        extracted_data=extracted_data,
                        evaluation_result=EvaluationResult.MD_DISCRETION  # Default, will be evaluated later
                    )
                    db.add(criteria_eval)
                    count += 1
                
            except Exception as e:
                logger.error(f"Error extracting data for criterion {criterion_name} in document {document_id}: {e}", exc_info=True)
                continue
        
        db.commit()
        logger.info(f"Stored extracted data for {count} criteria evaluations in document {document_id}")
        return count
        
    except Exception as e:
        logger.error(f"Error extracting criteria data for document {document_id}: {e}", exc_info=True)
        db.rollback()
        return 0


def extract_all_criteria_data_batched(
    document_id: int,
    donor_id: int,
    vectordb: Any,
    llm: Any,
    db: Session,
    page_doc_list: List[Any]
) -> int:
    """
    Extract data for ALL criteria in a single LLM call.
    This reduces LLM calls from 79 to 1 for criteria extraction.
    
    Returns:
        Number of criteria evaluations stored
    """
    try:
        # Load acceptance criteria config
        criteria_config = load_acceptance_criteria_config()
        
        # Build comprehensive semantic search queries covering major criteria categories
        queries = [
            "age donor age years old",
            "cancer malignancy tumor neoplasm",
            "HIV AIDS human immunodeficiency virus",
            "hepatitis HBV HCV liver disease",
            "syphilis RPR VDRL sexually transmitted",
            "sepsis infection septicemia",
            "culture contamination microorganisms",
            "diabetes diabetic",
            "hypertension high blood pressure",
            "medications drugs prescription",
            "surgery surgical procedure",
            "medical history past medical history PMH",
            "social history smoking alcohol drugs",
            "cause of death COD",
            "autopsy post-mortem examination"
        ]
        
        # Retrieve relevant chunks using multiple queries
        all_retrieved_docs = []
        retriever = vectordb.as_retriever(search_type='similarity', search_kwargs={'k': 10})
        
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
        
        retrieved_docs = unique_docs[:50]  # Limit to top 50 unique chunks
        
        # Also include first 20 pages from page_doc_list for comprehensive coverage
        context_pages = []
        for page_doc in page_doc_list[:20]:
            if hasattr(page_doc, 'page_content'):
                context_pages.append(page_doc)
        
        # Build comprehensive context
        context_parts = []
        for doc in retrieved_docs:
            context_parts.append(f"Page {doc.metadata.get('page', '?')}: {doc.page_content}")
        for page_doc in context_pages:
            page_num = getattr(page_doc, 'metadata', {}).get('page', '?')
            content = getattr(page_doc, 'page_content', '')
            context_parts.append(f"Page {page_num}: {content}")
        
        context = "\n".join(context_parts)
        
        # Build comprehensive criteria list with data points
        criteria_list = []
        for criterion_name, criterion_info in criteria_config.items():
            required_data_points = criterion_info.get('required_data_points', [])
            if required_data_points:
                data_points_str = ", ".join(required_data_points)
                criteria_list.append(f"- {criterion_name}: Extract [{data_points_str}]")
        
        criteria_list_str = "\n".join(criteria_list)
        
        # Build comprehensive prompt
        prompt = f"""You are an expert medical document analyst specializing in donor eligibility assessment. Analyze the provided donor document and extract ALL required data points for each of the 79 acceptance criteria listed below.

CRITICAL INSTRUCTIONS:
1. Extract ONLY information that is explicitly present in the document
2. If a data point is not found, set it to null (not false, not empty string, but null)
3. Be thorough - check all pages and sections of the document
4. Extract exact values as they appear (dates, numbers, text)
5. For boolean/yes-no questions, extract as true/false/null based on what's stated
6. For dates, extract in the format found in the document (or convert to YYYY-MM-DD if possible)
7. STRICT RULE FOR DIAGNOSIS FIELDS (sepsis_diagnosis, tb_diagnosis, etc.):
   - Extract true/Yes ONLY if the document contains a statement that indicates the patient 
     HAS or HAD the condition as a medical fact/diagnosis
   - The statement must indicate the condition is/was present in the patient, not just mentioned
   - Accept ANY phrasing that clearly indicates a diagnosis (e.g., "diagnosed with", "has", 
     "confirmed", "present", "active", "history of", "noted", "diagnosis:", etc.)
   - Extract null (NOT true) if:
     * The condition word appears only in test names (e.g., "Sepsis Protocol", "TB Test")
     * The condition word appears only in lab results without a diagnosis statement
     * Document says "rule out [condition]" or "R/O [condition]" (this means checking, not diagnosing)
     * Document says "no evidence of [condition]" or "negative for [condition]"
     * Document says "suspected [condition]" or "possible [condition]" (uncertainty, not diagnosis)
     * Test results are positive/negative but no explicit diagnosis statement exists
     * The word appears only in passing without indicating the patient has the condition
   
   KEY PRINCIPLE: A diagnosis field should be true ONLY when the document states that the 
   patient has/had the condition as a medical fact. If you're inferring it from test results 
   alone, or if it's only mentioned in test names/protocols, it must be null.

ACCEPTANCE CRITERIA TO EXTRACT DATA FOR:
{criteria_list_str}

OUTPUT FORMAT:
Return a JSON object where each key is a criterion name and the value is an object containing the extracted data points for that criterion.

Example structure:
{{
  "Age": {{
    "donor_age": 45,
    "tissue_type": "femur",
    "gender": "male"
  }},
  "Cancer": {{
    "cancer_type": null,
    "diagnosis_date": null,
    "treatment": null,
    "recurrence": null,
    "time_since_death": null
  }},
  "HIV": {{
    "hiv_history": false,
    "hiv_exposure": null,
    "hiv_test_results": "negative",
    "hiv_test_date": "2024-01-15"
  }}
}}

IMPORTANT:
- Include ALL 79 criteria in your response, even if most data points are null
- Use null (not false, not empty string) when data is not found
- Extract exact values from the document
- Be comprehensive - check medical history, social history, lab results, cause of death, etc.

Document content:
{context}

Return only the JSON object, no other text or markdown formatting:"""
        
        # Call LLM with longer timeout for comprehensive extraction
        response = call_llm_with_retry(
            llm=llm,
            prompt=prompt,
            max_retries=3,
            base_delay=1.0,
            timeout=120,  # Longer timeout for batched extraction
            context="batched criteria extraction"
        )
        
        # Parse JSON response
        try:
            all_extracted_data = safe_parse_llm_json(response.content)
        except LLMResponseParseError as e:
            logger.error(f"Failed to parse batched criteria extraction response for document {document_id}: {e}")
            # Fallback to individual extraction
            logger.info(f"Falling back to individual criteria extraction for document {document_id}")
            return extract_criteria_data(document_id, donor_id, vectordb, llm, db, page_doc_list)
        
        # Process extracted data and store in database
        count = 0
        for criterion_name, criterion_info in criteria_config.items():
            try:
                # Get extracted data for this criterion
                extracted_data = all_extracted_data.get(criterion_name)
                
                if not extracted_data:
                    # If criterion not in response, create empty data structure
                    required_data_points = criterion_info.get('required_data_points', [])
                    extracted_data = {dp: None for dp in required_data_points}
                
                # Ensure all required data points are present
                required_data_points = criterion_info.get('required_data_points', [])
                for dp in required_data_points:
                    if dp not in extracted_data:
                        extracted_data[dp] = None
                
                # Remove any extra keys that aren't required data points
                extracted_data = {k: v for k, v in extracted_data.items() if k in required_data_points or k.startswith('_')}
                
                # Add metadata
                extracted_data['_criterion_name'] = criterion_name
                extracted_data['_extraction_timestamp'] = str(os.path.getmtime(__file__))
                
                # Skip storing if there's no actual data (all values are null)
                if not _has_actual_data(extracted_data):
                    logger.debug(f"Skipping criterion {criterion_name} - no actual extracted data")
                    continue
                
                # Determine tissue types to evaluate
                tissue_types = []
                if criterion_info.get('tissue_specific', False):
                    tissue_types = [TissueType.MUSCULOSKELETAL, TissueType.SKIN]
                else:
                    tissue_types = [TissueType.BOTH]
                
                # Store extracted data for each tissue type
                for tissue_type in tissue_types:
                    criteria_eval = CriteriaEvaluation(
                        donor_id=donor_id,
                        document_id=document_id,
                        criterion_name=criterion_name,
                        tissue_type=tissue_type,
                        extracted_data=extracted_data,
                        evaluation_result=EvaluationResult.MD_DISCRETION  # Default, will be evaluated later
                    )
                    db.add(criteria_eval)
                    count += 1
                
            except Exception as e:
                logger.error(f"Error processing extracted data for criterion {criterion_name} in document {document_id}: {e}", exc_info=True)
                continue
        
        db.commit()
        logger.info(f"Stored extracted data for {count} criteria evaluations (batched extraction) in document {document_id}")
        return count
        
    except Exception as e:
        logger.error(f"Error in batched criteria extraction for document {document_id}: {e}", exc_info=True)
        db.rollback()
        # Fallback to individual extraction
        logger.info(f"Falling back to individual criteria extraction for document {document_id}")
        try:
            return extract_criteria_data(document_id, donor_id, vectordb, llm, db, page_doc_list)
        except Exception as fallback_error:
            logger.error(f"Fallback extraction also failed for document {document_id}: {fallback_error}", exc_info=True)
            return 0


def extract_single_criterion(
    criterion_name: str,
    criterion_info: Dict[str, Any],
    document_chunks: List[Any],
    vectordb: Any,
    llm: Any
) -> Optional[Dict[str, Any]]:
    """
    Extract data for a single criterion.
    
    Returns:
        Dictionary with extracted data points, or None if no data found
    """
    try:
        required_data_points = criterion_info.get('required_data_points', [])
        if not required_data_points:
            return None
        
        # Build search query from criterion name and required data points
        search_query = f"{criterion_name} {' '.join(required_data_points)}"
        
        # Retrieve relevant chunks
        retriever = vectordb.as_retriever(search_type='similarity', search_kwargs={'k': 5})
        retrieved_docs = retriever.invoke(search_query)
        
        if not retrieved_docs:
            # Also try searching in page_doc_list by keyword
            relevant_pages = []
            criterion_lower = criterion_name.lower()
            for page_doc in document_chunks:
                if hasattr(page_doc, 'page_content'):
                    content = page_doc.page_content.lower()
                    if criterion_lower in content or any(dp.lower() in content for dp in required_data_points):
                        relevant_pages.append(page_doc)
            
            if not relevant_pages:
                return None
            
            # Build context from relevant pages
            context = "\n".join([
                f"Page {getattr(page_doc, 'metadata', {}).get('page', '?')}: {getattr(page_doc, 'page_content', '')}"
                for page_doc in relevant_pages[:5]
            ])
        else:
            context = "\n".join([
                f"Page {doc.metadata.get('page', '?')}: {doc.page_content}"
                for doc in retrieved_docs
            ])
        
        # Create extraction prompt
        data_points_list = ", ".join(required_data_points)
        prompt = f"""You are a medical document analyst. Extract specific data points from the donor document for the criterion: {criterion_name}

Required data points to extract:
{data_points_list}

Extract ONLY the information that is explicitly present in the document. If a data point is not found, set it to null.

Return the data as a JSON object with keys matching the required data points.

Example output format:
{{
  "{required_data_points[0] if required_data_points else 'data_point'}": "extracted value or null",
  "{required_data_points[1] if len(required_data_points) > 1 else 'another_point'}": "extracted value or null"
}}

Document content:
{context}

Return only the JSON object, no other text:"""
        
        # Call LLM
        response = call_llm_with_retry(
            llm=llm,
            prompt=prompt,
            max_retries=3,
            base_delay=1.0,
            timeout=60,
            context=f"criteria extraction: {criterion_name}"
        )
        
        # Parse JSON response
        try:
            extracted_data = safe_parse_llm_json(response.content)
            
            # Add metadata
            extracted_data['_criterion_name'] = criterion_name
            extracted_data['_extraction_timestamp'] = str(os.path.getmtime(__file__))  # Simple timestamp
            
            return extracted_data
            
        except LLMResponseParseError as e:
            logger.warning(f"Failed to parse extraction response for criterion {criterion_name}: {e}")
            return None
        
    except Exception as e:
        logger.error(f"Error extracting single criterion {criterion_name}: {e}", exc_info=True)
        return None

