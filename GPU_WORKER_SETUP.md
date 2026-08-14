# FaceTalk free video engine (LivePortrait + MuseTalk)

The Telegram/Railway app now supports a self-hosted GPU video path before D-ID.
Heavy CUDA models should **not** be installed in the main Railway web service. Run them on a GPU host and paste the URLs in **Admin → API keys**.

## Admin fields

- `Видео движок = Auto` — tries LivePortrait + MuseTalk first, then D-ID as fallback.
- `Видео движок = Только LivePortrait + MuseTalk` — never spends D-ID credits.
- `LivePortrait URL` — base URL of a LivePortrait worker (optional when MuseTalk worker has combined `/facetalk`).
- `MuseTalk URL` — base URL of the MuseTalk/combined worker.
- `GPU Worker Token` — optional bearer token shared with the GPU worker.

## HTTP contract expected by FaceTalk

Preferred combined endpoint:

`POST {MUSETALK_URL}/facetalk` as multipart/form-data:
- `image`: JPEG/PNG portrait
- `audio`: final speech audio
- `liveportrait_url`: optional helper URL

Return either raw `video/mp4` or JSON:
`{"result_url":"https://.../result.mp4"}`

Compatibility two-step endpoints:

1. `POST {LIVEPORTRAIT_URL}/animate` with `image` -> MP4 idle/animated portrait.
2. `POST {MUSETALK_URL}/lipsync` with `source_video` + `audio` -> final MP4.

MuseTalk-only workers may also accept `image` + `audio` at `/lipsync`.

If `GPU_WORKER_TOKEN` is set, FaceTalk sends `Authorization: Bearer <token>`.

## Recommended deployment

Use the official LivePortrait and MuseTalk repositories on a CUDA GPU machine/container. Wrap their inference commands with a small FastAPI service implementing the contract above. Keep model weights on the GPU host volume so they are downloaded once.

The main FaceTalk bot remains on Railway and only uploads the selected person's photo and generated audio to that worker.
