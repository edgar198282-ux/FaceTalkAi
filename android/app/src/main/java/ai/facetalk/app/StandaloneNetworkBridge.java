package ai.facetalk.app;

import android.app.Activity;
import android.webkit.JavascriptInterface;
import android.webkit.WebView;
import org.json.JSONObject;
import java.io.ByteArrayOutputStream;
import java.io.InputStream;
import java.io.OutputStream;
import java.net.HttpURLConnection;
import java.net.URL;
import java.nio.charset.StandardCharsets;

public final class StandaloneNetworkBridge {
    private final Activity activity;
    private final WebView webView;
    StandaloneNetworkBridge(Activity activity, WebView webView) {
        this.activity = activity;
        this.webView = webView;
    }
    @JavascriptInterface
    public void request(String requestId, String rawUrl, String method, String body) {
        if (requestId == null || !requestId.matches("[a-zA-Z0-9_-]{1,64}")) return;
        new Thread(() -> {
            HttpURLConnection conn = null;
            int status = 0;
            String response;
            try {
                URL url = new URL(rawUrl);
                String protocol = url.getProtocol();
                if (!"https".equalsIgnoreCase(protocol) && !"http".equalsIgnoreCase(protocol)) {
                    throw new IllegalArgumentException("Unsupported protocol");
                }
                if (url.getUserInfo() != null) throw new IllegalArgumentException("Unsupported URL");
                String requestMethod = "POST".equalsIgnoreCase(method) ? "POST" : "GET";
                conn = (HttpURLConnection) url.openConnection();
                conn.setConnectTimeout(12000);
                conn.setReadTimeout(25000);
                conn.setInstanceFollowRedirects(true);
                conn.setRequestProperty("User-Agent", "AbajTV-Standalone/1.0");
                conn.setRequestProperty("Accept", "*/*");
                conn.setRequestMethod(requestMethod);
                if ("POST".equals(requestMethod)) {
                    conn.setDoOutput(true);
                    conn.setRequestProperty("Content-Type", "application/x-www-form-urlencoded; charset=utf-8");
                    byte[] bytes = (body == null ? "" : body).getBytes(StandardCharsets.UTF_8);
                    try (OutputStream out = conn.getOutputStream()) { out.write(bytes); }
                }
                status = conn.getResponseCode();
                InputStream input = status < 400 ? conn.getInputStream() : conn.getErrorStream();
                try (InputStream stream = input; ByteArrayOutputStream buffer = new ByteArrayOutputStream()) {
                    byte[] chunk = new byte[16384];
                    int n;
                    while (stream != null && (n = stream.read(chunk)) != -1) {
                        if (buffer.size() + n > 12 * 1024 * 1024) throw new IllegalArgumentException("Response exceeds 12 MB");
                        buffer.write(chunk, 0, n);
                    }
                    response = buffer.toString("UTF-8");
                }
            } catch (Exception e) {
                status = 0;
                response = e.getClass().getSimpleName() + ": " + e.getMessage();
            } finally {
                if (conn != null) conn.disconnect();
            }
            final int responseStatus = status;
            final String responseBody = response;
            activity.runOnUiThread(() -> {
                if (webView == null) return;
                String current = webView.getUrl();
                if (current == null || !current.startsWith("file:///android_asset/standalone/")) return;
                webView.evaluateJavascript(
                    "window.__abajStandaloneResponse&&window.__abajStandaloneResponse(" +
                    JSONObject.quote(requestId) + "," + responseStatus + "," +
                    JSONObject.quote(responseBody) + ");", null);
            });
        }, "abaj-standalone-http").start();
    }
}
