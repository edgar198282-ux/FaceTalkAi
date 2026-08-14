"""RunPod Serverless discovery entrypoint.
The production Docker image starts handler.py; this file also exposes the canonical
RunPod startup signature so repository-based deployment discovery can detect it.
"""
from handler import handler
import runpod

runpod.serverless.start({"handler": handler})
