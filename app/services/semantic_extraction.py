"""
Semantic extraction service using semantic search + pattern matching.
Extracts structured data without LLM calls.
"""
import re
import logging
from typing import Dict, Any, List, Optional
from sqlalchemy.orm import Session
from app.models.document_chunk import DocumentChunk
from app.models.laboratory_result import LaboratoryResult, TestType

logger = logging.getLogger(__name__)


def clean_time_of_death(raw_time: str) -> str:
    """
    Clean and extract date, time, and timezone from time of death string.
    Removes labels and other extraneous information.
    
    Args:
        raw_time: Raw time of death string that may contain dates, labels, etc.
    
    Returns:
        Cleaned string with date, time, and timezone (e.g., "07/03/2025 19:03 EDT")
    """
    if not raw_time:
        return raw_time
    
    # Remove common prefixes/labels but keep the original for fallback
    cleaned = re.sub(r'(?:death\s+date[-:]?\s*time|date[-:]?\s*time|time\s+of\s+death)[:\s]*', '', raw_time, flags=re.IGNORECASE)
    
    # Common timezone abbreviations
    timezone_abbrevs = r'(?:EDT|EST|PDT|PST|CDT|CST|MDT|MST|AKDT|AKST|HST|UTC|GMT)'
    
    # Date patterns: MM/DD/YYYY, MM-DD-YYYY, YYYY-MM-DD, DD/MM/YYYY, etc.
    date_patterns = [
        r'(\d{1,2}[/-]\d{1,2}[/-]\d{4})',  # MM/DD/YYYY or MM-DD-YYYY
        r'(\d{4}[/-]\d{1,2}[/-]\d{1,2})',  # YYYY-MM-DD or YYYY/MM/DD
        r'(\d{1,2}[/-]\d{1,2}[/-]\d{2})',  # MM/DD/YY or MM-DD-YY
    ]
    
    # Pattern to match date, time (HH:MM or HH:MM:SS), and timezone
    # Try to find date + time + timezone together
    for date_pattern in date_patterns:
        full_pattern = date_pattern + r'\s+(\d{1,2}:\d{2}(?::\d{2})?)\s*(' + timezone_abbrevs + r')\b'
        match = re.search(full_pattern, cleaned, re.IGNORECASE)
        if match:
            date_part = match.group(1)
            time_part = match.group(2)
            tz_part = match.group(3).upper()
            return f"{date_part} {time_part} {tz_part}"
    
    # Fallback: try to find date and time separately, then timezone
    date_match = None
    for date_pattern in date_patterns:
        date_match = re.search(date_pattern, cleaned)
        if date_match:
            break
    
    time_pattern = r'(\d{1,2}:\d{2}(?::\d{2})?)'
    time_match = re.search(time_pattern, cleaned)
    
    if date_match and time_match:
        date_part = date_match.group(1)
        time_part = time_match.group(1)
        # Look for timezone within reasonable distance after the time
        time_pos = time_match.end()
        remaining_text = cleaned[time_pos:time_pos+30]
        tz_match = re.search(r'\b(' + timezone_abbrevs + r')\b', remaining_text, re.IGNORECASE)
        if tz_match:
            return f"{date_part} {time_part} {tz_match.group(1).upper()}"
        return f"{date_part} {time_part}"
    
    # If we have time but no date, try to find timezone
    if time_match:
        time_part = time_match.group(1)
        time_pos = time_match.end()
        remaining_text = cleaned[time_pos:time_pos+30]
        tz_match = re.search(r'\b(' + timezone_abbrevs + r')\b', remaining_text, re.IGNORECASE)
        if tz_match:
            return f"{time_part} {tz_match.group(1).upper()}"
        return time_part
    
    # If we have date but no time, return the date
    if date_match:
        return date_match.group(1)
    
    # If no structured pattern found, clean unwanted words but preserve the rest
    # Remove words like "Asystole", "Death", etc. but keep date/time info
    cleaned_result = re.sub(r'\b(asystole|death|expired|deceased)\b', '', cleaned, flags=re.IGNORECASE)
    cleaned_result = re.sub(r'\s+', ' ', cleaned_result).strip()
    
    # If we still have something meaningful, return it
    if cleaned_result and len(cleaned_result) > 3:
        return cleaned_result
    
    # Last resort: return the original cleaned text (without prefix) if it has content
    if cleaned and len(cleaned.strip()) > 3:
        return cleaned.strip()
    
    # Final fallback: return original
    return raw_time


