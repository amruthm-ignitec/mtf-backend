"""
Conditional documents service.
Determines conditional document status based on criteria evaluations and extracts test results.
"""
import logging
from typing import Dict, Any, List, Optional
from sqlalchemy.orm import Session
from sqlalchemy import or_
from app.models.criteria_evaluation import CriteriaEvaluation
from app.models.laboratory_result import LaboratoryResult, TestType
from app.models.document import Document, DocumentStatus

logger = logging.getLogger(__name__)


def determine_conditional_documents_from_criteria(
    donor_id: int,
    db: Session
) -> Dict[str, Any]:
    """
    Determine conditional documents status based on criteria evaluations.
    
    Returns:
        Dictionary with conditional document status for bioburden_results, toxicology_report, autopsy_report, skin_dermal_cultures
    """
    try:
        conditional_documents = {}
        
        # Get all documents for this donor
        documents = db.query(Document).filter(
            Document.donor_id == donor_id,
            Document.status == DocumentStatus.COMPLETED
        ).all()
        
        if not documents:
            return {}
        
        document_ids = [doc.id for doc in documents]
        
        # 1. Toxicology Report
        toxicology_eval = db.query(CriteriaEvaluation).filter(
            CriteriaEvaluation.donor_id == donor_id,
            CriteriaEvaluation.criterion_name == 'Toxicology'
        ).first()
        
        toxicology_performed = False
        if toxicology_eval and toxicology_eval.extracted_data:
            toxicology_performed = toxicology_eval.extracted_data.get('toxicology_performed', False)
        
        if toxicology_performed:
            # Extract toxicology test results
            toxicology_results = None
            # Try to find toxicology-related lab results or extract from documents
            # For now, we'll set basic structure
            conditional_documents['toxicology_report'] = {
                'conditional_status': 'CONDITION MET',
                'condition_required': 'Toxicology Performed',
                'testing_performed': True,
                'test_results': toxicology_results,
                'source_document': None,
                'source_pages': []
            }
        else:
            conditional_documents['toxicology_report'] = {
                'conditional_status': 'CONDITION NOT MET',
                'condition_required': 'Toxicology Performed',
                'testing_performed': False,
                'test_results': None,
                'source_document': None,
                'source_pages': []
            }
        
        # 2. Autopsy Report
        autopsy_eval = db.query(CriteriaEvaluation).filter(
            CriteriaEvaluation.donor_id == donor_id,
            CriteriaEvaluation.criterion_name == 'Autopsy'
        ).first()
        
        autopsy_performed = False
        autopsy_type = None
        if autopsy_eval and autopsy_eval.extracted_data:
            autopsy_performed = autopsy_eval.extracted_data.get('autopsy_performed', False)
            autopsy_type = autopsy_eval.extracted_data.get('autopsy_type')
        
        if autopsy_performed:
            conditional_documents['autopsy_report'] = {
                'conditional_status': 'CONDITION MET',
                'condition_required': 'Autopsy Performed',
                'testing_performed': True,
                'report_details': {
                    'autopsy_type': autopsy_type,
                    'autopsy_performed': True
                },
                'source_document': None,
                'source_pages': []
            }
        else:
            conditional_documents['autopsy_report'] = {
                'conditional_status': 'CONDITION NOT MET',
                'condition_required': 'Autopsy Performed',
                'testing_performed': False,
                'report_details': None,
                'source_document': None,
                'source_pages': []
            }
        
        # 3. Bioburden Results
        # Check if fresh tissue was processed (this might be in criteria or we check for bioburden tests)
        bioburden_tests = db.query(LaboratoryResult).filter(
            LaboratoryResult.document_id.in_(document_ids),
            LaboratoryResult.test_type == TestType.CULTURE,
            LaboratoryResult.test_name.ilike('%bioburden%')
        ).all()
        
        # Also check for processing-related culture tests that might indicate fresh tissue processing
        processing_tests = db.query(LaboratoryResult).filter(
            LaboratoryResult.document_id.in_(document_ids),
            LaboratoryResult.test_type == TestType.CULTURE,
            or_(
                LaboratoryResult.test_name.ilike('%processing%'),
                LaboratoryResult.test_name.ilike('%transport%'),
                LaboratoryResult.test_name.ilike('%pre-processing%'),
                LaboratoryResult.test_name.ilike('%post-processing%')
            )
        ).all()
        
        fresh_tissue_processed = len(bioburden_tests) > 0 or len(processing_tests) > 0
        
        if fresh_tissue_processed:
            # Extract bioburden test results
            bioburden_result = None
            if bioburden_tests:
                # Use the first bioburden test result
                test = bioburden_tests[0]
                bioburden_result = {
                    'test_method': test.test_method or 'Bioburden Test',
                    'result': test.result,
                    'specimen_type': test.specimen_type,
                    'specimen_date': test.specimen_date,
                    'comments': test.comments
                }
            
            conditional_documents['bioburden_results'] = {
                'conditional_status': 'CONDITION MET',
                'condition_required': 'Fresh Tissue Processed',
                'bioburden_testing_performed': len(bioburden_tests) > 0,
                'test_result': bioburden_result,
                'laboratory_information': None,  # Could be extracted from documents if available
                'source_document': None,
                'source_pages': []
            }
        else:
            conditional_documents['bioburden_results'] = {
                'conditional_status': 'CONDITION NOT MET',
                'condition_required': 'Fresh Tissue Processed',
                'bioburden_testing_performed': False,
                'test_result': None,
                'laboratory_information': None,
                'source_document': None,
                'source_pages': []
            }
        
        # 4. Skin Dermal Cultures
        # Same condition as bioburden - fresh tissue processed
        skin_dermal_tests = db.query(LaboratoryResult).filter(
            LaboratoryResult.document_id.in_(document_ids),
            LaboratoryResult.test_type == TestType.CULTURE,
            or_(
                LaboratoryResult.test_name.ilike('%skin%'),
                LaboratoryResult.test_name.ilike('%dermal%'),
                LaboratoryResult.test_name.ilike('%dermis%')
            )
        ).all()
        
        if fresh_tissue_processed:
            skin_dermal_results = []
            for test in skin_dermal_tests:
                skin_dermal_results.append({
                    'test_name': test.test_name,
                    'test_method': test.test_method,
                    'result': test.result,
                    'specimen_type': test.specimen_type,
                    'specimen_date': test.specimen_date,
                    'comments': test.comments
                })
            
            conditional_documents['skin_dermal_cultures'] = {
                'conditional_status': 'CONDITION MET',
                'condition_required': 'Fresh Tissue Processed',
                'testing_performed': len(skin_dermal_tests) > 0,
                'test_results': skin_dermal_results if skin_dermal_results else None,
                'source_document': None,
                'source_pages': []
            }
        else:
            conditional_documents['skin_dermal_cultures'] = {
                'conditional_status': 'CONDITION NOT MET',
                'condition_required': 'Fresh Tissue Processed',
                'testing_performed': False,
                'test_results': None,
                'source_document': None,
                'source_pages': []
            }
        
        # Extract source document and pages for each conditional document
        for doc_type, doc_data in conditional_documents.items():
            if doc_data.get('testing_performed') or doc_data.get('bioburden_testing_performed'):
                # Find source documents and pages
                source_docs = []
                source_pages = []
                
                # For toxicology and autopsy, try to find related documents
                if doc_type in ['toxicology_report', 'autopsy_report']:
                    # Search for documents that might contain these reports
                    for doc in documents:
                        filename_lower = (doc.original_filename or '').lower()
                        if doc_type == 'toxicology_report' and 'toxicology' in filename_lower:
                            source_docs.append(doc)
                        elif doc_type == 'autopsy_report' and 'autopsy' in filename_lower:
                            source_docs.append(doc)
                
                # For bioburden and skin dermal cultures, use lab result source pages
                elif doc_type in ['bioburden_results', 'skin_dermal_cultures']:
                    tests = bioburden_tests if doc_type == 'bioburden_results' else skin_dermal_tests
                    for test in tests:
                        if test.source_page:
                            source_pages.append({
                                'document_id': test.document_id,
                                'page': test.source_page
                            })
                
                if source_docs:
                    doc_data['source_document'] = source_docs[0].original_filename
                    # Extract pages from document chunks if available
                    from app.models.document_chunk import DocumentChunk
                    chunks = db.query(DocumentChunk).filter(
                        DocumentChunk.document_id == source_docs[0].id,
                        DocumentChunk.page_number.isnot(None)
                    ).limit(5).all()
                    doc_data['source_pages'] = [
                        {'document_id': source_docs[0].id, 'page': chunk.page_number}
                        for chunk in chunks if chunk.page_number
                    ]
                elif source_pages:
                    doc_data['source_pages'] = source_pages
                    if source_pages:
                        doc_data['source_document'] = f"Document {source_pages[0]['document_id']}"
        
        return conditional_documents
        
    except Exception as e:
        logger.error(f"Error determining conditional documents for donor {donor_id}: {e}", exc_info=True)
        return {}

