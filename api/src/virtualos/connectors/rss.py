"""News connector over RSS: curated national media + Google News by keywords.

Replaces DuckDuckGo as the default news source (DDG rate-limits datacenter
IPs; it returned 0 news from the EC2 on 2026-11-13). RSS is the syndication
format publishers offer for exactly this purpose, it is free, and it is fresh
(every curated feed below had items from the same day when verified).

Security (CLAUDE.md rule 6): feed URLs are a FIXED list in code; the only
user-influenced input is the Google News *query string* (profile keywords)
against a fixed host. No arbitrary URL is ever fetched. Titles/summaries are
untrusted text: HTML is stripped here and prompts wrap them as untrusted.

Relevance is decided in code (cost funnel, no LLM):
- curated feeds are economy sections -> 1 keyword hit is enough;
- Google News is the whole web -> needs 2 distinct keywords, or one
  multi-word keyword ("tarjetas de crédito"), to cut noise like
  "ahorro de energía" or a hospital's "deudas".
"""

from __future__ import annotations

import asyncio
import html
import logging
import re
import unicodedata
from datetime import UTC, datetime
from typing import Any
from urllib.parse import quote_plus

import feedparser
import httpx

from virtualos.connectors.base import RawBatch
from virtualos.connectors.models import NewsItem
from virtualos.observability.usage import record_usage

logger = logging.getLogger(__name__)

_UA = "Mozilla/5.0 (compatible; VirtualOS-RSS/0.1; +https://vos.orkiza.com)"
_TIMEOUT = httpx.Timeout(15.0, connect=8.0)
_MAX_ITEMS = 40
_GNEWS_MAX_KEYWORDS = 6

# Verified 2026-11-13 from the production server (HTTP 200, same-day items).
# Dropped: La República and El Espectador economy feeds (404).
# Kind: "curated" = an economy/business section (financial context is given);
# "general" = a general news feed (needs stronger evidence of relevance —
# seen live: a football match matched 'acciones' in its summary).
CURATED_FEEDS: dict[str, list[tuple[str, str, str]]] = {
    "CO": [
        ("El Tiempo", "https://www.eltiempo.com/rss/economia.xml", "curated"),
        ("Portafolio", "https://www.portafolio.co/rss/economia.xml", "curated"),
        (
            "Semana",
            "https://www.semana.com/arc/outboundfeeds/rss/category/economia/?outputType=xml",
            "curated",
        ),
        ("Valora Analitik", "https://www.valoraanalitik.com/feed/", "curated"),
        (
            "Infobae Colombia",
            "https://www.infobae.com/arc/outboundfeeds/rss/category/colombia/?outputType=xml",
            "general",
        ),
        (
            "Bloomberg Línea",
            "https://www.bloomberglinea.com/arc/outboundfeeds/rss/?outputType=xml",
            "curated",
        ),
    ],
}

_GNEWS_LOCALE = {
    "CO": ("es-419", "CO", "CO:es-419"),
    "MX": ("es-419", "MX", "MX:es-419"),
    "AR": ("es-419", "AR", "AR:es-419"),
    "ES": ("es", "ES", "ES:es"),
    "US": ("es-419", "US", "US:es-419"),
}

_STOPWORDS = {
    "para",
    "como",
    "con",
    "del",
    "las",
    "los",
    "una",
    "uno",
    "por",
    "que",
    "sus",
    "mas",
    "sin",
    "sobre",
    "entre",
    "the",
    "and",
    "for",
}
_TAG = re.compile(r"<[^>]+>")
_WS = re.compile(r"\s+")


# ---------------------------------------------------------------------------
# Text helpers
# ---------------------------------------------------------------------------


def fold(text: str) -> str:
    """Lowercase, strip accents: 'Crédito' -> 'credito'."""
    nfkd = unicodedata.normalize("NFKD", text.lower())
    return "".join(c for c in nfkd if not unicodedata.combining(c))


def clean_text(raw: str | None, limit: int = 400) -> str:
    """Untrusted feed HTML -> plain text."""
    if not raw:
        return ""
    text = html.unescape(_TAG.sub(" ", raw))
    return _WS.sub(" ", text).strip()[:limit]


def _significant_words(keyword: str) -> list[str]:
    return [
        w for w in re.findall(r"[a-z0-9]+", fold(keyword)) if len(w) >= 4 and w not in _STOPWORDS
    ]


def _word_hits(word: str, tokens: set[str]) -> bool:
    # Light stemming: 'deudas' ~ 'deuda', 'inversiones' ~ 'inversion'.
    stem = word[: max(4, len(word) - 2)]
    return any(t.startswith(stem) for t in tokens)


def keyword_hits(text: str, keywords: list[str]) -> tuple[int, bool]:
    """(distinct keywords matched, whether a multi-word keyword matched).
    A keyword matches when ALL its significant words appear in the text."""
    tokens = set(re.findall(r"[a-z0-9]+", fold(text)))
    hits, multi = 0, False
    for kw in keywords:
        words = _significant_words(kw)
        if words and all(_word_hits(w, tokens) for w in words):
            hits += 1
            multi = multi or len(words) >= 2
    return hits, multi


