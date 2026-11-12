"""Transcripts from provider subtitles (Phase 3).

Only downloads subtitle URLs that Apify itself returned with the post
(stored in raw._subtitle_links). Never user- or LLM-supplied URLs (anti-SSRF,
CLAUDE.md rule 6). faster-whisper is a post-MVP optional extra.
"""

from __future__ import annotations

import logging
import re
from typing import Any

import httpx

logger = logging.getLogger(__name__)

_TIMEOUT = httpx.Timeout(20.0)
_MAX_TRANSCRIPT_CHARS = 8000

_VTT_TS = re.compile(r"^\d{2}:\d{2}:\d{2}[.,]\d{3}\s+-->")
_TAG = re.compile(r"<[^>]+>")


def parse_vtt(vtt: str) -> str:
    """WEBVTT/SRT -> plain text, deduplicating consecutive lines."""
    lines: list[str] = []
    for raw_line in vtt.splitlines():
        line = raw_line.strip()
        if (
            not line
            or line.startswith(("WEBVTT", "NOTE", "STYLE"))
            or line.isdigit()
            or _VTT_TS.match(line)
        ):
            continue
        text = _TAG.sub("", line).strip()
        if text and (not lines or lines[-1] != text):
            lines.append(text)
    return " ".join(lines)[:_MAX_TRANSCRIPT_CHARS]


def pick_subtitle_link(
    raw: dict[str, Any], preferred_langs: tuple[str, ...] = ("es", "spa")
) -> str | None:
    """Choose the best subtitle URL from the provider payload."""
    links = raw.get("_subtitle_links") or []
    if not isinstance(links, list) or not links:
        return None
    for lang in preferred_langs:
        for item in links:
            if isinstance(item, dict) and str(item.get("language", "")).lower().startswith(lang):
                url = item.get("downloadLink") or item.get("download_link") or item.get("url")
                if url:
                    return str(url)
    first = links[0]
    if isinstance(first, dict):
        url = first.get("downloadLink") or first.get("download_link") or first.get("url")
        return str(url) if url else None
    return None


async def fetch_transcript(raw: dict[str, Any]) -> str | None:
    """Download and parse the provider subtitle file, if any. Never raises."""
    url = pick_subtitle_link(raw)
    if not url:
        return None
    try:
        async with httpx.AsyncClient(timeout=_TIMEOUT, follow_redirects=True) as client:
            resp = await client.get(url)
            resp.raise_for_status()
            text = parse_vtt(resp.text)
            return text or None
    except Exception:
        logger.debug("subtitle fetch failed for %s", url[:80])
        return None