def extract_recovery_information(vectordb: Any, page_doc_list: List[Any]) -> Dict[str, Any]:
    """
    Extract recovery information using semantic search + pattern matching.
    
    Returns:
        Dictionary with recovery_window, location, consent_status
    """
    try:
        # Semantic queries for recovery information
        queries = [
            "recovery window time frame hours days",
            "recovery location facility location",
            "consent status authorization tissue donation"
        ]
        
        # Retrieve relevant chunks
        all_chunks = []
        retriever = vectordb.as_retriever(search_type='similarity', search_kwargs={'k': 10})
        
        for query in queries:
            try:
                chunks = retriever.invoke(query)
                all_chunks.extend(chunks)
            except Exception as e:
                logger.debug(f"Error retrieving chunks for query '{query}': {e}")
                continue
        
        # Deduplicate chunks
        seen = set()
        unique_chunks = []
        for chunk in all_chunks:
            key = (chunk.metadata.get('page'), chunk.page_content[:100])
            if key not in seen:
                seen.add(key)
                unique_chunks.append(chunk)
        
        # Combine text from all chunks
        text = " ".join([chunk.page_content for chunk in unique_chunks])
        
        recovery_info = {
            'recovery_window': None,
            'location': None,
            'consent_status': None
        }
        
        # Pattern: "Recovery Window: 24 hours" or "Window: 24 hours"
        window_patterns = [
            r'recovery\s+window[:\s]+([0-9]+\s*(?:hours?|days?|minutes?))',
            r'window[:\s]+([0-9]+\s*(?:hours?|days?))',
            r'within\s+([0-9]+\s*(?:hours?|days?))',
            r'recovery\s+time[:\s]+([0-9]+\s*(?:hours?|days?))'
        ]
        for pattern in window_patterns:
            match = re.search(pattern, text, re.IGNORECASE)
            if match:
                recovery_info['recovery_window'] = match.group(1).strip()
                break
        
        # Pattern: "Location: [location]" or "Recovery Location: [location]"
        location_patterns = [
            r'recovery\s+location[:\s]+([^\n,]+)',
            r'location[:\s]+([^\n,]+)',
            r'facility[:\s]+([^\n,]+)',
            r'recovery\s+facility[:\s]+([^\n,]+)'
        ]
        for pattern in location_patterns:
            match = re.search(pattern, text, re.IGNORECASE)
            if match:
                location = match.group(1).strip()
                # Clean up common suffixes
                location = re.sub(r'\s*(ICU|ER|ED|OR|floor|room).*$', '', location, flags=re.IGNORECASE)
                recovery_info['location'] = location
                break
        
        # Pattern: "Consent: [status]" or "Consent Status: [status]"
        consent_patterns = [
            r'consent\s+status[:\s]+([^\n,]+)',
            r'consent[:\s]+([^\n,]+)',
            r'authorization[:\s]+([^\n,]+)',
            r'tissue\s+donation\s+consent[:\s]+([^\n,]+)'
        ]
        for pattern in consent_patterns:
            match = re.search(pattern, text, re.IGNORECASE)
            if match:
                consent = match.group(1).strip()
                # Normalize common values
                if re.search(r'yes|obtained|signed|approved', consent, re.IGNORECASE):
                    recovery_info['consent_status'] = 'Obtained'
                elif re.search(r'no|not|declined|refused', consent, re.IGNORECASE):
                    recovery_info['consent_status'] = 'Not Obtained'
                else:
                    recovery_info['consent_status'] = consent
                break
        
        return recovery_info
        
    except Exception as e:
        logger.error(f"Error extracting recovery information: {e}", exc_info=True)
        return {'recovery_window': None, 'location': None, 'consent_status': None}


