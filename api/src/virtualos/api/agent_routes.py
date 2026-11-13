"""Mascot endpoints: SSE message stream + conversation history."""

from __future__ import annotations

import json
from typing import Any

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel
from sse_starlette.sse import EventSourceResponse

from virtualos.agent.loop import run_agent
from virtualos.auth.deps import Auth
from virtualos.db.client import get_pool

router = APIRouter(prefix="/agent", tags=["agent"])


class AgentMessageIn(BaseModel):
    message: str
    conversation_id: str | None = None


async def _check_quota(workspace_id: str) -> None:
    pool = get_pool()
    row = await pool.fetchrow(
        """
        SELECT pl.agent_messages_per_day,
               (SELECT COUNT(*) FROM vos.agent_messages m
                WHERE m.workspace_id = w.id AND m.role = 'user'
                  AND m.created_at >= CURRENT_DATE) AS used
        FROM vos.workspaces w JOIN vos.plan_limits pl ON pl.plan = w.plan
        WHERE w.id = $1
        """,
        workspace_id,
    )
    if row and row["used"] >= row["agent_messages_per_day"]:
        raise HTTPException(
            status_code=429,
            detail=f"Límite diario de mensajes a la mascota alcanzado ({row['agent_messages_per_day']}).",
        )


@router.post("/messages")
async def send_message(body: AgentMessageIn, auth: Auth) -> EventSourceResponse:
    if not body.message.strip():
        raise HTTPException(status_code=422, detail="Mensaje vacío")
    await _check_quota(auth.workspace_id)

    pool = get_pool()
    conversation_id = body.conversation_id
    if conversation_id:
        conv = await pool.fetchrow(
            "SELECT id FROM vos.agent_conversations WHERE id = $1 AND workspace_id = $2 AND user_id = $3",
            conversation_id,
            auth.workspace_id,
            auth.user_id,
        )
        if conv is None:
            raise HTTPException(status_code=404, detail="Conversación no encontrada")
    else:
        row = await pool.fetchrow(
            "INSERT INTO vos.agent_conversations (workspace_id, user_id, title) VALUES ($1, $2, $3) RETURNING id",
            auth.workspace_id,
            auth.user_id,
            body.message[:60],
        )
        assert row is not None
        conversation_id = str(row["id"])

    async def event_stream():
        yield {"event": "meta", "data": json.dumps({"conversation_id": conversation_id})}
        async for ev in run_agent(
            workspace_id=auth.workspace_id,
            user_id=auth.user_id,
            conversation_id=conversation_id,
            user_message=body.message,
        ):
            yield {"event": ev["type"], "data": json.dumps(ev, default=str)}

    return EventSourceResponse(event_stream())


@router.get("/conversations")
async def list_conversations(auth: Auth) -> dict[str, Any]:
    pool = get_pool()
    # Scoped to the requesting user too: in a multi-member (agency) workspace a
    # member must not load another member's chat.
    rows = await pool.fetch(
        """
        SELECT c.id, c.title, c.created_at,
               COALESCE(MAX(m.created_at), c.created_at) AS last_message_at
        FROM vos.agent_conversations c
        LEFT JOIN vos.agent_messages m ON m.conversation_id = c.id
        WHERE c.workspace_id = $1 AND c.user_id = $2
        GROUP BY c.id
        ORDER BY last_message_at DESC
        LIMIT 20
        """,
        auth.workspace_id,
        auth.user_id,
    )
    return {"items": [{**dict(r), "id": str(r["id"])} for r in rows]}


@router.get("/conversations/{conversation_id}/messages")
async def conversation_messages(conversation_id: str, auth: Auth) -> dict[str, Any]:
    pool = get_pool()
    rows = await pool.fetch(
        """
        SELECT m.id, m.role, m.content, m.created_at
        FROM vos.agent_messages m
        JOIN vos.agent_conversations c ON c.id = m.conversation_id
        WHERE m.conversation_id = $1 AND c.workspace_id = $2 AND c.user_id = $3
          AND m.content IS NOT NULL
        ORDER BY m.id
        """,
        conversation_id,
        auth.workspace_id,
        auth.user_id,
    )
    return {"items": [dict(r) for r in rows]}
