#!/usr/bin/env bash
set -euo pipefail

benchmark_root="${1:?benchmark repository path is required}"
output_path="${2:?output path is required}"
siglip_snapshot="${HOME}/.cache/huggingface/hub/models--google--siglip-base-patch16-384/snapshots/41aec1c83b32e0a6fca20ad88ba058aa5b5ea394"
medsiglip_snapshot="${HOME}/.cache/huggingface/hub/models--google--medsiglip-448/snapshots/9cea28a1a1195f665105faa6e8544c112fd960a4"

for required in \
  "$siglip_snapshot/model.safetensors" \
  "$medsiglip_snapshot/model.safetensors" \
  "$benchmark_root/data/models/siglip_tiled_classifier.joblib" \
  "$benchmark_root/data/models/medsiglip_tiled_classifier.joblib" \
  "$benchmark_root/data/models/two_encoder_tiled_ensemble.joblib"; do
  test -r "$required" || { echo "Missing model input: $required" >&2; exit 1; }
done

staging="$(mktemp -d)"
trap 'rm -rf "$staging"' EXIT
mkdir -p "$staging/siglip-base-patch16-384" "$staging/medsiglip-448"
cp -L "$siglip_snapshot/config.json" "$siglip_snapshot/model.safetensors" \
  "$siglip_snapshot/preprocessor_config.json" "$staging/siglip-base-patch16-384/"
cp -L "$medsiglip_snapshot/config.json" "$medsiglip_snapshot/model.safetensors" \
  "$medsiglip_snapshot/preprocessor_config.json" "$staging/medsiglip-448/"
cp "$benchmark_root/data/models/siglip_tiled_classifier.joblib" \
  "$benchmark_root/data/models/medsiglip_tiled_classifier.joblib" \
  "$benchmark_root/data/models/two_encoder_tiled_ensemble.joblib" "$staging/"
tar -C "$staging" -czf "$output_path" .