def extract_terminal_information(vectordb: Any, page_doc_list: List[Any]) -> Dict[str, Any]:
    """
    Extract terminal information using semantic search + pattern matching.
    
    Returns:
        Dictionary with time_of_death, cause_of_death, hypotension, sepsis
    """
    try:
        # Semantic queries for terminal information
        queries = [
            "time of death TOD expired",
            "cause of death COD manner of death",
            "hypotension low blood pressure hypotensive",
            "sepsis infection septicemia septic shock"
        ]
        
        # Retrieve relevant chunks
        all_chunks = []
        retriever = vectordb.as_retriever(search_type='similarity', search_kwargs={'k': 10})
        
        for query in queries:
            try:
                chunks = retriever.invoke(query)
                all_chunks.extend(chunks)
            except Exception as e:
                logger.debug(f"Error retrieving chunks for query '{query}': {e}")
                continue
        
        # Deduplicate chunks
        seen = set()
        unique_chunks = []
        for chunk in all_chunks:
            key = (chunk.metadata.get('page'), chunk.page_content[:100])
            if key not in seen:
                seen.add(key)
                unique_chunks.append(chunk)
        
        # Combine text from all chunks
        text = " ".join([chunk.page_content for chunk in unique_chunks])
        
        terminal_info = {
            'time_of_death': None,
            'cause_of_death': None,
            'hypotension': None,
            'sepsis': None
        }
        
        # Time of death patterns
        tod_patterns = [
            r'time\s+of\s+death[:\s]+([^\n,]+)',
            r'TOD[:\s]+([^\n,]+)',
            r'death\s+time[:\s]+([^\n,]+)',
            r'expired\s+at[:\s]+([^\n,]+)',
            r'date\s+and\s+time\s+of\s+death[:\s]+([^\n,]+)'
        ]
        for pattern in tod_patterns:
            match = re.search(pattern, text, re.IGNORECASE)
            if match:
                raw_time = match.group(1).strip()
                if raw_time:
                    # Clean the extracted time to only include date, time and timezone
                    cleaned_time = clean_time_of_death(raw_time)
                    # Only set if we got a meaningful result with digits (indicating date/time)
                    if cleaned_time and cleaned_time.strip() and re.search(r'\d', cleaned_time):
                        terminal_info['time_of_death'] = cleaned_time.strip()
                        logger.debug(f"Extracted time of death: {terminal_info['time_of_death']} from raw: {raw_time}")
                        break
                    else:
                        logger.debug(f"clean_time_of_death returned invalid result for raw_time: {raw_time}, cleaned: {cleaned_time}")
                        # Continue to try other patterns if this one didn't yield a result
        
        # Cause of death patterns
        cod_patterns = [
            r'cause\s+of\s+death[:\s]+([^\n,]+)',
            r'COD[:\s]+([^\n,]+)',
            r'manner\s+of\s+death[:\s]+([^\n,]+)',
            r'primary\s+cause[:\s]+([^\n,]+)'
        ]
        for pattern in cod_patterns:
            match = re.search(pattern, text, re.IGNORECASE)
            if match:
                terminal_info['cause_of_death'] = match.group(1).strip()
                break
        
        # Hypotension patterns
        if re.search(r'hypotension|low\s+blood\s+pressure|hypotensive', text, re.IGNORECASE):
            # Check for presence indicators
            hypotension_context = re.search(
                r'hypotension[^\n]{0,200}|low\s+blood\s+pressure[^\n]{0,200}',
                text, re.IGNORECASE
            )
            if hypotension_context:
                context_text = hypotension_context.group(0).lower()
                if re.search(r'present|yes|positive|confirmed|noted|observed', context_text):
                    terminal_info['hypotension'] = 'Present'
                elif re.search(r'absent|no|negative|none|not\s+present', context_text):
                    terminal_info['hypotension'] = 'Absent'
                else:
                    terminal_info['hypotension'] = 'Present'  # Default if mentioned
        
        # Sepsis patterns
        if re.search(r'sepsis|septicemia|septic\s+shock', text, re.IGNORECASE):
            # Check for presence indicators
            sepsis_context = re.search(
                r'sepsis[^\n]{0,200}|septicemia[^\n]{0,200}|septic\s+shock[^\n]{0,200}',
                text, re.IGNORECASE
            )
            if sepsis_context:
                context_text = sepsis_context.group(0).lower()
                if re.search(r'present|yes|positive|confirmed|diagnosed|evidence', context_text):
                    terminal_info['sepsis'] = 'Present'
                elif re.search(r'absent|no|negative|none|not\s+present|ruled\s+out', context_text):
                    terminal_info['sepsis'] = 'Absent'
                else:
                    terminal_info['sepsis'] = 'Present'  # Default if mentioned
        
        return terminal_info
        
    except Exception as e:
        logger.error(f"Error extracting terminal information: {e}", exc_info=True)
        return {'time_of_death': None, 'cause_of_death': None, 'hypotension': None, 'sepsis': None}


