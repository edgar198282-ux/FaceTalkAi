# Media cloud connections

The home screen switches are saved per device under `abaj_home_sections`. Settings always remains visible. Cloud accounts belong to the signed-in ABAJ TV user; they are not shared between users. Local selected files stay in browser memory and are never uploaded.

## Google Drive

1. Register a web OAuth client in Google Cloud, enable Drive API, configure consent and any required verification for the read-only Drive scope.
2. Register this redirect URI: `https://facetalkai-production-9387.up.railway.app/api/media/callback/google`.
3. Set `MEDIA_GOOGLE_CLIENT_ID` and `MEDIA_GOOGLE_CLIENT_SECRET` in the FaceTalkAi Railway service.

## Yandex Disk

1. Register an OAuth web application with read access to Disk.
2. Register this redirect URI: `https://facetalkai-production-9387.up.railway.app/api/media/callback/yandex`.
3. Set `MEDIA_YANDEX_CLIENT_ID` and `MEDIA_YANDEX_CLIENT_SECRET` in the FaceTalkAi Railway service.

`MEDIA_PUBLIC_URL` optionally overrides the canonical HTTPS origin; Railway's public domain is used otherwise. Credentials must remain on the server. Google Photos is a separate service and is not included in this Drive integration.

Cloud authorization opens externally or through a QR code on another device. Returning to ABAJ TV requires explicit confirmation of the displayed account. Authorization requests expire after 10 minutes. Tokens are encrypted in the existing persistent settings database using a key derived from the bot token, or `MEDIA_TOKEN_KEY` when supplied. Changing that encryption key requires users to reconnect their clouds. Each provider can be disconnected separately.

Cloud media is streamed through short-lived opaque URLs (two hours) with Range support. Disconnecting removes all active URLs for that user and provider. These URLs are bearer capabilities and must not be shared. No complete movie or personal photo is stored on disk by this feature. Video format compatibility depends on the device; this integration does not transcode personal cloud files.
