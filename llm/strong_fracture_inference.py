"""Exact local inference path for the externally evaluated open-model ensemble."""

from __future__ import annotations

import io
import os
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import joblib
import numpy as np
import torch
from huggingface_hub import snapshot_download
from PIL import Image, UnidentifiedImageError
from transformers import AutoImageProcessor, AutoModel


TILE_BOXES = np.array(
    [[0, 0, 1000, 1000]]
    + [[x, y, x + 550, y + 550] for y in (0, 225, 450) for x in (0, 225, 450)],
    dtype=np.int16,
)
MAX_IMAGES = 4
MAX_IMAGE_BYTES = 12 * 1024 * 1024


@dataclass
class EncoderBundle:
    name: str
    processor: Any
    model: Any
    classifier: dict[str, Any]


@dataclass
class ModelBundle:
    device: str
    encoders: dict[str, EncoderBundle]
    ensemble: dict[str, Any]


def _embedding_tensor(output: Any) -> torch.Tensor:
    if isinstance(output, torch.Tensor):
        return output
    for attribute in ("image_embeds", "pooler_output"):
        value = getattr(output, attribute, None)
        if value is not None:
            return value
    value = getattr(output, "last_hidden_state", None)
    if value is not None:
        return value.mean(dim=1)
    raise TypeError(f"Unsupported image feature output: {type(output).__name__}")


def _device_name(requested: str | None = None) -> str:
    if requested:
        return requested
    if torch.backends.mps.is_available():
        return "mps"
    if torch.cuda.is_available():
        return "cuda"
    return "cpu"


def _model_path(repository: str) -> str:
    return snapshot_download(repo_id=repository, local_files_only=True)


def _load_encoder(
    repository: str,
    classifier_path: Path,
    source_name: str,
    device: str,
) -> EncoderBundle:
    model_path = _model_path(repository)
    processor = AutoImageProcessor.from_pretrained(model_path, local_files_only=True)
    model = AutoModel.from_pretrained(model_path, local_files_only=True)
    model = model.to(device).eval()
    classifier = joblib.load(classifier_path)
    return EncoderBundle(source_name, processor, model, classifier)


def load_model(
    classifier_dir: str | os.PathLike[str], *, device: str | None = None
) -> ModelBundle:
    """Load the same two encoders and fitted heads used for the 0.892 AUC check."""
    root = Path(classifier_dir).expanduser().resolve()
    resolved_device = _device_name(device)
    encoders = {
        "medsiglip_tiled": _load_encoder(
            "google/medsiglip-448",
            root / "medsiglip_tiled_classifier.joblib",
            "medsiglip_tiled",
            resolved_device,
        ),
        "siglip_tiled": _load_encoder(
            "google/siglip-base-patch16-384",
            root / "siglip_tiled_classifier.joblib",
            "siglip_tiled",
            resolved_device,
        ),
    }
    ensemble = joblib.load(root / "two_encoder_tiled_ensemble.joblib")
    return ModelBundle(resolved_device, encoders, ensemble)


def decode_images(payload: dict[str, Any]) -> list[Image.Image]:
    """Decode already de-identified raster bytes from a worker payload."""
    import base64

    encoded_images = payload.get("images")
    if not isinstance(encoded_images, list) or not 1 <= len(encoded_images) <= MAX_IMAGES:
        raise ValueError("Supply between one and four images")
    images: list[Image.Image] = []
    try:
        for encoded in encoded_images:
            raw = base64.b64decode(encoded, validate=True)
            if not raw or len(raw) > MAX_IMAGE_BYTES:
                raise ValueError("An image is empty or exceeds the size limit")
            with Image.open(io.BytesIO(raw)) as source:
                source.load()
                images.append(source.convert("RGB"))
    except (ValueError, UnidentifiedImageError, OSError):
        for image in images:
            image.close()
        raise ValueError("An image could not be decoded safely") from None
    return images


def _tiles(image: Image.Image) -> list[Image.Image]:
    width, height = image.size
    result = [image.copy()]
    for x_min, y_min, x_max, y_max in TILE_BOXES[1:]:
        result.append(
            image.crop(
                (
                    round(x_min / 1000 * width),
                    round(y_min / 1000 * height),
                    round(x_max / 1000 * width),
                    round(y_max / 1000 * height),
                )
            )
        )
    return result


