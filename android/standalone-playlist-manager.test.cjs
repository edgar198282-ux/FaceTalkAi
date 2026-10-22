'use strict';
const {test}=require('node:test');
const assert=require('node:assert/strict');
const fs=require('node:fs');
const vm=require('node:vm');
const script=fs.readFileSync('app/src/main/assets/standalone/compat.js','utf8');
function setup(options={}){
 const elements=new Map(),handlers={},storage=new Map();
 const localStorage={
  get length(){return storage.size},
  key(i){return [...storage.keys()][i]??null},
  getItem(k){return storage.has(k)?storage.get(k):null},
  setItem(k,v){storage.set(String(k),String(v))},
  removeItem(k){storage.delete(k)}
 };
 class FakeElement{
  constructor(){this.children=[];this.style={};this.value='';this.hidden=false;this.dataset={};this.textContent='';this._html='';}
  set innerHTML(v){
   this._html=String(v);
   for(const m of this._html.matchAll(/\bid="([^"]+)"/g))
    if(!elements.has(m[1]))elements.set(m[1],new FakeElement());
  }
  get innerHTML(){return this._html}
  appendChild(e){this.children.push(e);return e}
  append(...x){this.children.push(...x)}
  replaceChildren(...x){this.children=[...x]}
  querySelector(s){return elements.get(s.slice(1))||null}
  focus(){}
  scrollIntoView(){}
 }
 const document={head:new FakeElement(),body:new FakeElement(),
  createElement(){return new FakeElement()},
  getElementById(id){return elements.get(id)||null},
  querySelector(){return null},
  addEventListener(event,cb){handlers[event]=cb}
 };
 const samples=new Map(),scheduled=[],requests=[];let menu=[],loads=0;
 const fakeSetTimeout=(fn,ms)=>{const job={fn,ms,active:true};scheduled.push(job);return job};
 const fakeClearTimeout=job=>{if(job)job.active=false};
 const win={
  indexedDB:options.indexedDB,
  fetch:async()=>new Response('{}'),
  renderNamedPlaylistChips:(lists)=>{menu=lists.map(x=>x.name)},
  load:async()=>{loads++},
  StandaloneNetwork:{request(id,url,method,body){
   const parsed=new URL(url),grant=parsed.searchParams.get('grant_type');
   requests.push({url,method,body,path:parsed.pathname});
   const raw=samples.has(url)?samples.get(url):(samples.has(parsed.pathname)?samples.get(parsed.pathname):samples.get(grant));
   win.__abajStandaloneResponse(id,raw===undefined?404:200,raw??'Not found');
  }}
 };
 vm.runInNewContext(script,{window:win,indexedDB:options.indexedDB,document,localStorage,Response,URL,URLSearchParams,console,setTimeout:fakeSetTimeout,clearTimeout:fakeClearTimeout,Date,Math,Promise,Error},{filename:'compat.js'});
 handlers.DOMContentLoaded();
 return{get:id=>elements.get(id),storage,win,samples,requests,scheduled,menu:()=>menu,loads:()=>loads};
}
function add(x,name,url){
 x.get('standaloneListName').value=name;
 x.get('standaloneListUrl').value=url;
 x.get('standaloneAdd').onclick();
}
test('IPTV refresh is above playlists and KinoPub, and EPG count updates below channel total',()=>{
 const x=setup();
 const html=x.get('standaloneConfig').innerHTML;
 const iptv=html.indexOf('<section class="standaloneSourceSection standaloneIptvSection"');
 const refresh=html.indexOf('id="standaloneRefresh"');
 const playlists=html.indexOf('Дополнительные IPTV-плейлисты');
 const kino=html.indexOf('<section class="standaloneSourceSection standaloneKpSection"');
 assert.ok(iptv>=0&&iptv<refresh&&refresh<playlists&&playlists<kino);
 assert.equal(html.split('id="standaloneRefresh"').length-1,1);
 assert.ok(html.indexOf('id="standaloneBuiltinIptvStatus"')<html.indexOf('id="standaloneBuiltinEpgCount"'));
 x.win.abajStandaloneEpgCount=()=>703;
 x.win.abajStandaloneOpenSources();
 assert.equal(x.get('standaloneBuiltinEpgCount').textContent,'EPG: 703');
 assert.ok(x.get('standaloneBuiltinIptvStatus').textContent.includes('каналов'));
 x.win.abajStandaloneEpgCount=()=>712;
 x.win.abajStandaloneUpdateEpgCount();
 assert.equal(x.get('standaloneBuiltinEpgCount').textContent,'EPG: 712');
 assert.equal(typeof x.get('standaloneRefresh').onclick,'function');
 assert.equal(x.get('standaloneKpStatus').hidden,false);
});
test('multiple playlists, edit existing name and URL, delete one without losing other',async()=>{
 const x=setup();
 x.win.abajStandaloneOpenSources();
 add(x,'Эдгар','https://iptv.test/first.m3u');
 add(x,'FREE FULL','https://iptv.test/second.m3u');
 let rows=JSON.parse(x.storage.get('abaj-standalone-playlists'));
 assert.equal(rows.length,2);
 assert.equal(x.get('standaloneSavedCount').textContent,'(2)');
 assert.equal(x.menu().join(','),'Эдгар,FREE FULL');
 const firstId=rows[0].id;
 x.get('standaloneRows').children[0].children[1].children[0].onclick();
 assert.equal(x.get('standaloneListName').value,'Эдгар');
 add(x,'Эдгар 2','https://iptv.test/new.m3u');
 rows=JSON.parse(x.storage.get('abaj-standalone-playlists'));
 assert.equal(rows.length,2);assert.equal(rows[0].id,firstId);
 assert.equal(rows[0].url,'https://iptv.test/new.m3u');
 x.get('standaloneRows').children[1].children[1].children[1].onclick();
 rows=JSON.parse(x.storage.get('abaj-standalone-playlists'));
 assert.equal(rows.length,1);assert.equal(rows[0].name,'Эдгар 2');
});
test('duplicates are rejected and original survives',()=>{
 const x=setup();x.win.abajStandaloneOpenSources();
 add(x,'First','https://t.test/list.m3u');
 add(x,'Duplicate','https://t.test/list.m3u');
 assert.equal(JSON.parse(x.storage.get('abaj-standalone-playlists')).length,1);
 assert.match(x.get('standalonePlaylistStatus').textContent,/уже добавлен/);
});
test('15,129 channels import completely, without storing giant cache',async()=>{
 const x=setup();x.win.abajStandaloneOpenSources();
 const url='https://t.test/all.m3u';let m='#EXTM3U\n';
 for(let i=0;i<15129;i++)m+='#EXTINF:-1 group-title="Free",TV '+i+'\nhttps://t.test/tv/'+i+'.m3u8\n';
 x.samples.set(url,m);add(x,'ABAJ Free',url);
 const r=await x.win.fetch('/api/iptv/edem/channels'),body=await r.json();
 assert.equal(body.channels.length,15129);
 assert.equal(body.playlists.length,1);
 assert.equal([...x.storage.keys()].filter(k=>k.includes('cache')).length,0);
});


