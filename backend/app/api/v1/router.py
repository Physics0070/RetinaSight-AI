"""Aggregates all /api/v1 routers."""

from __future__ import annotations

from fastapi import APIRouter

from app.api.v1.routers import (
    admin,
    auth,
    clinical,
    images,
    patients,
    screenings,
    sync,
    users,
)

api_router = APIRouter()

# Identity
api_router.include_router(auth.router)
api_router.include_router(users.router)

# Clinical workflow
api_router.include_router(patients.router)
api_router.include_router(screenings.router)
api_router.include_router(images.router)
api_router.include_router(clinical.router)

# Offline sync
api_router.include_router(sync.router)

# Administration (clinics, models, configuration, audit, system health)
api_router.include_router(admin.router)
