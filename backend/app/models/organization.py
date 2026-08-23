"""Clinics and the staff profiles (doctors, health workers) attached to users."""

from __future__ import annotations

import uuid

from sqlalchemy import Float, ForeignKey, String, Uuid
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base, TimestampMixin, UUIDPrimaryKeyMixin


class Clinic(Base, UUIDPrimaryKeyMixin, TimestampMixin):
    __tablename__ = "clinics"

    name: Mapped[str] = mapped_column(String(255), index=True)
    code: Mapped[str] = mapped_column(String(64), unique=True, index=True)
    location: Mapped[str] = mapped_column(String(255), default="")
    region: Mapped[str | None] = mapped_column(String(128), nullable=True)
    latitude: Mapped[float | None] = mapped_column(Float, nullable=True)
    longitude: Mapped[float | None] = mapped_column(Float, nullable=True)
    status: Mapped[str] = mapped_column(String(16), default="active", index=True)
    connectivity_status: Mapped[str] = mapped_column(String(16), default="unknown")

    doctors: Mapped[list["Doctor"]] = relationship(back_populates="clinic")
    health_workers: Mapped[list["HealthWorker"]] = relationship(back_populates="clinic")


class Doctor(Base, UUIDPrimaryKeyMixin, TimestampMixin):
    __tablename__ = "doctors"

    user_id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), unique=True, index=True
    )
    clinic_id: Mapped[uuid.UUID | None] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("clinics.id", ondelete="SET NULL"), nullable=True, index=True
    )
    specialty: Mapped[str] = mapped_column(String(128), default="ophthalmology")
    license_number: Mapped[str | None] = mapped_column(String(64), nullable=True)

    clinic: Mapped["Clinic | None"] = relationship(back_populates="doctors")


class HealthWorker(Base, UUIDPrimaryKeyMixin, TimestampMixin):
    __tablename__ = "health_workers"

    user_id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), unique=True, index=True
    )
    clinic_id: Mapped[uuid.UUID | None] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("clinics.id", ondelete="SET NULL"), nullable=True, index=True
    )
    staff_code: Mapped[str | None] = mapped_column(String(64), nullable=True)

    clinic: Mapped["Clinic | None"] = relationship(back_populates="health_workers")
