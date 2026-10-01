package ai.facetalk.app;

import android.Manifest;
import android.app.Activity;
import android.app.DownloadManager;
import android.app.UiModeManager;
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
import android.webkit.CookieManager;
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
import android.widget.FrameLayout;

import org.json.JSONObject;

import java.io.BufferedReader;
import java.io.InputStreamReader;
import java.net.HttpURLConnection;
import java.net.URL;

public class MainActivity extends Activity {
    private static final int FILE_CHOOSER_REQUEST=4101, MEDIA_PERMISSION_REQUEST=4102;
    private WebView webView; private ValueCallback<Uri[]> fileCallback; private PermissionRequest pendingWebPermission;
    private View customView; private WebChromeClient.CustomViewCallback customViewCallback;
    private FrameLayout fullscreenContainer;
    private SharedPreferences prefs; private boolean telegramLaunchAttempted=false; private boolean isTv=false; private long lastTvBackAt=0L;
    private long pendingApkDownloadId=-1L; private Uri pendingApkUri; private BroadcastReceiver downloadReceiver;
    private volatile boolean updateCheckRunning=false, updateDownloadRunning=false; private long lastUpdateCheckAt=0L;
    private final Handler updateHandler=new Handler(Looper.getMainLooper());
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
        webView=new WebView(this);
        webView.setBackgroundColor(Color.rgb(0,32,96));
        webView.setFocusable(true);
        webView.setFocusableInTouchMode(true);
        fullscreenContainer.addView(webView,new FrameLayout.LayoutParams(ViewGroup.LayoutParams.MATCH_PARENT,ViewGroup.LayoutParams.MATCH_PARENT));
        setContentView(fullscreenContainer);
        WebSettings s=webView.getSettings(); s.setJavaScriptEnabled(true); s.setDomStorageEnabled(true); s.setDatabaseEnabled(true); s.setMediaPlaybackRequiresUserGesture(false); s.setCacheMode(WebSettings.LOAD_NO_CACHE); s.setAllowFileAccess(true); s.setAllowContentAccess(true); s.setUserAgentString(s.getUserAgentString()+" AbajTV-Android/"+BuildConfig.VERSION_NAME); webView.clearCache(true);
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
                if("facetalk".equals(scheme)&&"check-update".equalsIgnoreCase(uri.getHost())){checkForAppUpdate(true,true);return true;}
                if(url.endsWith(".apk")||url.contains("/api/app-download")){downloadAndInstallApk(url);return true;}
                if("tg".equals(scheme)||"t.me".equals(host)||"telegram.me".equals(host)){openExternal(uri);return true;}
                if(!"http".equals(scheme)&&!"https".equals(scheme)){openExternal(uri);return true;} return false; }
        });
        registerApkDownloadReceiver();
        loadOrAuthorize();
        if(!isTv){
            updateHandler.postDelayed(()->checkForAppUpdate(true,false),2500L);
            updateHandler.postDelayed(periodicUpdateCheck,30L*60L*1000L);
        }
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
    private void loadOrAuthorize(){
        String init=prefs.getString("telegram_init_data","");
        if(init==null||init.trim().isEmpty()){
            if(isTv){
                loadAbajTv("");
                return;
            }
            showTelegramLinkScreen();
            if(!telegramLaunchAttempted){
                telegramLaunchAttempted=true;
                openExternal(Uri.parse(baseUrl()+"/api/app-auth/telegram-start"));
            }
            return;
        }
        loadAbajTv(init);
    }
    private void showTelegramLinkScreen(){String h="<!doctype html><html><head><meta name='viewport' content='width=device-width,initial-scale=1'><style>body{margin:0;background:linear-gradient(180deg,#061f59,#009cff);color:#fff;font-family:sans-serif;display:flex;align-items:center;justify-content:center;min-height:100vh;text-align:center;padding:24px;box-sizing:border-box}.b{max-width:380px;background:rgba(3,20,64,.78);border:1px solid rgba(255,255,255,.18);border-radius:24px;padding:28px;box-shadow:0 15px 45px rgba(0,0,0,.35)}p{color:#d6edff;line-height:1.5}button{width:100%;margin-top:14px;border:0;border-radius:15px;padding:15px;background:#00a6ff;color:white;font-weight:800;font-size:16px}.s{background:#123b78}</style></head><body><div class='b'><h2>Abaj TV</h2><p>Привяжите приложение к Telegram. После этого откроется ваш профиль Abaj TV.</p><button onclick=\"location.href='"+baseUrl()+"/api/app-auth/telegram-start'\">Привязать через Telegram</button><button class='s' onclick=\"location.href='facetalk://check-update'\">Проверить обновление</button></div></body></html>"; webView.loadDataWithBaseURL("https://abajtv.local/",h,"text/html","UTF-8",null);}
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
        webView.loadUrl(b+sep+"app=1&source="+source+tv+"&device_name="+Uri.encode(deviceName)+"&app_version="+Uri.encode(BuildConfig.VERSION_NAME)+"&app_version_code="+BuildConfig.VERSION_CODE+"&ota="+System.currentTimeMillis()+fragment);
        webView.requestFocus();
    }
    private void consumeAuthIntent(Intent i){if(i!=null)consumeAuthUri(i.getData());}
    private void consumeAuthUri(Uri u){if(u==null||!"facetalk".equalsIgnoreCase(u.getScheme())||!"auth".equalsIgnoreCase(u.getHost()))return; String init=u.getQueryParameter("init_data"); if(init==null||init.trim().isEmpty())return; prefs.edit().putString("telegram_init_data",init).apply();telegramLaunchAttempted=true;Toast.makeText(this,"Telegram подключён",Toast.LENGTH_SHORT).show();}
    @Override protected void onNewIntent(Intent intent){super.onNewIntent(intent);setIntent(intent);consumeAuthIntent(intent);loadOrAuthorize();}

    private void checkForAppUpdate(boolean force,boolean showResult){String b=baseUrl(); if(b.isEmpty()||updateCheckRunning||updateDownloadRunning)return; long n=System.currentTimeMillis(); if(!force&&n-lastUpdateCheckAt<60000L)return; lastUpdateCheckAt=n;updateCheckRunning=true; new Thread(()->{HttpURLConnection c=null;try{URL u=new URL(b+"/api/app-release?ts="+System.currentTimeMillis());c=(HttpURLConnection)u.openConnection();c.setConnectTimeout(10000);c.setReadTimeout(10000);c.setUseCaches(false);c.setRequestProperty("Cache-Control","no-cache");int http=c.getResponseCode();if(http!=200)throw new IllegalStateException("HTTP "+http);BufferedReader br=new BufferedReader(new InputStreamReader(c.getInputStream()));StringBuilder sb=new StringBuilder();String line;while((line=br.readLine())!=null)sb.append(line);br.close();JSONObject j=new JSONObject(sb.toString());boolean available=j.optBoolean("available",false);int latest=j.optInt("version_code",0);String download=j.optString("download_url",""); if(!available||latest<=0||download.isEmpty()){if(showResult)runOnUiThread(()->Toast.makeText(this,"Новая APK ещё не опубликована на сервер обновлений",Toast.LENGTH_LONG).show());return;} if(latest<=BuildConfig.VERSION_CODE){if(showResult)runOnUiThread(()->Toast.makeText(this,"Установлена последняя версия",Toast.LENGTH_LONG).show());return;} final String url=download.startsWith("http")?download:b+download;runOnUiThread(()->{if(!isFinishing()&&!updateDownloadRunning){Toast.makeText(this,"Найдено обновление Abaj TV. Загружаю…",Toast.LENGTH_LONG).show();downloadAndInstallApk(url);}});}catch(Exception e){if(showResult)runOnUiThread(()->Toast.makeText(this,"Сервер обновлений недоступен",Toast.LENGTH_LONG).show());}finally{updateCheckRunning=false;if(c!=null)c.disconnect();}},"abajtv-update-check").start();}

    private void registerApkDownloadReceiver(){if(downloadReceiver!=null)return;downloadReceiver=new BroadcastReceiver(){@Override public void onReceive(Context context,Intent intent){if(!DownloadManager.ACTION_DOWNLOAD_COMPLETE.equals(intent.getAction()))return;long id=intent.getLongExtra(DownloadManager.EXTRA_DOWNLOAD_ID,-1L);if(id!=pendingApkDownloadId)return;DownloadManager dm=(DownloadManager)getSystemService(DOWNLOAD_SERVICE);DownloadManager.Query q=new DownloadManager.Query().setFilterById(id);try(Cursor cur=dm.query(q)){if(cur==null||!cur.moveToFirst())return;int status=cur.getInt(cur.getColumnIndexOrThrow(DownloadManager.COLUMN_STATUS));if(status!=DownloadManager.STATUS_SUCCESSFUL){updateDownloadRunning=false;Toast.makeText(MainActivity.this,"Ошибка загрузки обновления",Toast.LENGTH_LONG).show();return;}}catch(Exception e){updateDownloadRunning=false;return;}updateDownloadRunning=false;pendingApkUri=dm.getUriForDownloadedFile(id);requestInstallOrOpen();}};IntentFilter f=new IntentFilter(DownloadManager.ACTION_DOWNLOAD_COMPLETE);if(Build.VERSION.SDK_INT>=33)registerReceiver(downloadReceiver,f,Context.RECEIVER_NOT_EXPORTED);else registerReceiver(downloadReceiver,f);}
    private void downloadAndInstallApk(String rawUrl){if(rawUrl==null||rawUrl.trim().isEmpty()||updateDownloadRunning)return;try{DownloadManager.Request req=new DownloadManager.Request(Uri.parse(rawUrl));req.setTitle("Abaj TV");req.setDescription("Загрузка обновления…");req.setMimeType("application/vnd.android.package-archive");req.setNotificationVisibility(DownloadManager.Request.VISIBILITY_VISIBLE_NOTIFY_COMPLETED);req.setAllowedOverMetered(true);req.setAllowedOverRoaming(true);req.setDestinationInExternalFilesDir(this,Environment.DIRECTORY_DOWNLOADS,"AbajTV-update.apk");DownloadManager dm=(DownloadManager)getSystemService(DOWNLOAD_SERVICE);pendingApkUri=null;updateDownloadRunning=true;pendingApkDownloadId=dm.enqueue(req);}catch(Exception e){updateDownloadRunning=false;Toast.makeText(this,"Не удалось загрузить обновление",Toast.LENGTH_LONG).show();}}
    private void requestInstallOrOpen(){if(pendingApkUri==null)return;if(Build.VERSION.SDK_INT>=Build.VERSION_CODES.O&&!getPackageManager().canRequestPackageInstalls()){try{startActivity(new Intent(Settings.ACTION_MANAGE_UNKNOWN_APP_SOURCES,Uri.parse("package:"+getPackageName())));Toast.makeText(this,"Разрешите Abaj TV устанавливать обновления",Toast.LENGTH_LONG).show();}catch(Exception ignored){}return;}Uri u=pendingApkUri;pendingApkUri=null;openPackageInstaller(u);}
    private void openPackageInstaller(Uri apkUri){if(apkUri==null)return;try{Intent install=new Intent(Intent.ACTION_VIEW);install.setDataAndType(apkUri,"application/vnd.android.package-archive");install.addFlags(Intent.FLAG_GRANT_READ_URI_PERMISSION|Intent.FLAG_ACTIVITY_NEW_TASK);startActivity(install);}catch(Exception e){Toast.makeText(this,"APK скачан, но установщик не открылся",Toast.LENGTH_LONG).show();}}
    private void handleWebPermission(PermissionRequest r){if(r==null)return;boolean mic=false,cam=false;for(String x:r.getResources()){if(PermissionRequest.RESOURCE_AUDIO_CAPTURE.equals(x))mic=true;if(PermissionRequest.RESOURCE_VIDEO_CAPTURE.equals(x))cam=true;}boolean mg=!mic||Build.VERSION.SDK_INT<23||checkSelfPermission(Manifest.permission.RECORD_AUDIO)==PackageManager.PERMISSION_GRANTED;boolean cg=!cam||Build.VERSION.SDK_INT<23||checkSelfPermission(Manifest.permission.CAMERA)==PackageManager.PERMISSION_GRANTED;if(mg&&cg){r.grant(r.getResources());return;}pendingWebPermission=r;if(Build.VERSION.SDK_INT>=23)requestPermissions(new String[]{Manifest.permission.RECORD_AUDIO,Manifest.permission.CAMERA},MEDIA_PERMISSION_REQUEST);else r.grant(r.getResources());}
    @Override public void onRequestPermissionsResult(int requestCode,String[] permissions,int[] grantResults){super.onRequestPermissionsResult(requestCode,permissions,grantResults);if(requestCode!=MEDIA_PERMISSION_REQUEST||pendingWebPermission==null)return;PermissionRequest r=pendingWebPermission;pendingWebPermission=null;boolean ok=true;for(int x:grantResults)if(x!=PackageManager.PERMISSION_GRANTED)ok=false;if(ok)r.grant(r.getResources());else r.deny();}
    @Override protected void onActivityResult(int requestCode,int resultCode,Intent data){super.onActivityResult(requestCode,resultCode,data);if(requestCode!=FILE_CHOOSER_REQUEST||fileCallback==null)return;fileCallback.onReceiveValue(WebChromeClient.FileChooserParams.parseResult(resultCode,data));fileCallback=null;}
    @Override protected void onPause(){
        if(isTv&&webView!=null){
            webView.evaluateJavascript("if(typeof suspendTvPlayback==='function')suspendTvPlayback()",null);
        }
        super.onPause();
    }

    @Override protected void onResume(){
        super.onResume();
        enterTvImmersive();
        if(isTv&&webView!=null){
            webView.evaluateJavascript("if(typeof resumeTvPlayback==='function')resumeTvPlayback();if(typeof load==='function'&&!document.getElementById('playerView')?.classList.contains('open'))load();if(typeof refreshTvAuth==='function')refreshTvAuth(true)",null);
        }
        if(pendingApkUri!=null&&(Build.VERSION.SDK_INT<Build.VERSION_CODES.O||getPackageManager().canRequestPackageInstalls())){
            Uri u=pendingApkUri;pendingApkUri=null;openPackageInstaller(u);
        }else if(!isTv)checkForAppUpdate(true,false);
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
        if(isTv&&event.getAction()==KeyEvent.ACTION_DOWN&&webView!=null){
            int code=event.getKeyCode();
            if(code==KeyEvent.KEYCODE_BACK){
                onBackPressed();
                return true;
            }
            if(code==KeyEvent.KEYCODE_DPAD_UP||code==KeyEvent.KEYCODE_DPAD_DOWN||code==KeyEvent.KEYCODE_DPAD_LEFT||code==KeyEvent.KEYCODE_DPAD_RIGHT||code==KeyEvent.KEYCODE_DPAD_CENTER||code==KeyEvent.KEYCODE_ENTER){
                String action="";
                if(code==KeyEvent.KEYCODE_DPAD_UP)action="up";
                else if(code==KeyEvent.KEYCODE_DPAD_DOWN)action="down";
                else if(code==KeyEvent.KEYCODE_DPAD_LEFT)action="left";
                else if(code==KeyEvent.KEYCODE_DPAD_RIGHT)action="right";
                else action="ok";
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
        return super.dispatchKeyEvent(event);
    }

    private void openExternal(Uri uri){if(uri==null)return;try{String s=uri.getScheme()==null?"":uri.getScheme().toLowerCase(),h=uri.getHost()==null?"":uri.getHost().toLowerCase();if("tg".equals(s)||"t.me".equals(h)||"telegram.me".equals(h)){Intent t=new Intent(Intent.ACTION_VIEW,uri);t.setPackage("org.telegram.messenger");try{startActivity(t);return;}catch(Exception ignored){}}startActivity(new Intent(Intent.ACTION_VIEW,uri));}catch(Exception ignored){}}
    @Override protected void onDestroy(){updateHandler.removeCallbacksAndMessages(null);if(downloadReceiver!=null){try{unregisterReceiver(downloadReceiver);}catch(Exception ignored){}}if(webView!=null)webView.destroy();super.onDestroy();}
    @Override public void onBackPressed(){
        if(customView!=null){hideCustomView();return;}
        if(isTv&&webView!=null){
            webView.evaluateJavascript(
                "(function(){try{return (typeof handleTvBack==='function')?handleTvBack():false}catch(e){return false}})()",
                value->{
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
        if(webView!=null&&webView.canGoBack())webView.goBack();else super.onBackPressed();
    }
}
