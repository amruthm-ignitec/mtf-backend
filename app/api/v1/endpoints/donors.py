from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session, joinedload
from typing import List, Dict, Any
from datetime import datetime
import logging
import json
import os
import re
from app.database.database import get_db
from app.models.donor import Donor
from app.models.document import Document, DocumentStatus, DocumentType
from app.models.user import User, UserRole
from app.schemas.donor import DonorCreate, DonorUpdate, DonorResponse, DonorPriorityUpdate
from app.api.v1.endpoints.auth import get_current_user

logger = logging.getLogger(__name__)
router = APIRouter()

def component_name_to_extraction_key(component_name: str) -> str:
    """
    Convert component name to extraction key format.
    Example: "Donor Log-In Information Packet" -> "donor_log_in_information_packet"
    """
    # Convert to lowercase and replace spaces/special chars with underscores
    key = component_name.lower()
    # Replace special characters and spaces with underscores
    key = re.sub(r'[^a-z0-9]+', '_', key)
    # Remove leading/trailing underscores
    key = key.strip('_')
    return key

@router.get("/", response_model=List[DonorResponse])
async def get_donors(
    skip: int = 0, 
    limit: int = 100, 
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """Get all donors with pagination."""
    donors = db.query(Donor).offset(skip).limit(limit).all()
    return donors

@router.get("/{donor_id}", response_model=DonorResponse)
async def get_donor(
    donor_id: int, 
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """Get a specific donor by ID."""
    donor = db.query(Donor).filter(Donor.id == donor_id).first()
    if not donor:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Donor not found"
        )
    return donor

@router.post("/", response_model=DonorResponse)
async def create_donor(
    donor: DonorCreate, 
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """Create a new donor."""
    # Check if donor ID already exists
    existing_donor = db.query(Donor).filter(Donor.unique_donor_id == donor.unique_donor_id).first()
    if existing_donor:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Donor with this ID already exists"
        )
    
    db_donor = Donor(**donor.dict())
    db.add(db_donor)
    db.commit()
    db.refresh(db_donor)
    
    logger.info(f"Donor created: {db_donor.unique_donor_id} by user: {current_user.email}")
    return db_donor

@router.put("/{donor_id}", response_model=DonorResponse)
async def update_donor(
    donor_id: int,
    donor_update: DonorUpdate,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """Update a donor."""
    donor = db.query(Donor).filter(Donor.id == donor_id).first()
    if not donor:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Donor not found"
        )
    
    update_data = donor_update.dict(exclude_unset=True)
    for field, value in update_data.items():
        setattr(donor, field, value)
    
    db.commit()
    db.refresh(donor)
    
    logger.info(f"Donor updated: {donor.unique_donor_id} by user: {current_user.email}")
    return donor

@router.put("/{donor_id}/priority", response_model=DonorResponse)
async def update_donor_priority(
    donor_id: int,
    priority_update: DonorPriorityUpdate,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """Update donor priority status."""
    donor = db.query(Donor).filter(Donor.id == donor_id).first()
    if not donor:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Donor not found"
        )
    
    donor.is_priority = priority_update.is_priority
    db.commit()
    db.refresh(donor)
    
    logger.info(f"Donor priority updated: {donor.unique_donor_id} to {priority_update.is_priority} by user: {current_user.email}")
    return donor

@router.delete("/{donor_id}")
async def delete_donor(
    donor_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """Delete a donor (Admin only)."""
    if current_user.role != UserRole.ADMIN:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Not enough permissions"
        )
    
    donor = db.query(Donor).filter(Donor.id == donor_id).first()
    if not donor:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Donor not found"
        )
    
    donor_id_str = donor.unique_donor_id
    db.delete(donor)
    db.commit()
    
    logger.info(f"Donor deleted: {donor_id_str} by admin: {current_user.email}")
    return {"message": "Donor deleted successfully"}

