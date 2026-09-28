# Neujin Solutions - Certificate Generator

Internal tool that replaces manual Canva editing for training certificates.
Pick a template, fill in a few fields, and download a ready-to-send PDF
certificate that keeps the original design untouched.

## Folder structure

```
Certificate generator/
├── app.py                      # Streamlit app (the tool itself)
├── requirements.txt
├── config/
│   ├── topics.json             # training topic -> course highlights mapping
│   └── templates.json          # per-template field coordinates (editable via Calibration mode)
├── templates/
│   ├── README.md
│   ├── eu_mdr_template.pdf      # <- add this file yourself (see below)
│   ├── cpd_iso13485_template.pdf  # <- add this file yourself (see below)
│   └── ivdr_template.pdf        # <- add this file yourself (see below)
├── utils/
│   ├── pdf_engine.py           # core overlay logic (PyMuPDF)
│   ├── text_utils.py           # date formatting, text wrap/autosize
│   └── bulk_generator.py       # Excel-driven batch generation, ZIP packaging
├── tools/
│   └── render_grid.py          # optional: prints a coordinate grid over a template
└── output/                     # (unused by default - PDFs are downloaded via the browser)
```

## 1. Setup

Requires Python 3.9+.

```bash
cd "Certificate generator"
python -m venv venv
venv\Scripts\activate          # Windows
pip install -r requirements.txt
```

## 2. Add the real certificate templates

The app ships without the actual certificate PDFs (they need to be added once).
Copy your master certificate PDFs into `templates/` and name them exactly:

- `templates/eu_mdr_template.pdf`
- `templates/cpd_iso13485_template.pdf`
- `templates/ivdr_template.pdf`
- `templates/Certificate template_NeuLearn.pdf`

## 3. Run the app

```bash
streamlit run app.py
```

