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
        
        
        # Get extraction data from DonorExtraction table for critical findings and document presence
        critical_findings = []
        rejection_reason = None
        
        from app.models.donor_extraction import DonorExtraction
        
        donor_extraction = db.query(DonorExtraction).filter(
            DonorExtraction.donor_id == donor.id
        ).first()
        
        extraction_data = None
        if donor_extraction and donor_extraction.extraction_data:
            extraction_data = donor_extraction.extraction_data
            
            # Get critical findings from validation
            if extraction_data.get("validation") and extraction_data["validation"].get("critical_findings"):
                for finding in extraction_data["validation"]["critical_findings"]:
                    critical_findings.append({
                        "type": finding.get("type", "Unknown"),
                        "severity": finding.get("severity", "CRITICAL"),
                        "automaticRejection": finding.get("automaticRejection", False),
                        "detectedAt": finding.get("detectedAt"),
                        "source": finding.get("source", {
                            "documentId": "Unknown",
                            "pageNumber": "Unknown",
                            "confidence": 0.95
                        })
                    })
                    if not rejection_reason and finding.get("automaticRejection"):
                        finding_type = finding.get("type", "Unknown")
                        rejection_reason = f"Critical Finding: {finding_type}"
                        # Update processing status to rejected if automatic rejection
                        if finding.get("automaticRejection"):
                            processing_status = "rejected"
        
        # Update required documents status based on extraction data present fields
        if extraction_data and extraction_data.get("extracted_data"):
            extracted_data = extraction_data["extracted_data"]
            
            # Map required document types to extraction data keys
            # These keys are generated from component names: "Component Name" -> "component_name"
            extraction_key_mapping = {
                'Medical History': ['medical_records', 'medical_records_review_summary'],
                'Serology Report': ['infectious_disease_testing'],
                'Laboratory Results': ['medical_records', 'medical_records_review_summary'],
                'Recovery Cultures': ['tissue_recovery_information'],
                'Consent Form': ['authorization_for_tissue_donation'],
                'Death Certificate': ['donor_information', 'donor_log_in_information_packet']
            }
            
            # Update document statuses based on present field in extraction data
            for req_doc in required_documents:
                doc_name = req_doc["name"]
                extraction_keys = extraction_key_mapping.get(doc_name, [])
                
                # Check if any of the mapped extraction keys have present=True
                found_present = False
                for extraction_key in extraction_keys:
                    if extraction_key in extracted_data:
                        section = extracted_data[extraction_key]
                        if section and isinstance(section, dict):
                            # Check the present field (can be boolean or "Yes"/"No" string)
                            present_value = section.get("present")
                            if present_value is True or present_value == "Yes" or present_value == "yes":
                                found_present = True
                                # If extraction says present, check if document actually exists
                                doc = doc_by_type.get(doc_name)
                                if doc:
                                    # Document exists - use actual document status
                                    if doc.status == DocumentStatus.COMPLETED:
                                        req_doc["status"] = "completed"
                                    elif doc.status in [DocumentStatus.PROCESSING, DocumentStatus.ANALYZING, DocumentStatus.REVIEWING]:
                                        req_doc["status"] = "processing"
                                    else:
                                        req_doc["status"] = "missing"
                                else:
                                    # Extraction says present but no document uploaded - might be in another document
                                    # Keep current status
                                    pass
                            elif present_value is False or present_value == "No" or present_value == "no":
                                # Explicitly marked as not present
                                if not doc_by_type.get(doc_name):
                                    req_doc["status"] = "missing"
                                break
                
                # If extraction data says not present and no document exists, mark as missing
                if not found_present and not doc_by_type.get(doc_name):
                    # Check if any extraction key exists and explicitly says not present
                    for extraction_key in extraction_keys:
                        if extraction_key in extracted_data:
                            section = extracted_data[extraction_key]
                            if section and isinstance(section, dict):
                                present_value = section.get("present")
                                if present_value is False or present_value == "No" or present_value == "no":
                                    req_doc["status"] = "missing"
                                    break
        
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
    """Get aggregated extraction data for a donor from DonorExtraction table."""
    from app.models.donor_extraction import DonorExtraction
    
    donor = db.query(Donor).filter(Donor.id == donor_id).first()
    if not donor:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Donor not found"
        )
    
    # Query DonorExtraction table
    donor_extraction = db.query(DonorExtraction).filter(
        DonorExtraction.donor_id == donor_id
    ).first()
    
    if donor_extraction and donor_extraction.extraction_data:
        return donor_extraction.extraction_data
    
    # Return empty structure if no extraction data found
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