@router.get("/queue/details")
async def get_queue_details(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """Get all donors with documents, critical findings, and missing documents for the queue page."""
    donors = db.query(Donor).all()
    result = []
    
    # Document components config was removed during cleanup
    # Using empty list for required document types
    REQUIRED_DOC_TYPES = []
    
    for donor in donors:
        # Get all documents for this donor
        documents = db.query(Document).filter(Document.donor_id == donor.id).all()
        
        # Map documents by type - convert enum values to display names
        doc_type_mapping = {
            'medical_history': 'Medical History',
            'serology_report': 'Serology Report',
            'lab_results': 'Laboratory Results',
            'recovery_cultures': 'Recovery Cultures',
            'consent_form': 'Consent Form',
            'death_certificate': 'Death Certificate',
            'other': 'Other'
        }
        
        doc_by_type: Dict[str, Document] = {}
        for doc in documents:
            if doc.document_type:
                doc_type_enum = doc.document_type.value if hasattr(doc.document_type, 'value') else str(doc.document_type)
                doc_type_display = doc_type_mapping.get(doc_type_enum, doc_type_enum.replace('_', ' ').title())
                doc_by_type[doc_type_display] = doc
        
        # Build required documents list
        required_documents = []
        for req_type in REQUIRED_DOC_TYPES:
            doc = doc_by_type.get(req_type)
            if doc:
                status = doc.status.value if hasattr(doc.status, 'value') else str(doc.status)
                required_documents.append({
                    "id": f"rd-{donor.id}-{req_type}",
                    "name": req_type,
                    "type": req_type.lower().replace(' ', '_'),
                    "label": req_type,
                    "status": "processing" if status in ["processing", "analyzing", "reviewing"] else "completed" if status == "completed" else "missing",
                    "isRequired": True,
                    "uploadDate": doc.created_at.isoformat() if doc.created_at else None,
                    "reviewedBy": None,
                    "notes": "",
                    "pageCount": 0
                })
            else:
                required_documents.append({
                    "id": f"rd-{donor.id}-{req_type}",
                    "name": req_type,
                    "type": req_type.lower().replace(' ', '_'),
                    "label": req_type,
                    "status": "missing",
                    "isRequired": True,
                    "uploadDate": None,
                    "reviewedBy": "Pending",
                    "notes": "Document not received",
                    "pageCount": 0
                })
        
        # Determine processing status
        if len(documents) == 0:
            processing_status = "pending"
        else:
            all_completed = all(doc.status == DocumentStatus.COMPLETED for doc in documents)
            has_processing = any(doc.status in [DocumentStatus.PROCESSING, DocumentStatus.ANALYZING, DocumentStatus.REVIEWING] for doc in documents)
            has_failed = any(doc.status == DocumentStatus.FAILED for doc in documents)
            has_rejected = any(doc.status == DocumentStatus.REJECTED for doc in documents)
            
            if has_rejected:
                processing_status = "rejected"
            elif has_failed:
                processing_status = "failed"
            elif all_completed:
                processing_status = "completed"
            elif has_processing:
                processing_status = "processing"
            else:
                processing_status = "pending"
        
        
        # Get eligibility data from DonorEligibility table for critical findings
        critical_findings = None  # None means evaluation hasn't happened yet, [] means no findings
        rejection_reason = None
        
        from app.models.donor_eligibility import DonorEligibility
        
        # Get eligibility for both tissue types
        eligibility_ms = db.query(DonorEligibility).filter(
            DonorEligibility.donor_id == donor.id,
            DonorEligibility.tissue_type == "musculoskeletal"
        ).first()
        
        eligibility_skin = db.query(DonorEligibility).filter(
            DonorEligibility.donor_id == donor.id,
            DonorEligibility.tissue_type == "skin"
        ).first()
        
        # Build critical findings from blocking criteria
        if eligibility_ms or eligibility_skin:
            critical_findings = []
            
            # Add blocking criteria from musculoskeletal eligibility
            if eligibility_ms and eligibility_ms.blocking_criteria:
                for criterion in eligibility_ms.blocking_criteria:
                    critical_findings.append({
                        "type": criterion.get("criterion_name", "Unknown"),
                        "severity": "CRITICAL",
                        "automaticRejection": True,
                        "detectedAt": eligibility_ms.evaluated_at.isoformat() if eligibility_ms.evaluated_at else None,
                        "source": {
                            "documentId": "Unknown",
                            "pageNumber": "Unknown",
                            "confidence": 0.95
                        }
                    })
                    if not rejection_reason:
                        rejection_reason = f"Critical Finding: {criterion.get('criterion_name', 'Unknown')}"
                        if eligibility_ms.overall_status.value == "ineligible":
                            processing_status = "rejected"
            
            # Add blocking criteria from skin eligibility (avoid duplicates)
            if eligibility_skin and eligibility_skin.blocking_criteria:
                for criterion in eligibility_skin.blocking_criteria:
                    criterion_name = criterion.get("criterion_name", "Unknown")
                    if not any(cf["type"] == criterion_name for cf in critical_findings):
                        critical_findings.append({
                            "type": criterion_name,
                            "severity": "CRITICAL",
                            "automaticRejection": True,
                            "detectedAt": eligibility_skin.evaluated_at.isoformat() if eligibility_skin.evaluated_at else None,
                            "source": {
                                "documentId": "Unknown",
                                "pageNumber": "Unknown",
                                "confidence": 0.95
                            }
                        })
                        if not rejection_reason:
                            rejection_reason = f"Critical Finding: {criterion_name}"
                            if eligibility_skin.overall_status.value == "ineligible":
                                processing_status = "rejected"
        
        # Update required documents status based on document processing
        # Simplified: just check if documents exist and are completed
        for req_doc in required_documents:
            doc_name = req_doc["name"]
            matching_doc = doc_by_type.get(doc_name)
            
            if matching_doc:
                status = matching_doc.status.value if hasattr(matching_doc.status, 'value') else str(matching_doc.status)
                if status == "completed":
                    req_doc["status"] = "completed"
                elif status in ["processing", "analyzing", "reviewing"]:
                    req_doc["status"] = "processing"
                else:
                    req_doc["status"] = "missing"
            else:
                req_doc["status"] = "missing"
        
        result.append({
            "id": str(donor.id),
            "donorName": donor.name,
            "age": donor.age,
            "gender": donor.gender,
            "causeOfDeath": None,  # Add if you have this field
            "uploadTimestamp": donor.created_at.isoformat() if donor.created_at else None,
            "processingStatus": processing_status,
            "status": processing_status,
            "criticalFindings": critical_findings,
            "screeningStatus": "HALTED" if critical_findings else None,
            "rejectionReason": rejection_reason,
            "requiredDocuments": required_documents,
            "documents": [
                {
                    "id": str(doc.id),
                    "fileName": doc.original_filename or doc.filename,
                    "fileType": doc.file_type,
                    "uploadTimestamp": doc.created_at.isoformat() if doc.created_at else None,
                    "status": doc.status.value if hasattr(doc.status, 'value') else str(doc.status)
                }
                for doc in documents
            ]
        })
    
    return result

@router.get("/{donor_id}/details")
async def get_donor_details(
    donor_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """Get detailed donor information for summary page."""
    donor = db.query(Donor).filter(Donor.id == donor_id).first()
    if not donor:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Donor not found"
        )
    
    # Return donor data in format expected by frontend
    return {
        "id": donor.id,
        "donorName": donor.name,
        "age": None,  # Add if you have age field
        "gender": donor.gender,
        "causeOfDeath": None,  # Add if you have this field
        "uploadTimestamp": donor.created_at.isoformat() if donor.created_at else None,
        "requiredDocuments": []  # Add if you have documents linked
    }

@router.get("/{donor_id}/extraction-data")
async def get_donor_extraction_data(
    donor_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """Get aggregated extraction data for a donor from new criteria-focused tables."""
    from app.models.document import Document
    from app.models.laboratory_result import LaboratoryResult
    from app.services.processing.result_parser import result_parser
    
    donor = db.query(Donor).filter(Donor.id == donor_id).first()
    if not donor:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Donor not found"
        )
    
    # Get all documents for this donor
    documents = db.query(Document).filter(Document.donor_id == donor_id).all()
    document_ids = [doc.id for doc in documents]
    
    # Get all laboratory results
    all_serology_results = {}
    all_culture_results = []
    all_serology_citations = []
    all_culture_citations = []
    
    for doc_id in document_ids:
        lab_results = result_parser.get_laboratory_results_for_document(doc_id, db)
        serology = lab_results.get("serology_results", {})
        culture = lab_results.get("culture_results", {})
        
        # Merge serology results
        all_serology_results.update(serology.get("result", {}))
        all_serology_citations.extend(serology.get("citations", []))
        
        # Merge culture results
        all_culture_results.extend(culture.get("result", []))
        all_culture_citations.extend(culture.get("citations", []))
    
    # Get criteria evaluations
    criteria_evaluations = result_parser.get_criteria_evaluations_for_donor(donor_id, db)
    
    # Get eligibility decisions
    from app.models.donor_eligibility import DonorEligibility
    eligibility_ms = db.query(DonorEligibility).filter(
        DonorEligibility.donor_id == donor_id,
        DonorEligibility.tissue_type == "musculoskeletal"
    ).first()
    
    eligibility_skin = db.query(DonorEligibility).filter(
        DonorEligibility.donor_id == donor_id,
        DonorEligibility.tissue_type == "skin"
    ).first()
    
    # Build validation from eligibility
    critical_findings = []
    if eligibility_ms and eligibility_ms.blocking_criteria:
        for criterion in eligibility_ms.blocking_criteria:
            critical_findings.append({
                "type": criterion.get("criterion_name", "Unknown"),
                "severity": "CRITICAL",
                "automaticRejection": True,
                "reasoning": criterion.get("reasoning", "")
            })
    
    if eligibility_skin and eligibility_skin.blocking_criteria:
        for criterion in eligibility_skin.blocking_criteria:
            # Avoid duplicates
            if not any(cf["type"] == criterion.get("criterion_name") for cf in critical_findings):
                critical_findings.append({
                    "type": criterion.get("criterion_name", "Unknown"),
                    "severity": "CRITICAL",
                    "automaticRejection": True,
                    "reasoning": criterion.get("reasoning", "")
                })
    
    # Build response in format expected by frontend (backward compatibility)
    return {
        "donor_id": donor.unique_donor_id,
        "case_id": f"{donor.unique_donor_id}81",
        "processing_timestamp": datetime.now().isoformat() if documents else None,
        "processing_duration_seconds": 0,
        "extracted_data": {},  # Can be populated from criteria_evaluations if needed
        "conditional_documents": {},
        "validation": {
            "critical_findings": critical_findings,
            "has_critical_findings": len(critical_findings) > 0,
            "automatic_rejection": any(cf.get("automaticRejection", False) for cf in critical_findings)
        } if critical_findings else None,
        "compliance_status": None,
        "document_summary": {
            "total_documents_processed": len([d for d in documents if d.status == DocumentStatus.COMPLETED]),
            "total_pages_processed": 0,
            "extraction_methods_used": ["laboratory_tests", "criteria_evaluation"]
        },
        # New fields for criteria-focused system
        "serology_results": {
            "result": all_serology_results,
            "citations": all_serology_citations
        },
        "culture_results": {
            "result": all_culture_results,
            "citations": all_culture_citations
        },
        "criteria_evaluations": criteria_evaluations,
        "eligibility": {
            "musculoskeletal": {
                "status": eligibility_ms.overall_status.value if eligibility_ms else None,
                "blocking_criteria": eligibility_ms.blocking_criteria if eligibility_ms else [],
                "md_discretion_criteria": eligibility_ms.md_discretion_criteria if eligibility_ms else []
            } if eligibility_ms else None,
            "skin": {
                "status": eligibility_skin.overall_status.value if eligibility_skin else None,
                "blocking_criteria": eligibility_skin.blocking_criteria if eligibility_skin else [],
                "md_discretion_criteria": eligibility_skin.md_discretion_criteria if eligibility_skin else []
            } if eligibility_skin else None
        }
    }

@router.get("/{donor_id}/eligibility")
async def get_donor_eligibility(
    donor_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """Get eligibility decisions for a donor per tissue type."""
    from app.models.donor_eligibility import DonorEligibility
    
    donor = db.query(Donor).filter(Donor.id == donor_id).first()
    if not donor:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Donor not found"
        )
    
    # Get eligibility for both tissue types
    eligibility_ms = db.query(DonorEligibility).filter(
        DonorEligibility.donor_id == donor_id,
        DonorEligibility.tissue_type == "musculoskeletal"
    ).first()
    
    eligibility_skin = db.query(DonorEligibility).filter(
        DonorEligibility.donor_id == donor_id,
        DonorEligibility.tissue_type == "skin"
    ).first()
    
    # Get criteria evaluations for details
    from app.models.criteria_evaluation import CriteriaEvaluation
    criteria_evaluations = db.query(CriteriaEvaluation).filter(
        CriteriaEvaluation.donor_id == donor_id
    ).all()
    
    # Group evaluations by criterion
    evaluations_by_criterion = {}
    for eval_obj in criteria_evaluations:
        criterion_name = eval_obj.criterion_name
        if criterion_name not in evaluations_by_criterion:
            evaluations_by_criterion[criterion_name] = []
        evaluations_by_criterion[criterion_name].append({
            "tissue_type": eval_obj.tissue_type.value,
            "evaluation_result": eval_obj.evaluation_result.value,
            "evaluation_reasoning": eval_obj.evaluation_reasoning,
            "extracted_data": eval_obj.extracted_data
        })
    
    return {
        "donor_id": donor.unique_donor_id,
        "eligibility": {
            "musculoskeletal": {
                "status": eligibility_ms.overall_status.value if eligibility_ms else None,
                "blocking_criteria": eligibility_ms.blocking_criteria if eligibility_ms else [],
                "md_discretion_criteria": eligibility_ms.md_discretion_criteria if eligibility_ms else [],
                "evaluated_at": eligibility_ms.evaluated_at.isoformat() if eligibility_ms and eligibility_ms.evaluated_at else None
            },
            "skin": {
                "status": eligibility_skin.overall_status.value if eligibility_skin else None,
                "blocking_criteria": eligibility_skin.blocking_criteria if eligibility_skin else [],
                "md_discretion_criteria": eligibility_skin.md_discretion_criteria if eligibility_skin else [],
                "evaluated_at": eligibility_skin.evaluated_at.isoformat() if eligibility_skin and eligibility_skin.evaluated_at else None
            }
        },
        "criteria_evaluations": evaluations_by_criterion
    }

@router.get("/{donor_id}/extraction/detailed")
async def get_donor_extraction_detailed(
    donor_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """Get detailed breakdown of extraction results per document for a donor."""
    from app.models.document import Document, DocumentStatus
    from app.services.processing.result_parser import result_parser
    
    donor = db.query(Donor).filter(Donor.id == donor_id).first()
    if not donor:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Donor not found"
        )
    
    # Get all completed documents
    documents = db.query(Document).filter(
        Document.donor_id == donor_id,
        Document.status == DocumentStatus.COMPLETED
    ).all()
    
    detailed_results = {}
    for document in documents:
        detailed_results[document.id] = {
            "document_id": document.id,
            "filename": document.original_filename,
            "culture": result_parser.get_culture_results_for_document(document.id, db),
            "serology": result_parser.get_serology_results_for_document(document.id, db),
            "topics": result_parser.get_topic_results_for_document(document.id, db),
            "components": result_parser.get_component_results_for_document(document.id, db)
        }
    
    return {
        "donor_id": donor_id,
        "documents": detailed_results
    }
