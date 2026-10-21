import json
import tempfile
import unittest
from pathlib import Path

from core import build_concat, load_state, m3u, save_state, verify_id
from server import create_app


class CoreTests(unittest.TestCase):
    def test_ids_reject_path_traversal_and_unicode(self):
        for value in ("../secret", "UPPER", "", "movie.ts", "фильм", "one/two"):
            with self.subTest(value=value):
                with self.assertRaises(ValueError):
                    verify_id(value)

    def test_playlist_from_prepared_files(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root / "prepared").mkdir()
            (root / "prepared" / "first.ts").write_bytes(b"testing")
            state = {"movies": {"first": {"title": "Проверка"}}, "playlist": ["first"]}
            save_state(root, state)
            self.assertEqual(load_state(root), state)
            self.assertIn("first.ts", build_concat(root, state))
            (root / "prepared" / "first.ts").unlink()
            with self.assertRaisesRegex(ValueError, "missing"):
                build_concat(root, state)

    def test_missing_catalogue(self):
        with tempfile.TemporaryDirectory() as directory:
            self.assertEqual(load_state(Path(directory)), {"movies": {}, "playlist": []})

    def test_invalid_catalogue(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root / "catalogue.json").write_text(json.dumps({"movies": {}, "playlist": ["bad"]}))
            with self.assertRaises(ValueError):
                load_state(root)

    def test_m3u(self):
        value = m3u("https://cinema.example.com/")
        self.assertIn("#EXTM3U", value)
        self.assertIn("ABAJ CINEMA 24/7", value)
        self.assertIn("https://cinema.example.com/live/index.m3u8", value)

    def test_requires_admin_token(self):
        with tempfile.TemporaryDirectory() as directory:
            with self.assertRaises(RuntimeError):
                create_app(root=directory, admin_token="short")


if __name__ == "__main__":
    unittest.main()
