"""
Core certificate generation engine.

Opens the fixed template PDF (untouched background: logo, borders, signature,
footer) and overlays only the variable fields on top, using coordinates from
config/templates.json - calibrated from real, previously-issued certificates
so text lands exactly where the design expects it. Nothing in the original
design is redrawn or altered except small footer/label rectangles that are
whited out immediately before the replacement text is written (certificate
number, and the EU MDR "DATE:" line).
"""

import json
import os
import fitz  # PyMuPDF

from utils.text_utils import fit_fontsize, wrap_text

BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
CONFIG_PATH = os.path.join(BASE_DIR, "config", "templates.json")
TOPICS_PATH = os.path.join(BASE_DIR, "config", "topics.json")


def load_template_config() -> dict:
    with open(CONFIG_PATH, "r", encoding="utf-8") as f:
        return json.load(f)


def load_topics() -> dict:
    with open(TOPICS_PATH, "r", encoding="utf-8") as f:
        return json.load(f)


def _draw_spaced_line(page, text, x, y, fontname, fontsize, color, align, spacing, rotate, rotate_offset):
    """Insert text one character at a time with extra tracking between
    glyphs - used to match the NeuLearn template's letter-spaced footer
    style, which a single insert_text call can't reproduce."""
    font = fitz.Font(fontname)
    total_width = font.text_length(text, fontsize=fontsize) + spacing * (len(text) - 1)
    cursor_x = x - total_width / 2 if align == "center" else x
    for ch in text:
        page.insert_text((cursor_x + rotate_offset, y), ch, fontsize=fontsize, fontname=fontname, color=color, rotate=rotate)
        cursor_x += font.text_length(ch, fontsize=fontsize) + spacing


def _draw_text_block(page, field_cfg: dict, text: str):
    """Draw a field with one of three behaviors, chosen per-field in config:
      - wrap: true         -> word-wrap across multiple lines (generous space)
      - shrink: true       -> single line, font shrinks to fit max_width
                              (used where the template only has a narrow gap
                              between two fixed labels and a second line
                              would collide with them)
      - neither            -> single line at fixed font size
    Fields with center_vertically use a y_center so a 1-line result sits in
    the middle of the same slot a 2-line result would occupy.
    letter_spacing (points) adds extra tracking between characters, for
    templates whose design uses a letter-spaced style (e.g. NeuLearn's
    footer line).
    """
    fontname = field_cfg.get("font", "helv")
    fontsize = field_cfg.get("fontsize", 14)
    color = tuple(field_cfg.get("color", [0, 0, 0]))
    max_width = field_cfg.get("max_width", 350)
    align = field_cfg.get("align", "left")
    line_spacing = field_cfg.get("line_spacing", fontsize * 1.3)
    letter_spacing = field_cfg.get("letter_spacing", 0)
    x = field_cfg["x"]

    if field_cfg.get("wrap"):
        lines = wrap_text(text, fontname, fontsize, max_width)
    elif field_cfg.get("shrink"):
        fontsize = fit_fontsize(text, fontname, max_width, fontsize, min_size=field_cfg.get("min_fontsize", 8.0), letter_spacing=letter_spacing)
        lines = [text]
    else:
        lines = [text]

    if field_cfg.get("center_vertically"):
        y_center = field_cfg["y_center"]
        y_start = y_center - (len(lines) - 1) * line_spacing / 2
    else:
        y_start = field_cfg["y"]

    rotate = field_cfg.get("rotate", 0)
    font = fitz.Font(fontname)
    # For rotated text, PyMuPDF anchors the insertion point using the font's
    # descender, which scales with fontsize - so a field that shrinks its
    # font (long certificate numbers, etc.) would otherwise drift sideways
    # out of its column. Compensate so "x" always means the same visual
    # edge regardless of the fontsize actually used.
    rotate_offset = abs(font.descender) * fontsize if rotate else 0
    for i, line in enumerate(lines):
        y = y_start + i * line_spacing
        if letter_spacing:
            _draw_spaced_line(page, line, x, y, fontname, fontsize, color, align, letter_spacing, rotate, rotate_offset)
        else:
            line_x = x - font.text_length(line, fontsize=fontsize) / 2 if align == "center" else x
            page.insert_text((line_x + rotate_offset, y), line, fontsize=fontsize, fontname=fontname, color=color, rotate=rotate)


