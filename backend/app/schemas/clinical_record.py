"""Medical history and prescription contracts."""

from __future__ import annotations

import uuid
from datetime import date, datetime

from pydantic import BaseModel, Field, field_validator

from app.domain.enums import HistoryEntryType, PrescriptionStatus
from app.schemas.common import ORMModel


# --------------------------------------------------------------------------- #
# Medical history
# --------------------------------------------------------------------------- #
class HistoryEntryCreate(BaseModel):
    entry_type: HistoryEntryType
    title: str = Field(min_length=1, max_length=255)
    detail: str | None = Field(default=None, max_length=4000)
    occurred_on: date | None = None
    status: str | None = Field(default=None, max_length=64)


class HistoryEntryUpdate(BaseModel):
    """Every field optional — a partial edit must not blank the rest."""

    entry_type: HistoryEntryType | None = None
    title: str | None = Field(default=None, min_length=1, max_length=255)
    detail: str | None = Field(default=None, max_length=4000)
    occurred_on: date | None = None
    status: str | None = Field(default=None, max_length=64)


class HistoryEntryRead(ORMModel):
    id: uuid.UUID
    patient_id: uuid.UUID
    entry_type: str
    title: str
    detail: str | None
    occurred_on: date | None
    status: str | None
    recorded_by_user_id: uuid.UUID | None
    updated_by_user_id: uuid.UUID | None
    created_at: datetime
    updated_at: datetime


# --------------------------------------------------------------------------- #
# Prescriptions
# --------------------------------------------------------------------------- #
class PrescriptionItem(BaseModel):
    """One prescribed medicine."""

    name: str = Field(min_length=1, max_length=200)
    dose: str = Field(min_length=1, max_length=100)
    frequency: str = Field(min_length=1, max_length=100)
    duration: str | None = Field(default=None, max_length=100)
    instructions: str | None = Field(default=None, max_length=500)


class PrescriptionCreate(BaseModel):
    # A prescription with no medicine on it is not a prescription; rejecting it
    # here keeps an empty document from ever reaching a pharmacy.
    items: list[PrescriptionItem] = Field(min_length=1)
    diagnosis: str | None = Field(default=None, max_length=255)
    notes: str | None = Field(default=None, max_length=4000)
    session_id: uuid.UUID | None = None
    valid_until: date | None = None

    @field_validator("items")
    @classmethod
    def _no_duplicate_medicines(cls, items: list[PrescriptionItem]):
        """Two lines for the same drug is a dosing error waiting to happen."""
        seen = {item.name.strip().lower() for item in items}
        if len(seen) != len(items):
            raise ValueError("The same medicine appears more than once.")
        return items


class PrescriptionUpdate(BaseModel):
    """Revising a prescription: its status, or the whole item list at once."""

    status: PrescriptionStatus | None = None
    items: list[PrescriptionItem] | None = Field(default=None, min_length=1)
    diagnosis: str | None = Field(default=None, max_length=255)
    notes: str | None = Field(default=None, max_length=4000)
    valid_until: date | None = None


class PrescriptionRead(ORMModel):
    id: uuid.UUID
    patient_id: uuid.UUID
    session_id: uuid.UUID | None
    prescribed_by_user_id: uuid.UUID | None
    items: list
    diagnosis: str | None
    notes: str | None
    status: str
    valid_until: date | None
    created_at: datetime
    updated_at: datetime
