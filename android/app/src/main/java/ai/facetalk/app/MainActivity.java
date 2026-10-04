package ai.facetalk.app;

import android.Manifest;
import android.app.Activity;
import android.app.AlarmManager;
import android.app.DownloadManager;
import android.app.PendingIntent;
import android.app.PictureInPictureParams;
import android.app.UiModeManager;
import android.app.SearchManager;
import android.media.AudioManager;
import android.content.BroadcastReceiver;
import android.content.Context;
import android.content.Intent;
import android.content.IntentFilter;
import android.content.SharedPreferences;
import android.content.pm.PackageManager;
import android.content.pm.ActivityInfo;
import android.content.res.Configuration;
import android.database.Cursor;
import android.graphics.Color;
import android.net.Uri;
import android.os.Build;
import android.os.Bundle;
import android.os.Environment;
import android.os.Handler;
import android.os.Looper;
import android.provider.Settings;
import android.util.Rational;
import android.util.Log;
import android.webkit.CookieManager;
import android.webkit.JavascriptInterface;
import android.webkit.PermissionRequest;
import android.webkit.ValueCallback;
import android.webkit.WebChromeClient;
import android.webkit.WebResourceRequest;
import android.webkit.WebSettings;
import android.webkit.WebView;
import android.webkit.WebViewClient;
import android.widget.Toast;
import android.view.View;
import android.view.KeyEvent;
import android.view.ViewGroup;
import android.view.WindowManager;
import android.view.inputmethod.InputMethodManager;
import android.widget.FrameLayout;

import androidx.core.content.FileProvider;
import androidx.media3.common.MediaItem;
import androidx.media3.common.PlaybackException;
import androidx.media3.common.Player;
import androidx.media3.exoplayer.DefaultLoadControl;
import androidx.media3.exoplayer.ExoPlayer;
import androidx.media3.ui.PlayerView;

import org.json.JSONObject;

import java.io.BufferedReader;
import java.io.File;
import java.io.FileOutputStream;
import java.io.InputStream;
import java.io.InputStreamReader;
import java.net.HttpURLConnection;
import java.net.URL;
import java.util.UUID;
import java.util.concurrent.Executors;
import java.util.concurrent.ScheduledExecutorService;
import java.util.concurrent.TimeUnit;

public class MainActivity extends Activity {
    private static final int FILE_CHOOSER_REQUEST=4101, MEDIA_PERMISSION_REQUEST=4102;
    private WebView webView; private ValueCallback<Uri[]> fileCallback; private PermissionRequest pendingWebPermission;
    private View customView; private WebChromeClient.CustomViewCallback customViewCallback;
    private FrameLayout fullscreenContainer;
    private PlayerView nativeProbeView;
    private ExoPlayer nativeProbePlayer;
    private volatile long nativeProbeStartedAt=0L;
    private volatile String nativeProbeUrl="";
    private SharedPreferences prefs; private boolean telegramLaunchAttempted=false; private boolean isTv=false; private long lastTvBackAt=0L;
    private long pendingApkDownloadId=-1L; private Uri pendingApkUri; private BroadcastReceiver downloadReceiver;
    private volatile boolean updateCheckRunning=false, updateDownloadRunning=false; private long lastUpdateCheckAt=0L;
    private final Handler updateHandler=new Handler(Looper.getMainLooper());
    private final ScheduledExecutorService tvWatchdogExecutor=Executors.newSingleThreadScheduledExecutor();
    private volatile long lastWebHeartbeatAt=System.currentTimeMillis();
    private volatile long lastTvChannelKeyAt=0L;
    private volatile boolean activityResumed=false;
    private volatile boolean pipPlaybackActive=false;
    private volatile boolean tvRecoveryQueued=false;
    private volatile long tvRecoveryStartedAt=0L;
    private WebView cinemaResolverWebView;
    private final Handler cinemaResolverHandler=new Handler(Looper.getMainLooper());
    private volatile String cinemaResolverRequestId="";
    private volatile String cinemaResolverTransport="";
    private volatile boolean cinemaResolverDone=false;
    private volatile String pendingExternalMediaUrl="";
    private volatile String pendingExternalMediaTitle="";
    private String decodeCinemaIntentPart(String raw,int index){
        try{
            String[] parts=(raw==null?"":raw).split(",",-1);
            if(index<0||index>=parts.length)return "";
            String value=parts[index].replace("\n","").trim();
            if(value.isEmpty())return "";
            byte[] data=android.util.Base64.decode(value,android.util.Base64.DEFAULT);
            return new String(data,java.nio.charset.StandardCharsets.UTF_8).trim();
        }catch(Exception e){return "";}
    }
    private String cinemaArticleUrl(String rawIntent){
        try{
            String[] parts=(rawIntent==null?"":rawIntent).split(",",-1);
            if(parts.length<2)return "";
            String source=parts[0].trim();
            String article=decodeCinemaIntentPart(rawIntent,1);
            if(article.isEmpty())return "";
            if("4".equals(source)){
                if(article.startsWith("/"))article=article.substring(1);
                if(article.startsWith("movies/"))article=article.substring("movies/".length());
                return "https://w127.zona.plus/movies/embed/"+article;
            }
            if("13".equals(source)){
                if(!article.startsWith("/"))article="/"+article;
                return "https://zonafilm.ru"+article;
            }
            return "";
        }catch(Exception e){return "";}
    }
    private boolean cinemaStreamMatches(String url,String transport){
        if(url==null)return false;
        String u=url.toLowerCase();
        if(!(u.startsWith("http://")||u.startsWith("https://")))return false;
        if("HLS".equals(transport))return u.contains(".m3u8")||u.contains("hls=")||u.contains("/hls/");
        if("DASH".equals(transport))return u.contains(".mpd")||u.contains("dash=")||u.contains("/dash/");
        return u.contains(".m3u8")||u.contains(".mpd")||u.contains("/hls/")||u.contains("/dash/");
    }
    private void finishCinemaResolve(String requestId,String url){
        if(requestId==null||!requestId.equals(cinemaResolverRequestId)||cinemaResolverDone)return;
        cinemaResolverDone=true;
        final String resolved=url==null?"":url.trim();
        cinemaResolverHandler.removeCallbacksAndMessages(null);
        runOnUiThread(()->{
            try{
                if(cinemaResolverWebView!=null){
                    try{cinemaResolverWebView.stopLoading();}catch(Exception ignored){}
                    try{fullscreenContainer.removeView(cinemaResolverWebView);}catch(Exception ignored){}
                    try{cinemaResolverWebView.destroy();}catch(Exception ignored){}
                    cinemaResolverWebView=null;
                }
                if(webView!=null){
                    String js="window.__abajCinemaResolved&&window.__abajCinemaResolved("+
                        JSONObject.quote(requestId)+","+JSONObject.quote(resolved)+");";
                    webView.evaluateJavascript(js,null);
                }
            }catch(Exception ignored){}
        });
    }
    private void resolveCinemaStreamInternal(String rawIntent,String transport,String requestId){
        final String articleUrl=cinemaArticleUrl(rawIntent);
        if(articleUrl.isEmpty()){
            finishCinemaResolve(requestId,"");
            return;
        }
        runOnUiThread(()->{
            try{
                if(cinemaResolverWebView!=null){
                    try{fullscreenContainer.removeView(cinemaResolverWebView);}catch(Exception ignored){}
                    try{cinemaResolverWebView.destroy();}catch(Exception ignored){}
                }
                cinemaResolverRequestId=requestId;
                cinemaResolverTransport=transport;
                cinemaResolverDone=false;
                WebView resolver=new WebView(MainActivity.this);
                cinemaResolverWebView=resolver;
                WebSettings ws=resolver.getSettings();
                ws.setJavaScriptEnabled(true);
                ws.setDomStorageEnabled(true);
                ws.setMediaPlaybackRequiresUserGesture(false);
                ws.setLoadsImagesAutomatically(false);
                if(Build.VERSION.SDK_INT>=Build.VERSION_CODES.LOLLIPOP)ws.setMixedContentMode(WebSettings.MIXED_CONTENT_ALWAYS_ALLOW);
                try{ws.setUserAgentString(webView!=null?webView.getSettings().getUserAgentString():ws.getUserAgentString());}catch(Exception ignored){}
                resolver.setBackgroundColor(Color.TRANSPARENT);
                resolver.setAlpha(0.01f);
                FrameLayout.LayoutParams lp=new FrameLayout.LayoutParams(2,2);
                lp.leftMargin=-10;lp.topMargin=-10;
                fullscreenContainer.addView(resolver,lp);
                resolver.setWebChromeClient(new WebChromeClient());
                resolver.setWebViewClient(new WebViewClient(){
                    private void inspect(String u){
                        if(!cinemaResolverDone&&cinemaStreamMatches(u,cinemaResolverTransport)){
                            finishCinemaResolve(requestId,u);
                        }
                    }
                    @Override public void onLoadResource(WebView view,String url){
                        inspect(url);
                        super.onLoadResource(view,url);
                    }
                    @Override public WebResourceResponse shouldInterceptRequest(WebView view,WebResourceRequest request){
                        try{if(request!=null&&request.getUrl()!=null)inspect(request.getUrl().toString());}catch(Exception ignored){}
                        return super.shouldInterceptRequest(view,request);
                    }
                    @Override public void onPageFinished(WebView view,String url){
                        super.onPageFinished(view,url);
                        try{
                            view.evaluateJavascript(
                                "(function(){try{"+
                                "var els=[...document.querySelectorAll('video,video source,source,a,button,[class*=play],[id*=play]')];"+
                                "for(var i=0;i<els.length;i++){var e=els[i],u=e.src||e.href||e.getAttribute('src')||e.getAttribute('data-src')||'';"+
                                "if(u&&(/m3u8|\\.mpd/i).test(u))return u;}"+
                                "var b=document.querySelector('button,[class*=play],[id*=play]');if(b){try{b.click()}catch(e){}}"+
                                "document.querySelectorAll('video').forEach(function(v){try{v.muted=true;v.play()}catch(e){}});"+
                                "}catch(e){}return '';})()",
                                value->{
                                    try{
                                        if(value!=null&&value.length()>2){
                                            String u=value;
                                            if(u.startsWith(""")&&u.endsWith("""))u=u.substring(1,u.length()-1);
                                            u=u.replace("\\/","/").replace("\u0026","&");
                                            if(cinemaStreamMatches(u,cinemaResolverTransport))finishCinemaResolve(requestId,u);
                                        }
                                    }catch(Exception ignored){}
                                }
                            );
                        }catch(Exception ignored){}
                    }
                });
                resolver.loadUrl(articleUrl);
                cinemaResolverHandler.postDelayed(()->finishCinemaResolve(requestId,""),18000);
            }catch(Exception e){
                finishCinemaResolve(requestId,"");
            }
        });
    }

