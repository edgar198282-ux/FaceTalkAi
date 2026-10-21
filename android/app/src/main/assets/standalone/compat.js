(function(){
'use strict';
window.ABAJ_STANDALONE=true;
const STORAGE='abaj_standalone_playlists';
const key=(k)=>'abaj-standalone-'+k;
const read=(k,def)=>{try{const v=JSON.parse(localStorage.getItem(key(k)));return v??def}catch(e){return def}};
const save=(k,v)=>localStorage.setItem(key(k),JSON.stringify(v));
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
const sources=()=>read('playlists',[]);
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
  const cache=read('playlist-cache-'+x.id,null);
  if(cache&&Date.now()-cache.t<3600000)return cache.items;
  try{const items=parseM3U(await nativeRequest(x.url),x.name,x.id,'').slice(0,12000);
   try{save('playlist-cache-'+x.id,{t:Date.now(),items})}catch(e){}
   return items;
  }catch(e){return cache?.items||[]}
 }));
 results.forEach(a=>all.push(...a));
 return{channels:all,playlists:lists.map(x=>({id:x.id,name:x.name,url:x.url}))};
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
function safe(t){return String(t||'').replace(/[&<>"']/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;':'&quot;',"'":'&#39;'}[c]))}
function settings(){
 if(document.getElementById('standaloneConfig'))return;
 const css=document.createElement('style');css.textContent=`
 #standaloneConfig{position:fixed;z-index:99000;inset:0;background:#001c32aa;align-items:center;justify-content:center;padding:15px}
 #standaloneConfig[hidden]{display:none!important}
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
 el.innerHTML='<div class="standaloneSheet"><div style="display:flex;justify-content:space-between;align-items:center"><h2 style="margin:0">ABAJ TV · Источники</h2><button id="standaloneClose">✕</button></div><h3>IPTV / Edo</h3><div id="standaloneRows"></div><label>Название плейлиста</label><input id="standaloneListName" placeholder="Edo IPTV"><label>Прямая ссылка M3U</label><input id="standaloneListUrl" placeholder="https://..."><button id="standaloneAdd">Добавить плейлист</button><small>Ссылки сохраняются только на этом устройстве. Основной сервер не используется.</small><hr><h3>KinoPub</h3><label>OAuth Client ID</label><input id="standaloneClientId" value="xbmc"><label>OAuth Client Secret</label><input type="password" id="standaloneClientSecret" placeholder="Секрет официального OAuth-клиента"><button id="standaloneConnect">Подключить KinoPub</button> <button id="standaloneKpOut" class="danger">Выйти</button><p id="standaloneKpStatus"></p><small>У каждого пользователя должна быть своя учётная запись KinoPub.</small><hr><button id="standaloneRefresh">Обновить каналы</button></div>';
 document.body.appendChild(el);
 const targets=['#tvSettingsModal .settingsCard','#settingsModal .settingsCard'];
let mounted=0;
for(const selector of targets){
 const holder=document.querySelector(selector);
 if(!holder)continue;
 const button=document.createElement('button');button.className='standaloneConfigBtn';button.textContent='⚙ Источники (без сервера)';
 button.style.cssText='position:relative;right:auto;bottom:auto;z-index:auto;display:block;margin:12px auto;width:fit-content';
 button.onclick=()=>{el.hidden=false;paint()};holder.appendChild(button);mounted++;
}
if(!mounted){const button=document.createElement('button');button.className='standaloneConfigBtn';button.textContent='⚙ Источники';button.onclick=()=>{el.hidden=false;paint()};document.body.appendChild(button)}
 const close=()=>{el.hidden=true};
 el.querySelector('#standaloneClose').onclick=close;
 const paint=()=>{const lists=sources();el.querySelector('#standaloneRows').innerHTML=lists.map((x,i)=>'<div style="display:flex;justify-content:space-between;align-items:center;gap:8px;margin-bottom:8px"><span>'+safe(x.name)+'</span><button class="danger" data-remove="'+safe(x.id)+'">Удалить</button></div>').join('')||'<small>Дополнительные плейлисты ещё не добавлены</small>';
 el.querySelectorAll('[data-remove]').forEach(b=>b.onclick=()=>{save('playlists',sources().filter(x=>x.id!==b.dataset.remove));save('playlist-cache-'+b.dataset.remove,null);paint();if(typeof window.load==='function')window.load()});
 const c=kpClient();el.querySelector('#standaloneClientId').value=c.client_id;el.querySelector('#standaloneClientSecret').value=c.client_secret;el.querySelector('#standaloneKpStatus').textContent=cinemaStatus()?'KinoPub подключён':'Для входа введите параметры своего OAuth-клиента';};
 el.querySelector('#standaloneAdd').onclick=()=>{const name=el.querySelector('#standaloneListName').value.trim(),url=el.querySelector('#standaloneListUrl').value.trim();if(!name||!URL_OK(url)){alert('Укажи название и ссылку M3U');return}save('playlists',[...sources(),{id:'list'+Date.now(),name,url}]);el.querySelector('#standaloneListName').value='';el.querySelector('#standaloneListUrl').value='';paint();window.load?.()};
 el.querySelector('#standaloneRefresh').onclick=()=>{save('free-cache',null);for(const x of sources())save('playlist-cache-'+x.id,null);window.load?.();close()};
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