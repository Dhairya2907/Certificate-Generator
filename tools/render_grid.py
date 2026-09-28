"""
Calibration helper: renders a template PDF page to a PNG with a ruled grid
(every 20 PDF points) so you can read off x/y coordinates for
config/templates.json by eye.

Usage:
    python tools/render_grid.py eu_mdr
    python tools/render_grid.py cpd_iso13485
"""

import os
import sys

import fitz  # PyMuPDF

BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, BASE_DIR)

from utils.pdf_engine import load_template_config  # noqa: E402

GRID_STEP = 20
ZOOM = 2.0


def main():
    if len(sys.argv) != 2:
        print("Usage: python tools/render_grid.py <eu_mdr|cpd_iso13485>")
        sys.exit(1)

    template_key = sys.argv[1]
    config = load_template_config()[template_key]
    template_path = os.path.join(BASE_DIR, config["file"])

    if not os.path.exists(template_path):
        print(f"Template not found: {template_path}")
        print("Place the certificate PDF there first (see templates/README.md).")
        sys.exit(1)

    doc = fitz.open(template_path)
    page = doc[0]
    width, height = page.rect.width, page.rect.height

    for x in range(0, int(width), GRID_STEP):
        page.draw_line((x, 0), (x, height), color=(1, 0, 0), width=0.3)
        if x % 100 == 0:
            page.insert_text((x + 2, 10), str(x), fontsize=6, color=(1, 0, 0))
    for y in range(0, int(height), GRID_STEP):
        page.draw_line((0, y), (width, y), color=(1, 0, 0), width=0.3)
        if y % 100 == 0:
            page.insert_text((2, y + 8), str(y), fontsize=6, color=(1, 0, 0))

    pix = page.get_pixmap(matrix=fitz.Matrix(ZOOM, ZOOM))
    out_path = os.path.join(BASE_DIR, "tools", f"{template_key}_grid.png")
    pix.save(out_path)
    doc.close()
    print(f"Saved: {out_path}")
    print("Open this image, read the red-axis numbers to find the x,y point")
    print("coordinates for each field, then update config/templates.json.")


if __name__ == "__main__":
    main()
