from datetime import datetime
from pathlib import Path
import re

from arabic_reshaper import reshape
from bidi.algorithm import get_display
from reportlab.lib.colors import HexColor
from reportlab.lib.pagesizes import A4
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont
from reportlab.pdfgen import canvas as pdfcanvas

BASE_DIR = Path(__file__).resolve().parent
FONT_DIR = BASE_DIR / "assets" / "fonts"
FONT_REGULAR = "NotoNaskhArabic"
FONT_BOLD = "NotoNaskhArabic-Bold"

ACCENT = HexColor("#1F6F5C")
DARK = HexColor("#1A1A1A")
GRAY = HexColor("#666666")
LIGHT = HexColor("#CFCFCF")

_fonts_ready = False


def _ensure_fonts():
    global _fonts_ready
    if _fonts_ready:
        return
    pdfmetrics.registerFont(
        TTFont(FONT_REGULAR, str(FONT_DIR / "NotoNaskhArabic-Regular.ttf"))
    )
    pdfmetrics.registerFont(
        TTFont(FONT_BOLD, str(FONT_DIR / "NotoNaskhArabic-Bold.ttf"))
    )
    _fonts_ready = True


def _ar(text):
    return get_display(reshape(str(text)))


def _wrap(text, font_name, font_size, max_width):
    lines = []
    for para in str(text).split("\n"):
        para = para.strip()
        if not para:
            lines.append("")
            continue
        current = ""
        for word in para.split():
            candidate = (current + " " + word).strip()
            if pdfmetrics.stringWidth(_ar(candidate), font_name, font_size) <= max_width:
                current = candidate
            else:
                if current:
                    lines.append(current)
                current = word
        if current:
            lines.append(current)
    return lines


def build_cv_pdf(data, out_path):
    _ensure_fonts()
    out_path = Path(out_path)
    out_path.parent.mkdir(parents=True, exist_ok=True)

    canvas = pdfcanvas.Canvas(str(out_path), pagesize=A4)
    width, height = A4
    margin = 46
    right = width - margin
    max_width = width - 2 * margin
    y = height - 56

    def new_page():
        nonlocal y
        _draw_footer(canvas, width, height, margin)
        canvas.showPage()
        y = height - 56

    def draw_line(text, font, size, color=DARK, leading=None):
        nonlocal y
        if y < 72:
            new_page()
        canvas.setFont(font, size)
        canvas.setFillColor(color)
        canvas.drawRightString(right, y, _ar(text))
        y -= leading or (size + 6)

    name = (data.get("full_name") or "").strip() or "سيفي"
    draw_line(name, FONT_BOLD, 24, DARK, 34)

    contact_parts = [
        (data.get("phone") or "").strip(),
        (data.get("email") or "").strip(),
        (data.get("city") or "").strip(),
    ]
    contact = "  •  ".join(part for part in contact_parts if part)
    if contact:
        draw_line(contact, FONT_REGULAR, 11, GRAY, 20)

    canvas.setStrokeColor(ACCENT)
    canvas.setLineWidth(2)
    canvas.line(margin, y + 6, right, y + 6)
    y -= 16

    sections = [
        ("الدراسة", data.get("education", "")),
        ("الخبرة بالشغل", data.get("work_experience", "")),
        ("المهارات", data.get("skills", "")),
        ("اللغات", data.get("languages", "")),
        ("نبذة عنك", data.get("summary", "")),
    ]

    for title, body in sections:
        body = (body or "").strip()
        if not body:
            continue
        if title == "المهارات":
            body = re.sub(r"[،,;؛]+", " • ", body)
        if y < 120:
            new_page()
        draw_line(title, FONT_BOLD, 14, ACCENT, 8)
        canvas.setStrokeColor(LIGHT)
        canvas.setLineWidth(1)
        canvas.line(margin, y + 4, right, y + 4)
        y -= 14
        for line in _wrap(body, FONT_REGULAR, 11, max_width):
            if line:
                draw_line(line, FONT_REGULAR, 11, DARK, 17)
            else:
                y -= 8
        y -= 8

    _draw_footer(canvas, width, height, margin)
    canvas.save()
    return out_path


def _draw_footer(canvas, width, height, margin):
    canvas.setFont(FONT_REGULAR, 8)
    canvas.setFillColor(GRAY)
    footer = _ar("سيفي — " + datetime.now().strftime("%Y-%m-%d"))
    canvas.drawCentredString(width / 2, 24, footer)
