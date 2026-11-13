"""RSS news connector — fixtures only, no network."""

from __future__ import annotations

import re
from urllib.parse import parse_qs, urlparse

import pytest
from pytest_httpx import HTTPXMock

from virtualos.connectors import rss
from virtualos.connectors.base import RawBatch
from virtualos.connectors.rss import (
    RssNewsConnector,
    clean_text,
    google_news_url,
    is_relevant,
    keyword_hits,
)

KEYWORDS = ["ahorro", "deudas", "tarjetas de crédito", "inversión para principiantes"]

CURATED_XML = b"""<?xml version="1.0" encoding="UTF-8"?>
<rss version="2.0"><channel><title>Economia</title>
<item><title>Bancos suben tasas de las tarjetas de cr&#233;dito en noviembre</title>
<link>https://medio.example/tarjetas</link>
<description>&lt;p&gt;Las &lt;b&gt;tasas&lt;/b&gt; de usura...&lt;/p&gt;</description>
<pubDate>Fri, 13 Nov 2026 12:15:28 -0500</pubDate></item>
<item><title>Petroleras reportan resultados del trimestre</title>
<link>https://medio.example/petroleo</link>
<description>Sin relacion con el nicho.</description>
<pubDate>Fri, 13 Nov 2026 11:00:00 -0500</pubDate></item>
<item><title>Cinco formas de aumentar tu ahorro antes de diciembre</title>
<link>https://medio.example/ahorro</link>
<description>Consejos practicos.</description>
<pubDate>Thu, 12 Nov 2026 09:00:00 -0500</pubDate></item>
</channel></rss>"""

GNEWS_XML = b"""<?xml version="1.0" encoding="UTF-8"?>
<rss version="2.0"><channel><title>Google News</title>
<item><title>Ahorro de energ&#237;a frente a El Ni&#241;o - Ministerio</title>
<link>https://news.google.com/rss/articles/energia</link>
<pubDate>Fri, 13 Nov 2026 14:00:00 GMT</pubDate>
<source url="https://min.example">Ministerio</source></item>
<item><title>C&#243;mo salir de deudas y empezar tu ahorro - Revista Finanzas</title>
<link>https://news.google.com/rss/articles/deudas-ahorro</link>
<pubDate>Fri, 13 Nov 2026 15:30:00 GMT</pubDate>
<source url="https://rev.example">Revista Finanzas</source></item>
<item><title>Bancos suben tasas de las tarjetas de cr&#233;dito en noviembre - Portafolio</title>
<link>https://news.google.com/rss/articles/dup</link>
<pubDate>Fri, 13 Nov 2026 17:00:00 GMT</pubDate>
<source url="https://portafolio.example">Portafolio</source></item>
</channel></rss>"""


class TestRelevance:
    def test_multiword_keyword_needs_all_words(self) -> None:
        hits, multi = keyword_hits("Bancos suben tasas de tarjetas de crédito", KEYWORDS)
        assert hits == 1 and multi

    def test_accents_and_plural_stemming(self) -> None:
        # 'Inversion' (no accent) and 'principiante' (singular) still match.
        hits, multi = keyword_hits("Guia de inversion para el principiante", KEYWORDS)
        assert hits == 1 and multi
        assert keyword_hits("Cómo pagar tu deuda", KEYWORDS)[0] == 1  # deuda ~ deudas

    def test_curated_needs_one_hit(self) -> None:
        assert is_relevant("curated", "Cinco formas de aumentar tu ahorro", "", KEYWORDS)
        assert not is_relevant("curated", "Petroleras reportan resultados", "", KEYWORDS)

    def test_gnews_single_generic_hit_is_noise(self) -> None:
        # Seen live: 'ahorro de energía' leaked into a personal-finance niche.
        assert not is_relevant("gnews", "Ahorro de energía frente a El Niño", "", KEYWORDS)

    def test_keyword_only_in_summary_is_not_enough(self) -> None:
        # Seen live: a football match matched 'acciones' in its summary.
        summary = "Las acciones del partido minuto a minuto"
        assert not is_relevant("general", "Colombia vs. Chile EN VIVO", summary, ["acciones"])
        assert not is_relevant("curated", "Colombia vs. Chile EN VIVO", summary, ["acciones"])

    def test_general_feed_needs_title_plus_second_signal(self) -> None:
        kw = ["ahorro", "deudas"]
        assert not is_relevant("general", "Plan de ahorro del Gobierno", "", kw)
        assert is_relevant("general", "Plan de ahorro para salir de deudas", "", kw)
        assert is_relevant("general", "Plan de ahorro", "Ayuda a pagar deudas", kw)

    def test_gnews_two_hits_or_multiword_passes(self) -> None:
        assert is_relevant("gnews", "Cómo salir de deudas y empezar tu ahorro", "", KEYWORDS)
        assert is_relevant("gnews", "Suben las tarjetas de crédito", "", KEYWORDS)


