from sqlalchemy import Boolean, ForeignKey, Identity, Integer, String, UniqueConstraint, true
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import Base, CreatedAtMixin


class ProviderGroup(CreatedAtMixin, Base):
    __tablename__ = "provider_groups"

    id: Mapped[int] = mapped_column(Integer, Identity(), primary_key=True)
    name: Mapped[str] = mapped_column(String(200), nullable=False)
    normalized_name: Mapped[str] = mapped_column(String(200), nullable=False, unique=True)

    providers: Mapped[list["Provider"]] = relationship(back_populates="group", lazy="raise")


class Provider(CreatedAtMixin, Base):
    """An individual provider. The CSV has no global provider id, so identity is the
    normalized name scoped to its group."""

    __tablename__ = "providers"

    id: Mapped[int] = mapped_column(Integer, Identity(), primary_key=True)
    provider_group_id: Mapped[int] = mapped_column(ForeignKey("provider_groups.id"), nullable=False)
    display_name: Mapped[str] = mapped_column(String(200), nullable=False)
    normalized_name: Mapped[str] = mapped_column(String(200), nullable=False)
    is_active: Mapped[bool] = mapped_column(Boolean, nullable=False, server_default=true())

    group: Mapped[ProviderGroup] = relationship(back_populates="providers", lazy="raise")

    __table_args__ = (UniqueConstraint("provider_group_id", "normalized_name"),)


class Payer(CreatedAtMixin, Base):
    __tablename__ = "payers"

    id: Mapped[int] = mapped_column(Integer, Identity(), primary_key=True)
    display_name: Mapped[str] = mapped_column(String(200), nullable=False)
    normalized_name: Mapped[str] = mapped_column(String(200), nullable=False, unique=True)