def _encoder_probabilities(
    images: list[Image.Image], bundle: EncoderBundle, device: str
) -> tuple[np.ndarray, np.ndarray]:
    all_embeddings: list[np.ndarray] = []
    for image in images:
        tiles = _tiles(image)
        try:
            inputs = bundle.processor(images=tiles, return_tensors="pt")
            pixel_values = inputs["pixel_values"].to(device)
            with torch.inference_mode():
                embeddings = _embedding_tensor(
                    bundle.model.get_image_features(pixel_values=pixel_values)
                )
                embeddings = torch.nn.functional.normalize(embeddings, dim=-1)
            all_embeddings.append(embeddings.detach().float().cpu().numpy())
        finally:
            for tile in tiles:
                tile.close()
    matrix = np.stack(all_embeddings)
    classifier = bundle.classifier
    global_probabilities = classifier["global_classifier"].predict_proba(
        matrix[:, 0, :]
    )[:, 1]
    local_shape = matrix[:, 1:, :].shape
    local_probabilities = (
        classifier["local_classifier"]
        .predict_proba(matrix[:, 1:, :].reshape(-1, matrix.shape[-1]))[:, 1]
        .reshape(local_shape[:2])
    )
    fusion_input = np.column_stack(
        [
            global_probabilities,
            local_probabilities.max(axis=1),
            np.sort(local_probabilities, axis=1)[:, -3:].mean(axis=1),
        ]
    )
    probabilities = classifier["fusion_classifier"].predict_proba(fusion_input)[:, 1]
    return probabilities, local_probabilities


def _status(probability: float, sources: list[float], ensemble: dict[str, Any]) -> str:
    disagreement = max(sources) - min(sources)
    if disagreement >= float(ensemble["disagreement_threshold"]):
        return "models_disagree"
    if probability >= float(ensemble["rule_in_threshold"]):
        return "suspected_fracture"
    if probability < float(ensemble["rule_out_threshold"]):
        return "fracture_unlikely"
    return "possible_fracture"


def predict(images: list[Image.Image], bundle: ModelBundle) -> dict[str, Any]:
    """Return per-view public-dataset estimates and a coarse attention tile."""
    started = time.monotonic()
    try:
        source_probabilities: dict[str, np.ndarray] = {}
        local_probabilities: dict[str, np.ndarray] = {}
        for source_name in bundle.ensemble["source_names"]:
            probabilities, local = _encoder_probabilities(
                images, bundle.encoders[source_name], bundle.device
            )
            source_probabilities[source_name] = probabilities
            local_probabilities[source_name] = local

        source_names = list(bundle.ensemble["source_names"])
        source_matrix = np.column_stack(
            [source_probabilities[name] for name in source_names]
        )
        ensemble_matrix = np.column_stack(
            [
                source_matrix,
                source_matrix.max(axis=1) - source_matrix.min(axis=1),
                source_matrix.mean(axis=1),
            ]
        )
        probabilities = bundle.ensemble["classifier"].predict_proba(ensemble_matrix)[:, 1]
        views: list[dict[str, Any]] = []
        for index, probability in enumerate(probabilities):
            sources = [float(source_probabilities[name][index]) for name in source_names]
            candidate_scores = np.mean(
                np.stack([local_probabilities[name][index] for name in source_names]),
                axis=0,
            )
            candidate_index = int(np.argmax(candidate_scores))
            box = TILE_BOXES[candidate_index + 1]
            views.append(
                {
                    "view_index": index + 1,
                    "fracture_probability": float(probability),
                    "status": _status(float(probability), sources, bundle.ensemble),
                    "source_probabilities": {
                        name: float(source_probabilities[name][index])
                        for name in source_names
                    },
                    "coarse_attention_box": {
                        "x_min": int(box[0]),
                        "y_min": int(box[1]),
                        "x_max": int(box[2]),
                        "y_max": int(box[3]),
                    },
                    "coarse_attention_score": float(candidate_scores[candidate_index]),
                }
            )
        highest_index = int(np.argmax(probabilities))
        return {
            "model": "calibrated_two_encoder_tiled_ensemble",
            "device": bundle.device,
            "view_probabilities": [float(value) for value in probabilities],
            "highest_view_probability": float(probabilities[highest_index]),
            "highest_view_index": highest_index + 1,
            "study_status": views[highest_index]["status"],
            "study_fusion": "maximum_of_view_scores_not_study_calibrated",
            "views": views,
            "elapsed_seconds": round(time.monotonic() - started, 3),
        }
    finally:
        for image in images:
            image.close()