@router.post("/search-similar")
async def search_similar_donors(
    query: str,
    limit: int = 10,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """Semantic search for similar donors based on extraction data."""
    from app.models.donor_extraction_vector import DonorExtractionVector
    from app.services.processing.utils.llm_config import llm_setup
    import asyncio
    
    try:
        # Generate embedding for query
        _, embeddings = await asyncio.get_event_loop().run_in_executor(None, llm_setup)
        query_embedding = await asyncio.get_event_loop().run_in_executor(
            None,
            lambda: embeddings.embed_query(query)
        )
        
        # Search using pgvector similarity
        # Note: This requires raw SQL for pgvector similarity search
        from sqlalchemy import text
        
        # Use cosine similarity
        # Convert embedding list to string format for pgvector
        embedding_str = '[' + ','.join(map(str, query_embedding)) + ']'
        
        results = db.execute(
            text("""
                SELECT 
                    donor_id,
                    extraction_type,
                    extraction_text,
                    1 - (embedding <=> CAST(:query_embedding AS vector)) as similarity
                FROM donor_extraction_vectors
                WHERE embedding IS NOT NULL
                ORDER BY embedding <=> CAST(:query_embedding AS vector)
                LIMIT :limit
            """),
            {
                "query_embedding": embedding_str,
                "limit": limit
            }
        ).fetchall()
        
        # Group by donor_id and get best matches
        donor_similarities = {}
        for row in results:
            donor_id = row[0]
            similarity = float(row[3])
            if donor_id not in donor_similarities or similarity > donor_similarities[donor_id]['similarity']:
                donor_similarities[donor_id] = {
                    "donor_id": donor_id,
                    "similarity": similarity,
                    "extraction_type": row[1],
                    "extraction_text": row[2]
                }
        
        # Get donor details
        similar_donors = []
        for donor_id, match_info in donor_similarities.items():
            donor = db.query(Donor).filter(Donor.id == donor_id).first()
            if donor:
                similar_donors.append({
                    "donor_id": donor_id,
                    "donor_name": donor.name,
                    "unique_donor_id": donor.unique_donor_id,
                    "similarity_score": match_info['similarity'],
                    "matched_on": match_info['extraction_type']
                })
        
        # Sort by similarity
        similar_donors.sort(key=lambda x: x['similarity_score'], reverse=True)
        
        return {
            "query": query,
            "results": similar_donors[:limit]
        }
        
    except Exception as e:
        logger.error(f"Error in similarity search: {e}", exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Error performing similarity search: {str(e)}"
        )

@router.get("/{donor_id}/similar")
async def get_similar_donors(
    donor_id: int,
    limit: int = 10,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """Get similar donors based on extraction data vectors."""
    from app.models.donor_extraction_vector import DonorExtractionVector
    from sqlalchemy import text
    
    donor = db.query(Donor).filter(Donor.id == donor_id).first()
    if not donor:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Donor not found"
        )
    
    # Get donor's extraction vectors
    donor_vectors = db.query(DonorExtractionVector).filter(
        DonorExtractionVector.donor_id == donor_id,
        DonorExtractionVector.embedding.isnot(None)
    ).all()
    
    if not donor_vectors:
        return {
            "donor_id": donor_id,
            "similar_donors": [],
            "message": "No extraction vectors found for this donor"
        }
    
    # Use the first vector for similarity search
    reference_vector = donor_vectors[0].embedding
    
    # Search for similar donors
    try:
        # Convert embedding to string format for pgvector
        if hasattr(reference_vector, '__iter__'):
            embedding_str = '[' + ','.join(map(str, reference_vector)) + ']'
        else:
            embedding_str = str(reference_vector)
        
        results = db.execute(
            text("""
                SELECT 
                    donor_id,
                    extraction_type,
                    1 - (embedding <=> CAST(:ref_embedding AS vector)) as similarity
                FROM donor_extraction_vectors
                WHERE donor_id != :donor_id
                AND embedding IS NOT NULL
                ORDER BY embedding <=> CAST(:ref_embedding AS vector)
                LIMIT :limit
            """),
            {
                "ref_embedding": embedding_str,
                "donor_id": donor_id,
                "limit": limit
            }
        ).fetchall()
        
        # Group by donor_id
        donor_similarities = {}
        for row in results:
            similar_donor_id = row[0]
            similarity = float(row[2])
            if similar_donor_id not in donor_similarities or similarity > donor_similarities[similar_donor_id]['similarity']:
                donor_similarities[similar_donor_id] = {
                    "donor_id": similar_donor_id,
                    "similarity": similarity
                }
        
        # Get donor details
        similar_donors = []
        for similar_donor_id, match_info in donor_similarities.items():
            similar_donor = db.query(Donor).filter(Donor.id == similar_donor_id).first()
            if similar_donor:
                similar_donors.append({
                    "donor_id": similar_donor_id,
                    "donor_name": similar_donor.name,
                    "unique_donor_id": similar_donor.unique_donor_id,
                    "similarity_score": match_info['similarity']
                })
        
        similar_donors.sort(key=lambda x: x['similarity_score'], reverse=True)
        
        return {
            "donor_id": donor_id,
            "similar_donors": similar_donors
        }
        
    except Exception as e:
        logger.error(f"Error finding similar donors for {donor_id}: {e}", exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Error finding similar donors: {str(e)}"
        )

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
