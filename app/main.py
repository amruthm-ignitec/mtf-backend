"""FastAPI app: upload, donors, document status. Worker started on lifespan."""
import asyncio
import re
from contextlib import asynccontextmanager
from pathlib import Path
from uuid import UUID

from fastapi import Depends, FastAPI, File, HTTPException, Query, UploadFile, Response
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.config import get_settings
from app.database import async_session_factory, init_db
from app.models import Document, Donor
from app.worker import processing_queue, start_worker


async def get_db() -> AsyncSession:
    async with async_session_factory() as session:
        yield session


@asynccontextmanager
async def lifespan(app: FastAPI):
    await init_db()
    task = start_worker()
    yield
    task.cancel()
    try:
        await task
    except asyncio.CancelledError:
        pass


app = FastAPI(title="DonorIQ", lifespan=lifespan)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:5173", "http://localhost:3000", "http://127.0.0.1:5173"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


def _donor_list_item(donor: Donor) -> dict:
    """Build list item with optional name/age from merged_data."""
    name = f"Donor {donor.external_id}"
    age = None
    if donor.merged_data and isinstance(donor.merged_data, dict):
        identity = donor.merged_data.get("Identity") or {}
        if identity.get("Donor_ID"):
            name = str(identity.get("Donor_ID", name))
        if identity.get("Age") is not None:
            try:
                age = int(identity["Age"])
            except (TypeError, ValueError):
                pass
    return {
        "id": str(donor.id),
        "external_id": donor.external_id,
        "name": name,
        "age": age,
        "eligibility_status": donor.eligibility_status,
        "flags": donor.flags,
    }


def _external_id_from_filename(filename: str) -> str:
    stem = Path(filename).stem
    match = re.match(r"^([0-9]+)", stem)
    return match.group(1) if match else stem or "unknown"


@app.post("/upload")
async def upload(
    file: UploadFile = File(...),
    db: AsyncSession = Depends(get_db),
):
    """Save file, create donor + document, add document to processing queue."""
    settings = get_settings()
    upload_dir = Path(settings.upload_dir)
    upload_dir.mkdir(parents=True, exist_ok=True)
    if not file.filename or not file.filename.lower().endswith(".pdf"):
        raise HTTPException(status_code=400, detail="PDF file required")
    contents = await file.read()
    max_bytes = settings.max_file_size_mb * 1024 * 1024
    if len(contents) > max_bytes:
        raise HTTPException(status_code=400, detail="File too large")
    safe_name = file.filename or "document.pdf"
    file_path = upload_dir / safe_name
    # Deduplicate if same filename
    if file_path.exists():
        stem = file_path.stem
        suffix = file_path.suffix
        counter = 1
        while file_path.exists():
            file_path = upload_dir / f"{stem}_{counter}{suffix}"
            counter += 1
    file_path.write_bytes(contents)
    external_id = _external_id_from_filename(safe_name)
    result = await db.execute(select(Donor).where(Donor.external_id == external_id))
    donor = result.scalar_one_or_none()
    if not donor:
        donor = Donor(external_id=external_id)
        db.add(donor)
        await db.flush()
    document = Document(
        donor_id=donor.id,
        filename=safe_name,
        file_path=str(file_path.resolve()),
        status="QUEUED",
    )
    db.add(document)
    await db.commit()
    await db.refresh(document)
    processing_queue.put_nowait(document.id)
    return {"document_id": str(document.id), "donor_id": str(donor.id), "status": "QUEUED"}


@app.get("/donors/")
async def list_donors(
    skip: int = Query(0, ge=0),
    limit: int = Query(100, ge=1, le=500),
    db: AsyncSession = Depends(get_db),
):
    """List donors with skip/limit. Each item includes id, external_id, name, age, eligibility_status, flags."""
    result = await db.execute(select(Donor).offset(skip).limit(limit).order_by(Donor.id))
    donors = result.scalars().all()
    return [_donor_list_item(d) for d in donors]


