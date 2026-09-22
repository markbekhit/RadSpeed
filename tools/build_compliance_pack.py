#!/usr/bin/env python3
"""Render docs/compliance/*.md to styled HTML and PDF.

Usage:
    python tools/build_compliance_pack.py            # HTML + PDF per document
    python tools/build_compliance_pack.py --review   # also a single tabbed review page

PDFs are printed with headless Chrome (always run with a timeout so a stuck
page never leaves a Chrome process behind). Requires pandoc on PATH.
"""

from __future__ import annotations

import argparse
import html
import shutil
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "docs" / "compliance"
OUT = SRC / "build"
CHROME = "/Applications/Google Chrome.app/Contents/MacOS/Google Chrome"

ORDER = [
    ("security-statement", "Security statement"),
    ("data-processing-agreement", "Data processing agreement"),
    ("privacy-policy", "Privacy policy"),
    ("terms-of-use", "Terms of use"),
    ("data-breach-response-plan", "Breach plan and retention"),
    ("ranzcr-ai-tool-evidence-pack", "RANZCR AI-tool evidence"),
    ("tga-scoping-statement", "TGA scoping statement"),
]

CSS = """
:root{--ink:#1a2530;--muted:#5b6771;--line:#d8dee3;--accent:#0e6b62;--accent-soft:#dff0ec;--bg:#fff}
body{font-family:"IBM Plex Sans",-apple-system,Segoe UI,Helvetica,Arial,sans-serif;color:var(--ink);background:var(--bg);
 line-height:1.5;font-size:11pt;max-width:820px;margin:0 auto;padding:28px 32px}
h1{font-family:"Source Serif 4",Georgia,serif;font-size:22pt;line-height:1.2;margin:0 0 4px;color:var(--accent)}
h2{font-family:"Source Serif 4",Georgia,serif;font-size:15pt;margin:22px 0 6px;padding-top:8px;border-top:1px solid var(--line)}
h3{font-size:12pt;margin:14px 0 4px}
p{margin:0 0 8px}
table{border-collapse:collapse;width:100%;font-size:9.5pt;margin:6px 0 12px}
th,td{border:1px solid var(--line);padding:5px 7px;vertical-align:top;text-align:left}
th{background:var(--accent-soft);font-size:8.5pt;text-transform:uppercase;letter-spacing:.05em}
code{font-family:"IBM Plex Mono",Menlo,monospace;font-size:9.5pt;background:#eef1f3;padding:0 3px;border-radius:3px}
ul,ol{margin:0 0 10px;padding-left:20px}
li{margin-bottom:3px}
strong{font-weight:600}
.draft{display:inline-block;font-size:8.5pt;letter-spacing:.08em;text-transform:uppercase;color:#a8701a;background:#f8ecd6;padding:2px 8px;border-radius:999px;margin-bottom:10px}
@page{size:A4;margin:16mm 14mm}
"""


def pandoc_fragment(md_path: Path) -> str:
    return subprocess.run(
        ["pandoc", "-f", "gfm", "-t", "html5", str(md_path)],
        check=True, capture_output=True, text=True,
    ).stdout


def standalone(title: str, fragment: str) -> str:
    return (
        "<!doctype html><html lang=\"en-AU\"><head><meta charset=\"utf-8\">"
        f"<title>{html.escape(title)}</title><style>{CSS}</style></head><body>"
        "<div class=\"draft\">Draft for review</div>"
        f"{fragment}</body></html>"
    )


def to_pdf(html_path: Path, pdf_path: Path) -> bool:
    if not Path(CHROME).exists():
        print(f"  (Chrome not found; skipped PDF for {html_path.name})")
        return False
    cmd = [
        "timeout", "60", CHROME, "--headless=new", "--disable-gpu",
        "--no-pdf-header-footer", f"--print-to-pdf={pdf_path}", html_path.as_uri(),
    ]
    result = subprocess.run(cmd, capture_output=True, text=True)
    if result.returncode != 0 or not pdf_path.exists():
        print(f"  PDF failed for {html_path.name}: {result.stderr[-300:]}")
        return False
    return True


