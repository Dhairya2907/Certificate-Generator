"""
Neujin Solutions - Internal Certificate Generator

Generates training certificates as PDFs by overlaying variable fields
(name, topic, highlights, date, address, certificate number) on top of
the fixed certificate template PDFs. The original design is never altered.

Run with:  streamlit run app.py
"""

import json
import os
from datetime import date

import streamlit as st

from utils.bulk_generator import generate_bulk, sample_template_bytes
from utils.pdf_engine import (
    BASE_DIR,
    CONFIG_PATH,
    TOPICS_PATH,
    generate_certificate,
    load_template_config,
    load_topics,
    render_certificate_overlay,
    render_preview_png,
)
from utils.template_wizard import build_template_config
from utils.text_utils import format_date_ordinal, slugify

st.set_page_config(page_title="Neujin Certificate Generator", page_icon="📜", layout="centered")

st.title("📜 Neujin Solutions - Certificate Generator")

templates = load_template_config()
topics = load_topics()
template_options = {cfg["display_name"]: key for key, cfg in templates.items()}

single_tab, bulk_tab, topics_tab, new_template_tab = st.tabs(
    ["Single Certificate", "Bulk Generate (Excel)", "Manage Training Topics", "Add New Template"]
)

# ---------------------------------------------------------------------------
# Single certificate form
# ---------------------------------------------------------------------------

with single_tab:
    st.caption("Fill in the fields below and generate a training certificate as a PDF.")

    template_display = st.selectbox("Certificate Template", list(template_options.keys()))
    template_key = template_options[template_display]

    col1, col2 = st.columns(2)
    with col1:
        participant_name = st.text_input("Participant Name", placeholder="e.g. Jane Doe")
    with col2:
        certificate_number = st.text_input("Certificate Number", placeholder="e.g. NJ_KD_EUMDR_31")

    template_fields = templates[template_key]["fields"]
    has_highlights = "course_highlights" in template_fields
    has_address = "address" in template_fields

    if has_highlights:
        topic_choice = st.selectbox("Training Topic", list(topics.keys()))
        highlights = topics[topic_choice]
        st.markdown("**Course Highlights (auto-filled):**")
        st.markdown("\n".join(f"- {h}" for h in highlights))
    else:
        topic_choice = st.text_input("Course Name", placeholder="e.g. AI in Regulatory Affairs")
        highlights = []

    if has_address:
        col3, col4 = st.columns(2)
        with col3:
            training_date = st.date_input("Training / Issue Date", value=date.today())
        with col4:
            address = st.text_input("Training Address / Place", placeholder="e.g. Vadodara, Gujarat")
    else:
        training_date = st.date_input("Training / Issue Date", value=date.today())
        address = ""

    # Template-specific fields beyond the standard set (e.g. a second
    # trainer's name on the IVDR template) - defined per-template in
    # config/templates.json under "extra_fields", so nothing here needs to
    # change when a new template adds its own.
    extra_field_defs = templates[template_key].get("extra_fields", {})
    extra_values = {}
    for key, extra_cfg in extra_field_defs.items():
        extra_values[key] = st.text_input(
            extra_cfg.get("label", key),
            value=extra_cfg.get("default", ""),
            placeholder=extra_cfg.get("placeholder", ""),
        )

    st.divider()

    generate_clicked = st.button("Generate Certificate", type="primary", use_container_width=True)

    if generate_clicked:
        missing = []
        if not participant_name.strip():
            missing.append("Participant Name")
        if not certificate_number.strip():
            missing.append("Certificate Number")
        if has_address and not address.strip():
            missing.append("Training Address / Place")
        if not has_highlights and not topic_choice.strip():
            missing.append("Course Name")

        if missing:
            st.error(f"Please fill in: {', '.join(missing)}")
        else:
            try:
                date_text = format_date_ordinal(training_date)
                pdf_bytes = generate_certificate(
                    template_key=template_key,
                    participant_name=participant_name.strip(),
                    training_topic=topic_choice.strip(),
                    course_highlights=highlights,
                    date_text=date_text,
                    address=address.strip(),
                    certificate_number=certificate_number.strip(),
                    extra_values=extra_values,
                )
                st.session_state["last_pdf"] = pdf_bytes
                st.session_state["last_filename"] = f"{certificate_number.strip()}.pdf"
                st.success("Certificate generated.")
            except FileNotFoundError as e:
                st.error(str(e))

    if "last_pdf" in st.session_state:
        st.subheader("Preview")
        png_bytes = render_preview_png(st.session_state["last_pdf"])
        st.image(png_bytes, use_container_width=True)

        dl_col1, dl_col2 = st.columns(2)
        with dl_col1:
            st.download_button(
                "Download PDF",
                data=st.session_state["last_pdf"],
                file_name=st.session_state["last_filename"],
                mime="application/pdf",
                use_container_width=True,
            )
        with dl_col2:
            st.download_button(
                "Download PNG",
                data=png_bytes,
                file_name=st.session_state["last_filename"].replace(".pdf", ".png"),
                mime="image/png",
                use_container_width=True,
            )

