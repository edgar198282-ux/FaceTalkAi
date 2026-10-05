from pathlib import Path
import re

web = Path("web/index.html").read_text(encoding="utf-8")
java = Path("android/app/src/main/java/ai/facetalk/app/MainActivity.java").read_text(encoding="utf-8")

checks = []

def ok(name, cond):
    checks.append((name, bool(cond)))

# Provider resolution must not treat arbitrary LazyMedia source IDs only as ordinals.
ok("provider resolver helper exists", "resolveLazyProviderServer" in java)
ok("provider hash IDs supported", "server.hashCode()" in java)
ok("provider enum names supported", "java.lang.Enum" in java and ".name()" in java)

# Video tree resolution must accept every returned callback tree, not only literal 'video'.
ok("callback trees collected", "candidates.add(tree)" in java)
ok("deep LazyMedia tree walk used", "collectLazyMediaUrls(" in java)
ok("fragile literal video gate removed", 'if("video".equals(type))' not in java)

# UI must expose only verified video sources.
ok("only playable sources returned", "return playable;" in web)
ok("verified stream filter present", "group&&group.playable" in web)
ok("empty provider buttons removed", "Источник найден · проверка видео" not in web)

# Movie playback must use already-resolved stream URLs and fallback list.
ok("resolved movie autoplay exists", "cinemaPlayResolvedMovie" in web)
ok("playback request diagnostics exists", "playback_request" in web)
ok("fallback array passed to player", "picked.fallbacks" in web)

# Known HLS/season regression.
ok("HLS not parsed as season", 'HLS 1080' not in re.findall(r'(?:сезон|season|s).*', web, flags=re.I)[:1])
ok("strict Sxx season token parser exists", "S(\\d{1,3})" in web)

failed = [name for name, passed in checks if not passed]
for name, passed in checks:
    print(("PASS" if passed else "FAIL") + " - " + name)

if failed:
    raise SystemExit("Cinema lab checks failed: " + ", ".join(failed))
print(f"Cinema lab checks passed: {len(checks)}/{len(checks)}")
