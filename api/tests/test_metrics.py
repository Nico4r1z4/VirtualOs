from datetime import UTC, datetime, timedelta

from virtualos.metrics.scores import outlier_score, rank_score, velocity

NOW = datetime(2026, 11, 12, 12, 0, tzinfo=UTC)


class TestOutlier:
    def test_basic(self) -> None:
        # median of [10k]*10 = 10k; 50k views = 5.0x
        assert outlier_score(50_000, [10_000] * 10) == 5.0

    def test_minimum_sample(self) -> None:
        assert outlier_score(50_000, [10_000] * 4) is None  # < 5 posts
        assert outlier_score(50_000, [10_000] * 5) == 5.0

    def test_window_caps_at_20(self) -> None:
        # 20 recent at 10k + older garbage that must be ignored
        views = [10_000] * 20 + [1] * 50
        assert outlier_score(20_000, views) == 2.0

    def test_none_views(self) -> None:
        assert outlier_score(None, [10_000] * 10) is None

    def test_zero_median(self) -> None:
        assert outlier_score(100, [0] * 10) is None

    def test_filters_none_in_sample(self) -> None:
        sample = [10_000, None, 10_000, None, 10_000, 10_000, 10_000]
        assert outlier_score(30_000, sample) == 3.0  # type: ignore[arg-type]


class TestVelocity:
    def test_basic(self) -> None:
        snaps = [(NOW - timedelta(hours=2), 1000), (NOW, 3000)]
        assert velocity(snaps) == 1000.0

    def test_uses_latest_two(self) -> None:
        snaps = [
            (NOW - timedelta(hours=10), 0),
            (NOW - timedelta(hours=1), 1000),
            (NOW, 2000),
        ]
        assert velocity(snaps) == 1000.0

    def test_insufficient(self) -> None:
        assert velocity([(NOW, 100)]) is None
        assert velocity([]) is None

    def test_same_instant(self) -> None:
        assert velocity([(NOW, 100), (NOW, 200)]) is None

    def test_declining_views_negative(self) -> None:
        snaps = [(NOW - timedelta(hours=1), 2000), (NOW, 1500)]
        assert velocity(snaps) == -500.0


class TestRankScore:
    def test_fresh_post_keeps_score(self) -> None:
        assert rank_score(4.0, NOW, now=NOW) == 4.0

    def test_half_life(self) -> None:
        ten_days_ago = NOW - timedelta(days=10)
        assert rank_score(4.0, ten_days_ago, now=NOW, half_life_days=10) == 2.0

    def test_none_passthrough(self) -> None:
        assert rank_score(None, NOW, now=NOW) is None
        assert rank_score(4.0, None, now=NOW) is None

    def test_future_date_clamped(self) -> None:
        tomorrow = NOW + timedelta(days=1)
        assert rank_score(4.0, tomorrow, now=NOW) == 4.0
