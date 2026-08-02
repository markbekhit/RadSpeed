"""Local KAD-512 chest-fracture score for the private fracture workbench."""

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
_MODEL_PATH = _PROJECT_ROOT / "models" / "kad512_chest_float.onnx"
_PARAMETERS_PATH = _PROJECT_ROOT / "models" / "kad512_chest_parameters.json"


def _prepare_image(image: "PreparedFractureImage") -> np.ndarray:
    with Image.open(io.BytesIO(image.data)) as source:
        resized = source.convert("RGB").resize((512, 512), Image.Resampling.BICUBIC)
        array = np.asarray(resized, dtype=np.float32) / 255.0
    array = (array - np.array((0.485, 0.456, 0.406), dtype=np.float32)) / np.array(
        (0.229, 0.224, 0.225), dtype=np.float32
    )
    return np.transpose(array, (2, 0, 1)).astype(np.float32)


@lru_cache(maxsize=1)
def _session_and_parameters():
    import onnxruntime as ort

    if not _MODEL_PATH.is_file() or not _PARAMETERS_PATH.is_file():
        raise FileNotFoundError("The chest fracture model is not installed")
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
    parameters = json.loads(_PARAMETERS_PATH.read_text())
    return session, parameters


def _probabilities_from_features(
    features: np.ndarray, parameters: dict[str, Any]
) -> np.ndarray:
    mean = np.asarray(parameters["feature_mean"], dtype=np.float32)
    scale = np.asarray(parameters["feature_scale"], dtype=np.float32)
    coefficient = np.asarray(
        parameters["classifier_coefficient"], dtype=np.float32
    )
    standardised = (features - mean) / scale
    decision = (
        standardised @ coefficient + float(parameters["classifier_intercept"])
    )
    calibrated_logit = (
        decision * float(parameters["calibrator_coefficient"])
        + float(parameters["calibrator_intercept"])
    )
    return 1.0 / (1.0 + np.exp(-calibrated_logit))


def score_chest_images(images: list["PreparedFractureImage"]) -> dict[str, Any]:
    """Return calibrated image-level scores; no image or features are retained."""
    if not images:
        raise ValueError("At least one chest image is required")
    session, parameters = _session_and_parameters()
    # Run views one at a time to cap the activation memory on the small private
    # server. The study result still returns every per-view score together.
    probabilities = np.concatenate(
        [
            _probabilities_from_features(
                session.run(
                    ["features"], {"image": _prepare_image(image)[None, ...]}
                )[0],
                parameters,
            )
            for image in images
        ]
    )
    if not np.isfinite(probabilities).all():
        raise RuntimeError("The chest fracture model returned an invalid score")
    view_probabilities = [float(np.clip(value, 0.0, 1.0)) for value in probabilities]
    return {
        "model": parameters["model"],
        "view_probabilities": view_probabilities,
        "highest_view_probability": max(view_probabilities),
        "validation_threshold": float(parameters["threshold"]),
    }
