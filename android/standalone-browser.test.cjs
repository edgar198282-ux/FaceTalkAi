'use strict';
const assert=require('node:assert/strict');
const fs=require('node:fs');
const path=require('node:path');
const {chromium}=require(process.env.PLAYWRIGHT_MODULE||'playwright');
(async()=>{
 const browser=await chromium.launch({headless:true,...(process.env.CHROME_PATH?{executablePath:process.env.CHROME_PATH}:{})});
 try{
  const page=await browser.newPage();
  const errors=[];
  page.on('pageerror',error=>errors.push(error.message));
  await page.route('**/*',route=>{
   const url=new URL(route.request().url());
   if(url.hostname==='abaj.test'){
    const file=path.join(__dirname,'app/src/main/assets/standalone',url.pathname==='/'?'index.html':url.pathname);
    if(fs.existsSync(file)&&fs.statSync(file).isFile())return route.fulfill({path:file});
   }
   return route.fulfill({status:404,body:''});
  });
  await page.goto('https://abaj.test/');
  await page.evaluate(async()=>{
   const items=Array.from({length:17103},(_,i)=>({0:'am|test '+i,1:{
    name:'Test '+i,url:'https://stream.test/'+i+'.m3u8',status:'ONLINE',country:'AM',
    quality:i%2?'HD':'FHD',height:i%2?720:1080,group:i%2?'News':'General'
   },provider:'IPTV',playlist_id:'free',personal:false}));
   await new Promise((resolve,reject)=>{
    const open=indexedDB.open('abaj_standalone_iptv_v1',1);
    open.onsuccess=()=>{
     const db=open.result,tx=db.transaction('builtins','readwrite');
     tx.objectStore('builtins').put({items,at:Date.now()},'iptv');
     tx.oncomplete=()=>{db.close();resolve()};tx.onerror=reject;
    };
    open.onerror=reject;
   });
  });
  await page.addInitScript(()=>{
   window.StandaloneNetwork={request(id){setTimeout(()=>window.__abajStandaloneResponse(id,404,''),0)}};
   window.AbajNative={lazyMediaInfo:()=>JSON.stringify({installed:true,version:'3.470',embeddedPlayback:false})};
  });
  await page.reload();
  await page.waitForFunction(()=>channels.length>=17103);
  const all=await page.evaluate(()=>{
   setSourceFilter(null,'free');setModeFilter(null,'all');
   return {count:channels.length,filtered:filteredNow.length,cards:document.querySelectorAll('#list .channel').length};
  });
  assert.ok(all.count>=17103);assert.equal(all.count,all.filtered);assert.equal(all.cards,240);
  await page.evaluate(()=>document.getElementById('standaloneMoreChannels').click());
  assert.equal(await page.locator('#list .channel').count(),480);
  for(const filter of ['HD','FHD','AM']){
   const state=await page.evaluate(filter=>{
    setModeFilter(null,filter);
    return {count:filteredNow.length,valid:filteredNow.every(x=>filter==='AM'?x.country==='AM':channelQuality(x)===filter)};
   },filter);
   assert.ok(state.count>0);assert.equal(state.valid,true);
  }
  await page.evaluate(()=>{setModeFilter(null,'all');setCategory('News')});
  assert.ok(await page.evaluate(()=>filteredNow.length>0&&filteredNow.every(x=>channelCategory(x)==='News')));
  const empty=await page.evaluate(()=>{
   document.getElementById('search').value='missing-query-xyz';render();
   return {count:filteredNow.length,query:document.getElementById('search').value,category:activeCategory};
  });
  assert.equal(empty.count,0);assert.equal(empty.query,'missing-query-xyz');assert.equal(empty.category,'News');
  const lazy=await page.evaluate(async()=>{
   cinemaSource='lazy';
   const item={id:'test-film',title:'Test film',intent:'catalog-only',provider:'HDREZKA'};
   renderCinemaDetail(item);await showCinemaSourcePicker(item);
   return {disabled:document.getElementById('cinemaDetailWatch').disabled,
    text:document.getElementById('cinemaSourceList').textContent,
    buttons:document.querySelectorAll('#cinemaSourceList button').length,
    directAvailable:!standaloneLazyPlaybackUnavailable({url:'https://stream.test/movie.m3u8'})};
  });
  assert.equal(lazy.disabled,true);assert.equal(lazy.buttons,0);assert.equal(lazy.directAvailable,true);
  assert.match(lazy.text,/интерфейс воспроизведения/);
  assert.deepEqual(errors,[]);
  console.log(JSON.stringify({catalog:all,filters:['ALL','HD','FHD','AM','News'],emptySearchPreserved:true,lazyCatalogOnlyGuard:true}));
 }finally{await browser.close()}
})().catch(error=>{console.error(error);process.exitCode=1});
