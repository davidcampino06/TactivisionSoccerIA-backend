"""PDF renderer for reports (used by PdfExporter).

Draws the format-neutral blocks of a ReportView: heading, text, facts, notice, issue and table.
Uses fpdf2's core Helvetica font, which covers Spanish (á, é, ñ, ¿, ¡) through Latin-1; the few
characters outside it are replaced by close equivalents.
"""

from __future__ import annotations

from fpdf import FPDF
from fpdf.fonts import FontFace

INK = (11, 15, 14)
MUTED = (96, 104, 101)
LINE = (214, 219, 216)
ACCENT = (227, 50, 74)          # brand red
WARN_BG = (253, 243, 222)
WARN_TEXT = (122, 77, 0)
SEVERITY = {"HIGH": (199, 54, 44), "MEDIUM": (186, 120, 0), "LOW": (46, 110, 180)}

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
        self.set_margins(18, 18, 18)
        self.set_auto_page_break(auto=True, margin=18)
        self.set_title(self.report_title)
        self.set_author("TactiVision IA")

    def footer(self) -> None:
        self.set_y(-12)
        self.set_font("helvetica", size=8)
        self.set_text_color(*MUTED)
        self.cell(0, 5, clean(f"TactiVision IA · {self.report_title}"), align="L")
        self.set_x(self.l_margin)
        self.cell(0, 5, clean(f"Página {self.page_no()} de {{nb}}"), align="R")


def _cover(pdf: ReportPdf, title: str, subtitle: str) -> None:
    pdf.set_fill_color(*INK)
    pdf.rect(0, 0, pdf.w, 46, style="F")
    pdf.set_fill_color(*ACCENT)
    pdf.rect(0, 46, pdf.w, 1.2, style="F")
    pdf.set_xy(pdf.l_margin, 12)
    pdf.set_text_color(242, 181, 68)
    pdf.set_font("helvetica", "B", 8.5)
    pdf.cell(0, 5, "TACTIVISION IA  ·  ANÁLISIS TÁCTICO", new_x="LMARGIN", new_y="NEXT")
    pdf.set_text_color(255, 255, 255)
    pdf.set_font("helvetica", "B", 18)
    pdf.multi_cell(0, 8, clean(title), new_x="LMARGIN", new_y="NEXT")
    pdf.set_font("helvetica", size=9.5)
    pdf.set_text_color(205, 210, 207)
    pdf.cell(0, 6, clean(subtitle), new_x="LMARGIN", new_y="NEXT")
    pdf.set_y(54)


def _heading(pdf: ReportPdf, text: str) -> None:
    if pdf.get_y() > pdf.h - 70:  # keep the heading with the start of its section
        pdf.add_page()
    pdf.ln(4)
    pdf.set_font("helvetica", "B", 12.5)
    pdf.set_text_color(*INK)
    pdf.cell(0, 7, clean(text.upper()), new_x="LMARGIN", new_y="NEXT")
    pdf.set_draw_color(*ACCENT)
    pdf.set_line_width(0.5)
    pdf.line(pdf.l_margin, pdf.get_y(), pdf.l_margin + 18, pdf.get_y())
    pdf.ln(3)


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
    for label, value in (("Evidencia", block.get("evidence")), ("Recomendación", block.get("recommendation"))):
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
                   padding=1.4) as table:
        header = table.row()
        for column in block["columns"]:
            header.cell(clean(column))
        for values in block["rows"]:
            row = table.row()
            for value in values:
                row.cell(clean(value))
    pdf.ln(3)


RENDERERS = {
    "heading": lambda pdf, block: _heading(pdf, block["text"]),
    "text": lambda pdf, block: _text(pdf, block["text"]),
    "facts": lambda pdf, block: _facts(pdf, block["items"]),
    "notice": lambda pdf, block: _notice(pdf, block["text"]),
    "issue": _issue,
    "table": _table,
}


def render_pdf(title: str, subtitle: str, blocks: list[dict]) -> bytes:
    pdf = ReportPdf(title)
    pdf.add_page()
    _cover(pdf, title, subtitle)
    for block in blocks:
        RENDERERS[block["kind"]](pdf, block)
    return bytes(pdf.output())
