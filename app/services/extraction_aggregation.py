"""
Service for aggregating extraction results from multiple documents per donor.
Merges results and stores in DonorExtraction table.
"""
import json
import logging
from typing import Dict, Any, Optional
from datetime import datetime
from sqlalchemy.orm import Session
from app.models.document import Document, DocumentStatus
from app.models.donor_extraction import DonorExtraction
from app.models.culture_result import CultureResult
from app.models.serology_result import SerologyResult
from app.models.topic_result import TopicResult
from app.models.component_result import ComponentResult
from app.services.processing.utils.merge_helpers import (
    merge_culture_results,
    merge_serology_results,
    merge_topics_results,
    merge_components_results
)
from app.services.processing.result_parser import result_parser
from app.services.critical_findings_service import critical_findings_service
from app.services.medical_findings_service import medical_findings_service
from app.services.tissue_eligibility_service import tissue_eligibility_service
from app.services.information_formatter_service import information_formatter_service

logger = logging.getLogger(__name__)


def _get_llm_instance() -> Optional[Any]:
    """
    Get LLM instance lazily if available.
    Returns None if LLM is not available or initialization fails.
    """
    try:
        from app.services.processing.utils.llm_config import llm_setup
        llm, _ = llm_setup()
        return llm
    except Exception as e:
        logger.debug(f"LLM not available for summary deduplication: {str(e)}")
        return None


