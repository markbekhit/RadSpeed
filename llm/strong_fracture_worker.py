"""Outbound-only SQS worker that runs strong fracture inference on this Mac."""

from __future__ import annotations

import json
import logging
import os
import signal
import threading
import time
from typing import Any

HEARTBEAT_KEY = "worker-status/default.json"


logger = logging.getLogger("radspeed.strong_fracture_worker")
_stop = threading.Event()


def _settings() -> tuple[str, str, str, str]:
    bucket = os.environ["RADSPEED_STRONG_MODEL_BUCKET"].strip()
    queue_url = os.environ["RADSPEED_STRONG_MODEL_QUEUE_URL"].strip()
    classifier_dir = os.environ["RADSPEED_STRONG_MODEL_CLASSIFIER_DIR"].strip()
    region = os.environ.get("AWS_REGION", "ap-southeast-2").strip()
    return bucket, queue_url, classifier_dir, region


def _heartbeat_loop(s3: Any, bucket: str) -> None:
    while not _stop.is_set():
        try:
            body = json.dumps(
                {"status": "ready", "updated_at_epoch": time.time()},
                separators=(",", ":"),
            ).encode()
            s3.put_object(
                Bucket=bucket,
                Key=HEARTBEAT_KEY,
                Body=body,
                ContentType="application/json",
                ServerSideEncryption="AES256",
            )
        except Exception as exc:
            logger.warning("Worker heartbeat failed (%s)", type(exc).__name__)
        _stop.wait(15)


def _valid_job(job: dict[str, Any], now: float) -> bool:
    job_id = job.get("job_id")
    input_key = job.get("input_key")
    result_key = job.get("result_key")
    expires_at = job.get("expires_at_epoch")
    return (
        job.get("version") == 1
        and isinstance(job_id, str)
        and len(job_id) == 32
        and input_key == f"jobs/{job_id}/input.json"
        and result_key == f"results/{job_id}.json"
        and isinstance(expires_at, (int, float))
        and now <= float(expires_at)
    )


def _write_result(s3: Any, bucket: str, key: str, result: dict[str, Any]) -> None:
    s3.put_object(
        Bucket=bucket,
        Key=key,
        Body=json.dumps(result, separators=(",", ":")).encode(),
        ContentType="application/json",
        ServerSideEncryption="AES256",
    )


def run() -> None:
    import boto3
    from llm.strong_fracture_inference import decode_images, load_model, predict

    bucket, queue_url, classifier_dir, region = _settings()
    s3 = boto3.client("s3", region_name=region)
    sqs = boto3.client("sqs", region_name=region)
    logger.info("Loading the two strong fracture encoders")
    model = load_model(classifier_dir)
    logger.info("Strong fracture worker ready on %s", model.device)

    heartbeat = threading.Thread(
        target=_heartbeat_loop, args=(s3, bucket), daemon=True
    )
    heartbeat.start()
    while not _stop.is_set():
        response = sqs.receive_message(
            QueueUrl=queue_url,
            MaxNumberOfMessages=1,
            WaitTimeSeconds=20,
            VisibilityTimeout=300,
        )
        for message in response.get("Messages", []):
            receipt = message["ReceiptHandle"]
            input_key: str | None = None
            result_key: str | None = None
            try:
                job = json.loads(message["Body"])
                input_key = job.get("input_key")
                result_key = job.get("result_key")
                if not _valid_job(job, time.time()):
                    raise ValueError("Invalid or expired fracture job")
                payload = s3.get_object(Bucket=bucket, Key=input_key)["Body"].read()
                images = decode_images(json.loads(payload))
                _write_result(s3, bucket, result_key, predict(images, model))
                logger.info("Completed one de-identified fracture study")
            except Exception as exc:
                logger.warning("Fracture job failed (%s)", type(exc).__name__)
                if result_key and result_key.startswith("results/"):
                    try:
                        _write_result(s3, bucket, result_key, {"error": "processing_failed"})
                    except Exception:
                        pass
            finally:
                if input_key and input_key.startswith("jobs/"):
                    try:
                        s3.delete_object(Bucket=bucket, Key=input_key)
                    except Exception:
                        pass
                sqs.delete_message(QueueUrl=queue_url, ReceiptHandle=receipt)


def main() -> None:
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
    for signum in (signal.SIGINT, signal.SIGTERM):
        signal.signal(signum, lambda *_: _stop.set())
    run()


if __name__ == "__main__":
    main()
