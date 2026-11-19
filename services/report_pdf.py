"""PDF renderer for reports (used by PdfExporter).

Draws the format-neutral blocks of a ReportView: summary, heading, text, facts, notice, issue and table.
Every document opens with the same band: the TactiVision IA mark, the title and, when the team has
one, its crest. Section headings are numbered in order, so a long report reads like an index.
Uses fpdf2's core Helvetica font, which covers Spanish (á, é, ñ, ¿, ¡) through Latin-1; the few
characters outside it are replaced by close equivalents.
"""

from __future__ import annotations

import io
import logging
from pathlib import Path

from fpdf import FPDF
from fpdf.fonts import FontFace

logger = logging.getLogger("tactivision.reports")
ASSETS = Path(__file__).resolve().parent.parent / "assets"
LOGO_ON_DARK = ASSETS / "tactivision_logo_light.png"   # light letters, for the dark band
LOGO_ON_LIGHT = ASSETS / "tactivision_logo_dark.png"   # dark letters, for the white page
DEFAULT_CREST = ASSETS / "default_crest.png"           # plain shield when the team has no crest

INK = (11, 15, 14)
MUTED = (96, 104, 101)
LINE = (214, 219, 216)
ACCENT = (224, 37, 31)          # the red recording dot of the mark
GREEN = (46, 90, 28)            # the viewfinder green of the mark
GOLD = (242, 181, 68)
TONES = {"good": (27, 135, 80), "bad": (199, 54, 44), "warn": (186, 120, 0), None: INK}
WARN_BG = (253, 243, 222)
WARN_TEXT = (122, 77, 0)
# Left bar and meta colour of each issue block; "STRENGTH" is what the team did well (green).
SEVERITY = {"HIGH": (199, 54, 44), "MEDIUM": (186, 120, 0), "LOW": (46, 110, 180), "STRENGTH": (27, 135, 80)}

REPLACEMENTS = {"—": "-", "–": "-", "−": "-", "“": '"', "”": '"', "‘": "'", "’": "'", "…": "...",
                "⚠": "!", "→": "->", "≥": ">=", "≤": "<=", " ": " ", " ": " "}


def clean(text: object) -> str:
    """Text that the Latin-1 core font can draw."""
    value = str(text if text is not None else "")
    for source, target in REPLACEMENTS.items():
        value = value.replace(source, target)
    return value.encode("latin-1", "replace").decode("latin-1")


class ReportPdf(FPDF):
    def __init__(self, title: str) -> None:
        super().__init__(orientation="P", unit="mm", format="A4")
        self.report_title = clean(title)
        self.section = 0
        self.set_margins(18, 18, 18)
        self.set_auto_page_break(auto=True, margin=20)
        self.set_title(self.report_title)
        self.set_author("TactiVision IA")

    def header(self) -> None:
        if self.page_no() == 1:
            return  # the first page has the full band
        if LOGO_ON_LIGHT.is_file():
            self.image(str(LOGO_ON_LIGHT), x=self.l_margin, y=7, h=7)
        self.set_xy(self.l_margin + 9, 8)
        self.set_font("helvetica", "B", 8)
        self.set_text_color(*MUTED)
        self.cell(0, 5, clean(self.report_title.upper()))
        self.set_draw_color(*LINE)
        self.set_line_width(0.2)
        self.line(self.l_margin, 16, self.w - self.r_margin, 16)
        self.set_y(21)

    def footer(self) -> None:
        self.set_y(-13)
        self.set_draw_color(*LINE)
        self.set_line_width(0.2)
        self.line(self.l_margin, self.get_y() - 1, self.w - self.r_margin, self.get_y() - 1)
        self.set_font("helvetica", size=8)
        self.set_text_color(*MUTED)
        self.cell(0, 5, clean("TactiVision IA · Proyecto académico · Universidad Cooperativa de Colombia"), align="L")
        self.set_x(self.l_margin)
        self.cell(0, 5, clean(f"Página {self.page_no()} de {{nb}}"), align="R")