This opens the tool in your browser (usually http://localhost:8501).

## 4. Calibrate text positions (one-time, per template)

Because every certificate design places text in different spots, the app
includes a built-in **Calibration Mode** so no code editing is needed:

1. In the sidebar, check **Calibration mode**.
2. Choose the field to adjust (e.g. `participant_name`).
3. Adjust `x`, `y`, `font size`, and `max width`, then click **Preview with
   current values** to see the result rendered over the real template.
4. Once it looks right, click **Save position** — this writes the new
   coordinates into `config/templates.json` permanently.
5. Repeat for each field (`participant_name`, `training_topic`,
   `course_highlights`, `date`, `address`, `certificate_number`, plus any
   template-specific extra fields) on each template.

Tip: coordinates are in PDF points, measured from the **top-left** corner of
the page (x increases right, y increases downward).

If you prefer working outside the app, `tools/render_grid.py` prints a red
ruled grid over a template so you can read off coordinates directly:

```bash
python tools/render_grid.py eu_mdr
python tools/render_grid.py cpd_iso13485
```

This saves `tools/eu_mdr_grid.png` / `tools/cpd_iso13485_grid.png` — open the
image, find where a field should sit, and type those x/y numbers into
Calibration Mode (or directly into `config/templates.json`).

## 5. Generate a certificate

1. Select the template from the dropdown.
2. Enter Participant Name, Certificate Number, Training Address/Place.
3. Select the Training Topic — Course Highlights auto-fill from
   `config/topics.json`.
4. Pick the Training/Issue Date from the calendar (rendered as
   `20th April 2026` on the certificate).
5. Click **Generate Certificate**, preview it, then **Download PDF**
   (a PNG download is also offered).

## 6. Bulk generate from an Excel sheet

The **Bulk Generate (Excel)** tab generates one certificate per row instead
of filling the form one at a time:

1. Click **Download sample Excel template** to get a `.xlsx` file with the
   correct column headers and one example row per template.
2. Fill in one row per certificate. The required column headers are:

   | Template | Participant Name | Training Topic | Date | Certificate Number |
   |---|---|---|---|---|

   - `Template` must match a template's display name (`EU MDR Certificate`,
     `CPD ISO 13485 Certificate`, `IVDR Certificate`,
     `NeuLearn Masterclass Certificate`) or its internal key (`eu_mdr`,
     `cpd_iso13485`, `ivdr`, `neulearn_masterclass`) - not case-sensitive.
   - `Training Topic` must match a topic name from `config/topics.json`
     exactly (not case-sensitive) for templates that display course
     highlights - course highlights are looked up automatically, same as
     the single-certificate form. Templates without a highlights section
     (e.g. NeuLearn Masterclass) accept any free-text course name instead -
     for that template, put the actual course name in this column.
   - `Date` can be a real Excel date cell or a text date like `2026-04-20`.
   - `Address` is an **optional column** - it's only required for templates
     whose design prints an address (EU MDR, CPD ISO 13485, IVDR). Leave it
     blank on rows that don't need it, or drop the column from the sheet
     entirely if none of your rows need it (e.g. an all-NeuLearn Masterclass
     batch - a sheet with just Template, Participant Name, Training Topic,
     Date, and Certificate Number is enough).
   - Templates with extra fields (e.g. IVDR's "Second Trainer Name") pick up
     a matching optional column automatically - leave it blank on rows for
     templates that don't use it.
3. Upload the filled sheet and click **Generate All Certificates**.
4. A results table shows the status of every row - rows with a problem
   (unknown topic, unreadable date, missing field, etc.) are reported with
   the reason and skipped, without stopping the rest of the batch.
5. Click **Download ZIP of certificates** to get every successfully
   generated PDF in one archive, named after each row's Participant Name
   (a numeric suffix is added automatically if a name repeats).

## Adding or editing training topics

Use the **Manage Training Topics** tab in the app - no file editing needed:

1. **Add a new topic**: enter a topic name and its course highlights (one per
   line), then **Save new topic**. It appears in the Training Topic dropdown
   immediately.
2. **Edit or delete an existing topic**: pick it from the dropdown, change
   the name and/or highlights, then **Save changes** - or click **Delete
   this topic** to remove it entirely.

This writes directly to `config/topics.json`, which is a plain JSON mapping
of topic name to a list of highlight bullets:

```json
{
  "New Topic Name": [
    "First highlight",
    "Second highlight",
    "Third highlight"
  ]
}
```

You can also edit this file directly (then restart `streamlit run`) if you
prefer working outside the app.

## Certificate number handling

The certificate number field in the footer is redrawn on every generation:
the app removes the old baked-in number (via PDF redaction, which deletes just
that text and leaves the rest of the background untouched) and writes your
entered number in its place. Document No., Revision No., and Effective Date
stay exactly as printed on the original template.

## Adding another certificate template

The template dropdown is built entirely from `config/templates.json` - adding
a new entry there and dropping in the PDF is enough for it to show up, no
other code changes required. To add one:

1. Save the blank master PDF into `templates/`, e.g. `templates/new_template.pdf`.
   If you have a filled example of the same design, keep it too (e.g.
   `templates/_demo_new_template_filled.pdf`) - it makes getting exact
   coordinates far easier than guessing blind.
2. Add a new top-level entry to `config/templates.json`, modeled on the
   existing ones:

   ```json
   "new_key": {
     "display_name": "New Template Name",
     "file": "templates/new_template.pdf",
     "page_size": [595.5, 842.25],
     "date_format": "ordinal",
     "fields": {
       "participant_name": { "x": ..., "y": ..., ... },
       "training_topic": { ... },
       "date": { ... },
       "address": { ... },
       "course_highlights": { ... },
       "certificate_number": { "redact_rect": [...], ... }
     }
   }
   ```

   Start with rough numbers (or copy an existing template's block as a
   starting point) and refine with **Calibration Mode** - it now works for
   any template key automatically.

   `address` and `course_highlights` are optional - if the design has no
   room for them (e.g. NeuLearn Masterclass), just leave them out of
   `"fields"` entirely. The app then hides the matching form inputs, skips
   them in bulk generation, and the training topic becomes a free-text
   "Course Name" field instead of the highlights-backed dropdown.
3. If a field's position sits on top of *fixed* baked-in text (e.g. a footer
   number, or an address already printed on the template), give it a
   `redact_rect` so the old text is removed before the new value is drawn.
   `certificate_number` almost always needs one; `address` only needs one if
   the template ships with a real address already printed on it (the IVDR
   template does, since it was built for a specific client's batch).
4. If the design needs a field beyond the standard six (the IVDR template has
   a second trainer's name, since it has two signature blocks instead of
   one), add it under an `"extra_fields"` dict instead of `"fields"`:

   ```json
   "extra_fields": {
     "trainer2_name": {
       "label": "Second Trainer Name",
       "default": "DR. ANITA JOSHI",
       "x": ..., "y": ..., "fontsize": ..., "redact_rect": [...]
     }
   }
   ```

   This automatically adds a text input to the Single Certificate form (with
   `default` pre-filled), an optional matching column in the bulk Excel sheet
   (named after `label`), and a calibratable entry in Calibration Mode - no
   Python changes needed.
5. If the template uses rotated text (the IVDR template's certificate number
   runs vertically along the left edge), add `"rotate": 270` (or `90`/`180`)
   to that field.
6. If the new template needs its own course, add it to `config/topics.json`
   (see below) so it's selectable from the Training Topic dropdown.

## Notes / current limitations

- Long names/addresses automatically shrink their font size (down to a
  floor) to avoid overlapping other design elements.
- Only the first page of each template PDF is used.
- Bulk generation only outputs PDFs (no PNG export) in the ZIP.
