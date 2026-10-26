# Legacy Android WebView

The server selects `web/legacy/index.html` for Chromium versions below 90.
Modern devices continue to receive the original page. Both variants use the same
API, authentication and playback logic. The compatibility target is Chrome 70.

After editing `web/index.html`, `free-film.js`, `abaj-media.js` or
`abaj-launcher.js`, rebuild and commit the generated files:

```sh
cd scripts/web-compat
npm ci
npm run build
cd ../..
python -m unittest discover -s tests -p test_web_compat.py
```