# ---------------------------------------------------------------------------
# Bulk generation from an Excel sheet - one row per certificate
# ---------------------------------------------------------------------------

with bulk_tab:
    st.caption(
        "Upload an Excel sheet with one row per certificate. Each row needs: "
        "Template, Participant Name, Training Topic, Date, Address, Certificate Number."
    )
    st.caption(
        "Template must match a template name below, and Training Topic must match one of the "
        "configured topics exactly (see the Single Certificate tab for the current lists)."
    )

    st.download_button(
        "Download sample Excel template",
        data=sample_template_bytes(),
        file_name="certificate_bulk_template.xlsx",
        mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
    )

    st.divider()

    uploaded_file = st.file_uploader("Upload filled Excel sheet (.xlsx)", type=["xlsx"])

    if uploaded_file is not None and st.button("Generate All Certificates", type="primary"):
        try:
            zip_bytes, results = generate_bulk(uploaded_file.read())
            success_count = sum(1 for r in results if r["status"] == "ok")
            error_count = len(results) - success_count

            if success_count:
                st.success(f"Generated {success_count} certificate(s).")
            if error_count:
                st.warning(f"{error_count} row(s) had errors - see the table below.")

            st.dataframe(results, use_container_width=True)

            if success_count:
                st.download_button(
                    "Download ZIP of certificates",
                    data=zip_bytes,
                    file_name="certificates.zip",
                    mime="application/zip",
                )
        except ValueError as e:
            st.error(str(e))

# ---------------------------------------------------------------------------
# Manage training topics - add, edit, or remove a topic and its course
# highlights, saved straight to config/topics.json. No file editing needed.
# ---------------------------------------------------------------------------

with topics_tab:
    st.caption(
        "Add a new training topic with its course highlights, or edit/remove an "
        "existing one. Changes save directly to config/topics.json and appear "
        "immediately in the Training Topic dropdown."
    )

    action = st.radio("Action", ["Add a new topic", "Edit or delete an existing topic"], horizontal=True)

    if action == "Add a new topic":
        new_name = st.text_input("Topic name", key="new_topic_name", placeholder="e.g. MDSAP Internal Auditor Training")
        new_highlights = st.text_area(
            "Course highlights (one per line)",
            key="new_topic_highlights",
            height=150,
            placeholder="First highlight\nSecond highlight\nThird highlight",
        )

        if st.button("Save new topic", type="primary"):
            name = new_name.strip()
            highlight_lines = [line.strip() for line in new_highlights.split("\n") if line.strip()]

            if not name:
                st.error("Please enter a topic name.")
            elif not highlight_lines:
                st.error("Please enter at least one course highlight.")
            elif name in topics:
                st.error(f"'{name}' already exists - use 'Edit or delete an existing topic' instead.")
            else:
                topics[name] = highlight_lines
                with open(TOPICS_PATH, "w", encoding="utf-8") as f:
                    json.dump(topics, f, indent=2)
                st.success(f"Added '{name}' with {len(highlight_lines)} highlight(s).")
                st.rerun()

    else:
        if not topics:
            st.info("No topics configured yet.")
        else:
            topic_to_edit = st.selectbox("Choose a topic", list(topics.keys()), key="topic_to_edit")
            edited_name = st.text_input("Topic name", value=topic_to_edit, key="edit_topic_name")
            edited_highlights = st.text_area(
                "Course highlights (one per line)",
                value="\n".join(topics[topic_to_edit]),
                key="edit_topic_highlights",
                height=150,
            )

            save_col, delete_col = st.columns(2)
            with save_col:
                if st.button("Save changes", type="primary", use_container_width=True):
                    name = edited_name.strip()
                    highlight_lines = [line.strip() for line in edited_highlights.split("\n") if line.strip()]

                    if not name:
                        st.error("Please enter a topic name.")
                    elif not highlight_lines:
                        st.error("Please enter at least one course highlight.")
                    elif name != topic_to_edit and name in topics:
                        st.error(f"'{name}' already exists.")
                    else:
                        if name != topic_to_edit:
                            del topics[topic_to_edit]
                        topics[name] = highlight_lines
                        with open(TOPICS_PATH, "w", encoding="utf-8") as f:
                            json.dump(topics, f, indent=2)
                        st.success(f"Saved '{name}'.")
                        st.rerun()
            with delete_col:
                if st.button("Delete this topic", use_container_width=True):
                    del topics[topic_to_edit]
                    with open(TOPICS_PATH, "w", encoding="utf-8") as f:
                        json.dump(topics, f, indent=2)
                    st.success(f"Deleted '{topic_to_edit}'.")
                    st.rerun()

