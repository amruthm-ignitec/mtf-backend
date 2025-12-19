#!/usr/bin/env python3
"""
Script to batch process donor folders from Azure Blob Storage and populate anchor database.
Processes DNC/ and Compliant/ folders, determines outcomes, processes documents, and stores in anchor DB.

Usage: python scripts/batch_process_donor_folders.py [--skip-existing]
"""
import sys
import os
import asyncio
import time
from typing import Dict, List, Optional
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from sqlalchemy.orm import sessionmaker
from app.database.database import engine, Base
from app.models.donor import Donor
from app.models.document import Document, DocumentStatus, DocumentType
from app.models.user import User
from app.models.donor_anchor_decision import DonorAnchorDecision, AnchorOutcome, OutcomeSource
from app.services.azure_service import azure_blob_service
from app.services.anchor_database_service import anchor_database_service
from app.services.extraction_aggregation import ExtractionAggregationService
from app.services.queue_service import queue_service
from app.services.document_processing import document_processing_service
from app.core.config import settings
import logging

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


def get_or_create_admin_user(db):
    """Get or create an admin user for document uploads."""
    admin = db.query(User).filter(User.email == "admin@donoriq.com").first()
    if not admin:
        from app.core.security import hash_password
        from app.models.user import UserRole
        admin = User(
            email="admin@donoriq.com",
            hashed_password=hash_password("admin123"),
            full_name="System Administrator",
            role=UserRole.ADMIN,
            is_active=True
        )
        db.add(admin)
        db.commit()
        db.refresh(admin)
    return admin


async def process_donor_folder(
    donor_folder_name: str,
    parent_folder: str,
    outcome: AnchorOutcome,
    documents: List[str],
    db,
    admin_user_id: int,
    skip_existing: bool = False
) -> bool:
    """
    Process a single donor folder.
    
    Args:
        donor_folder_name: Name of the donor folder (e.g., "donor_001")
        parent_folder: Parent folder name (e.g., "DNC/" or "Compliant/")
        outcome: ACCEPTED or REJECTED
        documents: List of document blob names
        db: Database session
        admin_user_id: ID of admin user for uploads
        skip_existing: If True, skip donors that already have anchor decisions
        
    Returns:
        True if successful, False otherwise
    """
    try:
        # Check if donor already has anchor decision
        if skip_existing:
            existing_donor = db.query(Donor).filter(
                Donor.unique_donor_id == donor_folder_name
            ).first()
            if existing_donor:
                existing_anchor = db.query(DonorAnchorDecision).filter(
                    DonorAnchorDecision.donor_id == existing_donor.id
                ).first()
                if existing_anchor:
                    logger.info(f"Skipping {donor_folder_name} - already has anchor decision")
                    return True
        
        # Get or create donor
        donor = db.query(Donor).filter(
            Donor.unique_donor_id == donor_folder_name
        ).first()
        
        if not donor:
            # Create donor (we don't have age/gender from folder name, so use defaults)
            donor = Donor(
                unique_donor_id=donor_folder_name,
                name=donor_folder_name,
                gender="Unknown",  # Will be extracted from documents
                age=None
            )
            db.add(donor)
            db.commit()
            db.refresh(donor)
            logger.info(f"Created donor: {donor_folder_name}")
        else:
            logger.info(f"Using existing donor: {donor_folder_name} (ID: {donor.id})")
        
        # Download and upload documents
        document_ids = []
        for doc_blob_name in documents:
            full_blob_name = f"{parent_folder}{donor_folder_name}/{doc_blob_name}"
            
            # Download blob
            blob_content = await azure_blob_service.download_blob_to_memory(full_blob_name)
            if not blob_content:
                logger.error(f"Failed to download {full_blob_name}")
                continue
            
            # Create document record
            import uuid
            unique_filename = f"{uuid.uuid4()}_{doc_blob_name}"
            
            # Upload to Azure (if not already there, or use existing blob)
            azure_url = await azure_blob_service.upload_file(
                file_content=blob_content,
                filename=full_blob_name,  # Keep original path structure
                content_type="application/pdf"
            )
            
            if not azure_url:
                logger.error(f"Failed to upload {full_blob_name}")
                continue
            
            # Create document record
            document = Document(
                filename=unique_filename,
                original_filename=doc_blob_name,
                file_size=len(blob_content),
                file_type="application/pdf",
                document_type=None,
                status=DocumentStatus.UPLOADED,
                azure_blob_url=azure_url,
                donor_id=donor.id,
                uploaded_by=admin_user_id
            )
            db.add(document)
            db.commit()
            db.refresh(document)
            document_ids.append(document.id)
            logger.info(f"  Uploaded document: {doc_blob_name} (ID: {document.id})")
        
        if not document_ids:
            logger.error(f"No documents uploaded for {donor_folder_name}")
            return False
        
        # Process documents directly
        for doc_id in document_ids:
            document = db.query(Document).filter(Document.id == doc_id).first()
            if document:
                # Mark as processing
                marked = await queue_service.mark_document_processing(doc_id, db)
                if marked:
                    # Process document directly
                    logger.info(f"  Processing document {doc_id}...")
                    await document_processing_service.process_document(doc_id, db)
                    logger.info(f"  Completed document {doc_id}")
                else:
                    logger.warning(f"  Could not mark document {doc_id} as processing")
        
        # Verify all documents are completed
        documents_status = db.query(Document).filter(
            Document.id.in_(document_ids)
        ).all()
        
        completed_count = sum(1 for doc in documents_status if doc.status == DocumentStatus.COMPLETED)
        failed_count = sum(1 for doc in documents_status if doc.status == DocumentStatus.FAILED)
        
        logger.info(f"  Documents status: {completed_count} completed, {failed_count} failed out of {len(document_ids)}")
        
        if completed_count == 0:
            logger.error(f"  No documents completed for {donor_folder_name}, skipping anchor DB creation")
            return False
        
        # Wait for aggregation to complete
        logger.info(f"  Waiting for aggregation to complete for {donor_folder_name}...")
        await ExtractionAggregationService.aggregate_donor_results(donor.id, db)
        
        # Create anchor decision
        anchor_decision = await anchor_database_service.create_anchor_decision(
            donor_id=donor.id,
            outcome=outcome,
            outcome_source=OutcomeSource.BATCH_IMPORT,
            db=db
        )
        
        if anchor_decision:
            logger.info(f"✓ Successfully processed {donor_folder_name} - Outcome: {outcome.value}")
            return True
        else:
            logger.error(f"✗ Failed to create anchor decision for {donor_folder_name}")
            return False
            
    except Exception as e:
        logger.error(f"Error processing donor folder {donor_folder_name}: {e}", exc_info=True)
        return False