def detect_document_presence(
    vectordb: Any,
    page_doc_list: List[Any],
    db: Session,
    document_id: int
) -> Dict[str, Any]:
    """
    Detect document presence using semantic search.
    
    Returns:
        Dictionary with document presence data for each document type
    """
    try:
        # Map document types to search queries
        doc_queries = {
            'donor_log_in_information_packet': [
                'donor log in', 'log-in packet', 'ascension number', 'log in information'
            ],
            'donor_information': [
                'donor information', 'donor demographics', 'patient information', 'donor profile'
            ],
            'donor_risk_assessment_interview': [
                'DRAI', 'donor risk assessment', 'risk assessment interview', 'donor risk interview'
            ],
            'medical_records_review_summary': [
                'medical records review', 'MRR summary', 'review summary', 'medical review'
            ],
            'tissue_recovery_information': [
                'tissue recovery', 'recovery information', 'tissues recovered', 'recovery procedures'
            ],
            'plasma_dilution': [
                'plasma dilution', 'dilution factor', 'plasma volume', 'dilution calculation'
            ],
            'authorization_for_tissue_donation': [
                'authorization', 'tissue donation authorization', 'consent form', 'donation authorization'
            ],
            'infectious_disease_testing': [
                'infectious disease', 'serology', 'culture results', 'infectious disease testing'
            ],
            'medical_records': [
                'medical records', 'patient records', 'clinical records', 'medical chart'
            ]
        }
        
        retriever = vectordb.as_retriever(search_type='similarity', search_kwargs={'k': 5})
        document_presence = {}
        
        for doc_type, queries in doc_queries.items():
            found_chunks = []
            
            for query in queries:
                try:
                    chunks = retriever.invoke(query)
                    found_chunks.extend(chunks)
                except Exception as e:
                    logger.debug(f"Error retrieving chunks for document type '{doc_type}', query '{query}': {e}")
                    continue
            
            # Deduplicate
            seen = set()
            unique_chunks = []
            for chunk in found_chunks:
                key = (chunk.metadata.get('page'), chunk.page_content[:50])
                if key not in seen:
                    seen.add(key)
                    unique_chunks.append(chunk)
            
            # Extract pages
            pages = []
            for chunk in unique_chunks[:5]:  # Limit to top 5
                page = chunk.metadata.get('page')
                if page and page not in pages:
                    pages.append(page)
            
            # Also check database for page numbers
            if not pages:
                chunks = db.query(DocumentChunk).filter(
                    DocumentChunk.document_id == document_id,
                    DocumentChunk.page_number.isnot(None)
                ).all()
                
                # Check if any chunk text contains document type keywords
                for chunk in chunks:
                    chunk_text_lower = (chunk.chunk_text or '').lower()
                    if any(keyword.lower() in chunk_text_lower for keyword in queries):
                        if chunk.page_number and chunk.page_number not in pages:
                            pages.append(chunk.page_number)
            
            # Special handling for infectious_disease_testing: also check for actual test results
            is_present = len(unique_chunks) > 0 or len(pages) > 0
            if doc_type == 'infectious_disease_testing' and not is_present:
                # Check if there are actual test results in the database
                test_results = db.query(LaboratoryResult).filter(
                    LaboratoryResult.document_id == document_id
                ).all()
                
                if test_results:
                    # If we have test results, mark as present and extract page numbers from results
                    is_present = True
                    result_pages = []
                    for result in test_results:
                        if result.source_page and result.source_page not in result_pages:
                            result_pages.append(result.source_page)
                    if result_pages:
                        pages.extend(result_pages)
                    logger.info(f"Found {len(test_results)} test results for document {document_id}, marking infectious_disease_testing as present")
            
            document_presence[doc_type] = {
                'present': is_present,
                'pages': [{'document_id': document_id, 'page': p} for p in sorted(set(pages))],
                'summary': {},
                'extracted_data': {},
                'confidence': min(len(unique_chunks) * 10.0, 100.0) if unique_chunks else 0.0
            }
        
        return document_presence
        
    except Exception as e:
        logger.error(f"Error detecting document presence: {e}", exc_info=True)
        return {}


