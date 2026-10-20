import uuid
from datetime import date, datetime
from typing import Any

from sqlalchemy import (
    BigInteger,
    Boolean,
    CheckConstraint,
    Date,
    DateTime,
    ForeignKey,
    Identity,
    Index,
    Integer,
    SmallInteger,
    String,
    Text,
    UniqueConstraint,
    Uuid,
    false,
    func,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base, CreatedAtMixin, TimestampMixin, str_enum
from app.models.enums import Disposition


class Opportunity(TimestampMixin, Base):
    """Canonical work item: one diagnosis for a member in a payer/provider/year context.

    Several source records (MAO-004, gap report, chart audit) may corroborate the same
    opportunity; they attach as SourceRecord rows instead of creating duplicate work.
    """

    __tablename__ = "opportunities"

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=uuid.uuid4)
    member_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("members.id"), nullable=False)
    payer_id: Mapped[int] = mapped_column(ForeignKey("payers.id"), nullable=False)
    provider_id: Mapped[int] = mapped_column(ForeignKey("providers.id"), nullable=False)
    performance_year: Mapped[int] = mapped_column(SmallInteger, nullable=False)
    icd10_code: Mapped[str] = mapped_column(String(16), nullable=False)
    icd10_description: Mapped[str | None] = mapped_column(String(500), nullable=True)

    # Canonical HCC only when all non-empty source assertions agree; otherwise NULL + conflict.
    hcc_code: Mapped[str | None] = mapped_column(String(16), nullable=True)
    hcc_description: Mapped[str | None] = mapped_column(String(500), nullable=True)
    hcc_conflict: Mapped[bool] = mapped_column(Boolean, nullable=False, server_default=false())

    current_disposition: Mapped[Disposition] = mapped_column(
        str_enum(Disposition, "disposition"), nullable=False, default=Disposition.OPEN
    )
    current_note: Mapped[str | None] = mapped_column(Text, nullable=True)
    disposition_version: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    last_disposition_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    last_disposition_by: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("users.id"), nullable=True
    )

    __table_args__ = (
        UniqueConstraint(
            "member_id",
            "payer_id",
            "provider_id",
            "performance_year",
            "icd10_code",
            name="uq_opportunity_business_key",
        ),
        CheckConstraint("performance_year BETWEEN 2000 AND 2100", name="performance_year_range"),
        Index(
            "ix_opp_provider_year_status_member",
            "provider_id",
            "performance_year",
            "current_disposition",
            "member_id",
        ),
        Index("ix_opp_member_provider", "member_id", "provider_id"),
        Index("ix_opp_payer_status_member", "payer_id", "current_disposition", "member_id"),
    )


class SourceRecord(CreatedAtMixin, Base):
    """Immutable provenance: one imported CSV row, as reported, linked to its opportunity."""

    __tablename__ = "source_records"

    id: Mapped[int] = mapped_column(BigInteger, Identity(), primary_key=True)
    upload_batch_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("upload_batches.id"), nullable=False, index=True
    )
    opportunity_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("opportunities.id"), nullable=False
    )
    source_file: Mapped[str] = mapped_column(String(255), nullable=False)
    source_row_number: Mapped[int] = mapped_column(Integer, nullable=False)
    row_fingerprint: Mapped[str] = mapped_column(String(64), nullable=False)
    policy_number: Mapped[str] = mapped_column(String(64), nullable=False)
    initiative: Mapped[str] = mapped_column(String(64), nullable=False)
    evidence: Mapped[str | None] = mapped_column(Text, nullable=True)
    last_dos: Mapped[date | None] = mapped_column(Date, nullable=True)
    reported_hcc_code: Mapped[str | None] = mapped_column(String(16), nullable=True)
    reported_hcc_description: Mapped[str | None] = mapped_column(String(500), nullable=True)
    raw_payload: Mapped[dict[str, Any]] = mapped_column(JSONB, nullable=False)

    __table_args__ = (
        UniqueConstraint("source_file", "row_fingerprint", name="uq_source_file_fingerprint"),
        Index("ix_source_initiative_opportunity", "initiative", "opportunity_id"),
        Index("ix_source_opportunity_initiative", "opportunity_id", "initiative"),
    )


class DispositionHistory(Base):
    """Append-only audit trail. The application never updates or deletes these rows."""

    __tablename__ = "disposition_history"

    id: Mapped[int] = mapped_column(BigInteger, Identity(), primary_key=True)
    opportunity_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("opportunities.id"), nullable=False
    )
    changed_by: Mapped[uuid.UUID] = mapped_column(ForeignKey("users.id"), nullable=False)
    changed_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    old_status: Mapped[Disposition] = mapped_column(
        str_enum(Disposition, "history_old_status"), nullable=False
    )
    new_status: Mapped[Disposition] = mapped_column(
        str_enum(Disposition, "history_new_status"), nullable=False
    )
    note: Mapped[str] = mapped_column(Text, nullable=False)
    old_version: Mapped[int] = mapped_column(Integer, nullable=False)
    new_version: Mapped[int] = mapped_column(Integer, nullable=False)

    __table_args__ = (
        CheckConstraint("new_version = old_version + 1", name="version_increments"),
        CheckConstraint("length(btrim(note)) > 0", name="note_not_blank"),
        Index(
            "ix_history_opp_changed",
            "opportunity_id",
            changed_at.desc(),
            id.desc(),
        ),
    )
