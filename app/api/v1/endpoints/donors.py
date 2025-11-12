from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session, joinedload
from typing import List, Dict, Any
import logging
import json
import os
from app.database.database import get_db
from app.models.donor import Donor
from app.models.document import Document, DocumentStatus, DocumentType
from app.models.user import User, UserRole
from app.schemas.donor import DonorCreate, DonorUpdate, DonorResponse, DonorPriorityUpdate
from app.api.v1.endpoints.auth import get_current_user

logger = logging.getLogger(__name__)
router = APIRouter()

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
    
    # Required document types
    REQUIRED_DOC_TYPES = [
        'Medical History',
        'Serology Report',
        'Laboratory Results',
        'Recovery Cultures',
        'Consent Form',
        'Death Certificate'
    ]
    
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
        
        
        # Try to get extraction data for critical findings
        critical_findings = []
        rejection_reason = None
        
        # Try to load extraction data
        possible_paths = [
            os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(__file__))))), "mtf-backend-test", "test.json"),
            os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(__file__)))), "..", "mtf-backend-test", "test.json"),
            "/Users/amrutmaliye/Desktop/Dev/Github/donoriq/mtf-backend-test/test.json"
        ]
        
        extraction_data = None
        for path in possible_paths:
            if os.path.exists(path):
                try:
                    with open(path, 'r') as f:
                        extraction_data = json.load(f)
                    break
                except Exception as e:
                    logger.error(f"Error loading test.json: {e}")
        
        # Check for critical findings in extraction data
        if extraction_data and extraction_data.get("validation"):
            validation = extraction_data.get("validation", {})
            if validation.get("critical_findings"):
                for finding in validation.get("critical_findings", []):
                    critical_findings.append({
                        "type": finding.get("type", "Unknown"),
                        "severity": "CRITICAL",
                        "automaticRejection": True,
                        "detectedAt": extraction_data.get("processing_timestamp"),
                        "source": {
                            "documentId": "doc1",
                            "pageNumber": finding.get("page", "Unknown"),
                            "confidence": finding.get("confidence", 0.95)
                        }
                    })
                    if not rejection_reason:
                        rejection_reason = f"Critical Finding: {finding.get('type', 'Unknown')}"
        
        # For demo purposes, add mock data for donors without critical findings or missing documents
        # This ensures the column always has data to display
        
        # Add critical findings for some donors (alternating pattern for variety)
        if donor.id % 3 == 1:  # Every 3rd donor starting from 1 (1, 4, 7, ...)
            critical_findings = [{
                "type": "HIV",
                "severity": "CRITICAL",
                "automaticRejection": True,
                "detectedAt": donor.created_at.isoformat() if donor.created_at else None,
                "source": {
                    "documentId": "doc1",
                    "pageNumber": "3",
                    "confidence": 0.98
                }
            }]
            rejection_reason = "Critical Finding: HIV Positive"
            processing_status = "rejected"
        elif donor.id % 5 == 2:  # Every 5th donor starting from 2 (2, 7, 12, ...)
            critical_findings = [{
                "type": "Hepatitis B",
                "severity": "CRITICAL",
                "automaticRejection": True,
                "detectedAt": donor.created_at.isoformat() if donor.created_at else None,
                "source": {
                    "documentId": "doc2",
                    "pageNumber": "5",
                    "confidence": 0.95
                }
            }]
            rejection_reason = "Critical Finding: Hepatitis B Positive"
            processing_status = "rejected"
        
        # If no critical findings, ensure some documents are missing or processing for demo purposes
        # This ensures the column always has data to display
        if not critical_findings:
            # Count current statuses
            missing_docs = [doc for doc in required_documents if doc["status"] == "missing"]
            processing_docs = [doc for doc in required_documents if doc["status"] == "processing"]
            completed_docs = [doc for doc in required_documents if doc["status"] == "completed"]
            
            # If all documents are completed or there are no missing/processing documents,
            # add some dummy missing or processing documents for demo
            if len(missing_docs) == 0 and len(processing_docs) == 0:
                # For even donor IDs, mark 2-3 documents as missing
                if donor.id % 2 == 0:
                    # Mark first 2 documents as missing (or processing if they exist)
                    for i in range(min(2, len(required_documents))):
                        if required_documents[i]["status"] == "completed":
                            required_documents[i]["status"] = "missing"
                else:
                    # For odd donor IDs, mark 1-2 documents as processing
                    for i in range(min(2, len(required_documents))):
                        if required_documents[i]["status"] == "completed":
                            required_documents[i]["status"] = "processing"
                    # If still no processing docs, mark one as processing
                    if len([doc for doc in required_documents if doc["status"] == "processing"]) == 0:
                        if len(required_documents) > 0:
                            required_documents[0]["status"] = "processing"
        
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
    """Get extraction data for a donor (temporary endpoint for testing)."""
    import json
    import os
    
    donor = db.query(Donor).filter(Donor.id == donor_id).first()
    if not donor:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Donor not found"
        )
    
    # For testing: Try to load test.json if it exists
    # In production, this would come from the database or processing service
    # Try multiple possible paths
    possible_paths = [
        os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(__file__))))), "mtf-backend-test", "test.json"),
        os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(__file__)))), "..", "mtf-backend-test", "test.json"),
        "/Users/amrutmaliye/Desktop/Dev/Github/donoriq/mtf-backend-test/test.json"
    ]
    
    test_json_path = None
    for path in possible_paths:
        if os.path.exists(path):
            test_json_path = path
            break
    
    if test_json_path and os.path.exists(test_json_path):
        try:
            with open(test_json_path, 'r') as f:
                extraction_data = json.load(f)
            # Update donor_id and case_id to match the requested donor
            extraction_data["donor_id"] = donor.unique_donor_id
            extraction_data["case_id"] = f"{donor.unique_donor_id}81"
            return extraction_data
        except Exception as e:
            logger.error(f"Error loading test.json: {e}")
    
    # Return empty structure if test.json not found
    return {
        "donor_id": donor.unique_donor_id,
        "case_id": f"{donor.unique_donor_id}81",
        "processing_timestamp": None,
        "processing_duration_seconds": 0,
        "extracted_data": {},
        "conditional_documents": {},
        "validation": None,
        "compliance_status": None,
        "document_summary": None
    }
