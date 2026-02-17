"""SQLAlchemy models: donors, documents."""
import uuid

from sqlalchemy import ARRAY, ForeignKey, String, Text
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database import Base


class Donor(Base):
    __tablename__ = "donors"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        primary_key=True,
        default=uuid.uuid4,
    )
    external_id: Mapped[str] = mapped_column(String(64), unique=True, nullable=False, index=True)
    merged_data: Mapped[dict | None] = mapped_column(JSONB, nullable=True)
    eligibility_status: Mapped[str] = mapped_column(
        String(32),
        nullable=False,
        default="PENDING",
    )  # ELIGIBLE, REVIEW, PENDING
    flags: Mapped[list[str]] = mapped_column(ARRAY(Text), nullable=False, default=list)

    documents: Mapped[list["Document"]] = relationship("Document", back_populates="donor")


class Document(Base):
    __tablename__ = "documents"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        primary_key=True,
        default=uuid.uuid4,
    )
    donor_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("donors.id", ondelete="CASCADE"),
        nullable=False,
    )
    filename: Mapped[str] = mapped_column(String(512), nullable=False)
    file_path: Mapped[str] = mapped_column(String(1024), nullable=False)  # local path for POC
    status: Mapped[str] = mapped_column(
        String(32),
        nullable=False,
        default="QUEUED",
    )  # QUEUED, PROCESSING, COMPLETED, FAILED
    raw_extraction: Mapped[dict | None] = mapped_column(JSONB, nullable=True)

    donor: Mapped["Donor"] = relationship("Donor", back_populates="documents")