@app.get("/donors/queue/details")
async def get_queue_details(db: AsyncSession = Depends(get_db)):
    """Return queue items for donors that have at least one document."""
    result = await db.execute(
        select(Donor)
        .where(Donor.id.in_(select(Document.donor_id).distinct()))
        .options(selectinload(Donor.documents))
    )
    donors = result.scalars().unique().all()
    items = []
    for donor in donors:
        docs = donor.documents or []
        processing_status = "pending"
        if docs:
            statuses = [d.status for d in docs]
            if any(s == "PROCESSING" or s == "QUEUED" for s in statuses):
                processing_status = "processing" if "PROCESSING" in statuses else "queued"
            elif all(s == "COMPLETED" for s in statuses):
                processing_status = "completed"
            elif any(s == "FAILED" for s in statuses):
                processing_status = "failed" if all(s == "FAILED" for s in statuses) else "completed"
        name = f"Donor {donor.external_id}"
        if donor.merged_data and isinstance(donor.merged_data, dict):
            identity = (donor.merged_data.get("Identity") or {}).get("Donor_ID")
            if identity:
                name = str(identity)
        inv = (donor.merged_data or {}).get("Document_Inventory") or {}
        required_documents = [
            {"id": k, "name": k, "type": "document", "label": k.replace("Has_", "").replace("_", " "), "status": "completed" if inv.get(k) else "missing", "isRequired": True, "pageCount": 0}
            for k in ("Has_Authorization", "Has_DRAI", "Has_Infectious_Disease_Labs")
        ]
        critical_findings = [
            {"type": "flag", "severity": "high", "automaticRejection": True, "description": f, "source": {"documentId": "", "pageNumber": "", "confidence": 0}}
            for f in (donor.flags or [])
        ]
        items.append({
            "id": str(donor.id),
            "donorName": name,
            "processingStatus": processing_status,
            "criticalFindings": critical_findings,
            "requiredDocuments": required_documents,
        })
    return items


@app.get("/donors/{donor_id}")
async def get_donor(donor_id: UUID, db: AsyncSession = Depends(get_db)):
    """Return merged_data, eligibility_status, and flags."""
    result = await db.execute(select(Donor).where(Donor.id == donor_id))
    donor = result.scalar_one_or_none()
    if not donor:
        raise HTTPException(status_code=404, detail="Donor not found")
    return {
        "id": str(donor.id),
        "external_id": donor.external_id,
        "merged_data": donor.merged_data,
        "eligibility_status": donor.eligibility_status,
        "flags": donor.flags,
    }


@app.get("/documents/donor/{donor_id}")
async def list_documents_by_donor(donor_id: UUID, db: AsyncSession = Depends(get_db)):
    """List documents for a donor."""
    result = await db.execute(select(Document).where(Document.donor_id == donor_id))
    documents = result.scalars().all()
    return [
        {"id": str(d.id), "donor_id": str(d.donor_id), "filename": d.filename, "status": d.status}
        for d in documents
    ]


@app.get("/documents/{document_id}/status")
async def get_document_status(document_id: UUID, db: AsyncSession = Depends(get_db)):
    """Return document processing status (and optional progress)."""
    result = await db.execute(select(Document).where(Document.id == document_id))
    document = result.scalar_one_or_none()
    if not document:
        raise HTTPException(status_code=404, detail="Document not found")
    return {
        "id": str(document.id),
        "donor_id": str(document.donor_id),
        "filename": document.filename,
        "status": document.status,
    }


@app.get("/documents/{document_id}/pdf")
async def get_document_pdf(document_id: UUID, db: AsyncSession = Depends(get_db)):
    """Stream PDF file from local storage."""
    result = await db.execute(select(Document).where(Document.id == document_id))
    document = result.scalar_one_or_none()
    if not document:
        raise HTTPException(status_code=404, detail="Document not found")
    path = Path(document.file_path)
    if not path.is_file():
        raise HTTPException(status_code=404, detail="File not found")
    return FileResponse(path=document.file_path, media_type="application/pdf", filename=document.filename)


@app.delete("/documents/{document_id}")
async def delete_document(document_id: UUID, db: AsyncSession = Depends(get_db)):
    """Delete document record and file on disk."""
    result = await db.execute(select(Document).where(Document.id == document_id))
    document = result.scalar_one_or_none()
    if not document:
        raise HTTPException(status_code=404, detail="Document not found")
    path = Path(document.file_path)
    if path.is_file():
        try:
            path.unlink()
        except OSError:
            pass
    await db.delete(document)
    await db.commit()
    return Response(status_code=204)
