#!/usr/bin/env python3
"""
Script to set all documents for a donor to COMPLETED (processed) status.

This will update all documents for the specified donor to:
- status: COMPLETED
- progress: 100.0

Usage: python scripts/set_all_documents_processed.py <donor_id>
       python scripts/set_all_documents_processed.py --all  # Process all donors
       python scripts/set_all_documents_processed.py <donor_id> --dry-run  # Preview changes
"""
import sys
import os
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from sqlalchemy.orm import sessionmaker
from app.database.database import engine
from app.models.document import Document, DocumentStatus
from app.models.donor import Donor
from datetime import datetime


def set_donor_documents_processed(donor_id: int = None, clear_all: bool = False, dry_run: bool = False):
    """
    Set all documents for a donor to COMPLETED status.
    
    Args:
        donor_id: ID of the donor to process (if None and not clear_all, will prompt)
        clear_all: If True, process documents for all donors
        dry_run: If True, only show what would be changed without applying changes
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
            
            print(f"Found {len(donors)} donor(s). Processing documents for all...")
            donor_ids = [donor.id for donor in donors]
        elif donor_id:
            # Verify donor exists
            donor = db.query(Donor).filter(Donor.id == donor_id).first()
            if not donor:
                print(f"❌ Donor with ID {donor_id} not found")
                return
            donor_ids = [donor_id]
            print(f"Processing documents for donor ID {donor_id} ({donor.name}, {donor.unique_donor_id})")
        else:
            print("❌ Please provide a donor_id or use --all flag")
            print("Usage: python scripts/set_all_documents_processed.py <donor_id>")
            print("       python scripts/set_all_documents_processed.py --all")
            return
        
        total_updated = 0
        
        for current_donor_id in donor_ids:
            donor = db.query(Donor).filter(Donor.id == current_donor_id).first()
            print(f"\n{'='*60}")
            print(f"Processing donor ID {current_donor_id}: {donor.name} ({donor.unique_donor_id})")
            print(f"{'='*60}")
            
            # Get all documents for this donor
            documents = db.query(Document).filter(Document.donor_id == current_donor_id).all()
            
            if not documents:
                print("ℹ No documents found for this donor")
                continue
            
            print(f"\n📄 Found {len(documents)} document(s) for this donor")
            
            # Count documents by current status
            status_counts = {}
            for doc in documents:
                status = doc.status.value if doc.status else "None"
                status_counts[status] = status_counts.get(status, 0) + 1
            
            print("Current document status distribution:")
            for status, count in sorted(status_counts.items()):
                print(f"  {status}: {count}")
            
            # Filter documents that are not already COMPLETED
            documents_to_update = [
                doc for doc in documents 
                if doc.status != DocumentStatus.COMPLETED
            ]
            
            if not documents_to_update:
                print("\n✅ All documents for this donor are already COMPLETED")
                continue
            
            print(f"\n📝 Documents to update: {len(documents_to_update)}")
            
            if dry_run:
                print("\n🔍 DRY RUN MODE - No changes will be applied")
                print("\nDocuments that would be updated:")
                for doc in documents_to_update:
                    print(f"  - ID {doc.id}: {doc.original_filename} (current status: {doc.status.value})")
                print(f"\nWould update {len(documents_to_update)} document(s) to COMPLETED status")
                total_updated += len(documents_to_update)
                continue
            
            # Update documents
            updated_count = 0
            for doc in documents_to_update:
                doc.status = DocumentStatus.COMPLETED
                doc.progress = 100.0
                doc.updated_at = datetime.now()
                updated_count += 1
            
            # Commit changes for this donor
            db.commit()
            total_updated += updated_count
            
            print(f"\n✅ Successfully updated {updated_count} document(s) to COMPLETED status for donor ID {current_donor_id}")
            print(f"   All updated documents now have status: COMPLETED and progress: 100.0")
        
        if not dry_run:
            print(f"\n{'='*60}")
            print("SUMMARY")
            print(f"{'='*60}")
            print(f"Total documents updated: {total_updated}")
            print(f"✅ All documents processed successfully!")
        else:
            print(f"\n{'='*60}")
            print("DRY RUN SUMMARY")
            print(f"{'='*60}")
            print(f"Total documents that would be updated: {total_updated}")
        
    except Exception as e:
        print(f"❌ Error updating documents: {e}")
        import traceback
        traceback.print_exc()
        db.rollback()
    finally:
        db.close()


if __name__ == "__main__":
    dry_run = "--dry-run" in sys.argv or "-d" in sys.argv
    
    # Remove dry-run flags from argv for parsing
    args = [arg for arg in sys.argv[1:] if arg not in ["--dry-run", "-d"]]
    
    if dry_run:
        print("🔍 Running in DRY RUN mode - no changes will be applied\n")
    
    if len(args) < 1:
        print("❌ Please provide a donor_id or use --all flag")
        print("Usage: python scripts/set_all_documents_processed.py <donor_id>")
        print("       python scripts/set_all_documents_processed.py --all")
        print("       python scripts/set_all_documents_processed.py <donor_id> --dry-run")
        sys.exit(1)
    
    arg = args[0]
    
    if arg == "--all":
        # Ask for confirmation
        response = input("⚠️  WARNING: This will update documents for ALL donors. Are you sure? (yes/no): ")
        if response.lower() != "yes":
            print("❌ Operation cancelled")
            sys.exit(0)
        set_donor_documents_processed(clear_all=True, dry_run=dry_run)
    else:
        try:
            donor_id = int(arg)
            set_donor_documents_processed(donor_id=donor_id, dry_run=dry_run)
        except ValueError:
            print(f"❌ Invalid donor_id: {arg}. Please provide a valid integer.")
            sys.exit(1)

