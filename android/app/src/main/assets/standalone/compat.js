(function(){
'use strict';
window.ABAJ_STANDALONE=true;
const STORAGE='abaj_standalone_playlists';
const key=(k)=>'abaj-standalone-'+k;
const read=(k,def)=>{try{const v=JSON.parse(localStorage.getItem(key(k)));return v??def}catch(e){return def}};
const save=(k,v)=>{localStorage.setItem(key(k),JSON.stringify(v));return true};
const URL_OK=u=>/^https?:\/\//i.test(String(u||''));
const bridge=window.StandaloneNetwork;
const pending=new Map();let seq=0;
const nativeRequest=(url,method='GET',body='')=>new Promise((resolve,reject)=>{
 if(!bridge||!URL_OK(url))return reject(Error('Нет сетевого подключения Android'));
 const id='sb'+(++seq);const timer=setTimeout(()=>{pending.delete(id);reject(Error('Тайм-аут источника'))},35000);
 pending.set(id,{resolve,reject,timer});
 try{bridge.request(id,url,method,body)}catch(e){pending.delete(id);clearTimeout(timer);reject(e)}
});
window.__abajStandaloneResponse=(id,status,body)=>{const x=pending.get(id);if(!x)return;pending.delete(id);clearTimeout(x.timer);if(status>=200&&status<300)x.resolve(body);else x.reject(Error('Источник: '+String(body).slice(0,160)))};
function parseM3U(raw,name='TV',id='free',country='AM'){
 const arr=[];let meta={};
 for(const line0 of String(raw||'').replace(/\r/g,'').split('\n')){
  const line=line0.trim();
  if(line.startsWith('#EXTINF:')){
   const attrs={};for(const m of line.matchAll(/([\w-]+)="([^"]*)"/g))attrs[m[1]]=m[2];
   const c=line.indexOf(',');
   meta={name:c>=0?line.slice(c+1).trim():'Канал',group:attrs['group-title']||'General',logo:attrs['tvg-logo']||'',tvg_id:attrs['tvg-id']||'',country};
  }else if(line&&!line.startsWith('#')&&URL_OK(line)){
   arr.push({...meta,id:id+':'+arr.length,url:line,status:'ONLINE',provider:id==='free'?'Free':'Edem',playlist_id:id,personal:id!=='free',country});
   meta={};
  }
 }
 return arr;
}
const sources=()=>{
 const v=read('playlists',[]);
 return Array.isArray(v)?v.filter(x=>x&&typeof x.id==='string'&&typeof x.name==='string'&&typeof x.url==='string'):[];
};
// Earlier standalone versions cached thousands of full channel objects in
// WebView localStorage. This exhausted the quota and prevented saving a second
// playlist. Remove ONLY obsolete channel caches; keep user playlists/settings.
try{
 const remove=[];
 for(let i=0;i<localStorage.length;i++){
  const k=localStorage.key(i);
  if(k&&(
    k.startsWith('abaj-standalone-playlist-cache-')||
    k==='abajtv_channels_cache_v6'
  ))remove.push(k);
 }
 remove.forEach(k=>localStorage.removeItem(k));
}catch(e){}
const playlistCache=new Map();
const playlistHealth=new Map();
let playlistsRevision=0;
function clearPlaylistCache(id){for(const k of playlistCache.keys())if(k.startsWith(id+'|'))playlistCache.delete(k)}
function refreshSavedPlaylistMenu(){
 try{window.renderNamedPlaylistChips?.(sources(),[])}catch(e){}
}
function announcePlaylist(message,error=false){
 const el=document.getElementById('standalonePlaylistStatus');
 if(el){el.textContent=message;el.style.color=error?'#a62b4d':'#206b48'}
}
function refreshAppPlaylists(selectId){
 const revision=++playlistsRevision;
 refreshSavedPlaylistMenu();
 const work=typeof window.load==='function'?Promise.resolve(window.load()):Promise.resolve();
 work.then(()=>{
  if(revision!==playlistsRevision)return;
  if(selectId&&typeof window.setSourceFilter==='function')window.setSourceFilter(null,'playlist:'+selectId);
  window.abajStandaloneRefreshRows?.();
 }).catch(e=>announcePlaylist('Ошибка обновления списка: '+e.message,true));
 return work;
}
const BUILTIN_IPTV_SOURCES=[["RU","https://iptv-org.github.io/iptv/subdivisions/ru-che.m3u"],["RU","https://iptv-org.github.io/iptv/subdivisions/ru-in.m3u"],["RU","https://iptv-org.github.io/iptv/subdivisions/ru-irk.m3u"],["RU","https://iptv-org.github.io/iptv/subdivisions/ru-kb.m3u"],["RU","https://iptv-org.github.io/iptv/subdivisions/ru-kgd.m3u"],["RU","https://iptv-org.github.io/iptv/subdivisions/ru-klu.m3u"],["RU","https://iptv-org.github.io/iptv/subdivisions/ru-kc.m3u"],["RU","https://iptv-org.github.io/iptv/subdivisions/ru-kem.m3u"],["RU","https://iptv-org.github.io/iptv/subdivisions/ru-kha.m3u"],["RU","https://iptv-org.github.io/iptv/subdivisions/ru-kk.m3u"],["RU","https://iptv-org.github.io/iptv/subdivisions/ru-khm.m3u"],["RU","https://iptv-org.github.io/iptv/subdivisions/ru-kos.m3u"],["RU","https://iptv-org.github.io/iptv/subdivisions/ru-kya.m3u"],["RU","https://iptv-org.github.io/iptv/subdivisions/ru-kgn.m3u"],["RU","https://iptv-org.github.io/iptv/subdivisions/ru-len.m3u"],["RU","https://iptv-org.github.io/iptv/subdivisions/ru-mo.m3u"],["RU","https://iptv-org.github.io/iptv/subdivisions/ru-nen.m3u"],["RU","https://iptv-org.github.io/iptv/subdivisions/ru-niz.m3u"],["RU","https://iptv-org.github.io/iptv/subdivisions/ru-ngr.m3u"],["RU","https://iptv-org.github.io/iptv/subdivisions/ru-oms.m3u"],["RU","https://iptv-org.github.io/iptv/subdivisions/ru-ore.m3u"],["RU","https://iptv-org.github.io/iptv/subdivisions/ru-per.m3u"],["RU","https://iptv-org.github.io/iptv/subdivisions/ru-pri.m3u"],["RU","https://iptv-org.github.io/iptv/subdivisions/ru-ros.m3u"],["RU","https://iptv-org.github.io/iptv/subdivisions/ru-rya.m3u"],["RU","https://iptv-org.github.io/iptv/subdivisions/ru-sa.m3u"],["RU","https://iptv-org.github.io/iptv/subdivisions/ru-se.m3u"],["RU","https://iptv-org.github.io/iptv/subdivisions/ru-sta.m3u"],["RU","https://iptv-org.github.io/iptv/subdivisions/ru-tom.m3u"],["RU","https://iptv-org.github.io/iptv/subdivisions/ru-tyu.m3u"],["RU","https://iptv-org.github.io/iptv/subdivisions/ru-ty.m3u"],["RU","https://iptv-org.github.io/iptv/subdivisions/ru-vgg.m3u"],["RU","https://iptv-org.github.io/iptv/subdivisions/ru-yan.m3u"],["RU","https://iptv-org.github.io/iptv/subdivisions/ru-yar.m3u"],["RU","https://iptv-org.github.io/iptv/subdivisions/ru-yev.m3u"],["RU","https://iptv-org.github.io/iptv/subdivisions/ru-ad.m3u"],["RU","https://iptv-org.github.io/iptv/subdivisions/ru-al.m3u"],["RU","https://iptv-org.github.io/iptv/subdivisions/ru-alt.m3u"],["RU","https://iptv-org.github.io/iptv/subdivisions/ru-ark.m3u"],["RU","https://iptv-org.github.io/iptv/subdivisions/ru-ast.m3u"],["RU","https://iptv-org.github.io/iptv/subdivisions/ru-bel.m3u"],["RU","https://iptv-org.github.io/iptv/subdivisions/ru-ce.m3u"],["RU","https://iptv-org.github.io/iptv/subdivisions/ru-mow.m3u"],["RU","https://iptv-org.github.io/iptv/subdivisions/ru-spe.m3u"],["RU","https://iptv-org.github.io/iptv/subdivisions/ru-mos.m3u"],["RU","https://iptv-org.github.io/iptv/subdivisions/ru-ta.m3u"],["RU","https://iptv-org.github.io/iptv/subdivisions/ru-ba.m3u"],["RU","https://iptv-org.github.io/iptv/subdivisions/ru-da.m3u"],["RU","https://iptv-org.github.io/iptv/subdivisions/ru-kda.m3u"],["RU","https://iptv-org.github.io/iptv/subdivisions/ru-sve.m3u"],["RU","https://iptv-org.github.io/iptv/subdivisions/ru-nvs.m3u"],["RU","https://iptv-org.github.io/iptv/subdivisions/ru-sam.m3u"],["HQ","https://iptv-org.github.io/iptv/categories/general.m3u"],["HQ","https://iptv-org.github.io/iptv/categories/movies.m3u"],["HQ","https://iptv-org.github.io/iptv/categories/series.m3u"],["HQ","https://iptv-org.github.io/iptv/categories/kids.m3u"],["HQ","https://iptv-org.github.io/iptv/categories/education.m3u"],["HQ","https://iptv-org.github.io/iptv/categories/science.m3u"],["HQ","https://raw.githubusercontent.com/Free-TV/IPTV/master/playlist.m3u8"],["HQ","https://iptv-org.github.io/iptv/categories/news.m3u"],["HQ","https://iptv-org.github.io/iptv/categories/sports.m3u"],["HQ","https://iptv-org.github.io/iptv/categories/documentary.m3u"],["HQ","https://iptv-org.github.io/iptv/categories/music.m3u"],["HQ","https://iptv-org.github.io/iptv/categories/entertainment.m3u"],["HQ","https://dearbulut.github.io/iptv/playlists/best.m3u"],["HQ","https://dearbulut.github.io/iptv/playlists/online.m3u"],["RU","https://raw.githubusercontent.com/smolnp/IPTVru/refs/heads/gh-pages/IPTVstable.m3u8"],["RU","https://raw.githubusercontent.com/denxvofficial/IPTV/main/iptv-top.m3u"],["RU","https://raw.githubusercontent.com/denxvofficial/IPTV/main/iptv.m3u"],["RU","https://dearbulut.github.io/iptv/playlists/country/ru.m3u"],["RU","https://iptv-org.github.io/iptv/languages/rus.m3u"],["AM","https://iptv-org.github.io/iptv/countries/am.m3u"],["AM","https://iptv-org.github.io/iptv/languages/hye.m3u"],["AM","https://raw.githubusercontent.com/iptv-org/iptv/master/streams/am.m3u"],["AM","https://dearbulut.github.io/iptv/playlists/country/am.m3u"],["AM","https://raw.githubusercontent.com/Free-TV/IPTV/master/playlists/playlist_armenia.m3u8"],["RU","https://iptv-org.github.io/iptv/countries/ru.m3u"],["RU","https://raw.githubusercontent.com/substanc1/iptv-russia/main/streams/ru.m3u"],["RU","https://ngrch.github.io/iptv/ru.m3u"],["RU","https://raw.githubusercontent.com/Free-TV/IPTV/master/playlists/playlist_russia.m3u8"],["GE","https://iptv-org.github.io/iptv/countries/ge.m3u"],["UA","https://iptv-org.github.io/iptv/countries/ua.m3u"],["BY","https://iptv-org.github.io/iptv/countries/by.m3u"],["KZ","https://iptv-org.github.io/iptv/countries/kz.m3u"],["UZ","https://iptv-org.github.io/iptv/countries/uz.m3u"],["MD","https://iptv-org.github.io/iptv/countries/md.m3u"]];
const BUILTIN_IPTV_OFFICIAL=[{"name":"Armenia 1","group":"General","tvg_id":"Armenia1.am","country":"AM","source":"operator:teamtv:h1","url":"http://ncdn-y1-vip2.teamcloud.am/live/eds/H1/SAF-HLS/H1.m3u8","adult":false,"quality":"FHD","height":1080},{"name":"First Channel News","group":"News","tvg_id":"FirstChannelNews.am","country":"AM","source":"operator:teamtv:h1-news","url":"http://ncdn-y1-vip2.teamcloud.am/live/eds/H1-News-SDI/SAF-HLS/H1-News-SDI.m3u8","adult":false,"quality":"FHD","height":1080},{"name":"Armenia TV","group":"General","tvg_id":"ArmeniaTV.am","country":"AM","source":"operator:teamtv:armenia-tv","url":"http://ncdn-y1-vip2.teamcloud.am/live/eds/ArmeniaTV-SDI/SAF-HLS/ArmeniaTV-SDI.m3u8","adult":false,"quality":"FHD","height":1080},{"name":"ATV Armenia","group":"General","tvg_id":"ATV.am","country":"AM","source":"operator:teamtv:atv","url":"http://ncdn-y1-vip2.teamcloud.am/live/eds/ATV/SAF-HLS/ATV.m3u8","adult":false,"quality":"FHD","height":1080},{"name":"Free News","group":"News","tvg_id":"FreeNews.am","country":"AM","source":"operator:teamtv:free-news","url":"http://ncdn-y1-vip2.teamcloud.am/live/eds/FreeNews/SAF-HLS/FreeNews.m3u8","adult":false,"quality":"FHD","height":1080},{"name":"Dar 21 TV","group":"General","tvg_id":"Dar21TV.am","country":"AM","source":"operator:teamtv:dar21","url":"http://ncdn-y1-vip2.teamcloud.am/live/eds/DAR21TV/SAF-HLS/DAR21TV.m3u8","adult":false,"quality":"FHD","height":1080},{"name":"Shant TV","group":"General","tvg_id":"ShantTV.am","country":"AM","source":"operator:teamtv:shant","url":"http://ncdn-y1-vip2.teamcloud.am/live/eds/ShantTV-SDI/SAF-HLS/ShantTV-SDI.m3u8","adult":false,"quality":"FHD","height":1080},{"name":"Nor Hayastan","group":"General","tvg_id":"NorHayastan.am","country":"AM","source":"operator:teamtv:nor-hayastan","url":"http://ncdn-y1-vip2.teamcloud.am/live/eds/NorHayastan/SAF-HLS/NorHayastan.m3u8","adult":false,"quality":"FHD","height":1080},{"name":"Fast Sport","group":"Sports","tvg_id":"FastSport.am","country":"AM","source":"operator:teamtv:fast-sport","url":"http://ncdn-y1-vip2.teamcloud.am/live/eds/VMedia/SAF-HLS/VMedia.m3u8","adult":false,"quality":"FHD","height":1080},{"name":"Yerkir Media","group":"General","tvg_id":"YerkirMedia.am","country":"AM","source":"official:yerkirmedia.am","url":"http://yerkirmedia.am/yerkirmedia/live.m3u8","adult":false,"quality":"","height":0},{"name":"Yerkir Media","group":"General","tvg_id":"YerkirMedia.am","country":"AM","source":"backup:ucom:s7-04","url":"http://ott-cdn.ucom.am/s7/04.m3u8","adult":false,"quality":"","height":0},{"name":"Yerkir Media","group":"General","tvg_id":"YerkirMedia.am","country":"AM","source":"backup:ucom:s7-index","url":"http://ott-cdn.ucom.am/s7/index.m3u8","adult":false,"quality":"","height":0},{"name":"5TV Armenia","group":"News","tvg_id":"5TV.am","country":"AM","source":"official:5tv.am","url":"https://live-5tvam.cdnvideo.ru/5tvam/5tvam/playlist.m3u8","adult":false,"quality":"","height":0},{"name":"AMGA (1080p)","group":"General","tvg_id":"AMGA.us","country":"AM","source":"public:connectto:amga","url":"https://streamer1.connectto.com/AMGA_WEB_1202/playlist.m3u8","adult":false,"quality":"FHD","height":1080},{"name":"Armenia 1 America (1080p)","group":"General","tvg_id":"Armenia1.am@America","country":"AM","source":"public:tulix:armenia1-america","url":"https://amtvusdvr.tulix.tv/am4abr/index.m3u8","adult":false,"quality":"FHD","height":1080},{"name":"AABC TV","group":"General","tvg_id":"KIIOLD104.us","country":"AM","source":"public:connectto:aabc","url":"https://streamer1.connectto.com/AABC_WEB_1201/index.m3u8","adult":false,"quality":"","height":480},{"name":"Luys TV (1080p)","group":"Culture","tvg_id":"LuysTV.tr@SD","country":"AM","source":"public:iptv-org:luys-tv","url":"https://b01c02nl.mediatriple.net/videoonlylive/mtpayqrfkgirxelive/broadcast_5e91c5ac96898.smil/playlist.m3u8","adult":false,"quality":"FHD","height":1080},{"name":"IRIB UHD (2160p)","group":"4K","tvg_id":"IRIBUHD.ir","country":"IR","source":"public:telewebion:irib-uhd","url":"https://ncdn.telewebion.ir/faratar/live/playlist.m3u8","adult":false,"quality":"4K","height":2160},{"name":"Bloomberg TV+ (2160p)","group":"4K","tvg_id":"BloombergTV.us@Plus","country":"US","source":"public:samsung:bloomberg-tv-plus","url":"https://d2d98ykcmmhgd4.cloudfront.net/v1/bloomberg_bloombergtv_2/samsungheadend_us/latest/main/hls/playlist.m3u8","adult":false,"quality":"4K","height":2160},{"name":"Fresh TV Armenia (1080p)","group":"Music","tvg_id":"FreshTV.am","country":"AM","source":"public:freshtv","url":"https://freshtv-live.ru/FreshTV/index.m3u8?token=livestream","adult":false,"quality":"FHD","height":1080},{"name":"Fireplace Vibes (2160p)","group":"4K","tvg_id":"","country":"US","source":"public:cloudfront:fireplace-4k","url":"https://d21izs34d0y5tl.cloudfront.net/Fireplace_4K_SONO20.m3u8","adult":false,"quality":"4K","height":2160},{"name":"TBN Armenia (1080p)","group":"Religious","tvg_id":"TBNArmenia.am","country":"AM","source":"public:gvideo:tbn-armenia","url":"https://164475.gvideo.io/cmaf/164475_650646/master.m3u8","adult":false,"quality":"FHD","height":1080},{"name":"Armenia 1 Satellite (1080p)","group":"General","tvg_id":"Armenia1.am@Sattelite","country":"AM","source":"public:tulix:armenia1-satellite","url":"https://amtv.tulixcdn.com/amtv2/am2abr/index.m3u8","adult":false,"quality":"FHD","height":1080},{"name":"Clarity 4K (2160p)","group":"4K","tvg_id":"Clarity4K.us","country":"US","source":"public:akamai:clarity-4k","url":"https://pb-qyrvophnifz47.akamaized.net/Clarity_4K.m3u8","adult":false,"quality":"4K","height":2160}];
const IPTV_REFRESH_MS=86400000;
let builtinIptvData=null,builtinIptvBoot=null,builtinIptvRefresh=null,builtinIptvLastAttempt=0;
const builtinIptvSeed=BUILTIN_IPTV_OFFICIAL.filter(x=>x&&URL_OK(x.url)).map((x,i)=>({
 id:'free:official:'+i,name:x.name,group:x.group||'General',url:x.url,logo:x.logo||'',
 tvg_id:x.tvg_id||'',country:x.country||'',quality:x.quality||'',height:x.height||0,
 status:'ONLINE',provider:'IPTV',playlist_id:'free',personal:false,adult:!!x.adult
}));
const iptvName=n=>String(n||'').toLocaleLowerCase('ru').replace(/\s*(?:\((?:2160p|1080p|720p|4k|uhd|fhd|hd|sd)\)|\b(?:2160p|1080p|720p|4k|uhd|fhd|hd|sd)\b)\s*$/gi,'').replace(/[^\p{L}\p{N}]+/gu,' ').trim();
function iptvHash(s){let h=2166136261;for(let i=0;i<s.length;i++){h^=s.charCodeAt(i);h=Math.imul(h,16777619)}return (h>>>0).toString(36)}
function mergeBuiltinIptv(rows){
 const selected=new Map();
 for(const item of rows){
  const k=(String(item.country||'')+'|'+iptvName(item.name)).toLowerCase();
  if(k.endsWith('|'))continue;
  const previous=selected.get(k);
  if(!previous){selected.set(k,item);continue}
  const score=x=>Number(x.height||0)+(x.logo?400:0)+(x.quality==='4K'?5000:x.quality==='FHD'?3000:x.quality==='HD'?2000:0);
  const best=score(item)>score(previous)?item:previous,other=best===item?previous:item;
  const backups=new Set([...(best.backups||[]),other.url,...(other.backups||[])]);
  best.backups=[...backups].filter(u=>URL_OK(u)&&u!==best.url).slice(0,6);
  if(!best.logo)best.logo=other.logo||'';
  selected.set(k,best);
 }
 return [...selected].map(x=>({...x,id:'free:'+iptvHash((String(x.country||'')+'|'+iptvName(x.name)).toLowerCase()),provider:'IPTV',playlist_id:'free',personal:false}));
}
function builtinFromM3u(raw,country){
 return parseM3U(raw,'IPTV','free',country).map(x=>{
  const attr=(x.name+' '+x.group).match(/\b(4k|2160p|fhd|1080p|hd|720p)\b/i);
  const q=(attr?.[1]||'').toUpperCase();
  const quality=/4K|2160P/.test(q)?'4K':/FHD|1080P/.test(q)?'FHD':/HD|720P/.test(q)?'HD':'';
  const height=quality==='4K'?2160:quality==='FHD'?1080:quality==='HD'?720:0;
  const adult=/(?:^|[\W_])(xxx|adult|erotic|porn|18\+|порно|взрослые)(?:$|[\W_])/i.test(x.name+' '+x.group);
  return {...x,country:country==='HQ'?'':country,quality,height,adult,personal:false,provider:'IPTV'};
 });
}
function iptvSnapshotRead(){
 if(!window.indexedDB)return Promise.resolve(null);
 return new Promise(resolve=>{
  let done=false;const finish=v=>{if(!done){done=true;resolve(v)}};
  setTimeout(()=>finish(null),1800);
  try{
   const open=indexedDB.open('abaj_standalone_iptv_v1',1);
   open.onupgradeneeded=()=>{if(!open.result.objectStoreNames.contains('builtins'))open.result.createObjectStore('builtins')};
   open.onerror=()=>finish(null);
   open.onsuccess=()=>{
    const db=open.result;const request=db.transaction('builtins','readonly').objectStore('builtins').get('iptv');
    request.onsuccess=()=>{finish(request.result||null);db.close()};
    request.onerror=()=>{finish(null);db.close()};
   };
  }catch(e){finish(null)}
 });
}
function iptvSnapshotSave(snapshot){
 if(!window.indexedDB)return;
 try{
  const open=indexedDB.open('abaj_standalone_iptv_v1',1);
  open.onupgradeneeded=()=>{if(!open.result.objectStoreNames.contains('builtins'))open.result.createObjectStore('builtins')};
  open.onsuccess=()=>{
   const db=open.result,transaction=db.transaction('builtins','readwrite');
   transaction.objectStore('builtins').put(snapshot,'iptv');
   transaction.oncomplete=()=>db.close();transaction.onerror=()=>db.close();
  };
 }catch(e){}
}
window.abajStandaloneIptvState=()=>({
 count:builtinIptvData?.items?.length||builtinIptvSeed.length,
 sources:BUILTIN_IPTV_SOURCES.length,
 updatedAt:builtinIptvData?.at||0,
 updating:!!builtinIptvRefresh
});
function iptvPublish(items,isFinal,successful){
 const list=mergeBuiltinIptv([...builtinIptvSeed,...items]);
 const prev=builtinIptvData?.items?.length||0;
 if(!successful||prev>list.length&&successful<7)return;
 builtinIptvData={items:list,at:isFinal?Date.now():0};
 if(isFinal)iptvSnapshotSave(builtinIptvData);
 window.abajStandaloneRefreshRows?.();
 if((isFinal||list.length>prev+40)&&typeof window.load==='function')
  setTimeout(()=>{try{window.load()}catch(e){}},120);
}
function refreshBuiltinIptv(force=false){
 if(builtinIptvRefresh)return builtinIptvRefresh;
 if(!force&&builtinIptvData?.at&&Date.now()-builtinIptvData.at<IPTV_REFRESH_MS)return Promise.resolve();
 if(!force&&Date.now()-builtinIptvLastAttempt<15*60*1000)return Promise.resolve();
 builtinIptvLastAttempt=Date.now();
 const work=async()=>{
  const urls=[...BUILTIN_IPTV_SOURCES].sort((a,b)=>{
   const rank=c=>c==='AM'?0:c==='HQ'?1:c==='RU'?2:3;
   return rank(a[0])-rank(b[0]);
  });
  let next=0,done=0,ok=0,partialAt=0;const data=[];
  const worker=async()=>{
   while(next<urls.length){
    const [country,url]=urls[next++];
    try{
     const raw=await nativeRequest(url);
     if(raw.trimStart().startsWith('#EXTM3U')){
      const rows=builtinFromM3u(raw,country);
      if(rows.length){data.push(...rows);ok++}
     }
    }catch(e){}
    finally{
     done++;
     if(ok>=3&&done>=6&&done-partialAt>=10){partialAt=done;iptvPublish(data,false,ok)}
    }
   }
  };
  await Promise.all(Array.from({length:6},worker));
  if(ok)iptvPublish(data,true,ok);
  else builtinIptvLastAttempt=Date.now()-14*60*1000;
 };
 builtinIptvRefresh=work().finally(()=>{builtinIptvRefresh=null;window.abajStandaloneRefreshRows?.()});
 return builtinIptvRefresh;
}
const freeList=async()=>{
 if(!builtinIptvBoot)builtinIptvBoot=iptvSnapshotRead().then(saved=>{
  builtinIptvData=saved&&Array.isArray(saved.items)&&saved.items.length>=builtinIptvSeed.length
   ?saved:{items:mergeBuiltinIptv(builtinIptvSeed),at:0};
 }).catch(()=>{builtinIptvData={items:mergeBuiltinIptv(builtinIptvSeed),at:0}});
 await builtinIptvBoot;
 if(!builtinIptvRefresh&&(!builtinIptvData.at||Date.now()-builtinIptvData.at>=IPTV_REFRESH_MS))
  setTimeout(()=>refreshBuiltinIptv().catch(()=>{}),50);
 return builtinIptvData.items;
};
setInterval(()=>{
 if(document.visibilityState==='visible'&&!builtinIptvRefresh)refreshBuiltinIptv().catch(()=>{});
},30*60*1000);
const customList=async()=>{
 const lists=sources(), all=[];
 const results=await Promise.all(lists.map(async x=>{
  const cacheKey=x.id+'|'+x.url,cache=playlistCache.get(cacheKey);
  if(cache&&Date.now()-cache.time<60*60*1000){
   playlistHealth.set(x.id,{count:cache.items.length,ok:true,cached:true});
   return cache.items;
  }
  playlistHealth.set(x.id,{count:0,loading:true});
  window.abajStandaloneRefreshRows?.();
  try{
   const raw=await nativeRequest(x.url);
   if(!raw.trimStart().startsWith('#EXTM3U'))throw Error('Ответ не является M3U');
   const items=parseM3U(raw,x.name,x.id,'').slice(0,30000);
   if(!items.length)throw Error('В M3U нет телеканалов');
   playlistCache.set(cacheKey,{time:Date.now(),items});
   playlistHealth.set(x.id,{count:items.length,ok:true});
   return items;
  }catch(e){
   playlistHealth.set(x.id,{count:cache?.items.length||0,ok:false,error:String(e.message||e)});
   return cache?.items||[];
  }finally{
   window.abajStandaloneRefreshRows?.();
  }
 }));
 for(const result of results)for(const ch of result){
  if(all.length>=70000)break;
  all.push(ch);
 }
 return {channels:all,playlists:lists.map(x=>({id:x.id,name:x.name}))};
};
let channelCache=[];
const reply=(o,status=200)=>new Response(JSON.stringify(o),{status,headers:{'content-type':'application/json; charset=utf-8','cache-control':'no-store'}});
const cinemaStatus=()=>!!read('kino-token',{}).access_token;
const kpBase='https://api.service-kp.com';
// Reuse the pre-existing public Kodi OAuth client configured in the original ABAJ TV.
// It is not a private credential or a dedicated ABAJ TV OAuth registration.
// For distributed production builds request a dedicated client from KinoPub.
const kpBundledClient={client_id:"xbmc",client_secret:"cgg3gtifu46urtfp2zp1nqtba0k2ezxh"};
const kpClient=()=>{const configured=read('kino-client',null);return configured?.client_id&&configured?.client_secret?configured:kpBundledClient};
async function kp(path,params={},method='GET'){
 const u=kpBase+path+'?'+new URLSearchParams(params).toString();
 const raw=await nativeRequest(u,method,'');
 const o=JSON.parse(raw);if(o.error)throw Error(o.error_description||o.error);return o;
}
async function access(){
 let t=read('kino-token',{});
 if(!t.access_token)throw Error('KinoPub не подключён');
 if(t.expires_at&&Date.now()>t.expires_at-90000&&t.refresh_token){
  const r=await kp('/oauth2/token',{grant_type:'refresh_token',...kpClient(),refresh_token:t.refresh_token},'POST');
  if(r.access_token){t={access_token:r.access_token,refresh_token:r.refresh_token||t.refresh_token,expires_at:Date.now()+Number(r.expires_in||3600)*1000};save('kino-token',t)}
 }
 return t.access_token;
}
// Keep exactly the metadata contract used by the original ABAJ TV server.
function kpLabelRows(input, keys=['title','name','label']){
 if(input==null)return '';
 const rows=Array.isArray(input)?input:[input];
 return rows.map(row=>{
  if(row==null)return '';
  if(typeof row==='string'||typeof row==='number')return String(row).trim();
  if(typeof row==='object'){
   for(const key of keys)if(typeof row[key]==='string'&&row[key].trim())return row[key].trim();
  }
  return '';
 }).filter(Boolean).join(', ');
}
function kpRating(value){
 if(value&&typeof value==='object'){
  for(const key of ['rating','value','score','average'])
   if(value[key]!=null){value=value[key];break}
 }
 const n=Number(String(value??'').trim().replace(',','.'));
 return Number.isFinite(n)&&n>0&&n<=10?String(Math.round(n*10)/10):'';
}
function kpDuration(value){
 if(value==null||value==='')return '';
 if(typeof value==='object'){
  if(Array.isArray(value)){
   for(const x of value){const d=kpDuration(x);if(d)return d}
   return '';
  }
  const hours=Number(value.hours??value.hour??value.h??0);
  const minutes=Number(value.minutes??value.minute??value.min??0);
  if(hours>0&&hours<24&&minutes>=0&&minutes<60)
   return Math.round(hours*60+minutes)+' мин';
  if(minutes>0&&minutes<=600)return Math.round(minutes)+' мин';
  const secs=value.seconds??value.sec??value.s;
  if(secs!=null&&Number(secs)>0)return Math.ceil(Number(secs)/60)+' мин';
  for(const key of ['duration','runtime','length','time','value']){
   const nested=value[key];
   if(nested!=null&&nested!==value){const d=kpDuration(nested);if(d)return d}
  }
  return '';
 }
 const raw=String(value).trim();
 if(!raw||/object Object|\[object/i.test(raw))return '';
 const hhmm=raw.match(/^(\d{1,2}):(\d{2})(?::(\d{2}))?$/);
 if(hhmm){
  const minutes=hhmm[3]
   ?Number(hhmm[1])*60+Number(hhmm[2])+Number(hhmm[3])/60
   :Number(hhmm[1])*60+Number(hhmm[2]);
  return Math.round(minutes)+' мин';
 }
 if(/^\d+(?:\.\d+)?$/.test(raw)){
  const n=Number(raw);
  if(n<=0)return '';
  return (n>600?Math.round(n/60):Math.round(n))+' мин';
 }
 return raw.length<=36?raw:'';
}
function kpImage(value){
 if(typeof value==='string')return URL_OK(value)?value:'';
 if(!value||typeof value!=='object')return '';
 for(const key of ['big','medium','large','original','full','small','url','poster','src']){
  const url=value[key];
  if(typeof url==='string'&&URL_OK(url))return url;
 }
 return '';
}
// KinoPub's horizontal artwork is separate from portrait posters.
// A portrait poster must never be mistaken for a backdrop.
function kpWideImages(item,portrait=''){
 const out=[],seen=new Set();
 const append=url=>{
  if(typeof url!=='string')return;
  const value=url.trim();
  if(!URL_OK(value)||value===portrait||seen.has(value))return;
  seen.add(value);out.push(value);
 };
 const from=value=>{
  if(typeof value==='string'){append(value);return}
  if(Array.isArray(value)){
   for(const row of value.slice(0,8)){
    if(typeof row==='string')append(row);
    else if(row&&typeof row==='object')
     for(const k of ['wide','backdrop','background','fanart','original','full','big','large','url','src'])
      append(row[k]);
   }
   return;
  }
  if(value&&typeof value==='object')
   for(const k of ['wide','backdrop','background','fanart','original','full','big','large','url','src'])
    append(value[k]);
 };
 for(const key of ['backdrop','background','fanart','poster_wide','wide_poster','backdrops','backgrounds'])
  from(item[key]);
 // A dedicated wide poster has priority over generic screenshots.
 for(const key of ['posters','images','cover']){
  const group=item[key];
  if(group&&typeof group==='object'&&!Array.isArray(group))
   for(const k of ['wide','backdrop','background','fanart','landscape','horizontal'])
    from(group[k]);
 }
 for(const key of ['screenshots','stills','gallery'])from(item[key]);
 return out.slice(0,4);
}
function normalizeKp(x){
 const item=x&&typeof x==='object'?x:{};
 const pics=item.posters||item.poster||item.cover||{};
 const poster=kpImage(pics);
 const wides=kpWideImages(item,poster);
 const origId=item.imdb_id||item.imdb||'';
 const imdbId=/^(?:tt)?\d{5,12}$/i.test(String(origId))?String(origId):'';
 const kpId=item.kp_id||item.kinopoisk_id||item.kinopoisk||'';
 const rating=kpRating(item.imdb_rating??item.rating?.imdb??item.rating?.imdb_rating??item.rating);
 const kp=kpRating(item.kinopoisk_rating??item.kp_rating??item.rating?.kinopoisk??item.rating?.kp);
 const actorsRaw=Array.isArray(item.actors)?item.actors:(Array.isArray(item.cast)?item.cast:[]);
 const actor_cards=actorsRaw.slice(0,24).map(p=>{
  const name=kpLabelRows(p,['name','title','full_name','original_name']);
  return name?{id:String(p?.id||''),name,search_name:String(p?.original_name||p?.name||name),image:kpImage(p?.photo||p?.poster||p?.image)}:null;
 }).filter(Boolean);
 const duration=kpDuration(item.duration||item.runtime||item.suggest_duration);
 return {...item,
  id:String(item.id||''),title:String(item.title||item.name||''),
  original_title:String(item.original_title||''),poster,poster_url:poster,
  backdrop:wides[0]||'',
  backdrops:wides,
  description:String(item.plot||item.description||''),
  rating,imdb:rating,imdb_id:imdbId,
  kp,kp_id:String(kpId||''),
  country:kpLabelRows(item.countries||item.country),
  genre:kpLabelRows(item.genres||item.genre),
  director:kpLabelRows(item.directors||item.director,['name','title','full_name']),
  actors:kpLabelRows(item.actors||item.cast||item.actor,['name','title','full_name']),
  actor_cards,
  translation:kpLabelRows(item.translations||item.translation||item.voice),
  duration,
  kind:/serial|series|tvshow|docuserial/i.test(String(item.type||''))?'series':'movie',
  source:'KINOPUB'
 };
}
function extractKp(data){if(Array.isArray(data))return data;for(const k of ['items','data','results','movies','serials'])if(data&&data[k]){const a=extractKp(data[k]);if(a.length)return a}return []}
function getItemUrl(id){return channelCache.find(x=>String(x.id)===String(id))?.url||''}


function kpMediaArray(value){
 if(Array.isArray(value))return value.filter(x=>x&&typeof x==='object');
 if(value&&typeof value==='object'){
  for(const key of ['items','videos','episodes','data']){
   if(Array.isArray(value[key]))return value[key].filter(x=>x&&typeof x==='object');
  }
 }
 return [];
}
function kpMediaRows(item){
 const rows=[];
 const videos=kpMediaArray(item.videos);
 if(videos.length)rows.push({title:videos.length===1?'Фильм':'Видео',items:videos});
 if(Array.isArray(item.seasons)){
  for(const [idx,season] of item.seasons.entries()){
   if(!season||typeof season!=='object')continue;
   const episodes=kpMediaArray(season.episodes||season.videos);
   if(episodes.length){
    const number=season.number??idx+1;
    rows.push({title:String(season.title||'Сезон '+number),season:number,
     items:episodes.map(ep=>({...ep,season:ep.season??number}))});
   }
  }
 }
 if(!rows.length&&Array.isArray(item.files))rows.push({title:'Фильм',items:[item]});
 return rows.map(row=>({...row,items:row.items.map(m=>({
  id:m.media_id||m.mid||m.id,number:m.number,season:m.season,
  title:m.title||m.name,duration:m.duration,watching:m.watching,
  files:Array.isArray(m.files)?m.files:[],audios:Array.isArray(m.audios)?m.audios:[],
  subtitles:Array.isArray(m.subtitles)?m.subtitles:[]
 }))}));
}
async function kpItemDetail(itemId){
 if(!cinemaStatus())return reply({ok:false,error:'kinopub_auth_required'},401);
 if(!/^\d+$/.test(String(itemId)))return reply({ok:false,error:'bad_item_id'},400);
 try{
  const result=await kpCached('/v1/items/'+encodeURIComponent(itemId),{},60000,'item:');
  const raw=result.item&&typeof result.item==='object'?result.item:result;
  const item=normalizeKp(raw);
  const similar=Array.isArray(raw.similar)?raw.similar:(Array.isArray(raw.related)?raw.related:[]);
  return reply({ok:true,item,media_rows:kpMediaRows(raw),
   related:similar.slice(0,24).map(normalizeKp)});
 }catch(e){return reply({ok:false,error:'kinopub_item_unavailable',detail:String(e.message||e).slice(0,140)},502)}
}

/* KinoPub personal favourites, history, and playback progress.
 * Synced directly to the signed-in individual's KinoPub account, not Railway.
 * A small local cache handles temporarily unavailable external sources.
 */
const cinemaStorage={
 get(section){const v=read('cinema-'+section,[]);return Array.isArray(v)?v:[]},
 put(section,items,limit=250){
  const safeRows=(Array.isArray(items)?items:[]).slice(0,limit);
  try{save('cinema-'+section,safeRows)}catch(e){}
  return safeRows;
 }
};
const kpRemoteCache=new Map();
function invalidateKpCache(prefix){
 for(const k of kpRemoteCache.keys())if(!prefix||k.startsWith(prefix))kpRemoteCache.delete(k);
}
async function kpCached(path,params={},ttl=45000,cachePrefix='kp:'){
 const token=await access();
 const cacheKey=cachePrefix+path+'?'+new URLSearchParams(params).toString();
 const entry=kpRemoteCache.get(cacheKey);
 if(entry&&Date.now()-entry.ts<ttl)return entry.value;
 const value=await kp(path,{access_token:token,...params});
 kpRemoteCache.set(cacheKey,{ts:Date.now(),value});
 return value;
}
function arrayOf(raw,keys=['items','data','results']){
 if(Array.isArray(raw))return raw;
 if(!raw||typeof raw!=='object')return [];
 for(const name of keys){
  if(raw[name]!==undefined){const a=arrayOf(raw[name],keys);if(a.length)return a}
 }
 return [];
}
function kinoCard(input){
 const raw=input&&typeof input==='object'?input:{};
 const item=raw.item&&typeof raw.item==='object'?raw.item:raw;
 const obj=normalizeKp(item);
 if(!obj.id)return null;
 const title=String(obj.title||item.original_title||'').trim();
 if(!title)return null;
 const card={...obj,title,source:'KINOPUB'};
 let poster=item.poster||item.posters||item.cover||'';
 if(poster&&typeof poster==='object')poster=poster.big||poster.medium||poster.small||poster.url||poster.poster||'';
 if(typeof poster==='string'&&URL_OK(poster))card.poster=poster;
 const t=Number(raw.last_seen||raw.watched_at||raw.updated_at||0);
 if(Number.isFinite(t)&&t>0)card.watched_at=t;
 return card;
}
function cardsFrom(raw,keys,limit=300){
 const unique=new Map();
 for(const entry of arrayOf(raw,keys)){
  const card=kinoCard(entry);
  if(card&&!unique.has(String(card.id)))unique.set(String(card.id),card);
  if(unique.size>=limit)break;
 }
 return [...unique.values()];
}
function mergeCinemaRows(newRows,oldRows,limit=250){
 const result=new Map();
 for(const row of [...newRows,...oldRows]){
  const id=String(row?.id||'').trim();
  if(!id||result.has(id))continue;
  result.set(id,row);
 }
 return [...result.values()].slice(0,limit);
}
function readLocalFolders(){
 const value=read('cinema-folders',{});
 return value&&typeof value==='object'&&!Array.isArray(value)?value:{};
}
function saveLocalFolders(value){
 try{save('cinema-folders',value);return true}catch(e){return false}
}
function folderKey(folder){return String(folder?.id||'').trim()}
function defaultFolderTitle(){return 'Избранное на устройстве (не KinoPub)'}
async function kpFolders(){
 const response=await kpCached('/v1/bookmarks',{},30000,'folders:');
 const raw=arrayOf(response,['bookmarks','folders','items','data']);
 return raw.map(row=>{
  const id=String(row?.id??row?.bookmark_id??row?.folder_id??'').trim();
  return id?{id:'kp:'+id,title:String(row.title||row.name||'Избранное'),
   count:Number(row.count??row.items_count??row.total??0)||0,
   kind:'bookmark_folder',source:'KINOPUB'}:null
 }).filter(Boolean);
}
async function kpFolderItems(folderId,limit=300){
 const id=String(folderId||'').replace(/^kp:/,'');
 if(!id)return [];
 const all=[],seen=new Set();
 for(let page=1;page<=5&&all.length<limit;page++){
  const payload=await kpCached('/v1/bookmarks/'+encodeURIComponent(id),
   {page,perpage:100},45000,'folderitems:');
  const batch=cardsFrom(payload,['items','data','results'],100);
  if(!batch.length)break;
  for(const item of batch){
   const k=String(item.id);
   if(!seen.has(k)){seen.add(k);all.push(item)}
  }
  if(batch.length<100)break;
 }
 return all.slice(0,limit);
}
async function kpSelectedFolders(itemId){
 const payload=await kp('/v1/bookmarks/get-item-folders',
  {access_token:await access(),item:String(itemId)});
 const list=arrayOf(payload,['folders','items','data']);
 return new Set(list.map(x=>'kp:'+String(x?.id??x?.folder_id??'')).filter(x=>x!=='kp:'));
}
async function kpChangeBookmark(folderId,itemId,add){
 const path=add?'/v1/bookmarks/add':'/v1/bookmarks/remove-item';
 const form=new URLSearchParams({item:String(itemId),folder:String(folderId).replace(/^kp:/,'')}).toString();
 const url=kpBase+path+'?'+new URLSearchParams({access_token:await access()}).toString();
 const raw=await nativeRequest(url,'POST',form);
 let response;
 try{response=JSON.parse(raw)}catch(e){response={}}
 if(response.error||Number(response.status||200)>=400)
  throw Error(String(response.error_description||response.error||response.message||'KinoPub rejected bookmark change'));
 return response;
}
async function kinoHistory(){
 const local=cinemaStorage.get('history');
 let remote=[];
 try{
  for(let page=1;page<=3;page++){
   const payload=await kpCached('/v1/history',{page,perpage:100},25000,'history:');
   const batch=cardsFrom(payload,['history','items','data','results'],100);
   remote.push(...batch);
   if(batch.length<100)break;
  }
  const merged=mergeCinemaRows(remote,local,200);
  cinemaStorage.put('history',merged,200);
  return merged;
 }catch(e){
  if(local.length)return local;
  throw e;
 }
}
async function kinoBookmarksFlat(){
 const local=cinemaStorage.get('bookmarks');
 let remote=[];
 try{
  const folders=await kpFolders();
  for(const folder of folders.slice(0,25)){
   const rows=await kpFolderItems(folder.id,300);
   remote=mergeCinemaRows(remote,rows,300);
  }
  const custom=readLocalFolders();
  for(const obj of Object.values(custom))
   remote=mergeCinemaRows(remote,obj.items||[],300);
  // Local favourites are deliberately separate: deleting a movie in
  // KinoPub must not be silently undone by uploading an old local cache.
  return mergeCinemaRows(remote,local,300);
 }catch(e){
  if(local.length)return local;
  throw e;
 }
}
async function kinoLibrary(section,query){
 if(!cinemaStatus())return reply({ok:false,error:'kinopub_auth_required'},401);
 try{
  if(section==='history'){
   const rows=await kinoHistory();
   return reply({ok:true,section,items:rows,count:rows.length});
  }
  if(section==='watching'){
   const watching=cinemaStorage.get('watching');
   const rows=mergeCinemaRows(watching,await kinoHistory(),100);
   return reply({ok:true,section,items:rows,count:rows.length});
  }
  if(section==='bookmarks'){
   const id=String(query.get('folder')||'').trim();
   if(id){
    let rows=[];
    if(id==='personal')rows=cinemaStorage.get('bookmarks');
    else if(id.startsWith('kp:'))rows=await kpFolderItems(id);
    else rows=readLocalFolders()[id]?.items||[];
    return reply({ok:true,section,items:rows,count:rows.length});
   }
   if(query.get('flat')==='1'){
    const rows=await kinoBookmarksFlat();
    return reply({ok:true,section,items:rows,count:rows.length});
   }
   const remote=await kpFolders();
   const local=readLocalFolders();
   const folders=[
    ...remote,
    {id:'personal',title:defaultFolderTitle(),kind:'bookmark_folder',
     count:cinemaStorage.get('bookmarks').length,source:'LOCAL'},
    ...Object.entries(local).map(([fid,entry])=>({id:fid,title:entry.title||'Папка на устройстве',count:(entry.items||[]).length,kind:'bookmark_folder',source:'LOCAL'}))
   ];
   return reply({ok:true,section,folders,items:[],count:folders.reduce((n,f)=>n+Number(f.count||0),0)});
  }
  return reply({ok:false,error:'invalid_section'},400);
 }catch(e){
  return reply({ok:false,error:'kinopub_sync_unavailable',detail:String(e.message||e).slice(0,140)},502);
 }
}
async function kinoFolderPicker(query,opts){
 if(!cinemaStatus())return reply({ok:false,error:'kinopub_auth_required'},401);
 if((opts?.method||'GET').toUpperCase()==='DELETE'){
  const id=String(query.get('folder_id')||'');
  if(!id||id.startsWith('kp:'))return reply({ok:false,error:'kinopub_folder_not_deletable'},403);
  if(id==='personal'){
   cinemaStorage.put('bookmarks',[],300);
   return reply({ok:true,deleted:id});
  }
  const all=readLocalFolders();
  if(!all[id])return reply({ok:false,error:'folder_not_found'},404);
  delete all[id];saveLocalFolders(all);
  return reply({ok:true,deleted:id});
 }
 if((opts?.method||'GET').toUpperCase()==='GET'){
  try{
   const folders=await kpFolders();
   const selected=query.get('item_id')?await kpSelectedFolders(query.get('item_id')):new Set();
   const id=String(query.get('item_id')||'');
   const local=readLocalFolders();
   for(const [fid,entry] of Object.entries(local)){
    folders.push({id:fid,title:entry.title||'Папка на устройстве',count:(entry.items||[]).length,
     selected:!!id&&(entry.items||[]).some(x=>String(x.id)===id),kind:'bookmark_folder',source:'LOCAL'});
   }
   folders.push({id:'personal',title:defaultFolderTitle(),count:cinemaStorage.get('bookmarks').length,
    selected:!!id&&cinemaStorage.get('bookmarks').some(x=>String(x.id)===id),kind:'bookmark_folder',source:'LOCAL'});
   return reply({ok:true,folders:folders.map(f=>({...f,selected:f.selected??selected.has(f.id)}))});
  }catch(e){return reply({ok:false,error:'kinopub_bookmarks_unavailable',detail:String(e.message||e).slice(0,140)},502)}
 }
 let request={};
 try{request=JSON.parse(opts?.body||'{}')}catch(e){}
 const item=kinoCard(request.item);
 if(!item)return reply({ok:false,error:'bad_item'},400);
 const wanted=new Set(Array.isArray(request.folders)?request.folders.map(String):[]);
 try{
  const available=await kpFolders();
  const allowed=new Set(available.map(f=>f.id));
  const remoteCurrent=await kpSelectedFolders(item.id);
  // Only mutate explicitly selected and existing KinoPub folders. Never
  // overwrite other accounts or all folders with a stale picker payload.
  for(const folder of available){
   const isWanted=wanted.has(folder.id),has=remoteCurrent.has(folder.id);
   if(isWanted===has)continue;
   await kpChangeBookmark(folder.id,item.id,isWanted);
  }
  invalidateKpCache('folders:');
  invalidateKpCache('folderitems:');
  const local=readLocalFolders();
  const newTitle=String(request.create_title||'').trim().slice(0,80);
  let created='';
  if(newTitle){
   created='local:'+Date.now()+'-'+Math.random().toString(36).slice(2,7);
   local[created]={title:newTitle+' (на устройстве)',items:[]};
   wanted.add(created);
  }
  const personal=cinemaStorage.get('bookmarks').filter(x=>String(x.id)!==String(item.id));
  if(wanted.has('personal'))personal.unshift(item);
  cinemaStorage.put('bookmarks',personal,300);
  for(const [fid,entry] of Object.entries(local)){
   if(!entry||typeof entry!=='object')continue;
   const rows=(Array.isArray(entry.items)?entry.items:[]).filter(x=>String(x.id)!==String(item.id));
   if(wanted.has(fid))rows.unshift(item);
   entry.items=rows.slice(0,300);
  }
  saveLocalFolders(local);
  const selected=[...wanted].filter(f=>allowed.has(f)||f==='personal'||Object.prototype.hasOwnProperty.call(local,f));
  return reply({ok:true,added:selected.length>0,selected,created});
 }catch(e){
  return reply({ok:false,error:'kinopub_bookmarks_write_failed',detail:String(e.message||e).slice(0,140)},502);
 }
}
async function kinoWatch(body){
 const item=kinoCard(body?.item);
 if(!item)return reply({ok:false,error:'bad_item'},400);
 const card={...item,watched_at:Math.floor(Date.now()/1000)};
 if(body.media_id)card.media_id=body.media_id;
 if(body.season!=null)card.season=body.season;
 if(body.episode!=null)card.episode=body.episode;
 for(const section of ['history','watching'])
  cinemaStorage.put(section,mergeCinemaRows([card],cinemaStorage.get(section),section==='watching'?100:200),section==='watching'?100:200);
 invalidateKpCache('history:');
 return reply({ok:true});
}
async function kinoProgress(opts,query){
 if(!cinemaStatus())return reply({ok:false,error:'kinopub_auth_required'},401);
 if((opts?.method||'GET').toUpperCase()==='GET'){
  const itemId=String(query.get('item_id')||'').trim();
  const mediaId=String(query.get('media_id')||'').trim();
  if(!itemId)return reply({ok:false,error:'missing_item_id'},400);
  const all=read('cinema-progress',{});
  const local=all[itemId+'|'+mediaId]||{};
  if(Number(local.position)>0)return reply({ok:true,progress:local});
  // Retrieve remote resume only when no local position exists.
  if(/^\d+$/.test(itemId)){
   try{
    const result=await kpCached('/v1/watching',{id:itemId},25000,'watching:');
    const entry=result?.item||result?.data?.item||result||{};
    const seconds=Number(entry.time??entry.position??entry.marktime??0);
    if(Number.isFinite(seconds)&&seconds>0)
     return reply({ok:true,progress:{item_id:itemId,media_id:mediaId,position:seconds,duration:0,from:'KINOPUB'}});
   }catch(e){}
  }
  return reply({ok:true,progress:local});
 }
 let body={};try{body=JSON.parse(opts?.body||'{}')}catch(e){}
 const id=String(body.item_id||''),mediaId=String(body.media_id||'');
 const pos=Number(body.position||0),duration=Number(body.duration||0);
 if(!id||!Number.isFinite(pos)||pos<0||!Number.isFinite(duration)||duration<0)
  return reply({ok:false,error:'bad_progress'},400);
 const done=duration>0&&pos/duration>=.96;
 const data={item_id:id,media_id:mediaId,position:done?0:pos,duration,completed:done,
  season:body.season??null,episode:body.episode??null,updated_at:Math.floor(Date.now()/1000)};
 const all=read('cinema-progress',{});
 all[id+'|'+mediaId]=data;
 const keys=Object.keys(all);
 if(keys.length>600)for(const k of keys.slice(0,keys.length-450))delete all[k];
 try{save('cinema-progress',all)}catch(e){}
 // The provider expects video number (episode) and season (for serials).
 // Report only actual playback positions; never mark an untouched title.
 if(!/^\d+$/.test(id)||pos<=0)return reply({ok:true,progress:data,remote_updated:false});
 try{
  const params={access_token:await access(),id,time:Math.floor(pos),
   video:Math.max(1,Number(body.episode)||1)};
  if(Number(body.season)>0)params.season=Number(body.season);
  const result=await kp('/v1/watching/marktime',params);
  if(result?.error||Number(result?.status||200)>=400)
   throw Error(String(result.error||result.message||'marktime failed'));
  invalidateKpCache('watching:');
  invalidateKpCache('history:');
  return reply({ok:true,progress:data,remote_updated:true});
 }catch(e){
  return reply({ok:true,progress:data,remote_updated:false,
   sync_warning:String(e.message||e).slice(0,120)});
 }
}
async function kinoApi(p,q,opts){
 if(p==='/api/cinema/library'&&(opts?.method||'GET').toUpperCase()==='GET')
  return kinoLibrary(q.get('section')||'history',q);
 if(p==='/api/cinema/bookmark-folders')return kinoFolderPicker(q,opts);
 if(p==='/api/cinema/library/watch'){
  if(!cinemaStatus())return reply({ok:false,error:'kinopub_auth_required'},401);
  let body={};try{body=JSON.parse(opts?.body||'{}')}catch(e){}
  return kinoWatch(body);
 }
 if(p==='/api/cinema/progress')return kinoProgress(opts,q);
 return null;
}


// Direct KinoPub endpoints used by the original ABAJ TV interface.
// These do not go through Railway, and never use another user's token.
function kpDeepFindFile(root,compat1080=false,selectedMid=''){
 const seen=new Set(),files=[],all=[];
 function walk(node,depth=0,media=''){
  if(!node||depth>10||typeof node!=='object'||seen.has(node))return;
  seen.add(node);
  if(Array.isArray(node)){for(const x of node)walk(x,depth+1,media);return}
  const ownMid=String(node.media_id||node.mid||node.id||media);
  if(typeof node.file==='string'&&node.file.trim()){
   const quality=String(node.quality??node.h??node.height??node.resolution??'');
   const q=Number((quality.match(/2160|1440|1080|720|480|360/)||[])[0]||Number(quality)||0);
   files.push({file:node.file.trim(),q,codec:String(node.codec||'').toLowerCase(),mid:media||ownMid});
  }
  for(const key of ['videos','seasons','episodes','files','items','data','media','links']){
   if(node[key])walk(node[key],depth+1,(/videos|seasons|episodes|media|files/.test(key)?ownMid:media));
  }
 }
 walk(root);
 if(!files.length)return '';
 const filtered=selectedMid?files.filter(f=>String(f.mid)===String(selectedMid)):[];
 const available=filtered.length?filtered:files;
 const allowed=compat1080?available.filter(f=>f.q>0&&f.q<=1080):available;
 const choices=allowed.length?allowed:available;
 choices.sort((a,b)=>{
  const aq=compat1080?Math.min(a.q||1080,1080):a.q;
  const bq=compat1080?Math.min(b.q||1080,1080):b.q;
  return bq-aq || Number(/h264|avc/.test(b.codec))-Number(/h264|avc/.test(a.codec));
 });
 return choices[0].file;
}
function kpDirectVideoUrl(obj,prefer='hls'){
 const seen=new Set();
 const order=[prefer,'hls','hls2','hls4','http','dash','stream','video_url','stream_url','url','link'];
 function find(v,depth=0){
  if(typeof v==='string')return URL_OK(v)?v:'';
  if(!v||typeof v!=='object'||depth>8||seen.has(v))return '';
  seen.add(v);
  if(Array.isArray(v)){for(const row of v){const found=find(row,depth+1);if(found)return found}return ''}
  for(const key of order){
   if(v[key]!=null){const found=find(v[key],depth+1);if(found)return found}
  }
  if(v.data)return find(v.data,depth+1);
  return '';
 }
 return find(obj);
}
async function kpResolvePlayback(query){
 if(!cinemaStatus())return reply({ok:false,error:'kinopub_auth_required'},401);
 const id=String(query.get('id')||'').trim(),mid=String(query.get('mid')||'').trim();
 let file=String(query.get('file')||'').trim();
 if(!id&&!mid&&!file)return reply({ok:false,error:'missing_item_or_media_id'},400);
 const compat1080=query.get('compat')==='1080';
 const requested=(query.get('format')||'hls').toLowerCase();
 const priority={
  hls:['hls','hls2','http','hls4'],
  hls2:['hls2','hls','http','hls4'],
  hls4:['hls4','hls2','hls','http'],
  http:['http','hls','hls2','hls4']
 }[requested]||['hls','hls2','http','hls4'];
 let lastError='';
 try{
  const token=await access();
  let item=null;
  if(id&&/^\d+$/.test(id)){
   const payload=await kpCached('/v1/items/'+encodeURIComponent(id),{},30000,'item:');
   item=payload?.item||payload;
  }
  if(!file&&item)file=kpDeepFindFile(item,compat1080,mid);
  if(!file&&mid){
   try{
    const media=await kp('/v1/items/media-links',{access_token:token,mid});
    file=kpDeepFindFile(media,compat1080,mid);
    if(!file){const direct=kpDirectVideoUrl(media,requested);if(direct)return reply({ok:true,url:direct,headers:{},provider:'KINOPUB'})}
   }catch(e){lastError=String(e.message||e)}
  }
  if(!file&&item){
   const direct=kpDirectVideoUrl(item,requested);
   if(direct)return reply({ok:true,url:direct,headers:{},provider:'KINOPUB'});
  }
  if(!file)return reply({ok:false,error:'kinopub_media_file_not_found',detail:lastError},404);
  for(const type of priority){
   try{
    const link=await kp('/v1/items/media-video-link',{access_token:token,file,type});
    const url=kpDirectVideoUrl(link,type);
    if(url)return reply({ok:true,url,headers:{},provider:'KINOPUB',format:type});
   }catch(e){lastError=String(e.message||e)}
  }
  return reply({ok:false,error:'kinopub_stream_not_found',detail:lastError},502);
 }catch(e){return reply({ok:false,error:'kinopub_stream_failed',detail:String(e.message||e).slice(0,180)},502)}
}
async function kpGenreSection(section){
 const raw=await kpCached('/v1/genres',{},30*60*1000,'genres:');
 const genres=extractKp(raw);
 return genres.filter(g=>{
  const s=String(g.title||g.name||'').toLowerCase();
  return section==='anime'?(/аниме|anime/.test(s)):(/мульт|cartoon|animation|animated/.test(s)&&!/аниме|anime/.test(s));
 }).map(g=>String(g.id||'')).filter(Boolean).join(',');
}
function kpSectionFilter(raw,section,requested=''){
 const type=String(raw.type||raw.raw_type||'').toLowerCase();
 const group=String(raw.group||'').toLowerCase();
 const genres=kpLabelRows(raw.genres||raw.genre).toLowerCase();
 const isAnime=/аниме|anime/.test(genres)||group==='anime';
 const isCartoon=/мульт|cartoon|animation/.test(genres)||group==='cartoons';
 const isSerial=/serial|series|tvshow|docuserial|docseries/.test(type);
 if(section==='anime')return isAnime;
 if(section==='cartoons')return isCartoon&&!isAnime;
 if(section==='movies')return !isSerial&&!isAnime&&!isCartoon;
 if(section==='series')return isSerial&&!isAnime&&!isCartoon;
 if(section==='docmovies')return /documovie|documentary|docmovie/.test(type);
 if(section==='docseries')return /docuserial|documentaryseries|docseries/.test(type);
 if(section==='tvshows')return type==='tvshow';
 if(section==='concerts')return type==='concert';
 if(requested==='series'||requested==='serial')return isSerial;
 if(requested==='movies'||requested==='movie')return !isSerial;
 return true;
}
async function kpLoadSection(query,catalog=false){
 if(!cinemaStatus())return reply({ok:false,error:'kinopub_auth_required',items:[]},401);
 const section=(query.get('section')||'movies').toLowerCase(),q=query.get('q')||'';
 const requested=query.get('type')||'',sort=query.get('sort')||'';
 const page=Math.max(1,Math.min(1000,Number(query.get('page')||1)||1));
 const perpage=Math.max(10,Math.min(60,Number(query.get('perpage')||40)||40));
 const apiType=/series|serial/.test(requested)?'serial':(/movies|movie/.test(requested)?'movie':'');
 let path=q?'/v1/items/search':'/v1/items',params={page,perpage};
 if(catalog){
  if(q)params.q=q;
  else params.sort='updated-';
  if(apiType)params.type=apiType;
  if(query.get('genre'))params.genre=query.get('genre');
  if(query.get('actor')){params.actor=query.get('actor');delete params.q}
 }else if(section==='collections')path='/v1/collections';
 else if(['fresh','popular','hot'].includes(section)){
  path='/v1/items/'+section;
  params.type=apiType||'movie';
 }else if(section==='4k'){
  params.quality='4k';
  if(apiType)params.type=apiType;
 }else if(section==='cartoons'||section==='anime'){
  try{const ids=await kpGenreSection(section);params.genre=ids|| (section==='anime'?'аниме':'мультфильм')}
  catch(e){params.genre=section==='anime'?'аниме':'мультфильм'}
 }else{
  const types={movies:'movie',series:'serial',docmovies:'documovie',docseries:'docuserial',
   tvshows:'tvshow',concerts:'concert'};
  params.type=types[section]||apiType||'movie';
 }
 const mappedSort={new:'created-',popular:'views-',hot:'rating-'}[sort]||sort;
 if(mappedSort)params.sort=mappedSort;
 const readPage=async(rpath,rparams)=>{
  const data=await kp(rpath,{access_token:await access(),...rparams});
  const originals=extractKp(data),items=originals.filter(x=>catalog||section==='collections'||section==='4k'||kpSectionFilter(x,section,requested));
  return {data,items};
 };
 try{
  let {data,items}=await readPage(path,params);
  if(!items.length&&['fresh','popular','hot'].includes(section)){
   const sortMap={fresh:'updated-',popular:'views-',hot:'rating-'};
   ({data,items}=await readPage('/v1/items',{page,perpage,type:apiType||'movie',sort:sortMap[section]}));
  }
  // Some provider pages are smaller than requested. Load up to three extras
  // to avoid a nearly-empty first screen, without a server-side background job.
  if(page===1&&items.length<Math.min(perpage,30)&&section!=='collections'){
   const seen=new Set(items.map(x=>String(x.id)));
   for(let next=2;next<=4&&items.length<Math.min(perpage,30);next++){
    let other;try{other=await readPage(path,{...params,page:next})}catch(e){break}
    if(!other.items.length)break;
    let added=0;
    for(const x of other.items){const key=String(x.id);if(!seen.has(key)){seen.add(key);items.push(x);added++}}
    if(!added)break;
   }
  }
  let list=items.map(item=>section==='collections'?{
    ...normalizeKp(item),kind:'collection',source:'KINOPUB_COLLECTION'
   }:normalizeKp(item));
  const rawTotal=Number(data.total??data.pagination?.total);
  const total=Number.isFinite(rawTotal)&&rawTotal>0?rawTotal:null;
  return reply({ok:true,items:list,count:list.length,page,perpage,total,
   has_more:!!list.length&&(total==null||page*perpage<total)});
 }catch(e){
  return reply({ok:false,error:'kinopub_section_unavailable',detail:String(e.message||e).slice(0,200),items:[]},502);
 }
}
async function kpCollectionItems(q){
 if(!cinemaStatus())return reply({ok:false,error:'kinopub_auth_required'},401);
 const id=q.get('id')||'';
 if(!/^\d+$/.test(id))return reply({ok:false,error:'invalid_collection_id'},400);
 try{
  const page=Math.max(1,Number(q.get('page')||1));
  const data=await kp('/v1/collections/view',{access_token:await access(),id,page,perpage:40});
  const items=extractKp(data).map(normalizeKp);
  return reply({ok:true,items,count:items.length,total:data.total??null,page});
 }catch(e){return reply({ok:false,error:'kinopub_collection_unavailable',detail:String(e.message||e)},502)}
}

async function api(path,opts){
 const u=new URL(path,'https://abaj.local'),p=u.pathname,q=u.searchParams,method=(opts?.method||'GET').toUpperCase();
 if(p==='/api/me')return reply({id:1,is_admin:false,language:localStorage.getItem('abaj_lang')||'ru',source_permissions:{iptv:true,cinema:true}});
 if(p==='/api/tv/device-auth')return reply({ok:true,authenticated:true,paired:true,device_id:'standalone'});
 if(p==='/api/iptv/state'){
  const state=read('iptv-state',{favorites:[],recent:[],last_channel:'',layout:'grid',tv_mode:true,updated_at:Date.now()/1000});
  if(method==='POST'){try{const d=JSON.parse(opts?.body||'{}');if(d.favorite_op){const f=new Set(state.favorites||[]);d.favorite_op.enabled?f.add(d.favorite_op.id):f.delete(d.favorite_op.id);state.favorites=[...f]}else Object.assign(state,d);state.updated_at=Date.now()/1000;save('iptv-state',state)}catch(e){}}
  return reply(state);
 }
 if(p==='/api/iptv/channels'){const rows=await freeList();channelCache=rows;return reply({channels:rows,stats:{offline:0},running:false})}
 if(p==='/api/iptv/edem/channels'){const data=await customList();channelCache.push(...data.channels);return reply(data)}
 if(p==='/api/iptv/edem/status'){const active=sources().length>0;return reply({active,configured:active,days_left:null,device_limit:0,device_count:1,payment:{status:'paid'}})}
 if(p==='/api/iptv/play'||p==='/api/iptv/edem/play')return reply({url:getItemUrl(q.get('id'))});
 if(p==='/api/iptv/refresh'){save('free-cache',null);for(const x of sources())save('playlist-cache-'+x.id,null);return reply({ok:true})}
 if(p==='/api/cinema/source-state')return reply({source:'kinopub',cinema_enabled:true,playback_allowed:true});
 if(p==='/api/kinopub/status')return reply({ok:true,authenticated:cinemaStatus(),pending:false,owner:false,verification_uri:'https://kino.pub/device'});
 if(p==='/api/kinopub/catalog'||p==='/api/kinopub/section')return kpLoadSection(q,p.endsWith('/catalog'));
 if(p==='/api/kinopub/play')return kpResolvePlayback(q);
 if(p==='/api/kinopub/collection')return kpCollectionItems(q);
 if(p==='/api/kinopub/item')return kpItemDetail(q.get('id'));
 if(p==='/api/kinopub/overview')return reply({ok:true,movies_total:0,series_total:0});
 if(p==='/api/kinopub/auth/start'||p==='/api/kinopub/auth/poll')return reply({ok:false,error:'Use standalone KinoPub device login in local settings'},400);
 if(p==='/api/cinema/library'||p==='/api/cinema/bookmark-folders'||p==='/api/cinema/progress'||p==='/api/cinema/library/watch')
  return kinoApi(p,q,opts);
 if(p==='/api/app-release')return reply({available:false,version_code:0});
 if(p.startsWith('/api/admin/'))return reply({ok:false,error:'Unavailable in standalone build'},403);
 return reply({ok:false,error:'Standalone endpoint not implemented: '+p},404);
}
const originalFetch=window.fetch.bind(window);
window.fetch=function(input,opts){const path=typeof input==='string'?input:input?.url||'';if(path.startsWith('/api/'))return api(path,opts);return originalFetch(input,opts)};
function safe(t){return String(t||'').replace(/[&<>"']/g,ch=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[ch]||ch))}
function settings(){
 if(document.getElementById('standaloneConfig'))return;
 const css=document.createElement('style');css.textContent=`
 #standaloneConfig{position:fixed;z-index:99000;inset:0;background:#001c32aa;align-items:center;justify-content:center;padding:15px}
 #standaloneConfig[hidden]{display:none!important}
 #standaloneConfig:not([hidden]){display:flex}
 #standaloneConfig .standaloneSheet{overscroll-behavior:contain}
 #standaloneConfig .savedPlaylists{max-height:260px;overflow:auto;margin-bottom:10px}
 #standaloneConfig .savedRow{padding:10px 0;border-bottom:1px solid #cadee8;display:flex;align-items:center;justify-content:space-between;gap:8px}
 #standaloneConfig .savedDetails{min-width:0;flex:1}
 #standaloneConfig .savedDetails b,#standaloneConfig .savedDetails small{display:block;overflow:hidden;text-overflow:ellipsis;white-space:nowrap}
 #standaloneConfig .savedActions{display:flex;gap:6px;flex:none}
 #standaloneConfig .savedActions button{font-size:13px;padding:8px}
 #standaloneConfig button:focus-visible{outline:3px solid #e8aa15}
 #standaloneConfig #standaloneCancel{background:#64859d}
 #standaloneConfig #standalonePlaylistStatus{min-height:20px;font-size:13px;font-weight:700;margin-top:10px}
 
 #standaloneConfig .standaloneSheet{background:#f2f9ff;color:#133b5a;border:2px solid #63b6e9;border-radius:20px;max-height:85vh;overflow:auto;max-width:520px;width:100%;padding:22px;box-shadow:0 15px 70px #0007;font-family:system-ui,sans-serif}
 #standaloneConfig input{width:100%;padding:11px;border:1px solid #87b5db;background:white;color:#13263a;border-radius:10px;margin:5px 0 12px;font-size:15px}
 #standaloneConfig button,.standaloneConfigBtn{background:#1287d2;color:white;border:0;border-radius:12px;padding:11px 14px;font-weight:800}
 #standaloneConfig .danger{background:#be4161}
 #standaloneConfig label{font-size:13px;font-weight:700;display:block}
 #standaloneConfig small{color:#486d88;display:block;margin:8px 0}
 /* Standalone: hide server updater, old version and subscription-only status. */
 #tvSettingsModal #appUpdateBtn,
 #tvSettingsModal #appVersionText,
 #tvSettingsModal #standaloneLegacyStatus { display:none!important; }
 #tvSettingsModal #supportAdminBtn, #tvSettingsModal #deviceManager { display:none!important; }
 #standaloneConfig #standaloneKpSync { font-size:14px; padding:8px 12px; line-height:1.2; border-radius:10px; }
 #standaloneConfig #standaloneKpOut:not([hidden]) { display:block; margin-top:12px; }
 `;
 document.head.appendChild(css);
 const el=document.createElement('div');el.id='standaloneConfig';el.hidden=true;
 el.innerHTML='<div class="standaloneSheet"><div style="display:flex;justify-content:space-between;align-items:center"><h2 style="margin:0">ABAJ TV · Источники</h2><button id="standaloneClose">✕</button></div><h3>Сохранённые IPTV-плейлисты <span id="standaloneSavedCount"></span></h3><div class="savedPlaylists" id="standaloneRows"></div><h3 id="standaloneEditorTitle">Добавить плейлист</h3><label>Название плейлиста</label><input id="standaloneListName" placeholder="Например, Free TV"><label>Прямая ссылка M3U</label><input id="standaloneListUrl" placeholder="https://..."><button id="standaloneAdd">Добавить плейлист</button> <button id="standaloneCancel" hidden>Отмена</button><div id="standalonePlaylistStatus" aria-live="polite"></div><hr><h3>KinoPub</h3><p id="standaloneKpStatus" aria-live="polite" style="font-weight:700">Нажми «Войти» для получения кода устройства</p><div id="standaloneKpCode" hidden style="padding:12px;background:#d9efff;border-radius:14px;margin:12px 0"><small>1. Открой на телефоне kino.pub/device</small><div id="standaloneKpUserCode" style="font-size:30px;font-weight:900;letter-spacing:3px;margin:6px 0"></div><small>2. Введи этот код и подтверди устройство. ABAJ TV подключится автоматически.</small><button id="standaloneKpCopy" type="button">Копировать код</button> <button id="standaloneKpVisit" type="button">Открыть сайт</button></div><button id="standaloneConnect">Войти в KinoPub</button> <button id="standaloneKpSync">Синхронизировать</button> <button id="standaloneKpOut" class="danger">Выйти</button><details id="standaloneKpAdvanced" style="margin-top:12px"><summary style="cursor:pointer;font-weight:800">Дополнительные настройки OAuth</summary><label>OAuth Client ID</label><input id="standaloneClientId" autocomplete="off"><label>OAuth Client Secret</label><input type="password" id="standaloneClientSecret" autocomplete="off"><button id="standaloneKpSaveClient" type="button">Сохранить параметры</button> <button id="standaloneKpResetClient" type="button">Сбросить</button><small>Нужны только если KinoPub выдал тебе отдельные параметры клиента.</small></details><hr><button id="standaloneRefresh">Обновить каналы</button></div>';
 document.body.appendChild(el);
 // The original "Подключить IPTV / KinoPub" button is the only entry point.
 // Do not inject a second "Источники (без сервера)" button at the bottom.
 const close=()=>{el.hidden=true;cancelEdit()};
 el.querySelector('#standaloneClose').onclick=close;
 let editingId=null;
 const nameInput=el.querySelector('#standaloneListName');
 const urlInput=el.querySelector('#standaloneListUrl');
 const addButton=el.querySelector('#standaloneAdd');
 const cancelButton=el.querySelector('#standaloneCancel');
 const editorTitle=el.querySelector('#standaloneEditorTitle');
 function cancelEdit(){
  editingId=null;
  nameInput.value='';
  urlInput.value='';
  addButton.textContent='Добавить плейлист';
  editorTitle.textContent='Добавить плейлист';
  cancelButton.hidden=true;
 }
 function editPlaylist(id){
  const item=sources().find(p=>p.id===id);
  if(!item)return;
  editingId=id;
  nameInput.value=item.name;
  urlInput.value=item.url;
  editorTitle.textContent='Изменить плейлист';
  addButton.textContent='Сохранить изменения';
  cancelButton.hidden=false;
  editorTitle.scrollIntoView({block:'nearest',behavior:'smooth'});
  nameInput.focus();
 }
 function paintRows(){
  const lists=sources(),host=el.querySelector('#standaloneRows');
  host.replaceChildren();
  el.querySelector('#standaloneSavedCount').textContent='('+lists.length+')';
  if(!lists.length){
   const empty=document.createElement('small');
   empty.textContent='Плейлистов пока нет. Добавь первый ниже.';
   host.appendChild(empty);
  }
  for(const item of lists){
   const row=document.createElement('div');row.className='savedRow';
   const info=document.createElement('div');info.className='savedDetails';
   const title=document.createElement('b');title.textContent=item.name;
   const detail=document.createElement('small');
   const h=playlistHealth.get(item.id);
   let hostName='';
   try{hostName=new URL(item.url).hostname}catch(e){}
   const state=h?.loading?'Загрузка…':h?.ok?(h.count+' каналов'):(h?.error?'Ошибка загрузки':'Не загружен');
   detail.textContent=hostName+' · '+state;
   if(h?.error)detail.title=h.error;
   info.append(title,detail);
   const actions=document.createElement('div');actions.className='savedActions';
   const edit=document.createElement('button');edit.textContent='Изменить';
   edit.onclick=()=>editPlaylist(item.id);
   const remove=document.createElement('button');remove.className='danger';remove.textContent='Удалить';
   remove.onclick=()=>{
    const next=sources().filter(p=>p.id!==item.id);
    try{save('playlists',next)}catch(e){announcePlaylist('Не удалось удалить: '+e.message,true);return}
    clearPlaylistCache(item.id);playlistHealth.delete(item.id);
    if(editingId===item.id)cancelEdit();
    if(localStorage.getItem('abaj_tv_source_filter')==='playlist:'+item.id)
     localStorage.setItem('abaj_tv_source_filter','free');
    paintRows();announcePlaylist('Плейлист удалён');
    refreshAppPlaylists();
   };
   actions.append(edit,remove);row.append(info,actions);host.appendChild(row);
  }
 }
 window.abajStandaloneRefreshRows=paintRows;
 const paint=()=>{
  paintRows();
  const c=kpClient();
  el.querySelector('#standaloneClientId').value=c.client_id;
  el.querySelector('#standaloneClientSecret').value=c.client_secret;
  paintKp();
 };
 window.abajStandaloneOpenSources=()=>{
  el.hidden=false;
  paint();
 };
 cancelButton.onclick=cancelEdit;
 addButton.onclick=()=>{
  const name=nameInput.value.trim(),url=urlInput.value.trim();
  let valid=false;
  try{valid=['http:','https:'].includes(new URL(url).protocol)}catch(e){}
  if(!name||!valid){announcePlaylist('Укажи название и правильную ссылку http(s)',true);return}
  const lists=sources();
  if(lists.some(x=>x.url===url&&x.id!==editingId)){
   announcePlaylist('Такой адрес уже добавлен. Нажми «Изменить» в сохранённом плейлисте.',true);return;
  }
  const old=editingId?lists.find(x=>x.id===editingId):null;
  if(editingId&&!old){cancelEdit();announcePlaylist('Плейлист не найден. Повтори сохранение.',true);return}
  const id=old?.id||'list'+Date.now()+'-'+Math.random().toString(36).slice(2,7);
  const changedUrl=!!old&&old.url!==url;
  const updated=old?lists.map(x=>x.id===id?{...x,name,url}:x):[...lists,{id,name,url}];
  try{save('playlists',updated)}
  catch(e){announcePlaylist('Не удалось сохранить: '+e.message,true);return}
  if(changedUrl){clearPlaylistCache(id);playlistHealth.delete(id)}
  cancelEdit();paintRows();
  announcePlaylist(old?'Изменения сохранены. Обновляем каналы…':'Плейлист добавлен. Обновляем каналы…');
  refreshAppPlaylists(id);
 };
 el.querySelector('#standaloneRefresh').onclick=()=>{
  playlistCache.clear();playlistHealth.clear();
  announcePlaylist('Обновляем все плейлисты…');
  refreshAppPlaylists();paintRows();
 };

 let kpPending=null,kpPollTimer=null,kpGeneration=0,kpBusy=false;
 const kpStatus=el.querySelector('#standaloneKpStatus');
 const kpCodeBox=el.querySelector('#standaloneKpCode');
 const kpCodeText=el.querySelector('#standaloneKpUserCode');
 const kpConnect=el.querySelector('#standaloneConnect');
 const kpDisconnect=el.querySelector('#standaloneKpOut');
 function clearKpPoll(){if(kpPollTimer){clearTimeout(kpPollTimer);kpPollTimer=null}}
 function stopKpPoll(){kpGeneration++;clearKpPoll();kpPending=null;kpBusy=false}
 function paintKp(){
  const connected=cinemaStatus();
  kpConnect.hidden=connected;
  kpDisconnect.hidden=!connected;
  el.querySelector('#standaloneKpSync').hidden=!connected;
  kpCodeBox.hidden=!kpPending||connected;
  const advanced=el.querySelector('#standaloneKpAdvanced');
  if(advanced){
   advanced.hidden=connected;
   if(connected)advanced.open=false;
  }
  if(kpPending){
   kpCodeText.textContent=kpPending.userCode;
   kpStatus.textContent='Ожидаем подтверждения в KinoPub…';
  }else if(connected)kpStatus.textContent='✓ KinoPub подключён';
  else kpStatus.textContent='Нажми «Войти в KinoPub», чтобы получить код';
 }
 // Keep authorization polling even when the settings sheet is closed or a mobile
 // browser is opened for device approval. Stop only on logout, expiry, or failure.
 function scheduleKpPoll(generation,delayMs){
  clearKpPoll();
  if(generation!==kpGeneration||!kpPending)return;
  kpPollTimer=setTimeout(()=>pollKp(generation),delayMs);
 }
 async function pollKp(generation){
  if(generation!==kpGeneration||!kpPending||kpBusy)return;
  if(Date.now()>=kpPending.expiresAt){
   stopKpPoll();kpStatus.textContent='Код истёк. Нажми «Войти», чтобы получить новый.';paintKp();return;
  }
  kpBusy=true;
  let nextDelay=kpPending.intervalMs;
  try{
   const config=kpClient();
   const result=await kp('/oauth2/device',{grant_type:'device_token',...config,code:kpPending.code},'POST');
   if(generation!==kpGeneration)return;
   if(result.access_token){
    const token={access_token:result.access_token,refresh_token:result.refresh_token||'',
     expires_at:Date.now()+Number(result.expires_in||3600)*1000};
    try{save('kino-token',token)}catch(e){stopKpPoll();kpStatus.textContent='Не удалось сохранить вход KinoPub';return}
    stopKpPoll();
    paintKp();
    try{window.loadGlobalCinemaSource?.()}catch(e){}
    try{window.loadCinemaCatalog?.(true)}catch(e){}
    return;
   }
   if(result.error==='slow_down')nextDelay+=5000;
   else if(result.error&&result.error!=='authorization_pending')
    throw Error(result.error_description||result.error);
  }catch(e){
   if(generation!==kpGeneration)return;
   const msg=String(e.message||e);
   if(/slow_down/i.test(msg))nextDelay+=5000;
   else if(/authorization_pending/i.test(msg)){}
   else if(/expired|invalid_grant|access_denied|authorization_declined/i.test(msg)){
    stopKpPoll();paintKp();kpStatus.textContent='Код не подтверждён или истёк. Запроси новый.';return;
   }else{
    // Transient connectivity errors should not discard the active device code.
    kpStatus.textContent='Ожидаем KinoPub (повторное подключение)…';
    nextDelay=Math.max(nextDelay,10000);
   }
  }finally{kpBusy=false}
  if(generation===kpGeneration&&kpPending)scheduleKpPoll(generation,nextDelay);
 }
 kpConnect.onclick=async()=>{
  if(kpBusy)return;
  stopKpPoll();kpConnect.disabled=true;kpStatus.textContent='Получаем код KinoPub…';
  const current=kpGeneration;
  try{
   const result=await kp('/oauth2/device',{grant_type:'device_code',...kpClient()},'POST');
   if(current!==kpGeneration)return;
   const code=String(result.code||result.device_code||'');
   const userCode=String(result.user_code||'');
   if(!code||!userCode)throw Error('Сервис KinoPub не прислал код');
   // KinoPub's API may return a legacy or alternate verification URL.
   // Device approval is always available through the canonical documented
   // https://kino.pub/device. Do not follow arbitrary untrusted API URLs.
   const verifyUrl='https://kino.pub/device';
   kpPending={code,userCode,verifyUrl,expiresAt:Date.now()+Math.max(60,Number(result.expires_in)||600)*1000,
    intervalMs:Math.max(5000,Number(result.interval||5)*1000)};
   kpStatus.textContent='Ожидаем подтверждения в KinoPub…';
   paintKp();scheduleKpPoll(current,kpPending.intervalMs);
  }catch(e){
   if(current===kpGeneration){
    paintKp();kpStatus.textContent='Не удалось получить код KinoPub: '+String(e.message||e).slice(0,220);
   }
  }finally{kpConnect.disabled=false}
 };
 kpDisconnect.onclick=()=>{
  stopKpPoll();
  localStorage.removeItem(key('kino-token'));
  // Never show a previous KinoPub account's library to someone who signs in later.
  invalidateKpCache();
  for(const section of ['history','watching','bookmarks','progress','folders'])
   localStorage.removeItem(key('cinema-'+section));
  paintKp();
 };
 el.querySelector('#standaloneKpSync').onclick=async()=>{
  const btn=el.querySelector('#standaloneKpSync');
  btn.disabled=true;
  kpStatus.textContent='Синхронизируем избранное и историю с KinoPub…';
  invalidateKpCache();
  try{
   const [history,bookmarks]=await Promise.all([kinoHistory(),kinoBookmarksFlat()]);
   kpStatus.textContent='✓ Синхронизация: история '+history.length+', избранное '+bookmarks.length;
   try{window.refreshCinemaLibraryCounts?.()}catch(e){}
  }catch(e){
   kpStatus.textContent='Ошибка синхронизации: '+String(e.message||e).slice(0,150);
  }finally{btn.disabled=false}
 };
 el.querySelector('#standaloneKpCopy').onclick=async()=>{
  const code=kpPending?.userCode||'';
  if(!code)return;
  let copied=false;
  try{if(navigator.clipboard?.writeText){await navigator.clipboard.writeText(code);copied=true}}catch(e){}
  if(!copied){
   const inp=document.createElement('input');inp.value=code;document.body.appendChild(inp);
   inp.select();try{copied=!!document.execCommand('copy')}catch(e){}
   inp.remove();
  }
  if(!copied)kpStatus.textContent='Код: '+code+' (введи его на kino.pub/device)';
  else kpStatus.textContent='Код скопирован: '+code;
 };
 el.querySelector('#standaloneKpVisit').onclick=()=>{
  if(!kpPending)return;
  // Android's WebView URL handler opens external HTTPS links in the browser.
  window.location.href=kpPending.verifyUrl;
 };
 el.querySelector('#standaloneKpSaveClient').onclick=()=>{
  const c={client_id:el.querySelector('#standaloneClientId').value.trim(),
   client_secret:el.querySelector('#standaloneClientSecret').value.trim()};
  if(!c.client_id||!c.client_secret){kpStatus.textContent='Заполни оба параметра OAuth либо нажми «Сбросить»';return}
  try{save('kino-client',c);stopKpPoll();paintKp();kpStatus.textContent='Параметры OAuth сохранены'}
  catch(e){kpStatus.textContent='Ошибка сохранения OAuth'}
 };
 el.querySelector('#standaloneKpResetClient').onclick=()=>{
  localStorage.removeItem(key('kino-client'));stopKpPoll();
  const c=kpClient();el.querySelector('#standaloneClientId').value=c.client_id;
  el.querySelector('#standaloneClientSecret').value=c.client_secret;
  paintKp();kpStatus.textContent='Параметры KinoPub восстановлены';
 };
 document.addEventListener('visibilitychange',()=>{
  if(document.visibilityState==='visible'&&kpPending&&!kpBusy&&Date.now()<kpPending.expiresAt)
   scheduleKpPoll(kpGeneration,Math.max(1000,kpPending.intervalMs));
 });
 paintKp();
}
document.addEventListener('DOMContentLoaded',settings);
})();