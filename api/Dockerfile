# VirtualOS API + Worker (same image; the worker overrides CMD in compose).
FROM python:3.12-slim

RUN pip install --no-cache-dir uv
WORKDIR /app
ENV UV_COMPILE_BYTECODE=1 UV_LINK_MODE=copy UV_PYTHON_DOWNLOADS=never PYTHONIOENCODING=utf-8

# Dependencies first (cacheable layer), then the code.
COPY pyproject.toml uv.lock README.md ./
RUN uv sync --frozen --no-dev --no-install-project

COPY src ./src
COPY db ./db
COPY scripts ./scripts
RUN uv sync --frozen --no-dev

EXPOSE 8000
CMD ["uv", "run", "--no-sync", "uvicorn", "virtualos.api.main:app", "--host", "0.0.0.0", "--port", "8000"]