def extract_simple_medical_records(vectordb: Any, page_doc_list: List[Any]) -> Optional[Dict[str, Any]]:
    """
    Extract simple medical records data using semantic search + pattern matching.
    Only extracts if data is structured (lists, bullet points, etc.)
    
    Returns:
        Dictionary with Diagnoses, Procedures, Medications if structured, None otherwise
    """
    try:
        # Semantic queries
        queries = [
            "diagnoses diagnosis medical conditions",
            "procedures surgeries operations",
            "medications drugs prescriptions"
        ]
        
        # Retrieve relevant chunks
        all_chunks = []
        retriever = vectordb.as_retriever(search_type='similarity', search_kwargs={'k': 10})
        
        for query in queries:
            try:
                chunks = retriever.invoke(query)
                all_chunks.extend(chunks)
            except Exception as e:
                logger.debug(f"Error retrieving chunks for query '{query}': {e}")
                continue
        
        # Deduplicate
        seen = set()
        unique_chunks = []
        for chunk in all_chunks:
            key = (chunk.metadata.get('page'), chunk.page_content[:100])
            if key not in seen:
                seen.add(key)
                unique_chunks.append(chunk)
        
        if not unique_chunks:
            return None
        
        # Combine text
        text = " ".join([chunk.page_content for chunk in unique_chunks])
        
        medical_records = {
            'Diagnoses': [],
            'Procedures': [],
            'Medications': []
        }
        
        # Extract diagnoses (look for bullet points, numbered lists, or "Diagnosis:" patterns)
        diagnosis_patterns = [
            r'diagnos(?:is|es)[:\s]+(?:.*?\n)?(?:[-•*]\s*)?([^\n]+)',
            r'diagnos(?:is|es)[:\s]+(?:.*?\n)?(?:[0-9]+\.\s*)?([^\n]+)'
        ]
        for pattern in diagnosis_patterns:
            matches = re.finditer(pattern, text, re.IGNORECASE | re.MULTILINE)
            for match in matches:
                diagnosis = match.group(1).strip()
                if diagnosis and len(diagnosis) > 3 and diagnosis not in medical_records['Diagnoses']:
                    medical_records['Diagnoses'].append(diagnosis)
        
        # Extract procedures
        procedure_patterns = [
            r'procedures?[:\s]+(?:.*?\n)?(?:[-•*]\s*)?([^\n]+)',
            r'procedures?[:\s]+(?:.*?\n)?(?:[0-9]+\.\s*)?([^\n]+)',
            r'surger(?:y|ies)[:\s]+(?:.*?\n)?(?:[-•*]\s*)?([^\n]+)'
        ]
        for pattern in procedure_patterns:
            matches = re.finditer(pattern, text, re.IGNORECASE | re.MULTILINE)
            for match in matches:
                procedure = match.group(1).strip()
                if procedure and len(procedure) > 3 and procedure not in medical_records['Procedures']:
                    medical_records['Procedures'].append(procedure)
        
        # Extract medications
        medication_patterns = [
            r'medications?[:\s]+(?:.*?\n)?(?:[-•*]\s*)?([^\n]+)',
            r'medications?[:\s]+(?:.*?\n)?(?:[0-9]+\.\s*)?([^\n]+)',
            r'drugs?[:\s]+(?:.*?\n)?(?:[-•*]\s*)?([^\n]+)'
        ]
        for pattern in medication_patterns:
            matches = re.finditer(pattern, text, re.IGNORECASE | re.MULTILINE)
            for match in matches:
                medication = match.group(1).strip()
                if medication and len(medication) > 3 and medication not in medical_records['Medications']:
                    medical_records['Medications'].append(medication)
        
        # Only return if we found at least one item
        if any(medical_records.values()):
            return {
                'extracted_data': medical_records,
                'summary': {
                    'Diagnoses': ', '.join(medical_records['Diagnoses'][:5]) if medical_records['Diagnoses'] else '',
                    'Procedures': ', '.join(medical_records['Procedures'][:3]) if medical_records['Procedures'] else '',
                    'Medications': ', '.join(medical_records['Medications'][:3]) if medical_records['Medications'] else ''
                }
            }
        
        return None
        
    except Exception as e:
        logger.error(f"Error extracting simple medical records: {e}", exc_info=True)
        return None


