#!/usr/bin/env python3
"""
Script to completely reset the database by removing all donors and their associated data.
This will delete:
- All donors and their records
- All documents and their associated data (chunks, laboratory results, criteria evaluations)
- All donor eligibility records
- All donor approvals
- All donor feedback
- All files from Azure Blob Storage

This script preserves:
- User accounts (admin and regular users)
- System settings
- Platform feedback

⚠️  WARNING: This is a destructive operation that cannot be undone!

Usage: python scripts/reset_database.py
       python scripts/reset_database.py --confirm  # Skip confirmation prompt
"""
import sys
import os
import asyncio
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from sqlalchemy.orm import sessionmaker
from app.database.database import engine
from app.models.donor import Donor
from app.models.document import Document
from app.models.document_chunk import DocumentChunk
from app.models.laboratory_result import LaboratoryResult
from app.models.criteria_evaluation import CriteriaEvaluation
from app.models.donor_eligibility import DonorEligibility
from app.models.donor_approval import DonorApproval
from app.models.donor_feedback import DonorFeedback
from app.services.azure_service import azure_blob_service


async def delete_all_document_files(db):
    """Delete all document files from Azure Blob Storage."""
    deleted_count = 0
    failed_count = 0
    
    # Get all documents
    documents = db.query(Document).all()
    
    if not documents:
        print("  ℹ No documents found to delete from Azure")
        return deleted_count, failed_count
    
    print(f"  📄 Found {len(documents)} document(s) to delete from Azure...")
    
    for document in documents:
        if document.filename:
            try:
                success = await azure_blob_service.delete_file(document.filename)
                if success:
                    deleted_count += 1
                    if deleted_count % 10 == 0:
                        print(f"    ✓ Deleted {deleted_count} files...")
                else:
                    failed_count += 1
                    print(f"    ⚠ Failed to delete file from Azure: {document.filename}")
            except Exception as e:
                failed_count += 1
                print(f"    ✗ Error deleting file {document.filename}: {e}")
    
    return deleted_count, failed_count


