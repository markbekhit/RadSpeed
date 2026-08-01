"""Adapt the offline benchmark review into RadSpeed's authenticated viewer."""

from __future__ import annotations

import argparse
from pathlib import Path


SOURCE_IMAGE_PREFIX = "../../data/extracted/orthofrac_xr/OrthoFrac-XR/"
HOSTED_IMAGE_PREFIX = "/fracture-workbench/images/"


def build(source: Path, destination: Path) -> int:
    html = source.read_text(encoding="utf-8")
    image_count = html.count(SOURCE_IMAGE_PREFIX)
    if image_count == 0:
        raise ValueError("No OrthoFrac-XR image references were found")

    html = html.replace(
        '<meta name="viewport" content="width=device-width, initial-scale=1">',
        '<meta name="viewport" content="width=device-width, initial-scale=1">\n'
        '  <meta name="robots" content="noindex, nofollow">',
    )
    html = html.replace(
        "<title>Hybrid fracture model review</title>",
        "<title>Fracture Lab · RadSpeed</title>",
    )
    html = html.replace(
        "    .notice { max-width: 900px; color: #fbbf24; }",
        "    .notice { max-width: 1050px; color: #fbbf24; }\n"
        "    .back { color: #93c5fd; text-decoration: none; }\n"
        "    .back:hover { text-decoration: underline; }",
    )
    html = html.replace(
        "  <h1>Hybrid fracture model review</h1>",
        '  <p><a class="back" href="/app">← Back to RadSpeed</a></p>\n'
        "  <h1>RadSpeed Fracture Lab</h1>",
    )
    html = html.replace(
        '<p class="notice">Public research images only.',
        '<p class="notice"><strong>Experimental benchmark viewer — uploads are not enabled.</strong> '
        "Public research images only. ",
    )
    notice_end = (
        "All boxes are approximate research proposals, not validated localisations. "
        "Not for patient care.</p>"
    )
    attribution = (
        notice_end
        + '\n  <p>Images: <a class="back" '
        + 'href="https://doi.org/10.6084/m9.figshare.32021085.v1" '
        + 'rel="external noopener">OrthoFrac-XR v1</a> by Tabib, Liza, Bijoy, '
        + 'Hasan and Khan, <a class="back" '
        + 'href="https://creativecommons.org/licenses/by/4.0/" '
        + 'rel="external noopener">CC BY 4.0</a>.</p>'
    )
    if notice_end not in html:
        raise ValueError("The benchmark safety notice could not be found")
    html = html.replace(notice_end, attribution, 1)
    html = html.replace(SOURCE_IMAGE_PREFIX, HOSTED_IMAGE_PREFIX)

    if html.count(HOSTED_IMAGE_PREFIX) != image_count:
        raise ValueError("Not all image references were converted")
    destination.parent.mkdir(parents=True, exist_ok=True)
    destination.write_text(html, encoding="utf-8")
    return image_count


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("source", type=Path)
    parser.add_argument("destination", type=Path)
    args = parser.parse_args()
    count = build(args.source, args.destination)
    print(f"Built {args.destination} with {count} image references")


if __name__ == "__main__":
    main()
