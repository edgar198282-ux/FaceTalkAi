#!/usr/bin/env bash
set -euo pipefail
cd /workspace
if [ ! -d MuseTalk/.git ]; then git clone https://github.com/TMElyralab/MuseTalk.git; fi
cd MuseTalk
# MuseTalk official README recommends Python 3.10 / CUDA and its requirements.
pip install -r requirements.txt
pip install --no-cache-dir -U openmim
mim install mmengine
mim install "mmcv==2.0.1"
mim install "mmdet==3.1.0"
mim install "mmpose==1.1.0"
sh ./download_weights.sh

cd /workspace
if [ ! -d LivePortrait/.git ]; then git clone https://github.com/KlingTeam/LivePortrait.git; fi
cd LivePortrait
pip install -r requirements.txt
pip install -U "huggingface_hub[cli]"
huggingface-cli download KlingTeam/LivePortrait --local-dir pretrained_weights --exclude "*.git*" "README.md" "docs"

echo "Models ready. Install gpu_worker/requirements-worker.txt and start worker.py."
