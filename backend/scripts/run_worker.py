"""Background worker.

Takes the expensive work off the request path: model inference, Grad-CAM
generation, and the risk assessment that follows. A health worker on a slow
connection should not hold an HTTP request open while a GPU-less container
runs a convolutional network.

Enable by setting ``RS_INFERENCE_MODE=worker`` on the API service. In ``sync``
mode the API does this work inline and this process is unnecessary.

Design notes
------------
* **Claim-then-work.** A session is moved to ``inference_running`` in its own
  committed transaction before any work starts, so two workers cannot pick up
  the same screening.
* **Idempotent.** ``InferenceService`` returns the stored result if one already
  exists, so a crash mid-job is safe to retry.
* **Failures are recorded, not swallowed.** A session that cannot be processed
  moves to ``error``, which is a recoverable state the health worker can resume
  from — it is never left silently stuck in ``inference_running``.

Usage:
    python -m scripts.run_worker
"""

from __future__ import annotations

import signal
import sys
import time
from datetime import datetime, timedelta, timezone

from sqlalchemy import select

from app.core.config import settings
from app.core.logging import configure_logging, get_logger
from app.db.session import SessionLocal, engine
from app.domain.enums import ScreeningState
from app.models.screening import ScreeningSession
from app.services.screening_service import ScreeningService

logger = get_logger(__name__)

POLL_INTERVAL_SECONDS = 5
BATCH_SIZE = 5
# A session stuck in inference_running past this is assumed to be from a worker
# that died, and is returned to the queue.
STALE_CLAIM_MINUTES = 15

_shutdown = False


def _request_shutdown(signum, frame) -> None:  # noqa: ANN001
    """Finish the current job, then exit — never abandon a half-written result."""
    global _shutdown
    logger.info("Shutdown requested (signal %s); finishing current job.", signum)
    _shutdown = True


def claim_next_sessions(db, limit: int = BATCH_SIZE) -> list[ScreeningSession]:
    """Atomically claim sessions that are ready for inference."""
    stmt = (
        select(ScreeningSession)
        .where(ScreeningSession.state == ScreeningState.READY_FOR_INFERENCE.value)
        .order_by(ScreeningSession.created_at)
        .limit(limit)
    )
    # SELECT ... FOR UPDATE SKIP LOCKED lets several workers share the queue.
    # SQLite does not support it, so local development falls back to a plain
    # read — acceptable because dev runs a single worker.
    if not settings.is_sqlite:
        stmt = stmt.with_for_update(skip_locked=True)

    sessions = list(db.execute(stmt).scalars().all())
    for session in sessions:
        session.state = ScreeningState.INFERENCE_RUNNING.value
    db.commit()
    return sessions


def recover_stale_claims(db) -> int:
    """Return sessions abandoned by a dead worker to the queue."""
    cutoff = datetime.now(tz=timezone.utc) - timedelta(minutes=STALE_CLAIM_MINUTES)
    stale = list(
        db.execute(
            select(ScreeningSession).where(
                ScreeningSession.state == ScreeningState.INFERENCE_RUNNING.value,
                ScreeningSession.updated_at < cutoff,
            )
        ).scalars().all()
    )
    for session in stale:
        logger.warning("Recovering stale session %s", session.id)
        session.state = ScreeningState.READY_FOR_INFERENCE.value
    if stale:
        db.commit()
    return len(stale)


def process(session_id) -> bool:  # noqa: ANN001
    """Run inference, explanation and risk for one session."""
    with SessionLocal() as db:
        service = ScreeningService(db)
        try:
            session = service.get(session_id)
            # The claim moved it to inference_running; step back so the service's
            # own transition guard sees a legal starting state.
            session.state = ScreeningState.READY_FOR_INFERENCE.value
            db.commit()

            outcome = service.run_inference(session_id)
            risk = outcome.get("risk")
            logger.info(
                "Processed session=%s category=%s risk=%s",
                session_id,
                getattr(outcome.get("worst"), "category", None),
                getattr(risk, "risk_level", None),
            )
            return True
        except Exception:  # noqa: BLE001
            logger.exception("Inference failed for session=%s", session_id)
            try:
                session = service.get(session_id)
                session.state = ScreeningState.ERROR.value
                db.commit()
            except Exception:  # noqa: BLE001
                logger.exception("Could not mark session=%s as errored", session_id)
            return False


def main() -> int:
    configure_logging()
    signal.signal(signal.SIGTERM, _request_shutdown)
    signal.signal(signal.SIGINT, _request_shutdown)

    logger.info(
        "Worker starting env=%s db=%s poll=%ss",
        settings.env.value,
        "sqlite" if settings.is_sqlite else "postgresql",
        POLL_INTERVAL_SECONDS,
    )

    processed = 0
    failed = 0
    idle_cycles = 0

    while not _shutdown:
        try:
            with SessionLocal() as db:
                if idle_cycles % 60 == 0:
                    recover_stale_claims(db)
                claimed = claim_next_sessions(db)
                session_ids = [s.id for s in claimed]

            if not session_ids:
                idle_cycles += 1
                time.sleep(POLL_INTERVAL_SECONDS)
                continue

            idle_cycles = 0
            for session_id in session_ids:
                if _shutdown:
                    break
                if process(session_id):
                    processed += 1
                else:
                    failed += 1

        except Exception:  # noqa: BLE001
            # A worker must survive a transient database blip rather than
            # crash-looping the container.
            logger.exception("Worker loop error; backing off")
            time.sleep(POLL_INTERVAL_SECONDS * 2)

    engine.dispose()
    logger.info("Worker stopped. processed=%s failed=%s", processed, failed)
    return 0


if __name__ == "__main__":
    sys.exit(main())
