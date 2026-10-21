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
 const samples=new Map();let menu=[],loads=0;
 const win={
  fetch:async()=>new Response('{}'),
  renderNamedPlaylistChips:(lists)=>{menu=lists.map(x=>x.name)},
  load:async()=>{loads++},
  StandaloneNetwork:{request(id,url){
   const raw=samples.get(url);
   win.__abajStandaloneResponse(id,raw===undefined?404:200,raw??'Not found');
  }}
 };
 vm.runInNewContext(script,{window:win,document,localStorage,Response,URL,URLSearchParams,console,setTimeout,clearTimeout,Date,Math,Promise,Error},{filename:'compat.js'});
 handlers.DOMContentLoaded();
 return{get:id=>elements.get(id),storage,win,samples,menu:()=>menu,loads:()=>loads};
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