def _draw_highlights(page, field_cfg: dict, highlights: list):
    x, y = field_cfg["x"], field_cfg["y"]
    fontname = field_cfg.get("font", "helv")
    fontsize = field_cfg.get("fontsize", 11)
    color = tuple(field_cfg.get("color", [0, 0, 0]))
    max_width = field_cfg.get("max_width", 380)
    line_spacing = field_cfg.get("line_spacing", 16)
    bullet = field_cfg.get("bullet", "")
    align = field_cfg.get("align", "left")

    font = fitz.Font(fontname)
    bullet_width = font.text_length(bullet, fontsize=fontsize) if bullet else 0

    cursor_y = y
    for item in highlights:
        wrapped = wrap_text(item, fontname, fontsize, max_width - bullet_width)
        for i, line in enumerate(wrapped):
            prefix = bullet if i == 0 else " " * len(bullet)
            full_line = prefix + line
            line_x = x - font.text_length(full_line, fontsize=fontsize) / 2 if align == "center" else x
            page.insert_text((line_x, cursor_y), full_line, fontsize=fontsize, fontname=fontname, color=color)
            cursor_y += line_spacing


def render_certificate_overlay(
    pdf_bytes: bytes,
    fields: dict,
    participant_name: str,
    training_topic: str,
    course_highlights: list,
    date_text: str,
    address: str,
    certificate_number: str,
    extra_fields: dict = None,
    extra_values: dict = None,
    static_overrides: list = None,
) -> bytes:
    """Overlay the variable fields onto a template's raw PDF bytes and return
    the result's bytes. This is the shared drawing core behind both
    generate_certificate() (which looks a template up by key in
    config/templates.json) and the Add New Template wizard's live preview
    (which draws directly onto a not-yet-saved upload using in-progress field
    positions, before anything is written to disk)."""
    extra_fields = extra_fields or {}
    extra_values = extra_values or {}
    static_overrides = static_overrides or []

    doc = fitz.open(stream=pdf_bytes, filetype="pdf")
    page = doc[0]

    # Remove old fixed text (e.g. a mispositioned "OF ACHIEVEMENT", the
    # baked-in footer certificate number) using PDF redaction rather than
    # painting a solid rectangle over it. Redaction deletes just the text
    # objects in that rect and leaves everything else - including background
    # images/watermarks - completely untouched, so the new text drawn on top
    # sits on the real background instead of a flat color patch.
    redact_rects = [f["redact_rect"] for f in fields.values() if f.get("redact_rect")]
    redact_rects += [o["redact_rect"] for o in static_overrides if o.get("redact_rect")]
    redact_rects += [f["redact_rect"] for f in extra_fields.values() if f.get("redact_rect")]
    for rect in redact_rects:
        page.add_redact_annot(fitz.Rect(*rect), fill=None)
    if redact_rects:
        page.apply_redactions(images=fitz.PDF_REDACT_IMAGE_NONE)

    for override in static_overrides:
        _draw_text_block(page, override, override["text"])

    _draw_text_block(page, fields["participant_name"], participant_name)
    _draw_text_block(page, fields["training_topic"], training_topic)
    if "course_highlights" in fields:
        _draw_highlights(page, fields["course_highlights"], course_highlights)

    date_field = fields["date"]
    _draw_text_block(page, date_field, date_field.get("date_prefix", "") + date_text)

    if "address" in fields:
        _draw_text_block(page, fields["address"], address)
    _draw_text_block(page, fields["certificate_number"], certificate_number)

    for key, extra_cfg in extra_fields.items():
        value = extra_values.get(key, extra_cfg.get("default", ""))
        if value:
            _draw_text_block(page, extra_cfg, value)

    result_bytes = doc.tobytes()
    doc.close()
    return result_bytes


def generate_certificate(
    template_key: str,
    participant_name: str,
    training_topic: str,
    course_highlights: list,
    date_text: str,
    address: str,
    certificate_number: str,
    extra_values: dict = None,
) -> bytes:
    """Build the final certificate PDF and return its bytes."""
    config = load_template_config()[template_key]
    template_path = os.path.join(BASE_DIR, config["file"])

    if not os.path.exists(template_path):
        raise FileNotFoundError(
            f"Template file not found: {template_path}\n"
            "Place the original certificate PDF in the templates/ folder with this exact name."
        )

    with open(template_path, "rb") as f:
        pdf_bytes = f.read()

    return render_certificate_overlay(
        pdf_bytes=pdf_bytes,
        fields=config["fields"],
        participant_name=participant_name,
        training_topic=training_topic,
        course_highlights=course_highlights,
        date_text=date_text,
        address=address,
        certificate_number=certificate_number,
        extra_fields=config.get("extra_fields", {}),
        extra_values=extra_values,
        static_overrides=config.get("static_overrides", []),
    )


def render_preview_png(pdf_bytes: bytes, zoom: float = 1.5) -> bytes:
    """Rasterize the first page of a generated PDF for on-screen preview / PNG export."""
    doc = fitz.open(stream=pdf_bytes, filetype="pdf")
    page = doc[0]
    pix = page.get_pixmap(matrix=fitz.Matrix(zoom, zoom))
    png_bytes = pix.tobytes("png")
    doc.close()
    return png_bytes
