# RetinaSight AI API -- Hugging Face Spaces (Docker SDK).
#
# Built from the directory produced by `python scripts/package_hf_space.py`,
# NOT from the repository root: a Space is its own git repo whose root must
# hold this file. The layout it expects is
#
#   /app/backend/        the FastAPI service
#   /app/ml/models/      dr-v2.onnx + dr-v2.json
#
# which mirrors the repository, because the application anchors RS_MODEL_DIR
# to the directory two levels above backend/app/core/config.py.
#
# No secrets are baked in. Everything sensitive arrives as Space secrets, which
# Hugging Face exposes to the container as ordinary environment variables.

FROM python:3.12-slim

# Spaces run the container as uid 1000; a root-owned /app would be read-only.
RUN useradd -m -u 1000 app
ENV HOME=/home/app \
    PATH=/home/app/.local/bin:$PATH \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1
WORKDIR /app

COPY --chown=app:app backend/requirements.txt backend/requirements-serve.txt backend/
USER app
RUN pip install --user -r backend/requirements-serve.txt

COPY --chown=app:app backend backend
COPY --chown=app:app ml ml

WORKDIR /app/backend

# Hugging Face routes traffic to app_port from README.md (7860).
EXPOSE 7860

# Migrate, then serve. A failed migration stops the container instead of
# serving against a half-built schema.
CMD ["sh", "-c", "alembic upgrade head && uvicorn app.main:app --host 0.0.0.0 --port 7860"]