    public final class AbajNativeBridge {
        @JavascriptInterface public int adjustVolume(int delta){
            AudioManager am=(AudioManager)getSystemService(Context.AUDIO_SERVICE);
            if(am==null)return -1;
            int max=Math.max(1,am.getStreamMaxVolume(AudioManager.STREAM_MUSIC));
            int cur=am.getStreamVolume(AudioManager.STREAM_MUSIC);
            int target=Math.max(0,Math.min(max,cur+delta));
            am.setStreamVolume(AudioManager.STREAM_MUSIC,target,0);
            return Math.round(target*100f/max);
        }
        @JavascriptInterface public int getVolumePercent(){
            AudioManager am=(AudioManager)getSystemService(Context.AUDIO_SERVICE);
            if(am==null)return -1;
            int max=Math.max(1,am.getStreamMaxVolume(AudioManager.STREAM_MUSIC));
            return Math.round(am.getStreamVolume(AudioManager.STREAM_MUSIC)*100f/max);
        }
        @JavascriptInterface public void showKeyboard(){
            runOnUiThread(()->{
                try{
                    webView.requestFocus();
                    InputMethodManager imm=(InputMethodManager)getSystemService(Context.INPUT_METHOD_SERVICE);
                    if(imm!=null)imm.showSoftInput(webView,InputMethodManager.SHOW_IMPLICIT);
                }catch(Exception ignored){}
            });
        }
        @JavascriptInterface public void hideKeyboard(){
            runOnUiThread(()->{
                try{
                    InputMethodManager imm=(InputMethodManager)getSystemService(Context.INPUT_METHOD_SERVICE);
                    if(imm!=null)imm.hideSoftInputFromWindow(webView.getWindowToken(),0);
                }catch(Exception ignored){}
            });
        }
        @JavascriptInterface public void heartbeat(){
            lastWebHeartbeatAt=System.currentTimeMillis();
            tvRecoveryQueued=false;
            tvRecoveryStartedAt=0L;
        }
        @JavascriptInterface public void setPipPlaybackActive(boolean active){
            pipPlaybackActive=active&&!isTv;
            runOnUiThread(()->updatePictureInPictureParams());
        }
        @JavascriptInterface public void enterPictureInPicture(){
            if(isTv||!pipPlaybackActive)return;
            runOnUiThread(()->enterAbajPictureInPicture());
        }
        @JavascriptInterface public void nativeProbeStart(String rawUrl){
            if(!isTv||rawUrl==null)return;
            String url=rawUrl.trim();
            if(!(url.startsWith("http://")||url.startsWith("https://")))return;
            runOnUiThread(()->startNativeProbe(url));
        }
        @JavascriptInterface public void nativeProbeStop(){
            if(!isTv)return;
            runOnUiThread(()->stopNativeProbe(false));
        }
        @JavascriptInterface public void nativeProbePause(){
            if(!isTv)return;
            runOnUiThread(()->{if(nativeProbePlayer!=null)nativeProbePlayer.pause();});
        }
        @JavascriptInterface public void nativeProbeResume(){
            if(!isTv)return;
            runOnUiThread(()->{if(nativeProbePlayer!=null)nativeProbePlayer.play();});
        }
        @JavascriptInterface public void nativeProbeToggle(){
            if(!isTv)return;
            runOnUiThread(()->{
                if(nativeProbePlayer==null)return;
                if(nativeProbePlayer.isPlaying())nativeProbePlayer.pause();else nativeProbePlayer.play();
            });
        }
        @JavascriptInterface public String lazyMediaInfo(){
            try{
                android.content.pm.PackageInfo pi=getPackageManager().getPackageInfo("com.lazycatsoftware.lmd",0);
                JSONObject o=new JSONObject();
                o.put("installed",true);
                o.put("version",pi.versionName==null?"":pi.versionName);
                return o.toString();
            }catch(Exception e){
                try{
                    JSONObject o=new JSONObject();
                    o.put("installed",false);
                    return o.toString();
                }catch(Exception ignored){return "{\"installed\":false}";}
            }
        }
        @JavascriptInterface public boolean openLazyMedia(){
            try{
                Intent launch=getPackageManager().getLaunchIntentForPackage("com.lazycatsoftware.lmd");
                if(launch==null)return false;
                runOnUiThread(()->{
                    try{startActivity(launch);}catch(Exception ignored){}
                });
                return true;
            }catch(Exception e){return false;}
        }
        @JavascriptInterface public boolean openLazyMediaSection(String section){
            try{
                String s=section==null?"":section.trim().toLowerCase();
                Uri uri;
                if("bookmarks".equals(s))uri=Uri.parse("tvhomechannels://com.lazycatsoftware.lmd/bookmarks");
                else if("history".equals(s))uri=Uri.parse("tvhomechannels://com.lazycatsoftware.lmd/history");
                else return openLazyMedia();
                Intent i=new Intent(Intent.ACTION_VIEW,uri);
                i.setPackage("com.lazycatsoftware.lmd");
                runOnUiThread(()->{
                    try{startActivity(i);}catch(Exception e){
                        try{
                            Intent launch=getPackageManager().getLaunchIntentForPackage("com.lazycatsoftware.lmd");
                            if(launch!=null)startActivity(launch);
                        }catch(Exception ignored){}
                    }
                });
                return true;
            }catch(Exception e){return false;}
        }
        @JavascriptInterface public String lazyMediaSearch(String rawQuery){
            String query=rawQuery==null?"":rawQuery.trim();
            org.json.JSONArray out=new org.json.JSONArray();
            Cursor cur=null;
            try{
                Uri base=Uri.parse("content://com.lazycatsoftware.lmd.tvsearch/search_suggest_query");
                try{
                    cur=getContentResolver().query(base,null,null,new String[]{query},null);
                }catch(Exception first){
                    try{
                        String[] projection=new String[]{
                            SearchManager.SUGGEST_COLUMN_TEXT_1,
                            "suggest_content_type",
                            "suggest_production_year",
                            "suggest_result_card_image",
                            SearchManager.SUGGEST_COLUMN_TEXT_2,
                            "suggest_duration",
                            SearchManager.SUGGEST_COLUMN_INTENT_DATA
                        };
                        cur=getContentResolver().query(base,projection,null,new String[]{query},null);
                    }catch(Exception ignored){}
                }
                if(cur==null)return "[]";
                int t1Col=cur.getColumnIndex(SearchManager.SUGGEST_COLUMN_TEXT_1);
                int typeCol=cur.getColumnIndex("suggest_content_type");
                int yearCol=cur.getColumnIndex("suggest_production_year");
                int posterCol=cur.getColumnIndex("suggest_result_card_image");
                int t2Col=cur.getColumnIndex(SearchManager.SUGGEST_COLUMN_TEXT_2);
                int durationCol=cur.getColumnIndex("suggest_duration");
                int dataCol=cur.getColumnIndex(SearchManager.SUGGEST_COLUMN_INTENT_DATA);
                int count=0;
                while(cur.moveToNext()&&count<180){
                    JSONObject o=new JSONObject();
                    if(t1Col>=0)o.put("title",cur.getString(t1Col));
                    if(typeCol>=0)o.put("content_type",cur.getString(typeCol));
                    if(yearCol>=0)o.put("year",cur.getString(yearCol));
                    if(posterCol>=0)o.put("poster",cur.getString(posterCol));
                    if(t2Col>=0)o.put("subtitle",cur.getString(t2Col));
                    if(durationCol>=0)o.put("duration",cur.getString(durationCol));
                    if(dataCol>=0){
                        String intent=cur.getString(dataCol);
                        o.put("intent",intent);
                        o.put("id",intent);
                    }
                    out.put(o); count++;
                }
            }catch(Exception ignored){}finally{
                if(cur!=null)try{cur.close();}catch(Exception ignored){}
            }
            return out.toString();
        }
        @JavascriptInterface public void lazyMediaSearchAsync(String rawQuery,String rawRequestId){
            final String query=rawQuery==null?"":rawQuery;
            final String requestId=rawRequestId==null?"":rawRequestId.replaceAll("[^A-Za-z0-9_-]","");
            new Thread(()->{
                String result;
                try{result=lazyMediaSearch(query);}catch(Exception e){result="[]";}
                final String payload=result==null?"[]":result;
                runOnUiThread(()->{
                    if(webView==null)return;
                    String js="window.__abajLazyMediaResult&&window.__abajLazyMediaResult("+
                        JSONObject.quote(requestId)+","+payload+");";
                    try{webView.evaluateJavascript(js,null);}catch(Exception ignored){}
                });
            },"abaj-lazy-search").start();
        }
        @JavascriptInterface public void resolveCinemaStream(String rawIntent,String rawTransport,String rawRequestId){
            final String requestId=(rawRequestId==null?"":rawRequestId).replaceAll("[^A-Za-z0-9_-]","");
            String raw=(rawTransport==null?"":rawTransport).trim().toUpperCase();
            final String transport=raw.contains("|")?raw.substring(0,raw.indexOf('|')):raw;
            if(requestId.isEmpty())return;
            resolveCinemaStreamInternal(rawIntent,transport,requestId);
        }
        @JavascriptInterface public boolean openLazyMediaIntent(String raw){
            try{
                String value=raw==null?"":raw.trim();
                if(value.isEmpty())return false;
                Uri uri=Uri.parse(value);
                String scheme=uri.getScheme()==null?"":uri.getScheme().toLowerCase();
                if(scheme.isEmpty()){
                    String article=value.startsWith("/")?value.substring(1):value;
                    if(article.startsWith("article/"))article=article.substring("article/".length());
                    uri=Uri.parse("tvhomechannels://com.lazycatsoftware.lmd/article/"+Uri.encode(article));
                    scheme="tvhomechannels";
                }
                if(!("tvhomechannels".equals(scheme)||"http".equals(scheme)||"https".equals(scheme)))return false;
                Intent i=new Intent(Intent.ACTION_VIEW,uri);
                i.setPackage("com.lazycatsoftware.lmd");
                if(i.resolveActivity(getPackageManager())==null)return false;
                final Intent target=i;
                runOnUiThread(()->{
                    try{
                        startActivity(target);
                    }catch(Exception ignored){
                        try{
                            Intent launch=getPackageManager().getLaunchIntentForPackage("com.lazycatsoftware.lmd");
                            if(launch!=null)startActivity(launch);
                        }catch(Exception ignored2){}
                    }
                });
                return true;
            }catch(Exception e){return false;}
        }
    }
    private final Runnable periodicUpdateCheck=new Runnable(){
        @Override public void run(){
            checkForAppUpdate(true,false);
            updateHandler.postDelayed(this,30L*60L*1000L);
        }
    };

