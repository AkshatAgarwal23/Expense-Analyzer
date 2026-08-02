FROM python:3.12-slim

WORKDIR /app

# Install only the base package (no faster-whisper; Sarvam handles STT in production)
COPY pyproject.toml .
RUN pip install --no-cache-dir -e "."

COPY . .

EXPOSE 8000

# Run migrations then start the server.
# PORT env var is set by Railway; default to 8000 locally.
CMD alembic upgrade head && uvicorn app.main:app --host 0.0.0.0 --port "${PORT:-8000}"
