# FaceTalk — RunPod Serverless worker

Эта папка полностью отделена от Railway-приложения FaceTalk.

В RunPod при Deploy from GitHub укажи:
- Dockerfile path: `/runpod_serverless/Dockerfile`
- Handler/entrypoint внутри контейнера: `/workspace/handler.py`
- Active workers: `0`
- Max workers: `1`

Railway НЕ должен запускать файлы из этой папки. Railway запускает только `python main.py` через `railway.toml`.
