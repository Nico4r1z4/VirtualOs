"""TikTok connectors over Apify: profile posts + Creative Center trends."""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Any

from virtualos.config.settings import get_settings
from virtualos.connectors.apify import run_actor_sync
from virtualos.connectors.base import RawBatch
from virtualos.connectors.models import PlatformTrend, Post


def _parse_ts(item: dict[str, Any]) -> datetime | None:
    iso = item.get("createTimeISO")
    if iso:
        try:
            return datetime.fromisoformat(str(iso).replace("Z", "+00:00"))
        except ValueError:
            pass
    epoch = item.get("createTime")
    if isinstance(epoch, (int, float)) and epoch > 0:
        return datetime.fromtimestamp(epoch, tz=UTC)
    return None


class TikTokProfilesConnector:
    """Posts of specific TikTok profiles (clockworks/tiktok-scraper shape)."""

    source = "tiktok_profiles"

    async def fetch(self, *, workspace_id: str, params: dict[str, Any]) -> RawBatch:
        settings = get_settings()
        handles: list[str] = params["handles"]
        per_profile: int = int(params.get("results_per_profile", 20))
        run_input = {
            "profiles": handles,
            "resultsPerPage": per_profile,
            "excludePinnedPosts": True,
            "shouldDownloadVideos": False,
            "shouldDownloadCovers": False,
            "shouldDownloadSubtitles": True,
        }
        items = await run_actor_sync(
            settings.apify_actor_tiktok_profiles,
            run_input,
            workspace_id=workspace_id,
            max_items=per_profile * len(handles),
        )
        return RawBatch(
            source=f"apify:{settings.apify_actor_tiktok_profiles}",
            items=items,
            meta={"handles": handles},
        )

    def normalize(self, raw: RawBatch) -> list[Post]:
        posts: list[Post] = []
        for item in raw.items:
            external_id = str(item.get("id") or "")
            if not external_id:
                continue
            author = item.get("authorMeta") or {}
            music = item.get("musicMeta") or {}
            video = item.get("videoMeta") or {}
            hashtags = [
                h["name"] for h in item.get("hashtags") or [] if isinstance(h, dict) and h.get("name")
            ]
            subtitles = item.get("videoMeta", {}).get("subtitleLinks") or []
            posts.append(
                Post(
                    platform="tiktok",
                    external_id=external_id,
                    author_handle=author.get("name"),
                    url=item.get("webVideoUrl"),
                    published_at=_parse_ts(item),
                    views=item.get("playCount"),
                    likes=item.get("diggCount"),
                    comments=item.get("commentCount"),
                    shares=item.get("shareCount"),
                    caption=item.get("text"),
                    hashtags=hashtags,
                    sound_id=str(music.get("musicId")) if music.get("musicId") else None,
                    sound_name=music.get("musicName"),
                    duration_s=video.get("duration"),
                    thumbnail_url=video.get("coverUrl"),
                    author_followers=author.get("fans"),
                    raw={**item, "_subtitle_links": subtitles},
                )
            )
        return posts


class TikTokTrendsConnector:
    """Creative Center trending hashtags by country."""

    source = "tiktok_trends"

    async def fetch(self, *, workspace_id: str, params: dict[str, Any]) -> RawBatch:
        settings = get_settings()
        country: str = params.get("country", "CO")
        limit: int = int(params.get("limit", 50))
        run_input = {
            "countryCode": country.upper(),
            "maxItems": limit,
            "period": params.get("period", "7"),
        }
        items = await run_actor_sync(
            settings.apify_actor_tiktok_trends,
            run_input,
            workspace_id=workspace_id,
            max_items=limit,
        )
        return RawBatch(
            source=f"apify:{settings.apify_actor_tiktok_trends}",
            items=items,
            meta={"country": country.upper()},
        )

    def normalize(self, raw: RawBatch) -> list[PlatformTrend]:
        country = raw.meta.get("country", "")
        trends: list[PlatformTrend] = []
        for item in raw.items:
            name = (
                item.get("hashtagName")
                or item.get("hashtag")
                or item.get("name")
                or item.get("title")
            )
            if not name:
                continue
            metrics = {
                k: item[k]
                for k in ("publishCnt", "videoViews", "viewCount", "postCount", "trend")
                if k in item
            }
            trends.append(
                PlatformTrend(
                    platform="tiktok",
                    country=str(item.get("countryCode") or country),
                    trend_type="hashtag",
                    name=str(name).lstrip("#"),
                    external_id=str(item.get("hashtagId")) if item.get("hashtagId") else None,
                    rank=item.get("rank") or item.get("position"),
                    metrics=metrics,
                )
            )
        return trends
