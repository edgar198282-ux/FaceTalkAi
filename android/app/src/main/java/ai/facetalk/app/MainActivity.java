package ai.facetalk.app;

import android.Manifest;
import android.app.Activity;
import android.app.DownloadManager;
import android.content.BroadcastReceiver;
import android.content.Context;
import android.content.Intent;
import android.content.IntentFilter;
import android.content.pm.PackageManager;
import android.database.Cursor;
import android.graphics.Color;
import android.net.Uri;
import android.os.Build;
import android.os.Bundle;
import android.os.Environment;
import android.provider.Settings;
import android.webkit.CookieManager;
import android.webkit.PermissionRequest;
import android.webkit.ValueCallback;
import android.webkit.WebChromeClient;
import android.webkit.WebResourceRequest;
import android.webkit.WebSettings;
import android.webkit.WebView;
import android.webkit.WebViewClient;
import android.widget.Toast;

import org.json.JSONObject;

import java.io.BufferedReader;
import java.io.InputStreamReader;
import java.net.HttpURLConnection;
import java.net.URL;

public class MainActivity extends Activity {
    private static final int FILE_CHOOSER_REQUEST = 4101;
    private static final int MEDIA_PERMISSION_REQUEST = 4102;
    private WebView webView;
    private ValueCallback<Uri[]> fileCallback;
    private PermissionRequest pendingWebPermission;
    private long pendingApkDownloadId = -1L;
    private Uri pendingApkUri;
    private BroadcastReceiver downloadReceiver;
    private volatile boolean updateCheckRunning = false;
    private volatile boolean updateDownloadRunning = false;
    private long lastUpdateCheckAt = 0L;

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
            @Override public void onPermissionRequest(PermissionRequest request) { runOnUiThread(() -> handleWebPermission(request)); }
            @Override public boolean onShowFileChooser(WebView view, ValueCallback<Uri[]> callback, FileChooserParams params) {
                if (fileCallback != null) fileCallback.onReceiveValue(null);
                fileCallback = callback;
                try {
                    Intent intent = params != null ? params.createIntent() : new Intent(Intent.ACTION_GET_CONTENT);
                    if (params == null) { intent.addCategory(Intent.CATEGORY_OPENABLE); intent.setType("*/*"); }
                    startActivityForResult(intent, FILE_CHOOSER_REQUEST);
                    return true;
                } catch (Exception e) { fileCallback = null; return false; }
            }
        });

        webView.setWebViewClient(new WebViewClient() {
            @Override public boolean shouldOverrideUrlLoading(WebView view, WebResourceRequest request) {
                Uri uri = request.getUrl();
                String url = uri.toString();
                String scheme = uri.getScheme() == null ? "" : uri.getScheme().toLowerCase();
                String host = uri.getHost() == null ? "" : uri.getHost().toLowerCase();
                if (url.endsWith(".apk") || url.contains("/api/app-download")) { downloadAndInstallApk(url); return true; }
                if ("tg".equals(scheme) || "t.me".equals(host) || "telegram.me".equals(host)) { openExternal(uri); return true; }
                if (!"http".equals(scheme) && !"https".equals(scheme)) { openExternal(uri); return true; }
                return false;
            }
        });

        registerApkDownloadReceiver();
        loadFaceTalk();
        checkForAppUpdate(true);
    }

    private String baseUrl() {
        String base = BuildConfig.WEB_APP_URL == null ? "" : BuildConfig.WEB_APP_URL.trim();
        if (!base.startsWith("http://") && !base.startsWith("https://") && !base.isEmpty()) base = "https://" + base;
        while (base.endsWith("/")) base = base.substring(0, base.length() - 1);
        return base;
    }

    private void loadFaceTalk() {
        String base = baseUrl();
        if (base.isEmpty()) {
            webView.loadData("<html><body style='margin:0;background:#050510;color:white;font-family:sans-serif;display:flex;align-items:center;justify-content:center;height:100vh;text-align:center'><div><h2>FaceTalk AI</h2><p>Приложение временно недоступно</p></div></body></html>", "text/html", "UTF-8");
            return;
        }
        String sep = base.contains("?") ? "&" : "?";
        webView.loadUrl(base + sep + "app=1&source=android&app_version=" + Uri.encode(BuildConfig.VERSION_NAME)
                + "&app_version_code=" + BuildConfig.VERSION_CODE + "&ota=" + System.currentTimeMillis());
    }

    private void checkForAppUpdate(boolean force) {
        String base = baseUrl();
        if (base.isEmpty() || updateCheckRunning || updateDownloadRunning) return;
        long now = System.currentTimeMillis();
        if (!force && now - lastUpdateCheckAt < 60_000L) return;
        lastUpdateCheckAt = now;
        updateCheckRunning = true;
        new Thread(() -> {
            HttpURLConnection c = null;
            try {
                URL u = new URL(base + "/api/app-release?ts=" + System.currentTimeMillis());
                c = (HttpURLConnection) u.openConnection();
                c.setConnectTimeout(10000);
                c.setReadTimeout(10000);
                c.setUseCaches(false);
                c.setRequestProperty("Cache-Control", "no-cache");
                if (c.getResponseCode() != 200) return;
                BufferedReader br = new BufferedReader(new InputStreamReader(c.getInputStream()));
                StringBuilder sb = new StringBuilder(); String line;
                while ((line = br.readLine()) != null) sb.append(line);
                br.close();
                JSONObject j = new JSONObject(sb.toString());
                int latestCode = j.optInt("version_code", 0);
                String download = j.optString("download_url", "");
                boolean available = j.optBoolean("available", false);
                if (available && latestCode > BuildConfig.VERSION_CODE && !download.isEmpty()) {
                    final String url = download.startsWith("http") ? download : base + download;
                    runOnUiThread(() -> {
                        if (!isFinishing() && !updateDownloadRunning) {
                            Toast.makeText(this, "Найдено обновление FaceTalk AI. Загружаю…", Toast.LENGTH_LONG).show();
                            downloadAndInstallApk(url);
                        }
                    });
                }
            } catch (Exception ignored) {
            } finally {
                updateCheckRunning = false;
                if (c != null) c.disconnect();
            }
        }, "facetalk-update-check").start();
    }

    private void registerApkDownloadReceiver() {
        if (downloadReceiver != null) return;
        downloadReceiver = new BroadcastReceiver() {
            @Override public void onReceive(Context context, Intent intent) {
                if (!DownloadManager.ACTION_DOWNLOAD_COMPLETE.equals(intent.getAction())) return;
                long id = intent.getLongExtra(DownloadManager.EXTRA_DOWNLOAD_ID, -1L);
                if (id != pendingApkDownloadId) return;
                DownloadManager dm = (DownloadManager) getSystemService(DOWNLOAD_SERVICE);
                DownloadManager.Query q = new DownloadManager.Query().setFilterById(id);
                try (Cursor cur = dm.query(q)) {
                    if (cur == null || !cur.moveToFirst()) return;
                    int status = cur.getInt(cur.getColumnIndexOrThrow(DownloadManager.COLUMN_STATUS));
                    if (status != DownloadManager.STATUS_SUCCESSFUL) {
                        updateDownloadRunning = false;
                        Toast.makeText(MainActivity.this, "Ошибка загрузки обновления", Toast.LENGTH_LONG).show();
                        return;
                    }
                } catch (Exception e) { updateDownloadRunning = false; return; }
                updateDownloadRunning = false;
                pendingApkUri = dm.getUriForDownloadedFile(id);
                requestInstallOrOpen();
            }
        };
        IntentFilter f = new IntentFilter(DownloadManager.ACTION_DOWNLOAD_COMPLETE);
        if (Build.VERSION.SDK_INT >= 33) registerReceiver(downloadReceiver, f, Context.RECEIVER_NOT_EXPORTED); else registerReceiver(downloadReceiver, f);
    }

    private void downloadAndInstallApk(String rawUrl) {
        if (rawUrl == null || rawUrl.trim().isEmpty() || updateDownloadRunning) return;
        try {
            DownloadManager.Request req = new DownloadManager.Request(Uri.parse(rawUrl));
            req.setTitle("FaceTalk AI"); req.setDescription("Загрузка обновления…");
            req.setMimeType("application/vnd.android.package-archive");
            req.setNotificationVisibility(DownloadManager.Request.VISIBILITY_VISIBLE_NOTIFY_COMPLETED);
            req.setAllowedOverMetered(true);
            req.setAllowedOverRoaming(true);
            req.setDestinationInExternalFilesDir(this, Environment.DIRECTORY_DOWNLOADS, "FaceTalkAI-update.apk");
            DownloadManager dm = (DownloadManager) getSystemService(DOWNLOAD_SERVICE);
            pendingApkUri = null;
            updateDownloadRunning = true;
            pendingApkDownloadId = dm.enqueue(req);
        } catch (Exception e) {
            updateDownloadRunning = false;
            Toast.makeText(this, "Не удалось загрузить обновление", Toast.LENGTH_LONG).show();
        }
    }

    private void requestInstallOrOpen() {
        if (pendingApkUri == null) return;
        if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.O && !getPackageManager().canRequestPackageInstalls()) {
            try {
                startActivity(new Intent(Settings.ACTION_MANAGE_UNKNOWN_APP_SOURCES, Uri.parse("package:" + getPackageName())));
                Toast.makeText(this, "Разрешите FaceTalk AI устанавливать обновления", Toast.LENGTH_LONG).show();
            } catch (Exception ignored) {}
            return;
        }
        Uri uri = pendingApkUri;
        pendingApkUri = null;
        openPackageInstaller(uri);
    }

    private void openPackageInstaller(Uri apkUri) {
        if (apkUri == null) return;
        try {
            Intent install = new Intent(Intent.ACTION_VIEW);
            install.setDataAndType(apkUri, "application/vnd.android.package-archive");
            install.addFlags(Intent.FLAG_GRANT_READ_URI_PERMISSION | Intent.FLAG_ACTIVITY_NEW_TASK);
            startActivity(install);
        } catch (Exception e) { Toast.makeText(this, "APK скачан, но установщик не открылся", Toast.LENGTH_LONG).show(); }
    }

    private void handleWebPermission(PermissionRequest request) {
        if (request == null) return;
        boolean needsMic = false, needsCamera = false;
        for (String resource : request.getResources()) {
            if (PermissionRequest.RESOURCE_AUDIO_CAPTURE.equals(resource)) needsMic = true;
            if (PermissionRequest.RESOURCE_VIDEO_CAPTURE.equals(resource)) needsCamera = true;
        }
        boolean micGranted = !needsMic || Build.VERSION.SDK_INT < 23 || checkSelfPermission(Manifest.permission.RECORD_AUDIO) == PackageManager.PERMISSION_GRANTED;
        boolean cameraGranted = !needsCamera || Build.VERSION.SDK_INT < 23 || checkSelfPermission(Manifest.permission.CAMERA) == PackageManager.PERMISSION_GRANTED;
        if (micGranted && cameraGranted) { request.grant(request.getResources()); return; }
        pendingWebPermission = request;
        if (Build.VERSION.SDK_INT >= 23) requestPermissions(new String[]{Manifest.permission.RECORD_AUDIO, Manifest.permission.CAMERA}, MEDIA_PERMISSION_REQUEST);
        else request.grant(request.getResources());
    }

    @Override public void onRequestPermissionsResult(int requestCode, String[] permissions, int[] grantResults) {
        super.onRequestPermissionsResult(requestCode, permissions, grantResults);
        if (requestCode != MEDIA_PERMISSION_REQUEST || pendingWebPermission == null) return;
        PermissionRequest request = pendingWebPermission; pendingWebPermission = null;
        boolean ok = true; for (int result : grantResults) if (result != PackageManager.PERMISSION_GRANTED) ok = false;
        if (ok) request.grant(request.getResources()); else request.deny();
    }

    @Override protected void onActivityResult(int requestCode, int resultCode, Intent data) {
        super.onActivityResult(requestCode, resultCode, data);
        if (requestCode != FILE_CHOOSER_REQUEST || fileCallback == null) return;
        fileCallback.onReceiveValue(WebChromeClient.FileChooserParams.parseResult(resultCode, data)); fileCallback = null;
    }

    @Override protected void onResume() {
        super.onResume();
        if (pendingApkUri != null && (Build.VERSION.SDK_INT < Build.VERSION_CODES.O || getPackageManager().canRequestPackageInstalls())) {
            Uri u = pendingApkUri; pendingApkUri = null; openPackageInstaller(u);
        } else {
            checkForAppUpdate(false);
        }
    }

    private void openExternal(Uri uri) {
        if (uri == null) return;
        try { startActivity(new Intent(Intent.ACTION_VIEW, uri)); } catch (Exception ignored) {}
    }

    @Override protected void onDestroy() {
        if (downloadReceiver != null) { try { unregisterReceiver(downloadReceiver); } catch (Exception ignored) {} }
        if (webView != null) webView.destroy();
        super.onDestroy();
    }

    @Override public void onBackPressed() { if (webView != null && webView.canGoBack()) webView.goBack(); else super.onBackPressed(); }
}
