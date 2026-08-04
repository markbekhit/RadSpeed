ARG DLC_IMAGE=763104351884.dkr.ecr.ap-southeast-2.amazonaws.com/huggingface-pytorch-inference:2.6.0-transformers5.5.3-gpu-py312-cu124-ubuntu22.04
FROM ${DLC_IMAGE}

RUN pip install --no-cache-dir \
    "transformers==5.5.3" \
    "accelerate==1.10.0" \
    "scikit-learn==1.7.1" \
    "joblib==1.5.1" \
    "pillow==11.3.0"

COPY inference.py /opt/ml/code/inference.py
ENV SAGEMAKER_PROGRAM=inference.py \
    SAGEMAKER_SUBMIT_DIRECTORY=/opt/ml/code \
    HF_HUB_OFFLINE=1 \
    TRANSFORMERS_OFFLINE=1
