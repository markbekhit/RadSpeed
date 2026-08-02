"""Safety and request-contract coverage for live fracture review."""

from __future__ import annotations

import io
import json
from types import SimpleNamespace
import unittest
from unittest.mock import MagicMock, patch

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


def _assessment(summary: str = "Possible subtle fracture.") -> str:
    return json.dumps(
        {
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
            result, method = analyse_fracture_images(
                images, clinical_context="synthetic trauma context"
            )

        self.assertEqual(method, "frontier_multiview_with_visual_critic")
        self.assertEqual(result.summary, "Critic-confirmed opinion.")
        self.assertEqual(client.chat.completions.create.call_count, 2)
        second_request = client.chat.completions.create.call_args_list[1].kwargs
        second_content = second_request["messages"][1]["content"]
        self.assertIn("fresh second reader", second_content[0]["text"])
        self.assertTrue(
            any(item.get("type") == "image_url" for item in second_content)
        )

    def test_chest_mode_adds_two_hemithorax_zooms_per_view(self):
        client = MagicMock()
        client.chat.completions.create.side_effect = [
            _completion(_assessment("Initial chest opinion.")),
            _completion(_assessment("Critic-confirmed chest opinion.")),
        ]
        images = prepare_fracture_images([_png(width=120, height=96)])

        with patch("llm.fracture_analysis.OpenAI", return_value=client):
            _, method = analyse_fracture_images(images, study_type="chest_ribs")

        self.assertEqual(method, "frontier_chest_multiscale_with_visual_critic")
        first_content = client.chat.completions.create.call_args_list[0].kwargs[
            "messages"
        ][1]["content"]
        image_parts = [
            item for item in first_content if item.get("type") == "image_url"
        ]
        self.assertEqual(len(image_parts), 3)
        self.assertIn("Search each rib sequentially", first_content[0]["text"])
        self.assertTrue(
            any("Supplemental displayed left" in item.get("text", "") for item in first_content)
        )

    def test_chest_mode_includes_open_classifier_as_fallible_context(self):
        client = MagicMock()
        client.chat.completions.create.side_effect = [
            _completion(_assessment()),
            _completion(_assessment()),
        ]
        images = prepare_fracture_images([_png()])

        with patch("llm.fracture_analysis.OpenAI", return_value=client):
            analyse_fracture_images(
                images,
                study_type="chest_ribs",
                open_model_probability=0.37,
            )

        prompt = client.chat.completions.create.call_args_list[0].kwargs["messages"][1][
            "content"
        ][0]["text"]
        self.assertIn("37.0% fracture probability", prompt)
        self.assertIn("fallible supporting evidence", prompt)

    def test_rejects_unknown_study_type(self):
        with self.assertRaises(FractureImageError):
            analyse_fracture_images(
                prepare_fracture_images([_png()]), study_type="unsupported"
            )

    def test_returns_initial_read_if_critic_response_is_malformed(self):
        client = MagicMock()
        client.chat.completions.create.side_effect = [
            _completion(_assessment("Initial opinion.")),
            _completion("not json"),
        ]
        images = prepare_fracture_images([_png()])

        with patch("llm.fracture_analysis.OpenAI", return_value=client):
            result, method = analyse_fracture_images(images)

        self.assertEqual(method, "frontier_multiview_single_pass_fallback")
        self.assertEqual(result.summary, "Initial opinion.")
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
