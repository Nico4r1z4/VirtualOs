"""Normalized domain models every connector must produce.

CLAUDE.md: `Post` normalizado — platform, external_id, author_handle, url,
published_at, views, likes, comments, shares, caption, hashtags[],
sound_id/sound_name, duration_s, thumbnail_url, transcript, raw.
"""

from __future__ import annotations

from datetime import datetime
from typing import Any, Literal

from pydantic import BaseModel, Field

Platform = Literal["tiktok", "instagram", "facebook"]


class Post(BaseModel):
    platform: Platform
    external_id: str
    author_handle: str | None = None
    url: str | None = None
    published_at: datetime | None = None
    views: int | None = None
    likes: int | None = None
    comments: int | None = None
    shares: int | None = None
    caption: str | None = None
    hashtags: list[str] = Field(default_factory=list)
    sound_id: str | None = None
    sound_name: str | None = None
    duration_s: float | None = None
    thumbnail_url: str | None = None
    transcript: str | None = None
    author_followers: int | None = None
    raw: dict[str, Any] = Field(default_factory=dict)


class PlatformTrend(BaseModel):
    platform: Platform
    country: str
    trend_type: Literal["hashtag", "sound"]
    name: str
    external_id: str | None = None
    rank: int | None = None
    metrics: dict[str, Any] = Field(default_factory=dict)


class NewsItem(BaseModel):
    title: str
    url: str
    source: str | None = None
    snippet: str | None = None
    published_at: datetime | None = None
    raw: dict[str, Any] = Field(default_factory=dict)
