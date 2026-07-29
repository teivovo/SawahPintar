"""Build a nicely formatted PDF of the deployment manual.

Converts docs/deployment-manual.md to HTML with pandoc, inlines the
screenshots as data URIs, wraps it in a print-optimised template (cover
page, SawahPintar palette, framed figures, styled tables and callouts),
and renders it to docs/deployment-manual.pdf with headless Edge/Chrome.

Dependencies (developer machine only, not the workshop laptop):
- pandoc on PATH
- Microsoft Edge or Google Chrome (for --headless --print-to-pdf)

Run from the repository root:
    python scripts/build_manual_pdf.py
"""

import base64
import re
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
DOCS = ROOT / "docs"
MD = DOCS / "deployment-manual.md"
OUT_PDF = DOCS / "deployment-manual.pdf"

CSS = """
:root {
  --green:#2e6b3e; --green-deep:#1f4e2c; --water:#35708f;
  --ink:#1b2016; --muted:#5b6357; --line:#d8dfcc; --tint:#eef3ea;
}
* { box-sizing: border-box; }
@page { size: A4; margin: 16mm 16mm 18mm 16mm; }
html { -webkit-print-color-adjust: exact; print-color-adjust: exact; }
body {
  font-family: "Segoe UI", "Helvetica Neue", Arial, sans-serif;
  color: var(--ink); font-size: 10.5pt; line-height: 1.5; margin: 0;
}

/* Cover */
.cover { height: 246mm; display: flex; flex-direction: column; page-break-after: always; }
.cover-band {
  background: linear-gradient(140deg, var(--green) 0%, var(--water) 100%);
  color: #fff; padding: 24mm 18mm 16mm; border-radius: 0 0 12px 12px;
}
.cover-logo { font-size: 11pt; letter-spacing: 0.14em; text-transform: uppercase; font-weight: 700; opacity: 0.92; }
.cover h1 { font-size: 42pt; margin: 7mm 0 2mm; font-weight: 800; letter-spacing: -0.01em; color: #fff; border: none; }
.cover .sub { font-size: 15pt; font-weight: 500; opacity: 0.96; max-width: 40em; }
.cover-hero { margin: 12mm 0 0; text-align: center; }
.cover-hero img { max-width: 100%; max-height: 118mm; border-radius: 8px; border: 1px solid rgba(0,0,0,0.15); }
.cover-hero .cap { font-size: 9pt; color: var(--muted); font-style: italic; margin-top: 2mm; }
.cover-meta { margin-top: auto; padding: 0 18mm; color: var(--muted); font-size: 10pt; }
.cover-meta strong { color: var(--green-deep); }

h1, h2, h3, h4 { color: var(--green-deep); line-height: 1.22; }
h1 { font-size: 22pt; }
h2 {
  font-size: 18pt; margin: 0 0 4mm; padding-bottom: 2mm;
  border-bottom: 2px solid var(--green); page-break-before: always; page-break-after: avoid;
}
/* The first section flows straight onto the page after the cover, rather
   than leaving a near-empty page under the removed title. */
h2:first-of-type { page-break-before: avoid; }
h3 { font-size: 13pt; margin: 6mm 0 2mm; page-break-after: avoid; }
h4 { font-size: 11.5pt; margin: 4mm 0 1mm; color: var(--water); page-break-after: avoid; }
p { margin: 0 0 2.6mm; }
a { color: var(--water); text-decoration: none; }
strong { color: var(--green-deep); }
ul, ol { margin: 0 0 3mm; padding-left: 6mm; }
li { margin: 0 0 1.4mm; }

code { font-family: "Consolas", "Courier New", monospace; font-size: 9.3pt; background: #f2f4ef; padding: 0.4mm 1.2mm; border-radius: 3px; }
pre {
  background: #f6f8f3; border: 1px solid var(--line); border-left: 3px solid var(--green);
  border-radius: 6px; padding: 3mm 4mm; overflow: auto; page-break-inside: avoid;
}
pre code { background: none; padding: 0; font-size: 9pt; }

table { border-collapse: collapse; width: 100%; margin: 2mm 0 4mm; font-size: 9.5pt; page-break-inside: avoid; }
th, td { text-align: left; padding: 2mm 3mm; border: 1px solid var(--line); vertical-align: top; }
th { background: var(--tint); color: var(--green-deep); font-weight: 700; }
tr:nth-child(even) td { background: #fafbf8; }

figure { margin: 4mm 0; text-align: center; page-break-inside: avoid; }
figure img { max-width: 100%; border: 1px solid var(--line); border-radius: 6px; }
figcaption { font-size: 9pt; color: var(--muted); font-style: italic; margin-top: 1.6mm; }

blockquote { margin: 3mm 0; padding: 2.5mm 4mm; background: var(--tint); border-left: 4px solid var(--green); border-radius: 4px; }
blockquote p:last-child { margin-bottom: 0; }
hr { border: none; border-top: 1px solid var(--line); margin: 5mm 0; }
"""


