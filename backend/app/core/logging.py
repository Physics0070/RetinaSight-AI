"""Structured, production-safe logging.

Never logs credentials, tokens, or raw patient data. Handlers write to stdout so
Render (and any container platform) captures them.
"""

from __future__ import annotations

import logging
import sys

from app.core.config import settings

_CONFIGURED = False

# Fields that must never appear in log output even if passed in `extra`.
_REDACT_KEYS = {
    "password",
    "password_hash",
    "token",
    "access_token",
    "refresh_token",
    "authorization",
    "secret",
    "jwt_secret",
}


class _RedactFilter(logging.Filter):
    def filter(self, record: logging.LogRecord) -> bool:
        for key in list(vars(record).keys()):
            if key.lower() in _REDACT_KEYS:
                setattr(record, key, "***redacted***")
        return True


def configure_logging() -> None:
    global _CONFIGURED
    if _CONFIGURED:
        return

    level = getattr(logging, settings.log_level.upper(), logging.INFO)
    handler = logging.StreamHandler(sys.stdout)
    handler.setFormatter(
        logging.Formatter(
            fmt="%(asctime)s %(levelname)s %(name)s %(message)s",
            datefmt="%Y-%m-%dT%H:%M:%S%z",
        )
    )
    handler.addFilter(_RedactFilter())

    root = logging.getLogger()
    root.handlers.clear()
    root.addHandler(handler)
    root.setLevel(level)

    _CONFIGURED = True


def get_logger(name: str) -> logging.Logger:
    configure_logging()
    return logging.getLogger(name)
