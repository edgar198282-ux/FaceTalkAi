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
print("Abaj TV smoke checks passed")