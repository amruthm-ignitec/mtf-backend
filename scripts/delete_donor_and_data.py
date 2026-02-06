#!/usr/bin/env python3
"""
Script to completely delete a single donor AND all of its related data/files.

This will delete, for the specified donor:
- All documents and their associated data (chunks, laboratory results, criteria evaluations)
- All donor eligibility records
- All donor approvals
- All files from Azure Blob Storage
- The donor record itself (last, after all FKs are cleared)

Usage:
    python scripts/delete_donor_and_data.py <donor_id>
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
from app.services.azure_service import azure_blob_service


async def delete_document_files(documents):
    """Delete document files for this donor from Azure Blob Storage."""
    deleted_count = 0
    failed_count = 0

    for document in documents:
        if not document.filename:
            continue

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


def delete_donor_and_data(donor_id: int):
    """
    Delete a donor and all associated data/files.

    Args:
        donor_id: ID of the donor to delete
    """
    SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
    db = SessionLocal()

    try:
        donor = db.query(Donor).filter(Donor.id == donor_id).first()
        if not donor:
            print(f"❌ Donor with ID {donor_id} not found")
            return

        print(f"{'=' * 60}")
        print(f"Deleting donor ID {donor.id}: {donor.name} ({donor.unique_donor_id})")
        print(f"{'=' * 60}")

        # Get all documents for this donor
        documents = db.query(Document).filter(Document.donor_id == donor.id).all()
        document_ids = [doc.id for doc in documents]

        total_deleted = {
            "documents": 0,
            "chunks": 0,
            "laboratory_results": 0,
            "criteria_evaluations": 0,
            "donor_eligibility": 0,
            "approvals": 0,
            "files_deleted": 0,
            "files_failed": 0,
            "donors": 0,
        }

        if documents:
            print(f"\n📄 Found {len(documents)} document(s) for this donor")

            # Delete document chunks first
            chunks_deleted = (
                db.query(DocumentChunk)
                .filter(DocumentChunk.document_id.in_(document_ids))
                .delete(synchronize_session=False)
            )
            total_deleted["chunks"] += chunks_deleted
            print(f"  ✓ Deleted {chunks_deleted} document chunk(s)")

            # Delete criteria evaluations that reference these documents
            criteria_eval_deleted = (
                db.query(CriteriaEvaluation)
                .filter(CriteriaEvaluation.document_id.in_(document_ids))
                .delete(synchronize_session=False)
            )
            total_deleted["criteria_evaluations"] += criteria_eval_deleted
            print(f"  ✓ Deleted {criteria_eval_deleted} criteria evaluation(s) linked to documents")

            # Delete laboratory results
            lab_results_deleted = (
                db.query(LaboratoryResult)
                .filter(LaboratoryResult.document_id.in_(document_ids))
                .delete(synchronize_session=False)
            )
            total_deleted["laboratory_results"] += lab_results_deleted
            print(f"  ✓ Deleted {lab_results_deleted} laboratory result(s)")

            # Delete files from Azure Blob Storage
            print("\n🗑️  Deleting files from Azure Blob Storage...")
            try:
                loop = asyncio.get_event_loop()
            except RuntimeError:
                loop = asyncio.new_event_loop()
                asyncio.set_event_loop(loop)

            files_deleted, files_failed = loop.run_until_complete(delete_document_files(documents))
            total_deleted["files_deleted"] += files_deleted
            total_deleted["files_failed"] += files_failed

            # Delete documents
            docs_deleted = (
                db.query(Document)
                .filter(Document.donor_id == donor.id)
                .delete(synchronize_session=False)
            )
            total_deleted["documents"] += docs_deleted
            print(f"  ✓ Deleted {docs_deleted} document record(s)")
        else:
            print("  ℹ No documents found for this donor")

        # Delete donor-level data that may not reference documents
        criteria_eval_no_doc_deleted = (
            db.query(CriteriaEvaluation)
            .filter(CriteriaEvaluation.donor_id == donor.id, CriteriaEvaluation.document_id.is_(None))
            .delete(synchronize_session=False)
        )
        if criteria_eval_no_doc_deleted > 0:
            total_deleted["criteria_evaluations"] += criteria_eval_no_doc_deleted
            print(f"  ✓ Deleted {criteria_eval_no_doc_deleted} criteria evaluation(s) without document reference")

        eligibility_deleted = (
            db.query(DonorEligibility)
            .filter(DonorEligibility.donor_id == donor.id)
            .delete(synchronize_session=False)
        )
        total_deleted["donor_eligibility"] += eligibility_deleted
        if eligibility_deleted > 0:
            print(f"  ✓ Deleted {eligibility_deleted} donor eligibility record(s)")

        approvals_deleted = (
            db.query(DonorApproval)
            .filter(DonorApproval.donor_id == donor.id)
            .delete(synchronize_session=False)
        )
        total_deleted["approvals"] += approvals_deleted
        if approvals_deleted > 0:
            print(f"  ✓ Deleted {approvals_deleted} donor approval(s)")

        # Finally, delete the donor record itself
        db.delete(donor)
        total_deleted["donors"] += 1
        print("\n🧾 Deleting donor record...")

        # Commit all deletions
        db.commit()

        print(f"\n✅ Successfully deleted donor ID {donor_id} and all associated data")
        print(f"\n{'=' * 60}")
        print("SUMMARY")
        print(f"{'=' * 60}")
        print(f"Donor records deleted:        {total_deleted['donors']}")
        print(f"Documents deleted:            {total_deleted['documents']}")
        print(f"Document chunks deleted:      {total_deleted['chunks']}")
        print(f"Laboratory results deleted:   {total_deleted['laboratory_results']}")
        print(f"Criteria evaluations deleted: {total_deleted['criteria_evaluations']}")
        print(f"Donor eligibility deleted:    {total_deleted['donor_eligibility']}")
        print(f"Donor approvals deleted:      {total_deleted['approvals']}")
        print(f"Files deleted from Azure:     {total_deleted['files_deleted']}")
        if total_deleted["files_failed"] > 0:
            print(f"Files failed to delete:       {total_deleted['files_failed']} ⚠")

    except Exception as e:
        print(f"❌ Error deleting donor and data: {e}")
        import traceback

        traceback.print_exc()
        db.rollback()
    finally:
        db.close()


if __name__ == "__main__":
    if len(sys.argv) != 2:
        print("❌ Please provide a donor_id")
        print("Usage: python scripts/delete_donor_and_data.py <donor_id>")
        sys.exit(1)

    try:
        donor_id_arg = int(sys.argv[1])
    except ValueError:
        print(f"❌ Invalid donor_id: {sys.argv[1]}. Please provide a valid integer.")
        sys.exit(1)

    confirm = input(
        f"⚠️  This will PERMANENTLY DELETE donor ID {donor_id_arg} and all related data/files. "
        "Type 'DELETE' to confirm: "
    )
    if confirm != "DELETE":
        print("❌ Operation cancelled")
        sys.exit(0)

    delete_donor_and_data(donor_id_arg)


