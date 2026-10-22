package ai.facetalk.app;

import android.app.Activity;
import android.webkit.JavascriptInterface;
import android.webkit.WebView;
import android.util.Log;
import java.io.InputStream;
import java.io.BufferedInputStream;
import java.net.HttpURLConnection;
import java.net.URL;
import java.text.SimpleDateFormat;
import java.util.ArrayList;
import java.util.Date;
import java.util.HashMap;
import java.util.Locale;
import java.util.Map;
import java.util.TimeZone;
import java.util.concurrent.atomic.AtomicBoolean;
import java.util.zip.GZIPInputStream;
import javax.xml.parsers.SAXParserFactory;
import org.json.JSONArray;
import org.json.JSONObject;
import org.xml.sax.Attributes;
import org.xml.sax.helpers.DefaultHandler;

public final class StandaloneEpgBridge {
    private final Activity activity;
    private final WebView view;
    private final AtomicBoolean busy=new AtomicBoolean(false);
    private static final String[][] FEEDS={
        {"AM","https://iptv-epg.org/files/epg-am.xml.gz"},
        {"RU","https://iptv-epg.org/files/epg-ru.xml.gz"},
        {"ALT","http://epg.one/epg.xml.gz"}
    };
    StandaloneEpgBridge(Activity a,WebView w){activity=a;view=w;}

    @JavascriptInterface public void refresh(){
        if(!busy.compareAndSet(false,true))return;
        new Thread(()->{
            try{
                for(String[] feed:FEEDS){
                    try{
                        JSONObject parsed=download(feed[1],feed[0]);
                        if(parsed!=null&&parsed.optJSONArray("channels")!=null&&parsed.optJSONArray("channels").length()>0)
                            deliver(parsed);
                    }catch(Exception ex){
                        Log.w("AbajStandaloneEPG",feed[0]+" guide unavailable: "+ex.getClass().getSimpleName());
                    }
                }
            }finally{busy.set(false);}
        },"abaj-standalone-epg").start();
    }

    private static long xmlTimestamp(String value){
        try{
            if(value==null||value.length()<14)return 0;
            String v=value.substring(0,14);
            String tz=value.length()>=20?value.substring(15).trim():"";
            SimpleDateFormat fmt=new SimpleDateFormat(tz.length()==5?"yyyyMMddHHmmss Z":"yyyyMMddHHmmss",Locale.US);
            if(tz.length()!=5)fmt.setTimeZone(TimeZone.getTimeZone("UTC"));
            Date dt=fmt.parse(tz.length()==5?v+" "+tz:v);
            return dt==null?0:dt.getTime()/1000;
        }catch(Exception ex){return 0;}
    }
    private static final long EPG_HORIZON_SECONDS=10L*60L*60L;
    private static final int MAX_SCHEDULE_ITEMS=20;
    private static class Program {
        long start,stop;
        String title;
        Program(long a,long b,String c){start=a;stop=b;title=c;}
        JSONObject json(){
            JSONObject out=new JSONObject();
            try{out.put("start",start);out.put("stop",stop);out.put("title",title);}
            catch(Exception ignored){}
            return out;
        }
    }
    private static class TvChannel {
        String id;
        ArrayList<String> names=new ArrayList<>();
        Program now,next;
        final ArrayList<Program> schedule=new ArrayList<>();
        TvChannel(String key){id=key;}
    }

