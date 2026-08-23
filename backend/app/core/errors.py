"""Application error taxonomy.

Services raise these; a single exception handler converts them into the
client-safe :class:`app.schemas.common.ErrorResponse` envelope. Raw exceptions
and stack traces are never returned to clients.
"""

from __future__ import annotations

from typing import Any


class AppError(Exception):
    """Base application error."""

    status_code: int = 400
    code: str = "app_error"
    message: str = "The request could not be completed."

    def __init__(
        self,
        message: str | None = None,
        *,
        code: str | None = None,
        details: dict[str, Any] | None = None,
    ) -> None:
        self.message = message or self.message
        self.code = code or self.code
        self.details = details
        super().__init__(self.message)


class AuthenticationError(AppError):
    status_code = 401
    code = "authentication_failed"
    message = "Your email or password is incorrect."


class InvalidTokenError(AppError):
    status_code = 401
    code = "invalid_token"
    message = "Your session has expired. Please sign in again."


class AccountInactiveError(AppError):
    status_code = 403
    code = "account_inactive"
    message = "This account is not active. Contact your administrator."


class PermissionDeniedError(AppError):
    status_code = 403
    code = "permission_denied"
    message = "You do not have permission to perform this action."


class NotFoundError(AppError):
    status_code = 404
    code = "not_found"
    message = "The requested item could not be found."


class ConflictError(AppError):
    status_code = 409
    code = "conflict"
    message = "That item already exists."


class ValidationError(AppError):
    status_code = 422
    code = "validation_error"
    message = "Some of the submitted information is not valid."


class WorkflowError(AppError):
    """Illegal screening-state transition or out-of-order workflow action."""

    status_code = 409
    code = "invalid_workflow_transition"
    message = "That action is not available at this step."


class RateLimitError(AppError):
    status_code = 429
    code = "rate_limited"
    message = "Too many attempts. Please wait a moment and try again."


class ServiceUnavailableError(AppError):
    status_code = 503
    code = "service_unavailable"
    message = "This service is temporarily unavailable. Please try again."
