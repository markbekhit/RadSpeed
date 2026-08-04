"""Safety and request-contract coverage for live fracture review."""

from __future__ import annotations

import io
import json
from types import SimpleNamespace
import unittest
from unittest.mock import MagicMock, patch

import numpy as np
from PIL import Image, PngImagePlugin

from llm.fracture_analysis import (
    FractureImageError,
    analyse_fracture_images,
    prepare_fracture_images,
)


def _png(*, width: int = 96, height: int = 80, marker: str | None = None) -> bytes:
    output = io.BytesIO()
    metadata = None
    if marker:
        metadata = PngImagePlugin.PngInfo()
        metadata.add_text("PatientName", marker)
    Image.new("L", (width, height), color=110).save(
        output, format="PNG", pnginfo=metadata
    )
    return output.getvalue()


def _assessment(
    summary: str = "Possible subtle fracture.", *, study_region: str = "other"
) -> str:
    return json.dumps(
        {
            "study_region": study_region,
            "assessment": "possible_fracture",
            "confidence_percent": 64,
            "summary": summary,
            "key_findings": ["Subtle cortical irregularity."],
            "limitations": ["Single study without priors."],
            "views": [
                {
                    "view_index": 1,
                    "summary": "Possible cortical irregularity.",
                    "confidence_percent": 59,
                    "boxes": [
                        {
                            "x_min": 300,
                            "y_min": 250,
                            "x_max": 600,
                            "y_max": 610,
                            "label": "possible fracture",
                        }
                    ],
                }
            ],
        }
    )


def _completion(text: str):
    return SimpleNamespace(
        choices=[SimpleNamespace(message=SimpleNamespace(content=text))]
    )


class FractureImagePreparationTests(unittest.TestCase):
    def test_reencodes_without_embedded_metadata(self):
        marker = "SYNTHETIC_PATIENT_MARKER"
        prepared = prepare_fracture_images([_png(marker=marker)])
        self.assertEqual(len(prepared), 1)
        self.assertEqual(prepared[0].mime_type, "image/png")
        self.assertNotIn(marker.encode(), prepared[0].data)
        with Image.open(io.BytesIO(prepared[0].data)) as image:
            self.assertEqual(image.size, (96, 80))
            self.assertEqual(image.info, {})

    def test_preserves_16_bit_display_contrast(self):
        source = io.BytesIO()
        gradient = np.linspace(0, 65535, 96 * 80, dtype=np.uint16).reshape(80, 96)
        Image.fromarray(gradient).save(source, format="PNG")

        prepared = prepare_fracture_images([source.getvalue()])

        with Image.open(io.BytesIO(prepared[0].data)) as image:
            values = np.asarray(image)
        self.assertGreater(len(np.unique(values)), 200)
        self.assertEqual(int(values.min()), 0)
        self.assertEqual(int(values.max()), 255)

    def test_rejects_non_image_and_too_small_raster(self):
        with self.assertRaises(FractureImageError):
            prepare_fracture_images([b"not an image"])
        with self.assertRaises(FractureImageError):
            prepare_fracture_images([_png(width=32, height=32)])

    def test_rejects_more_than_four_views(self):
        with self.assertRaises(FractureImageError):
            prepare_fracture_images([_png()] * 5)


