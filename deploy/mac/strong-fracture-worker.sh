#!/bin/zsh
set -euo pipefail

export PATH="/usr/bin:/bin:/usr/sbin:/sbin"
export AWS_ACCESS_KEY_ID="$(/usr/bin/security find-generic-password -a radspeed-mac-fracture-worker -s radspeed-strong-worker-access-key -w)"
export AWS_SECRET_ACCESS_KEY="$(/usr/bin/security find-generic-password -a radspeed-mac-fracture-worker -s radspeed-strong-worker-secret-key -w)"
export AWS_REGION="ap-southeast-2"
export HF_HUB_OFFLINE="1"
export TRANSFORMERS_OFFLINE="1"

: "${RADSPEED_STRONG_MODEL_BUCKET:?Missing worker bucket}"
: "${RADSPEED_STRONG_MODEL_QUEUE_URL:?Missing worker queue}"
: "${RADSPEED_STRONG_MODEL_CLASSIFIER_DIR:?Missing classifier directory}"
: "${RADSPEED_WORKER_PYTHON:?Missing worker Python}"
: "${RADSPEED_REPOSITORY:?Missing RadSpeed repository}"

cd "$RADSPEED_REPOSITORY"
exec "$RADSPEED_WORKER_PYTHON" -m llm.strong_fracture_worker