    @Override protected void onCreate(Bundle savedInstanceState){
        super.onCreate(savedInstanceState); setTheme(R.style.AppTheme);
        UiModeManager uiModeManager=(UiModeManager)getSystemService(Context.UI_MODE_SERVICE);
        PackageManager pm=getPackageManager();
        boolean tvUi=uiModeManager!=null&&uiModeManager.getCurrentModeType()==Configuration.UI_MODE_TYPE_TELEVISION;
        boolean leanback=pm.hasSystemFeature("android.software.leanback");
        boolean television=pm.hasSystemFeature("android.hardware.type.television");
        isTv=tvUi||leanback||television;
        if(isTv){
            setRequestedOrientation(ActivityInfo.SCREEN_ORIENTATION_LANDSCAPE);
            getWindow().addFlags(WindowManager.LayoutParams.FLAG_KEEP_SCREEN_ON);
            enterTvImmersive();
        }
        prefs=getSharedPreferences("facetalk_auth",MODE_PRIVATE); consumeAuthIntent(getIntent());
        fullscreenContainer=new FrameLayout(this);
        fullscreenContainer.setBackgroundColor(Color.BLACK);
        if(isTv){
            nativeProbeView=new PlayerView(this);
            nativeProbeView.setUseController(false);
            nativeProbeView.setBackgroundColor(Color.BLACK);
            fullscreenContainer.addView(nativeProbeView,new FrameLayout.LayoutParams(ViewGroup.LayoutParams.MATCH_PARENT,ViewGroup.LayoutParams.MATCH_PARENT));
        }
        webView=new WebView(this);
        // Keep the WebView transparent at the Android layer so the native
        // Media3 surface underneath can be revealed without recreating views.
        // Normal pages remain opaque because their HTML/CSS paints the blue UI.
        webView.setBackgroundColor(Color.TRANSPARENT);
        webView.setFocusable(true);
        webView.setFocusableInTouchMode(true);
        fullscreenContainer.addView(webView,new FrameLayout.LayoutParams(ViewGroup.LayoutParams.MATCH_PARENT,ViewGroup.LayoutParams.MATCH_PARENT));
        setContentView(fullscreenContainer);
        webView.addJavascriptInterface(new AbajNativeBridge(),"AbajNative");
        WebSettings s=webView.getSettings(); s.setJavaScriptEnabled(true); s.setDomStorageEnabled(true); s.setDatabaseEnabled(true); s.setMediaPlaybackRequiresUserGesture(false); s.setCacheMode(WebSettings.LOAD_DEFAULT); s.setAllowFileAccess(true); s.setAllowContentAccess(true); if(Build.VERSION.SDK_INT>=Build.VERSION_CODES.LOLLIPOP)s.setMixedContentMode(WebSettings.MIXED_CONTENT_ALWAYS_ALLOW); s.setUserAgentString(s.getUserAgentString()+" AbajTV-Android/"+BuildConfig.VERSION_NAME);
        if(isTv){
            s.setTextZoom(115);
            s.setBuiltInZoomControls(false);
            s.setDisplayZoomControls(false);
        }
        CookieManager.getInstance().setAcceptCookie(true); CookieManager.getInstance().setAcceptThirdPartyCookies(webView,true);
        webView.setWebChromeClient(new WebChromeClient(){
            @Override public void onPermissionRequest(PermissionRequest request){runOnUiThread(()->handleWebPermission(request));}
            @Override public boolean onShowFileChooser(WebView view,ValueCallback<Uri[]> callback,FileChooserParams params){ if(fileCallback!=null)fileCallback.onReceiveValue(null); fileCallback=callback; try{Intent i=params!=null?params.createIntent():new Intent(Intent.ACTION_GET_CONTENT); if(params==null){i.addCategory(Intent.CATEGORY_OPENABLE);i.setType("*/*");} startActivityForResult(i,FILE_CHOOSER_REQUEST);return true;}catch(Exception e){fileCallback=null;return false;}}
            @Override public void onShowCustomView(View view, CustomViewCallback callback){
                if(customView!=null){callback.onCustomViewHidden();return;}
                customView=view;
                customViewCallback=callback;
                fullscreenContainer.addView(view,new FrameLayout.LayoutParams(ViewGroup.LayoutParams.MATCH_PARENT,ViewGroup.LayoutParams.MATCH_PARENT));
                webView.setVisibility(View.GONE);
                getWindow().getDecorView().setSystemUiVisibility(
                    View.SYSTEM_UI_FLAG_FULLSCREEN|
                    View.SYSTEM_UI_FLAG_HIDE_NAVIGATION|
                    View.SYSTEM_UI_FLAG_IMMERSIVE_STICKY
                );
            }
            @Override public void onHideCustomView(){hideCustomView();}
        });
        webView.setWebViewClient(new WebViewClient(){
            @Override public boolean shouldOverrideUrlLoading(WebView view,WebResourceRequest request){ Uri uri=request.getUrl(); String url=uri.toString(), scheme=uri.getScheme()==null?"":uri.getScheme().toLowerCase(), host=uri.getHost()==null?"":uri.getHost().toLowerCase();
                if("facetalk".equals(scheme)&&"auth".equalsIgnoreCase(uri.getHost())){consumeAuthUri(uri);loadOrAuthorize();return true;}
                if("facetalk".equals(scheme)&&"check-update".equalsIgnoreCase(uri.getHost())){if(!BuildConfig.PLAY_STORE_BUILD)checkForAppUpdate(true,true);return true;}
                if(url.endsWith(".apk")||url.contains("/api/app-download")){if(!BuildConfig.PLAY_STORE_BUILD)downloadAndInstallApk(url);return true;}
                if("tg".equals(scheme)||"t.me".equals(host)||"telegram.me".equals(host)){openExternal(uri);return true;}
                if(!"http".equals(scheme)&&!"https".equals(scheme)){openExternal(uri);return true;} return false; }
            @Override public void onPageFinished(WebView view,String url){
                super.onPageFinished(view,url);
                deliverPendingExternalMedia();
            }
        });
        if(!BuildConfig.PLAY_STORE_BUILD)registerApkDownloadReceiver();
        startTvHangWatchdog();
        loadOrAuthorize();
        if(!BuildConfig.PLAY_STORE_BUILD){
            updateHandler.postDelayed(()->checkForAppUpdate(true,false),2500L);
            updateHandler.postDelayed(periodicUpdateCheck,30L*60L*1000L);
        }
    }