def reset_database(skip_confirmation: bool = False):
    """
    Completely reset the database by removing all donors and their data.
    
    Args:
        skip_confirmation: If True, skip the confirmation prompt
    """
    # Create session
    SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
    db = SessionLocal()
    
    try:
        # Count existing data
        donor_count = db.query(Donor).count()
        document_count = db.query(Document).count()
        chunk_count = db.query(DocumentChunk).count()
        lab_result_count = db.query(LaboratoryResult).count()
        criteria_eval_count = db.query(CriteriaEvaluation).count()
        eligibility_count = db.query(DonorEligibility).count()
        approval_count = db.query(DonorApproval).count()
        feedback_count = db.query(DonorFeedback).count()
        
        print("=" * 60)
        print("DATABASE RESET - Current Data Summary")
        print("=" * 60)
        print(f"Donors:                    {donor_count}")
        print(f"Documents:                 {document_count}")
        print(f"Document chunks:           {chunk_count}")
        print(f"Laboratory results:        {lab_result_count}")
        print(f"Criteria evaluations:      {criteria_eval_count}")
        print(f"Donor eligibility records: {eligibility_count}")
        print(f"Donor approvals:           {approval_count}")
        print(f"Donor feedback:            {feedback_count}")
        print("=" * 60)
        
        if donor_count == 0:
            print("✅ Database is already empty. Nothing to reset.")
            return
        
        # Confirmation prompt
        if not skip_confirmation:
            print("\n⚠️  WARNING: This will PERMANENTLY DELETE all donors and their data!")
            print("   This operation CANNOT be undone.")
            print("\n   The following will be deleted:")
            print("   - All donor records")
            print("   - All documents and files")
            print("   - All associated data (chunks, lab results, evaluations, etc.)")
            print("   - All files from Azure Blob Storage")
            print("\n   The following will be preserved:")
            print("   - User accounts")
            print("   - System settings")
            print("   - Platform feedback")
            
            response = input("\n   Are you absolutely sure you want to proceed? (type 'RESET' to confirm): ")
            if response != "RESET":
                print("❌ Operation cancelled")
                return
        
        print("\n" + "=" * 60)
        print("Starting database reset...")
        print("=" * 60)
        
        # Step 1: Delete all document chunks
        print("\n1️⃣  Deleting document chunks...")
        chunks_deleted = db.query(DocumentChunk).delete(synchronize_session=False)
        print(f"   ✓ Deleted {chunks_deleted} document chunk(s)")
        
        # Step 2: Delete criteria evaluations
        print("\n2️⃣  Deleting criteria evaluations...")
        criteria_eval_deleted = db.query(CriteriaEvaluation).delete(synchronize_session=False)
        print(f"   ✓ Deleted {criteria_eval_deleted} criteria evaluation(s)")
        
        # Step 3: Delete laboratory results
        print("\n3️⃣  Deleting laboratory results...")
        lab_results_deleted = db.query(LaboratoryResult).delete(synchronize_session=False)
        print(f"   ✓ Deleted {lab_results_deleted} laboratory result(s)")
        
        # Step 4: Delete files from Azure Blob Storage
        print("\n4️⃣  Deleting files from Azure Blob Storage...")
        try:
            loop = asyncio.get_event_loop()
        except RuntimeError:
            loop = asyncio.new_event_loop()
            asyncio.set_event_loop(loop)
        
        files_deleted, files_failed = loop.run_until_complete(
            delete_all_document_files(db)
        )
        print(f"   ✓ Deleted {files_deleted} file(s) from Azure")
        if files_failed > 0:
            print(f"   ⚠ Failed to delete {files_failed} file(s) from Azure")
        
        # Step 5: Delete documents
        print("\n5️⃣  Deleting documents...")
        docs_deleted = db.query(Document).delete(synchronize_session=False)
        print(f"   ✓ Deleted {docs_deleted} document record(s)")
        
        # Step 6: Delete donor eligibility records
        print("\n6️⃣  Deleting donor eligibility records...")
        eligibility_deleted = db.query(DonorEligibility).delete(synchronize_session=False)
        print(f"   ✓ Deleted {eligibility_deleted} donor eligibility record(s)")
        
        # Step 7: Delete donor approvals
        print("\n7️⃣  Deleting donor approvals...")
        approvals_deleted = db.query(DonorApproval).delete(synchronize_session=False)
        print(f"   ✓ Deleted {approvals_deleted} donor approval(s)")
        
        # Step 8: Delete donor feedback
        print("\n8️⃣  Deleting donor feedback...")
        feedback_deleted = db.query(DonorFeedback).delete(synchronize_session=False)
        print(f"   ✓ Deleted {feedback_deleted} donor feedback record(s)")
        
        # Step 9: Delete donors (last, after all foreign key dependencies are removed)
        print("\n9️⃣  Deleting donors...")
        donors_deleted = db.query(Donor).delete(synchronize_session=False)
        print(f"   ✓ Deleted {donors_deleted} donor record(s)")
        
        # Commit all deletions
        db.commit()
        
        # Final summary
        print("\n" + "=" * 60)
        print("✅ DATABASE RESET COMPLETE")
        print("=" * 60)
        print(f"Donors deleted:            {donors_deleted}")
        print(f"Documents deleted:         {docs_deleted}")
        print(f"Document chunks deleted:    {chunks_deleted}")
        print(f"Laboratory results deleted: {lab_results_deleted}")
        print(f"Criteria evaluations deleted: {criteria_eval_deleted}")
        print(f"Donor eligibility deleted:  {eligibility_deleted}")
        print(f"Donor approvals deleted:    {approvals_deleted}")
        print(f"Donor feedback deleted:     {feedback_deleted}")
        print(f"Files deleted from Azure:   {files_deleted}")
        if files_failed > 0:
            print(f"Files failed to delete:     {files_failed} ⚠")
        print("\n✅ Database has been reset. Ready for fresh uploads!")
        
    except Exception as e:
        print(f"\n❌ Error resetting database: {e}")
        import traceback
        traceback.print_exc()
        db.rollback()
        sys.exit(1)
    finally:
        db.close()


if __name__ == "__main__":
    skip_confirmation = "--confirm" in sys.argv or "-y" in sys.argv
    
    try:
        reset_database(skip_confirmation=skip_confirmation)
    except KeyboardInterrupt:
        print("\n\n❌ Operation cancelled by user")
        sys.exit(1)

