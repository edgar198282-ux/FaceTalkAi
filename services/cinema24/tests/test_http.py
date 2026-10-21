import asyncio
import tempfile
import unittest
from pathlib import Path

from aiohttp.test_utils import TestClient, TestServer

from server import create_app


class HttpTests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        self.directory = tempfile.TemporaryDirectory()
        self.addCleanup(self.directory.cleanup)
        self.server = TestServer(create_app(root=Path(self.directory.name), admin_token="a" * 32, public_url="https://example.test"))
        self.client = TestClient(self.server)
        await self.client.start_server()
        self.addAsyncCleanup(self.client.close)

    async def test_m3u(self):
        async with self.client.get("/cinema.m3u") as result:
            self.assertEqual(result.status, 200)
            self.assertIn("https://example.test/live/index.m3u8", await result.text())
            self.assertEqual(result.headers["Access-Control-Allow-Origin"], "*")

    async def test_secure_admin(self):
        async with self.client.get("/admin/movies") as result:
            self.assertEqual(result.status, 401)
        async with self.client.get("/admin/movies", headers={"Authorization": "Bearer " + "a" * 32}) as result:
            self.assertEqual(result.status, 200)
            self.assertEqual((await result.json())["playlist"], [])

    async def test_reject_invalid_playlist(self):
        headers = {"Authorization": "Bearer " + "a" * 32}
        async with self.client.put("/admin/playlist", json={"playlist": ["missing"]}, headers=headers) as result:
            self.assertEqual(result.status, 400)
        async with self.client.put("/admin/playlist", json={"playlist": []}, headers=headers) as result:
            self.assertEqual(result.status, 200)

    async def test_missing_media_unavailable(self):
        async with self.client.get("/live/index.m3u8") as result:
            self.assertEqual(result.status, 503)
        async with self.client.get("/live/../../etc/passwd") as result:
            self.assertNotEqual(result.status, 200)


if __name__ == "__main__":
    unittest.main()
