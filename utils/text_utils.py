"""Small text helpers: ordinal date formatting and word-wrap for the PDF overlay."""

import re

import fitz  # PyMuPDF


def slugify(text: str) -> str:
    """'My New Certificate!' -> 'my_new_certificate' (used as a template's internal key)."""
    slug = re.sub(r"[^a-z0-9]+", "_", text.strip().lower()).strip("_")
    return slug or "template"


def ordinal_suffix(day: int) -> str:
    if 11 <= day % 100 <= 13:
        return "th"
    return {1: "st", 2: "nd", 3: "rd"}.get(day % 10, "th")


def format_date_ordinal(date_obj) -> str:
    """date(2026, 4, 20) -> '20th April 2026'"""
    day = date_obj.day
    return f"{day}{ordinal_suffix(day)} {date_obj.strftime('%B')} {date_obj.year}"


def fit_fontsize(text: str, fontname: str, max_width: float, start_size: float, min_size: float = 8.0, letter_spacing: float = 0.0) -> float:
    """Shrink fontsize until the text (plus any extra letter-spacing) fits max_width, down to a floor."""
    size = start_size
    font = fitz.Font(fontname)
    while size > min_size and font.text_length(text, fontsize=size) + letter_spacing * (len(text) - 1) > max_width:
        size -= 0.5
    return size


def wrap_text(text: str, fontname: str, fontsize: float, max_width: float) -> list:
    """Greedy word-wrap so a line of text never exceeds max_width."""
    font = fitz.Font(fontname)
    words = text.split()
    lines, current = [], ""
    for word in words:
        candidate = f"{current} {word}".strip()
        if font.text_length(candidate, fontsize=fontsize) <= max_width or not current:
            current = candidate
        else:
            lines.append(current)
            current = word
    if current:
        lines.append(current)
    return lines
