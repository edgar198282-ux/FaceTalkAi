"""Run: python -m unittest discover -s tests -p 'test_iptv_ad_frame.py'."""
import asyncio
import base64
import importlib.util
import io
import shutil
import sys
import types
import unittest
from pathlib import Path
from unittest.mock import AsyncMock, patch

from aiohttp import web
from aiohttp.test_utils import TestClient, TestServer
from PIL import Image, ImageDraw, ImageFont

# These route tests never use the database. Load the actual IPTV module with
# only that dependency isolated so a production bot/database is not required.
spec = importlib.util.spec_from_file_location('app._iptv_frame_test', Path(__file__).parents[1] / 'app/iptv.py')
iptv = importlib.util.module_from_spec(spec)
db = types.ModuleType('app.db')
db.get_setting = AsyncMock()
with patch.dict(sys.modules, {'app.db': db}):
    spec.loader.exec_module(iptv)


def image_frame(text='NEWS LIVE', size=(640, 360)):
    image = Image.new('RGB', size, 'black')
    draw = ImageDraw.Draw(image)
    font_path = '/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf'
    font = ImageFont.truetype(font_path, 48) if Path(font_path).exists() else ImageFont.load_default()
    draw.text((30, 120), text, font=font, fill='white')
    out = io.BytesIO()
    image.save(out, 'JPEG')
    return base64.b64encode(out.getvalue()).decode()


class PlayerFrames(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        iptv._state['channels'] = {
            'fresh': {'id': 'fresh', 'status': 'ONLINE', 'url': 'http://stream.mcquack.net/429/index.m3u8'},
            'personal': {'personal': True}, 'cinema:one': {},
        }
        iptv._ad_frame_slots = asyncio.Semaphore(2)
        iptv._ottclub_ad_state.clear()
        iptv._ad_frame_seen.clear()
        app = web.Application(client_max_size=1000000)
        app.router.add_post('/frame', iptv.api_ad_frame)
        app.router.add_post('/viewing', iptv.api_ad_viewing)
        self.client = TestClient(TestServer(app))
        await self.client.start_server()

    async def asyncTearDown(self):
        await self.client.close()

    async def send(self, **kwargs):
        return await self.client.post('/frame', json={'channel_id': 'fresh', 'frame': image_frame(), **kwargs})

    async def test_viewer_results_do_not_use_or_change_shared_state(self):
        iptv._ottclub_ad_state['fresh'] = {'active': False}
        with patch.object(iptv, '_ocr_ottclub_frame', AsyncMock(return_value='OTT CLUB QR')):
            response = await self.send()
            self.assertTrue((await response.json())['active'])
        self.assertFalse(iptv._ottclub_ad_state['fresh']['active'])
        iptv._ottclub_ad_state['fresh']['active'] = True
        with patch.object(iptv, '_ocr_ottclub_frame', AsyncMock(return_value='NEWS LIVE')):
            response = await self.send()
            self.assertFalse((await response.json())['active'])
        self.assertTrue(iptv._ottclub_ad_state['fresh']['active'])

    async def test_errors_are_not_clean_frames(self):
        with patch.object(iptv, '_ocr_ottclub_frame', AsyncMock(side_effect=RuntimeError('unavailable'))):
            response = await self.send()
            self.assertEqual(response.status, 503)
            self.assertNotIn('active', await response.json())

    async def test_reject_invalid_oversized_blank_and_private_frames(self):
        for body, status in [({'frame': '%%%bad'}, 400), ({'frame': image_frame(size=(641, 360))}, 400),
                             ({'frame': image_frame(text='')}, 400), ({'channel_id': 'personal'}, 404),
                             ({'channel_id': 'cinema:one'}, 404), ({'channel_id': 'missing'}, 404)]:
            response = await self.send(**body)
            self.assertEqual(response.status, status)
        response = await self.client.post('/frame', data=b'x' * 360001)
        self.assertEqual(response.status, 413)
        async def chunks():
            for _ in range(23):
                yield b'x' * 16384
        response = await self.client.post('/frame', data=chunks())
        self.assertEqual(response.status, 413)

    async def test_backpressure_without_queued_ocr(self):
        await iptv._ad_frame_slots.acquire()
        await iptv._ad_frame_slots.acquire()
        with patch.object(iptv, '_ocr_ottclub_frame', AsyncMock()) as ocr:
            response = await self.send()
            self.assertEqual(response.status, 429)
            ocr.assert_not_awaited()
        iptv._ad_frame_slots.release()
        iptv._ad_frame_slots.release()

    async def test_player_viewing_does_not_open_second_stream(self):
        with patch.object(iptv.asyncio, 'create_task') as create_task:
            response = await self.client.post('/viewing', json={'channel_id': 'fresh', 'player_frames': True})
            self.assertEqual(response.status, 200)
            create_task.assert_not_called()

    @unittest.skipUnless(shutil.which('tesseract'), 'Tesseract not installed')
    async def test_real_ocr_on_uploaded_player_frames(self):
        for text, active, reason in [('OTT CLUB', True, 'ottclub'), ('CINERAMA', True, 'cinerama_placeholder'), ('NEWS LIVE', False, ''), ('Не успел?\nПросто перемотай', True, 'ottclub')]:
            response = await self.send(frame=image_frame(text))
            self.assertEqual(response.status, 200)
            result = await response.json()
            self.assertEqual((result['active'], result['reason']), (active, reason), text)
            self.assertEqual(response.headers['Cache-Control'], 'no-store')


class PromoSignatures(unittest.TestCase):
    def test_recorded_id_promo_ocr(self):
        item = {'url': 'http://stream.mcquack.net/205/index.m3u8'}
        for text in (
            'HE YCnEJI? Mpocto i = CEC 01:08:58 all | HE YCnEJI? npocto nepemoran',
            'Не успел? Просто перемотай',
            'НЕ УСПЕЛ? ПРОСТО ПЕРЕМОТАЙ',
            'НЕ УСПЕЛ? ПPOCTO ПEPEMOTАЙ',
        ):
            self.assertTrue(iptv._ottclub_promo_hit(text, item), text)
            self.assertFalse(iptv._ottclub_promo_hit(text, {'url': 'https://example.com/news.m3u8'}), text)
        for text in ('Не успел?', 'Просто перемотай', 'Не успел? Сегодня новости', 'Не успел сказать прощай. Нажми на паузу, перемотай'):
            self.assertFalse(iptv._ottclub_promo_hit(text, item), text)

    def test_multilingual_ocr_keeps_brand_matches(self):
        self.assertTrue(iptv._ottclub_text_hit('ОТТ CLUВ'))
        self.assertTrue(iptv._cinerama_text_hit('СINЕRАМА'))


if __name__ == '__main__':
    unittest.main()