class ExtractionAggregationService:
    """Service for aggregating extraction results per donor."""
    
    @staticmethod
    async def aggregate_donor_results(donor_id: int, db: Session) -> bool:
        """
        Aggregate extraction results from all completed documents for a donor.
        
        Args:
            donor_id: ID of the donor
            db: Database session
            
        Returns:
            True if successful, False otherwise
        """
        try:
            # Get all completed documents for this donor
            documents = db.query(Document).filter(
                Document.donor_id == donor_id,
                Document.status == DocumentStatus.COMPLETED
            ).all()
            
            if not documents:
                logger.info(f"No completed documents found for donor {donor_id}")
                return False
            
            logger.info(f"Aggregating results from {len(documents)} documents for donor {donor_id}")
            
            # Collect results from all documents
            all_culture_results = []
            all_serology_results = []
            all_topic_results = []
            all_component_results = []
            
            for document in documents:
                # Get culture results
                culture_data = result_parser.get_culture_results_for_document(document.id, db)
                # Always add culture_data if it exists (even if result is empty list)
                # This ensures we capture the structure even when no results found
                if culture_data:
                    # Check if result exists and has items (not just empty list)
                    if culture_data.get('result') and len(culture_data.get('result', [])) > 0:
                        all_culture_results.append(culture_data)
                    else:
                        # Log when no culture results found for this document
                        logger.debug(f"No culture results found for document {document.id}")
                
                # Get serology results
                serology_data = result_parser.get_serology_results_for_document(document.id, db)
                # Always add serology_data if it exists (even if result is empty dict)
                # This ensures we capture the structure even when no results found
                if serology_data:
                    # Check if result exists and has items (not just empty dict)
                    if serology_data.get('result') and len(serology_data.get('result', {})) > 0:
                        all_serology_results.append(serology_data)
                    else:
                        # Log when no serology results found for this document
                        logger.debug(f"No serology results found for document {document.id}")
                
                # Get topic results
                topic_data = result_parser.get_topic_results_for_document(document.id, db)
                if topic_data:
                    all_topic_results.append(topic_data)
                
                # Get component results
                component_data = result_parser.get_component_results_for_document(document.id, db)
                if component_data:
                    all_component_results.append(component_data)
            
            # Get LLM instance for summary deduplication (optional, will fall back if unavailable)
            llm_instance = _get_llm_instance()
            
            # Merge results
            merged_culture = merge_culture_results(all_culture_results) if all_culture_results else {}
            merged_serology = merge_serology_results(all_serology_results) if all_serology_results else {}
            merged_topics = merge_topics_results(all_topic_results) if all_topic_results else {}
            merged_components = merge_components_results(all_component_results, llm=llm_instance) if all_component_results else {}
            
            # Log merge results for debugging
            logger.info(f"Merge results for donor {donor_id}: "
                       f"culture_docs={len(all_culture_results)}, serology_docs={len(all_serology_results)}, "
                       f"culture_merged={bool(merged_culture)}, serology_merged={bool(merged_serology)}")
            if merged_serology:
                logger.debug(f"Serology results: {merged_serology}")
            else:
                logger.warning(f"No serology results merged for donor {donor_id}. "
                             f"Checked {len(documents)} documents, found {len(all_serology_results)} with serology data")
            if merged_culture:
                logger.debug(f"Culture results: {merged_culture}")
            else:
                logger.warning(f"No culture results merged for donor {donor_id}. "
                             f"Checked {len(documents)} documents, found {len(all_culture_results)} with culture data")
            
            # Build ExtractionDataResponse structure
            extraction_data = {
                "donor_id": str(donor_id),  # Will be updated with unique_donor_id
                "case_id": f"{donor_id}81",  # Will be updated
                "processing_timestamp": datetime.now().isoformat(),
                "processing_duration_seconds": 0,  # Can be calculated if needed
                "extracted_data": {
                    # This will be populated based on component results
                    # Structure matches frontend ExtractionDataResponse
                },
                "conditional_documents": merged_components.get("conditional_components", {}),
                "validation": None,  # Can be calculated
                "compliance_status": None,  # Can be calculated
                "document_summary": {
                    "total_documents_processed": len(documents),
                    "total_pages_processed": 0,  # Can be calculated
                    "extraction_methods_used": ["culture", "serology", "topics", "components"]
                }
            }
            
            # Get donor to update donor_id and case_id
            from app.models.donor import Donor
            donor = db.query(Donor).filter(Donor.id == donor_id).first()
            if donor:
                extraction_data["donor_id"] = donor.unique_donor_id
                extraction_data["case_id"] = f"{donor.unique_donor_id}81"
            
            # Build extracted_data from components
            # Map component results to the expected structure
            initial_components = merged_components.get("initial_components", {})
            for component_name, component_info in initial_components.items():
                # Map component names to extraction data keys
                component_key = component_name.lower().replace(' ', '_').replace('-', '_')
                extraction_data["extracted_data"][component_key] = component_info
                
                # Extract serology results from infectious_disease_testing component if serology_results table is empty
                if component_key == "infectious_disease_testing" and component_info.get("present"):
                    component_extracted_data = component_info.get("extracted_data", {})
                    if component_extracted_data:
                        # Check if we have serology results in the component data
                        # The extracted_data should contain test names as keys with results as values
                        serology_from_component = {}
                        citations_from_component = component_info.get("pages", [])
                        
                        # Common serology test name patterns
                        serology_test_patterns = [
                            "hiv", "hbv", "hcv", "htlv", "syphilis", "west nile", "zika",
                            "sars-cov", "covid", "legionella", "hepatitis", "hbsag", 
                            "anti-hbc", "anti-hcv", "anti-hiv", "pcr", "antigen", "antibody"
                        ]
                        
                        # Import parsing function from serology module
                        from app.services.processing.serology import parse_test_name_and_method
                        
                        for key, value in component_extracted_data.items():
                            if value:  # Skip empty values
                                key_lower = key.lower()
                                # Check if key looks like a serology test name
                                if any(pattern in key_lower for pattern in serology_test_patterns):
                                    # Parse test name to extract clean name and method
                                    clean_test_name, test_method = parse_test_name_and_method(key)
                                    # Store with clean test name (method is stored separately in DB, but for component extraction we just use clean name)
                                    serology_from_component[clean_test_name] = str(value)
                        
                        # If we found serology results in component and don't have any from database, use component data
                        if serology_from_component and not merged_serology.get("result"):
                            logger.info(f"Extracted {len(serology_from_component)} serology results from infectious_disease_testing component for donor {donor_id}")
                            # Merge citations properly (citations are dicts, need to deduplicate by tuple)
                            all_citations = merged_serology.get("citations", []) + citations_from_component
                            unique_citations = []
                            seen = set()
                            for citation in all_citations:
                                if isinstance(citation, dict) and "document_id" in citation and "page" in citation:
                                    key = (citation["document_id"], citation["page"])
                                    if key not in seen:
                                        seen.add(key)
                                        unique_citations.append(citation)
                                else:
                                    # Handle non-standard citation formats
                                    if citation not in seen:
                                        seen.add(citation)
                                        unique_citations.append(citation)
                            # Sort by document_id, then page
                            unique_citations.sort(key=lambda x: (x.get("document_id", 0), x.get("page", 0)) if isinstance(x, dict) else (0, 0))
                            
                            # Merge with existing (empty) serology results
                            merged_serology = {
                                "result": serology_from_component,
                                "citations": unique_citations
                            }
                        elif serology_from_component and merged_serology.get("result"):
                            # Merge component data with database results (database takes precedence)
                            existing_results = merged_serology.get("result", {})
                            for test_name, result_value in serology_from_component.items():
                                if test_name not in existing_results:
                                    existing_results[test_name] = result_value
                            merged_serology["result"] = existing_results
                            
                            # Merge citations properly (citations are dicts, need to deduplicate by tuple)
                            all_citations = merged_serology.get("citations", []) + citations_from_component
                            unique_citations = []
                            seen = set()
                            for citation in all_citations:
                                if isinstance(citation, dict) and "document_id" in citation and "page" in citation:
                                    key = (citation["document_id"], citation["page"])
                                    if key not in seen:
                                        seen.add(key)
                                        unique_citations.append(citation)
                                else:
                                    # Handle non-standard citation formats
                                    if citation not in seen:
                                        seen.add(citation)
                                        unique_citations.append(citation)
                            # Sort by document_id, then page
                            unique_citations.sort(key=lambda x: (x.get("document_id", 0), x.get("page", 0)) if isinstance(x, dict) else (0, 0))
                            merged_serology["citations"] = unique_citations
                
                # Extract culture results from infectious_disease_testing component if culture_results table is empty
                if component_key == "infectious_disease_testing" and component_info.get("present"):
                    component_extracted_data = component_info.get("extracted_data", {})
                    if component_extracted_data:
                        # Check if we have culture results in the component data
                        # Look for Test_Result, Test_Method, Specimen_Type, Specimen_Date_Time patterns
                        culture_from_component = []
                        citations_from_component = component_info.get("pages", [])
                        
                        # Culture test patterns
                        culture_test_patterns = [
                            "test_result", "test_method", "specimen_type", "specimen_date",
                            "blood.*culture", "urine.*culture", "sputum.*culture", "stool.*culture"
                        ]
                        
                        # Look for test result objects (Test_Result, Test_Result_1, etc.)
                        test_result_keys = [key for key in component_extracted_data.keys() 
                                          if key.lower().startswith('test_result') and component_extracted_data[key]]
                        
                        for test_key in test_result_keys:
                            # Get the test result value
                            test_result = component_extracted_data.get(test_key)
                            if not test_result:
                                continue
                            
                            # Extract related fields
                            # Try to find corresponding Test_Method, Specimen_Type, Specimen_Date_Time
                            key_index = test_key.replace('Test_Result', '').replace('test_result', '').strip('_')
                            method_key = f"Test_Method{key_index}" if key_index else "Test_Method"
                            specimen_type_key = f"Specimen_Type{key_index}" if key_index else "Specimen_Type"
                            specimen_date_key = f"Specimen_Date_Time{key_index}" if key_index else "Specimen_Date_Time"
                            comments_key = f"Comments{key_index}" if key_index else "Comments"
                            
                            # Also try with underscores and spaces
                            method_key_alt = method_key.replace('_', ' ') if '_' in method_key else method_key.replace(' ', '_')
                            specimen_type_key_alt = specimen_type_key.replace('_', ' ') if '_' in specimen_type_key else specimen_type_key.replace(' ', '_')
                            specimen_date_key_alt = specimen_date_key.replace('_', ' ') if '_' in specimen_date_key else specimen_date_key.replace(' ', '_')
                            comments_key_alt = comments_key.replace('_', ' ') if '_' in comments_key else comments_key.replace(' ', '_')
                            
                            test_method = (component_extracted_data.get(method_key) or 
                                         component_extracted_data.get(method_key_alt) or 
                                         component_extracted_data.get(f"Test Method{key_index}" if key_index else "Test Method") or
                                         "")
                            specimen_type = (component_extracted_data.get(specimen_type_key) or 
                                           component_extracted_data.get(specimen_type_key_alt) or
                                           component_extracted_data.get(f"Specimen Type{key_index}" if key_index else "Specimen Type") or
                                           "")
                            specimen_date = (component_extracted_data.get(specimen_date_key) or 
                                           component_extracted_data.get(specimen_date_key_alt) or
                                           component_extracted_data.get(f"Specimen Date-Time{key_index}" if key_index else "Specimen Date-Time") or
                                           component_extracted_data.get(f"Specimen Date{key_index}" if key_index else "Specimen Date") or
                                           "")
                            comments = (component_extracted_data.get(comments_key) or 
                                      component_extracted_data.get(comments_key_alt) or
                                      component_extracted_data.get(f"Comment{key_index}" if key_index else "Comment") or
                                      "")
                            
                            # Determine test name from specimen type or method
                            test_name = ""
                            if specimen_type:
                                if "blood" in specimen_type.lower():
                                    test_name = "Blood Culture"
                                elif "urine" in specimen_type.lower():
                                    test_name = "Urine Culture"
                                elif "sputum" in specimen_type.lower():
                                    test_name = "Sputum Culture"
                                elif "stool" in specimen_type.lower():
                                    test_name = "Stool Culture"
                                else:
                                    test_name = f"{specimen_type} Culture" if specimen_type else "Culture"
                            elif test_method:
                                test_name = test_method if "culture" in test_method.lower() else f"{test_method} Culture"
                            else:
                                test_name = "Culture"
                            
                            culture_from_component.append({
                                "test_name": test_name,
                                "test_method": str(test_method) if test_method else None,
                                "specimen_type": str(specimen_type) if specimen_type else None,
                                "specimen_date": str(specimen_date) if specimen_date else None,
                                "result": str(test_result),
                                "comments": str(comments) if comments else None
                            })
                        
                        # If we found culture results in component and don't have any from database, use component data
                        if culture_from_component and not merged_culture.get("result"):
                            logger.info(f"Extracted {len(culture_from_component)} culture results from infectious_disease_testing component for donor {donor_id}")
                            # Merge citations properly
                            all_citations = merged_culture.get("citations", []) + citations_from_component
                            unique_citations = []
                            seen = set()
                            for citation in all_citations:
                                if isinstance(citation, dict) and "document_id" in citation and "page" in citation:
                                    key = (citation["document_id"], citation["page"])
                                    if key not in seen:
                                        seen.add(key)
                                        unique_citations.append(citation)
                                else:
                                    if citation not in seen:
                                        seen.add(citation)
                                        unique_citations.append(citation)
                            # Sort by document_id, then page
                            unique_citations.sort(key=lambda x: (x.get("document_id", 0), x.get("page", 0)) if isinstance(x, dict) else (0, 0))
                            
                            # Merge with existing (empty) culture results
                            merged_culture = {
                                "result": culture_from_component,
                                "citations": unique_citations
                            }
                        elif culture_from_component and merged_culture.get("result"):
                            # Merge component data with database results
                            existing_results = merged_culture.get("result", [])
                            # Add new results that don't already exist
                            existing_test_names = {r.get("test_name") for r in existing_results if isinstance(r, dict) and r.get("test_name")}
                            for culture_item in culture_from_component:
                                if culture_item.get("test_name") not in existing_test_names:
                                    existing_results.append(culture_item)
                            merged_culture["result"] = existing_results
                            
                            # Merge citations properly
                            all_citations = merged_culture.get("citations", []) + citations_from_component
                            unique_citations = []
                            seen = set()
                            for citation in all_citations:
                                if isinstance(citation, dict) and "document_id" in citation and "page" in citation:
                                    key = (citation["document_id"], citation["page"])
                                    if key not in seen:
                                        seen.add(key)
                                        unique_citations.append(citation)
                                else:
                                    if citation not in seen:
                                        seen.add(citation)
                                        unique_citations.append(citation)
                            # Sort by document_id, then page
                            unique_citations.sort(key=lambda x: (x.get("document_id", 0), x.get("page", 0)) if isinstance(x, dict) else (0, 0))
                            merged_culture["citations"] = unique_citations
            
            # Add culture and serology results to extraction data
            # Always include them, even if empty, so frontend knows the structure
            # Merge functions now return proper structure even when empty, but ensure we always have the fields
            if not merged_culture or not isinstance(merged_culture, dict) or "result" not in merged_culture:
                merged_culture = {"result": [], "citations": []}
            if not merged_serology or not isinstance(merged_serology, dict) or "result" not in merged_serology:
                merged_serology = {"result": {}, "citations": []}
            
            extraction_data["culture_results"] = merged_culture
            extraction_data["serology_results"] = merged_serology
            
            # Detect critical findings
            critical_findings = critical_findings_service.detect_critical_findings(donor_id, db)
            
            # Generate key medical findings summary
            key_medical_findings = medical_findings_service.generate_medical_findings_summary(
                extraction_data["extracted_data"]
            )
            extraction_data["key_medical_findings"] = key_medical_findings
            
            # Analyze tissue eligibility using LLM
            donor_age = None
            if donor:
                donor_age = donor.age
            # Use existing LLM instance if available (from summary deduplication)
            tissue_eligibility = tissue_eligibility_service.analyze_tissue_eligibility(
                extraction_data["extracted_data"],
                donor_age,
                llm=llm_instance  # Reuse LLM instance from line 115
            )
            extraction_data["tissue_eligibility"] = tissue_eligibility
            
            # Format recovery information
            recovery_info = information_formatter_service.format_recovery_information(
                extraction_data["extracted_data"]
            )
            extraction_data["recovery_information"] = recovery_info
            
            # Format terminal information
            terminal_info = information_formatter_service.format_terminal_information(
                extraction_data["extracted_data"],
                merged_topics
            )
            extraction_data["terminal_information"] = terminal_info
            
            # Extract critical lab values
            critical_lab_values = information_formatter_service.extract_critical_lab_values(
                extraction_data["extracted_data"]
            )
            extraction_data["critical_lab_values"] = critical_lab_values
            
            # Build validation object with critical findings
            validation = {
                "critical_findings": critical_findings,
                "has_critical_findings": len(critical_findings) > 0,
                "automatic_rejection": any(f.get("automaticRejection", False) for f in critical_findings)
            }
            extraction_data["validation"] = validation
            
            # Store or update DonorExtraction
            donor_extraction = db.query(DonorExtraction).filter(
                DonorExtraction.donor_id == donor_id
            ).first()
            
            if donor_extraction and donor_extraction.extraction_data:
                # Merge with existing data instead of replacing
                existing_data = donor_extraction.extraction_data
                logger.info(f"Merging new extraction data with existing data for donor {donor_id}")
                
                # Helper to merge pages that may be ints or citation dicts
                def _merge_pages_list(existing_pages_raw, new_pages_raw):
                    """
                    Merge pages from existing/new components.
                    
                    Pages can be:
                    - simple integers (legacy)
                    - citation dicts: {"page": int, "document_id": int, ...}
                    
                    We preserve the original objects but deduplicate using a
                    normalized key so we don't rely on them being hashable.
                    """
                    merged_pages: list[Any] = []
                    seen_keys: set[Any] = set()
                    
                    for p in list(existing_pages_raw or []) + list(new_pages_raw or []):
                        # Build a key that is hashable
                        if isinstance(p, dict):
                            key = (p.get("page"), p.get("document_id"), p.get("source_document"))  # type: ignore[assignment]
                        else:
                            key = p
                        
                        if key in seen_keys:
                            continue
                        seen_keys.add(key)
                        merged_pages.append(p)
                    
                    return merged_pages
                
                # Merge extracted_data components
                existing_extracted_data = existing_data.get("extracted_data", {})
                new_extracted_data = extraction_data.get("extracted_data", {})
                
                # For each component in new data, merge with existing if present
                merged_extracted_data = existing_extracted_data.copy()
                for component_key, new_component in new_extracted_data.items():
                    if component_key in merged_extracted_data:
                        # Component exists in both - merge them
                        existing_component = merged_extracted_data[component_key]
                        
                        # Merge pages (support both ints and citation dicts)
                        merged_pages = _merge_pages_list(
                            existing_component.get('pages', []),
                            new_component.get('pages', [])
                        )
                        
                        # Get confidence scores
                        existing_confidence = existing_component.get('confidence', 0.0) or 0.0
                        new_confidence = new_component.get('confidence', 0.0) or 0.0
                        
                        # Use higher confidence as base
                        if new_confidence > existing_confidence:
                            base_component = new_component.copy()
                            base_confidence = new_confidence
                            merge_component = existing_component
                            merge_confidence = existing_confidence
                        else:
                            base_component = existing_component.copy()
                            base_confidence = existing_confidence
                            merge_component = new_component
                            merge_confidence = new_confidence
                        
                        # Merge extracted_data
                        from app.services.processing.utils.merge_helpers import _merge_extracted_data, _merge_summaries
                        base_component['extracted_data'] = _merge_extracted_data(
                            base_component.get('extracted_data', {}),
                            merge_component.get('extracted_data', {}),
                            base_confidence,
                            merge_confidence
                        )
                        
                        # Merge summaries
                        base_component['summary'] = _merge_summaries(
                            base_component.get('summary'),
                            merge_component.get('summary'),
                            base_confidence,
                            merge_confidence,
                            llm=llm_instance,
                            component_name=component_key
                        )
                        
                        # Update pages and present flag
                        base_component['pages'] = merged_pages
                        base_component['present'] = base_component.get('present', False) or merge_component.get('present', False)
                        base_component['confidence'] = max(base_confidence, merge_confidence)
                        
                        merged_extracted_data[component_key] = base_component
                    else:
                        # New component, add it
                        merged_extracted_data[component_key] = new_component
                
                # Merge other fields - prefer newer but preserve existing if new is incomplete
                merged_data = existing_data.copy()
                merged_data["extracted_data"] = merged_extracted_data
                
                # Merge culture_results and serology_results (already merged from all documents)
                if extraction_data.get("culture_results"):
                    merged_data["culture_results"] = extraction_data["culture_results"]
                if extraction_data.get("serology_results"):
                    merged_data["serology_results"] = extraction_data["serology_results"]
                
                # Merge conditional_documents
                existing_conditional = existing_data.get("conditional_documents", {})
                new_conditional = extraction_data.get("conditional_documents", {})
                merged_conditional = existing_conditional.copy()
                merged_conditional.update(new_conditional)
                merged_data["conditional_documents"] = merged_conditional
                
                # Update computed fields (always recalculate)
                merged_data["validation"] = extraction_data.get("validation")
                merged_data["key_medical_findings"] = extraction_data.get("key_medical_findings")
                merged_data["tissue_eligibility"] = extraction_data.get("tissue_eligibility")
                merged_data["recovery_information"] = extraction_data.get("recovery_information")
                merged_data["terminal_information"] = extraction_data.get("terminal_information")
                merged_data["critical_lab_values"] = extraction_data.get("critical_lab_values")
                
                # Update metadata
                merged_data["processing_timestamp"] = extraction_data.get("processing_timestamp")
                merged_data["document_summary"] = extraction_data.get("document_summary")
                
                # Update DonorExtraction with merged data
                donor_extraction.extraction_data = merged_data
                donor_extraction.documents_processed = len(documents)
                donor_extraction.processing_status = "complete"
                donor_extraction.last_updated_at = datetime.now()
                logger.info(f"Successfully merged extraction data for donor {donor_id}")
            else:
                # Create new or update without existing data
                if donor_extraction:
                    donor_extraction.extraction_data = extraction_data
                    donor_extraction.documents_processed = len(documents)
                    donor_extraction.processing_status = "complete"
                    donor_extraction.last_updated_at = datetime.now()
                else:
                    donor_extraction = DonorExtraction(
                        donor_id=donor_id,
                        extraction_data=extraction_data,
                        documents_processed=len(documents),
                        processing_status="complete"
                    )
                    db.add(donor_extraction)
            
            db.commit()
            logger.info(f"Successfully aggregated results for donor {donor_id}")
            
            # Trigger vector conversion as fire-and-forget task (non-blocking)
            # Vector conversion is only used for similarity search and is not critical for main processing
            import asyncio
            from app.services.vector_conversion import vector_conversion_service
            
            async def run_vector_conversion_safely():
                """Run vector conversion with error handling to prevent blocking main flow."""
                try:
                    logger.info(f"Starting vector conversion for donor {donor_id} (background task)")
                    # Create a new database session for the background task
                    from app.database.database import SessionLocal
                    background_db = SessionLocal()
                    try:
                        success = await vector_conversion_service.convert_and_store_donor_vectors(donor_id, background_db)
                        if success:
                            logger.info(f"Successfully completed vector conversion for donor {donor_id}")
                        else:
                            logger.warning(f"Vector conversion returned False for donor {donor_id}")
                    finally:
                        background_db.close()
                except Exception as e:
                    # Log error but don't raise - vector conversion failure shouldn't affect main processing
                    logger.error(f"Error in background vector conversion for donor {donor_id}: {e}", exc_info=True)
            
            # Create background task - don't await it
            # Store task reference to prevent "Task exception was never retrieved" warnings
            task = asyncio.create_task(run_vector_conversion_safely())
            # Add done callback to log any unhandled exceptions (shouldn't happen due to try-except, but safety net)
            def log_task_exception(task):
                try:
                    task.result()  # This will raise if task had an exception
                except Exception as e:
                    logger.error(f"Unhandled exception in vector conversion task for donor {donor_id}: {e}", exc_info=True)
            task.add_done_callback(log_task_exception)
            logger.debug(f"Vector conversion task created for donor {donor_id} (running in background)")
            
            return True
            
        except Exception as e:
            logger.error(f"Error aggregating results for donor {donor_id}: {e}", exc_info=True)
            db.rollback()
            return False


# Global instance
extraction_aggregation_service = ExtractionAggregationService()

