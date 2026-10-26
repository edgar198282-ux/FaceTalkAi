import hashlib
import json
import tempfile
import unittest
from pathlib import Path

from app.web_compat import index_path


class WebCompatTests(unittest.TestCase):
    def test_legacy_selection(self):
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            (root / 'legacy').mkdir()
            (root / 'legacy/index.html').touch()
            for version in (70, 79, 89):
                self.assertEqual(index_path(root, f'Android Chrome/{version}.0'), str(root / 'legacy/index.html'))
            for agent in ('Chrome/90.0', 'Chrome/130.0', 'Safari/605', ''):
                self.assertEqual(index_path(root, agent), str(root / 'index.html'))

    def test_missing_legacy_falls_back(self):
        with tempfile.TemporaryDirectory() as folder:
            self.assertEqual(index_path(folder, 'Chrome/70.0'), str(Path(folder) / 'index.html'))

    def test_legacy_sources_current(self):
        web = Path(__file__).resolve().parents[1] / 'web'
        hashes = json.loads((web / 'legacy/sources.json').read_text())
        for name, expected in hashes.items():
            self.assertEqual(hashlib.sha256((web / name).read_bytes()).hexdigest(), expected,
                             f'Rebuild compatibility files: cd scripts/web-compat && npm ci && npm run build ({name})')
