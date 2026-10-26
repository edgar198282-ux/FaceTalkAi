import re
from pathlib import Path


def index_path(web_dir, user_agent):
    match = re.search(r'(?:Chrome|Chromium)/(\d+)', user_agent or '')
    legacy = Path(web_dir) / 'legacy' / 'index.html'
    if match and int(match.group(1)) < 90 and legacy.is_file():
        return str(legacy)
    return str(Path(web_dir) / 'index.html')
