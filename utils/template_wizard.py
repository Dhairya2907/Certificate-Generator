"""
Best-effort automatic field-position detection for a newly uploaded
certificate template - lets a non-developer add a template through the
Streamlit UI (the "Add New Template" tab) without hand-editing
config/templates.json or measuring PDF coordinates.

Works by searching the blank template for common label text ("Name",
"Course Name", "Date", "Certificate No.", ...) and building a field config
around wherever it's found - the same manual process used to calibrate the
existing templates, automated. Two placement styles are used depending on
the field:

  - participant_name / training_topic: the matched label text IS the value
    slot (e.g. a bold "Name" placeholder) - it gets redacted and the real
    value is drawn in its place, with a lot of room to its right.
  - date / address / certificate_number: the matched text is a fixed label
    that stays printed (e.g. "DATE:") - the value is drawn right after it,
    redacting only the space to its right in case a placeholder value is
    already printed there.

Anything not found on the page falls back to a rough stacked default
position, flagged in the returned warnings list - Calibration Mode (already
in the app) is how those get nudged into place by eye afterwards.
"""

import fitz

_LABEL_CANDIDATES = {
    "participant_name": ["Participant Name", "Attendee Name", "Recipient Name", "Full Name", "Name"],
    "training_topic": ["Course Name", "Training Topic", "Course Title", "Topic"],
    "date": ["Date of Issue", "Issue Date", "Date:", "Date"],
    "address": ["Address", "Venue", "Location"],
    "certificate_number": ["Certificate No.", "Certificate No", "Certificate Number", "Cert. No.", "Cert No"],
}

# Fields whose matched label text IS the value slot (redrawn in place) vs.
# fields whose label stays printed and the value is appended after it.
_IN_PLACE_FIELDS = {"participant_name", "training_topic"}

_RIGHT_MARGIN = 40  # stay clear of the page edge / corner graphics


def _find_label_rect(page, field_key):
    for phrase in _LABEL_CANDIDATES[field_key]:
        for variant in (phrase, phrase.upper(), phrase.title(), phrase.lower()):
            rects = page.search_for(variant)
            if rects:
                return rects[0]
    return None


def _in_place_field(rect, page_width):
    pad = 2
    max_width = max(page_width - rect.x0 - _RIGHT_MARGIN, 80)
    return {
        "redact_rect": [round(rect.x0 - pad, 1), round(rect.y0 - pad, 1), round(rect.x1 + pad, 1), round(rect.y1 + pad, 1)],
        "x": round(rect.x0, 1), "y": round(rect.y1 - (rect.y1 - rect.y0) * 0.18, 1),
        "shrink": True, "min_fontsize": 10, "fontsize": 18, "font": "hebo",
        "color": [0.05, 0.05, 0.05], "align": "left", "max_width": round(max_width, 1),
    }


def _appended_field(rect, page_width):
    gap = 4
    max_width = max(page_width - rect.x1 - gap - _RIGHT_MARGIN, 60)
    return {
        "redact_rect": [round(rect.x1, 1), round(rect.y0 - 2, 1), round(page_width - _RIGHT_MARGIN, 1), round(rect.y1 + 2, 1)],
        "x": round(rect.x1 + gap, 1), "y": round(rect.y1 - (rect.y1 - rect.y0) * 0.18, 1),
        "shrink": True, "min_fontsize": 8, "fontsize": 13, "font": "hebo",
        "color": [0.05, 0.05, 0.05], "align": "left", "max_width": round(max_width, 1),
    }


def _fallback_field(index, page_width, page_height):
    """Rough stacked default when no matching label text was found - always
    a valid, non-crashing position, just needs calibrating by hand."""
    y = page_height * (0.35 + index * 0.1)
    return {
        "x": round(page_width * 0.1, 1), "y": round(y, 1),
        "shrink": True, "min_fontsize": 8, "fontsize": 16, "font": "hebo",
        "color": [0.05, 0.05, 0.05], "align": "left", "max_width": round(page_width * 0.8, 1),
    }


def build_template_config(pdf_bytes: bytes, include_address: bool, include_highlights: bool):
    """Returns (fields_dict, page_size, warnings) for a newly uploaded blank
    template PDF. `warnings` lists the field keys that couldn't be
    auto-positioned and got a fallback instead."""
    doc = fitz.open(stream=pdf_bytes, filetype="pdf")
    page = doc[0]
    page_width, page_height = page.rect.width, page.rect.height

    wanted = ["participant_name", "training_topic", "date"]
    if include_address:
        wanted.append("address")
    wanted.append("certificate_number")

    fields = {}
    warnings = []
    fallback_index = 0
    for key in wanted:
        rect = _find_label_rect(page, key)
        if rect is None:
            fields[key] = _fallback_field(fallback_index, page_width, page_height)
            fallback_index += 1
            warnings.append(key)
        else:
            fields[key] = _in_place_field(rect, page_width) if key in _IN_PLACE_FIELDS else _appended_field(rect, page_width)

    if include_highlights:
        fields["course_highlights"] = {
            "x": round(page_width * 0.15, 1), "y": round(page_height * 0.62, 1),
            "fontsize": 12, "font": "helv", "color": [0.1, 0.1, 0.1],
            "align": "left", "max_width": round(page_width * 0.7, 1),
            "line_spacing": 16, "bullet": "•  ",
        }
        warnings.append("course_highlights")

    doc.close()
    page_size = [round(page_width, 2), round(page_height, 2)]
    return fields, page_size, warnings
