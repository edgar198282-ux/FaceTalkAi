import argparse
import os
import subprocess
import tempfile
from pathlib import Path

from core import load_state, save_state, verify_id


def has_audio(source):
    result = subprocess.run(
        ["ffprobe", "-v", "error", "-select_streams", "a:0", "-show_entries", "stream=index", "-of", "csv=p=0", str(source)],
        capture_output=True, text=True, check=True,
    )
    return bool(result.stdout.strip())


def prepare(source: Path, movie_id: str, title: str, root: Path, width=1280, height=720):
    verify_id(movie_id)
    if not title.strip() or len(title) > 200:
        raise ValueError("Title must be 1–200 characters")
    if width < 128 or height < 128 or width % 2 or height % 2:
        raise ValueError("Width/height must be even and at least 128")
    if not source.is_file():
        raise FileNotFoundError(source)
    root.mkdir(parents=True, exist_ok=True)
    prepared = root / "prepared"
    prepared.mkdir(parents=True, exist_ok=True)
    output = prepared / f"{movie_id}.ts"
    state = load_state(root)
    if movie_id in state["movies"] or output.exists():
        raise ValueError("Movie ID already exists; choose a new ID")
    fd, name = tempfile.mkstemp(prefix=".prepare-", suffix=".ts", dir=prepared)
    os.close(fd)
    tmp = Path(name)
    try:
        audio = has_audio(source)
        cmd = ["ffmpeg", "-hide_banner", "-loglevel", "error", "-nostdin", "-y", "-i", str(source)]
        if not audio:
            cmd.extend(["-f", "lavfi", "-i", "anullsrc=channel_layout=stereo:sample_rate=48000"])
        cmd.extend(["-map", "0:v:0", "-map", "0:a:0" if audio else "1:a:0"])
        if not audio:
            cmd.append("-shortest")
        cmd.extend([
            "-vf", f"fps=25,scale={width}:{height}:force_original_aspect_ratio=decrease,pad={width}:{height}:(ow-iw)/2:(oh-ih)/2,format=yuv420p",
            "-c:v", "libx264", "-preset", "veryfast", "-profile:v", "main", "-level:v", "3.1",
            "-b:v", "2200k", "-maxrate", "2500k", "-bufsize", "5000k",
            "-g", "50", "-keyint_min", "50", "-sc_threshold", "0", "-r", "25",
            "-c:a", "aac", "-b:a", "128k", "-ar", "48000", "-ac", "2",
            "-mpegts_flags", "+resend_headers", "-f", "mpegts", str(tmp),
        ])
        subprocess.run(cmd, check=True)
        if tmp.stat().st_size == 0:
            raise RuntimeError("FFmpeg output was empty")
        os.replace(tmp, output)
        state["movies"][movie_id] = {"title": title.strip()}
        state["playlist"].append(movie_id)
        save_state(root, state)
    finally:
        tmp.unlink(missing_ok=True)
    return output


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Normalize an authorized movie for ABAJ CINEMA 24/7")
    parser.add_argument("source", type=Path)
    parser.add_argument("--id", required=True)
    parser.add_argument("--title", required=True)
    parser.add_argument("--data-dir", type=Path, default=Path(os.getenv("DATA_DIR", "/data/cinema24")))
    parser.add_argument("--width", type=int, default=1280)
    parser.add_argument("--height", type=int, default=720)
    args = parser.parse_args()
    print(prepare(args.source, args.id, args.title, args.data_dir, args.width, args.height))
