"""Local broad fracture proposal locator for second-pass visual zooms."""

from __future__ import annotations

import io
import json
from functools import lru_cache
from pathlib import Path
from typing import TYPE_CHECKING, Any

import numpy as np
from PIL import Image

if TYPE_CHECKING:
    from llm.fracture_analysis import PreparedFractureImage


_PROJECT_ROOT = Path(__file__).resolve().parents[1]
_MODEL_PATH = _PROJECT_ROOT / "models" / "rtdetr_fracatlas_full.onnx"
_PARAMETERS_PATH = _PROJECT_ROOT / "models" / "rtdetr_fracatlas_full_parameters.json"


def _prepare_image(
    image: "PreparedFractureImage", image_size: int
) -> np.ndarray:
    with Image.open(io.BytesIO(image.data)) as source:
        resized = source.convert("RGB").resize(
            (image_size, image_size), Image.Resampling.BILINEAR
        )
        array = np.asarray(resized, dtype=np.float32) / 255.0
    return np.transpose(array, (2, 0, 1)).astype(np.float32)


@lru_cache(maxsize=1)
def _session_and_parameters():
    import onnxruntime as ort

    if not _MODEL_PATH.is_file() or not _PARAMETERS_PATH.is_file():
        raise FileNotFoundError("The broad fracture locator is not installed")
    options = ort.SessionOptions()
    options.intra_op_num_threads = 1
    options.inter_op_num_threads = 1
    options.enable_cpu_mem_arena = False
    options.enable_mem_pattern = False
    session = ort.InferenceSession(
        str(_MODEL_PATH),
        sess_options=options,
        providers=["CPUExecutionProvider"],
    )
    return session, json.loads(_PARAMETERS_PATH.read_text())


def _decode_boxes(
    logits: np.ndarray, pred_boxes: np.ndarray, top_k: int
) -> list[dict[str, int]]:
    scores = 1.0 / (1.0 + np.exp(-np.clip(logits[0], -30.0, 30.0)))
    order = np.argsort(scores.max(axis=1))[::-1][:top_k]
    boxes: list[dict[str, int]] = []
    for query_index in order:
        center_x, center_y, width, height = pred_boxes[0, query_index]
        box = {
            "x_min": max(0, min(1000, round(float(center_x - width / 2) * 1000))),
            "y_min": max(0, min(1000, round(float(center_y - height / 2) * 1000))),
            "x_max": max(0, min(1000, round(float(center_x + width / 2) * 1000))),
            "y_max": max(0, min(1000, round(float(center_y + height / 2) * 1000))),
        }
        if box["x_max"] > box["x_min"] and box["y_max"] > box["y_min"]:
            boxes.append(box)
    return boxes


def locate_fracture_candidates(
    images: list["PreparedFractureImage"],
) -> dict[str, Any]:
    """Return ranked proposal boxes without presenting scores as probabilities."""
    if not images:
        raise ValueError("At least one radiograph is required")
    session, parameters = _session_and_parameters()
    image_size = int(parameters["input_size"])
    top_k = int(parameters["recommended_top_k"])
    views = []
    for index, image in enumerate(images, start=1):
        logits, pred_boxes = session.run(
            ["logits", "pred_boxes"],
            {"pixel_values": _prepare_image(image, image_size)[None, ...]},
        )
        views.append(
            {
                "view_index": index,
                "boxes": _decode_boxes(logits, pred_boxes, top_k),
            }
        )
    return {
        "model": parameters["model"],
        "score_semantics": parameters["score_semantics"],
        "views": views,
    }