# ---------------------------------------------------------------------------
# Add New Template - lets anyone add a brand-new certificate design by
# uploading the blank PDF, with no file editing or coordinate-hunting.
# Field positions are auto-detected by searching the PDF for common label
# text ("Name", "Course Name", "Date", "Certificate No.", ...); every field's
# position is then shown as an editable x/y/font size/width right here, with
# a live preview, so it can be adjusted and confirmed before anything is
# saved - not just fixed up afterwards in a separate Calibration Mode step.
# ---------------------------------------------------------------------------

_SAMPLE_VALUES = {
    "participant_name": "Sample Name",
    "training_topic": "Sample Course Title",
    "date": "20th April 2026",
    "address": "Sample Address, City",
    "certificate_number": "SAMPLE-001",
}
_SAMPLE_HIGHLIGHTS = ["Sample highlight one", "Sample highlight two"]

with new_template_tab:
    st.subheader("Add a new template")
    st.caption(
        "Upload the blank certificate PDF, adjust any field position that needs it "
        "using the live preview, then save - it becomes immediately usable above "
        "and in Bulk Generate."
    )

    new_pdf = st.file_uploader("Blank certificate PDF", type=["pdf"], key="new_template_pdf")
    new_display_name = st.text_input("Template name", key="new_template_name", placeholder="e.g. Advanced Diploma Certificate")

    col_a, col_b = st.columns(2)
    with col_a:
        new_has_address = st.checkbox("Design prints an address / venue line", key="new_template_has_address")
    with col_b:
        new_has_highlights = st.checkbox("Design has a course-highlights bullet list", key="new_template_has_highlights")

    if new_pdf is not None:
        pdf_bytes = new_pdf.getvalue()
        detect_key = (new_pdf.name, len(pdf_bytes), new_has_address, new_has_highlights)
        if st.session_state.get("wizard_detect_key") != detect_key:
            try:
                fields, page_size, warnings = build_template_config(pdf_bytes, new_has_address, new_has_highlights)
                # Drop any leftover per-field widget state from a previous upload so
                # the number inputs below start from this file's fresh detection.
                for k in list(st.session_state.keys()):
                    if k.startswith("wizard_pos_"):
                        del st.session_state[k]
                st.session_state["wizard_fields"] = fields
                st.session_state["wizard_page_size"] = page_size
                st.session_state["wizard_warnings"] = warnings
                st.session_state["wizard_detect_key"] = detect_key
                st.session_state["wizard_pdf_bytes"] = pdf_bytes
                st.session_state.pop("wizard_preview_png", None)
            except Exception as e:
                st.error(f"Couldn't read that PDF: {e}")
                st.session_state.pop("wizard_fields", None)

    wizard_fields = st.session_state.get("wizard_fields")

    if wizard_fields:
        warnings = st.session_state.get("wizard_warnings", [])
        if warnings:
            st.info(
                "Couldn't auto-detect a position for: " + ", ".join(warnings) + ". "
                "They've been given a rough starting spot - pick them below, check the "
                "preview, and adjust x/y until they land correctly."
            )

        st.markdown("**Field positions**")
        wizard_field_choice = st.selectbox("Field to adjust", list(wizard_fields.keys()), key="wizard_field_choice")
        wcfg = wizard_fields[wizard_field_choice]

        wc1, wc2, wc3, wc4 = st.columns(4)
        with wc1:
            wcfg["x"] = st.number_input("x", value=float(wcfg.get("x", 50.0)), step=1.0, key=f"wizard_pos_x_{wizard_field_choice}")
        with wc2:
            wcfg["y"] = st.number_input("y", value=float(wcfg.get("y", 50.0)), step=1.0, key=f"wizard_pos_y_{wizard_field_choice}")
        with wc3:
            wcfg["fontsize"] = st.number_input("font size", value=float(wcfg.get("fontsize", 14)), step=0.5, key=f"wizard_pos_size_{wizard_field_choice}")
        with wc4:
            wcfg["max_width"] = st.number_input("max width", value=float(wcfg.get("max_width", 300)), step=10.0, key=f"wizard_pos_width_{wizard_field_choice}")

        if st.button("Preview with sample data", key="wizard_preview_btn"):
            try:
                preview_bytes = render_certificate_overlay(
                    pdf_bytes=st.session_state["wizard_pdf_bytes"],
                    fields=wizard_fields,
                    participant_name=_SAMPLE_VALUES["participant_name"],
                    training_topic=_SAMPLE_VALUES["training_topic"],
                    course_highlights=_SAMPLE_HIGHLIGHTS,
                    date_text=_SAMPLE_VALUES["date"],
                    address=_SAMPLE_VALUES["address"],
                    certificate_number=_SAMPLE_VALUES["certificate_number"],
                )
                st.session_state["wizard_preview_png"] = render_preview_png(preview_bytes)
            except Exception as e:
                st.error(f"Couldn't render preview: {e}")

        if "wizard_preview_png" in st.session_state:
            st.image(st.session_state["wizard_preview_png"], caption="Preview with sample data - adjust fields above and re-preview as needed", use_container_width=True)

        st.divider()
        st.markdown("Once every field looks right in the preview:")
        if st.button("Save Template", type="primary", key="wizard_save_btn"):
            if not new_display_name.strip():
                st.error("Please give the template a name.")
            elif any(cfg["display_name"].lower() == new_display_name.strip().lower() for cfg in templates.values()):
                st.error(f"A template named '{new_display_name.strip()}' already exists.")
            else:
                base_key = slugify(new_display_name)
                key = base_key
                n = 1
                while key in templates:
                    n += 1
                    key = f"{base_key}_{n}"

                template_rel_path = f"templates/{key}.pdf"
                with open(os.path.join(BASE_DIR, template_rel_path), "wb") as f:
                    f.write(st.session_state["wizard_pdf_bytes"])

                templates[key] = {
                    "display_name": new_display_name.strip(),
                    "file": template_rel_path,
                    "page_size": st.session_state["wizard_page_size"],
                    "date_format": "ordinal",
                    "fields": wizard_fields,
                }
                with open(CONFIG_PATH, "w", encoding="utf-8") as f:
                    json.dump(templates, f, indent=2)

                for k in list(st.session_state.keys()):
                    if k.startswith("wizard_"):
                        del st.session_state[k]

                st.success(f"Created '{new_display_name.strip()}'. Select it above to generate certificates.")
                st.rerun()

    st.divider()
    st.subheader("Rename or delete an existing template")

    if not templates:
        st.info("No templates configured yet.")
    else:
        manage_display = st.selectbox("Choose a template", list(template_options.keys()), key="manage_template_choice")
        manage_key = template_options[manage_display]

        manage_col1, manage_col2 = st.columns(2)
        with manage_col1:
            renamed = st.text_input("Name", value=manage_display, key="manage_template_rename")
            if st.button("Save name", key="manage_template_rename_btn", use_container_width=True):
                new_name = renamed.strip()
                if not new_name:
                    st.error("Please enter a name.")
                elif new_name.lower() != manage_display.lower() and any(
                    cfg["display_name"].lower() == new_name.lower() for cfg in templates.values()
                ):
                    st.error(f"A template named '{new_name}' already exists.")
                else:
                    templates[manage_key]["display_name"] = new_name
                    with open(CONFIG_PATH, "w", encoding="utf-8") as f:
                        json.dump(templates, f, indent=2)
                    st.success(f"Renamed to '{new_name}'.")
                    st.rerun()
        with manage_col2:
            st.write("")
            st.write("")
            if st.button(f"Delete '{manage_display}'", key="manage_template_delete_btn", use_container_width=True):
                del templates[manage_key]
                with open(CONFIG_PATH, "w", encoding="utf-8") as f:
                    json.dump(templates, f, indent=2)
                st.success(f"Deleted '{manage_display}' (its PDF file was left in templates/, only removed from the list).")
                st.rerun()

