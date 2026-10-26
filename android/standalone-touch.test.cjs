'use strict';
const assert=require('node:assert/strict');
const fs=require('node:fs');
const path=require('node:path');
const {chromium}=require(process.env.PLAYWRIGHT_MODULE||'playwright');
(async()=>{
 const browser=await chromium.launch({headless:true});
 try{
  const context=await browser.newContext({viewport:{width:1280,height:720},hasTouch:true,isMobile:true,deviceScaleFactor:1});
  const page=await context.newPage();
  const errors=[];
  page.on('pageerror',e=>errors.push(e.message));
  await page.route('**/*',route=>{
   const url=new URL(route.request().url());
   if(url.hostname==='abaj.test'){
    const file=path.join(__dirname,'app/src/main/assets/standalone',url.pathname==='/'?'index.html':url.pathname);
    if(fs.existsSync(file)&&fs.statSync(file).isFile())return route.fulfill({path:file});
   }
   return route.fulfill({status:404,body:''});
  });
  await page.addInitScript(()=>{window.StandaloneNetwork={request(id){window.__abajStandaloneResponse?.(id,503,'offline')}}});
  await page.goto('https://abaj.test/?source=android');
  await page.locator('#abajLauncher [data-target="iptv"]').waitFor({state:'visible',timeout:20000});
  await page.locator('#abajLauncher [data-target="iptv"]').tap();
  await page.waitForFunction(()=>document.getElementById('abajLauncher')?.hidden,{timeout:15000});
  const state=await page.evaluate(()=>({
   homeHidden:document.getElementById('abajLauncher').hidden,
   appVisible:getComputedStyle(document.getElementById('app')).visibility,
   viewport:document.documentElement.clientWidth
  }));
  assert.equal(state.homeHidden,true,'Touching IPTV tile must open IPTV');
  assert.equal(state.appVisible,'visible','Main interface must remain visible');
  assert.ok(state.viewport>0);
  assert.deepEqual(errors.filter(e=>/SyntaxError|is not a function|is not defined/.test(e)),[],'No fatal JS bootstrap errors');
  console.log('Standalone touch navigation passed');
 }finally{await browser.close()}
})().catch(e=>{console.error(e);process.exitCode=1});
