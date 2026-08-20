package ai.facetalk.app;

import android.Manifest;
import android.app.Activity;
import android.content.Intent;
import android.content.pm.PackageManager;
import android.graphics.Color;
import android.net.Uri;
import android.os.Build;
import android.os.Bundle;
import android.provider.MediaStore;
import android.webkit.CookieManager;
import android.webkit.PermissionRequest;
import android.webkit.ValueCallback;
import android.webkit.WebChromeClient;
import android.webkit.WebResourceRequest;
import android.webkit.WebSettings;
import android.webkit.WebView;
import android.webkit.WebViewClient;
import android.widget.Toast;

public class MainActivity extends Activity {
    private static final int FILE_CHOOSER_REQUEST = 4101;
    private static final int MEDIA_PERMISSION_REQUEST = 4102;
    private WebView webView;
    private ValueCallback<Uri[]> fileCallback;
    private PermissionRequest pendingWebPermission;

    @Override
    protected void onCreate(Bundle savedInstanceState) {
        super.onCreate(savedInstanceState);
        setTheme(R.style.AppTheme);

        webView = new WebView(this);
        webView.setBackgroundColor(Color.rgb(5, 5, 16));
        setContentView(webView);

        WebSettings s = webView.getSettings();
        s.setJavaScriptEnabled(true);
        s.setDomStorageEnabled(true);
        s.setDatabaseEnabled(true);
        s.setMediaPlaybackRequiresUserGesture(false);
        s.setCacheMode(WebSettings.LOAD_NO_CACHE);
        s.setAllowFileAccess(true);
        s.setAllowContentAccess(true);
        s.setUserAgentString(s.getUserAgentString() + " FaceTalkAI-Android/" + BuildConfig.VERSION_NAME);
        webView.clearCache(true);

        CookieManager.getInstance().setAcceptCookie(true);
        CookieManager.getInstance().setAcceptThirdPartyCookies(webView, true);

        webView.setWebChromeClient(new WebChromeClient() {
            @Override
            public void onPermissionRequest(PermissionRequest request) {
                runOnUiThread(() -> handleWebPermission(request));
            }

            @Override
            public boolean onShowFileChooser(WebView view, ValueCallback<Uri[]> callback, FileChooserParams params) {
                if (fileCallback != null) fileCallback.onReceiveValue(null);
                fileCallback = callback;
                try {
                    Intent intent = params != null ? params.createIntent() : new Intent(Intent.ACTION_GET_CONTENT);
                    if (params == null) {
                        intent.addCategory(Intent.CATEGORY_OPENABLE);
                        intent.setType("*/*");
                    }
                    startActivityForResult(intent, FILE_CHOOSER_REQUEST);
                    return true;
                } catch (Exception e) {
                    try {
                        Intent fallback = new Intent(Intent.ACTION_GET_CONTENT);
                        fallback.addCategory(Intent.CATEGORY_OPENABLE);
                        fallback.setType("*/*");
                        startActivityForResult(Intent.createChooser(fallback, "Выберите файл"), FILE_CHOOSER_REQUEST);
                        return true;
                    } catch (Exception ignored) {
                        fileCallback = null;
                        return false;
                    }
                }
            }
        });

        webView.setWebViewClient(new WebViewClient() {
            @Override
            public boolean shouldOverrideUrlLoading(WebView view, WebResourceRequest request) {
                Uri uri = request.getUrl();
                String scheme = uri.getScheme() == null ? "" : uri.getScheme().toLowerCase();
                String host = uri.getHost() == null ? "" : uri.getHost().toLowerCase();
                if ("tg".equals(scheme) || "t.me".equals(host) || "telegram.me".equals(host)) {
                    openExternal(uri);
                    return true;
                }
                if (!"http".equals(scheme) && !"https".equals(scheme)) {
                    openExternal(uri);
                    return true;
                }
                return false;
            }
        });

        loadFaceTalk();
    }

