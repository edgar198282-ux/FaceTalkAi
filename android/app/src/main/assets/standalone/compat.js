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
const freeUrl='https://iptv-org.github.io/iptv/countries/am.m3u';
const freeList=async()=>{
 const cache=read('free-cache',null);
 if(cache&&Date.now()-cache.t<86400000)return cache.items;
 try{const rows=parseM3U(await nativeRequest(freeUrl),'Free','free','AM').slice(0,60);
 save('free-cache',{t:Date.now(),items:rows});return rows}catch(e){return cache?.items||[]}
};
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
function normalizeKp(x){
 const item=x&&typeof x==='object'?x:{};
 const pics=item.posters||item.poster||item.cover||{};
 const poster=kpImage(pics);
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
  backdrop:kpImage(item.backdrop)||kpImage(item.background),
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
 if(p==='/api/kinopub/catalog'||p==='/api/kinopub/section'){
  try{const token=await access(),query=q.get('q')||'',section=q.get('section')||'movies',kind=q.get('type')||(/series/.test(section)?'serial':'movie');
    const pg=Number(q.get('page')||1),perpage=Number(q.get('perpage')||40);
    const params={access_token:token,page:pg,perpage,type:/serial|series/i.test(kind)?'serial':'movie'};
    if(query)params.q=query;if(q.get('sort'))params.sort=q.get('sort');
    const data=await kp(query?'/v1/items/search':'/v1/items',params);
    const list=extractKp(data).map(normalizeKp);
    return reply({ok:true,items:list,total:Number(data.total||data.pagination?.total||list.length),has_more:list.length>=perpage});
  }catch(e){return reply({error:String(e.message),items:[]},502)}
 }
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
 .standaloneConfigBtn{position:fixed;z-index:9100;right:12px;bottom:14px;font-size:13px;box-shadow:0 4px 16px #0005}
 `;
 document.head.appendChild(css);
 const el=document.createElement('div');el.id='standaloneConfig';el.hidden=true;
 el.innerHTML='<div class="standaloneSheet"><div style="display:flex;justify-content:space-between;align-items:center"><h2 style="margin:0">ABAJ TV · Источники</h2><button id="standaloneClose">✕</button></div><h3>Сохранённые IPTV-плейлисты <span id="standaloneSavedCount"></span></h3><div class="savedPlaylists" id="standaloneRows"></div><h3 id="standaloneEditorTitle">Добавить плейлист</h3><label>Название плейлиста</label><input id="standaloneListName" placeholder="Например, Free TV"><label>Прямая ссылка M3U</label><input id="standaloneListUrl" placeholder="https://..."><button id="standaloneAdd">Добавить плейлист</button> <button id="standaloneCancel" hidden>Отмена</button><div id="standalonePlaylistStatus" aria-live="polite"></div><small>Ссылки сохраняются только на этом устройстве. Основной сервер не используется.</small><hr><h3>KinoPub</h3><p id="standaloneKpStatus" aria-live="polite" style="font-weight:700">Нажми «Войти» для получения кода устройства</p><div id="standaloneKpCode" hidden style="padding:12px;background:#d9efff;border-radius:14px;margin:12px 0"><small>1. Открой на телефоне kino.pub/device</small><div id="standaloneKpUserCode" style="font-size:30px;font-weight:900;letter-spacing:3px;margin:6px 0"></div><small>2. Введи этот код и подтверди устройство. ABAJ TV подключится автоматически.</small><button id="standaloneKpCopy" type="button">Копировать код</button> <button id="standaloneKpVisit" type="button">Открыть сайт</button></div><button id="standaloneConnect">Войти в KinoPub</button> <button id="standaloneKpSync">↻ Синхронизировать избранное и историю</button> <button id="standaloneKpOut" class="danger">Выйти</button><small>Нужна действующая учётная запись KinoPub. Токен хранится только на этом устройстве.</small><details id="standaloneKpAdvanced" style="margin-top:12px"><summary style="cursor:pointer;font-weight:800">Дополнительные настройки OAuth</summary><label>OAuth Client ID</label><input id="standaloneClientId" autocomplete="off"><label>OAuth Client Secret</label><input type="password" id="standaloneClientSecret" autocomplete="off"><button id="standaloneKpSaveClient" type="button">Сохранить параметры</button> <button id="standaloneKpResetClient" type="button">Сбросить</button><small>Нужны только если KinoPub выдал тебе отдельные параметры клиента.</small></details><hr><button id="standaloneRefresh">Обновить каналы</button></div>';
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