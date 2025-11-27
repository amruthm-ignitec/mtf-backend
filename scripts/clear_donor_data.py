#!/usr/bin/env python3
"""
Script to clear all data related to a donor except the donor details.
This will delete:
- All documents and their associated data (chunks, extraction results)
- All donor approvals
- All donor extraction data
- All files from Azure Blob Storage

The donor record itself will be preserved.

Usage: python scripts/clear_donor_data.py <donor_id>
       python scripts/clear_donor_data.py --all  # Clear data for all donors
"""
import sys
import os
import asyncio
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from sqlalchemy.orm import sessionmaker
from app.database.database import engine, Base
from app.models.donor import Donor
from app.models.document import Document
from app.models.document_chunk import DocumentChunk
from app.models.culture_result import CultureResult
from app.models.serology_result import SerologyResult
from app.models.topic_result import TopicResult
from app.models.component_result import ComponentResult
from app.models.donor_approval import DonorApproval
from app.models.donor_extraction import DonorExtraction
from app.models.donor_extraction_vector import DonorExtractionVector
from app.services.azure_service import azure_blob_service


async def delete_document_files(documents, db):
    """Delete document files from Azure Blob Storage."""
    deleted_count = 0
    failed_count = 0
    
    for document in documents:
        if document.filename:
            try:
                success = await azure_blob_service.delete_file(document.filename)
                if success:
                    deleted_count += 1
                    print(f"  ✓ Deleted file from Azure: {document.filename}")
                else:
                    failed_count += 1
                    print(f"  ⚠ Failed to delete file from Azure: {document.filename}")
            except Exception as e:
                failed_count += 1
                print(f"  ✗ Error deleting file {document.filename}: {e}")
    
    return deleted_count, failed_count