    private void loadFaceTalk() {
        String base = BuildConfig.WEB_APP_URL == null ? "" : BuildConfig.WEB_APP_URL.trim();
        if (base.isEmpty()) {
            webView.loadData("<html><body style='margin:0;background:#050510;color:white;font-family:sans-serif;display:flex;align-items:center;justify-content:center;height:100vh;text-align:center'><div><h2>FaceTalk AI</h2><p>Приложение временно недоступно</p></div></body></html>", "text/html", "UTF-8");
            return;
        }
        if (!base.startsWith("http://") && !base.startsWith("https://")) base = "https://" + base;
        String sep = base.contains("?") ? "&" : "?";
        String url = base + sep + "app=1&source=android&app_version=" + Uri.encode(BuildConfig.VERSION_NAME)
                + "&app_version_code=" + BuildConfig.VERSION_CODE
                + "&ota=" + System.currentTimeMillis();
        webView.loadUrl(url);
    }

    private void handleWebPermission(PermissionRequest request) {
        if (request == null) return;
        boolean needsMic = false;
        boolean needsCamera = false;
        for (String resource : request.getResources()) {
            if (PermissionRequest.RESOURCE_AUDIO_CAPTURE.equals(resource)) needsMic = true;
            if (PermissionRequest.RESOURCE_VIDEO_CAPTURE.equals(resource)) needsCamera = true;
        }

        boolean micGranted = !needsMic || Build.VERSION.SDK_INT < 23 || checkSelfPermission(Manifest.permission.RECORD_AUDIO) == PackageManager.PERMISSION_GRANTED;
        boolean cameraGranted = !needsCamera || Build.VERSION.SDK_INT < 23 || checkSelfPermission(Manifest.permission.CAMERA) == PackageManager.PERMISSION_GRANTED;

        if (micGranted && cameraGranted) {
            request.grant(request.getResources());
            return;
        }

        pendingWebPermission = request;
        if (Build.VERSION.SDK_INT >= 23) {
            requestPermissions(new String[]{Manifest.permission.RECORD_AUDIO, Manifest.permission.CAMERA}, MEDIA_PERMISSION_REQUEST);
        } else {
            request.grant(request.getResources());
        }
    }

    @Override
    public void onRequestPermissionsResult(int requestCode, String[] permissions, int[] grantResults) {
        super.onRequestPermissionsResult(requestCode, permissions, grantResults);
        if (requestCode != MEDIA_PERMISSION_REQUEST || pendingWebPermission == null) return;
        PermissionRequest request = pendingWebPermission;
        pendingWebPermission = null;
        boolean ok = true;
        for (int result : grantResults) if (result != PackageManager.PERMISSION_GRANTED) ok = false;
        if (ok) request.grant(request.getResources());
        else {
            request.deny();
            Toast.makeText(this, "Для FaceTalk нужен доступ к микрофону и камере", Toast.LENGTH_LONG).show();
        }
    }

    @Override
    protected void onActivityResult(int requestCode, int resultCode, Intent data) {
        super.onActivityResult(requestCode, resultCode, data);
        if (requestCode != FILE_CHOOSER_REQUEST || fileCallback == null) return;
        Uri[] result = WebChromeClient.FileChooserParams.parseResult(resultCode, data);
        fileCallback.onReceiveValue(result);
        fileCallback = null;
    }

    private void openExternal(Uri uri) {
        if (uri == null) return;
        try {
            String host = uri.getHost() == null ? "" : uri.getHost().toLowerCase();
            String scheme = uri.getScheme() == null ? "" : uri.getScheme().toLowerCase();
            if ("tg".equals(scheme) || "t.me".equals(host) || "telegram.me".equals(host)) {
                Intent tg = new Intent(Intent.ACTION_VIEW, uri);
                tg.setPackage("org.telegram.messenger");
                try { startActivity(tg); return; } catch (Exception ignored) {}
            }
            startActivity(new Intent(Intent.ACTION_VIEW, uri));
        } catch (Exception ignored) {}
    }

    @Override
    public void onBackPressed() {
        if (webView != null && webView.canGoBack()) webView.goBack();
        else super.onBackPressed();
    }
}