def test_clean_text_strips_untrusted_html() -> None:
    assert clean_text("<p>Las <b>tasas</b> &amp; la usura</p>") == "Las tasas & la usura"
    assert clean_text(None) == ""


def test_google_news_url_is_fixed_host_with_freshness() -> None:
    url = google_news_url(KEYWORDS, "CO")
    parsed = urlparse(url)
    assert parsed.netloc == "news.google.com"  # never a user/LLM-chosen host
    q = parse_qs(parsed.query)
    assert "when:7d" in q["q"][0]
    assert '"tarjetas de crédito"' in q["q"][0]
    assert q["gl"] == ["CO"]


@pytest.fixture(autouse=True)
def _no_usage(monkeypatch: pytest.MonkeyPatch) -> None:
    async def noop(*a: object, **k: object) -> None:
        return None

    monkeypatch.setattr(rss, "record_usage", noop)


async def test_fetch_and_normalize_end_to_end(httpx_mock: HTTPXMock, monkeypatch) -> None:
    monkeypatch.setattr(
        rss, "CURATED_FEEDS", {"CO": [("Medio CO", "https://medio.example/rss.xml", "curated")]}
    )
    httpx_mock.add_response(url="https://medio.example/rss.xml", content=CURATED_XML)
    httpx_mock.add_response(
        url=re.compile(r"https://news\.google\.com/rss/search.*"), content=GNEWS_XML
    )

    conn = RssNewsConnector()
    raw = await conn.fetch(workspace_id="ws", params={"keywords": KEYWORDS, "country": "CO"})
    assert raw.meta["feeds_ok"] == 2
    items = conn.normalize(raw)

    titles = [n.title for n in items]
    # Noise filtered out (petroleum, energy saving), duplicate story collapsed.
    assert "Petroleras reportan resultados del trimestre" not in titles
    assert not any("energía" in t for t in titles)
    assert sum("tarjetas de crédito" in t for t in titles) == 1
    # Google News suffix " - Outlet" removed from title and kept as source.
    deudas = next(n for n in items if "deudas" in n.title)
    assert deudas.title == "Cómo salir de deudas y empezar tu ahorro"
    assert deudas.source == "Revista Finanzas"
    # Freshest first.
    dates = [n.published_at for n in items]
    assert dates == sorted(dates, reverse=True)
    # HTML stripped from snippets.
    assert all("<" not in (n.snippet or "") for n in items)


async def test_one_failing_feed_does_not_break_the_batch(
    httpx_mock: HTTPXMock, monkeypatch
) -> None:
    monkeypatch.setattr(
        rss,
        "CURATED_FEEDS",
        {
            "CO": [
                ("Caido", "https://caido.example/rss", "curated"),
                ("Medio CO", "https://medio.example/rss.xml", "curated"),
            ]
        },
    )
    httpx_mock.add_response(url="https://caido.example/rss", status_code=404)
    httpx_mock.add_response(url="https://medio.example/rss.xml", content=CURATED_XML)
    raw = await RssNewsConnector().fetch(
        workspace_id="ws", params={"keywords": [], "country": "CO"}
    )
    assert raw.meta == {"country": "CO", "keywords": [], "feeds_ok": 1, "feeds": 2}
    # No keywords: curated items pass through (economy sections), no Google query made.
    assert (
        len(RssNewsConnector().normalize(RawBatch(source="rss", items=raw.items, meta=raw.meta)))
        == 3
    )
