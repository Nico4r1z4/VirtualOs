"""Pure metric functions (CLAUDE.md):

- outlier  = views / median(views of the author's last N posts), N=20, min 5
- velocity = delta views / delta hours between post_snapshots
- ranking  = outlier weighted by recency (half-life 7-14 days, default 10)

Pure and fully unit-tested; no DB access here.
"""

from __future__ import annotations

import math
from datetime import datetime
from statistics import median

OUTLIER_WINDOW = 20
OUTLIER_MIN_POSTS = 5
DEFAULT_HALF_LIFE_DAYS = 10.0


def outlier_score(views: int | None, author_recent_views: list[int]) -> float | None:
    """views / median of the author's recent views.

    Returns None when views is missing, when the author has fewer than
    OUTLIER_MIN_POSTS posts with views, or when the median is 0.
    """
    if views is None:
        return None
    sample = [v for v in author_recent_views[:OUTLIER_WINDOW] if v is not None]
    if len(sample) < OUTLIER_MIN_POSTS:
        return None
    med = median(sample)
    if med <= 0:
        return None
    return round(views / med, 3)


def velocity(
    snapshots: list[tuple[datetime, int | None]],
) -> float | None:
    """Views gained per hour between the two most recent usable snapshots."""
    usable = [(t, v) for t, v in snapshots if v is not None]
    if len(usable) < 2:
        return None
    usable.sort(key=lambda s: s[0])
    (t0, v0), (t1, v1) = usable[-2], usable[-1]
    hours = (t1 - t0).total_seconds() / 3600
    if hours <= 0:
        return None
    return round((v1 - v0) / hours, 3)


def rank_score(
    outlier: float | None,
    published_at: datetime | None,
    *,
    now: datetime,
    half_life_days: float = DEFAULT_HALF_LIFE_DAYS,
) -> float | None:
    """Outlier score decayed by age: score * 0.5^(age_days / half_life)."""
    if outlier is None or published_at is None:
        return None
    age_days = max(0.0, (now - published_at).total_seconds() / 86400)
    return round(outlier * math.pow(0.5, age_days / half_life_days), 6)
