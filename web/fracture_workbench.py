"""Filesystem helpers for the authenticated fracture research workbench."""

from __future__ import annotations

import os
from pathlib import Path


SUPPORTED_IMAGE_SUFFIXES = {".jpg", ".jpeg", ".png"}


def fracture_workbench_root() -> Path:
    """Return the persistent data directory used by the hosted workbench."""
    configured = os.environ.get(
        "RADSPEED_FRACTURE_WORKBENCH_DIR", "/data/fracture_workbench"
    )
    return Path(configured).expanduser().resolve()


def resolve_workbench_image(image_path: str, *, root: Path | None = None) -> Path:
    """Resolve an image below the workbench root without allowing traversal."""
    image_root = (root or fracture_workbench_root()) / "images"
    image_root = image_root.resolve()
    requested = Path(image_path)
    if requested.is_absolute() or requested.suffix.lower() not in SUPPORTED_IMAGE_SUFFIXES:
        raise ValueError("Unsupported fracture workbench image path")

    candidate = (image_root / requested).resolve()
    try:
        candidate.relative_to(image_root)
    except ValueError as exc:
        raise ValueError("Fracture workbench image path escapes its data directory") from exc
    return candidate