def build_review_page(fragments: list[tuple[str, str, str]]) -> str:
    tabs = "".join(
        f'<button class="tab" data-target="{slug}" id="tab-{slug}">{html.escape(label)}</button>'
        for slug, label, _ in fragments
    )
    panels = "".join(
        f'<section class="panel" id="{slug}" hidden>{frag}</section>'
        for slug, _, frag in fragments
    )
    return f"""<title>RadSpeed Compliance Pack</title>
<link rel="stylesheet" href="https://fonts.googleapis.com/css2?family=Source+Serif+4:opsz,wght@8..60,500;8..60,600&family=IBM+Plex+Sans:wght@400;500;600&family=IBM+Plex+Mono:wght@400&display=swap">
<style>
:root{{--bg:#f5f7f8;--surface:#fff;--ink:#1a2530;--muted:#5b6771;--line:#d8dee3;--accent:#0e6b62;--accent-soft:#dff0ec;--warn:#a8701a;--warn-soft:#f8ecd6;--mono-bg:#eef1f3}}
@media (prefers-color-scheme: dark){{:root:not([data-theme="light"]){{--bg:#121a20;--surface:#1a242c;--ink:#e6ebef;--muted:#9aa7b1;--line:#2d3a44;--accent:#5cc4b6;--accent-soft:#173933;--warn:#e2b05d;--warn-soft:#3b2e17;--mono-bg:#222d36}}}}
:root[data-theme="dark"]{{--bg:#121a20;--surface:#1a242c;--ink:#e6ebef;--muted:#9aa7b1;--line:#2d3a44;--accent:#5cc4b6;--accent-soft:#173933;--warn:#e2b05d;--warn-soft:#3b2e17;--mono-bg:#222d36}}
body{{background:var(--bg);color:var(--ink);font-family:"IBM Plex Sans",system-ui,sans-serif;font-size:16px;line-height:1.55;margin:0}}
.wrap{{max-width:900px;margin:0 auto;padding-inline:20px;padding-block:28px 64px}}
h1{{font-family:"Source Serif 4",Georgia,serif;font-size:1.9rem;font-weight:600;line-height:1.2;margin:0;text-wrap:balance}}
.eyebrow{{font-size:.75rem;letter-spacing:.08em;text-transform:uppercase;color:var(--muted);font-weight:600;margin-bottom:.4rem}}
.intro{{color:var(--muted);margin:.6rem 0 1.2rem;max-width:68ch}}
.todo{{background:var(--warn-soft);color:var(--ink);border-left:4px solid var(--warn);padding:.8rem 1rem;border-radius:6px;margin-bottom:1.2rem;max-width:68ch}}
.todo ul{{margin:.4rem 0 0;padding-left:1.2rem}}
.tabs{{display:flex;flex-wrap:wrap;gap:.4rem;position:sticky;top:env(safe-area-inset-top,0px);background:var(--bg);padding:.6rem 0;z-index:2;border-bottom:1px solid var(--line)}}
.tab{{font:inherit;font-size:.85rem;font-weight:500;padding:.35rem .8rem;border-radius:999px;border:1px solid var(--line);background:var(--surface);color:var(--ink);cursor:pointer}}
.tab[aria-selected="true"]{{background:var(--accent);border-color:var(--accent);color:#fff}}
.tab:focus-visible{{outline:2px solid var(--accent);outline-offset:2px}}
.panel{{background:var(--surface);border:1px solid var(--line);border-radius:8px;padding:1.4rem 1.6rem;margin-top:1rem}}
.panel h1{{font-size:1.5rem;color:var(--accent)}}
.panel h2{{font-family:"Source Serif 4",Georgia,serif;font-size:1.2rem;font-weight:600;margin:1.8rem 0 .5rem;padding-top:.8rem;border-top:1px solid var(--line)}}
.panel h3{{font-size:1rem;font-weight:600;margin:1.1rem 0 .3rem}}
.panel p{{margin:0 0 .8rem;max-width:72ch}}
.panel table{{border-collapse:collapse;width:100%;font-size:.9rem;margin:.5rem 0 1rem;display:block;overflow-x:auto}}
.panel th,.panel td{{border:1px solid var(--line);padding:.45rem .6rem;vertical-align:top;text-align:left}}
.panel th{{background:var(--accent-soft);font-size:.72rem;text-transform:uppercase;letter-spacing:.05em}}
.panel code{{font-family:"IBM Plex Mono",ui-monospace,monospace;font-size:.85em;background:var(--mono-bg);padding:.05em .35em;border-radius:3px}}
.panel ul,.panel ol{{padding-left:1.3rem;margin:0 0 1rem}}
.panel li{{margin-bottom:.35rem;max-width:72ch}}
.panel a{{color:var(--accent)}}
</style>
<div class="wrap">
  <div class="eyebrow">RadSpeed · Tier 2 document pack · drafts 22 September 2026</div>
  <h1>RadSpeed Compliance Pack</h1>
  <p class="intro">Seven documents a radiology practice will ask for before a pilot. Editable sources live in the repository under <code>docs/compliance/</code>, with PDFs in <code>docs/compliance/build/</code>. Pick a tab to read each one.</p>
  <div class="todo"><strong>Confirm before sending:</strong>
    <ul>
      <li>The legal entity and ABN supplying RadSpeed (existing material names Clarity Insights Imaging Pty Ltd for Imaging Finder).</li>
      <li>A monitored privacy and security contact address on radspeed.com.au.</li>
      <li>Cyber insurance status, and whether each practice gets a dedicated instance (recommended).</li>
      <li>A backup person for the breach plan roles.</li>
    </ul>
  </div>
  <nav class="tabs" role="tablist" aria-label="Documents">{tabs}</nav>
  {panels}
</div>
<script>
(function(){{
  const tabs=[...document.querySelectorAll('.tab')];
  const panels=[...document.querySelectorAll('.panel')];
  function show(slug){{
    tabs.forEach(t=>t.setAttribute('aria-selected',String(t.dataset.target===slug)));
    panels.forEach(p=>p.hidden=(p.id!==slug));
    try{{localStorage.setItem('radspeed-pack-tab',slug);}}catch(e){{}}
    if(location.hash!=='#'+slug) history.replaceState(null,'','#'+slug);
  }}
  tabs.forEach(t=>t.addEventListener('click',()=>show(t.dataset.target)));
  let initial=(location.hash||'').slice(1);
  if(!panels.some(p=>p.id===initial)){{ try{{initial=localStorage.getItem('radspeed-pack-tab')||'';}}catch(e){{}} }}
  if(!panels.some(p=>p.id===initial)) initial=panels[0].id;
  show(initial);
}})();
</script>
"""


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--review", action="store_true", help="also write the tabbed review page")
    args = parser.parse_args()
    if not shutil.which("pandoc"):
        print("pandoc is required", file=sys.stderr)
        return 1
    OUT.mkdir(exist_ok=True)
    fragments = []
    for slug, label in ORDER:
        md = SRC / f"{slug}.md"
        frag = pandoc_fragment(md)
        fragments.append((slug, label, frag))
        html_path = OUT / f"{slug}.html"
        html_path.write_text(standalone(label, frag), encoding="utf-8")
        ok = to_pdf(html_path, OUT / f"{slug}.pdf")
        print(f"{slug}: html{' + pdf' if ok else ''}")
    if args.review:
        review = OUT / "review.html"
        review.write_text(build_review_page(fragments), encoding="utf-8")
        print(f"review page: {review}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
