import asyncio
import glob
import os
import shutil
import subprocess
import tempfile
import time
from pathlib import Path

from fastapi import FastAPI, File, Form, Header, HTTPException, UploadFile
from fastapi.responses import FileResponse, JSONResponse

APP = FastAPI(title="FaceTalk GPU Worker", version="1.0")
TOKEN = os.getenv("GPU_WORKER_TOKEN", "").strip()
MUSETALK_DIR = Path(os.getenv("MUSETALK_DIR", "/workspace/MuseTalk"))
LIVEPORTRAIT_DIR = Path(os.getenv("LIVEPORTRAIT_DIR", "/workspace/LivePortrait"))
DRIVING_VIDEO = os.getenv("LIVEPORTRAIT_DRIVING_VIDEO", "").strip()
FFMPEG_PATH = os.getenv("FFMPEG_PATH", "").strip()
WORK_DIR = Path(os.getenv("FACETALK_WORK_DIR", "/workspace/facetalk_jobs"))
WORK_DIR.mkdir(parents=True, exist_ok=True)
LOCK = asyncio.Lock()  # one GPU job at a time; avoids VRAM collisions


def _auth(authorization: str | None):
    if not TOKEN:
        return
    if authorization != f"Bearer {TOKEN}":
        raise HTTPException(status_code=401, detail="bad worker token")


def _run(cmd, cwd: Path, timeout: int = 900):
    env = os.environ.copy()
    if FFMPEG_PATH:
        env["PATH"] = FFMPEG_PATH + os.pathsep + env.get("PATH", "")
    p = subprocess.run(cmd, cwd=str(cwd), env=env, stdout=subprocess.PIPE,
                       stderr=subprocess.STDOUT, text=True, timeout=timeout)
    if p.returncode != 0:
        tail = p.stdout[-6000:]
        raise RuntimeError(f"command failed ({p.returncode})\n{tail}")
    return p.stdout


def _newest_mp4(folder: Path, since: float):
    files = [Path(p) for p in glob.glob(str(folder / "**" / "*.mp4"), recursive=True)]
    files = [p for p in files if p.exists() and p.stat().st_mtime >= since - 2]
    if not files:
        return None
    # Prefer final MuseTalk result over temp files.
    files.sort(key=lambda p: ("temp" in p.name.lower(), -p.stat().st_mtime))
    return files[0]


def _save_upload(upload: UploadFile, dst: Path):
    with dst.open("wb") as f:
        shutil.copyfileobj(upload.file, f)


def _musetalk(source: Path, audio: Path, job: Path) -> Path:
    if not (MUSETALK_DIR / "scripts" / "inference.py").exists():
        raise RuntimeError(f"MuseTalk not installed in {MUSETALK_DIR}")
    result_dir = job / "musetalk_result"
    result_dir.mkdir(exist_ok=True)
    cfg = job / "musetalk.yaml"
    # MuseTalk official normal inference accepts image or video in video_path.
    cfg.write_text(
        "task_0:\n"
        f"  video_path: \"{source.as_posix()}\"\n"
        f"  audio_path: \"{audio.as_posix()}\"\n",
        encoding="utf-8",
    )
    cmd = [
        "python", "-m", "scripts.inference",
        "--inference_config", str(cfg),
        "--result_dir", str(result_dir),
        "--unet_model_path", "models/musetalkV15/unet.pth",
        "--unet_config", "models/musetalkV15/musetalk.json",
        "--version", "v15",
    ]
    if FFMPEG_PATH:
        cmd += ["--ffmpeg_path", FFMPEG_PATH]
    started = time.time()
    _run(cmd, MUSETALK_DIR, int(os.getenv("MUSETALK_TIMEOUT", "1200")))
    out = _newest_mp4(result_dir, started)
    if not out:
        # Some repo versions write under the repository's default results dir.
        out = _newest_mp4(MUSETALK_DIR / "results", started)
    if not out:
        raise RuntimeError("MuseTalk finished but no mp4 result was found")
    final = job / "result.mp4"
    shutil.copy2(out, final)
    return final