def _cover(pdf: ReportPdf, title: str, subtitle: str, meta: str | None, crest: bytes | None) -> None:
    """Dark band: the TactiVision IA mark on the left, the title in the middle, the team crest on the right."""
    band = 50
    pdf.set_fill_color(*INK)
    pdf.rect(0, 0, pdf.w, band, style="F")
    pdf.set_fill_color(*GREEN)
    pdf.rect(0, band, pdf.w, 1.4, style="F")
    pdf.set_fill_color(*ACCENT)
    pdf.rect(pdf.w - 40, band, 22, 1.4, style="F")

    text_x = pdf.l_margin
    if LOGO_ON_DARK.is_file():
        pdf.image(str(LOGO_ON_DARK), x=pdf.l_margin, y=11, h=28)
        text_x = pdf.l_margin + 35
    right = pdf.w - pdf.r_margin
    if not crest and DEFAULT_CREST.is_file():
        crest = DEFAULT_CREST.read_bytes()
    if crest:
        try:
            pdf.set_fill_color(255, 255, 255)
            pdf.rect(right - 30, 10, 30, 30, style="F", round_corners=True, corner_radius=4)
            pdf.image(io.BytesIO(crest), x=right - 27, y=13, w=24, h=24, keep_aspect_ratio=True)
            right -= 36
        except Exception:  # a damaged crest must never stop the report
            logger.warning("The team crest could not be drawn in the PDF")
    width = right - text_x

    pdf.set_xy(text_x, 11)
    pdf.set_text_color(*GOLD)
    pdf.set_font("helvetica", "B", 8)
    pdf.cell(width, 5, "TACTIVISION IA  ·  ANÁLISIS TÁCTICO", new_x="LEFT", new_y="NEXT")
    pdf.set_text_color(255, 255, 255)
    pdf.set_font("helvetica", "B", 17)
    pdf.multi_cell(width, 7.5, clean(title), new_x="LEFT", new_y="NEXT", max_line_height=7.5)
    pdf.set_font("helvetica", size=9.5)
    pdf.set_text_color(205, 210, 207)
    pdf.multi_cell(width, 5, clean(subtitle), new_x="LEFT", new_y="NEXT")
    if meta:
        pdf.set_font("helvetica", size=8)
        pdf.set_text_color(150, 158, 154)
        pdf.multi_cell(width, 4.5, clean(meta), new_x="LEFT", new_y="NEXT")
    pdf.set_y(band + 9)


def _heading(pdf: ReportPdf, text: str) -> None:
    """Numbered section title: a green number box and the name in capitals."""
    if pdf.get_y() > pdf.h - 70:  # keep the heading with the start of its section
        pdf.add_page()
    pdf.section += 1
    pdf.ln(3)
    y = pdf.get_y()
    pdf.set_fill_color(*GREEN)
    pdf.rect(pdf.l_margin, y, 9, 7, style="F", round_corners=True, corner_radius=1.2)
    pdf.set_xy(pdf.l_margin, y)
    pdf.set_font("helvetica", "B", 9.5)
    pdf.set_text_color(255, 255, 255)
    pdf.cell(9, 7, f"{pdf.section:02d}", align="C")
    pdf.set_xy(pdf.l_margin + 12, y)
    pdf.set_font("helvetica", "B", 12.5)
    pdf.set_text_color(*INK)
    pdf.cell(0, 7, clean(text.upper()), new_x="LMARGIN", new_y="NEXT")
    pdf.set_draw_color(*LINE)
    pdf.set_line_width(0.3)
    pdf.line(pdf.l_margin, pdf.get_y() + 1.5, pdf.w - pdf.r_margin, pdf.get_y() + 1.5)
    pdf.ln(4.5)


