from __future__ import annotations

import io
from pathlib import Path
from types import SimpleNamespace
import unittest
from unittest.mock import MagicMock, patch

import numpy as np
from PIL import Image

from llm.fracture_locator import locate_fracture_candidates


def _png(value: int = 100) -> bytes:
    output = io.BytesIO()
    Image.new("L", (96, 80), color=value).save(output, format="PNG")
    return output.getvalue()


class FractureLocatorTests(unittest.TestCase):
    def test_returns_ranked_boxes_without_exposing_raw_scores(self):
        session = MagicMock()
        session.run.return_value = [
            np.asarray([[[0.0], [4.0], [2.0]]], dtype=np.float32),
            np.asarray(
                [
                    [
                        [0.5, 0.5, 0.2, 0.2],
                        [0.1, 0.1, 0.4, 0.4],
                        [0.8, 0.7, 0.2, 0.2],
                    ]
                ],
                dtype=np.float32,
            ),
        ]
        parameters = {
            "model": "synthetic detector",
            "input_size": 32,
            "recommended_top_k": 2,
            "score_semantics": "ranking_only_not_calibrated_probability",
        }
        image = SimpleNamespace(data=_png())

        with patch(
            "llm.fracture_locator._session_and_parameters",
            return_value=(session, parameters),
        ):
            result = locate_fracture_candidates([image])

        self.assertEqual(result["views"][0]["view_index"], 1)
        self.assertEqual(
            result["views"][0]["boxes"][0],
            {"x_min": 0, "y_min": 0, "x_max": 300, "y_max": 300},
        )
        self.assertNotIn("score", result["views"][0]["boxes"][0])
        submitted = session.run.call_args.args[1]["pixel_values"]
        self.assertEqual(submitted.shape, (1, 3, 32, 32))

    @unittest.skipUnless(
        (
            Path(__file__).resolve().parents[1]
            / "models"
            / "rtdetr_fracatlas_full.onnx"
        ).is_file(),
        "packaged fracture locator is fetched during the container build",
    )
    def test_packaged_locator_runs_end_to_end(self):
        image = SimpleNamespace(data=_png())

        result = locate_fracture_candidates([image])

        self.assertEqual(len(result["views"]), 1)
        self.assertEqual(len(result["views"][0]["boxes"]), 3)
        self.assertEqual(
            result["score_semantics"],
            "ranking_only_not_calibrated_probability",
        )


if __name__ == "__main__":
    unittest.main()
