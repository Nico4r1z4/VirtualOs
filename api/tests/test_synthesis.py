"""Synthesis unit tests: VTT parsing, hook JSON parsing, evidence validation."""

from __future__ import annotations

from virtualos.synthesis.brief import _parse_ideas, parse_evidence
from virtualos.synthesis.hooks import _parse_hook
from virtualos.synthesis.prompts import wrap_untrusted
from virtualos.synthesis.transcripts import parse_vtt, pick_subtitle_link

VTT = """WEBVTT

00:00:00.000 --> 00:00:02.500
¿Sabías que el 80% de tu sueldo

00:00:02.500 --> 00:00:05.000
se va en gastos que no registras?

00:00:05.000 --> 00:00:07.000
se va en gastos que no registras?
"""


class TestTranscripts:
    def test_parse_vtt(self) -> None:
        text = parse_vtt(VTT)
        assert "¿Sabías que el 80% de tu sueldo" in text
        assert "WEBVTT" not in text
        assert "-->" not in text
        # Consecutive duplicate line removed
        assert text.count("se va en gastos") == 1

    def test_pick_subtitle_prefers_spanish(self) -> None:
        raw = {
            "_subtitle_links": [
                {"language": "eng-US", "downloadLink": "https://cdn.example/en.vtt"},
                {"language": "spa-ES", "downloadLink": "https://cdn.example/es.vtt"},
            ]
        }
        assert pick_subtitle_link(raw) == "https://cdn.example/es.vtt"

    def test_pick_subtitle_fallback_first(self) -> None:
        raw = {
            "_subtitle_links": [
                {"language": "eng-US", "downloadLink": "https://cdn.example/en.vtt"}
            ]
        }
        assert pick_subtitle_link(raw) == "https://cdn.example/en.vtt"
        assert pick_subtitle_link({}) is None


class TestHookParsing:
    def test_valid_json(self) -> None:
        text = 'Claro: {"hook_text": "¿Sabías que...?", "hook_type": "pregunta", "structure": {"beats": ["a"]}, "cta": null, "language": "es"}'
        hook = _parse_hook(text)
        assert hook is not None
        assert hook.hook_type == "pregunta"

    def test_garbage_returns_none(self) -> None:
        assert _parse_hook("no hay json aquí") is None
        assert _parse_hook('{"hook_text": }') is None


class TestEvidence:
    def test_valid_refs_kept(self) -> None:
        posts, trends, news = parse_evidence(
            ["post:p1", "trend:t1", "news:n1"],
            valid_posts={"p1"},
            valid_trends={"t1"},
            valid_news={"n1"},
        )
        assert posts == ["p1"] and trends == ["t1"] and news == ["n1"]

    def test_invented_ids_discarded(self) -> None:
        posts, trends, news = parse_evidence(
            ["post:fake", "trend:t1", "garbage", "news:"],
            valid_posts={"p1"},
            valid_trends={"t1"},
            valid_news={"n1"},
        )
        assert posts == []
        assert trends == ["t1"]
        assert news == []

    def test_ideas_response_parsing(self) -> None:
        text = '{"summary": "resumen", "ideas": [{"title": "Idea 1", "evidence": ["post:x"]}]}'
        parsed = _parse_ideas(text)
        assert parsed is not None
        assert parsed.ideas[0].title == "Idea 1"
        assert _parse_ideas("not json") is None


def test_wrap_untrusted_delimits() -> None:
    out = wrap_untrusted("texto scrapeado")
    assert out.startswith("<contenido_no_confiable>")
    assert out.endswith("</contenido_no_confiable>")
