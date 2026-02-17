"""Background worker: consume from asyncio queue, run extraction pipeline, update DB."""
import asyncio
import logging
import re
from pathlib import Path
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.orm import selectinload

from app.database import async_session_factory
from app.models import Document, Donor
from app.services.compliance import evaluate_eligibility
from app.services.extraction import extract_full_pipeline
from app.services.merger import merge_donor_data

logger = logging.getLogger(__name__)

processing_queue: asyncio.Queue = asyncio.Queue()


def _external_id_from_filename(filename: str) -> str:
    """Derive external_id from filename (e.g. '0042510891 Section 1.pdf' -> '0042510891')."""
    stem = Path(filename).stem
    match = re.match(r"^([0-9]+)", stem)
    return match.group(1) if match else stem or "unknown"


async def _process_document(document_id: UUID) -> None:
    async with async_session_factory() as session:
        result = await session.execute(
            select(Document).where(Document.id == document_id).options(selectinload(Document.donor))
        )
        document = result.scalar_one_or_none()
        if not document:
            logger.warning("Document %s not found", document_id)
            return
        donor = document.donor
        file_path = Path(document.file_path)
        if not file_path.is_file():
            logger.error("File not found: %s", document.file_path)
            document.status = "FAILED"
            await session.commit()
            return
        document.status = "PROCESSING"
        await session.commit()

    try:
        extraction = await asyncio.to_thread(extract_full_pipeline, str(file_path))
    except Exception as e:
        logger.exception("Extraction failed for document %s: %s", document_id, e)
        async with async_session_factory() as session:
            result = await session.execute(select(Document).where(Document.id == document_id))
            doc = result.scalar_one_or_none()
            if doc:
                doc.status = "FAILED"
                await session.commit()
        return

    async with async_session_factory() as session:
        result = await session.execute(
            select(Document).where(Document.id == document_id).options(selectinload(Document.donor))
        )
        document = result.scalar_one()
        donor = document.donor
        master = donor.merged_data or {}
        merged = merge_donor_data(master, extraction)
        status, flags = evaluate_eligibility(merged)
        # Optionally update external_id from extraction if it was a placeholder
        ident = merged.get("Identity") or {}
        for key in ("Donor_ID", "UNOS_ID", "Tissue_ID"):
            val = ident.get(key)
            if val and isinstance(val, str) and val.strip():
                if donor.external_id.startswith("unknown") or not re.match(r"^\d+$", donor.external_id):
                    donor.external_id = val.strip()[:64]
                break
        donor.merged_data = merged
        donor.eligibility_status = status
        donor.flags = flags
        document.raw_extraction = extraction
        document.status = "COMPLETED"
        await session.commit()
    logger.info("Document %s completed; donor %s status=%s", document_id, donor.id, status)


async def worker_process() -> None:
    """Infinite loop: get document id from queue, run pipeline, update DB."""
    while True:
        try:
            document_id: UUID = await processing_queue.get()
            await _process_document(document_id)
        except asyncio.CancelledError:
            raise
        except Exception as e:
            logger.exception("Worker error: %s", e)
        finally:
            processing_queue.task_done()


def start_worker() -> asyncio.Task:
    return asyncio.create_task(worker_process())