    private void ensureNativeProbePlayer(){
        if(!isTv||nativeProbeView==null||nativeProbePlayer!=null)return;
        DefaultLoadControl loadControl=new DefaultLoadControl.Builder()
            .setBufferDurationsMs(500,4000,120,250)
            .setPrioritizeTimeOverSizeThresholds(true)
            .build();
        nativeProbePlayer=new ExoPlayer.Builder(this).setLoadControl(loadControl).build();
        nativeProbeView.setPlayer(nativeProbePlayer);
        nativeProbePlayer.addListener(new Player.Listener(){
            @Override public void onRenderedFirstFrame(){
                long started=nativeProbeStartedAt;
                if(started<=0L)return;
                long elapsed=Math.max(0L,System.currentTimeMillis()-started);
                Log.i("AbajTVNativeProbe","first_frame_ms="+elapsed+" url="+nativeProbeUrl);
                nativeProbeStartedAt=0L;
                if(webView!=null){
                    webView.evaluateJavascript(
                        "if(typeof nativeProbeFirstFrame==='function')nativeProbeFirstFrame("+elapsed+")",
                        null
                    );
                }
            }
            @Override public void onPlayerError(PlaybackException error){
                long started=nativeProbeStartedAt;
                long elapsed=started>0L?Math.max(0L,System.currentTimeMillis()-started):0L;
                String code=error==null?"unknown":error.getErrorCodeName();
                Log.w("AbajTVNativeProbe","error_ms="+elapsed+" code="+code+" url="+nativeProbeUrl);
                nativeProbeStartedAt=0L;
                if(webView!=null){
                    String safe=code.replace("\\","\\\\").replace("'","\\'");
                    webView.evaluateJavascript(
                        "if(typeof nativeProbeError==='function')nativeProbeError('"+safe+"')",
                        null
                    );
                }
                try{nativeProbePlayer.stop();nativeProbePlayer.clearMediaItems();}catch(Exception ignored){}
            }
        });
    }
    private void startNativeProbe(String url){
        if(!isTv||nativeProbeView==null)return;
        try{
            ensureNativeProbePlayer();
            if(nativeProbePlayer==null)return;
            nativeProbeUrl=url;
            nativeProbeStartedAt=System.currentTimeMillis();
            nativeProbePlayer.setMediaItem(MediaItem.fromUri(Uri.parse(url)),true);
            nativeProbePlayer.prepare();
            nativeProbePlayer.play();
        }catch(Exception e){
            Log.w("AbajTVNativeProbe","start_error "+e.getClass().getSimpleName());
            nativeProbeStartedAt=0L;
        }
    }
    private void stopNativeProbe(boolean release){
        nativeProbeStartedAt=0L;
        nativeProbeUrl="";
        if(nativeProbePlayer!=null){
            try{nativeProbePlayer.stop();nativeProbePlayer.clearMediaItems();}catch(Exception ignored){}
            if(release){
                try{nativeProbePlayer.release();}catch(Exception ignored){}
                nativeProbePlayer=null;
                if(nativeProbeView!=null)nativeProbeView.setPlayer(null);
            }
        }
    }

    private void startTvHangWatchdog(){
        if(!isTv)return;
        lastWebHeartbeatAt=System.currentTimeMillis();
        tvWatchdogExecutor.scheduleAtFixedRate(()->{
            if(!activityResumed||webView==null)return;
            long now=System.currentTimeMillis();
            long stale=now-lastWebHeartbeatAt;
            if(stale>=12000L&&!tvRecoveryQueued){
                tvRecoveryQueued=true;
                tvRecoveryStartedAt=now;
                runOnUiThread(()->{
                    try{
                        if(webView!=null){
                            webView.stopLoading();
                            loadOrAuthorize();
                        }
                    }catch(Exception ignored){}
                });
                return;
            }
            if(tvRecoveryQueued&&tvRecoveryStartedAt>0L&&now-tvRecoveryStartedAt>=13000L&&stale>=25000L){
                restartTvProcess();
            }
        },5L,5L,TimeUnit.SECONDS);
    }
    private void restartTvProcess(){
        if(!isTv)return;
        try{
            Intent launch=getPackageManager().getLaunchIntentForPackage(getPackageName());
            if(launch==null)return;
            launch.addFlags(Intent.FLAG_ACTIVITY_NEW_TASK|Intent.FLAG_ACTIVITY_CLEAR_TOP|Intent.FLAG_ACTIVITY_CLEAR_TASK);
            int flags=PendingIntent.FLAG_UPDATE_CURRENT;
            if(Build.VERSION.SDK_INT>=Build.VERSION_CODES.M)flags|=PendingIntent.FLAG_IMMUTABLE;
            PendingIntent pi=PendingIntent.getActivity(this,9917,launch,flags);
            AlarmManager am=(AlarmManager)getSystemService(Context.ALARM_SERVICE);
            if(am!=null)am.setExact(AlarmManager.ELAPSED_REALTIME_WAKEUP,android.os.SystemClock.elapsedRealtime()+1200L,pi);
            android.os.Process.killProcess(android.os.Process.myPid());
        }catch(Exception ignored){}
    }