def _summary(pdf: ReportPdf, block: dict) -> None:
    """A row of tiles with the numbers to read first: big value, label under it, optional colour."""
    tiles = block["tiles"]
    gap = 4
    width = (pdf.w - pdf.l_margin - pdf.r_margin - gap * (len(tiles) - 1)) / len(tiles)
    y = pdf.get_y()
    for index, tile in enumerate(tiles):
        x = pdf.l_margin + index * (width + gap)
        pdf.set_fill_color(246, 247, 246)
        pdf.set_draw_color(*LINE)
        pdf.set_line_width(0.2)
        pdf.rect(x, y, width, 21, style="DF", round_corners=True, corner_radius=2.5)
        pdf.set_fill_color(*TONES.get(tile.get("tone"), INK))
        pdf.rect(x, y + 3, 1.2, 15, style="F")
        pdf.set_xy(x + 4, y + 3)
        pdf.set_font("helvetica", "B", 15)
        pdf.set_text_color(*TONES.get(tile.get("tone"), INK))
        pdf.cell(width - 6, 8, clean(tile["value"]))
        pdf.set_xy(x + 4, y + 11.5)
        pdf.set_font("helvetica", size=7.5)
        pdf.set_text_color(*MUTED)
        pdf.multi_cell(width - 6, 3.6, clean(tile["label"]), align="L", new_x="LMARGIN", new_y="NEXT")
    pdf.set_xy(pdf.l_margin, y + 25)


def _text(pdf: ReportPdf, text: str) -> None:
    pdf.set_font("helvetica", size=9.5)
    pdf.set_text_color(*MUTED)
    pdf.multi_cell(0, 5, clean(text), align="L", new_x="LMARGIN", new_y="NEXT")
    pdf.ln(1.5)


def _facts(pdf: ReportPdf, items: list[tuple[str, str]]) -> None:
    """Key/value pairs in two columns."""
    column = (pdf.w - pdf.l_margin - pdf.r_margin) / 2
    for index in range(0, len(items), 2):
        y = pdf.get_y()
        heights = []
        for offset, (key, value) in enumerate(items[index:index + 2]):
            x = pdf.l_margin + offset * column
            pdf.set_xy(x, y)
            pdf.set_font("helvetica", size=7.5)
            pdf.set_text_color(*MUTED)
            pdf.cell(column - 4, 4, clean(key.upper()), new_x="LEFT", new_y="NEXT")
            pdf.set_font("helvetica", "B", 10)
            pdf.set_text_color(*INK)
            pdf.multi_cell(column - 4, 5, clean(value), new_x="LEFT", new_y="NEXT")
            heights.append(pdf.get_y() - y)
        pdf.set_xy(pdf.l_margin, y + max(heights) + 2.5)


def _notice(pdf: ReportPdf, text: str) -> None:
    pdf.set_fill_color(*WARN_BG)
    pdf.set_text_color(*WARN_TEXT)
    pdf.set_font("helvetica", "B", 9)
    pdf.multi_cell(0, 5.5, clean(f"  {text}"), fill=True, new_x="LMARGIN", new_y="NEXT")
    pdf.ln(2)


def _issue(pdf: ReportPdf, block: dict) -> None:
    if pdf.get_y() > pdf.h - 50:
        pdf.add_page()
    top = pdf.get_y()
    pdf.set_x(pdf.l_margin + 4)
    pdf.set_font("helvetica", "B", 10.5)
    pdf.set_text_color(*INK)
    width = pdf.w - pdf.l_margin - pdf.r_margin - 4
    pdf.multi_cell(width, 5.2, clean(block["title"]), new_x="LEFT", new_y="NEXT")
    pdf.set_font("helvetica", size=8.5)
    pdf.set_text_color(*SEVERITY.get(block.get("severity", ""), MUTED))
    pdf.multi_cell(width, 4.6, clean(block["meta"]), new_x="LEFT", new_y="NEXT")
    pdf.set_font("helvetica", size=9)
    pdf.set_text_color(*MUTED)
    details = block.get("details") or (("Evidencia", block.get("evidence")), ("Recomendación", block.get("recommendation")))
    for label, value in details:
        if value:
            # Markdown bold keeps label and text in one paragraph, so wrapped lines start at the margin.
            pdf.multi_cell(width, 4.8, f"**{clean(label)}:** {clean(value)}", markdown=True, align="L",
                           new_x="LEFT", new_y="NEXT")
    bottom = pdf.get_y()
    pdf.set_draw_color(*SEVERITY.get(block.get("severity", ""), LINE))
    pdf.set_line_width(1)
    pdf.line(pdf.l_margin + 0.5, top + 0.5, pdf.l_margin + 0.5, bottom - 0.5)
    pdf.set_xy(pdf.l_margin, bottom + 3)