def _liveportrait(image: Path, job: Path) -> Path:
    """Optional head/mimic animation before MuseTalk.

    LivePortrait is video-driven. Set LIVEPORTRAIT_DRIVING_VIDEO to a neutral
    1:1 head-motion clip (or .pkl motion template). Without it, FaceTalk uses
    MuseTalk directly on the still image, which is valid and faster.
    """
    if not DRIVING_VIDEO:
        return image
    if not (LIVEPORTRAIT_DIR / "inference.py").exists():
        raise RuntimeError(f"LivePortrait not installed in {LIVEPORTRAIT_DIR}")
    drv = Path(DRIVING_VIDEO)
    if not drv.exists():
        raise RuntimeError(f"LIVEPORTRAIT_DRIVING_VIDEO not found: {drv}")
    anim_dir = LIVEPORTRAIT_DIR / "animations"
    anim_dir.mkdir(exist_ok=True)
    started = time.time()
    cmd = ["python", "inference.py", "-s", str(image), "-d", str(drv), "--flag_crop_driving_video"]
    _run(cmd, LIVEPORTRAIT_DIR, int(os.getenv("LIVEPORTRAIT_TIMEOUT", "600")))
    candidates = [p for p in anim_dir.glob("*.mp4") if p.stat().st_mtime >= started - 2]
    # Avoid the *_concat preview if a clean output is available.
    clean = [p for p in candidates if "concat" not in p.name.lower()]
    candidates = clean or candidates
    if not candidates:
        raise RuntimeError("LivePortrait finished but no mp4 result was found")
    out = max(candidates, key=lambda p: p.stat().st_mtime)
    final = job / "liveportrait.mp4"
    shutil.copy2(out, final)
    return final


@APP.get("/health")
def health():
    return {
        "ok": True,
        "musetalk_installed": (MUSETALK_DIR / "scripts" / "inference.py").exists(),
        "musetalk_models": (MUSETALK_DIR / "models" / "musetalkV15" / "unet.pth").exists(),
        "liveportrait_installed": (LIVEPORTRAIT_DIR / "inference.py").exists(),
        "liveportrait_enabled": bool(DRIVING_VIDEO),
        "gpu_token_enabled": bool(TOKEN),
    }


async def _process(image: UploadFile | None, source_video: UploadFile | None,
                   audio: UploadFile, authorization: str | None):
    _auth(authorization)
    if image is None and source_video is None:
        raise HTTPException(status_code=400, detail="image or source_video required")
    async with LOCK:
        job = Path(tempfile.mkdtemp(prefix="facetalk_", dir=str(WORK_DIR)))
        try:
            audio_suffix = Path(audio.filename or "speech.mp3").suffix or ".mp3"
            ap = job / ("audio" + audio_suffix)
            _save_upload(audio, ap)
            if source_video is not None:
                sp = job / ("source" + (Path(source_video.filename or "source.mp4").suffix or ".mp4"))
                _save_upload(source_video, sp)
                animated = sp
            else:
                ip = job / ("face" + (Path(image.filename or "face.jpg").suffix or ".jpg"))
                _save_upload(image, ip)
                animated = _liveportrait(ip, job)
            final = _musetalk(animated, ap, job)
            # FileResponse streams before cleanup; keep finished jobs and let cleanup script prune them.
            return FileResponse(str(final), media_type="video/mp4", filename="facetalk.mp4")
        except HTTPException:
            raise
        except subprocess.TimeoutExpired as e:
            raise HTTPException(status_code=504, detail=f"GPU inference timeout: {e}")
        except Exception as e:
            raise HTTPException(status_code=500, detail=str(e)[:3000])


@APP.post("/facetalk")
async def facetalk(image: UploadFile = File(...), audio: UploadFile = File(...),
                   liveportrait_url: str = Form(""), authorization: str | None = Header(None)):
    return await _process(image, None, audio, authorization)


@APP.post("/lipsync")
async def lipsync(audio: UploadFile = File(...), image: UploadFile | None = File(None),
                  source_video: UploadFile | None = File(None), authorization: str | None = Header(None)):
    return await _process(image, source_video, audio, authorization)


@APP.post("/animate")
async def animate(image: UploadFile = File(...), authorization: str | None = Header(None)):
    _auth(authorization)
    if not DRIVING_VIDEO:
        raise HTTPException(status_code=503, detail="Set LIVEPORTRAIT_DRIVING_VIDEO first")
    async with LOCK:
        job = Path(tempfile.mkdtemp(prefix="facetalk_lp_", dir=str(WORK_DIR)))
        ip = job / ("face" + (Path(image.filename or "face.jpg").suffix or ".jpg"))
        _save_upload(image, ip)
        try:
            out = _liveportrait(ip, job)
            return FileResponse(str(out), media_type="video/mp4", filename="portrait.mp4")
        except Exception as e:
            raise HTTPException(status_code=500, detail=str(e)[:3000])