def find_browser():
    candidates = [
        r"C:\Program Files (x86)\Microsoft\Edge\Application\msedge.exe",
        r"C:\Program Files\Microsoft\Edge\Application\msedge.exe",
        r"C:\Program Files\Google\Chrome\Application\chrome.exe",
        r"C:\Program Files (x86)\Google\Chrome\Application\chrome.exe",
    ]
    for path in candidates:
        if Path(path).exists():
            return path
    raise SystemExit("No Edge or Chrome found for PDF rendering.")


def inline_images(html: str) -> str:
    def repl(match):
        src = match.group(1)
        img_path = (DOCS / src).resolve()
        if not img_path.exists():
            return match.group(0)
        data = base64.b64encode(img_path.read_bytes()).decode("ascii")
        return f'src="data:image/png;base64,{data}"'

    return re.sub(r'src="([^"]+\.png)"', repl, html)


def main() -> int:
    if not shutil.which("pandoc"):
        raise SystemExit("pandoc not found on PATH.")
    body = subprocess.run(
        ["pandoc", str(MD), "-f", "gfm+implicit_figures", "-t", "html5", "--wrap=none"],
        capture_output=True, text=True, check=True, encoding="utf-8",
    ).stdout
    # Drop the manual's own top title; the cover page already carries it.
    body = re.sub(r"<h1[^>]*>.*?</h1>", "", body, count=1, flags=re.S)
    body = inline_images(body)

    hero = ROOT / "docs" / "screenshots" / "field-map.png"
    hero_uri = "data:image/png;base64," + base64.b64encode(hero.read_bytes()).decode("ascii")

    cover = f"""
    <div class="cover">
      <div class="cover-band">
        <div class="cover-logo">Rural AI - Newcastle x Universitas Hasanuddin</div>
        <h1>SawahPintar</h1>
        <div class="sub">Deployment Manual - building the kit and running a workshop</div>
      </div>
      <div class="cover-hero">
        <img src="{hero_uri}" alt="The SawahPintar field map">
        <div class="cap">The farmer display: a map of the field, one plot per sensor.</div>
      </div>
      <div class="cover-meta">
        <p><strong>For Newcastle and Hasanuddin faculty</strong> building kits and running
        soil-sensor teaching workshops for rice farmers in South Sulawesi.</p>
        <p>This document is generated from docs/deployment-manual.md.</p>
      </div>
    </div>
    """

    html = (
        "<!doctype html><html lang=\"en\"><head><meta charset=\"utf-8\">"
        f"<title>SawahPintar Deployment Manual</title><style>{CSS}</style></head>"
        f"<body>{cover}{body}</body></html>"
    )

    tmp = Path(tempfile.gettempdir()) / "sawahpintar-manual.html"
    tmp.write_text(html, encoding="utf-8")

    browser = find_browser()
    subprocess.run(
        [browser, "--headless", "--disable-gpu", "--no-pdf-header-footer",
         f"--print-to-pdf={OUT_PDF}", tmp.as_uri()],
        check=True, timeout=120,
    )
    size = OUT_PDF.stat().st_size
    print(f"Wrote {OUT_PDF} ({size} bytes)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