    private void enterTvImmersive(){
        if(!isTv)return;
        getWindow().getDecorView().setSystemUiVisibility(
            View.SYSTEM_UI_FLAG_FULLSCREEN|
            View.SYSTEM_UI_FLAG_HIDE_NAVIGATION|
            View.SYSTEM_UI_FLAG_IMMERSIVE_STICKY|
            View.SYSTEM_UI_FLAG_LAYOUT_FULLSCREEN|
            View.SYSTEM_UI_FLAG_LAYOUT_HIDE_NAVIGATION|
            View.SYSTEM_UI_FLAG_LAYOUT_STABLE
        );
    }

    private String baseUrl(){String b=BuildConfig.WEB_APP_URL==null?"":BuildConfig.WEB_APP_URL.trim(); if(!b.startsWith("http://")&&!b.startsWith("https://")&&!b.isEmpty())b="https://"+b; while(b.endsWith("/"))b=b.substring(0,b.length()-1); return b;}
    private String ensureAuthNonce(){String n=prefs.getString("app_auth_nonce","");if(n==null||n.trim().isEmpty()){n=UUID.randomUUID().toString().replace("-","");prefs.edit().putString("app_auth_nonce",n).apply();}return n;}
    private boolean hasSignedAuth(){return !prefs.getString("ft_uid","").isEmpty()&&!prefs.getString("ft_ts","").isEmpty()&&!prefs.getString("ft_sig","").isEmpty();}
    private void loadOrAuthorize(){
        String init=prefs.getString("telegram_init_data","");
        if(!isTv&&!hasSignedAuth()){
            String nonce=ensureAuthNonce();
            showTelegramLinkScreen();
            if(!telegramLaunchAttempted){telegramLaunchAttempted=true;openExternal(Uri.parse(baseUrl()+"/api/app-auth/telegram-start?nonce="+Uri.encode(nonce)));}
            return;
        }
        if(isTv&&(init==null||init.trim().isEmpty())&&!hasSignedAuth()){loadAbajTv("");return;}
        loadAbajTv(init==null?"":init);
    }
    private void showTelegramLinkScreen(){String nonce=ensureAuthNonce();String updateButton=BuildConfig.PLAY_STORE_BUILD?"":"<button class='s' onclick=\"location.href='facetalk://check-update'\">Проверить обновление</button>";String h="<!doctype html><html><head><meta name='viewport' content='width=device-width,initial-scale=1'><style>body{margin:0;background:linear-gradient(180deg,#061f59,#009cff);color:#fff;font-family:sans-serif;display:flex;align-items:center;justify-content:center;min-height:100vh;text-align:center;padding:24px;box-sizing:border-box}.b{max-width:380px;background:rgba(3,20,64,.78);border:1px solid rgba(255,255,255,.18);border-radius:24px;padding:28px;box-shadow:0 15px 45px rgba(0,0,0,.35)}p{color:#d6edff;line-height:1.5}button{width:100%;margin-top:14px;border:0;border-radius:15px;padding:15px;background:#00a6ff;color:white;font-weight:800;font-size:16px}.s{background:#123b78}</style></head><body><div class='b'><h2>Abaj TV</h2><p>Привяжите приложение к Telegram. После подтверждения просто вернитесь сюда.</p><button onclick=\"location.href='"+baseUrl()+"/api/app-auth/telegram-start?nonce="+Uri.encode(nonce)+"'\">Привязать через Telegram</button>"+updateButton+"</div></body></html>"; webView.loadDataWithBaseURL("https://abajtv.local/",h,"text/html","UTF-8",null);}
    private void loadAbajTv(String init){
        String b=baseUrl();
        if(b.isEmpty()){showTelegramLinkScreen();return;}
        int p=b.indexOf('#'); if(p>=0)b=b.substring(0,p);
        String sep=b.contains("?")?"&":"?";
        String source=isTv?"android_tv":"android";
        String tv=isTv?"&tv=1":"";
        String fragment=(init!=null&&!init.trim().isEmpty())
            ?"#tgWebAppData="+Uri.encode(init)+"&tgWebAppVersion=8.0&tgWebAppPlatform="+(isTv?"android_tv":"android")
            :"";
        String deviceName=isTv?(android.os.Build.MANUFACTURER+" "+android.os.Build.MODEL).trim():"Android";
        String uid=prefs.getString("ft_uid",""); String ts=prefs.getString("ft_ts",""); String sig=prefs.getString("ft_sig","");
        String signedAuth=(!uid.isEmpty()&&!ts.isEmpty()&&!sig.isEmpty())?("&ft_uid="+Uri.encode(uid)+"&ft_ts="+Uri.encode(ts)+"&ft_sig="+Uri.encode(sig)):"";
        webView.loadUrl(b+sep+"app=1&source="+source+tv+"&device_name="+Uri.encode(deviceName)+"&app_version="+Uri.encode(BuildConfig.VERSION_NAME)+"&app_version_code="+BuildConfig.VERSION_CODE+signedAuth+"&ota="+System.currentTimeMillis()+fragment);
        webView.requestFocus();
    }
    private boolean consumeExternalMediaIntent(Intent i){
        if(i==null||!Intent.ACTION_VIEW.equals(i.getAction()))return false;
        Uri data=i.getData();
        if(data==null)return false;
        String scheme=data.getScheme()==null?"":data.getScheme().toLowerCase();
        if("facetalk".equals(scheme))return false;
        String type=i.getType()==null?"":i.getType().toLowerCase();
        boolean mediaType=type.startsWith("video/")||type.contains("mpegurl")||type.contains("dash+xml");
        String raw=data.toString();
        String low=raw.toLowerCase();
        boolean mediaUrl=low.contains(".m3u8")||low.contains(".mp4")||low.contains(".mkv")||low.contains(".webm")||low.contains(".mpd");
        if(!mediaType&&!mediaUrl)return false;
        pendingExternalMediaUrl=raw;
        String title=i.getStringExtra(Intent.EXTRA_TITLE);
        pendingExternalMediaTitle=title==null?"":title;
        if(webView!=null)runOnUiThread(this::deliverPendingExternalMedia);
        return true;
    }
    private void deliverPendingExternalMedia(){
        if(webView==null)return;
        String url=pendingExternalMediaUrl;
        if(url==null||url.isEmpty())return;
        String title=pendingExternalMediaTitle==null?"":pendingExternalMediaTitle;
        pendingExternalMediaUrl="";
        pendingExternalMediaTitle="";
        String js="window.__abajOpenExternalMedia&&window.__abajOpenExternalMedia("+
            JSONObject.quote(url)+","+JSONObject.quote(title)+");";
        try{webView.evaluateJavascript(js,null);}catch(Exception ignored){}
    }
    private void consumeAuthIntent(Intent i){if(i!=null){consumeAuthUri(i.getData());consumeExternalMediaIntent(i);}}
    private void saveSignedAuth(String uid,String ts,String sig){if(uid==null||ts==null||sig==null||uid.isEmpty()||ts.isEmpty()||sig.isEmpty())return;prefs.edit().putString("ft_uid",uid).putString("ft_ts",ts).putString("ft_sig",sig).remove("app_auth_nonce").apply();}
    private void checkPendingAppAuth(){
        if(isTv||hasSignedAuth())return;
        String nonce=prefs.getString("app_auth_nonce","");
        if(nonce==null||nonce.isEmpty())return;
        new Thread(()->{
            HttpURLConnection c=null;
            try{
                c=(HttpURLConnection)new URL(baseUrl()+"/api/app-auth/status?nonce="+Uri.encode(nonce)).openConnection();
                c.setConnectTimeout(8000);c.setReadTimeout(8000);c.setUseCaches(false);
                if(c.getResponseCode()!=200)return;
                BufferedReader br=new BufferedReader(new InputStreamReader(c.getInputStream()));StringBuilder sb=new StringBuilder();String line;while((line=br.readLine())!=null)sb.append(line);br.close();
                JSONObject j=new JSONObject(sb.toString());
                if(!j.optBoolean("paired",false))return;
                String uid=j.optString("ft_uid","");String ts=j.optString("ft_ts","");String sig=j.optString("ft_sig","");
                if(uid.isEmpty()||ts.isEmpty()||sig.isEmpty())return;
                saveSignedAuth(uid,ts,sig);
                runOnUiThread(()->{Toast.makeText(this,"Telegram подключён",Toast.LENGTH_SHORT).show();loadAbajTv("");});
            }catch(Exception ignored){}finally{if(c!=null)c.disconnect();}
        },"abajtv-auth-check").start();
    }
    private void consumeAuthUri(Uri u){if(u==null||!"facetalk".equalsIgnoreCase(u.getScheme())||!"auth".equalsIgnoreCase(u.getHost()))return; String init=u.getQueryParameter("init_data"); String uid=u.getQueryParameter("ft_uid"); String ts=u.getQueryParameter("ft_ts"); String sig=u.getQueryParameter("ft_sig"); if((init==null||init.trim().isEmpty())&&(uid==null||uid.trim().isEmpty()))return; android.content.SharedPreferences.Editor ed=prefs.edit(); if(init!=null&&!init.trim().isEmpty())ed.putString("telegram_init_data",init); ed.apply(); saveSignedAuth(uid,ts,sig); telegramLaunchAttempted=true;Toast.makeText(this,"Telegram подключён",Toast.LENGTH_SHORT).show();}
    @Override protected void onNewIntent(Intent intent){
        super.onNewIntent(intent);
        setIntent(intent);
        boolean media=consumeExternalMediaIntent(intent);
        if(!media){
            consumeAuthUri(intent==null?null:intent.getData());
            loadOrAuthorize();
        }
    }

