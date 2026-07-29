"""Build a one-slide-per-page landscape PDF of the team briefing deck.

The deck (docs/slides/index.html) shows one slide at a time via JS. This
script injects a print stylesheet that reveals every slide, sizes each to
a landscape page, hides the on-screen navigation, and inlines the
screenshots, then renders it to docs/slides.pdf with headless Edge/Chrome.

Dependencies (developer machine only): Microsoft Edge or Google Chrome.
Run from the repository root:
    python scripts/build_slides_pdf.py
"""

import base64
import re
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
SLIDES = ROOT / "docs" / "slides" / "index.html"
SHOTS = ROOT / "docs" / "screenshots"
OUT_PDF = ROOT / "docs" / "slides.pdf"

PRINT_CSS = """
  html { -webkit-print-color-adjust: exact; print-color-adjust: exact; }
  @media print {
    @page { size: 297mm 210mm; margin: 0; }
    html, body { overflow: visible !important; height: auto !important; }
    .progress-track, .counter, .nav-buttons, .nav-hint { display: none !important; }
    .deck { position: static !important; width: auto !important; height: auto !important; }
    .slide {
      display: flex !important; position: relative !important; inset: auto !important;
      width: 297mm; height: 210mm; overflow: hidden;
      padding: 13mm 17mm; page-break-after: always; break-after: page;
    }
    .slide:last-child { page-break-after: auto; break-after: auto; }
    .shot { max-height: 126mm !important; }
    .shot-wrap { min-height: 0; }
    h1 { font-size: 30pt; } .title-slide h1 { font-size: 40pt; }
    h2 { font-size: 22pt; }
    .subtitle { font-size: 13pt; }
    p, li { font-size: 11.5pt; }
    table { font-size: 10.5pt; }
    .stat .num { font-size: 20pt; }
  }
"""


def find_browser():
    for path in (
        r"C:\Program Files (x86)\Microsoft\Edge\Application\msedge.exe",
        r"C:\Program Files\Microsoft\Edge\Application\msedge.exe",
        r"C:\Program Files\Google\Chrome\Application\chrome.exe",
        r"C:\Program Files (x86)\Google\Chrome\Application\chrome.exe",
    ):
        if Path(path).exists():
            return path
    raise SystemExit("No Edge or Chrome found for PDF rendering.")


def main() -> int:
    import subprocess

    html = SLIDES.read_text(encoding="utf-8")

    def inline(match):
        name = match.group(1).split("/")[-1]
        img = SHOTS / name
        if not img.exists():
            return match.group(0)
        data = base64.b64encode(img.read_bytes()).decode("ascii")
        return f'src="data:image/png;base64,{data}"'

    html = re.sub(r'src="(\.\./screenshots/[a-z0-9-]+\.png)"', inline, html)
    html = html.replace("</style>", PRINT_CSS + "</style>", 1)

    tmp = Path(tempfile.gettempdir()) / "sawahpintar-slides-print.html"
    tmp.write_text(html, encoding="utf-8")

    subprocess.run(
        [find_browser(), "--headless", "--disable-gpu", "--no-pdf-header-footer",
         f"--print-to-pdf={OUT_PDF}", tmp.as_uri()],
        check=True, timeout=120,
    )
    print(f"Wrote {OUT_PDF} ({OUT_PDF.stat().st_size} bytes)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
