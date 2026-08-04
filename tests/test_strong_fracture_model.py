"""Queue contract tests for the private Mac fracture worker."""

from __future__ import annotations

import io
import json
import os
import unittest
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

from llm.fracture_analysis import PreparedFractureImage
from llm.strong_fracture_model import _worker_ready, score_strong_fracture_images
from llm.strong_fracture_worker import _valid_job


class _MissingResult(Exception):
    def __init__(self):
        self.response = {"Error": {"Code": "NoSuchKey"}}


class StrongFractureQueueTests(unittest.TestCase):
    def test_requires_recent_ready_worker_heartbeat(self):
        s3 = MagicMock()
        s3.get_object.return_value = {
            "Body": io.BytesIO(
                json.dumps({"status": "ready", "updated_at_epoch": 100}).encode()
            )
        }
        self.assertTrue(_worker_ready(s3, "bucket", now=130))
        self.assertFalse(_worker_ready(s3, "bucket", now=146))

    def test_job_contract_rejects_expired_or_mismatched_keys(self):
        job_id = "a" * 32
        job = {
            "version": 1,
            "job_id": job_id,
            "input_key": f"jobs/{job_id}/input.json",
            "result_key": f"results/{job_id}.json",
            "expires_at_epoch": 200,
        }
        self.assertTrue(_valid_job(job, 150))
        self.assertFalse(_valid_job(job, 201))
        self.assertFalse(_valid_job({**job, "input_key": "jobs/other/input.json"}, 150))

    def test_uploads_transient_job_and_returns_worker_result(self):
        s3 = MagicMock()
        sqs = MagicMock()
        result = {
            "model": "calibrated_two_encoder_tiled_ensemble",
            "highest_view_probability": 0.73,
        }

        def get_object(*, Bucket, Key):
            if Key == "worker-status/default.json":
                return {
                    "Body": io.BytesIO(
                        json.dumps(
                            {"status": "ready", "updated_at_epoch": 1000}
                        ).encode()
                    )
                }
            if Key.startswith("results/"):
                return {"Body": io.BytesIO(json.dumps(result).encode())}
            raise AssertionError(Key)

        s3.get_object.side_effect = get_object
        boto3 = SimpleNamespace(
            client=lambda service, **_: s3 if service == "s3" else sqs
        )
        botocore_exceptions = SimpleNamespace(ClientError=_MissingResult)
        image = PreparedFractureImage(
            data=b"synthetic", mime_type="image/png", width=96, height=80
        )
        environment = {
            "RADSPEED_STRONG_MODEL_BUCKET": "private-bucket",
            "RADSPEED_STRONG_MODEL_QUEUE_URL": "https://sqs.example/queue",
            "AWS_REGION": "ap-southeast-2",
        }
        with (
            patch.dict(os.environ, environment, clear=False),
            patch.dict(
                "sys.modules",
                {
                    "boto3": boto3,
                    "botocore.exceptions": botocore_exceptions,
                },
            ),
            patch("llm.strong_fracture_model.time.time", return_value=1000),
        ):
            observed = score_strong_fracture_images([image], poll_seconds=0)

        self.assertEqual(observed, result)
        s3.put_object.assert_called_once()
        self.assertEqual(
            s3.put_object.call_args.kwargs["ServerSideEncryption"], "AES256"
        )
        sqs.send_message.assert_called_once()
        queued = json.loads(sqs.send_message.call_args.kwargs["MessageBody"])
        self.assertEqual(queued["input_key"], f"jobs/{queued['job_id']}/input.json")
        self.assertEqual(queued["result_key"], f"results/{queued['job_id']}.json")
        self.assertEqual(s3.delete_object.call_count, 2)

    def test_offline_worker_fails_before_uploading_images(self):
        s3 = MagicMock()
        s3.get_object.side_effect = RuntimeError("not found")
        sqs = MagicMock()
        boto3 = SimpleNamespace(
            client=lambda service, **_: s3 if service == "s3" else sqs
        )
        botocore_exceptions = SimpleNamespace(ClientError=_MissingResult)
        environment = {
            "RADSPEED_STRONG_MODEL_BUCKET": "private-bucket",
            "RADSPEED_STRONG_MODEL_QUEUE_URL": "https://sqs.example/queue",
        }
        with (
            patch.dict(os.environ, environment, clear=False),
            patch.dict(
                "sys.modules",
                {
                    "boto3": boto3,
                    "botocore.exceptions": botocore_exceptions,
                },
            ),
        ):
            with self.assertRaisesRegex(RuntimeError, "offline"):
                score_strong_fracture_images(
                    [
                        PreparedFractureImage(
                            data=b"synthetic",
                            mime_type="image/png",
                            width=96,
                            height=80,
                        )
                    ]
                )

        s3.put_object.assert_not_called()
        sqs.send_message.assert_not_called()


if __name__ == "__main__":
    unittest.main()
