"""Shared response envelopes and pagination contracts."""

from __future__ import annotations

import math
from typing import Any, Generic, TypeVar

from pydantic import BaseModel, ConfigDict, Field

T = TypeVar("T")


class ORMModel(BaseModel):
    """Base for schemas read directly from SQLAlchemy objects."""

    model_config = ConfigDict(from_attributes=True)


class MessageResponse(BaseModel):
    message: str


class ErrorDetail(BaseModel):
    """Client-safe error body. Technical detail stays in server logs."""

    code: str = Field(description="Stable machine-readable error code.")
    message: str = Field(description="Human-readable, non-technical message.")
    details: dict[str, Any] | None = None


class ErrorResponse(BaseModel):
    error: ErrorDetail


class PaginationParams(BaseModel):
    page: int = Field(default=1, ge=1)
    page_size: int = Field(default=25, ge=1, le=200)

    @property
    def offset(self) -> int:
        return (self.page - 1) * self.page_size


class Page(BaseModel, Generic[T]):
    items: list[T]
    total: int
    page: int
    page_size: int
    pages: int

    @classmethod
    def build(cls, items: list[T], total: int, params: PaginationParams) -> "Page[T]":
        return cls(
            items=items,
            total=total,
            page=params.page,
            page_size=params.page_size,
            pages=max(1, math.ceil(total / params.page_size)) if total else 0,
        )
