FROM python:3.11-slim

WORKDIR /app

# System deps
RUN apt-get update && apt-get install -y curl && rm -rf /var/lib/apt/lists/*

# Python dependencies — one image shared by all services
RUN pip install --no-cache-dir \
    fastapi==0.111.0 \
    "uvicorn[standard]==0.29.0" \
    sqlalchemy==2.0.30 \
    "sqlalchemy[asyncio]==2.0.30" \
    asyncpg==0.29.0 \
    alembic==1.13.1 \
    "redis[asyncio]==5.0.4" \
    pydantic==2.7.1 \
    pydantic-settings==2.2.1 \
    httpx==0.27.0 \
    qdrant-client==1.9.1 \
    neo4j==5.19.0

COPY shared/ ./shared/
COPY services/ ./services/

ENV PYTHONPATH=/app
ENV PYTHONUNBUFFERED=1

# Default command (overridden per-service in docker-compose)
CMD ["uvicorn", "services.orchestrator.main:app", "--host", "0.0.0.0", "--port", "8000"]
