"""
Bulk certificate generation from an Excel sheet - one row per certificate.

Required columns (case-insensitive, extra spaces trimmed):
    Template, Participant Name, Training Topic, Date, Certificate Number

Address is optional - the column can be omitted entirely (e.g. for an
all-NeuLearn-Masterclass sheet) and is only enforced per-row for templates
whose design actually prints an address.

Template must match a template's display name or key (config/templates.json).
Training Topic must match a key in config/topics.json for templates with a
course-highlights section - course highlights are looked up automatically,
same as the single-certificate form. Templates without one (e.g. NeuLearn
Masterclass) treat this column as a free-text course name instead.
"""

import io
import re
import zipfile
from datetime import datetime

import pandas as pd

from utils.pdf_engine import generate_certificate, load_template_config, load_topics
from utils.text_utils import format_date_ordinal

REQUIRED_COLUMNS = ["Template", "Participant Name", "Training Topic", "Date", "Certificate Number"]


def _normalize_template_key(value, templates):
    value = str(value).strip().lower()
    for key, cfg in templates.items():
        if value == key.lower() or value == cfg["display_name"].lower():
            return key
    return None


def _normalize_topic(value, topics):
    value = str(value).strip().lower()
    for topic in topics:
        if value == topic.lower():
            return topic
    return None


def _parse_date(value):
    if isinstance(value, datetime):
        return value.date()
    parsed = pd.to_datetime(value, errors="coerce")
    if pd.isna(parsed):
        return None
    return parsed.date()


def sample_template_bytes() -> bytes:
    """A ready-to-fill Excel sheet with the right headers and one example row
    per configured template - including any template-specific extra columns
    (e.g. a second trainer's name), left blank on rows that don't need them."""
    templates = load_template_config()
    rows = [
        {
            "Template": "EU MDR Certificate",
            "Participant Name": "Jane Doe",
            "Training Topic": "EU MDR Technical Documentation",
            "Date": "2026-04-20",
            "Address": "Vadodara, Gujarat",
            "Certificate Number": "NJ_KD_EUMDR_31",
        },
        {
            "Template": "CPD ISO 13485 Certificate",
            "Participant Name": "John Smith",
            "Training Topic": "ISO 13485 Internal Auditor Training",
            "Date": "2026-04-21",
            "Address": "Online Training",
            "Certificate Number": "NJ_ML_CPDIA_334",
        },
        {
            "Template": "IVDR Certificate",
            "Participant Name": "Mr. Sample Trainee",
            "Training Topic": "In-Vitro Diagnostic Regulations",
            "Date": "2026-04-22",
            "Address": "Sample Company Pvt. Ltd, Surat, Gujarat, INDIA.",
            "Certificate Number": "NJ_AH_IVDR_135",
            "Second Trainer Name": "DR. ANITA JOSHI",
        },
        {
            "Template": "NeuLearn Masterclass Certificate",
            "Participant Name": "Priya Sharma",
            "Training Topic": "AI in Regulatory Affairs",
            "Date": "2026-04-23",
            "Address": "",
            "Certificate Number": "NL_I_MSAMD_466",
        },
    ]

    extra_columns = []
    for cfg in templates.values():
        for extra_cfg in cfg.get("extra_fields", {}).values():
            label = extra_cfg.get("label", "")
            if label and label not in extra_columns:
                extra_columns.append(label)

    for row in rows:
        for col in extra_columns:
            row.setdefault(col, "")

    df = pd.DataFrame(rows)
    buffer = io.BytesIO()
    df.to_excel(buffer, index=False)
    return buffer.getvalue()


def generate_bulk(file_bytes: bytes):
    """
    Generate one certificate per row of the uploaded Excel file.

    Returns (zip_bytes, results) where results is a list of dicts:
        {"row": <sheet row number>, "name": ..., "status": "ok"/"error", "detail": ...}
    A row's failure never blocks the rest - it's just recorded and skipped.
    """
    df = pd.read_excel(io.BytesIO(file_bytes))
    df.columns = [str(c).strip() for c in df.columns]

    missing = [c for c in REQUIRED_COLUMNS if c not in df.columns]
    if missing:
        raise ValueError(f"Missing required column(s): {', '.join(missing)}")

    templates = load_template_config()
    topics = load_topics()

    results = []
    used_filenames = set()
    zip_buffer = io.BytesIO()

    with zipfile.ZipFile(zip_buffer, "w", zipfile.ZIP_DEFLATED) as zf:
        for idx, row in df.iterrows():
            row_num = idx + 2  # +2: header row + 1-indexing
            name = str(row.get("Participant Name", "")).strip()
            try:
                template_key = _normalize_template_key(row["Template"], templates)
                if not template_key:
                    raise ValueError(f"Unknown template '{row['Template']}'")

                needs_highlights = "course_highlights" in templates[template_key]["fields"]
                if needs_highlights:
                    topic = _normalize_topic(row["Training Topic"], topics)
                    if not topic:
                        raise ValueError(f"Unknown training topic '{row['Training Topic']}'")
                    course_highlights = topics[topic]
                else:
                    topic = str(row["Training Topic"]).strip()
                    if not topic:
                        raise ValueError("Training Topic is required")
                    course_highlights = []

                date_val = _parse_date(row["Date"])
                if date_val is None:
                    raise ValueError(f"Could not read date '{row['Date']}'")

                cert_number = str(row["Certificate Number"]).strip()
                address_raw = row.get("Address", "")
                address = "" if pd.isna(address_raw) else str(address_raw).strip()
                needs_address = "address" in templates[template_key]["fields"]

                if not name or not cert_number or (needs_address and not address):
                    raise ValueError("Participant Name and Certificate Number are required" + (", and Address" if needs_address else ""))

                extra_values = {}
                for key, extra_cfg in templates[template_key].get("extra_fields", {}).items():
                    label = extra_cfg.get("label", key)
                    if label in df.columns and str(row[label]).strip().lower() != "nan":
                        extra_values[key] = str(row[label]).strip()

                pdf_bytes = generate_certificate(
                    template_key=template_key,
                    participant_name=name,
                    training_topic=topic,
                    course_highlights=course_highlights,
                    date_text=format_date_ordinal(date_val),
                    address=address,
                    certificate_number=cert_number,
                    extra_values=extra_values,
                )

                filename = re.sub(r'[\\/:*?"<>|]', "", name).strip() + ".pdf"
                base = filename
                n = 1
                while filename in used_filenames:
                    n += 1
                    filename = f"{base[:-4]}_{n}.pdf"
                used_filenames.add(filename)

                zf.writestr(filename, pdf_bytes)
                results.append({"row": row_num, "name": name, "status": "ok", "detail": filename})

            except Exception as e:
                results.append({"row": row_num, "name": name or "(blank)", "status": "error", "detail": str(e)})

    return zip_buffer.getvalue(), results
