// Run: node tests/test_iptv_ad_watch.cjs
const fs=require('node:fs');
const vm=require('node:vm');
const assert=require('node:assert/strict');
const html=fs.readFileSync(require('node:path').join(__dirname,'../web/index.html'),'utf8');
const context=vm.createContext({console,setTimeout,clearTimeout,clearInterval,AbortController,Date});
const bootstrap=`
var window=globalThis;
var nativeTv=true,nativeMedia3Active=true,streamAttemptToken=1;
var current={id:'fresh'},freeAdRequestBusy=false,freeAdActive=false;
var freeAdShieldChannel='',freeAdShieldStartedAt=0,freeAdShieldVerifiedNegative=0,freeAdShieldSawPositive=false;
var freeAdTimer=null,freeViewingTimer=null,qrAdChannel='',qrAdLastSeenAt=0;
var AbajNative={adFrameSupported:()=>true,captureTvAdFrame:()=>{}};
var selectedFreeStreamUrl=()=> 'http://stream.mcquack.net/429/index.m3u8';
var isProviderAdStreamUrl=url=>url.includes('mcquack');
var notifyFreeViewing=()=>{},stopBurnedAdObserver=()=>{};
var setFreeAdOverlay=active=>{freeAdActive=active};
`;
vm.runInContext(bootstrap+html.slice(html.indexOf('let freeAdWatchGeneration='),html.indexOf("let freeAdShieldChannel='';"))
    +html.slice(html.indexOf('function stopFreeAdWatch(){'),html.indexOf('async function reportBurnedAdObserverState')),context);
vm.runInContext("captureFreeAdFrame=async()=> 'test-frame'; var reply={},httpOk=true,requests=[]; fetch=async(url,opts)=>{requests.push(url);return {ok:httpOk,json:async()=>reply}}",context);
const run=code=>vm.runInContext(code,context);
(async()=>{
  run("reply={ok:true,active:true,checked_at:10,estimated_duration:30}");
  await run('checkFreeAdState()');
  assert.equal(run('freeAdActive'),true);
  assert.equal(run('requests[0]'),'/api/iptv/ad-frame');
  run("httpOk=false;reply={ok:true,active:false,checked_at:11}");
  await run('checkFreeAdState()');
  assert.equal(run('freeAdShieldVerifiedNegative'),0);
  assert.equal(run('freeAdActive'),true);
  run("httpOk=true;reply={ok:true,active:false,checked_at:Date.now()/1000+1}");
  await run('checkFreeAdState()');
  await run('checkFreeAdState()'); // Repeated result cannot be counted twice.
  assert.equal(run('freeAdActive'),true);
  assert.equal(run('freeAdShieldVerifiedNegative'),1);
  run('reply.checked_at+=1');
  await run('checkFreeAdState()');
  assert.equal(run('freeAdActive'),false);
  // A delayed positive response for a previous playback must not hide a new channel.
  run("var finish; fetch=()=>new Promise(resolve=>{finish=resolve})");
  const pending=run('checkFreeAdState()');
  await new Promise(resolve=>setImmediate(resolve));
  run("stopFreeAdWatch();current={id:'other'};finish({ok:true,json:async()=>({ok:true,active:true,checked_at:9999999999})})");
  await pending;
  assert.equal(run('freeAdActive'),false);
  // A WebView capture failure does not disable capture if Media3 wins the race later.
  run('freeAdFrameDisabled=true;nativeMedia3Active=false');
  assert.equal(run('usesPlayerAdFrames(current)'),false);
  run('nativeMedia3Active=true');
  assert.equal(run('usesPlayerAdFrames(current)'),true);
  // Old APKs, personal playlists and cinema keep their existing paths.
  run('AbajNative.adFrameSupported=undefined');
  assert.equal(run('usesPlayerAdFrames(current)'),false);
  run('AbajNative.adFrameSupported=()=>true');
  assert.equal(run("usesPlayerAdFrames({id:'cinema:one'})"),false);
  assert.equal(run("usesPlayerAdFrames({id:'personal',personal:true})"),false);
  console.log('Player ad watch: fresh negatives, errors, stale channel replies, native race and legacy compatibility passed');
})().catch(error=>{console.error(error);process.exitCode=1});
