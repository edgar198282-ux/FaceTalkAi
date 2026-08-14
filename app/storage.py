import os
import shutil
from .config import DATA_DIR, DB_PATH

def migrate_legacy_db():
    """
    One-time best-effort migration from older non-volume locations.
    Does nothing if persistent DB already exists.
    """
    if os.path.exists(DB_PATH):
        return False

    candidates = [
        os.path.join(os.getcwd(), "facetalk.db"),
        os.path.join(os.getcwd(), "data", "facetalk.db"),
        "/app/facetalk.db",
        "/app/data.db",
    ]
    for old in candidates:
        try:
            if old != DB_PATH and os.path.isfile(old):
                os.makedirs(os.path.dirname(DB_PATH), exist_ok=True)
                shutil.copy2(old, DB_PATH)
                return True
        except Exception:
            pass
    return False
