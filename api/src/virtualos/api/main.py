"""FastAPI app: lifespan (pool), CORS, health, and route mounting."""

from __future__ import annotations

from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from virtualos.api.webhooks import router as webhooks_router
from virtualos.auth.deps import Auth
from virtualos.config.settings import get_settings
from virtualos.db import client as db_client
from virtualos.observability.logs import setup_logging


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncIterator[None]:
    setup_logging()
    await db_client.init_pool()
    yield
    await db_client.close_pool()


def create_app() -> FastAPI:
    settings = get_settings()
    app = FastAPI(title="VirtualOS API", version="0.1.0", lifespan=lifespan)
    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.cors_origin_list,
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    @app.get("/health")
    async def health() -> dict[str, str]:
        pool = db_client.get_pool()
        await pool.fetchval("SELECT 1")
        return {"status": "ok"}

    @app.get("/me")
    async def me(auth: Auth) -> dict[str, str | None]:
        return {
            "user_id": auth.user_id,
            "email": auth.email,
            "workspace_id": auth.workspace_id,
        }

    app.include_router(webhooks_router)

    return app


app = create_app()
