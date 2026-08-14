# FaceTalk GPU Worker — следующий шаг

Этот каталог превращает официальный MuseTalk 1.5 + LivePortrait в HTTP worker, который уже понимает FaceTalk v3.4.x.

## Что реально происходит

- `/facetalk`: фото + готовое аудио -> MP4.
- MuseTalk 1.5 делает lip-sync. Официальный MuseTalk допускает `video_path` как видео **или изображение**, поэтому worker работает даже без driving-video.
- LivePortrait включается дополнительно, когда задан `LIVEPORTRAIT_DRIVING_VIDEO`: сначала добавляет движения головы/мимику по нейтральному driving-клипу, затем MuseTalk синхронизирует рот.
- `/health`: проверяет, установлены ли репозитории/веса.
- Один job одновременно, чтобы несколько запросов не убили VRAM.

## Вариант A — отдельный Linux GPU сервер / RunPod

1. Нужен NVIDIA GPU и Python 3.10. MuseTalk официально рекомендует CUDA 11.7/11.8; LivePortrait поддерживает актуальные CUDA-сборки PyTorch.
2. Скопируй папку `gpu_worker` на сервер в `/workspace/gpu_worker`.
3. Запусти:

```bash
cd /workspace/gpu_worker
bash setup_models.sh
pip install -r requirements-worker.txt
export GPU_WORKER_TOKEN='придумай-длинный-секрет'
# Необязательно: включить LivePortrait с нейтральным driving-video:
# export LIVEPORTRAIT_DRIVING_VIDEO=/workspace/driving/neutral.mp4
bash start_worker.sh
```

4. Открой наружу порт `8000` через HTTPS. Проверка: `GET https://ТВОЙ-ДОМЕН/health`.
5. В FaceTalk Mini App -> Админ -> API ключи:
   - `MuseTalk URL` = `https://ТВОЙ-ДОМЕН`
   - `LivePortrait URL` можно оставить пустым, потому что этот worker комбинированный.
   - `GPU Worker Token` = тот же секрет.
   - `Видео движок` = `Только LivePortrait + MuseTalk` (никаких расходов D-ID) или `Auto` (D-ID запасной).
6. Нажми новую кнопку `Проверить GPU worker`.

## Вариант B — свой компьютер с NVIDIA

Можно запустить worker на своём GPU-компьютере и дать Railway HTTPS URL через Cloudflare Tunnel/ngrok. Модели бесплатные; платить придётся только за электричество/сам сервер. Не открывай worker без `GPU_WORKER_TOKEN`.

## Driving-video для LivePortrait

LivePortrait — video-driven модель: ей нужен нейтральный driving ролик или motion-template. Лучше 1:1, лицо фронтально в первом кадре, минимум движения плеч. Без driving-video FaceTalk не ломается: worker сразу передаёт фото в MuseTalk, что быстрее, но движения головы будут скромнее.

## Производительность

MuseTalk сообщает 30+ FPS на Tesla V100 в real-time pipeline, но обычный `normal` режим этого worker сначала ориентирован на надёжность. Следующая оптимизация — кэшировать подготовленного аватара и держать модели в памяти через realtime inference, чтобы повторные ответы одного человека генерировались заметно быстрее.
