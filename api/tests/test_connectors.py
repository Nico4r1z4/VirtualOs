"""Connector normalization tests — pure fixtures, no network."""

from __future__ import annotations

import json
from pathlib import Path

from virtualos.connectors.base import RawBatch
from virtualos.connectors.facebook import FacebookPagesConnector
from virtualos.connectors.instagram import InstagramProfilesConnector
from virtualos.connectors.news import SerperNewsConnector
from virtualos.connectors.tiktok import TikTokProfilesConnector, TikTokTrendsConnector

FIXTURES = Path(__file__).parent / "fixtures"


def _load(name: str):
    return json.loads((FIXTURES / name).read_text(encoding="utf-8"))


def test_tiktok_profiles_normalize() -> None:
    raw = RawBatch(source="apify:test", items=_load("tiktok_profile_items.json"))
    posts = TikTokProfilesConnector().normalize(raw)

    # Item without id is dropped
    assert len(posts) == 2

    p = posts[0]
    assert p.platform == "tiktok"
    assert p.external_id == "7421337700112233445"
    assert p.author_handle == "finanzas.claras"
    assert p.views == 1_250_000
    assert p.likes == 98_200
    assert p.shares == 12_400
    assert p.comments == 3_100
    assert p.hashtags == ["finanzaspersonales", "ahorro", "colombia"]
    assert p.sound_id == "7301234567890123456"
    assert p.sound_name == "original sound - finanzas.claras"
    assert p.duration_s == 42
    assert p.author_followers == 412_000
    assert p.published_at is not None and p.published_at.year == 2026
    # Subtitle links preserved for Phase 3 transcription
    assert p.raw["_subtitle_links"][0]["language"] == "spa-ES"

    # Second post has empty hashtags and no subtitles
    assert posts[1].hashtags == []


def test_tiktok_trends_normalize() -> None:
    raw = RawBatch(
        source="apify:test", items=_load("tiktok_trend_items.json"), meta={"country": "CO"}
    )
    trends = TikTokTrendsConnector().normalize(raw)

    assert len(trends) == 3  # nameless item dropped
    assert trends[0].name == "finanzaspersonales"
    assert trends[0].rank == 1
    assert trends[0].country == "CO"
    assert trends[0].metrics["videoViews"] == 94_000_000
    # '#' prefix stripped, fallback country from meta, rank from 'position'
    assert trends[2].name == "inversiones"
    assert trends[2].rank == 3
    assert trends[2].country == "CO"


def test_instagram_normalize() -> None:
    raw = RawBatch(source="apify:test", items=_load("instagram_items.json"))
    posts = InstagramProfilesConnector().normalize(raw)

    assert len(posts) == 2
    p = posts[0]
    assert p.platform == "instagram"
    assert p.external_id == "3482001122334455667"
    assert p.author_handle == "plata.sencilla"
    assert p.views == 489_000  # videoPlayCount preferred over videoViewCount
    assert p.likes == 23_100
    assert p.shares is None
    assert p.sound_name == "Audio original"
    assert p.duration_s == 31.5

    # Image post: falls back to shortCode id, no views
    assert posts[1].external_id == "DAzZyYxXwWv"
    assert posts[1].views is None


def test_news_normalize() -> None:
    data = _load("serper_news.json")
    raw = RawBatch(source="serper:news", items=data["news"], meta={"query": "finanzas"})
    items = SerperNewsConnector().normalize(raw)

    assert len(items) == 2  # item without title/link dropped
    assert items[0].title.startswith("Banco de la República")
    assert items[0].url == "https://ejemplo-noticias.co/banrep-tasas"
    assert items[0].source == "Ejemplo Noticias"


async def test_facebook_stub_returns_empty() -> None:
    conn = FacebookPagesConnector()
    raw = await conn.fetch(workspace_id="w", params={"pages": ["x"]})
    assert raw.items == []
    assert conn.normalize(raw) == []