    private static JSONObject download(String source,String country)throws Exception{
        HttpURLConnection connection=null;
        try{
            connection=(HttpURLConnection)new URL(source).openConnection();
            connection.setConnectTimeout(12000);
            connection.setReadTimeout(25000);
            connection.setRequestProperty("User-Agent","ABAJ-TV-Standalone/1.0");
            connection.setRequestProperty("Accept","application/xml,application/octet-stream,*/*");
            if(connection.getResponseCode()!=200)throw new IllegalStateException("XMLTV HTTP "+connection.getResponseCode());
            try(InputStream raw=new BufferedInputStream(connection.getInputStream())){
                raw.mark(4);
                int first=raw.read(),second=raw.read();
                raw.reset();
                InputStream body=first==0x1f&&second==0x8b?new GZIPInputStream(raw):raw;
                final HashMap<String,TvChannel> map=new HashMap<>();
                final long now=System.currentTimeMillis()/1000;
                DefaultHandler handler=new DefaultHandler(){
                    String currentId="",node="",title="";
                    StringBuilder content=new StringBuilder();
                    long start=0,stop=0;
                    @Override public void startElement(String uri,String localName,String qName,Attributes a){
                        String element=localName==null||localName.isEmpty()?qName:localName;
                        if("channel".equals(element)){
                            currentId=a.getValue("id");
                            if(currentId!=null&&!currentId.isEmpty()&&!map.containsKey(currentId))map.put(currentId,new TvChannel(currentId));
                        }else if("programme".equals(element)){
                            currentId=a.getValue("channel");
                            start=xmlTimestamp(a.getValue("start"));
                            stop=xmlTimestamp(a.getValue("stop"));
                            title="";
                            if(currentId!=null&&!currentId.isEmpty()&&!map.containsKey(currentId))map.put(currentId,new TvChannel(currentId));
                        }
                        node=element;
                        content.setLength(0);
                    }
                    @Override public void characters(char[] ch,int st,int length){
                        if(("display-name".equals(node)||"title".equals(node))&&content.length()<350)
                            content.append(ch,st,Math.min(length,350-content.length()));
                    }
                    @Override public void endElement(String uri,String localName,String qName){
                        String element=localName==null||localName.isEmpty()?qName:localName;
                        if("display-name".equals(element)){
                            TvChannel item=map.get(currentId);
                            String label=content.toString().trim();
                            if(item!=null&&!label.isEmpty()&&item.names.size()<6&&!item.names.contains(label))item.names.add(label);
                        }else if("title".equals(element)&&start>0){
                            if(title.isEmpty())title=content.toString().trim();
                        }else if("programme".equals(element)){
                            TvChannel item=map.get(currentId);
                            if(item!=null&&!title.isEmpty()&&start>0&&stop>now){
                                Program p=new Program(start,stop,title);
                                if(start<now+EPG_HORIZON_SECONDS)item.schedule.add(p);
                                if(start<=now&&(item.now==null||start>item.now.start))item.now=p;
                                else if(start>now&&(item.next==null||start<item.next.start))item.next=p;
                            }
                            currentId="";start=0;stop=0;
                        }else if("channel".equals(element)){currentId="";}
                        node="";
                        content.setLength(0);
                    }
                };
                SAXParserFactory factory=SAXParserFactory.newInstance();
                factory.setNamespaceAware(false);
                try{factory.setFeature("http://xml.org/sax/features/external-general-entities",false);}catch(Exception ignored){}
                try{factory.setFeature("http://xml.org/sax/features/external-parameter-entities",false);}catch(Exception ignored){}
                factory.newSAXParser().parse(body,handler);
                JSONArray items=new JSONArray();
                for(TvChannel item:map.values()){
                    if(item.now==null&&item.next==null)continue;
                    JSONObject entry=new JSONObject();
                    entry.put("id",item.id);
                    entry.put("names",new JSONArray(item.names));
                    if(item.now!=null)entry.put("now",item.now.json());
                    if(item.next!=null)entry.put("next",item.next.json());
                    item.schedule.sort((a,b)->Long.compare(a.start,b.start));
                    JSONArray schedule=new JSONArray();
                    for(int i=0;i<item.schedule.size()&&i<MAX_SCHEDULE_ITEMS;i++)schedule.put(item.schedule.get(i).json());
                    entry.put("programmes",schedule);
                    items.put(entry);
                }
                JSONObject result=new JSONObject();
                result.put("country",country);
                result.put("updated",now);
                result.put("channels",items);
                return result;
            }
        }finally{if(connection!=null)connection.disconnect();}
    }
    private void deliver(JSONObject result){
        activity.runOnUiThread(()->{
            try{
                String location=view.getUrl();
                if(location==null||!location.startsWith("file:///android_asset/standalone/"))return;
                view.evaluateJavascript("window.__abajStandaloneEpgUpdate&&window.__abajStandaloneEpgUpdate("+
                    result.toString()+");",null);
            }catch(Exception ex){Log.w("AbajStandaloneEPG","EPG bridge callback failed",ex);}
        });
    }
}
