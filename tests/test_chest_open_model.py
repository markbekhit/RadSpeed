from __future__ import annotations

import io
from pathlib import Path
from types import SimpleNamespace
import unittest
from unittest.mock import patch

import numpy as np
from PIL import Image

from llm.chest_open_model import score_chest_images


class _Session:
    def run(self, outputs, inputs):
        assert outputs == ["features"]
        assert inputs["image"].shape == (1, 3, 512, 512)
        first_feature = float(inputs["image"].mean())
        return [np.array([[first_feature, 2.0]], dtype=np.float32)]


def _png(shade: int) -> bytes:
    output = io.BytesIO()
    Image.new("L", (96, 80), color=shade).save(output, format="PNG")
    return output.getvalue()


class ChestOpenModelTests(unittest.TestCase):
    def test_scores_each_prepared_chest_view_without_retaining_pixels(self):
        parameters = {
            "model": "synthetic KAD",
            "feature_mean": [0.0, 0.0],
            "feature_scale": [1.0, 1.0],
            "classifier_coefficient": [1.0, 0.0],
            "classifier_intercept": 0.0,
            "calibrator_coefficient": 1.0,
            "calibrator_intercept": 0.0,
            "threshold": 0.2,
        }
        prepared = [
            SimpleNamespace(data=_png(70)),
            SimpleNamespace(data=_png(130)),
        ]

        with patch(
            "llm.chest_open_model._session_and_parameters",
            return_value=(_Session(), parameters),
        ):
            result = score_chest_images(prepared)

        self.assertEqual(result["model"], "synthetic KAD")
        self.assertEqual(len(result["view_probabilities"]), 2)
        self.assertNotEqual(
            result["view_probabilities"][0], result["view_probabilities"][1]
        )
        self.assertEqual(
            result["highest_view_probability"], max(result["view_probabilities"])
        )
        self.assertEqual(result["validation_threshold"], 0.2)

    @unittest.skipUnless(
        (
            Path(__file__).resolve().parents[1]
            / "models"
            / "kad512_chest_float.onnx"
        ).is_file(),
        "packaged chest model is fetched during the container build",
    )
    def test_packaged_chest_model_runs_end_to_end(self):
        result = score_chest_images([SimpleNamespace(data=_png(100))])

        self.assertTrue(result["model"].startswith("KAD-512"))
        self.assertEqual(len(result["view_probabilities"]), 1)
        self.assertGreaterEqual(result["highest_view_probability"], 0.0)
        self.assertLessEqual(result["highest_view_probability"], 1.0)
