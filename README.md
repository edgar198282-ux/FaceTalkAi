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


## v2.1 FIX
- Bot no longer stays silent on OpenAI errors; shows exact short error.
- OpenAI model fallback added.
- Mini App shows the uploaded photo on the call screen.
- Bottom Home/Chat/Voice/Profile buttons are wired.
- Mini App API returns readable AI errors.

## v2.2 — Admin costs & limits
- Admin button appears only for `ADMIN_ID`.
- Tracks daily/all-time AI requests, text token usage, TTS characters, D-ID video attempts/successes.
- Admin can change the daily video limit per user with +/- buttons without redeploy.
- Mini App shows today's remaining video quota and falls back to voice when the quota is exhausted.
- Fixed Mini App JSON parsing error: non-JSON server errors now display a readable message instead of `Unexpected non-whitespace character...`.
- Money figures are estimates. Set the optional Railway variables below to match your current provider tariff:
  - `OPENAI_INPUT_USD_PER_1M`
  - `OPENAI_OUTPUT_USD_PER_1M`
  - `OPENAI_TTS_USD_PER_1M_CHARS`
  - `DID_USD_PER_VIDEO`
- `VIDEO_DAILY_LIMIT=5` is the default initial limit; the admin can then change it from the bot.


## v2.3 Runtime Fix
- Fixed Mini App uploaded photo: image is now fetched with Telegram init-data authorization and rendered from a Blob URL.
- Fixed /api/photo download using BytesIO.
- Added API middleware: every /api runtime failure returns JSON instead of Railway/plain-text HTML.
- Mini App now prints the server error into the chat instead of silently showing a temporary toast.
- Improved bot OpenAI 401/429 diagnostics.
- Corrected Home/Chat bottom navigation state.


## v2.4 — Real OpenAI Costs in Admin
Add to Railway if you want real OpenAI spend:
- OPENAI_ADMIN_KEY = organization Admin API key
- OPENAI_PROJECT_ID = optional FaceTalk project id (proj_...). If omitted, organization costs are shown.

Admin now shows:
- OpenAI status: working / no credits / bad key / error
- Real spend today
- Real spend since start of month
- Local token, TTS and D-ID usage
- Video/day limit

The official Organization Costs API reports spend, not exact remaining prepaid-credit balance.


## v2.5 Mini App Full Admin
Visible only for Telegram ADMIN_ID:
- users
- OpenAI runtime status
- real OpenAI spend today/month
- token/request/TTS usage
- D-ID attempts/videos and cost estimate
- all-time usage
- video/day limit +/- controls
- refresh button


## v2.6 — Groq Free First
New Railway variable:
- `GROQ_API_KEY` — primary AI key.
Optional:
- `GROQ_TEXT_MODEL=openai/gpt-oss-20b`
- `GROQ_TRANSCRIBE_MODEL=whisper-large-v3-turbo`
- `FREE_TTS_ENABLED=1`
- `FREE_TTS_VOICE_RU=ru-RU-SvetlanaNeural`
- `FREE_TTS_VOICE_HY=hy-AM-AnahitNeural`
- `FREE_TTS_VOICE_EN=en-US-AvaNeural`

Provider order:
1. Chat: Groq -> OpenAI fallback
2. Speech recognition: Groq Whisper -> OpenAI fallback
3. TTS: edge-tts free -> OpenAI fallback
4. Video: D-ID remains unchanged

This allows text, speech recognition and normally voice synthesis to keep working without OpenAI API credits.
