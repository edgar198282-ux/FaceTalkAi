'use strict';
const {test}=require('node:test');
const assert=require('node:assert/strict');
const fs=require('node:fs');
const vm=require('node:vm');
const script=fs.readFileSync('app/src/main/assets/standalone/compat.js','utf8');
function setup(){
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
 const samples=new Map(),scheduled=[];let menu=[],loads=0;
 const fakeSetTimeout=(fn,ms)=>{const job={fn,ms,active:true};scheduled.push(job);return job};
 const fakeClearTimeout=job=>{if(job)job.active=false};
 const win={
  fetch:async()=>new Response('{}'),
  renderNamedPlaylistChips:(lists)=>{menu=lists.map(x=>x.name)},
  load:async()=>{loads++},
  StandaloneNetwork:{request(id,url){
   const grant=new URL(url).searchParams.get('grant_type');
   const raw=samples.has(url)?samples.get(url):samples.get(grant);
   win.__abajStandaloneResponse(id,raw===undefined?404:200,raw??'Not found');
  }}
 };
 vm.runInNewContext(script,{window:win,document,localStorage,Response,URL,URLSearchParams,console,setTimeout:fakeSetTimeout,clearTimeout:fakeClearTimeout,Date,Math,Promise,Error},{filename:'compat.js'});
 handlers.DOMContentLoaded();
 return{get:id=>elements.get(id),storage,win,samples,scheduled,menu:()=>menu,loads:()=>loads};
}
function add(x,name,url){
 x.get('standaloneListName').value=name;
 x.get('standaloneListUrl').value=url;
 x.get('standaloneAdd').onclick();
}
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