def clear_donor_data(donor_id: int = None, clear_all: bool = False):
    """
    Clear all data related to a donor except the donor record itself.
    
    Args:
        donor_id: ID of the donor to clear data for (if None and not clear_all, will prompt)
        clear_all: If True, clear data for all donors
    """
    # Create session
    SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
    db = SessionLocal()
    
    try:
        if clear_all:
            # Get all donors
            donors = db.query(Donor).all()
            if not donors:
                print("❌ No donors found in database")
                return
            
            print(f"Found {len(donors)} donor(s). Clearing data for all...")
            donor_ids = [donor.id for donor in donors]
        elif donor_id:
            # Verify donor exists
            donor = db.query(Donor).filter(Donor.id == donor_id).first()
            if not donor:
                print(f"❌ Donor with ID {donor_id} not found")
                return
            donor_ids = [donor_id]
            print(f"Clearing data for donor ID {donor_id} ({donor.name}, {donor.unique_donor_id})")
        else:
            print("❌ Please provide a donor_id or use --all flag")
            print("Usage: python scripts/clear_donor_data.py <donor_id>")
            print("       python scripts/clear_donor_data.py --all")
            return
        
        total_deleted = {
            'documents': 0,
            'chunks': 0,
            'culture_results': 0,
            'serology_results': 0,
            'topic_results': 0,
            'component_results': 0,
            'approvals': 0,
            'extractions': 0,
            'extraction_vectors': 0,
            'files_deleted': 0,
            'files_failed': 0
        }
        
        for current_donor_id in donor_ids:
            donor = db.query(Donor).filter(Donor.id == current_donor_id).first()
            print(f"\n{'='*60}")
            print(f"Processing donor ID {current_donor_id}: {donor.name} ({donor.unique_donor_id})")
            print(f"{'='*60}")
            
            # Get all documents for this donor
            documents = db.query(Document).filter(Document.donor_id == current_donor_id).all()
            document_ids = [doc.id for doc in documents]
            
            if documents:
                print(f"\n📄 Found {len(documents)} document(s)")
                
                # Delete document chunks
                chunks_deleted = db.query(DocumentChunk).filter(
                    DocumentChunk.document_id.in_(document_ids)
                ).delete(synchronize_session=False)
                total_deleted['chunks'] += chunks_deleted
                print(f"  ✓ Deleted {chunks_deleted} document chunk(s)")
                
                # Delete culture results
                culture_deleted = db.query(CultureResult).filter(
                    CultureResult.document_id.in_(document_ids)
                ).delete(synchronize_session=False)
                total_deleted['culture_results'] += culture_deleted
                print(f"  ✓ Deleted {culture_deleted} culture result(s)")
                
                # Delete serology results
                serology_deleted = db.query(SerologyResult).filter(
                    SerologyResult.document_id.in_(document_ids)
                ).delete(synchronize_session=False)
                total_deleted['serology_results'] += serology_deleted
                print(f"  ✓ Deleted {serology_deleted} serology result(s)")
                
                # Delete topic results
                topic_deleted = db.query(TopicResult).filter(
                    TopicResult.document_id.in_(document_ids)
                ).delete(synchronize_session=False)
                total_deleted['topic_results'] += topic_deleted
                print(f"  ✓ Deleted {topic_deleted} topic result(s)")
                
                # Delete component results
                component_deleted = db.query(ComponentResult).filter(
                    ComponentResult.document_id.in_(document_ids)
                ).delete(synchronize_session=False)
                total_deleted['component_results'] += component_deleted
                print(f"  ✓ Deleted {component_deleted} component result(s)")
                
                # Delete files from Azure Blob Storage
                print(f"\n🗑️  Deleting files from Azure Blob Storage...")
                try:
                    loop = asyncio.get_event_loop()
                except RuntimeError:
                    loop = asyncio.new_event_loop()
                    asyncio.set_event_loop(loop)
                files_deleted, files_failed = loop.run_until_complete(
                    delete_document_files(documents, db)
                )
                total_deleted['files_deleted'] += files_deleted
                total_deleted['files_failed'] += files_failed
                
                # Delete documents
                docs_deleted = db.query(Document).filter(
                    Document.donor_id == current_donor_id
                ).delete(synchronize_session=False)
                total_deleted['documents'] += docs_deleted
                print(f"  ✓ Deleted {docs_deleted} document record(s)")
            else:
                print("  ℹ No documents found for this donor")
            
            # Delete donor approvals
            approvals_deleted = db.query(DonorApproval).filter(
                DonorApproval.donor_id == current_donor_id
            ).delete(synchronize_session=False)
            total_deleted['approvals'] += approvals_deleted
            if approvals_deleted > 0:
                print(f"  ✓ Deleted {approvals_deleted} donor approval(s)")
            
            # Delete donor extraction vectors
            vectors_deleted = db.query(DonorExtractionVector).filter(
                DonorExtractionVector.donor_id == current_donor_id
            ).delete(synchronize_session=False)
            total_deleted['extraction_vectors'] += vectors_deleted
            if vectors_deleted > 0:
                print(f"  ✓ Deleted {vectors_deleted} extraction vector(s)")
            
            # Delete donor extraction
            extraction_deleted = db.query(DonorExtraction).filter(
                DonorExtraction.donor_id == current_donor_id
            ).delete(synchronize_session=False)
            total_deleted['extractions'] += extraction_deleted
            if extraction_deleted > 0:
                print(f"  ✓ Deleted {extraction_deleted} donor extraction record(s)")
            
            # Commit all deletions for this donor
            db.commit()
            print(f"\n✅ Successfully cleared all data for donor ID {current_donor_id}")
            print(f"   (Donor record preserved)")
        
        # Print summary
        print(f"\n{'='*60}")
        print("SUMMARY")
        print(f"{'='*60}")
        print(f"Documents deleted:        {total_deleted['documents']}")
        print(f"Document chunks deleted:  {total_deleted['chunks']}")
        print(f"Culture results deleted:  {total_deleted['culture_results']}")
        print(f"Serology results deleted: {total_deleted['serology_results']}")
        print(f"Topic results deleted:    {total_deleted['topic_results']}")
        print(f"Component results deleted: {total_deleted['component_results']}")
        print(f"Donor approvals deleted:  {total_deleted['approvals']}")
        print(f"Extraction vectors deleted: {total_deleted['extraction_vectors']}")
        print(f"Donor extractions deleted: {total_deleted['extractions']}")
        print(f"Files deleted from Azure: {total_deleted['files_deleted']}")
        if total_deleted['files_failed'] > 0:
            print(f"Files failed to delete:   {total_deleted['files_failed']} ⚠")
        print(f"\n✅ All donor data cleared successfully!")
        print(f"   (Donor records preserved)")
        
    except Exception as e:
        print(f"❌ Error clearing donor data: {e}")
        import traceback
        traceback.print_exc()
        db.rollback()
    finally:
        db.close()


if __name__ == "__main__":
    if len(sys.argv) < 2:
        print("❌ Please provide a donor_id or use --all flag")
        print("Usage: python scripts/clear_donor_data.py <donor_id>")
        print("       python scripts/clear_donor_data.py --all")
        sys.exit(1)
    
    arg = sys.argv[1]
    
    if arg == "--all":
        # Ask for confirmation
        response = input("⚠️  WARNING: This will clear data for ALL donors. Are you sure? (yes/no): ")
        if response.lower() != "yes":
            print("❌ Operation cancelled")
            sys.exit(0)
        clear_donor_data(clear_all=True)
    else:
        try:
            donor_id = int(arg)
            clear_donor_data(donor_id=donor_id)
        except ValueError:
            print(f"❌ Invalid donor_id: {arg}. Please provide a valid integer.")
            sys.exit(1)

