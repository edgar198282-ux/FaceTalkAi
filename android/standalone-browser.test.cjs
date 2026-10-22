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
   window.AbajNative={
    lazyMediaInfo:()=>JSON.stringify({installed:true,version:'3.470',embeddedPlayback:false}),
    openLazyMediaIntent:intent=>{window.__lazyMediaLaunchedIntent=intent;return true;},
    openLazyMedia:()=>{window.__lazyMediaLaunchedIntent='app';return true;}
   };
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
   cinemaSource='lazy';cinemaPlaybackAllowed=true;
   const item={id:'test-film',title:'Test film',intent:'catalog-only',provider:'HDREZKA'};
   renderCinemaDetail(item);
   const disabled=document.getElementById('cinemaDetailWatch').disabled;
   const label=document.getElementById('cinemaDetailWatch').textContent;
   await watchCinemaDetail();
   const sourceLabels=[...document.querySelectorAll('#cinemaSourceList .cinemaSourceBtn')].map(b=>b.textContent);
   const opened=!!document.getElementById('cinemaSourceModal')?.classList.contains('open');
   return {disabled,label,sourceLabels,opened,externalLaunch:window.__lazyMediaLaunchedIntent||''};
  });
  assert.equal(lazy.disabled,false);
  assert.match(lazy.label,/ВЫБРАТЬ ВИДЕО/);
  assert.equal(lazy.opened,true);
  assert.ok(lazy.sourceLabels.some(x=>x.includes('HDREZKA')));
  assert.equal(lazy.externalLaunch,'');
  const manualSelection=await page.evaluate(()=>{
   const group={name:'HDREZKA'};
   const options=[
    {name:'Озвучка A Сезон 1 Серия 1 720p',url:'https://stream.test/a_s1e1_720.m3u8',quality:'720p',format:'HLS'},
    {name:'Озвучка A Сезон 1 Серия 1 1080p',url:'https://stream.test/a_s1e1_1080.m3u8',quality:'1080p',format:'HLS'},
    {name:'Озвучка A Сезон 1 Серия 2 1080p',url:'https://stream.test/a_s1e2_1080.m3u8',quality:'1080p',format:'HLS'},
    {name:'Озвучка B Сезон 1 Серия 1 720p',url:'https://stream.test/b_s1e1_720.m3u8',quality:'720p',format:'HLS'}
   ];
   const infos=options.map(cinemaResolvedRowInfo);
   const stages=[],getStage=()=>document.getElementById('cinemaSourceTitle')?.textContent||'';
   const click=term=>{const b=[...document.querySelectorAll('#cinemaSourceList .cinemaSourceBtn')].find(el=>el.textContent.includes(term));if(!b)throw Error('Missing selection '+term);b.click()};
   cinemaRenderResolvedRows(group,infos);
   stages.push(getStage());
   click('Озвучка A');
   stages.push(getStage());
   click('Сезон 1');
   stages.push(getStage());
   click('Серия 1');
   stages.push(getStage());
   const qualityOptions=[...document.querySelectorAll('#cinemaSourceList .cinemaSourceBtn')].map(e=>e.textContent);
   window.__abajOpenExternalMedia=(...args)=>{window.__testPlaybackArgs=args};
   click('1080p');
   return {stages,qualityOptions,chosen:window.__testPlaybackArgs?.[0]||''};
  });
  assert.match(manualSelection.stages[0],/ОЗВУЧКА/);
  assert.match(manualSelection.stages[1],/СЕЗОН/);
  assert.match(manualSelection.stages[2],/СЕРИИ/);
  assert.match(manualSelection.stages[3],/КАЧЕСТВО/);
  assert.ok(manualSelection.qualityOptions.some(x=>x.includes('1080p')));
  assert.match(manualSelection.chosen,/a_s1e1_1080.m3u8/);
  assert.deepEqual(errors,[]);
  console.log(JSON.stringify({catalog:all,filters:['ALL','HD','FHD','AM','News'],emptySearchPreserved:true,lazySourceSelection:true,lazyOrderedStages:true}));
 }finally{await browser.close()}
})().catch(error=>{console.error(error);process.exitCode=1});
