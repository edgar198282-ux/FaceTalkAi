import json
import os
import re
from pathlib import Path

IDENTIFIER = re.compile(r"^[a-z0-9][a-z0-9_-]{0,63}$")


def verify_id(value):
    if not isinstance(value, str) or not IDENTIFIER.fullmatch(value):
        raise ValueError("Invalid movie id: use lowercase ASCII letters, numbers, - or _")
    return value


def load_state(root: Path):
    path = root / "catalogue.json"
    if not path.exists():
        return {"movies": {}, "playlist": []}
    data = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(data, dict) or not isinstance(data.get("movies"), dict) or not isinstance(data.get("playlist"), list):
        raise ValueError("Invalid catalogue.json")
    movies = data["movies"]
    for movie_id, movie in movies.items():
        verify_id(movie_id)
        if not isinstance(movie, dict) or not isinstance(movie.get("title"), str) or not movie["title"].strip():
            raise ValueError(f"Invalid movie metadata: {movie_id}")
    for movie_id in data["playlist"]:
        verify_id(movie_id)
        if movie_id not in movies:
            raise ValueError(f"Playlist contains unknown movie: {movie_id}")
    return data


def save_state(root: Path, data):
    root.mkdir(parents=True, exist_ok=True)
    path = root / "catalogue.json"
    tmp = root / f".catalogue.{os.getpid()}.tmp"
    try:
        with tmp.open("w", encoding="utf-8") as f:
            json.dump(data, f, indent=2, ensure_ascii=False)
            f.write("\n")
            f.flush()
            os.fsync(f.fileno())
        os.replace(tmp, path)
    finally:
        tmp.unlink(missing_ok=True)


def build_concat(root: Path, state):
    result = ["ffconcat version 1.0"]
    for movie_id in state["playlist"]:
        filename = root / "prepared" / (verify_id(movie_id) + ".ts")
        if not filename.is_file() or filename.stat().st_size == 0:
            raise ValueError(f"Prepared movie missing or empty: {movie_id}")
        # All paths originate from the controlled data directory and verified IDs.
        escaped = str(filename.resolve()).replace("'", "'\\''")
        result.append(f"file '{escaped}'")
    if len(result) == 1:
        raise ValueError("Playlist is empty")
    return "\n".join(result) + "\n"


def m3u(base_url):
    return (
        '#EXTM3U\n'
        '#EXTINF:-1 tvg-id="abaj.cinema" tvg-name="ABAJ CINEMA 24/7" '
        'group-title="Фильмы",ABAJ CINEMA 24/7\n'
        + base_url.rstrip("/") + "/live/index.m3u8\n"
    )
