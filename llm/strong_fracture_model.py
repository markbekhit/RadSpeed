"""Ephemeral client for the private Mac-hosted strong fracture classifier."""

from __future__ import annotations

import base64
import json
import os
import time
import uuid
from typing import Any

from llm.fracture_analysis import PreparedFractureImage


HEARTBEAT_KEY = "worker-status/default.json"
HEARTBEAT_MAX_AGE_SECONDS = 45
MAX_JOB_AGE_SECONDS = 600


def _settings() -> tuple[str, str, str]:
    bucket = os.environ.get("RADSPEED_STRONG_MODEL_BUCKET", "").strip()
    queue_url = os.environ.get("RADSPEED_STRONG_MODEL_QUEUE_URL", "").strip()
    region = os.environ.get("AWS_REGION", "ap-southeast-2").strip()
    if not bucket or not queue_url:
        raise RuntimeError("The strong fracture model is not configured")
    return bucket, queue_url, region


def _worker_ready(s3: Any, bucket: str, *, now: float | None = None) -> bool:
    """Return true only for a recent ready heartbeat from the Mac worker."""
    try:
        response = s3.get_object(Bucket=bucket, Key=HEARTBEAT_KEY)
        heartbeat = json.loads(response["Body"].read())
        updated_at = float(heartbeat["updated_at_epoch"])
    except Exception:
        return False
    current = time.time() if now is None else now
    return (
        heartbeat.get("status") == "ready"
        and 0 <= current - updated_at <= HEARTBEAT_MAX_AGE_SECONDS
    )


def score_strong_fracture_images(
    images: list[PreparedFractureImage],
    *,
    timeout_seconds: int = 90,
    poll_seconds: float = 1.0,
) -> dict[str, Any]:
    """Ask the outbound-only Mac worker to score de-identified raster images."""
    import boto3
    from botocore.exceptions import ClientError

    bucket, queue_url, region = _settings()
    s3 = boto3.client("s3", region_name=region)
    if not _worker_ready(s3, bucket):
        raise RuntimeError("The local strong fracture worker is offline")

    sqs = boto3.client("sqs", region_name=region)
    identifier = uuid.uuid4().hex
    input_key = f"jobs/{identifier}/input.json"
    result_key = f"results/{identifier}.json"
    created_at = time.time()
    body = json.dumps(
        {"images": [base64.b64encode(image.data).decode("ascii") for image in images]},
        separators=(",", ":"),
    ).encode("utf-8")
    try:
        s3.put_object(
            Bucket=bucket,
            Key=input_key,
            Body=body,
            ContentType="application/json",
            ServerSideEncryption="AES256",
        )
        sqs.send_message(
            QueueUrl=queue_url,
            MessageBody=json.dumps(
                {
                    "version": 1,
                    "job_id": identifier,
                    "input_key": input_key,
                    "result_key": result_key,
                    "created_at_epoch": created_at,
                    "expires_at_epoch": created_at + MAX_JOB_AGE_SECONDS,
                },
                separators=(",", ":"),
            ),
        )

        deadline = time.monotonic() + timeout_seconds
        while time.monotonic() < deadline:
            try:
                response = s3.get_object(Bucket=bucket, Key=result_key)
                result = json.loads(response["Body"].read())
                if result.get("error"):
                    raise RuntimeError("The local strong fracture worker could not process the study")
                return result
            except ClientError as exc:
                code = exc.response.get("Error", {}).get("Code")
                if code not in {"NoSuchKey", "404"}:
                    raise
            time.sleep(poll_seconds)
        raise TimeoutError("The local strong fracture worker did not finish in time")
    finally:
        for key in (input_key, result_key):
            try:
                s3.delete_object(Bucket=bucket, Key=key)
            except Exception:
                pass