def _table(pdf: ReportPdf, block: dict) -> None:
    if pdf.get_y() > pdf.h - 40:
        pdf.add_page()
    pdf.set_font("helvetica", size=8.5)
    pdf.set_text_color(*INK)
    pdf.set_draw_color(*LINE)
    pdf.set_line_width(0.2)
    pdf.set_fill_color(255, 255, 255)  # do not inherit the notice background
    headings = FontFace(emphasis="BOLD", color=(255, 255, 255), fill_color=INK)
    with pdf.table(col_widths=tuple(block["widths"]), headings_style=headings, line_height=5.2,
                   borders_layout="HORIZONTAL_LINES", cell_fill_color=(246, 247, 246), cell_fill_mode="ROWS",
                   padding=1.4, text_align="LEFT") as table:
        header = table.row()
        for column in block["columns"]:
            header.cell(clean(column))
        for values in block["rows"]:
            row = table.row()
            for value in values:
                row.cell(clean(value))
    pdf.ln(3)


SERIES = ((57, 135, 229), (217, 89, 38), (25, 158, 112), (201, 133, 0))   # one colour per compared match
CHANGE = {"BETTER": (27, 135, 80), "WORSE": (199, 54, 44), "SAME": (120, 128, 125), None: (120, 128, 125)}


def _legend(pdf: ReportPdf, block: dict) -> None:
    """One line per compared match with the colour it has in every chart."""
    for index, (title, detail) in enumerate(block["items"]):
        y = pdf.get_y()
        pdf.set_fill_color(*SERIES[index % len(SERIES)])
        pdf.rect(pdf.l_margin, y + 1.2, 3.6, 3.6, style="F")
        pdf.set_xy(pdf.l_margin + 6, y)
        pdf.set_font("helvetica", "B", 10)
        pdf.set_text_color(*INK)
        pdf.cell(0, 6, clean(title), new_x="LMARGIN", new_y="NEXT")
        pdf.set_x(pdf.l_margin + 6)
        pdf.set_font("helvetica", size=8.5)
        pdf.set_text_color(*MUTED)
        pdf.multi_cell(0, 4.5, clean(detail), new_x="LMARGIN", new_y="NEXT")
        pdf.ln(1.5)
    pdf.ln(1)


def _bars(pdf: ReportPdf, block: dict) -> None:
    """One indicator: a horizontal bar per match (its colour), the value at the end, the threshold as a line."""
    bars = block["bars"]
    height = 9 + 6 * len(bars) + 7
    if pdf.get_y() + height > pdf.h - pdf.b_margin:
        pdf.add_page()
    pdf.set_font("helvetica", "B", 9.5)
    pdf.set_text_color(*INK)
    pdf.cell(0, 5, clean(block["title"]), new_x="LMARGIN", new_y="NEXT")
    pdf.set_font("helvetica", size=8)
    pdf.set_text_color(*MUTED)
    pdf.cell(0, 4, clean(block["note"]), new_x="LMARGIN", new_y="NEXT")
    label_width, value_width = 42, 30
    track = pdf.w - pdf.l_margin - pdf.r_margin - label_width - value_width
    numbers = [bar["value"] for bar in bars if bar["value"] is not None] + ([block["threshold"]] if block.get("threshold") is not None else [])
    top = max([abs(n) for n in numbers] or [1]) or 1
    start_y = pdf.get_y() + 1
    for index, bar in enumerate(bars):
        y = start_y + index * 6
        pdf.set_xy(pdf.l_margin, y)
        pdf.set_font("helvetica", size=8)
        pdf.set_text_color(*INK)
        pdf.cell(label_width, 5, clean(bar["label"])[:28])
        x = pdf.l_margin + label_width
        pdf.set_fill_color(238, 240, 239)
        pdf.rect(x, y + 0.8, track, 3.4, style="F")
        if bar["value"] is not None:
            pdf.set_fill_color(*SERIES[bar["slot"] % len(SERIES)])
            pdf.rect(x, y + 0.8, max(0.6, track * abs(bar["value"]) / top), 3.4, style="F")
        pdf.set_xy(x + track + 2, y)
        pdf.set_font("helvetica", "B" if bar.get("flag") else "", 8)
        pdf.set_text_color(*(SEVERITY["HIGH"] if bar.get("flag") else INK))
        pdf.cell(value_width - 2, 5, clean(bar["text"] + (" !" if bar.get("flag") else "")))
    if block.get("threshold") is not None:
        x = pdf.l_margin + label_width + track * abs(block["threshold"]) / top
        pdf.set_draw_color(*INK)
        pdf.set_line_width(0.3)
        pdf.set_dash_pattern(dash=1, gap=1)
        pdf.line(x, start_y, x, start_y + 6 * len(bars) - 1)
        pdf.set_dash_pattern()
    pdf.set_xy(pdf.l_margin, start_y + 6 * len(bars))
    pdf.set_font("helvetica", size=8)
    pdf.set_text_color(*CHANGE[block.get("assessment")])
    pdf.cell(0, 5, clean(block["difference"]), new_x="LMARGIN", new_y="NEXT")
    pdf.ln(2.5)


