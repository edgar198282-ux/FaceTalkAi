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
  await page.waitForFunction(()=>{
    const tile=document.querySelector('#abajLauncher [data-target="cinema"]');
    const canvas=tile?.querySelector('.abajCinemaScene');
    return !!(tile?.classList.contains('abajCinemaSceneReady')&&canvas&&!canvas.hidden&&canvas.width>0);
  },{timeout:15000});
  const cinemaBefore=await page.evaluate(()=>{
    const tile=document.querySelector('#abajLauncher [data-target="cinema"]');
    const canvas=tile.querySelector('.abajCinemaScene');
    return {image:canvas.toDataURL(),fakeEffects:tile.querySelectorAll('.abajPopcornSpark').length};
  });
  await page.waitForTimeout(850);
  const cinemaAfter=await page.evaluate(()=>{
    const tile=document.querySelector('#abajLauncher [data-target="cinema"]');
    return tile.querySelector('.abajCinemaScene').toDataURL();
  });
  assert.equal(cinemaBefore.fakeEffects,0);
  assert.notEqual(cinemaBefore.image,cinemaAfter,'Original cinema scene must animate actual film, sun and popcorn pixels');

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
  const epg=await page.evaluate(()=>{
    const now=Math.floor(Date.now()/1000);
    window.__abajStandaloneEpgUpdate({
      country:'AM',updated:now,channels:[{
        id:'test0.am',names:['Test 0'],
        now:{start:now-900,stop:now+900,title:'Тестовая передача'},
        next:{start:now+900,stop:now+4500,title:'Следующая передача'}
      }]
    });
    const item=channels.find(x=>x.name==='Test 0');
    const badge=document.getElementById('standaloneCatalogMeta');
    return {count:badge?.textContent||'',now:item?.epg_now?.title,
      next:item?.epg_next?.title,visible:getComputedStyle(badge).display!=='none'};
  });
  assert.match(epg.count,/IPTV:/);
  assert.equal(epg.visible,true);
  assert.equal(epg.now,'Тестовая передача');
  assert.equal(epg.next,'Следующая передача');
  const ui=await page.evaluate(()=>{
    document.getElementById('search').value='';
    setCategory('');setModeFilter(null,'all');render();
    const cinema=document.querySelector('#abajLauncher .abajLaunchTile[data-target="cinema"]');
    const scene=cinema?.querySelector('.abajCinemaScene');
    const noGuide=Array.from(document.querySelectorAll('#list .channel'))
      .filter(node=>node.dataset.id&&node.dataset.id!==channels.find(x=>x.name==='Test 0')?.id);
    return {
      cinemaReady:!!cinema,
      sceneReady:!!scene&&!!cinema?.classList.contains('abajCinemaSceneReady'),
      sceneVisible:!!scene&&!scene.hidden,
      noEmptyEpgText:noGuide.every(node=>!node.textContent.includes('Программа недоступна')),
      noEmptyEpgRows:noGuide.every(node=>!node.querySelector('.abajEpgSmall'))
    };
  });
  assert.equal(ui.cinemaReady,true);
  assert.equal(ui.sceneReady,true);
  assert.equal(ui.sceneVisible,true);
  assert.equal(ui.noEmptyEpgText,true);
  assert.equal(ui.noEmptyEpgRows,true);
  const settingsBefore=await page.evaluate(()=>{
    window.abajStandaloneOpenSources();
    const config=document.getElementById('standaloneConfig');
    const iptv=config.querySelector('.standaloneIptvSection');
    const kp=config.querySelector('.standaloneKpSection');
    const refresh=config.querySelector('#standaloneRefresh');
    const epg=config.querySelector('#standaloneBuiltinEpgCount');
    const info=config.querySelector('#standaloneBuiltinIptvStatus');
    return {
      epg:epg.textContent,
      channelCount:info.textContent,
      refreshInsideIptv:iptv.contains(refresh),
      refreshOutsideKp:!kp.contains(refresh),
      sectionColorsDistinct:getComputedStyle(iptv).backgroundColor!==getComputedStyle(kp).backgroundColor,
      epgUnderCount:!!(info.compareDocumentPosition(epg)&Node.DOCUMENT_POSITION_FOLLOWING)
    };
  });
  assert.equal(settingsBefore.epg,'EPG: 1');
  assert.match(settingsBefore.channelCount,/каналов/);
  assert.equal(settingsBefore.refreshInsideIptv,true);
  assert.equal(settingsBefore.refreshOutsideKp,true);
  assert.equal(settingsBefore.sectionColorsDistinct,true);
  assert.equal(settingsBefore.epgUnderCount,true);
  const settingsAfter=await page.evaluate(()=>{
    const now=Math.floor(Date.now()/1000);
    window.__abajStandaloneEpgUpdate({country:'AM',updated:now,channels:[
      {id:'test0.am',names:['Test 0'],now:{start:now-30,stop:now+300,title:'News 0'}},
      {id:'test1.am',names:['Test 1'],now:{start:now-30,stop:now+300,title:'News 1'}}
    ]});
    return document.getElementById('standaloneBuiltinEpgCount').textContent;
  });
  assert.equal(settingsAfter,'EPG: 2');
  const remoteNavigation=await page.evaluate(()=>{
    const config=document.getElementById('standaloneConfig');
    const focusOrder=[document.activeElement.id];
    for(let i=0;i<5;i++){
      window.abajStandaloneRemoteKey('ArrowDown');
      focusOrder.push(document.activeElement.id);
    }
    const reachedKinoPub=config.querySelector('.standaloneKpSection').contains(document.activeElement);
    window.abajStandaloneRemoteKey('ArrowUp');
    focusOrder.push(document.activeElement.id);
    window.abajStandaloneRemoteKey('Back');
    return {focusOrder,reachedKinoPub,closed:config.hidden};
  });
  assert.deepEqual(remoteNavigation.focusOrder.slice(0,5),[
    'standaloneClose','standaloneRefresh','standaloneListName','standaloneListUrl','standaloneAdd'
  ]);
  assert.equal(remoteNavigation.reachedKinoPub,true);
  assert.equal(remoteNavigation.focusOrder[6],'standaloneAdd');
  assert.equal(remoteNavigation.closed,true);


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