# ---------------------------------------------------------------------------
# Calibration mode - lets a non-developer nudge field positions/sizes and
# save them back to config/templates.json, without touching any code.
# ---------------------------------------------------------------------------

with st.sidebar:
    st.header("Admin")
    calibration_on = st.checkbox("Calibration mode")

if calibration_on:
    st.divider()
    st.subheader("🛠️ Calibration Mode")
    st.caption(
        "Adjust field position (x, y in PDF points from the top-left corner), "
        "font size, and text-box width. Use the preview to fine-tune, then save."
    )

    all_fields = {**templates[template_key]["fields"], **templates[template_key].get("extra_fields", {})}
    field_names = list(all_fields.keys())
    field_to_edit = st.selectbox("Field to adjust", field_names)
    field_cfg = all_fields[field_to_edit]

    widget_ns = f"{template_key}_{field_to_edit}"
    y_key = "y_center" if field_cfg.get("center_vertically") else "y"

    c1, c2, c3 = st.columns(3)
    with c1:
        new_x = st.number_input("x", value=float(field_cfg["x"]), step=1.0, key=f"x_{widget_ns}")
    with c2:
        new_y = st.number_input(y_key, value=float(field_cfg[y_key]), step=1.0, key=f"y_{widget_ns}")
    with c3:
        new_size = st.number_input("font size", value=float(field_cfg.get("fontsize", 12)), step=0.5, key=f"size_{widget_ns}")

    c4, c5 = st.columns(2)
    with c4:
        new_width = st.number_input("max width", value=float(field_cfg.get("max_width", 300)), step=10.0, key=f"width_{widget_ns}")
    with c5:
        has_line_spacing = "line_spacing" in field_cfg
        new_line_spacing = st.number_input(
            "line spacing", value=float(field_cfg.get("line_spacing", field_cfg.get("fontsize", 12) * 1.3)),
            step=0.5, key=f"ls_{widget_ns}", disabled=not has_line_spacing,
        )

    preview_col, save_col = st.columns([3, 1])
    with save_col:
        if st.button("Save position", use_container_width=True):
            field_cfg["x"] = new_x
            field_cfg[y_key] = new_y
            field_cfg["fontsize"] = new_size
            field_cfg["max_width"] = new_width
            if has_line_spacing:
                field_cfg["line_spacing"] = new_line_spacing
            with open(CONFIG_PATH, "w", encoding="utf-8") as f:
                json.dump(templates, f, indent=2)
            st.success(f"Saved position for '{field_to_edit}'.")

    if st.button("Preview with current values"):
        try:
            preview_bytes = generate_certificate(
                template_key=template_key,
                participant_name=participant_name.strip() or "Sample Name",
                training_topic=topic_choice,
                course_highlights=highlights,
                date_text=format_date_ordinal(training_date),
                address=address.strip() or "Sample Address",
                certificate_number=certificate_number.strip() or "NJ_SAMPLE_001",
                extra_values=extra_values,
            )
            st.image(render_preview_png(preview_bytes), use_container_width=True)
        except FileNotFoundError as e:
            st.error(str(e))
