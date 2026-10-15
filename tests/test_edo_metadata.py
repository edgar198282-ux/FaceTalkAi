import ast
import asyncio
import gzip
import hashlib
import re
import time
import types
import unittest
from pathlib import Path
from urllib.parse import urlparse

ROOT = Path(__file__).resolve().parents[1]


def load_functions(path, names, namespace):
    tree = ast.parse((ROOT / path).read_text())
    nodes = [node for node in tree.body if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)) and node.name in names]
    exec(compile(ast.Module(body=nodes, type_ignores=[]), path, 'exec'), namespace)


class EdoMetadata(unittest.IsolatedAsyncioTestCase):
    def setUp(self):
        self.ns = dict(re=re, hashlib=hashlib, urlparse=urlparse, time=time, asyncio=asyncio,
                       COUNTRY_CODES={'AM', 'RU'}, _edem_xmltv_cache={})
        load_functions('app/iptv.py', {'_attrs', '_extinf_name', '_normalize_name', '_channel_key', '_looks_junk', '_parse_m3u'}, self.ns)
        load_functions('app/webapp_plus.py', {'_playlist_xmltv_url', '_edem_xmltv_guide'}, self.ns)

    def test_provider_headers(self):
        for key in ('url-tvg', 'x-tvg-url', 'tvg-url'):
            for quote in ('', '"', "'"):
                with self.subTest(key=key, quote=quote):
                    header = f'\ufeff#EXTM3U {key} = {quote}https://example.org/guide.xml.gz{quote}'
                    self.assertEqual(self.ns['_playlist_xmltv_url'](header), 'https://example.org/guide.xml.gz')
        self.assertEqual(self.ns['_playlist_xmltv_url']('#EXTM3U url-tvg="file:///tmp/a"'), '')

    def test_provider_channels_and_groups_are_preserved(self):
        body = '''#EXTM3U
#EXTINF:-1 tvg-id=one tvg-logo=https://example.org/logo.png group-title=News,News 576p
https://example.org/one
#EXTINF:-1 tvg-id='two' group-title='Кино, сериалы',Кино HD
https://example.org/two
#EXTINF:-1 tvg-id=three,Adult 4K
#EXTGRP:18+
https://example.org/three
'''
        rows = self.ns['_parse_m3u'](body, 'ED', 'https://example.org/list')
        self.assertEqual(len(rows), 3)
        self.assertEqual(rows[0]['tvg_id'], 'one')
        self.assertEqual(rows[0]['logo'], 'https://example.org/logo.png')
        self.assertEqual(rows[1]['name'], 'Кино HD')
        self.assertEqual(rows[1]['group'], 'Кино, сериалы')
        self.assertEqual(rows[2]['group'], '18+')
        free = self.ns['_parse_m3u'](body, 'RU', 'https://example.org/list')
        self.assertNotIn('News 576p', [row['name'] for row in free])

    async def test_entire_chunked_guide_is_read(self):
        for compressed in (False, True):
            self.ns['_edem_xmltv_cache'].clear()
            xml = '<tv><channel id="one"/></tv>'
            payload = gzip.compress(xml.encode()) if compressed else xml.encode()
            class Response:
                def raise_for_status(self):
                    pass
                async def iter_chunked(self, size):
                    for index in range(0, len(payload), 3):
                        yield payload[index:index + 3]
                async def __aenter__(self):
                    self.content = self
                    return self
                async def __aexit__(self, *args):
                    pass
            class Session(Response):
                def __init__(self, **kwargs):
                    pass
                def get(self, *args, **kwargs):
                    return Response()
            parsed = []
            def parse(text):
                parsed.append(text)
                return ({}, {}, {'one': 'https://example.org/one.png'}, {})
            self.ns['aiohttp'] = types.SimpleNamespace(ClientTimeout=lambda **kw: None, ClientSession=Session, ClientError=ConnectionError)
            self.ns['iptv'] = types.SimpleNamespace(_parse_epg_xml=parse)
            guide = await self.ns['_edem_xmltv_guide']('https://example.org/epg' + ('.gz' if compressed else '.xml'))
            self.assertEqual(parsed, [xml])
            self.assertIn('one', guide[2])


if __name__ == '__main__':
    unittest.main()
