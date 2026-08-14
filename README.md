# FaceTalk AI v2 — Video + Mini App

Telegram AI video companion. User uploads a face photo, chooses a role and talks by text or microphone. FaceTalk replies with OpenAI and, when D-ID is configured, animates the uploaded photo into a talking-head MP4.

## New in v2
- VIRALAI-inspired dark neon Telegram Mini App
- Mini App: photo upload, roles, text chat, microphone recording, video/voice mode
- Telegram bot: Video / Voice selector
- D-ID talking-head integration: image upload + audio upload + Talks render + polling + MP4
- automatic voice fallback if D-ID is missing, out of credits or temporarily errors
- Telegram Mini App initData signature validation
- integrated aiohttp web server on Railway PORT
- old SQLite database upgrades automatically (`reply_mode` migration)

## Railway Variables
Required:
- `TELEGRAM_BOT_TOKEN`
- `OPENAI_API_KEY`

For real video:
- `DID_API_KEY` — D-ID Studio API key

For Mini App button:
- `MINIAPP_URL=https://YOUR-RAILWAY-DOMAIN`

Railway needs a public domain: Service → Settings → Networking → Generate Domain. Put that exact HTTPS address into `MINIAPP_URL`, then redeploy.

## Start
`python main.py`

## Notes
Generated MP4/MP3 files are temporary and cleaned after 2 hours. For production history/storage add Railway Volume or object storage later.
