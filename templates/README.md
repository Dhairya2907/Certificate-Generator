# Templates folder

Place the original certificate PDFs here with these **exact filenames**
(referenced in `config/templates.json`):

- `eu_mdr_template.pdf`
- `cpd_iso13485_template.pdf`
- `ivdr_template.pdf`
- `Certificate template_NeuLearn.pdf`

These files are the fixed background design — logo, borders, signature, CPD
logo, footer text (document no. / revision / effective date) — and are never
modified by the app. Only the variable fields (name, topic, highlights, date,
address, certificate number) are drawn on top at generation time.

After adding the files, run the calibration steps in the main `README.md` to
align the text positions to this exact design.
