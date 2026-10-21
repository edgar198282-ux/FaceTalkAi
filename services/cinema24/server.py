import asyncio
import hmac
import logging
import os
import re
import shutil
import signal
import time
from pathlib import Path

from aiohttp import web

from core import build_concat, load_state, m3u, save_state, verify_id

LOG = logging.getLogger("cinema24")
SEGMENT_RE = re.compile(r"^seg_[0-9]+\.ts$")


class Cinema:
    def __init__(self, root: Path, admin_token: str, public_url: str):
        self.root = root
        self.admin_token = admin_token
        self.public_url = public_url.rstrip("/")
        self.stream = root / "live"
        self.process = None
        self.task = None
        self.lock = asyncio.Lock()
        self.started_at = None
        self.error = None
        self.launches = 0

    def state(self):
        return load_state(self.root)

    async def _stop(self):
        proc = self.process
        self.process = None
        if proc and proc.returncode is None:
            try:
                os.killpg(proc.pid, signal.SIGTERM)
            except ProcessLookupError:
                pass
            try:
                await asyncio.wait_for(proc.wait(), 8)
            except asyncio.TimeoutError:
                os.killpg(proc.pid, signal.SIGKILL)
                await proc.wait()
        elif proc:
            await proc.wait()

    async def _launch(self):
        self.stream.mkdir(parents=True, exist_ok=True)
        for old in self.stream.glob("seg_*.ts"):
            old.unlink(missing_ok=True)
        (self.stream / "index.m3u8").unlink(missing_ok=True)
        try:
            playlist = build_concat(self.root, self.state())
        except (ValueError, OSError) as exc:
            self.error = str(exc)
            LOG.warning("Stream not started: %s", exc)
            return
        list_path = self.root / "active.ffconcat"
        list_path.write_text(playlist, encoding="utf-8")
        cmd = [
            "ffmpeg", "-hide_banner", "-loglevel", "warning", "-nostdin", "-re",
            "-stream_loop", "-1", "-f", "concat", "-safe", "0", "-i", str(list_path),
            "-map", "0:v:0", "-map", "0:a:0", "-c", "copy", "-f", "hls",
            "-hls_time", "6", "-hls_list_size", "10", "-hls_delete_threshold", "4",
            "-hls_start_number_source", "epoch", "-hls_flags", "delete_segments+independent_segments+program_date_time+omit_endlist+temp_file",
            "-hls_segment_filename", str(self.stream / "seg_%d.ts"),
            str(self.stream / "index.m3u8"),
        ]
        self.process = await asyncio.create_subprocess_exec(*cmd, start_new_session=True)
        self.launches += 1
        self.started_at = time.time()
        self.error = None
        LOG.info("Cinema 24/7 FFmpeg started pid=%s", self.process.pid)

    async def restart(self):
        async with self.lock:
            await self._stop()
            await self._launch()

    async def run(self):
        await self.restart()
        while True:
            await asyncio.sleep(3)
            if self.process and self.process.returncode is not None:
                self.error = f"FFmpeg exited with code {self.process.returncode}"
                LOG.warning("%s; restarting", self.error)
                await asyncio.sleep(3)
                await self.restart()

    async def close(self):
        if self.task:
            self.task.cancel()
            await asyncio.gather(self.task, return_exceptions=True)
        async with self.lock:
            await self._stop()

    def status(self):
        ready = self.process is not None and self.process.returncode is None and (self.stream / "index.m3u8").is_file()
        return {
            "service": "ABAJ CINEMA 24/7",
            "ready": ready,
            "running": self.process is not None and self.process.returncode is None,
            "movies": len(self.state()["movies"]),
            "playlist": self.state()["playlist"],
            "launches": self.launches,
            "uptime_seconds": int(time.time() - self.started_at) if self.started_at and self.process else 0,
            "error": self.error,
        }


def require_admin(request):
    expected = request.app["cinema"].admin_token
    authorization = request.headers.get("Authorization", "")
    token = authorization[len("Bearer "):] if authorization.startswith("Bearer ") else ""
    if not token or not hmac.compare_digest(token, expected):
        raise web.HTTPUnauthorized(headers={"WWW-Authenticate": "Bearer"})


