"""FastAPI auth dependencies: current user + workspace context.

Every user-facing endpoint depends on `AuthContext`. The workspace is resolved
from vos.workspace_members; on a user's very first request a personal workspace
is created automatically (owner role) so onboarding has somewhere to live.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Annotated, Any

from fastapi import Depends, HTTPException, Request

from virtualos.auth.jwt import AuthError, verify_token
from virtualos.db.client import get_pool


@dataclass(slots=True)
class AuthContext:
    user_id: str
    email: str | None
    workspace_id: str
    claims: dict[str, Any]


async def get_auth_context(request: Request) -> AuthContext:
    auth = request.headers.get("Authorization", "")
    if not auth.startswith("Bearer "):
        raise HTTPException(status_code=401, detail="Missing bearer token")
    try:
        claims = await verify_token(auth.removeprefix("Bearer ").strip())
    except AuthError as exc:
        raise HTTPException(status_code=401, detail=str(exc)) from exc

    user_id = claims.get("sub")
    if not user_id:
        raise HTTPException(status_code=401, detail="Token has no sub claim")
    email = claims.get("email")

    pool = get_pool()
    row = await pool.fetchrow(
        "SELECT workspace_id FROM vos.workspace_members WHERE user_id = $1 ORDER BY created_at LIMIT 1",
        user_id,
    )
    if row is None:
        # First login: create a personal workspace (runs as owner role, bypasses RLS).
        async with pool.acquire() as conn, conn.transaction():
            ws = await conn.fetchrow(
                "INSERT INTO vos.workspaces (name, kind) VALUES ($1, 'creator') RETURNING id",
                (email or "workspace").split("@")[0],
            )
            assert ws is not None
            await conn.execute(
                "INSERT INTO vos.workspace_members (workspace_id, user_id, role) VALUES ($1, $2, 'owner')",
                ws["id"],
                user_id,
            )
            workspace_id = str(ws["id"])
    else:
        workspace_id = str(row["workspace_id"])

    return AuthContext(user_id=user_id, email=email, workspace_id=workspace_id, claims=claims)


Auth = Annotated[AuthContext, Depends(get_auth_context)]
