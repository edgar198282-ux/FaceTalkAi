# FaceTalk — RunPod Serverless

RunPod должен видеть в корне репозитория `Dockerfile` и `handler.py`.

1. Загрузите содержимое этой папки проекта в корень GitHub репозитория FaceTalkAi.
2. В RunPod выберите FaceTalkAi, branch main, Dockerfile path `/Dockerfile`, Queue.
3. Первый build будет долгим: Docker скачивает MuseTalk и его веса.
4. Для экономии: Active workers = 0, Max workers = 1.
5. После создания endpoint скопируйте Endpoint ID и создайте RunPod API key.
6. В админке FaceTalk заполните RUNPOD_ENDPOINT_ID и RUNPOD_API_KEY и выберите AVATAR_ENGINE=runpod (поддержка добавлена в v3.4.2).

Важно: Serverless queue принимает JSON. FaceTalk отправляет фото/аудио base64. Для очень длинных ответов позднее лучше перейти на объектное хранилище, чтобы не упереться в лимит payload.
