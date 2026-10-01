import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from app import iptv

sample = '''#EXTM3U
#EXTINF:-1 tvg-id="am.one" tvg-name="Armenia One" group-title="General",Armenia One
https://example.com/live.m3u8
'''
rows = iptv._parse_m3u(sample, "AM", "smoke")
assert len(rows) == 1
assert rows[0]["name"] == "Armenia One"
assert rows[0]["id"]

ua_sample = '''#EXTM3U
#EXTINF:-1 tvg-id="am.atv" http-user-agent="Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36, Chrome/149.0.0.0 Safari/537.36" group-title="General",ATV Armenia
https://example.com/atv.m3u8
'''
ua_rows = iptv._parse_m3u(ua_sample, "AM", "smoke")
assert len(ua_rows) == 1
assert ua_rows[0]["name"] == "ATV Armenia"
assert iptv._normalize_name("Test HD TV") == "test"
assert iptv._token("https://example.com/a") == iptv._token("https://example.com/a")
assert iptv._token("https://example.com/a") != iptv._token("https://example.com/b")
low_sample = '''#EXTM3U
#EXTINF:-1 tvg-id="am.low" group-title="General",Low 480p Feed
https://example.com/low.m3u8
'''
assert iptv._parse_m3u(low_sample, "AM", "smoke") == []
iptv._stream_health['https://example.com/dead.m3u8'] = {
    'successes': 0, 'failures': 4, 'consecutive_failures': 4,
    'uptime_pct': 0.0, 'last_fail': __import__('time').time()
}
assert iptv._is_quarantined('https://example.com/dead.m3u8')
print("Abaj TV smoke checks passed")
