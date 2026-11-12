"""Instagram connector over Apify (apify/instagram-scraper, reels/posts)."""

from __future__ import annotations

from datetime import datetime
from typing import Any

from virtualos.config.settings import get_settings
from virtualos.connectors.apify import run_actor_sync
from virtualos.connectors.base import RawBatch
from virtualos.connectors.models import Post


def _parse_ts(value: Any) -> datetime | None:
    if not value:
        return None
    try:
        return datetime.fromisoformat(str(value).replace("Z", "+00:00"))
    except ValueError:
        return None


class InstagramProfilesConnector:
    """Posts/reels of specific Instagram profiles."""

    source = "instagram_profiles"

    async def fetch(self, *, workspace_id: str, params: dict[str, Any]) -> RawBatch:
        settings = get_settings()
        handles: list[str] = params["handles"]
        per_profile: int = int(params.get("results_per_profile", 20))
        run_input = {
            "directUrls": [f"https://www.instagram.com/{h.lstrip('@')}/" for h in handles],
            "resultsType": "posts",
            "resultsLimit": per_profile,
            "addParentData": True,
        }
        items = await run_actor_sync(
            settings.apify_actor_instagram_profiles,
            run_input,
            workspace_id=workspace_id,
            max_items=per_profile * len(handles),
        )
        return RawBatch(
            source=f"apify:{settings.apify_actor_instagram_profiles}",
            items=items,
            meta={"handles": handles},
        )

    def normalize(self, raw: RawBatch) -> list[Post]:
        posts: list[Post] = []
        for item in raw.items:
            external_id = str(item.get("id") or item.get("shortCode") or "")
            if not external_id:
                continue
            views = item.get("videoPlayCount") or item.get("videoViewCount")
            music = item.get("musicInfo") or {}
            posts.append(
                Post(
                    platform="instagram",
                    external_id=external_id,
                    author_handle=item.get("ownerUsername"),
                    url=item.get("url"),
                    published_at=_parse_ts(item.get("timestamp")),
                    views=views,
                    likes=item.get("likesCount"),
                    comments=item.get("commentsCount"),
                    shares=None,  # Instagram does not expose share counts
                    caption=item.get("caption"),
                    hashtags=list(item.get("hashtags") or []),
                    sound_id=str(music.get("audio_id")) if music.get("audio_id") else None,
                    sound_name=music.get("song_name"),
                    duration_s=item.get("videoDuration"),
                    thumbnail_url=item.get("displayUrl"),
                    author_followers=(item.get("ownerFollowersCount")),
                    raw=item,
                )
            )
        return posts
