"""Ephemeral client for the scale-to-zero SageMaker fracture classifier."""

from __future__ import annotations

import base64
import json
import os
import time
import uuid
from typing import Any
from urllib.parse import urlparse

from llm.fracture_analysis import PreparedFractureImage


def _settings() -> tuple[str, str, str]:
    endpoint = os.environ.get("RADSPEED_STRONG_MODEL_ENDPOINT", "").strip()
    bucket = os.environ.get("RADSPEED_STRONG_MODEL_BUCKET", "").strip()
    region = os.environ.get("AWS_REGION", "ap-southeast-2").strip()
    if not endpoint or not bucket:
        raise RuntimeError("The strong fracture model is not configured")
    return endpoint, bucket, region


def _s3_location(uri: str) -> tuple[str, str]:
    parsed = urlparse(uri)
    if parsed.scheme != "s3" or not parsed.netloc or not parsed.path.lstrip("/"):
        raise ValueError("SageMaker returned an invalid output location")
    return parsed.netloc, parsed.path.lstrip("/")


def score_strong_fracture_images(
    images: list[PreparedFractureImage],
    *,
    timeout_seconds: int = 720,
    poll_seconds: float = 4.0,
) -> dict[str, Any]:
    """Run the calibrated extremity classifier and delete transient S3 objects."""
    import boto3
    from botocore.exceptions import ClientError

    endpoint, bucket, region = _settings()
    identifier = uuid.uuid4().hex
    input_key = f"async-input/{identifier}.json"
    body = json.dumps(
        {"images": [base64.b64encode(image.data).decode("ascii") for image in images]},
        separators=(",", ":"),
    ).encode("utf-8")
    s3 = boto3.client("s3", region_name=region)
    runtime = boto3.client("sagemaker-runtime", region_name=region)
    cleanup: list[tuple[str, str]] = [(bucket, input_key)]
    try:
        s3.put_object(
            Bucket=bucket,
            Key=input_key,
            Body=body,
            ContentType="application/json",
            ServerSideEncryption="AES256",
        )
        response = runtime.invoke_endpoint_async(
            EndpointName=endpoint,
            InputLocation=f"s3://{bucket}/{input_key}",
            ContentType="application/json",
            Accept="application/json",
            RequestTTLSeconds=timeout_seconds,
            InvocationTimeoutSeconds=min(timeout_seconds, 3600),
            InferenceId=identifier,
        )
        output = _s3_location(response["OutputLocation"])
        cleanup.append(output)
        failure_uri = response.get("FailureLocation")
        failure = _s3_location(failure_uri) if failure_uri else None
        if failure:
            cleanup.append(failure)

        deadline = time.monotonic() + timeout_seconds
        while time.monotonic() < deadline:
            try:
                result = s3.get_object(Bucket=output[0], Key=output[1])
                return json.loads(result["Body"].read())
            except ClientError as exc:
                code = exc.response.get("Error", {}).get("Code")
                if code not in {"NoSuchKey", "404"}:
                    raise
            if failure:
                try:
                    result = s3.get_object(Bucket=failure[0], Key=failure[1])
                    result["Body"].read()
                    raise RuntimeError("The strong fracture model could not process the study")
                except ClientError as exc:
                    code = exc.response.get("Error", {}).get("Code")
                    if code not in {"NoSuchKey", "404"}:
                        raise
            time.sleep(poll_seconds)
        raise TimeoutError("The strong fracture model did not finish in time")
    finally:
        for object_bucket, key in cleanup:
            try:
                s3.delete_object(Bucket=object_bucket, Key=key)
            except Exception:
                pass