def cors_response(text, content_type, cache="no-store"):
    return web.Response(
        text=text, content_type=content_type,
        headers={"Access-Control-Allow-Origin": "*", "Cache-Control": cache},
    )


async def health(request):
    cinema = request.app["cinema"]
    status = cinema.status()
    return web.json_response(status, status=200 if status["ready"] else 503)


async def iptv(request):
    cinema = request.app["cinema"]
    origin = cinema.public_url or f"{request.scheme}://{request.host}"
    return cors_response(m3u(origin), "audio/x-mpegurl")


async def manifest(request):
    path = request.app["cinema"].stream / "index.m3u8"
    if not path.is_file():
        raise web.HTTPServiceUnavailable(text="Live stream is starting or no films have been added")
    return cors_response(path.read_text(encoding="utf-8"), "application/vnd.apple.mpegurl")


async def segment(request):
    name = request.match_info["name"]
    if not SEGMENT_RE.fullmatch(name):
        raise web.HTTPNotFound()
    path = request.app["cinema"].stream / name
    if not path.is_file():
        raise web.HTTPNotFound()
    return web.FileResponse(path, headers={"Access-Control-Allow-Origin": "*", "Cache-Control": "public, max-age=60", "Content-Type": "video/mp2t"})


async def admin_movies(request):
    require_admin(request)
    return web.json_response(request.app["cinema"].state())


async def admin_playlist(request):
    require_admin(request)
    cinema = request.app["cinema"]
    try:
        data = await request.json()
        if not isinstance(data, dict) or not isinstance(data.get("playlist"), list):
            raise ValueError("Expected JSON: {\"playlist\": [\"movie-id\", ...]}")
        order = data["playlist"]
        if len(order) != len(set(order)):
            raise ValueError("Playlist contains duplicate IDs")
        for movie_id in order:
            verify_id(movie_id)
        async with cinema.lock:
            state = cinema.state()
            for movie_id in order:
                if movie_id not in state["movies"]:
                    raise ValueError(f"Unknown movie ID: {movie_id}")
                filename = cinema.root / "prepared" / f"{movie_id}.ts"
                if not filename.is_file():
                    raise ValueError(f"Missing prepared file for {movie_id}")
            state["playlist"] = order
            save_state(cinema.root, state)
            await cinema._stop()
            await cinema._launch()
        return web.json_response({"ok": True, "playlist": order, "ready": cinema.status()["ready"]})
    except (ValueError, TypeError) as exc:
        raise web.HTTPBadRequest(text=str(exc)) from exc


async def admin_reload(request):
    require_admin(request)
    cinema = request.app["cinema"]
    await cinema.restart()
    return web.json_response({"ok": True, "status": cinema.status()})


async def service_lifecycle(app):
    cinema = app["cinema"]
    cinema.root.mkdir(parents=True, exist_ok=True)
    cinema.task = asyncio.create_task(cinema.run())
    yield
    await cinema.close()


def create_app(root=None, admin_token=None, public_url=None):
    root = Path(root or os.getenv("DATA_DIR", "/data/cinema24")).resolve()
    token = admin_token if admin_token is not None else os.getenv("CINEMA_ADMIN_TOKEN", "")
    if len(token) < 24:
        raise RuntimeError("CINEMA_ADMIN_TOKEN must contain at least 24 characters")
    app = web.Application(client_max_size=64 * 1024)
    app["cinema"] = Cinema(root, token, public_url if public_url is not None else os.getenv("PUBLIC_BASE_URL", ""))
    app.router.add_get("/health", health)
    app.router.add_get("/cinema.m3u", iptv)
    app.router.add_get("/live/index.m3u8", manifest)
    app.router.add_get("/live/{name}", segment)
    app.router.add_get("/admin/movies", admin_movies)
    app.router.add_put("/admin/playlist", admin_playlist)
    app.router.add_post("/admin/reload", admin_reload)
    app.cleanup_ctx.append(service_lifecycle)
    return app


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    web.run_app(create_app(), host="0.0.0.0", port=int(os.getenv("PORT", "8080")))
