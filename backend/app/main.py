"""FastAPI application factory.

Binds to Render's injected ``PORT`` via ``app.db.session.bind_port`` (see
``scripts/run_api.py``); nothing here assumes a fixed production port.
"""

from __future__ import annotations

from contextlib import asynccontextmanager

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from sqlalchemy import text

from app import __version__
from app.api.v1.router import api_router
from app.core.config import settings
from app.core.errors import AppError
from app.core.logging import configure_logging, get_logger
from app.db.session import engine
from app.schemas.common import ErrorDetail, ErrorResponse

logger = get_logger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI):  # noqa: ANN201
    configure_logging()
    logger.info(
        "RetinaSight AI API starting env=%s version=%s", settings.env.value, __version__
    )
    yield
    # Graceful shutdown: release pooled DB connections.
    engine.dispose()
    logger.info("RetinaSight AI API stopped")


def create_app() -> FastAPI:
    configure_logging()

    app = FastAPI(
        title="RetinaSight AI API",
        version=__version__,
        summary="AI-assisted diabetic retinopathy screening and referral support.",
        description=(
            "Screening and referral-support system. AI output is decision support "
            "for a qualified clinician — it is not an autonomous diagnosis."
        ),
        docs_url="/docs" if not settings.is_production else None,
        redoc_url=None,
        openapi_url="/openapi.json" if not settings.is_production else None,
        lifespan=lifespan,
    )

    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.cors_origins_list,
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    _register_exception_handlers(app)
    _register_health_routes(app)
    app.include_router(api_router, prefix=settings.api_prefix)
    return app


def _register_exception_handlers(app: FastAPI) -> None:
    @app.exception_handler(AppError)
    async def _app_error(request: Request, exc: AppError) -> JSONResponse:
        return JSONResponse(
            status_code=exc.status_code,
            content=ErrorResponse(
                error=ErrorDetail(code=exc.code, message=exc.message, details=exc.details)
            ).model_dump(exclude_none=True),
        )

    @app.exception_handler(RequestValidationError)
    async def _validation_error(
        request: Request, exc: RequestValidationError
    ) -> JSONResponse:
        # Field-level hints are safe; the raw exception is not surfaced.
        fields = {
            ".".join(str(p) for p in err.get("loc", [])[1:]): err.get("msg", "Invalid value")
            for err in exc.errors()
        }
        return JSONResponse(
            status_code=422,
            content=ErrorResponse(
                error=ErrorDetail(
                    code="validation_error",
                    message="Some of the submitted information is not valid.",
                    details=fields,
                )
            ).model_dump(exclude_none=True),
        )

    @app.exception_handler(Exception)
    async def _unhandled(request: Request, exc: Exception) -> JSONResponse:
        # Full detail to logs, generic message to the client.
        logger.exception("Unhandled error on %s %s", request.method, request.url.path)
        return JSONResponse(
            status_code=500,
            content=ErrorResponse(
                error=ErrorDetail(
                    code="internal_error",
                    message="Something went wrong on our side. Please try again.",
                )
            ).model_dump(exclude_none=True),
        )


def _register_health_routes(app: FastAPI) -> None:
    @app.get("/health", tags=["system"])
    def health() -> dict:
        return {"status": "ok", "version": __version__, "environment": settings.env.value}

    @app.get("/health/ready", tags=["system"])
    def readiness() -> JSONResponse:
        """Readiness includes a real database round-trip."""
        try:
            with engine.connect() as conn:
                conn.execute(text("SELECT 1"))
            return JSONResponse({"status": "ready", "database": "connected"})
        except Exception:  # noqa: BLE001
            logger.exception("Readiness probe failed: database unreachable")
            return JSONResponse(
                status_code=503, content={"status": "not_ready", "database": "unavailable"}
            )


app = create_app()
