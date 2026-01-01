"""
Document-specific extraction service.
Extracts DRAI, Medical Records Review, Plasma Dilution, and Infectious Disease Summary in one batched LLM call.
"""
import logging
from typing import Dict, Any, List, Optional
from sqlalchemy.orm import Session
from app.services.processing.utils.llm_wrapper import call_llm_with_retry
from app.services.processing.utils.json_parser import safe_parse_llm_json, LLMResponseParseError

logger = logging.getLogger(__name__)


def extract_document_specific_data_batched(
    document_id: int,
    vectordb: Any,
    llm: Any,
    page_doc_list: List[Any],
    db: Session
) -> Dict[str, Any]:
    """
    Extract document-specific data (DRAI, Medical Records Review, Plasma Dilution, Infectious Disease Summary)
    in a single batched LLM call.
    
    Returns:
        Dictionary matching expected extracted_data structure
    """
    try:
        # Build comprehensive semantic search queries
        queries = [
            # DRAI queries
            "donor risk assessment interview DRAI medical history social history risk factors",
            "risk assessment interview questions answers donor interview",
            # Medical Records Review queries
            "medical records review summary diagnoses procedures medications",
            "medical review summary clinical summary patient summary",
            # Plasma Dilution queries
            "plasma dilution factor volumes measurements procedures",
            "plasma dilution calculation volume measurement",
            # Infectious Disease Testing Summary queries
            "infectious disease testing summary test results laboratory information",
            "serology culture test summary infectious disease report"
        ]
        
        # Retrieve relevant chunks using multiple queries
        all_retrieved_docs = []
        retriever = vectordb.as_retriever(search_type='similarity', search_kwargs={'k': 15})
        
        for query in queries:
            try:
                retrieved_docs = retriever.invoke(query)
                all_retrieved_docs.extend(retrieved_docs)
            except Exception as e:
                logger.debug(f"Error retrieving chunks for query '{query}': {e}")
                continue
        
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
        
        # Build comprehensive prompt
        prompt = f"""You are an expert medical document analyst specializing in donor eligibility assessment. Analyze the provided donor document and extract document-specific information for the following sections:

CRITICAL INSTRUCTIONS:
1. Extract ONLY information that is explicitly present in the document
2. If a section is not found, set it to null or empty structure
3. Be thorough - check all pages and sections of the document
4. Extract exact values as they appear (dates, numbers, text)
5. For key-value pairs, extract both keys and values exactly as they appear
6. For lists, extract all items found in the document

SECTIONS TO EXTRACT:

1. DRAI (Donor Risk Assessment Interview):
   - Medical_History: Extract as key-value pairs (e.g., {{"Diabetes": "Yes", "Hypertension": "No"}})
   - Social_History: Extract as key-value pairs (e.g., {{"Smoking": "No", "Alcohol": "Occasional"}})
   - Risk_Factors: Extract as key-value pairs (e.g., {{"IV Drug Use": "No", "High Risk Behavior": "No"}})
   - Additional_Information: Any additional information from the DRAI
   - summary: Create a brief summary of the DRAI findings

2. Medical Records Review Summary:
   - Diagnoses: Extract as a list of diagnosis strings
   - Procedures: Extract as a list of procedure strings
   - Medications: Extract as a list of medication strings
   - Significant_History: Extract as a list of significant history items
   - summary: Create summary objects with formatted text:
     * Diagnoses: Comma-separated string of diagnoses
     * Procedures: Comma-separated string of procedures
     * Medications: Comma-separated string of medications
     * Significant History: Summary of significant history

3. Plasma Dilution:
   - Dilution_Factor: Extract the dilution factor value (number or text)
   - Volumes: Extract volume measurements (text or structured)
   - Procedures: Extract procedure details (text)
   - Measurements: Extract measurement values (text or structured)
   - summary: Create summary fields for each extracted value

4. Infectious Disease Testing Summary:
   - Test_Results: Extract as an array of test result objects, each with:
     * Test_Name: Name of the test
     * Test_Result: Result value
     * Specimen_Date_Time: Date and time of specimen collection
     * Specimen_Type: Type of specimen
     * Test_Method: Testing method used
     * Comments: Any additional comments
   - Test_Dates: Extract as an array of test dates (strings)
   - Laboratory_Information: Extract as an object with:
     * testing_laboratory: Laboratory name
     * laboratory_address: Laboratory address
     * phone: Phone number
     * fax: Fax number
     * fda: FDA number
     * clia: CLIA number
     * category: Category
     * ashi: ASHI number
     * client: Client name
   - Sample_Information: Extract as an object with:
     * sample_date: Sample collection date
     * sample_time: Sample collection time
     * sample_type_1: Primary sample type
     * sample_type_2: Secondary sample type (if applicable)
     * report_generated: Report generation date
   - Additional_Notes: Extract any additional notes as a string
   - summary: Create summary object with formatted text for each field

OUTPUT FORMAT:
Return a JSON object with the following structure:

{{
  "donor_risk_assessment_interview": {{
    "extracted_data": {{
      "Medical_History": {{}},
      "Social_History": {{}},
      "Risk_Factors": {{}},
      "Additional_Information": {{}}
    }},
    "summary": {{
      "Medical History": "",
      "Social History": "",
      "Risk Factors": "",
      "Additional Information": ""
    }}
  }},
  "medical_records_review_summary": {{
    "extracted_data": {{
      "Diagnoses": [],
      "Procedures": [],
      "Medications": [],
      "Significant_History": []
    }},
    "summary": {{
      "Diagnoses": "",
      "Procedures": "",
      "Medications": "",
      "Significant History": ""
    }}
  }},
  "plasma_dilution": {{
    "extracted_data": {{
      "Dilution_Factor": null,
      "Volumes": null,
      "Procedures": null,
      "Measurements": null
    }},
    "summary": {{
      "Dilution Factor": "",
      "Volumes": "",
      "Procedures": "",
      "Measurements": ""
    }}
  }},
  "infectious_disease_testing": {{
    "extracted_data": {{
      "Test_Results": [],
      "Test_Dates": [],
      "Laboratory_Information": {{
        "testing_laboratory": null,
        "laboratory_address": null,
        "phone": null,
        "fax": null,
        "fda": null,
        "clia": null,
        "category": null,
        "ashi": null,
        "client": null
      }},
      "Sample_Information": {{
        "sample_date": null,
        "sample_time": null,
        "sample_type_1": null,
        "sample_type_2": null,
        "report_generated": null
      }},
      "Additional_Notes": null
    }},
    "summary": {{
      "Test Results": "",
      "Test Dates": "",
      "Laboratory Information": "",
      "Sample Information": "",
      "Additional Notes": ""
    }}
  }}
}}

IMPORTANT:
- Extract ONLY information explicitly present in the document
- Use null for missing values (not empty strings, not false)
- For lists, use empty arrays [] if no items found
- For objects, use empty objects {{}} if no data found
- Create meaningful summaries that capture the essence of each section
- Be comprehensive - check all pages and sections

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
            context="document-specific extraction"
        )
        
        # Parse JSON response
        try:
            extracted_data = safe_parse_llm_json(response.content)
            
            # Ensure all expected keys are present
            result = {
                'donor_risk_assessment_interview': extracted_data.get('donor_risk_assessment_interview', {
                    'extracted_data': {},
                    'summary': {}
                }),
                'medical_records_review_summary': extracted_data.get('medical_records_review_summary', {
                    'extracted_data': {},
                    'summary': {}
                }),
                'plasma_dilution': extracted_data.get('plasma_dilution', {
                    'extracted_data': {},
                    'summary': {}
                }),
                'infectious_disease_testing': extracted_data.get('infectious_disease_testing', {
                    'extracted_data': {},
                    'summary': {}
                })
            }
            
            logger.info(f"Successfully extracted document-specific data for document {document_id}")
            return result
            
        except LLMResponseParseError as e:
            logger.error(f"Failed to parse document-specific extraction response for document {document_id}: {e}")
            # Return empty structure on parse error
            return {
                'donor_risk_assessment_interview': {'extracted_data': {}, 'summary': {}},
                'medical_records_review_summary': {'extracted_data': {}, 'summary': {}},
                'plasma_dilution': {'extracted_data': {}, 'summary': {}},
                'infectious_disease_testing': {'extracted_data': {}, 'summary': {}}
            }
        
    except Exception as e:
        logger.error(f"Error in document-specific extraction for document {document_id}: {e}", exc_info=True)
        # Return empty structure on error
        return {
            'donor_risk_assessment_interview': {'extracted_data': {}, 'summary': {}},
            'medical_records_review_summary': {'extracted_data': {}, 'summary': {}},
            'plasma_dilution': {'extracted_data': {}, 'summary': {}},
            'infectious_disease_testing': {'extracted_data': {}, 'summary': {}}
        }