class FractureAnalysisTests(unittest.TestCase):
    def test_runs_one_independent_frontier_read(self):
        client = MagicMock()
        client.chat.completions.create.return_value = _completion(
            _assessment("Independent frontier opinion.")
        )
        images = prepare_fracture_images([_png()])

        with patch("llm.fracture_analysis.OpenAI", return_value=client):
            result, method, supporting_models = analyse_fracture_images(
                images, clinical_context="synthetic trauma context"
            )

        self.assertEqual(method, "frontier_multiview_independent_single_pass")
        self.assertEqual(result.summary, "Independent frontier opinion.")
        self.assertEqual(supporting_models, [])
        self.assertEqual(client.chat.completions.create.call_count, 1)
        content = client.chat.completions.create.call_args.kwargs["messages"][1][
            "content"
        ]
        self.assertIn("synthetic trauma context", content[0]["text"])
        self.assertTrue(any(item.get("type") == "image_url" for item in content))

    def test_chest_study_returns_classifier_separately(self):
        client = MagicMock()
        client.chat.completions.create.return_value = _completion(
            _assessment("Independent chest opinion.", study_region="chest_ribs")
        )
        chest_scorer = MagicMock(
            return_value={
                "model": "synthetic KAD",
                "view_probabilities": [0.37],
                "highest_view_probability": 0.37,
                "validation_threshold": 0.05,
            }
        )
        general_locator = MagicMock()
        images = prepare_fracture_images([_png(width=120, height=96)])

        with patch("llm.fracture_analysis.OpenAI", return_value=client):
            result, method, supporting_models = analyse_fracture_images(
                images,
                chest_scorer=chest_scorer,
                general_locator=general_locator,
            )

        self.assertEqual(result.summary, "Independent chest opinion.")
        self.assertEqual(method, "frontier_multiview_independent_single_pass")
        self.assertEqual(len(supporting_models), 1)
        opinion = supporting_models[0]
        self.assertEqual(opinion["kind"], "classifier")
        self.assertEqual(opinion["highest_view_probability"], 0.37)
        self.assertEqual(opinion["evaluation"]["auc"], 0.780)
        chest_scorer.assert_called_once_with(images)
        general_locator.assert_not_called()
        self.assertEqual(client.chat.completions.create.call_count, 1)
        frontier_content = client.chat.completions.create.call_args.kwargs["messages"][
            1
        ]["content"]
        self.assertNotIn("37", frontier_content[0]["text"])
        self.assertNotIn("KAD", frontier_content[0]["text"])

    def test_general_study_does_not_run_chest_classifier(self):
        client = MagicMock()
        client.chat.completions.create.return_value = _completion(_assessment())
        chest_scorer = MagicMock()
        images = prepare_fracture_images([_png()])

        with patch("llm.fracture_analysis.OpenAI", return_value=client):
            _, method, supporting_models = analyse_fracture_images(
                images, chest_scorer=chest_scorer
            )

        self.assertEqual(method, "frontier_multiview_independent_single_pass")
        self.assertEqual(supporting_models, [])
        chest_scorer.assert_not_called()

    def test_general_study_returns_locator_as_separate_attention_cues(self):
        client = MagicMock()
        client.chat.completions.create.return_value = _completion(
            _assessment("Independent opinion.")
        )
        locator = MagicMock(
            return_value={
                "model": "synthetic locator",
                "score_semantics": "ranking_only_not_calibrated_probability",
                "views": [
                    {
                        "view_index": 1,
                        "boxes": [
                            {
                                "x_min": 300,
                                "y_min": 250,
                                "x_max": 500,
                                "y_max": 550,
                            }
                        ],
                    }
                ],
            }
        )
        images = prepare_fracture_images([_png(width=120, height=96)])

        with patch("llm.fracture_analysis.OpenAI", return_value=client):
            result, method, supporting_models = analyse_fracture_images(
                images, general_locator=locator
            )

        self.assertEqual(result.summary, "Independent opinion.")
        self.assertEqual(method, "frontier_multiview_independent_single_pass")
        self.assertEqual(len(supporting_models), 1)
        opinion = supporting_models[0]
        self.assertEqual(opinion["kind"], "locator")
        self.assertEqual(opinion["role"], "broad_fracture_locator")
        self.assertEqual(opinion["evaluation"]["auc"], 0.625)
        self.assertEqual(len(opinion["views"][0]["boxes"]), 1)
        locator.assert_called_once_with(images)
        self.assertEqual(client.chat.completions.create.call_count, 1)
        frontier_text = client.chat.completions.create.call_args.kwargs["messages"][1][
            "content"
        ][0]["text"]
        self.assertNotIn("detector", frontier_text)
        self.assertNotIn("proposal", frontier_text)

    def test_general_study_returns_strong_classifier_independently(self):
        client = MagicMock()
        client.chat.completions.create.return_value = _completion(
            _assessment("Independent frontier opinion.")
        )
        strong_scorer = MagicMock(
            return_value={
                "model": "calibrated_two_encoder_tiled_ensemble",
                "view_probabilities": [0.41],
                "highest_view_probability": 0.41,
                "study_status": "suspected_fracture",
                "study_fusion": "maximum_of_view_scores_not_study_calibrated",
                "views": [],
            }
        )
        images = prepare_fracture_images([_png(width=120, height=96)])

        with patch("llm.fracture_analysis.OpenAI", return_value=client):
            _, _, supporting_models = analyse_fracture_images(
                images, strong_scorer=strong_scorer
            )

        self.assertEqual(len(supporting_models), 1)
        opinion = supporting_models[0]
        self.assertEqual(opinion["role"], "calibrated_extremity_fracture_classifier")
        self.assertEqual(opinion["highest_view_probability"], 0.41)
        self.assertEqual(opinion["evaluation"]["auc"], 0.892)
        strong_scorer.assert_called_once_with(images)
        frontier_text = client.chat.completions.create.call_args.kwargs["messages"][
            1
        ]["content"][0]["text"]
        self.assertNotIn("0.41", frontier_text)

    def test_chest_study_does_not_run_extremity_classifier(self):
        client = MagicMock()
        client.chat.completions.create.return_value = _completion(
            _assessment("Independent chest opinion.", study_region="chest_ribs")
        )
        strong_scorer = MagicMock()
        images = prepare_fracture_images([_png(width=120, height=96)])

        with patch("llm.fracture_analysis.OpenAI", return_value=client):
            analyse_fracture_images(images, strong_scorer=strong_scorer)

        strong_scorer.assert_not_called()

    def test_offline_strong_classifier_is_shown_without_discarding_other_reads(self):
        client = MagicMock()
        client.chat.completions.create.return_value = _completion(
            _assessment("Independent frontier opinion.")
        )
        strong_scorer = MagicMock(side_effect=RuntimeError("synthetic offline"))
        images = prepare_fracture_images([_png(width=120, height=96)])

        with patch("llm.fracture_analysis.OpenAI", return_value=client):
            result, _, supporting_models = analyse_fracture_images(
                images, strong_scorer=strong_scorer
            )

        self.assertEqual(result.summary, "Independent frontier opinion.")
        self.assertEqual(len(supporting_models), 1)
        self.assertEqual(supporting_models[0]["kind"], "availability")
        self.assertFalse(supporting_models[0]["available"])

    def test_wrist_study_uses_paediatric_specialist_locator(self):
        client = MagicMock()
        client.chat.completions.create.return_value = _completion(
            _assessment("Independent wrist opinion.", study_region="wrist")
        )
        general_locator = MagicMock()
        wrist_locator = MagicMock(
            return_value={
                "model": "synthetic wrist locator",
                "scope": "paediatric wrist radiographs only",
                "score_semantics": "ranking_only_not_calibrated_probability",
                "views": [],
            }
        )
        images = prepare_fracture_images([_png()])

        with patch("llm.fracture_analysis.OpenAI", return_value=client):
            result, method, supporting_models = analyse_fracture_images(
                images,
                general_locator=general_locator,
                wrist_locator=wrist_locator,
            )

        self.assertEqual(result.study_region, "wrist")
        self.assertEqual(method, "frontier_multiview_independent_single_pass")
        self.assertEqual(supporting_models[0]["role"], "wrist_fracture_locator")
        self.assertEqual(supporting_models[0]["evaluation"]["auc"], 0.996)
        wrist_locator.assert_called_once_with(images)
        general_locator.assert_not_called()
        self.assertEqual(client.chat.completions.create.call_count, 1)
        frontier_text = client.chat.completions.create.call_args.kwargs["messages"][1][
            "content"
        ][0]["text"]
        self.assertNotIn("paediatric wrist", frontier_text)

    def test_open_locator_failure_does_not_discard_frontier_read(self):
        client = MagicMock()
        client.chat.completions.create.return_value = _completion(
            _assessment("Independent opinion.")
        )
        locator = MagicMock(side_effect=RuntimeError("synthetic unavailable"))
        images = prepare_fracture_images([_png()])

        with patch("llm.fracture_analysis.OpenAI", return_value=client):
            result, method, supporting_models = analyse_fracture_images(
                images, general_locator=locator
            )

        self.assertEqual(method, "frontier_multiview_independent_single_pass")
        self.assertEqual(result.summary, "Independent opinion.")
        self.assertEqual(supporting_models, [])
        locator.assert_called_once_with(images)

    def test_rejects_boxes_with_no_area(self):
        invalid = json.loads(_assessment())
        invalid["views"][0]["boxes"][0]["x_max"] = 300
        client = MagicMock()
        client.chat.completions.create.return_value = _completion(json.dumps(invalid))
        images = prepare_fracture_images([_png()])

        with patch("llm.fracture_analysis.OpenAI", return_value=client):
            with self.assertRaises(ValueError):
                analyse_fracture_images(images)


if __name__ == "__main__":
    unittest.main()