    private void checkForAppUpdate(boolean force,boolean showResult){String b=baseUrl(); if(b.isEmpty()||updateCheckRunning||updateDownloadRunning)return; long n=System.currentTimeMillis(); if(!force&&n-lastUpdateCheckAt<60000L)return; lastUpdateCheckAt=n;updateCheckRunning=true; new Thread(()->{HttpURLConnection c=null;try{URL u=new URL(b+"/api/app-release?ts="+System.currentTimeMillis());c=(HttpURLConnection)u.openConnection();c.setConnectTimeout(10000);c.setReadTimeout(10000);c.setUseCaches(false);c.setRequestProperty("Cache-Control","no-cache");int http=c.getResponseCode();if(http!=200)throw new IllegalStateException("HTTP "+http);BufferedReader br=new BufferedReader(new InputStreamReader(c.getInputStream()));StringBuilder sb=new StringBuilder();String line;while((line=br.readLine())!=null)sb.append(line);br.close();JSONObject j=new JSONObject(sb.toString());boolean available=j.optBoolean("available",false);int latest=j.optInt("version_code",0);String download=j.optString("download_url",""); if(!available||latest<=0||download.isEmpty()){if(showResult)runOnUiThread(()->Toast.makeText(this,"Новая APK ещё не опубликована на сервер обновлений",Toast.LENGTH_LONG).show());return;} if(latest<=BuildConfig.VERSION_CODE){if(showResult)runOnUiThread(()->Toast.makeText(this,"Установлена последняя версия",Toast.LENGTH_LONG).show());return;} if(!showResult){int lastCode=prefs.getInt("last_auto_update_code",0);long lastAt=prefs.getLong("last_auto_update_at",0L);if(lastCode==latest&&System.currentTimeMillis()-lastAt<24L*60L*60L*1000L)return;} final String url=download.startsWith("http")?download:b+download; if(!showResult)prefs.edit().putInt("last_auto_update_code",latest).putLong("last_auto_update_at",System.currentTimeMillis()).apply();runOnUiThread(()->{if(!isFinishing()&&!updateDownloadRunning){Toast.makeText(this,"Найдено обновление Abaj TV. Загружаю…",Toast.LENGTH_LONG).show();downloadAndInstallApk(url);}});}catch(Exception e){if(showResult)runOnUiThread(()->Toast.makeText(this,"Сервер обновлений недоступен",Toast.LENGTH_LONG).show());}finally{updateCheckRunning=false;if(c!=null)c.disconnect();}},"abajtv-update-check").start();}