async def batch_process_folders(skip_existing: bool = False):
    """Batch process all donor folders from Azure Blob Storage."""
    print("=" * 60)
    print("Batch Processing Donor Folders from Azure Blob Storage")
    print("=" * 60)
    
    # Check if Azure is enabled
    if not azure_blob_service.is_enabled():
        print("❌ Azure Blob Storage is not configured or not enabled")
        return
    
    print(f"✓ Azure Blob Storage: Connected")
    print(f"  Container: {azure_blob_service.container_name}")
    print()
    
    # Create database session
    SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
    db = SessionLocal()
    
    try:
        # Get admin user
        admin_user = get_or_create_admin_user(db)
        
        # Process DNC/ and Compliant/ folders
        parent_folders = {
            "DNC/": AnchorOutcome.REJECTED,
            "Compliant/": AnchorOutcome.ACCEPTED
        }
        
        all_donor_folders = []
        
        for parent_folder, outcome in parent_folders.items():
            # List blobs with this prefix
            blobs = azure_blob_service.list_blobs_by_prefix(parent_folder)
            
            if not blobs:
                print(f"No blobs found in {parent_folder}")
                continue
            
            # Group blobs by donor folder
            donor_folders: Dict[str, List[str]] = {}
            for blob_name in blobs:
                # Extract donor folder name
                parts = blob_name[len(parent_folder):].split('/')
                if len(parts) >= 2:
                    donor_folder = parts[0]
                    document_name = '/'.join(parts[1:])
                    
                    if donor_folder not in donor_folders:
                        donor_folders[donor_folder] = []
                    donor_folders[donor_folder].append(document_name)
            
            # Add to processing list
            for donor_folder, documents in donor_folders.items():
                all_donor_folders.append({
                    "donor_folder": donor_folder,
                    "parent_folder": parent_folder,
                    "outcome": outcome,
                    "documents": documents
                })
        
        total = len(all_donor_folders)
        print(f"Found {total} donor folders to process")
        print()
        
        # Process each donor folder
        successful = 0
        failed = 0
        
        for idx, folder_info in enumerate(all_donor_folders, 1):
            print(f"[{idx}/{total}] Processing {folder_info['donor_folder']} ({folder_info['outcome'].value})...")
            
            success = await process_donor_folder(
                donor_folder_name=folder_info["donor_folder"],
                parent_folder=folder_info["parent_folder"],
                outcome=folder_info["outcome"],
                documents=folder_info["documents"],
                db=db,
                admin_user_id=admin_user.id,
                skip_existing=skip_existing
            )
            
            if success:
                successful += 1
            else:
                failed += 1
            
            print()
        
        print("=" * 60)
        print(f"Batch Processing Complete:")
        print(f"  Total: {total}")
        print(f"  Successful: {successful}")
        print(f"  Failed: {failed}")
        print("=" * 60)
        
    except Exception as e:
        logger.error(f"Error in batch processing: {e}", exc_info=True)
        print(f"❌ Error: {e}")
    finally:
        db.close()


if __name__ == "__main__":
    import argparse
    parser = argparse.ArgumentParser(description="Batch process donor folders from Azure Blob Storage")
    parser.add_argument("--skip-existing", action="store_true", help="Skip donors that already have anchor decisions")
    args = parser.parse_args()
    
    try:
        asyncio.run(batch_process_folders(skip_existing=args.skip_existing))
    except KeyboardInterrupt:
        print("\n⚠️  Interrupted by user")
        sys.exit(1)
    except Exception as e:
        print(f"❌ Error: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)

