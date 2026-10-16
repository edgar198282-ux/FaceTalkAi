import ast
import json
import logging
import time
import types
import unittest
from pathlib import Path
from unittest.mock import AsyncMock, patch
from urllib.parse import urlparse
import asyncio


class EdoSnapshot(unittest.IsolatedAsyncioTestCase):
    def setUp(self):
        self.db = {}
        async def get(key, default=''):
            return self.db.get(key, default)
        async def put(key, value):
            self.db[key] = value
        self.ns = dict(json=json, time=time, logging=logging, asyncio=asyncio,
                       urlparse=urlparse, get_setting=get, set_setting=put,
                       EDEM_REFRESH_SECONDS=86400, _edem_named_cache={})
        tree = ast.parse((Path(__file__).resolve().parents[1] / 'app/webapp_plus.py').read_text())
        names = {'_read_edem_snapshot', '_save_edem_snapshot', '_load_edem_playlist_for_uid'}
        nodes = [n for n in tree.body if isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef)) and n.name in names]
        exec(compile(ast.Module(body=nodes, type_ignores=[]), 'edo', 'exec'), self.ns)

    async def test_snapshot_survives_restart_and_rejects_changed_source(self):
        snapshot = {'url': 'https://example.org/list', 'ts': int(time.time()),
                    'channels': [{'id': 'one', 'name': 'Channel'}]}
        await self.ns['_save_edem_snapshot']('0:public:one', snapshot)
        await self.ns['_save_edem_snapshot']('0:public:one', {**snapshot, 'channels': []})
        self.assertEqual(await self.ns['_read_edem_snapshot']('0:public:one', snapshot['url']), snapshot)
        self.assertIsNone(await self.ns['_read_edem_snapshot']('0:public:one', 'https://example.org/new'))
        self.assertIsNone(await self.ns['_read_edem_snapshot']('1:public:one', snapshot['url']))

    async def test_daily_cache_and_failed_refresh_keep_channels(self):
        url = 'https://example.org/list'
        rows = [{'id': 'one', 'name': 'Channel', 'country': 'RU', 'public_playlist': True}]
        self.db['edem_named_playlists:0'] = json.dumps([{'id': 'one', 'name': 'Edo', 'url': url}])
        self.ns.update(_load_edem_legacy_for_uid=AsyncMock(return_value={'active': True, 'channels': []}),
                       _abaj_sources=AsyncMock(return_value=None),
                       _edem_channel_country=lambda ch: 'RU',
                       _fill_edem_logos_from_catalog=lambda ch: None,
                       _match_edem_catalog_logos=lambda ch, catalog: None,
                       _edem_logo_catalog=AsyncMock(return_value={}),
                       iptv=types.SimpleNamespace(_state={'channels': {}}, _logo_name_variants=lambda name: [],
                                                  _epg_logo_for_channel=lambda ch: None))
        class Session:
            calls = 0
            def __init__(self, **kwargs):
                pass
            async def __aenter__(self):
                return self
            async def __aexit__(self, *args):
                pass
            def get(self, *args, **kwargs):
                Session.calls += 1
                raise ConnectionError('offline')
        self.ns['aiohttp'] = types.SimpleNamespace(ClientSession=Session, ClientError=ConnectionError,
                                                   ClientTimeout=lambda **kw: None)
        for age, expected_calls in [(3600, 0), (86401, 2)]:
            self.ns['_edem_named_cache'].clear()
            await self.ns['_save_edem_snapshot']('0:public:one', {'url': url, 'ts': int(time.time()) - age, 'channels': rows})
            with patch('socket.getaddrinfo', return_value=[]):
                result = await self.ns['_load_edem_playlist_for_uid'](123)
            self.assertEqual(result['channels'], rows)
            self.assertEqual(Session.calls, expected_calls)
        self.ns['_abaj_sources'] = AsyncMock(return_value=[])
        result = await self.ns['_load_edem_playlist_for_uid'](123)
        self.assertEqual(result['channels'], [])


if __name__ == '__main__':
    unittest.main()
