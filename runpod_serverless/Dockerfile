FROM nvidia/cuda:12.1.1-cudnn8-runtime-ubuntu22.04
ENV DEBIAN_FRONTEND=noninteractive PIP_NO_CACHE_DIR=1 PYTHONUNBUFFERED=1
RUN apt-get update && apt-get install -y --no-install-recommends python3.10 python3-pip python3-dev git ffmpeg wget ca-certificates build-essential && rm -rf /var/lib/apt/lists/*
RUN python3 -m pip install --upgrade pip && pip install runpod
WORKDIR /workspace
RUN git clone --depth 1 https://github.com/TMElyralab/MuseTalk.git
WORKDIR /workspace/MuseTalk
RUN pip install -r requirements.txt
RUN pip install -U huggingface_hub
RUN bash download_weights.sh
WORKDIR /workspace
COPY runpod_serverless/handler.py /workspace/handler.py
CMD ["python3","-u","/workspace/handler.py"]