def extract_critical_lab_values(vectordb: Any, page_doc_list: List[Any]) -> Dict[str, Any]:
    """
    Extract critical lab values using semantic search + pattern matching.
    
    Returns:
        Dictionary of critical lab values with reference ranges
    """
    try:
        # Semantic queries
        queries = [
            "critical lab values abnormal results",
            "reference range normal values",
            "abnormal laboratory results critical values"
        ]
        
        # Retrieve relevant chunks
        all_chunks = []
        retriever = vectordb.as_retriever(search_type='similarity', search_kwargs={'k': 10})
        
        for query in queries:
            try:
                chunks = retriever.invoke(query)
                all_chunks.extend(chunks)
            except Exception as e:
                logger.debug(f"Error retrieving chunks for query '{query}': {e}")
                continue
        
        # Deduplicate
        seen = set()
        unique_chunks = []
        for chunk in all_chunks:
            key = (chunk.metadata.get('page'), chunk.page_content[:100])
            if key not in seen:
                seen.add(key)
                unique_chunks.append(chunk)
        
        if not unique_chunks:
            return {}
        
        # Combine text
        text = " ".join([chunk.page_content for chunk in unique_chunks])
        
        critical_values = {}
        
        # Pattern: "Test Name: value (reference range)"
        lab_pattern = r'([A-Za-z\s]+(?:glucose|creatinine|BUN|sodium|potassium|hemoglobin|hematocrit|WBC|platelet))[:\s]+([0-9.]+)\s*(?:\(([^)]+)\)|\[([^\]]+)\]|reference[:\s]+([^\n,]+))?'
        
        matches = re.finditer(lab_pattern, text, re.IGNORECASE)
        for match in matches:
            test_name = match.group(1).strip()
            value = match.group(2).strip()
            ref_range = match.group(3) or match.group(4) or match.group(5) or None
            
            if test_name and value:
                critical_values[test_name] = {
                    'value': value,
                    'reference_range': ref_range.strip() if ref_range else None
                }
        
        return critical_values
        
    except Exception as e:
        logger.error(f"Error extracting critical lab values: {e}", exc_info=True)
        return {}