def is_relevant(origin: str, title: str, summary: str, keywords: list[str]) -> bool:
    """The TITLE must carry the topic; the summary only reinforces it.

    - curated (economy sections): >= 1 keyword in the title.
    - general feeds and Google News: a multi-word keyword in the title, or
      >= 2 distinct keywords overall with >= 1 of them in the title.
    """
    if not keywords:
        return origin == "curated"
    title_hits, title_multi = keyword_hits(title, keywords)
    if origin == "curated":
        return title_hits >= 1
    total_hits, _ = keyword_hits(f"{title} {summary}", keywords)
    return title_multi or (total_hits >= 2 and title_hits >= 1)


def google_news_url(keywords: list[str], country: str) -> str:
    hl, gl, ceid = _GNEWS_LOCALE.get(country.upper(), _GNEWS_LOCALE["CO"])
    terms = [f'"{k.strip()}"' for k in keywords[:_GNEWS_MAX_KEYWORDS] if k.strip()]
    query = " OR ".join(terms) + " when:7d"
    return (
        f"https://news.google.com/rss/search?q={quote_plus(query)}"
        f"&hl={hl}&gl={gl}&ceid={quote_plus(ceid)}"
    )


def _published(entry: Any) -> datetime | None:
    parsed = entry.get("published_parsed") or entry.get("updated_parsed")
    if parsed:
        try:
            return datetime(*parsed[:6], tzinfo=UTC)
        except (TypeError, ValueError):
            return None
    return None


# ---------------------------------------------------------------------------
# Connector
# ---------------------------------------------------------------------------


class RssNewsConnector:
    source = "news_rss"

    async def fetch(self, *, workspace_id: str, params: dict[str, Any]) -> RawBatch:
        country = str(params.get("country", "CO")).upper()
        keywords: list[str] = list(params.get("keywords") or [])

        feeds = [(name, url, kind) for name, url, kind in CURATED_FEEDS.get(country, [])]
        if keywords:
            feeds.append(("Google News", google_news_url(keywords, country), "gnews"))

        async with httpx.AsyncClient(
            timeout=_TIMEOUT, headers={"User-Agent": _UA}, follow_redirects=True
        ) as client:
            results = await asyncio.gather(
                *(self._fetch_one(client, name, url, origin) for name, url, origin in feeds),
                return_exceptions=True,
            )

        items: list[dict[str, Any]] = []
        ok = 0
        for (name, _, _), res in zip(feeds, results, strict=True):
            if isinstance(res, BaseException):
                logger.warning("rss feed failed: %s (%s)", name, type(res).__name__)
                continue
            ok += 1
            items.extend(res)

        # Free source, but every external call is still accounted (rule 7).
        await record_usage(workspace_id, "rss", calls=len(feeds), cost_usd=0.0)
        logger.info("rss: %d/%d feeds ok, %d raw items", ok, len(feeds), len(items))
        return RawBatch(
            source="rss",
            items=items,
            meta={"country": country, "keywords": keywords, "feeds_ok": ok, "feeds": len(feeds)},
        )

    async def _fetch_one(
        self, client: httpx.AsyncClient, name: str, url: str, origin: str
    ) -> list[dict[str, Any]]:
        resp = await client.get(url)
        resp.raise_for_status()
        parsed = feedparser.parse(resp.content)
        out = []
        for entry in parsed.entries:
            link = entry.get("link")
            title = clean_text(entry.get("title"), 300)
            if not link or not title:
                continue
            # Google News titles end in " - Outlet"; keep the outlet as source.
            source = name
            if origin == "gnews":
                src = entry.get("source") or {}
                source = (src.get("title") if isinstance(src, dict) else None) or name
                if " - " in title:
                    head, _, tail = title.rpartition(" - ")
                    title, source = head.strip(), (source if src else tail.strip())
            published = _published(entry)
            out.append(
                {
                    "title": title,
                    "link": link,
                    "summary": clean_text(entry.get("summary")),
                    "source": source,
                    "origin": origin,
                    "published_at": published.isoformat() if published else None,
                }
            )
        return out

    def normalize(self, raw: RawBatch) -> list[NewsItem]:
        keywords: list[str] = list(raw.meta.get("keywords") or [])
        seen: set[str] = set()
        ranked: list[tuple[datetime, NewsItem]] = []
        epoch = datetime(1970, 1, 1, tzinfo=UTC)
        for item in raw.items:
            title, summary = item.get("title", ""), item.get("summary", "")
            if not is_relevant(item.get("origin", "curated"), title, summary, keywords):
                continue
            dedupe_key = fold(title)[:80]
            if dedupe_key in seen:
                continue
            seen.add(dedupe_key)
            published = (
                datetime.fromisoformat(item["published_at"]) if item.get("published_at") else None
            )
            ranked.append(
                (
                    published or epoch,
                    NewsItem(
                        title=title,
                        url=item["link"],
                        source=item.get("source"),
                        snippet=summary or None,
                        published_at=published,
                        raw={"origin": item.get("origin")},
                    ),
                )
            )
        ranked.sort(key=lambda r: r[0], reverse=True)  # freshest first
        return [n for _, n in ranked[:_MAX_ITEMS]]
