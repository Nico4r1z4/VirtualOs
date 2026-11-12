"""Weekly brief PDF export (reportlab). Adapted from orkiza-captacion's
pdf_renderer pattern, without personal data or signature assets."""

from __future__ import annotations

import io
from typing import Any

from reportlab.lib import colors
from reportlab.lib.pagesizes import letter
from reportlab.lib.styles import ParagraphStyle
from reportlab.lib.units import mm
from reportlab.platypus import (
    HRFlowable,
    Paragraph,
    SimpleDocTemplate,
    Spacer,
    Table,
    TableStyle,
)

NAVY = colors.HexColor("#1e2a38")
BLUE = colors.HexColor("#1d9bf0")
GRAY = colors.HexColor("#637180")
LIGHT = colors.HexColor("#eef1f5")

_TITLE = ParagraphStyle(
    "title", fontName="Helvetica-Bold", fontSize=20, textColor=NAVY, spaceAfter=2
)
_SUB = ParagraphStyle("sub", fontName="Helvetica", fontSize=10, textColor=GRAY, spaceAfter=10)
_H2 = ParagraphStyle(
    "h2", fontName="Helvetica-Bold", fontSize=13, textColor=NAVY, spaceBefore=12, spaceAfter=4
)
_BODY = ParagraphStyle("body", fontName="Helvetica", fontSize=9.5, textColor=NAVY, leading=13)
_SMALL = ParagraphStyle("small", fontName="Helvetica", fontSize=8, textColor=GRAY, leading=11)
_DAY = ParagraphStyle("day", fontName="Helvetica-Bold", fontSize=9, textColor=BLUE)


def _esc(text: str | None) -> str:
    if not text:
        return ""
    return text.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")


def render_brief_pdf(
    *,
    niche_name: str,
    week_start: str,
    summary: str | None,
    ideas: list[dict[str, Any]],
) -> io.BytesIO:
    """ideas: [{title, angle, hook_suggestion, script_outline, day, evidence_count}]"""
    buf = io.BytesIO()
    doc = SimpleDocTemplate(
        buf,
        pagesize=letter,
        topMargin=18 * mm,
        bottomMargin=16 * mm,
        leftMargin=18 * mm,
        rightMargin=18 * mm,
        title=f"Brief semanal — {niche_name}",
    )

    story: list[Any] = [
        Paragraph("Brief semanal de grabación", _TITLE),
        Paragraph(
            f"Nicho: {_esc(niche_name)} · Semana del {_esc(week_start)} · VirtualOS (Orkiza)", _SUB
        ),
        HRFlowable(width="100%", thickness=1.5, color=BLUE),
    ]

    if summary:
        story.append(Paragraph("Qué está funcionando", _H2))
        story.append(Paragraph(_esc(summary), _BODY))

    story.append(Paragraph("Plan de la semana", _H2))

    for idea in ideas:
        rows = [
            [
                Paragraph(_esc(idea.get("day", "")).upper(), _DAY),
                Paragraph(f"<b>{_esc(idea.get('title'))}</b>", _BODY),
            ]
        ]
        if idea.get("hook_suggestion"):
            rows.append(["", Paragraph(f"<b>Gancho:</b> {_esc(idea['hook_suggestion'])}", _BODY)])
        if idea.get("angle"):
            rows.append(["", Paragraph(f"<b>Por qué:</b> {_esc(idea['angle'])}", _SMALL)])
        if idea.get("script_outline"):
            outline = _esc(idea["script_outline"]).replace("\n", "<br/>")
            rows.append(["", Paragraph(f"<b>Guion:</b><br/>{outline}", _SMALL)])
        rows.append(
            ["", Paragraph(f"Evidencia: {idea.get('evidence_count', 0)} piezas enlazadas", _SMALL)]
        )

        table = Table(rows, colWidths=[22 * mm, None])
        table.setStyle(
            TableStyle(
                [
                    ("VALIGN", (0, 0), (-1, -1), "TOP"),
                    ("BACKGROUND", (0, 0), (-1, -1), colors.white),
                    ("LINEBELOW", (0, -1), (-1, -1), 0.5, LIGHT),
                    ("TOPPADDING", (0, 0), (-1, 0), 6),
                    ("BOTTOMPADDING", (0, -1), (-1, -1), 8),
                ]
            )
        )
        story.append(table)

    story.append(Spacer(1, 10))
    story.append(
        Paragraph(
            "Cada idea está anclada a evidencia real del nicho (posts outliers, tendencias y noticias). "
            "Generado por VirtualOS.",
            _SMALL,
        )
    )

    doc.build(story)
    buf.seek(0)
    return buf