    private void finishApkDownload(long id){if(id<=0||id!=pendingApkDownloadId)return;DownloadManager dm=(DownloadManager)getSystemService(DOWNLOAD_SERVICE);if(dm==null)return;DownloadManager.Query q=new DownloadManager.Query().setFilterById(id);try(Cursor cur=dm.query(q)){if(cur==null||!cur.moveToFirst())return;int status=cur.getInt(cur.getColumnIndexOrThrow(DownloadManager.COLUMN_STATUS));if(status==DownloadManager.STATUS_SUCCESSFUL){pendingApkDownloadId=-1L;updateDownloadRunning=false;pendingApkUri=dm.getUriForDownloadedFile(id);runOnUiThread(this::requestInstallOrOpen);return;}if(status==DownloadManager.STATUS_FAILED){int reason=cur.getInt(cur.getColumnIndexOrThrow(DownloadManager.COLUMN_REASON));pendingApkDownloadId=-1L;updateDownloadRunning=false;runOnUiThread(()->Toast.makeText(MainActivity.this,"Ошибка загрузки обновления ("+reason+")",Toast.LENGTH_LONG).show());}}catch(Exception ignored){}}
    private void pollApkDownload(long id,int attempt){if(id<=0||id!=pendingApkDownloadId)return;finishApkDownload(id);if(id!=pendingApkDownloadId)return;if(attempt>=300){pendingApkDownloadId=-1L;updateDownloadRunning=false;runOnUiThread(()->Toast.makeText(MainActivity.this,"Загрузка обновления не завершилась",Toast.LENGTH_LONG).show());return;}updateHandler.postDelayed(()->pollApkDownload(id,attempt+1),1000L);}
    private void registerApkDownloadReceiver(){if(downloadReceiver!=null)return;downloadReceiver=new BroadcastReceiver(){@Override public void onReceive(Context context,Intent intent){if(!DownloadManager.ACTION_DOWNLOAD_COMPLETE.equals(intent.getAction()))return;long id=intent.getLongExtra(DownloadManager.EXTRA_DOWNLOAD_ID,-1L);finishApkDownload(id);}};IntentFilter f=new IntentFilter(DownloadManager.ACTION_DOWNLOAD_COMPLETE);if(Build.VERSION.SDK_INT>=33)registerReceiver(downloadReceiver,f,Context.RECEIVER_EXPORTED);else registerReceiver(downloadReceiver,f);}
    private void downloadAndInstallApk(String rawUrl){
        if(rawUrl==null||rawUrl.trim().isEmpty()||updateDownloadRunning)return;
        updateDownloadRunning=true;
        pendingApkDownloadId=-1L;
        pendingApkUri=null;
        new Thread(()->{
            HttpURLConnection c=null;
            try{
                URL u=new URL(rawUrl);
                c=(HttpURLConnection)u.openConnection();
                c.setConnectTimeout(15000);
                c.setReadTimeout(60000);
                c.setInstanceFollowRedirects(true);
                c.setUseCaches(false);
                c.setRequestProperty("Cache-Control","no-cache");
                c.setRequestProperty("User-Agent","AbajTV-Updater/"+BuildConfig.VERSION_NAME);
                int code=c.getResponseCode();
                if(code<200||code>=300)throw new IllegalStateException("HTTP "+code);
                File dir=getExternalFilesDir(Environment.DIRECTORY_DOWNLOADS);
                if(dir==null)throw new IllegalStateException("No downloads directory");
                if(!dir.exists()&&!dir.mkdirs())throw new IllegalStateException("Cannot create downloads directory");
                File apk=new File(dir,"AbajTV-update-"+System.currentTimeMillis()+".apk");
                long total=0;
                try(InputStream in=c.getInputStream();FileOutputStream out=new FileOutputStream(apk)){
                    byte[] buf=new byte[65536]; int n;
                    while((n=in.read(buf))!=-1){out.write(buf,0,n);total+=n;}
                    out.flush();
                }
                if(total<300000L)throw new IllegalStateException("APK too small: "+total);
                Uri uri=FileProvider.getUriForFile(this,getPackageName()+".fileprovider",apk);
                pendingApkUri=uri;
                updateDownloadRunning=false;
                runOnUiThread(this::requestInstallOrOpen);
            }catch(Exception ex){
                updateDownloadRunning=false;
                runOnUiThread(()->Toast.makeText(this,"Ошибка загрузки обновления: "+ex.getMessage(),Toast.LENGTH_LONG).show());
            }finally{if(c!=null)c.disconnect();}
        },"abajtv-apk-download").start();
    }
    private void requestInstallOrOpen(){if(pendingApkUri==null)return;if(Build.VERSION.SDK_INT>=Build.VERSION_CODES.O&&!getPackageManager().canRequestPackageInstalls()){try{startActivity(new Intent(Settings.ACTION_MANAGE_UNKNOWN_APP_SOURCES,Uri.parse("package:"+getPackageName())));Toast.makeText(this,"Разрешите Abaj TV устанавливать обновления",Toast.LENGTH_LONG).show();}catch(Exception ignored){}return;}Uri u=pendingApkUri;pendingApkUri=null;openPackageInstaller(u);}
    private void openPackageInstaller(Uri apkUri){if(apkUri==null)return;try{Intent install=new Intent(Intent.ACTION_VIEW);install.setDataAndType(apkUri,"application/vnd.android.package-archive");install.addFlags(Intent.FLAG_GRANT_READ_URI_PERMISSION|Intent.FLAG_ACTIVITY_NEW_TASK);startActivity(install);}catch(Exception e){Toast.makeText(this,"APK скачан, но установщик не открылся",Toast.LENGTH_LONG).show();}}
    private void handleWebPermission(PermissionRequest r){if(r==null)return;if(BuildConfig.PLAY_STORE_BUILD){r.deny();return;}boolean mic=false,cam=false;for(String x:r.getResources()){if(PermissionRequest.RESOURCE_AUDIO_CAPTURE.equals(x))mic=true;if(PermissionRequest.RESOURCE_VIDEO_CAPTURE.equals(x))cam=true;}boolean mg=!mic||Build.VERSION.SDK_INT<23||checkSelfPermission(Manifest.permission.RECORD_AUDIO)==PackageManager.PERMISSION_GRANTED;boolean cg=!cam||Build.VERSION.SDK_INT<23||checkSelfPermission(Manifest.permission.CAMERA)==PackageManager.PERMISSION_GRANTED;if(mg&&cg){r.grant(r.getResources());return;}pendingWebPermission=r;if(Build.VERSION.SDK_INT>=23)requestPermissions(new String[]{Manifest.permission.RECORD_AUDIO,Manifest.permission.CAMERA},MEDIA_PERMISSION_REQUEST);else r.grant(r.getResources());}
    @Override public void onRequestPermissionsResult(int requestCode,String[] permissions,int[] grantResults){super.onRequestPermissionsResult(requestCode,permissions,grantResults);if(requestCode!=MEDIA_PERMISSION_REQUEST||pendingWebPermission==null)return;PermissionRequest r=pendingWebPermission;pendingWebPermission=null;boolean ok=true;for(int x:grantResults)if(x!=PackageManager.PERMISSION_GRANTED)ok=false;if(ok)r.grant(r.getResources());else r.deny();}
    @Override protected void onActivityResult(int requestCode,int resultCode,Intent data){super.onActivityResult(requestCode,resultCode,data);if(requestCode!=FILE_CHOOSER_REQUEST||fileCallback==null)return;fileCallback.onReceiveValue(WebChromeClient.FileChooserParams.parseResult(resultCode,data));fileCallback=null;}
    private void updatePictureInPictureParams(){
        if(isTv||Build.VERSION.SDK_INT<Build.VERSION_CODES.O)return;
        try{
            PictureInPictureParams.Builder b=new PictureInPictureParams.Builder()
                .setAspectRatio(new Rational(16,9));
            if(Build.VERSION.SDK_INT>=Build.VERSION_CODES.S){
                b.setAutoEnterEnabled(pipPlaybackActive);
                b.setSeamlessResizeEnabled(true);
            }
            setPictureInPictureParams(b.build());
        }catch(Exception ignored){}
    }

    private void enterAbajPictureInPicture(){
        if(isTv||!pipPlaybackActive||Build.VERSION.SDK_INT<Build.VERSION_CODES.O||isInPictureInPictureMode())return;
        try{
            PictureInPictureParams.Builder b=new PictureInPictureParams.Builder()
                .setAspectRatio(new Rational(16,9));
            if(Build.VERSION.SDK_INT>=Build.VERSION_CODES.S){
                b.setAutoEnterEnabled(true);
                b.setSeamlessResizeEnabled(true);
            }
            enterPictureInPictureMode(b.build());
        }catch(Exception ignored){}
    }

    @Override protected void onUserLeaveHint(){
        super.onUserLeaveHint();
        if(!isTv&&pipPlaybackActive&&Build.VERSION.SDK_INT>=Build.VERSION_CODES.O&&Build.VERSION.SDK_INT<Build.VERSION_CODES.S){
            enterAbajPictureInPicture();
        }
    }

    @Override public void onPictureInPictureModeChanged(boolean isInPictureInPictureMode, Configuration newConfig){
        super.onPictureInPictureModeChanged(isInPictureInPictureMode,newConfig);
        if(webView!=null){
            webView.evaluateJavascript(
                "if(typeof setNativePipMode==='function')setNativePipMode("+(isInPictureInPictureMode?"true":"false")+")",
                null
            );
        }
    }

    @Override protected void onPause(){
        activityResumed=false;
        if(isTv&&webView!=null){
            webView.evaluateJavascript("if(typeof suspendTvPlayback==='function')suspendTvPlayback()",null);
        }
        super.onPause();
    }

    @Override protected void onResume(){
        super.onResume();
        activityResumed=true;
        lastWebHeartbeatAt=System.currentTimeMillis();
        tvRecoveryQueued=false;
        tvRecoveryStartedAt=0L;
        enterTvImmersive();
        if(!isTv)checkPendingAppAuth();
        if(isTv&&webView!=null){
            webView.evaluateJavascript("if(typeof resumeTvPlayback==='function')resumeTvPlayback();if(typeof load==='function'&&!document.getElementById('playerView')?.classList.contains('open'))load();if(typeof refreshTvAuth==='function')refreshTvAuth(true)",null);
        }
        if(!BuildConfig.PLAY_STORE_BUILD&&pendingApkUri!=null&&(Build.VERSION.SDK_INT<Build.VERSION_CODES.O||getPackageManager().canRequestPackageInstalls())){
            Uri u=pendingApkUri;pendingApkUri=null;openPackageInstaller(u);
        }else if(!BuildConfig.PLAY_STORE_BUILD)checkForAppUpdate(true,false);
    }

    @Override public void onWindowFocusChanged(boolean hasFocus){
        super.onWindowFocusChanged(hasFocus);
        if(hasFocus)enterTvImmersive();
    }
    private void hideCustomView(){
        if(customView==null)return;
        try{fullscreenContainer.removeView(customView);}catch(Exception ignored){}
        customView=null;
        if(customViewCallback!=null){try{customViewCallback.onCustomViewHidden();}catch(Exception ignored){}}
        customViewCallback=null;
        webView.setVisibility(View.VISIBLE);
        getWindow().getDecorView().setSystemUiVisibility(View.SYSTEM_UI_FLAG_VISIBLE);
    }

