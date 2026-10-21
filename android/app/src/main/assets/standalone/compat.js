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
const kpClient=()=>read('kino-client',null)||{client_id:'xbmc',client_secret:''};
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
function normalizeKp(x){
 const item=x||{},pics=item.posters||item.poster||{},pic=(typeof pics==='string'?pics:(pics.medium||pics.big||pics.small||pics.url||''))||'';
 return {...item,id:item.id,title:item.title||item.name||'',poster:pic,poster_url:pic,
 kind:/serial|series/i.test(String(item.type||''))?'series':'movie',source:'KINOPUB'};
}
function extractKp(data){if(Array.isArray(data))return data;for(const k of ['items','data','results','movies','serials'])if(data&&data[k]){const a=extractKp(data[k]);if(a.length)return a}return []}
function getItemUrl(id){return channelCache.find(x=>String(x.id)===String(id))?.url||''}
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
 if(p==='/api/kinopub/overview')return reply({ok:true,movies_total:0,series_total:0});
 if(p==='/api/kinopub/auth/start'||p==='/api/kinopub/auth/poll')return reply({ok:false,error:'Use standalone KinoPub device login in local settings'},400);
 if(p==='/api/cinema/library')return reply({ok:true,items:[],folders:[],count:0});
 if(p==='/api/cinema/bookmark-folders')return reply({ok:true,folders:[]});
 if(p==='/api/cinema/progress')return reply({ok:true});
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
 el.innerHTML='<div class="standaloneSheet"><div style="display:flex;justify-content:space-between;align-items:center"><h2 style="margin:0">ABAJ TV · Источники</h2><button id="standaloneClose">✕</button></div><h3>Сохранённые IPTV-плейлисты <span id="standaloneSavedCount"></span></h3><div class="savedPlaylists" id="standaloneRows"></div><h3 id="standaloneEditorTitle">Добавить плейлист</h3><label>Название плейлиста</label><input id="standaloneListName" placeholder="Например, Free TV"><label>Прямая ссылка M3U</label><input id="standaloneListUrl" placeholder="https://..."><button id="standaloneAdd">Добавить плейлист</button> <button id="standaloneCancel" hidden>Отмена</button><div id="standalonePlaylistStatus" aria-live="polite"></div><small>Ссылки сохраняются только на этом устройстве. Основной сервер не используется.</small><hr><h3>KinoPub</h3><label>OAuth Client ID</label><input id="standaloneClientId" value="xbmc"><label>OAuth Client Secret</label><input type="password" id="standaloneClientSecret" placeholder="Секрет официального OAuth-клиента"><button id="standaloneConnect">Подключить KinoPub</button> <button id="standaloneKpOut" class="danger">Выйти</button><p id="standaloneKpStatus"></p><small>У каждого пользователя должна быть своя учётная запись KinoPub.</small><hr><button id="standaloneRefresh">Обновить каналы</button></div>';
 document.body.appendChild(el);
 const targets=['#tvSettingsModal .settingsCard','#settingsModal .settingsCard'];
let mounted=0;
for(const selector of targets){
 const holder=document.querySelector(selector);
 if(!holder)continue;
 const button=document.createElement('button');button.className='standaloneConfigBtn';button.textContent='⚙ Источники (без сервера)';
 button.style.cssText='position:relative;right:auto;bottom:auto;z-index:auto;display:block;margin:12px auto;width:fit-content';
 button.onclick=()=>window.abajStandaloneOpenSources();holder.appendChild(button);mounted++;
}
if(!mounted){const button=document.createElement('button');button.className='standaloneConfigBtn';button.textContent='⚙ Источники';button.onclick=()=>window.abajStandaloneOpenSources();document.body.appendChild(button)}
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
  el.querySelector('#standaloneKpStatus').textContent=cinemaStatus()?'KinoPub подключён':'Для входа введите параметры своего OAuth-клиента';
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
 el.querySelector('#standaloneKpOut').onclick=()=>{save('kino-token',null);paint()};
 el.querySelector('#standaloneConnect').onclick=async()=>{
  const c={client_id:el.querySelector('#standaloneClientId').value.trim(),client_secret:el.querySelector('#standaloneClientSecret').value.trim()};
  save('kino-client',c);const st=el.querySelector('#standaloneKpStatus');
  if(!c.client_id||!c.client_secret){st.textContent='Нужны Client ID и Client Secret для авторизации';return}
  st.textContent='Запрашиваем код KinoPub…';
  try{
   const x=await kp('/oauth2/device',{grant_type:'device_code',...c},'POST');
   const code=x.code||x.device_code;if(!code||!x.user_code)throw Error('KinoPub не прислал код');
   st.innerHTML='Открой <b>kino.pub/device</b> и введи код <b>'+safe(x.user_code)+'</b><br>Ожидаем подтверждение…';
   const expiry=Date.now()+Number(x.expires_in||600)*1000;
   const delay=Math.max(3500,Number(x.interval||5)*1000);
   const loop=async()=>{if(el.hidden)return;if(Date.now()>expiry){st.textContent='Код истёк. Попробуй снова.';return}
    try{const t=await kp('/oauth2/device',{grant_type:'device_token',...c,code},'POST');
     if(t.access_token){save('kino-token',{access_token:t.access_token,refresh_token:t.refresh_token||'',expires_at:Date.now()+Number(t.expires_in||3600)*1000});st.textContent='KinoPub подключён';if(typeof window.loadCinemaCatalog==='function')window.loadCinemaCatalog(true);return}
    }catch(e){if(!/authorization_pending|slow_down/i.test(e.message)){st.textContent=e.message;return}}
    setTimeout(loop,delay)};
   setTimeout(loop,delay)
  }catch(e){st.textContent=e.message}
 };
}
document.addEventListener('DOMContentLoaded',settings);
})();