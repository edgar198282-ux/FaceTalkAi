# ABAJ CINEMA 24/7

Independent live HLS channel for ABAJ TV. Does not modify the existing IPTV, KinoPub, APK or Railway service.

## Architecture

`authorized MP4/MKV -> prepare.py (H.264/AAC MPEG-TS) -> /data/cinema24/prepared/*.ts -> looping FFmpeg concat -> rolling HLS -> /live/index.m3u8 -> /cinema.m3u -> ABAJ TV`

One FFmpeg process serves all viewers. Playback always starts at the *current* live position, not the beginning of a film. HLS has around 30–60 seconds latency by design. Media must be owned or licensed for public broadcasting. This service does **not** fetch KinoPub/private/copyrighted sources or bypass DRM.

## Quick start

Requires Python 3.12+, FFmpeg+FFprobe, and `pip install -r requirements.txt`.

```bash
export DATA_DIR="$PWD/data"
export PUBLIC_BASE_URL="http://localhost:8080"
export CINEMA_ADMIN_TOKEN="$(python -c 'import secrets; print(secrets.token_urlsafe(32))')"
python prepare.py /path/to/licensed-film-1.mp4 --id film-1 --title "Фильм 1" --data-dir "$DATA_DIR"
python prepare.py /path/to/licensed-film-2.mp4 --id film-2 --title "Фильм 2" --data-dir "$DATA_DIR"
python server.py
```

Open `http://localhost:8080/health`. After a segment appears, playback is available at `http://localhost:8080/live/index.m3u8`; feed `http://localhost:8080/cinema.m3u` into ABAJ TV's existing custom M3U playlist flow. The admin token is required only for management; **do not put it into an M3U link**.

## Reordering and reloading

```bash
curl -X PUT http://localhost:8080/admin/playlist \
  -H "Authorization: Bearer $CINEMA_ADMIN_TOKEN" \
  -H 'Content-Type: application/json' \
  --data '{"playlist":["film-2","film-1"]}'

curl -X POST http://localhost:8080/admin/reload \
  -H "Authorization: Bearer $CINEMA_ADMIN_TOKEN"
```

`prepare.py` appends new films to the saved queue, but the running FFmpeg must be reloaded before it plays them. Reordering also restarts the muxer and can briefly interrupt viewers. Removing a film from the queue leaves its prepared file intact. **Never run more than one replica against the same HLS directory.** Persist `/data/cinema24` on a Railway Volume. Keep prepared films outside GitHub.

## Railway (separate service)

Create a **new** service from this repository, configure root directory `/services/cinema24` (after merging the feature branch), use its `Dockerfile`, mount a persistent Volume at `/data/cinema24`, set `CINEMA_ADMIN_TOKEN` (min 24 random characters) and `PUBLIC_BASE_URL` to the new service's HTTPS domain, expose `$PORT` (default 8080), and use only **one instance**. Set at least 1GB RAM, and more if preparing media inside the instance. Do not replace the existing ABAJ TV Railway service or its deploy configuration. Attach custom M3U `https://<cinema-service-domain>/cinema.m3u` to the existing ABAJ TV playlist manager.

The entrypoint creates and assigns the storage directories to the non-root worker (UID 10001). Upload media with read permissions for that worker.

## Limits

- Simple single-channel/single-worker MVP, no EPG or public admin UI yet.
- On a reboot the HLS stream restarts and clients may need to reconnect.
- Reencoding takes storage (typically ~1GB per hour at the default bitrate), and bandwidth scales linearly with viewers. Put a CDN in front for large audiences.
- Uploading films is deliberately not exposed as an unauthenticated web endpoint.
- External storage/CDN, access control for pay-TV, loudness normalization and seamless playlist edits can be added later.
