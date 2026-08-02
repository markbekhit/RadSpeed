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
    def test_runs_fresh_multiview_read_and_visual_critic(self):
        client = MagicMock()
        client.chat.completions.create.side_effect = [
            _completion(_assessment("Initial opinion.")),
            _completion(_assessment("Critic-confirmed opinion.")),
        ]
        images = prepare_fracture_images([_png()])

        with patch("llm.fracture_analysis.OpenAI", return_value=client):
            result, method, open_model = analyse_fracture_images(
                images, clinical_context="synthetic trauma context"
            )

        self.assertEqual(method, "frontier_multiview_with_visual_critic")
        self.assertEqual(result.summary, "Critic-confirmed opinion.")
        self.assertIsNone(open_model)
        self.assertEqual(client.chat.completions.create.call_count, 2)
        second_request = client.chat.completions.create.call_args_list[1].kwargs
        second_content = second_request["messages"][1]["content"]
        self.assertIn("fresh second reader", second_content[0]["text"])
        self.assertTrue(
            any(item.get("type") == "image_url" for item in second_content)
        )

    def test_chest_study_is_auto_routed_to_open_model_and_zoomed_critic(self):
        client = MagicMock()
        client.chat.completions.create.side_effect = [
            _completion(
                _assessment("Initial chest opinion.", study_region="chest_ribs")
            ),
            _completion(
                _assessment(
                    "Critic-confirmed chest opinion.", study_region="chest_ribs"
                )
            ),
        ]
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
            _, method, open_model = analyse_fracture_images(
                images,
                chest_scorer=chest_scorer,
                general_locator=general_locator,
            )

        self.assertEqual(method, "frontier_chest_multiscale_with_visual_critic")
        self.assertEqual(open_model["highest_view_probability"], 0.37)
        chest_scorer.assert_called_once_with(images)
        general_locator.assert_not_called()
        first_content = client.chat.completions.create.call_args_list[0].kwargs[
            "messages"
        ][1]["content"]
        second_content = client.chat.completions.create.call_args_list[1].kwargs[
            "messages"
        ][1]["content"]
        first_images = [
            item for item in first_content if item.get("type") == "image_url"
        ]
        second_images = [
            item for item in second_content if item.get("type") == "image_url"
        ]
        self.assertEqual(len(first_images), 1)
        self.assertEqual(len(second_images), 3)
        self.assertIn("Search each rib sequentially", second_content[0]["text"])
        self.assertIn("37.0% fracture probability", second_content[0]["text"])
        self.assertIn("fallible supporting evidence", second_content[0]["text"])
        self.assertTrue(
            any(
                "Supplemental displayed left" in item.get("text", "")
                for item in second_content
            )
        )

    def test_general_study_does_not_run_chest_classifier(self):
        client = MagicMock()
        client.chat.completions.create.side_effect = [
            _completion(_assessment()),
            _completion(_assessment()),
        ]
        chest_scorer = MagicMock()
        images = prepare_fracture_images([_png()])

        with patch("llm.fracture_analysis.OpenAI", return_value=client):
            _, method, open_model = analyse_fracture_images(
                images, chest_scorer=chest_scorer
            )

        self.assertEqual(method, "frontier_multiview_with_visual_critic")
        self.assertIsNone(open_model)
        chest_scorer.assert_not_called()

    def test_general_study_uses_untrusted_locator_zooms_for_second_read(self):
        client = MagicMock()
        client.chat.completions.create.side_effect = [
            _completion(_assessment("Initial opinion.")),
            _completion(_assessment("Proposal-assisted opinion.")),
        ]
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
            result, method, open_model = analyse_fracture_images(
                images, general_locator=locator
            )

        self.assertEqual(result.summary, "Proposal-assisted opinion.")
        self.assertEqual(
            method, "frontier_proposal_multiscale_with_visual_critic"
        )
        self.assertIsNone(open_model)
        locator.assert_called_once_with(images)
        second_content = client.chat.completions.create.call_args_list[1].kwargs[
            "messages"
        ][1]["content"]
        second_images = [
            item for item in second_content if item.get("type") == "image_url"
        ]
        self.assertEqual(len(second_images), 2)
        self.assertIn("not a fracture classifier", second_content[0]["text"])
        self.assertTrue(
            any(
                "Untrusted detector proposal" in item.get("text", "")
                for item in second_content
            )
        )

    def test_wrist_study_uses_paediatric_specialist_locator(self):
        client = MagicMock()
        client.chat.completions.create.side_effect = [
            _completion(_assessment("Initial wrist opinion.", study_region="wrist")),
            _completion(_assessment("Wrist-assisted opinion.", study_region="wrist")),
        ]
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
            result, method, _ = analyse_fracture_images(
                images,
                general_locator=general_locator,
                wrist_locator=wrist_locator,
            )

        self.assertEqual(result.study_region, "wrist")
        self.assertEqual(
            method, "frontier_wrist_proposal_multiscale_with_visual_critic"
        )
        wrist_locator.assert_called_once_with(images)
        general_locator.assert_not_called()
        second_content = client.chat.completions.create.call_args_list[1].kwargs[
            "messages"
        ][1]["content"]
        self.assertIn("paediatric wrist", second_content[0]["text"])

    def test_returns_initial_read_if_critic_response_is_malformed(self):
        client = MagicMock()
        client.chat.completions.create.side_effect = [
            _completion(_assessment("Initial opinion.")),
            _completion("not json"),
        ]
        images = prepare_fracture_images([_png()])

        with patch("llm.fracture_analysis.OpenAI", return_value=client):
            result, method, open_model = analyse_fracture_images(images)

        self.assertEqual(method, "frontier_multiview_single_pass_fallback")
        self.assertEqual(result.summary, "Initial opinion.")
        self.assertIsNone(open_model)
        self.assertIn("second-pass visual critique was unavailable", result.limitations[-1])

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