def _changes(pdf: ReportPdf, block: dict) -> None:
    """Differences chart: change of each indicator from the first to the last match, in percent of the
    first. Bars grow to the right when the value went up and to the left when it went down; green is
    better for the team, red is worse."""
    rows = block["rows"]
    if pdf.get_y() + 8 + 6.5 * min(len(rows), 6) > pdf.h - pdf.b_margin:
        pdf.add_page()
    label_width, value_width = 66, 24
    track = pdf.w - pdf.l_margin - pdf.r_margin - label_width - value_width
    centre = pdf.l_margin + label_width + track / 2
    top = max([abs(row["percent"]) for row in rows] or [1]) or 1
    for row in rows:
        if pdf.get_y() + 7 > pdf.h - pdf.b_margin:
            pdf.add_page()
        y = pdf.get_y()
        pdf.set_font("helvetica", size=8)
        pdf.set_text_color(*INK)
        pdf.set_xy(pdf.l_margin, y)
        pdf.cell(label_width, 5.5, clean(row["label"])[:44])
        length = (track / 2) * abs(row["percent"]) / top
        pdf.set_fill_color(*CHANGE[row["assessment"]])
        pdf.rect(centre if row["percent"] >= 0 else centre - length, y + 1, max(0.5, length), 3.5, style="F")
        pdf.set_xy(pdf.l_margin + label_width + track + 2, y)
        pdf.set_font("helvetica", "B", 8)
        pdf.set_text_color(*CHANGE[row["assessment"]])
        pdf.cell(value_width - 2, 5.5, clean(row["text"]), new_x="LMARGIN", new_y="NEXT")
        pdf.set_draw_color(*LINE)
        pdf.set_line_width(0.2)
        pdf.line(centre, y, centre, y + 5.5)
    pdf.ln(3)


RENDERERS = {
    "legend": _legend,
    "bars": _bars,
    "changes": _changes,
    "summary": _summary,
    "heading": lambda pdf, block: _heading(pdf, block["text"]),
    "text": lambda pdf, block: _text(pdf, block["text"]),
    "facts": lambda pdf, block: _facts(pdf, block["items"]),
    "notice": lambda pdf, block: _notice(pdf, block["text"]),
    "issue": _issue,
    "table": _table,
}


def render_pdf(title: str, subtitle: str, blocks: list[dict], *, meta: str | None = None,
               crest: bytes | None = None) -> bytes:
    pdf = ReportPdf(title)
    pdf.add_page()
    _cover(pdf, title, subtitle, meta, crest)
    for block in blocks:
        RENDERERS[block["kind"]](pdf, block)
    return bytes(pdf.output())
