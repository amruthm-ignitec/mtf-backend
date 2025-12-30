"""
Criteria-specific data extraction service.
Extracts only data points needed for each criterion in the acceptance criteria table.
"""
import json
import os
import logging
from typing import Dict, Any, List, Optional
from sqlalchemy.orm import Session
from app.models.criteria_evaluation import CriteriaEvaluation, EvaluationResult, TissueType
from app.services.processing.utils.llm_wrapper import call_llm_with_retry, LLMCallError
from app.services.processing.utils.json_parser import safe_parse_llm_json, LLMResponseParseError

logger = logging.getLogger(__name__)

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

