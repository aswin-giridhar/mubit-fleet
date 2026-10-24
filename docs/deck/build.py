"""Build the deck: inline docs/architecture.svg into template.html, write index.html, export pitch-deck.pdf.

  python docs/deck/build.py            # HTML only
  python docs/deck/build.py --pdf      # HTML + docs/pitch-deck.pdf (needs Chrome)
"""
from __future__ import annotations

import re
import subprocess
import sys
from pathlib import Path

DECK = Path(__file__).resolve().parent
DOCS = DECK.parent
CHROME = r"C:\Program Files\Google\Chrome\Application\chrome.exe"


HATCH_RECT = re.compile(r'<rect x="([\d.]+)" y="([\d.]+)" width="([\d.]+)" height="([\d.]+)"(?: rx="([\d.]+)")? '
                        r'fill="url\(#(?:hatch|h2)\)"/>')


def _flat_hatch(html: str) -> str:
    """Replace pattern-filled rects with clipped stripe polygons.

    PDF viewers draw SVG pattern tiles with visible seams at the edge of the SVG; explicit polygons
    inside a clip path print cleanly everywhere.
    """
    def clip(poly, x0, y0, x1, y1):
        """Sutherland-Hodgman clip of a convex polygon to an axis-aligned rectangle."""
        edges = [(lambda p: p[0] >= x0, lambda a, b: (x0, a[1] + (b[1] - a[1]) * (x0 - a[0]) / (b[0] - a[0]))),
                 (lambda p: p[0] <= x1, lambda a, b: (x1, a[1] + (b[1] - a[1]) * (x1 - a[0]) / (b[0] - a[0]))),
                 (lambda p: p[1] >= y0, lambda a, b: (a[0] + (b[0] - a[0]) * (y0 - a[1]) / (b[1] - a[1]), y0)),
                 (lambda p: p[1] <= y1, lambda a, b: (a[0] + (b[0] - a[0]) * (y1 - a[1]) / (b[1] - a[1]), y1))]
        for inside, cut in edges:
            out = []
            for i, cur in enumerate(poly):
                prev = poly[i - 1]
                if inside(cur):
                    if not inside(prev):
                        out.append(cut(prev, cur))
                    out.append(cur)
                elif inside(prev):
                    out.append(cut(prev, cur))
            poly = out
            if not poly:
                break
        return poly

    def stripes(m: re.Match) -> str:
        x, y, w, h = (float(v) for v in m.groups()[:4])
        rx = m.group(5) or "0"
        parts = [f'<rect x="{x:g}" y="{y:g}" width="{w:g}" height="{h:g}" rx="{rx}" fill="#2E3438"/>']
        c = 0.0
        while c < w + h:
            band = [(x + c, y), (x + c + 11, y), (x + c + 11 - h, y + h), (x + c - h, y + h)]
            pts = clip(band, x, y, x + w, y + h)
            if len(pts) >= 3:
                parts.append('<polygon points="' + " ".join(f"{a:.2f},{b:.2f}" for a, b in pts) + '" fill="#F2B33D"/>')
            c += 22
        return "".join(parts)

    return HATCH_RECT.sub(stripes, html)


def build_html() -> Path:
    svg = (DOCS / "architecture.svg").read_text(encoding="utf-8")
    svg = re.sub(r'\swidth="1600" height="860"', "", svg, count=1)  # let CSS size the inline copy
    html = (DECK / "template.html").read_text(encoding="utf-8").replace("{{ARCH_SVG}}", svg)
    html = _flat_hatch(html)
    assert "url(#hatch)" not in html and "url(#h2)" not in html, "a hatch pattern survived"
    out = DECK / "index.html"
    out.write_text(html, encoding="utf-8")
    return out


def build_pdf(index: Path) -> Path:
    pdf = DOCS / "pitch-deck.pdf"
    subprocess.run([CHROME, "--headless=new", "--disable-gpu", "--no-pdf-header-footer",
                    "--virtual-time-budget=8000", f"--print-to-pdf={pdf}", index.as_uri()], check=True)
    return pdf


if __name__ == "__main__":
    index = build_html()
    print("wrote", index)
    if "--pdf" in sys.argv:
        print("wrote", build_pdf(index))
