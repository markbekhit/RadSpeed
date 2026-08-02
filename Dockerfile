FROM python:3.11-slim

# tkinter is a system package required transitively by ui.utils and utils.encryption.
# ffmpeg is optional but enables broader audio format support via soundfile.
RUN apt-get update && apt-get install -y --no-install-recommends \
        python3-tk \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

# Install Python dependencies before copying app code so layer is cached.
COPY requirements-web.txt .
RUN pip install --no-cache-dir -r requirements-web.txt

# Copy application source.
COPY . .

# Pin the public open-model artifact by content hash so the private app always
# runs the exact chest classifier that was evaluated before deployment.
ADD --checksum=sha256:02a46abdc14bcf8f234c098d821a17a09002668e1149b46c4a1f9150ef3f54c0 \
    https://github.com/markbekhit/RadSpeed/releases/download/chest-fracture-model-v1/kad512_chest_float.onnx \
    /app/models/kad512_chest_float.onnx

# Broad detector is used only to create ranked zoom proposals for the fresh
# frontier read. Its raw scores are never displayed as fracture probabilities.
ADD --checksum=sha256:e61a9097343cd0efc57552c6e031a70de39cd88767d053d382c0da26e944d5ec \
    https://github.com/markbekhit/RadSpeed/releases/download/fracture-locator-v1/rtdetr_fracatlas_full.onnx \
    /app/models/rtdetr_fracatlas_full.onnx

# /data/working  — templates, guidelines, reports (bind-mount or named volume)
# /root/.voxrad  — encrypted API keys + settings.ini (named volume)
VOLUME ["/data/working", "/root/.voxrad"]

ENV VOXRAD_WEB_PASSWORD=voxrad \
    VOXRAD_WORKING_DIR=/data/working

EXPOSE 8765

HEALTHCHECK --interval=30s --timeout=5s --start-period=10s --retries=3 \
    CMD python -c "import urllib.request, sys; urllib.request.urlopen('http://localhost:8765/health', timeout=4); sys.exit(0)"

CMD ["python", "RadSpeed.py", "--web", "--host", "0.0.0.0", "--port", "8765"]