    @Override public boolean dispatchKeyEvent(KeyEvent event){
        if(isTv&&webView!=null){
            int code=event.getKeyCode();
            if(code==KeyEvent.KEYCODE_DPAD_CENTER||code==KeyEvent.KEYCODE_ENTER){
                if(event.getAction()==KeyEvent.ACTION_DOWN){
                    if(event.getRepeatCount()==0){
                        webView.evaluateJavascript(
                            "if(typeof tvNativeOkDown==='function')tvNativeOkDown();else if(typeof tvNativeRemote==='function')tvNativeRemote('ok')",
                            null
                        );
                    }
                    return true;
                }
                if(event.getAction()==KeyEvent.ACTION_UP){
                    webView.evaluateJavascript(
                        "if(typeof tvNativeOkUp==='function')tvNativeOkUp()",
                        null
                    );
                    return true;
                }
            }
            if(event.getAction()==KeyEvent.ACTION_DOWN){
                if(code==KeyEvent.KEYCODE_BACK){
                    onBackPressed();
                    return true;
                }
                if(code==KeyEvent.KEYCODE_DPAD_UP||code==KeyEvent.KEYCODE_DPAD_DOWN||code==KeyEvent.KEYCODE_DPAD_LEFT||code==KeyEvent.KEYCODE_DPAD_RIGHT){
                    String action="";
                    if(code==KeyEvent.KEYCODE_DPAD_UP)action="up";
                    else if(code==KeyEvent.KEYCODE_DPAD_DOWN)action="down";
                    else if(code==KeyEvent.KEYCODE_DPAD_LEFT)action="left";
                    else action="right";
                    if(code==KeyEvent.KEYCODE_DPAD_LEFT||code==KeyEvent.KEYCODE_DPAD_RIGHT){
                        if(event.getRepeatCount()>0)return true;
                        long now=System.currentTimeMillis();
                        if(now-lastTvChannelKeyAt<180L)return true;
                        lastTvChannelKeyAt=now;
                    }
                    webView.evaluateJavascript("if(typeof tvNativeRemote==='function')tvNativeRemote('"+action+"')",null);
                    return true;
                }
            if(code>=KeyEvent.KEYCODE_0&&code<=KeyEvent.KEYCODE_9){
                int digit=code-KeyEvent.KEYCODE_0;
                webView.evaluateJavascript("if(typeof tvTuneDigit==='function')tvTuneDigit('"+digit+"')",null);
                return true;
            }
            if(code==KeyEvent.KEYCODE_LAST_CHANNEL){
                webView.evaluateJavascript("if(typeof playPreviousChannel==='function')playPreviousChannel()",null);
                return true;
            }
            if(code==KeyEvent.KEYCODE_MEDIA_PLAY_PAUSE||code==KeyEvent.KEYCODE_SPACE){
                webView.evaluateJavascript("(function(){var v=document.getElementById('video');if(v){if(v.paused){v.play()}else{v.pause()}}})()",null);
                return true;
            }
            if(code==KeyEvent.KEYCODE_MEDIA_NEXT||code==KeyEvent.KEYCODE_CHANNEL_UP||code==KeyEvent.KEYCODE_PAGE_DOWN){
                webView.evaluateJavascript("if(typeof playNext==='function')playNext()",null);
                return true;
            }
            if(code==KeyEvent.KEYCODE_MEDIA_PREVIOUS||code==KeyEvent.KEYCODE_CHANNEL_DOWN||code==KeyEvent.KEYCODE_PAGE_UP){
                webView.evaluateJavascript("if(typeof playPrev==='function')playPrev()",null);
                return true;
            }
            if(code==KeyEvent.KEYCODE_MENU){
                webView.evaluateJavascript("(function(){var p=document.getElementById('playerView');if(p&&p.classList.contains('open')){if(typeof toggleTvRail==='function')toggleTvRail()}else if(typeof openTvSettings==='function'){openTvSettings()}})()",null);
                return true;
            }
            if(code==KeyEvent.KEYCODE_PROG_RED){
                webView.evaluateJavascript("if(typeof tvSetModeFilter==='function')tvSetModeFilter('all')",null);
                return true;
            }
            if(code==KeyEvent.KEYCODE_PROG_GREEN){
                webView.evaluateJavascript("if(typeof tvSetModeFilter==='function')tvSetModeFilter('fav')",null);
                return true;
            }
            if(code==KeyEvent.KEYCODE_PROG_YELLOW){
                webView.evaluateJavascript("if(typeof tvSetModeFilter==='function')tvSetModeFilter('recent')",null);
                return true;
            }
            if(code==KeyEvent.KEYCODE_PROG_BLUE||code==KeyEvent.KEYCODE_STAR){
                webView.evaluateJavascript("(function(){var p=document.getElementById('playerView');if(p&&p.classList.contains('open')){if(typeof tvToggleFavoriteCurrent==='function')tvToggleFavoriteCurrent()}else if(typeof tvSetModeFilter==='function'){tvSetModeFilter('fav')}})()",null);
                return true;
            }
            if(code==KeyEvent.KEYCODE_GUIDE){
                webView.evaluateJavascript("if(typeof toggleTvGuide==='function')toggleTvGuide()",null);
                return true;
            }
            if(code==KeyEvent.KEYCODE_SEARCH){
                webView.evaluateJavascript("if(typeof openTvSearch==='function')openTvSearch()",null);
                return true;
            }
            if(code==KeyEvent.KEYCODE_INFO){
                webView.evaluateJavascript("if(typeof tvTogglePlayerUi==='function')tvTogglePlayerUi()",null);
                return true;
            }
            }
        }
        return super.dispatchKeyEvent(event);
    }

    private void openExternal(Uri uri){if(uri==null)return;try{String s=uri.getScheme()==null?"":uri.getScheme().toLowerCase(),h=uri.getHost()==null?"":uri.getHost().toLowerCase();if("tg".equals(s)||"t.me".equals(h)||"telegram.me".equals(h)){Intent t=new Intent(Intent.ACTION_VIEW,uri);t.setPackage("org.telegram.messenger");try{startActivity(t);return;}catch(Exception ignored){}}startActivity(new Intent(Intent.ACTION_VIEW,uri));}catch(Exception ignored){}}
    @Override protected void onDestroy(){activityResumed=false;updateHandler.removeCallbacksAndMessages(null);try{tvWatchdogExecutor.shutdownNow();}catch(Exception ignored){}if(downloadReceiver!=null){try{unregisterReceiver(downloadReceiver);}catch(Exception ignored){}}stopNativeProbe(true);if(webView!=null)webView.destroy();super.onDestroy();}
    @Override public void onBackPressed(){
        if(customView!=null){hideCustomView();return;}
        if(isTv&&webView!=null){
            final boolean[] answered={false};
            updateHandler.postDelayed(()->{
                if(answered[0]||isFinishing())return;
                answered[0]=true;
                lastWebHeartbeatAt=System.currentTimeMillis();
                try{
                    webView.stopLoading();
                    loadOrAuthorize();
                }catch(Exception ignored){}
            },800L);
            webView.evaluateJavascript(
                "(function(){try{return (typeof handleTvBack==='function')?handleTvBack():false}catch(e){return false}})()",
                value->{
                    if(answered[0])return;
                    answered[0]=true;
                    if("true".equals(value)){
                        lastTvBackAt=0L;
                        return;
                    }
                    long now=System.currentTimeMillis();
                    if(now-lastTvBackAt<=1500L){
                        finish();
                        return;
                    }
                    lastTvBackAt=now;
                    webView.evaluateJavascript("if(typeof showTvShortcut==='function')showTvShortcut('Нажмите Назад ещё раз для выхода')",null);
                }
            );
            return;
        }
        if(webView!=null){
            webView.evaluateJavascript(
                "(function(){try{return (typeof handleAppBack==='function')?handleAppBack():false}catch(e){return false}})()",
                value->{
                    if("true".equals(value))return;
                    if(webView.canGoBack())webView.goBack();
                    else super.onBackPressed();
                }
            );
            return;
        }
        super.onBackPressed();
    }
}
