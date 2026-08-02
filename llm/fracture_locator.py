"""Local fracture proposal locators for second-pass visual zooms."""

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
_WRIST_MODEL_PATH = _PROJECT_ROOT / "models" / "yolov9_c_grazpedwri.onnx"
_WRIST_PARAMETERS_PATH = (
    _PROJECT_ROOT / "models" / "yolov9_c_grazpedwri_parameters.json"
)


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
def _session_and_parameters(locator: str):
    import onnxruntime as ort

    paths = {
        "broad": (_MODEL_PATH, _PARAMETERS_PATH),
        "wrist": (_WRIST_MODEL_PATH, _WRIST_PARAMETERS_PATH),
    }
    if locator not in paths:
        raise ValueError(f"Unknown fracture locator: {locator}")
    model_path, parameters_path = paths[locator]
    if not model_path.is_file() or not parameters_path.is_file():
        raise FileNotFoundError(f"The {locator} fracture locator is not installed")
    options = ort.SessionOptions()
    options.intra_op_num_threads = 1
    options.inter_op_num_threads = 1
    options.enable_cpu_mem_arena = False
    options.enable_mem_pattern = False
    session = ort.InferenceSession(
        str(model_path),
        sess_options=options,
        providers=["CPUExecutionProvider"],
    )
    return session, json.loads(parameters_path.read_text())


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
    session, parameters = _session_and_parameters("broad")
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


def _letterbox_image(
    image: "PreparedFractureImage", image_size: int
) -> tuple[np.ndarray, float, float, float, int, int]:
    with Image.open(io.BytesIO(image.data)) as source:
        rgb = source.convert("RGB")
        width, height = rgb.size
        ratio = min(image_size / width, image_size / height)
        resized_width = round(width * ratio)
        resized_height = round(height * ratio)
        resized = rgb.resize(
            (resized_width, resized_height), Image.Resampling.BILINEAR
        )
        pad_x = (image_size - resized_width) / 2
        pad_y = (image_size - resized_height) / 2
        canvas = Image.new("RGB", (image_size, image_size), (114, 114, 114))
        canvas.paste(resized, (round(pad_x - 0.1), round(pad_y - 0.1)))
        array = np.asarray(canvas, dtype=np.float32) / 255.0
    return (
        np.transpose(array, (2, 0, 1)).astype(np.float32),
        ratio,
        pad_x,
        pad_y,
        width,
        height,
    )


def _nms(
    boxes: np.ndarray, scores: np.ndarray, iou_threshold: float, top_k: int
) -> list[int]:
    order = np.argsort(scores)[::-1]
    retained: list[int] = []
    while order.size and len(retained) < top_k:
        current = int(order[0])
        retained.append(current)
        if order.size == 1:
            break
        remainder = order[1:]
        left = np.maximum(boxes[current, 0], boxes[remainder, 0])
        top = np.maximum(boxes[current, 1], boxes[remainder, 1])
        right = np.minimum(boxes[current, 2], boxes[remainder, 2])
        bottom = np.minimum(boxes[current, 3], boxes[remainder, 3])
        intersection = np.maximum(0, right - left) * np.maximum(0, bottom - top)
        current_area = max(
            0,
            (boxes[current, 2] - boxes[current, 0])
            * (boxes[current, 3] - boxes[current, 1]),
        )
        remainder_area = np.maximum(
            0,
            (boxes[remainder, 2] - boxes[remainder, 0])
            * (boxes[remainder, 3] - boxes[remainder, 1]),
        )
        union = current_area + remainder_area - intersection
        iou = np.divide(
            intersection,
            union,
            out=np.zeros_like(intersection),
            where=union > 0,
        )
        order = remainder[iou <= iou_threshold]
    return retained


def _decode_wrist_boxes(
    output: np.ndarray,
    parameters: dict[str, Any],
    geometry: tuple[float, float, float, int, int],
) -> list[dict[str, int]]:
    ratio, pad_x, pad_y, width, height = geometry
    class_row = 4 + int(parameters["fracture_class_index"])
    scores = output[0, class_row, :]
    selected = np.flatnonzero(scores >= float(parameters["candidate_min_score"]))
    if not selected.size:
        return []
    xywh = output[0, :4, selected]
    boxes = np.column_stack(
        (
            xywh[:, 0] - xywh[:, 2] / 2,
            xywh[:, 1] - xywh[:, 3] / 2,
            xywh[:, 0] + xywh[:, 2] / 2,
            xywh[:, 1] + xywh[:, 3] / 2,
        )
    )
    retained = _nms(
        boxes,
        scores[selected],
        float(parameters["nms_iou_threshold"]),
        int(parameters["recommended_top_k"]),
    )
    normalised: list[dict[str, int]] = []
    for retained_index in retained:
        left, top, right, bottom = boxes[retained_index]
        mapped = {
            "x_min": round(max(0, min(width, (left - pad_x) / ratio)) / width * 1000),
            "y_min": round(max(0, min(height, (top - pad_y) / ratio)) / height * 1000),
            "x_max": round(max(0, min(width, (right - pad_x) / ratio)) / width * 1000),
            "y_max": round(max(0, min(height, (bottom - pad_y) / ratio)) / height * 1000),
        }
        if mapped["x_max"] > mapped["x_min"] and mapped["y_max"] > mapped["y_min"]:
            normalised.append(mapped)
    return normalised


def locate_wrist_fracture_candidates(
    images: list["PreparedFractureImage"],
) -> dict[str, Any]:
    """Return paediatric-wrist specialist boxes without exposing raw scores."""
    if not images:
        raise ValueError("At least one radiograph is required")
    session, parameters = _session_and_parameters("wrist")
    image_size = int(parameters["input_size"])
    views = []
    for index, image in enumerate(images, start=1):
        prepared, ratio, pad_x, pad_y, width, height = _letterbox_image(
            image, image_size
        )
        output = session.run(
            [parameters["output_name"]],
            {parameters["input_name"]: prepared[None, ...]},
        )[0]
        views.append(
            {
                "view_index": index,
                "boxes": _decode_wrist_boxes(
                    output, parameters, (ratio, pad_x, pad_y, width, height)
                ),
            }
        )
    return {
        "model": parameters["model"],
        "score_semantics": parameters["score_semantics"],
        "scope": parameters["scope"],
        "views": views,
    }
