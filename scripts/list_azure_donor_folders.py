#!/usr/bin/env python3
"""
Script to list donor folders from Azure Blob Storage.
Lists DNC/ and Compliant/ folders with their donor subfolders and documents.

Usage: python scripts/list_azure_donor_folders.py
"""
import sys
import os
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app.services.azure_service import azure_blob_service
from app.core.config import settings


def list_azure_folders():
    """List all donor folders from Azure Blob Storage."""
    print("=" * 60)
    print("Azure Blob Storage Donor Folder Listing")
    print("=" * 60)
    
    # Check if Azure is enabled
    if not azure_blob_service.is_enabled():
        print("❌ Azure Blob Storage is not configured or not enabled")
        print("   Please check your environment variables:")
        print("   - AZURE_STORAGE_ACCOUNT_NAME")
        print("   - AZURE_STORAGE_ACCOUNT_KEY")
        print("   - AZURE_STORAGE_CONTAINER_NAME")
        return
    
    print(f"✓ Azure Blob Storage Connection: Connected")
    print(f"  Container: {azure_blob_service.container_name}")
    print()
    
    # List parent folders (DNC/ and Compliant/)
    parent_folders = ["DNC/", "Compliant/"]
    total_donor_folders = 0
    total_documents = 0
    
    print("Found folders:")
    print()
    
    for parent_folder in parent_folders:
        # List blobs with this prefix
        blobs = azure_blob_service.list_blobs_by_prefix(parent_folder)
        
        if not blobs:
            print(f"  {parent_folder}")
            print(f"    (empty)")
            print()
            continue
        
        print(f"  {parent_folder}")
        
        # Group blobs by donor folder
        donor_folders = {}
        for blob_name in blobs:
            # Extract donor folder name (e.g., "DNC/donor_001/" from "DNC/donor_001/doc1.pdf")
            parts = blob_name[len(parent_folder):].split('/')
            if len(parts) >= 2:
                donor_folder = parts[0]
                document_name = '/'.join(parts[1:])
                
                if donor_folder not in donor_folders:
                    donor_folders[donor_folder] = []
                donor_folders[donor_folder].append(document_name)
        
        # Display donor folders
        for donor_folder, documents in sorted(donor_folders.items()):
            print(f"    - {donor_folder}/")
            for doc in sorted(documents):
                print(f"      - {doc}")
            total_donor_folders += 1
            total_documents += len(documents)
        
        print()
    
    print("=" * 60)
    print(f"Summary:")
    print(f"  Parent folders: {len(parent_folders)}")
    print(f"  Donor folders: {total_donor_folders}")
    print(f"  Documents: {total_documents}")
    print("=" * 60)


if __name__ == "__main__":
    try:
        list_azure_folders()
    except Exception as e:
        print(f"❌ Error listing folders: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)

