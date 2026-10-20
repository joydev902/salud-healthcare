import uuid
from datetime import date

from sqlalchemy import (
    BigInteger,
    Date,
    ForeignKey,
    Identity,
    Index,
    String,
    UniqueConstraint,
    Uuid,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import Base, CreatedAtMixin, TimestampMixin


class Member(TimestampMixin, Base):
    """Canonical person, keyed by the internal member_id (not by payer policy)."""

    __tablename__ = "members"

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=uuid.uuid4)
    external_member_id: Mapped[str] = mapped_column(String(64), nullable=False, unique=True)
    member_name: Mapped[str] = mapped_column(String(200), nullable=False)
    date_of_birth: Mapped[date | None] = mapped_column(Date, nullable=True)

    policies: Mapped[list["MemberPolicy"]] = relationship(back_populates="member", lazy="raise")

    # Trigram indexes serve the queue's case-insensitive member search (ILIKE).
    __table_args__ = (
        Index(
            "ix_members_name_trgm",
            "member_name",
            postgresql_using="gin",
            postgresql_ops={"member_name": "gin_trgm_ops"},
        ),
        Index(
            "ix_members_external_id_trgm",
            "external_member_id",
            postgresql_using="gin",
            postgresql_ops={"external_member_id": "gin_trgm_ops"},
        ),
    )


class MemberPolicy(CreatedAtMixin, Base):
    """Payer-issued subscriber number. One member may hold several (dual coverage);
    a policy number belongs to exactly one member within a payer."""

    __tablename__ = "member_policies"

    id: Mapped[int] = mapped_column(BigInteger, Identity(), primary_key=True)
    member_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("members.id", ondelete="CASCADE"), nullable=False, index=True
    )
    payer_id: Mapped[int] = mapped_column(ForeignKey("payers.id"), nullable=False)
    policy_number: Mapped[str] = mapped_column(String(64), nullable=False)

    member: Mapped[Member] = relationship(back_populates="policies", lazy="raise")

    __table_args__ = (UniqueConstraint("payer_id", "policy_number"),)
