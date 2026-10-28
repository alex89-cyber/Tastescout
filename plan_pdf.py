"""PDF del plan de TasteScout: plan del agente + calendario de 4 semanas."""

from __future__ import annotations

import re
from datetime import date

from fpdf import FPDF

# Las fuentes base de fpdf solo cubren latin-1: cambia la puntuación tipográfica
# y quita lo que no quepa (emojis), para que el PDF nunca falle.
_REPLACE = {"–": "-", "—": "-", "“": '"', "”": '"', "‘": "'", "’": "'", "…": "...", "•": "-", "→": "->"}


def _latin1(text: str) -> str:
    for a, b in _REPLACE.items():
        text = text.replace(a, b)
    return text.encode("latin-1", "ignore").decode("latin-1")


def _inline(text: str) -> str:
    """Deja solo negritas (**) para fpdf; quita cursivas y código."""
    text = re.sub(r"(?<!\*)\*(?!\*)([^*]+)\*(?!\*)", r"\1", text)
    return _latin1(text.replace("`", ""))


def build_pdf(title: str, subtitle: str, plan_md: str, calendar: list[dict]) -> bytes:
    pdf = FPDF(format="Letter")
    pdf.set_margins(15, 15, 15)
    pdf.set_auto_page_break(True, margin=15)
    pdf.add_page()

    pdf.set_font("Helvetica", "B", 18)
    pdf.cell(0, 9, _latin1(title), new_x="LMARGIN", new_y="NEXT")
    pdf.set_font("Helvetica", "", 9)
    pdf.set_text_color(100)
    pdf.cell(0, 5, _latin1(f"{subtitle} · {date.today():%d/%m/%Y} · Datos de Qloo Taste AI"), new_x="LMARGIN", new_y="NEXT")
    pdf.set_text_color(0)
    pdf.ln(3)

    for line in plan_md.splitlines():
        line = line.rstrip()
        if not line.strip() or line.strip() == "---":
            pdf.ln(1.5)
            continue
        heading = re.match(r"^(#{1,4})\s+(.*)", line)
        if heading:
            pdf.ln(1.5)
            pdf.set_font("Helvetica", "B", 12 if len(heading.group(1)) <= 2 else 10)
            pdf.multi_cell(0, 6, _inline(heading.group(2)).replace("**", ""), new_x="LMARGIN", new_y="NEXT")
            continue
        bullet = re.match(r"^(\s*)([-*]|\d+\.)\s+(.*)", line)
        pdf.set_font("Helvetica", "", 9)
        if bullet:
            indent = 4 + min(len(bullet.group(1)), 8)
            marker = bullet.group(2) if bullet.group(2)[0].isdigit() else "-"
            pdf.set_x(pdf.l_margin + indent)
            pdf.multi_cell(0, 4.5, f"{marker} {_inline(bullet.group(3))}", markdown=True, new_x="LMARGIN", new_y="NEXT")
        else:
            pdf.multi_cell(0, 4.5, _inline(line), markdown=True, new_x="LMARGIN", new_y="NEXT")

    if calendar:
        pdf.ln(4)
        pdf.set_font("Helvetica", "B", 12)
        pdf.cell(0, 7, "Calendario de publicaciones (4 semanas)", new_x="LMARGIN", new_y="NEXT")
        pdf.set_font("Helvetica", "", 8)
        with pdf.table(col_widths=(12, 18, 20, 80, 50), line_height=4.5, first_row_as_headings=True) as table:
            table.row(["Sem.", "Día", "Formato", "Tema", "Inspiración (Qloo)"])
            for row in calendar:
                table.row([_latin1(str(row.get(k, ""))) for k in ("semana", "dia", "formato", "tema", "inspiracion")])

    return bytes(pdf.output())