test('built-in IPTV keeps highest quality and distinguishes time shifts, regional versions and user playlists',async()=>{
 const x=setup();
 x.samples.set('https://iptv-org.github.io/iptv/countries/ru.m3u',[
  '#EXTM3U',
  '#EXTINF:-1 tvg-id="Mir.ru",Mir +2 (540p) [Not 24/7]',
  'https://stream.test/mir-plus2-sd.m3u8',
  '#EXTINF:-1 tvg-id="Mir.ru",Mir +2 (1080p)',
  'https://stream.test/mir-plus2-fhd.m3u8',
  '#EXTINF:-1,Mir +7 (540p)',
  'https://stream.test/mir-plus7.m3u8',
  '#EXTINF:-1,Mir (720p)',
  'https://stream.test/mir-hd.m3u8',
  '#EXTINF:-1,Mir (1080p)',
  'https://stream.test/mir-fhd.m3u8',
  '#EXTINF:-1,Mir Moscow (720p)',
  'https://stream.test/mir-moscow.m3u8'
 ].join('\n'));
 x.samples.set('https://iptv-org.github.io/iptv/countries/am.m3u',[
  '#EXTM3U',
  '#EXTINF:-1,Armenia 1 (576p)',
  'https://stream.test/armenia1-sd.m3u8',
  '#EXTINF:-1,Armenia 1 (1080p)',
  'https://stream.test/armenia1-fhd.m3u8',
  '#EXTINF:-1,Armenia 1 America (1080p)',
  'https://stream.test/armenia1-us.m3u8'
 ].join('\n'));
 await x.win.abajStandaloneGetIptvChannels();
 const update=x.scheduled.find(job=>job.active&&job.ms===50);
 assert.ok(update);
 await update.fn();
 const rows=await x.win.abajStandaloneGetIptvChannels();
 const plus2=rows.filter(c=>/^mir \+2\b/i.test(c.name));
 assert.equal(plus2.length,1);
 assert.equal(plus2[0].url,'https://stream.test/mir-plus2-fhd.m3u8');
 assert.ok(plus2[0].backups.includes('https://stream.test/mir-plus2-sd.m3u8'));
 assert.equal(rows.filter(c=>/^mir \+7\b/i.test(c.name)).length,1);
 assert.equal(rows.filter(c=>/^mir \(/i.test(c.name)).length,1);
 assert.equal(rows.filter(c=>/^mir moscow\b/i.test(c.name)).length,1);
 const armenia=rows.filter(c=>/^armenia 1(?: \(|$)/i.test(c.name));
 assert.equal(armenia.length,1);
 assert.equal(armenia[0].height,1080);
 assert.ok(rows.some(c=>/^armenia 1 america/i.test(c.name)));
 assert.ok(rows.every(c=>c.personal===false));
});

test('KinoPub: one tap requests a device code without manual OAuth inputs',async()=>{
 const x=setup();x.win.abajStandaloneOpenSources();
 const st=x.get('standaloneKpStatus');
 assert.equal(x.get('standaloneKpAdvanced').hidden,false);
 assert.equal(x.get('standaloneKpCode').hidden,true);
 x.samples.set('device_code',JSON.stringify({
  code:'private-device-code',user_code:'ABCD12',
  verification_uri:'https://kino.pub/device',expires_in:600,interval:5
 }));
 await x.get('standaloneConnect').onclick();
 assert.equal(x.get('standaloneKpUserCode').textContent,'ABCD12');
 assert.equal(x.get('standaloneKpCode').hidden,false);
 assert.match(st.textContent,/Ожидаем/);
 const timer=x.scheduled.find(t=>t.active&&t.ms===5000);
 assert.ok(timer,'Device flow must schedule polling');
 x.samples.set('device_token',JSON.stringify({
  access_token:'personal-access-token',refresh_token:'personal-refresh-token',expires_in:3600
 }));
 timer.active=false;
 await timer.fn();
 const token=JSON.parse(x.storage.get('abaj-standalone-kino-token'));
 assert.equal(token.access_token,'personal-access-token');
 assert.equal(x.get('standaloneKpCode').hidden,true);
 assert.equal(x.get('standaloneKpOut').hidden,false);
 assert.match(st.textContent,/подключён/);
});

test('KinoPub: cancelled auth cannot register a token after disconnect',async()=>{
 const x=setup();x.win.abajStandaloneOpenSources();
 x.samples.set('device_code',JSON.stringify({code:'pending',user_code:'WXYZ12',expires_in:600,interval:5}));
 await x.get('standaloneConnect').onclick();
 assert.equal(x.get('standaloneKpCode').hidden,false);
 x.get('standaloneKpOut').onclick();
 assert.equal(x.get('standaloneKpCode').hidden,true);
 assert.equal(x.storage.has('abaj-standalone-kino-token'),false);
 assert.equal(x.scheduled.some(t=>t.active&&t.ms===5000),false);
});

test('KinoPub accepts device code even when provider reports unexpected activation URL',async()=>{
 const x=setup();x.win.abajStandaloneOpenSources();
 x.samples.set('device_code',JSON.stringify({
  code:'device-token-xyz',user_code:'KINO42',
  verification_uri:'https://alternate.example.org/login',expires_in:600,interval:5
 }));
 await x.get('standaloneConnect').onclick();
 assert.equal(x.get('standaloneKpCode').hidden,false);
 assert.equal(x.get('standaloneKpUserCode').textContent,'KINO42');
 assert.match(x.get('standaloneKpStatus').textContent,/Ожидаем подтверждения/);
 assert.ok(x.scheduled.some(t=>t.active&&t.ms===5000));
});

function connected(x){
 x.storage.set('abaj-standalone-kino-token',JSON.stringify({
  access_token:'my-personal-token',refresh_token:'refresh-token',
  expires_at:Date.now()+3600000
 }));
}
test('KinoPub history imports remote watched titles into standalone',async()=>{
 const x=setup();connected(x);
 x.samples.set('/v1/history',JSON.stringify({history:[
  {item:{id:101,title:'Movie watched on KinoPub',poster:'https://img.test/poster.jpg'},last_seen:1720000000},
  {item:{id:102,title:'Series watched on KinoPub'},last_seen:1720000100}
 ]}));
 const response=await x.win.fetch('/api/cinema/library?section=history');
 assert.equal(response.status,200);
 const body=await response.json();
 assert.equal(body.items.length,2);
 assert.equal(body.items[0].title,'Movie watched on KinoPub');
 assert.equal(body.items[0].watched_at,1720000000);
 assert.equal(JSON.parse(x.storage.get('abaj-standalone-cinema-history')).length,2);
});
test('KinoPub folder sync reads remote bookmarks and writes to selected folder',async()=>{
 const x=setup();connected(x);
 x.samples.set('/v1/bookmarks',JSON.stringify({
  bookmarks:[{id:'42',title:'My favourites on KinoPub',count:1}]
 }));
 x.samples.set('/v1/bookmarks/42',JSON.stringify({
  items:[{id:1234,title:'KinoPub favourite film'}]
 }));
 x.samples.set('/v1/bookmarks/get-item-folders',JSON.stringify({folders:[]}));
 x.samples.set('/v1/bookmarks/add',JSON.stringify({status:200}));
 const lib=await (await x.win.fetch('/api/cinema/library?section=bookmarks')).json();
 assert.ok(lib.folders.some(f=>f.id==='kp:42'&&f.title==='My favourites on KinoPub'));
 const selected=await (await x.win.fetch('/api/cinema/library?section=bookmarks&folder=kp%3A42')).json();
 assert.equal(selected.items.length,1);
 assert.equal(selected.items[0].title,'KinoPub favourite film');
 const saved=await x.win.fetch('/api/cinema/bookmark-folders',{
  method:'POST',body:JSON.stringify({item:{id:555,title:'New favourite'},folders:['kp:42'],original:[]})
 });
 assert.equal(saved.status,200);
 assert.equal((await saved.json()).added,true);
 const addReq=x.requests.find(req=>req.path==='/v1/bookmarks/add');
 assert.ok(addReq,'KinoPub remote bookmarks/add must be called');
 assert.equal(addReq.method,'POST');
 assert.match(addReq.body,/folder=42/);
 assert.match(addReq.body,/item=555/);
});
test('KinoPub playback reports real watch position remotely, not a fake watched title',async()=>{
 const x=setup();connected(x);
 x.samples.set('/v1/watching/marktime',JSON.stringify({status:200}));
 const response=await x.win.fetch('/api/cinema/progress',{
  method:'POST',body:JSON.stringify({
   item_id:'432',media_id:'med1',position:123,duration:3600,season:2,episode:3
  })
 });
 assert.equal(response.status,200);
 assert.equal((await response.json()).remote_updated,true);
 const req=x.requests.find(x=>x.path==='/v1/watching/marktime');
 assert.ok(req);
 assert.equal(new URL(req.url).searchParams.get('id'),'432');
 assert.equal(new URL(req.url).searchParams.get('time'),'123');
 assert.equal(new URL(req.url).searchParams.get('season'),'2');
 assert.equal(new URL(req.url).searchParams.get('video'),'3');
 const local=(await (await x.win.fetch('/api/cinema/progress?item_id=432&media_id=med1')).json()).progress;
 assert.equal(local.position,123);
});


test('KinoPub catalog uses ratings, never IMDb numeric identifier as a score',async()=>{
 const x=setup();connected(x);
 x.samples.set('/v1/items',JSON.stringify({items:[{
  id:55,title:'Чистые руки',original_title:'Clean Hands',year:2026,
  imdb:36271247,imdb_rating:6.7,kinopoisk:123456,kp_rating:7.2,
  duration:{minutes:97},genres:[{id:4,title:'Триллер'},{id:8,title:'Драма'}],
  countries:[{id:1,title:'США'}],directors:[{name:'Гай Моше'}],
  actors:[{name:'Актёр 1',id:100}],posters:{medium:'https://poster.example/p.jpg'}
 }]}));
 const result=await (await x.win.fetch('/api/kinopub/catalog?type=movie')).json();
 assert.equal(result.items.length,1);
 const item=result.items[0];
 assert.equal(item.rating,'6.7');assert.equal(item.imdb,'6.7');
 assert.equal(item.imdb_id,'36271247');
 assert.equal(item.kp,'7.2');assert.equal(item.kp_id,'123456');
 assert.equal(item.duration,'97 мин');
 assert.equal(item.genre,'Триллер, Драма');
 assert.equal(item.country,'США');assert.equal(item.director,'Гай Моше');
 assert.equal(item.actors,'Актёр 1');
 assert.equal(item.poster,'https://poster.example/p.jpg');
 assert.ok(!JSON.stringify(item).includes('[object Object]'));
});
test('KinoPub detailed title supplies genre and episode runtime without exposing object text',async()=>{
 const x=setup();connected(x);
 x.samples.set('/v1/items/55',JSON.stringify({item:{
  id:55,title:'The Fix',imdb:'tt09601292',imdb_rating:5.5,
  kinopoisk_rating:6.2,genre:[{title:'Action'}],
  runtime:{seconds:5340},directors:[{name:'Director One'}],
  videos:[{id:1234,number:1,duration:5340,files:[{file:'abc',quality:'1080p'}]}]
 }}));
 const response=await x.win.fetch('/api/kinopub/item?id=55');
 assert.equal(response.status,200);
 const detail=await response.json();
 assert.equal(detail.item.imdb_id,'tt09601292');
 assert.equal(detail.item.rating,'5.5');
 assert.equal(detail.item.genre,'Action');
 assert.equal(detail.item.duration,'89 мин');
 assert.equal(detail.media_rows[0].items[0].duration,5340);
 assert.equal(detail.item.director,'Director One');
 assert.ok(!JSON.stringify(detail.item).includes('[object Object]'));
});

test('KinoPub: film Watch endpoint resolves mobile-friendly HLS stream instead of HTTP 404',async()=>{
 const x=setup();connected(x);
 x.samples.set('/v1/items/55',JSON.stringify({item:{
  id:55,title:'Movie',videos:[{id:100,files:[
   {file:'film-4k',quality:'2160p',codec:'hevc'},
   {file:'film-1080',quality:'1080p',codec:'h264'}
  ]}]
 }}));
 x.samples.set('/v1/items/media-video-link',JSON.stringify({url:{hls:'https://cdn.example.com/film/1080/manifest.m3u8'}}));
 const r=await x.win.fetch('/api/kinopub/play?id=55&compat=1080&format=hls&direct=1');
 assert.equal(r.status,200);
 const body=await r.json();
 assert.equal(body.ok,true);
 assert.equal(body.url,'https://cdn.example.com/film/1080/manifest.m3u8');
 const api=x.requests.find(req=>req.path==='/v1/items/media-video-link');
 assert.ok(api,'Must call KinoPub video link API');
 assert.equal(new URL(api.url).searchParams.get('file'),'film-1080');
 assert.equal(new URL(api.url).searchParams.get('type'),'hls');
});

test('KinoPub: TV 4K playback selects higher resolution stream',async()=>{
 const x=setup();connected(x);
 x.samples.set('/v1/items/55',JSON.stringify({item:{
  id:55,title:'4K movie',videos:[{id:100,files:[
   {file:'film-4k',quality:'2160p',codec:'hevc'},
   {file:'film-1080',quality:'1080p',codec:'h264'}
  ]}]
 }}));
 x.samples.set('/v1/items/media-video-link',JSON.stringify({url:{hls4:'https://cdn.example.com/film/4k/master.m3u8'}}));
 const r=await x.win.fetch('/api/kinopub/play?id=55&format=hls4&direct=1');
 assert.equal(r.status,200);
 assert.equal((await r.json()).url,'https://cdn.example.com/film/4k/master.m3u8');
 const api=x.requests.find(req=>req.path==='/v1/items/media-video-link');
 assert.equal(new URL(api.url).searchParams.get('file'),'film-4k');
 assert.equal(new URL(api.url).searchParams.get('type'),'hls4');
});

test('KinoPub: series selected episode stays selected by media id',async()=>{
 const x=setup();connected(x);
 x.samples.set('/v1/items/33',JSON.stringify({item:{
  id:33,title:'Series',seasons:[{number:2,episodes:[
   {id:101,number:1,files:[{file:'series-episode-1',quality:'1080p'}]},
   {id:102,number:2,files:[{file:'series-episode-2',quality:'1080p'}]}
  ]}]
 }}));
 x.samples.set('/v1/items/media-video-link',JSON.stringify({url:'https://cdn.example.com/series/e2.m3u8'}));
 const r=await x.win.fetch('/api/kinopub/play?id=33&mid=102&format=hls&compat=1080');
 assert.equal(r.status,200);
 assert.equal((await r.json()).ok,true);
 const media=x.requests.find(req=>req.path==='/v1/items/media-video-link');
 assert.equal(new URL(media.url).searchParams.get('file'),'series-episode-2');
});

test('KinoPub film sections route to separate provider categories including 4K and documentary',async()=>{
 const x=setup();connected(x);
 x.samples.set('/v1/items',JSON.stringify({items:[
  {id:23,title:'4K Movie',type:'movie',quality:'4k'},
  {id:24,title:'Documentary',type:'documovie'}
 ]}));
 const four=await x.win.fetch('/api/kinopub/section?section=4k&type=movies&page=2');
 assert.equal(four.status,200);
 const p=x.requests.find(req=>req.path==='/v1/items');
 assert.equal(new URL(p.url).searchParams.get('quality'),'4k');
 const doc=await x.win.fetch('/api/kinopub/section?section=docmovies');
 assert.equal(doc.status,200);
 const d=x.requests.filter(req=>req.path==='/v1/items').at(-1);
 assert.equal(new URL(d.url).searchParams.get('type'),'documovie');
 const bad=await x.win.fetch('/api/kinopub/section?section=series');
 assert.equal(bad.status,200);
 assert.equal(new URL(x.requests.at(-1).url).searchParams.get('type'),'serial');
});

test('KinoPub cartoons and anime filter by the actual genre IDs',async()=>{
 const x=setup();connected(x);
 x.samples.set('/v1/genres',JSON.stringify({items:[
  {id:11,title:'Аниме'}, {id:12,title:'Мультфильмы'}
 ]}));
 x.samples.set('/v1/items',JSON.stringify({items:[{id:1,title:'Мультфильм',genre:'Мультфильмы',type:'movie'}]}));
 await x.win.fetch('/api/kinopub/section?section=cartoons&page=2');
 const first=x.requests.filter(req=>req.path==='/v1/items').at(-1);
 assert.equal(new URL(first.url).searchParams.get('genre'),'12');
 await x.win.fetch('/api/kinopub/section?section=anime&page=2');
 const second=x.requests.filter(req=>req.path==='/v1/items').at(-1);
 assert.equal(new URL(second.url).searchParams.get('genre'),'11');
});

test('KinoPub collections open via provider collections/view endpoint',async()=>{
 const x=setup();connected(x);
 x.samples.set('/v1/collections/view',JSON.stringify({items:[{id:321,title:'Included in collection',type:'movie'}]}));
 const result=await x.win.fetch('/api/kinopub/collection?id=45&page=1');
 assert.equal(result.status,200);
 assert.equal((await result.json()).items[0].title,'Included in collection');
 assert.ok(x.requests.some(req=>req.path==='/v1/collections/view'));
});


test('KinoPub film detail selects a real landscape poster from posters.wide and keeps small portrait separately',async()=>{
 const x=setup();connected(x);
 x.samples.set('/v1/items/903',JSON.stringify({item:{
  id:903,title:'KinoPub film 903',posters:{
   big:'https://images.test/portrait-903.jpg',
   small:'https://images.test/portrait-small.jpg',
   wide:'https://images.test/cinematic-wide-903.jpg'
  },
  screenshots:['https://images.test/still-903.jpg'],
  duration:105
 }}));
 const reply=await x.win.fetch('/api/kinopub/item?id=903');
 assert.equal(reply.status,200);
 const data=await reply.json();
 assert.equal(data.item.poster,'https://images.test/portrait-903.jpg');
 assert.equal(data.item.backdrop,'https://images.test/cinematic-wide-903.jpg');
 assert.equal(data.item.backdrops[0],data.item.backdrop);
 assert.ok(data.item.backdrops.includes('https://images.test/still-903.jpg'));
 assert.ok(!data.item.backdrops.includes(data.item.poster));
});
test('KinoPub detail with only a portrait has no fake widescreen backdrop',async()=>{
 const x=setup();connected(x);
 x.samples.set('/v1/items/904',JSON.stringify({item:{
  id:904,title:'No wide art',posters:{big:'https://images.test/only-portrait.jpg'}
 }}));
 const reply=await x.win.fetch('/api/kinopub/item?id=904');
 const data=await reply.json();
 assert.equal(data.item.poster,'https://images.test/only-portrait.jpg');
 assert.equal(data.item.backdrop,'');
 assert.equal(data.item.backdrops.length,0);
});
test('Standalone mobile movie detail hides duplicate centered poster, keeping the main image area',()=>{
 const html=fs.readFileSync('app/src/main/assets/standalone/index.html','utf8');
 assert.ok(html.includes('body:not(.nativeTv) .cinemaDetailHero.posterFallback .cinemaDetailHeroPoster{display:none!important}'));
 assert.ok(html.includes("heroPoster.style.display=(!bg&&poster&&nativeTv)?'block':'none';"));
});

function snapshotDatabase(snapshot){
 return {open(){
  const request={};
  queueMicrotask(()=>{
   request.result={close(){},transaction(){return {objectStore(){return {put(){},get(){
    const read={};queueMicrotask(()=>{read.result=snapshot;read.onsuccess()});return read;
   }}}}}};
   request.onsuccess();
  });
  return request;
 }};
}
test('built-in catalog supplies renderable channel objects, not Map entries',async()=>{
 const x=setup();
 const rows=await x.win.abajStandaloneGetIptvChannels();
 assert.ok(rows.length>10);
 for(const row of rows){
  assert.equal(row.status,'ONLINE');
  assert.match(row.url,/^https?:\/\//);
  assert.ok(row.name);
  assert.equal(row.personal,false);
  assert.equal(row.playlist_id,'free');
 }
 assert.ok(rows.some(row=>row.country==='AM'&&row.quality==='FHD'));
});
test('standalone built-in IPTV includes only Armenia and Russia, even after a legacy cache import',async()=>{
 const saved=[
  {name:'Russian legacy',url:'https://iptv.test/russia.m3u8',status:'ONLINE',country:'RU'},
  {name:'Armenian legacy',url:'https://iptv.test/armenia.m3u8',status:'ONLINE',country:'AM'},
  {name:'Georgian legacy',url:'https://iptv.test/georgia.m3u8',status:'ONLINE',country:'GE'},
  {name:'Unclassified legacy',url:'https://iptv.test/unknown.m3u8',status:'ONLINE',country:''}
 ];
 const x=setup({indexedDB:snapshotDatabase({items:saved,at:Date.now()})});
 const rows=await x.win.abajStandaloneGetIptvChannels();
 assert.ok(rows.every(row=>row.country==='AM'||row.country==='RU'));
 assert.ok(rows.some(row=>row.name==='Russian legacy'));
 assert.ok(rows.some(row=>row.name==='Armenian legacy'));
 assert.ok(!rows.some(row=>row.name==='Georgian legacy'||row.name==='Unclassified legacy'));
 assert.ok(rows.some(row=>row.playlist_id==='free'));
});
test('old 17103-entry IndexedDB snapshot is repaired without dropping its channels',async()=>{
 const items=Array.from({length:17103},(_,i)=>({0:'am|channel '+i,1:{
  name:'Channel '+i,url:'https://iptv.test/'+i+'.m3u8',status:'ONLINE',
  country:'AM',quality:'FHD',height:1080
 },id:'free:'+i,provider:'IPTV',playlist_id:'free',personal:false}));
 const x=setup({indexedDB:snapshotDatabase({items,at:Date.now()})});
 const rows=await x.win.abajStandaloneGetIptvChannels();
 assert.equal(rows.filter(row=>row.name?.startsWith('Channel ')).length,17103);
 assert.ok(rows.every(row=>row.status==='ONLINE'&&row.url&&row.name));
 assert.equal(new Set(rows.map(row=>row.id)).size,rows.length);
 assert.equal(x.win.abajStandaloneIptvState().count,rows.length);
});

test('partial refresh retains last successful channels when other feeds fail',async()=>{
 const stored={name:'Last known channel',url:'https://iptv.test/last.m3u8',status:'ONLINE',country:'AM'};
 const x=setup({indexedDB:snapshotDatabase({items:[stored],at:Date.now()})});
 await x.win.abajStandaloneGetIptvChannels();
 for(const country of ['am','ru','ge','ua','by','kz','uz','md']){
  x.samples.set('/iptv/countries/'+country+'.m3u','#EXTM3U\n#EXTINF:-1,New '+country+'\nhttps://iptv.test/'+country+'.m3u8');
 }
 await x.win.fetch('/api/iptv/refresh');
 for(let i=0;i<100&&x.win.abajStandaloneIptvState().updating;i++)await new Promise(setImmediate);
 assert.equal(x.win.abajStandaloneIptvState().updating,false);
 const rows=await x.win.abajStandaloneGetIptvChannels();
 assert.ok(rows.some(row=>row.name==='Last known channel'));
 assert.ok(rows.some(row=>row.name==='New am'));
});
