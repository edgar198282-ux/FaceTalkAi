/* ABAJ TV Premium Dark launcher — isolated UI layer */
(()=>{'use strict';
const css=`
#abajLauncher{position:fixed;inset:0;z-index:9000;box-sizing:border-box;overflow-y:auto;display:flex;flex-direction:column;padding:18px 28px 28px;color:#f6fbff;background:#020b18 url('/static/launcher-header-20261014.webp') center top / 100% auto no-repeat;font-family:Arial,sans-serif;overscroll-behavior:contain;scrollbar-width:none}
#abajLauncher[hidden],#abajLaunchHome[hidden]{display:none!important}
#abajLauncher::-webkit-scrollbar{display:none}
#abajLauncher *{box-sizing:border-box}
.abajLaunchTop{display:flex;align-items:flex-end;justify-content:center;flex-shrink:0;min-height:112px}
.abajLaunchBrand{font-size:clamp(46px,6vw,76px);font-weight:900;line-height:1.12;letter-spacing:1px;white-space:nowrap;color:#fff;text-shadow:0 3px 24px #00112780}
.abajLaunchBrand b{color:#08bbef}
.abajLaunchBrand{position:relative;isolation:isolate}
.abajBrandSpark{position:absolute;width:5px;height:5px;border-radius:50%;background:#fff;box-shadow:0 0 5px 2px #fff,0 0 12px 4px #63dfff,0 0 22px 7px #0af;pointer-events:none;opacity:0;animation:abajSparkBlink var(--spark-speed,2.5s) ease-in-out infinite;animation-delay:var(--spark-delay,0s)}
@keyframes abajSparkBlink{0%,12%,36%,100%{opacity:0;transform:scale(.3)}19%,25%{opacity:1;transform:scale(1.2)}29%{opacity:.45;transform:scale(.7)}}
@media(prefers-reduced-motion:reduce){.abajBrandSpark{animation:none;opacity:.65}}

.abajLaunchTitle{flex-shrink:0;text-align:center;font-size:clamp(11px,1.45vw,17px);line-height:1.5;font-weight:500;letter-spacing:4px;color:#b9e8ff;margin:12px 0 24px}
#abajLauncher[data-launch-lang="hy"] .abajLaunchTitle{max-width:100%;width:100%;padding:0 6px;white-space:normal;overflow-wrap:normal;text-align:center;letter-spacing:1px;font-size:clamp(10px,2.5vw,15px);line-height:1.35}
.abajLaunchTiles{display:grid;grid-template-columns:repeat(3,minmax(0,1fr));gap:20px;flex:1;min-height:0}
.abajLaunchTile{position:relative;isolation:isolate;overflow:hidden;min-width:0;min-height:250px;display:flex;align-items:flex-end;text-align:left;padding:24px;border-radius:24px;border:1.5px solid #55b8ed;background-color:#031020;background-image:linear-gradient(0deg,#010b19b3,transparent 42%),var(--tile-bg);background-size:cover;background-position:center;color:#fff;box-shadow:inset 0 0 0 1px #9bdbff26,0 6px 22px #0005;cursor:pointer;transition:border-color .18s,box-shadow .18s,transform .18s;-webkit-tap-highlight-color:transparent}
#abajLauncher .abajLaunchTile:after{inset:auto;animation:none;-webkit-mask:none;mask:none;z-index:0;content:'';position:absolute;right:20px;bottom:26px;width:38px;height:38px;border:1.5px solid #4ab9f0;border-radius:50%;background:radial-gradient(circle at 50% 100%,#0b355b99,#020d1ba6);box-shadow:inset 0 0 12px #1a82ba33,0 0 14px #0879b52b;pointer-events:none}
#abajLauncher .abajLaunchTile:before{content:'';position:absolute;z-index:1;right:35px;bottom:40px;width:10px;height:10px;border-top:2.5px solid #f4fbff;border-right:2.5px solid #f4fbff;transform:rotate(45deg);pointer-events:none}
.abajLaunchTile:hover{border-color:#b5eaff;box-shadow:0 0 18px #16a9ef42}
#abajLauncher .abajLaunchTile:focus-visible{outline:2px solid #b5efff!important;outline-offset:3px;border-color:#d5f5ff;box-shadow:0 0 20px #12bdff80!important}
.abajLaunchTile:active{transform:scale(.992)}
/* Lightweight animated scene accents: only composited transforms/opacity. */
.abajLaunchTile .abajSceneMotion{position:absolute;inset:0;z-index:1;overflow:hidden;pointer-events:none;border-radius:inherit}
/* Subtle camera movement of the original artwork, without duplicate figures. */
#abajLauncher .abajLaunchTile[data-target="cinema"]{animation:abajCinemaPan 22s ease-in-out infinite alternate}
#abajLauncher .abajLaunchTile[data-target="iptv"]{animation:abajIptvPan 26s ease-in-out infinite alternate}
@keyframes abajCinemaPan{from{background-position:center,49% 50%}to{background-position:center,53% 48%}}
@keyframes abajIptvPan{from{background-position:center,49% 50%}to{background-position:center,52% 51%}}
@media(prefers-reduced-motion:reduce){#abajLauncher .abajLaunchTile[data-target="cinema"],#abajLauncher .abajLaunchTile[data-target="iptv"]{animation:none!important}}
#abajLauncher[hidden] .abajLaunchTile{animation-play-state:paused!important}

.abajSceneMotion i{position:absolute;display:block;pointer-events:none}
.abajLaunchTile[data-target="cinema"] .abajSceneSun{left:35%;top:19%;width:26%;aspect-ratio:1;border-radius:50%;background:radial-gradient(circle,#fff5b34d 0%,#ffbf4440 15%,#ffb12a16 39%,transparent 69%);mix-blend-mode:screen;animation:abajSunDrift 32s ease-in-out infinite}
.abajLaunchTile[data-target="iptv"] .abajSceneWater{left:47%;top:37%;width:18%;height:17%;border-radius:50%;background:radial-gradient(ellipse,#64d9ff25,transparent 72%);mix-blend-mode:screen;animation:abajWaterSwim 9s ease-in-out infinite alternate}
/* Subtle blue TV backlight, confined to the right-side TV artwork. */
.abajLaunchTile[data-target="iptv"] .abajTvBacklight{position:absolute;z-index:2;left:45%;top:1%;width:53%;height:70%;pointer-events:none;background:radial-gradient(ellipse 70% 56% at 64% 42%,rgba(14,150,255,.35) 0%,rgba(0,100,225,.17) 49%,transparent 80%);mix-blend-mode:screen;opacity:.35;animation:abajTvBacklightBreathe 4s ease-in-out infinite alternate}
@keyframes abajTvBacklightBreathe{from{opacity:.2}to{opacity:.7}}
#abajLauncher[hidden] .abajTvBacklight{animation-play-state:paused}
@media(prefers-reduced-motion:reduce){.abajLaunchTile[data-target="iptv"] .abajTvBacklight{animation:none;opacity:.28}}
/* Gentle screen-only light movement. No video/canvas, opaque strip, or duplicate football. */
.abajLaunchTile[data-target="iptv"] .abajTvScreenMotion{position:absolute;left:62.8%;top:11%;width:6.8%;height:27%;z-index:2;overflow:hidden;pointer-events:none;opacity:.65;clip-path:inset(3% round 2px);mix-blend-mode:screen}
.abajLaunchTile[data-target="iptv"] .abajTvScreenMotion:after{content:'';position:absolute;inset:0;background:radial-gradient(ellipse at 50% 40%,rgba(115,207,255,.19),transparent 72%);animation:abajTvLiveBrightness 3.6s ease-in-out infinite alternate}
@keyframes abajTvLiveBrightness{from{opacity:.12}to{opacity:.65}}
.abajLaunchTile[data-target="iptv"] .abajTvScreenMotion:before{content:'';position:absolute;inset:-10%;background:linear-gradient(110deg,transparent 38%,rgba(170,225,255,.12) 50%,transparent 62%);transform:translateX(-120%);animation:abajTvPictureSweep 7s ease-in-out infinite}
@keyframes abajTvPictureSweep{0%,15%{transform:translateX(-120%)}70%,100%{transform:translateX(120%)}}
#abajLauncher[hidden] .abajTvScreenMotion:before,#abajLauncher[hidden] .abajTvScreenMotion:after{animation-play-state:paused}
@media(prefers-reduced-motion:reduce){.abajLaunchTile[data-target="iptv"] .abajTvScreenMotion{display:none}}
/* Subtle drifting cloud haze confined to the upper-left mountain picture.
   Transparent overlay: the original mountains remain visible, with no duplicate imagery. */
/* Keep the lighting layers over the artwork but behind the IPTV title. */
#abajLauncher .abajLaunchTile[data-target="iptv"] .abajSceneMotion{z-index:1;isolation:isolate}
#abajLauncher .abajLaunchTile[data-target="iptv"] .abajLaunchText{z-index:3}

.abajIptvFlightCurtain{position:fixed;inset:0;z-index:2147483646;background:#06152c;opacity:0;pointer-events:none}.abajCinemaLensWash{position:fixed;inset:0;z-index:2147483646;pointer-events:none;opacity:0;background:linear-gradient(90deg,#ff26382b 0%,#f4293b3b 49.7%,#1aafff3b 50.3%,#09b8ff30 100%)}.abaj3dRig{position:absolute;inset:0;transform-style:preserve-3d;perspective:600px}.abaj3dFront{position:absolute;left:8%;top:25%;width:84%;height:50%;display:flex;gap:7%;align-items:center;transform:translateZ(22px);transform-style:preserve-3d}.abaj3dLens{position:relative;width:46.5%;height:100%;border:11px solid #11151d;border-radius:27% 27% 38% 38%;box-shadow:inset 0 3px 7px #0009,0 2px 2px #77808a,0 6px 9px #0007;box-sizing:border-box;backface-visibility:visible}.abaj3dRed{background:linear-gradient(145deg,#ffabb880,#ff183eab 55%,#8d0929cb)}.abaj3dBlue{background:linear-gradient(145deg,#b9f4ff9c,#13b4f8bd 55%,#0643a8c9)}.abaj3dBridge{position:absolute;left:45%;top:21%;width:10%;height:23%;border-top:10px solid #16191e;border-radius:50%;z-index:2}.abaj3dArm{position:absolute;top:34%;width:12px;height:105px;background:linear-gradient(90deg,#050608,#505864,#0c0e12);border-radius:8px;transform-origin:top center;box-shadow:1px 0 3px #0008;backface-visibility:visible}.abaj3dArmLeft{left:9%;transform:translateZ(17px) rotateX(-64deg) rotateY(-16deg)}.abaj3dArmRight{right:9%;transform:translateZ(17px) rotateX(-64deg) rotateY(16deg)}.abajCinema3dGlasses{position:fixed;z-index:2147483647;width:300px;height:145px;pointer-events:none;transform:translate(-50%,-50%);transform-style:preserve-3d;will-change:transform;filter:drop-shadow(0 5px 5px #0005)}.abajIptvFlyingBall{position:fixed;z-index:2147483647;display:block;width:76px;height:76px;line-height:0;text-align:center;pointer-events:none;transform:translate(-50%,-50%);filter:drop-shadow(0 7px 8px #0009);user-select:none;transform-style:preserve-3d}
.abajLaunchTile[data-target="iptv"] .abajIptvMotionVideo{position:absolute;inset:0;width:100%;height:100%;object-fit:cover;pointer-events:none;z-index:1;border-radius:inherit}
.abajLaunchTile[data-target="iptv"].abajIptvVideoReady{background-image:linear-gradient(0deg,#010b19b3,transparent 42%),var(--tile-bg)!important}
body:not(.darkMode) #abajLauncher .abajLaunchTile[data-target="iptv"].abajIptvVideoReady .abajIptvMotionVideo{opacity:.82}
.abajLaunchTile[data-target="settings"].abajGearReady{background-image:linear-gradient(0deg,#010b19b3,transparent 42%),url('/static/launcher-settings-background.webp')!important;background-size:cover,cover!important;background-position:center,center!important}
.abajLaunchTile[data-target="settings"].abajGearReady .abajSceneMotion:before{content:'';position:absolute;inset:0;pointer-events:none;background:radial-gradient(ellipse 37% 68% at 75% 42%,#031b34e8 0%,#04203aa8 52%,transparent 100%);opacity:.42}
.abajLaunchTile[data-target="settings"].abajGearReady .abajSceneGear{display:none}
.abajLaunchTile[data-target="settings"] .abajGearForeground{display:none;position:absolute;z-index:1;left:55.34%;top:4.39%;width:35.81%;height:69.01%;background:url('/static/launcher-gear-foreground.png') center/contain no-repeat;pointer-events:none;transform-origin:center center}
.abajLaunchTile[data-target="settings"].abajGearReady .abajGearForeground{display:block;animation:abajGearTurn 18s linear infinite}
@media(prefers-reduced-motion:reduce){.abajLaunchTile[data-target="settings"].abajGearReady .abajGearForeground{animation:none!important}}
#abajLauncher[hidden] .abajGearForeground{animation-play-state:paused!important}
.abajLaunchTile[data-target="settings"] .abajSceneGear{display:block;left:51%;top:6%;width:44%;height:72%;border-radius:50%;background:conic-gradient(from 0deg,transparent 0deg,transparent 275deg,#b8ecff00 295deg,#c8edff24 316deg,transparent 340deg,transparent 360deg);mix-blend-mode:screen;opacity:.4;animation:abajGearLight 18s linear infinite}
@keyframes abajGearLight{to{transform:rotate(360deg)}}
@keyframes abajSunDrift{0%{transform:translate(-8%,20%) scale(.7);opacity:.12}25%{transform:translate(-2%,3%) scale(.95);opacity:.55}50%{transform:translate(5%,-13%) scale(1.16);opacity:.9}75%{transform:translate(10%,4%) scale(.94);opacity:.5}100%{transform:translate(14%,20%) scale(.7);opacity:.12}}
@keyframes abajWaterSwim{from{transform:translate(-25%,7%) scale(.85);opacity:.22}to{transform:translate(48%,-14%) scale(1.3);opacity:.7}}
@keyframes abajGearTurn{to{transform:rotate(360deg)}}
@media(prefers-reduced-motion:reduce){.abajSceneMotion i,.abajSceneDolphin,.abajSceneGearOverlay{animation:none!important}}

.abajLaunchText{display:flex;flex-direction:column;gap:7px;max-width:calc(100% - 48px);position:relative;z-index:2}
.abajLaunchName{font-size:clamp(28px,3.25vw,44px);font-weight:800;line-height:1.08;letter-spacing:-.7px;text-shadow:0 2px 8px #0008}
.abajLaunchDesc{font-size:clamp(13px,1.5vw,19px);line-height:1.35;font-weight:400;color:#b8ccdf;text-shadow:0 1px 5px #0009}
.abajLaunchIcon,.abajLaunchFoot{display:none}
#abajLaunchHome{position:fixed;bottom:18px;left:18px;z-index:8000;background:#041b3ae8;color:#fff;border:2px solid #12baff;border-radius:50%;width:49px;height:49px;font-size:26px;box-shadow:0 0 18px #039bff}
@media(min-width:651px){.abajLaunchTile[data-target="settings"]{background-size:cover,auto 90%;background-repeat:no-repeat;background-position:center,85% top}}
@media(max-width:650px){
#abajLauncher{height:100vh;height:100dvh;padding:0 13px max(14px,env(safe-area-inset-bottom));background-size:100% auto}
.abajLaunchTop{min-height:90px;min-height:clamp(85px,12dvh,132px)}
.abajLaunchBrand{font-size:clamp(42px,11.4vw,67px);letter-spacing:.5px}
.abajLaunchTitle{font-size:clamp(9px,2.8vw,14px);letter-spacing:clamp(1px,.5vw,2.5px);margin:9px 0 14px;white-space:nowrap}
.abajLaunchTiles{display:flex;flex-direction:column;gap:10px;flex:1 0 auto;min-height:555px}
.abajLaunchTile{flex:1.26 1 0;min-height:185px;padding:16px 20px;border-radius:18px;background-position:center}
.abajLaunchTile[data-target="settings"]{flex:1 1 0;min-height:165px}
.abajLaunchName{font-size:clamp(27px,8vw,40px)}
.abajLaunchDesc{font-size:clamp(12px,3.7vw,18px)}
.abajLaunchText{gap:6px;max-width:calc(100% - 38px)}
#abajLauncher .abajLaunchTile:after{width:34px;height:34px;right:17px;bottom:21px}
#abajLauncher .abajLaunchTile:before{right:30px;bottom:33px;width:9px;height:9px}
}
@media(max-height:620px) and (max-width:650px) and (orientation:portrait){
.abajLaunchTop{min-height:65px}.abajLaunchBrand{font-size:39px}.abajLaunchTitle{margin:5px 0 10px;font-size:9px}.abajLaunchTiles{min-height:430px;gap:8px}.abajLaunchTile{min-height:145px;padding:12px 16px}.abajLaunchTile[data-target="settings"]{min-height:124px}.abajLaunchName{font-size:26px}.abajLaunchDesc{font-size:12px}
}
@media(orientation:landscape) and (max-height:520px){
#abajLauncher{padding:8px 18px 16px}.abajLaunchTop{min-height:48px}.abajLaunchBrand{font-size:40px}.abajLaunchTitle{font-size:10px;margin:6px 0 12px}.abajLaunchTiles{display:grid;grid-template-columns:repeat(3,minmax(0,1fr));gap:12px;min-height:180px}.abajLaunchTile,.abajLaunchTile[data-target="settings"]{min-height:180px;padding:14px}.abajLaunchName{font-size:25px}.abajLaunchDesc{font-size:12px}.abajLaunchText{max-width:100%;padding-right:0}#abajLauncher .abajLaunchTile:after,#abajLauncher .abajLaunchTile:before{display:none}
}
body:not(.darkMode) #abajLauncher{color:#102b46;background-color:#edf5fc;background-size:100% 34.4vw;background-image:linear-gradient(180deg,#edf6ff80 0%,#edf5fca8 70%,#edf5fc 100%),url('/static/launcher-header-20261014.webp')}
body:not(.darkMode) #abajLauncher .abajLaunchBrand{color:#103a5c;text-shadow:0 2px 16px #ffffffb3}
body:not(.darkMode) #abajLauncher .abajLaunchBrand b{color:#008fc8}
body:not(.darkMode) #abajLauncher .abajLaunchTitle{color:#386681}
body:not(.darkMode) #abajLauncher .abajLaunchTile{color:#102b46;background-color:#f7fbff;background-image:linear-gradient(0deg,#f7fbff 0%,#f7fbfff7 26%,#f7fbff59 48%,transparent 68%),var(--tile-bg);border-color:#88bddc;box-shadow:inset 0 0 0 1px #ffffffb3,0 7px 24px #245b8226}
body:not(.darkMode) #abajLauncher .abajLaunchTile[data-target="settings"].abajGearReady{background-image:linear-gradient(0deg,#f7fbff 0%,#f7fbfff7 26%,#f7fbff59 48%,transparent 68%),url('/static/launcher-settings-background.webp')!important}
body:not(.darkMode) #abajLauncher .abajLaunchName{color:#10314d;text-shadow:0 1px 6px #ffffffb3}
body:not(.darkMode) #abajLauncher .abajLaunchDesc{color:#3e607a;text-shadow:0 1px 4px #ffffffb3}
body:not(.darkMode) #abajLauncher .abajLaunchTile:after{border-color:#58a7d2;background:linear-gradient(145deg,#ffffffed,#e0f2ffed);box-shadow:inset 0 0 0 1px #fff,0 3px 12px #25678926}
body:not(.darkMode) #abajLauncher .abajLaunchTile:before{border-color:#17608a}
body:not(.darkMode) #abajLauncher .abajLaunchTile:hover{border-color:#198fc6;box-shadow:0 7px 24px #167eb833}
body:not(.darkMode) #abajLauncher .abajLaunchTile:focus-visible{outline-color:#087fb9!important;border-color:#087fb9;box-shadow:0 0 20px #159bdb59!important}
body:not(.darkMode) #abajLaunchHome{background:#f3faff;color:#12628f;border-color:#58a7d2;box-shadow:0 3px 14px #25678926}
@media(prefers-reduced-motion:reduce){.abajLaunchTile{animation:none!important;transition:none!important}}
`;
function start(){
if(document.getElementById('abajLauncher'))return;
const style=document.createElement('style');style.textContent=css;document.head.appendChild(style);
const root=document.createElement('section');root.id='abajLauncher';root.setAttribute('aria-label','ABAJ TV — главная');root.innerHTML=`<div class="abajLaunchTop"><div class="abajLaunchBrand">ABAJ<b>TV</b></div></div><div class="abajLaunchTitle">ВАШ МИР КИНО И ТЕЛЕВИДЕНИЯ</div><div class="abajLaunchTiles"><button class="abajLaunchTile" data-target="cinema" style="--tile-bg:url('/static/launcher-cinema-20261014.webp')"><span class="abajLaunchIcon">🎞</span><span class="abajLaunchText"><span class="abajLaunchName">Кинотеатр</span><span class="abajLaunchDesc">Фильмы, сериалы, мультфильмы</span></span></button><button class="abajLaunchTile" data-target="iptv" style="--tile-bg:url('/static/launcher-iptv-20261014.webp')"><span class="abajLaunchIcon">▣</span><span class="abajLaunchText"><span class="abajLaunchName">IPTV</span><span class="abajLaunchDesc">Каналы и прямые эфиры</span></span></button><button class="abajLaunchTile" data-target="settings" style="--tile-bg:url('/static/launcher-settings-20261014.webp')"><span class="abajLaunchIcon">⚙</span><span class="abajLaunchText"><span class="abajLaunchName">Настройки</span><span class="abajLaunchDesc">Параметры и управление</span></span></button></div><div class="abajLaunchFoot"></div>`;
document.body.appendChild(root);
for(const tile of root.querySelectorAll('.abajLaunchTile')){
const motion=document.createElement('span');motion.className='abajSceneMotion';motion.setAttribute('aria-hidden','true');
const accent=document.createElement('i');accent.className=tile.dataset.target==='cinema'?'abajSceneSun':tile.dataset.target==='iptv'?'abajSceneWater':'abajSceneGear';
motion.appendChild(accent);
if(tile.dataset.target==='iptv'){const backlight=document.createElement('i');backlight.className='abajTvBacklight';motion.appendChild(backlight);const screen=document.createElement('i');screen.className='abajTvScreenMotion';motion.appendChild(screen);}
tile.insertBefore(motion,tile.firstChild);
}
// A true dolphin dive must be a rendered sequence, not a rotated flat PNG.
// Enable a seamless full-card video only if the approved asset exists.
// The old optional dolphin .webm does not exist in this repository.
// Do not request a missing video or cover the photo with a broken player.
// Original IPTV artwork is kept intact: no artificial video strip or duplicate ball.


// Progressive enhancement: only replace the original settings art if BOTH layers load.
const settingsTile=root.querySelector('.abajLaunchTile[data-target="settings"]');
if(settingsTile){
 const urls=['/static/launcher-settings-background.webp','/static/launcher-gear-foreground.png'];
 let loaded=0,failed=false;
 const expectedSizes=[[1536,797],[550,555]];
 urls.forEach((url,index)=>{
  const img=new Image();
  img.onload=()=>{
   if(failed||!settingsTile.isConnected)return;
   // Reject an HTML fallback, corrupt asset, or a mismatched export.
   if(img.naturalWidth!==expectedSizes[index][0]||img.naturalHeight!==expectedSizes[index][1]){failed=true;return}
   if(++loaded===urls.length){
   const gear=document.createElement('span');gear.className='abajGearForeground';gear.setAttribute('aria-hidden','true');
   settingsTile.insertBefore(gear,settingsTile.querySelector('.abajLaunchText'));
   // Align the original 550x555px cutout to the 1536x797px source
   // using the same centered "cover" geometry as the background image.
   const alignGear=()=>{
    const w=settingsTile.clientWidth,h=settingsTile.clientHeight;
    if(!w||!h)return;
    const scale=Math.max(w/1536,h/797);
    const offsetX=(w-1536*scale)/2,offsetY=(h-797*scale)/2;
    gear.style.left=(offsetX+850*scale)+'px';
    gear.style.top=(offsetY+35*scale)+'px';
    gear.style.width=(550*scale)+'px';
    gear.style.height=(555*scale)+'px';
   };
   alignGear();
   if(typeof ResizeObserver!=='undefined'){
    const observer=new ResizeObserver(alignGear);observer.observe(settingsTile);
   }else{window.addEventListener('resize',alignGear,{passive:true})}
   settingsTile.classList.add('abajGearReady');
  }};
  img.onerror=()=>{failed=true};
  img.src=url;
 });
}
const brand=root.querySelector('.abajLaunchBrand');
for(const [x,y,delay,speed] of [[5,22,0,2.7],[17,70,-1.3,3.2],[29,18,-.8,2.4],[42,77,-2.1,3.5],[54,25,-1.7,2.9],[67,69,-.4,3.1],[80,16,-2.5,2.6],[93,73,-1.1,3.4]]){
const spark=document.createElement('i');
spark.className='abajBrandSpark';
spark.style.cssText='left:'+x+'%;top:'+y+'%;--spark-delay:'+delay+'s;--spark-speed:'+speed+'s';
spark.setAttribute('aria-hidden','true');
brand.appendChild(spark);
}
const launcherTranslations={
ru:{title:'ВАШ МИР КИНО И ТЕЛЕВИДЕНИЯ',cinema:'Кинотеатр',cinemaDesc:'Фильмы, сериалы, мультфильмы',iptv:'IPTV',iptvDesc:'Каналы и прямые эфиры',settings:'Настройки',settingsDesc:'Параметры и управление',home:'Главная ABAJ TV'},
hy:{title:'ԿԻՆՈՅԻ ԵՎ ՀԵՌՈՒՍՏԱՏԵՍՈՒԹՅԱՆ ՁԵՐ ԱՇԽԱՐՀԸ',cinema:'Կինոթատրոն',cinemaDesc:'Ֆիլմեր, սերիալներ, մուլտֆիլմեր',iptv:'IPTV',iptvDesc:'Հեռուստաալիքներ և ուղիղ եթերներ',settings:'Կարգավորումներ',settingsDesc:'Կարգավորումներ և կառավարում',home:'ABAJ TV գլխավոր էջ'},
en:{title:'YOUR WORLD OF MOVIES AND TELEVISION',cinema:'Cinema',cinemaDesc:'Movies, series, cartoons',iptv:'IPTV',iptvDesc:'Channels and live TV',settings:'Settings',settingsDesc:'Preferences and controls',home:'ABAJ TV Home'}
};
let launcherLanguage='';
function applyLauncherLanguage(){
const selected=localStorage.getItem('abaj_tv_lang')||'ru';
const lang=launcherTranslations[selected]?selected:'ru';
if(lang===launcherLanguage)return;
launcherLanguage=lang;
root.dataset.launchLang=lang;
const t=launcherTranslations[lang];
root.querySelector('.abajLaunchTitle').textContent=t.title;
for(const [target,name,desc] of [['cinema',t.cinema,t.cinemaDesc],['iptv',t.iptv,t.iptvDesc],['settings',t.settings,t.settingsDesc]]){
const tile=root.querySelector('[data-target="'+target+'"]');
tile.querySelector('.abajLaunchName').textContent=name;
tile.querySelector('.abajLaunchDesc').textContent=desc;
}
root.setAttribute('aria-label',t.home);
if(typeof home!=='undefined'){home.title=t.home;home.setAttribute('aria-label',t.home)}
}
document.addEventListener('click',e=>{
if(e.target.closest('#langHyBtn,#langRuBtn,#langEnBtn'))queueMicrotask(applyLauncherLanguage);
});
window.addEventListener('storage',e=>{if(e.key==='abaj_tv_lang')applyLauncherLanguage()});
const home=document.createElement('button');home.id='abajLaunchHome';home.textContent='⌂';home.title='Главная ABAJ TV';home.setAttribute('aria-label','Главная ABAJ TV');home.hidden=true;document.body.appendChild(home);applyLauncherLanguage();

// IPTV transition: the football from the sports thumbnail flies towards the viewer.
let iptvTransitionBusy=false;
let cinemaTransitionBusy=false;
async function playCinemaGlassesTransition(tile){
 if(cinemaTransitionBusy)return false;
 cinemaTransitionBusy=true;
 if(window.matchMedia('(prefers-reduced-motion: reduce)').matches){cinemaTransitionBusy=false;return true}
 const glasses=document.createElement('div');
 glasses.className='abajCinema3dGlasses';
 glasses.setAttribute('aria-hidden','true');
 glasses.innerHTML='<div class="abaj3dRig"><div class="abaj3dArm abaj3dArmLeft"></div><div class="abaj3dArm abaj3dArmRight"></div><div class="abaj3dFront"><div class="abaj3dLens abaj3dRed"></div><div class="abaj3dBridge"></div><div class="abaj3dLens abaj3dBlue"></div></div></div>';
 // Rear view with visible temples and the inner rim, as if the glasses approach the eyes.
 const lensWash=document.createElement('div');
 lensWash.className='abajCinemaLensWash';
 lensWash.setAttribute('aria-hidden','true');
 const rect=tile.getBoundingClientRect();
 glasses.style.left=(rect.left+rect.width*.5)+'px';
 glasses.style.top=(rect.top+rect.height*.48)+'px';
 document.body.appendChild(lensWash);document.body.appendChild(glasses);
 try{
  const dx=innerWidth*.5-(rect.left+rect.width*.5),dy=innerHeight*.5-(rect.top+rect.height*.48);
  const scale=Math.min(3.3,Math.max(1.9,innerWidth/300*2.3));
  const animation=glasses.animate([
   {transform:'translate(-50%,-50%) translate(0px,0px) scale(.12) rotateX(-19deg) rotateY(-20deg) rotateZ(-4deg)',opacity:0,offset:0},
   {transform:'translate(-50%,-50%) translate('+dx*.25+'px,'+dy*.25+'px) scale(.46) rotateX(-12deg) rotateY(-10deg) rotateZ(-2deg)',opacity:1,offset:.28},
   {transform:'translate(-50%,-50%) translate('+dx*.8+'px,'+dy*.8+'px) scale('+scale*.7+') rotateX(-4deg) rotateY(0deg) rotateZ(0deg)',opacity:1,offset:.78},
   {transform:'translate(-50%,-50%) translate('+dx+'px,'+dy+'px) scale('+scale+') rotateX(0deg) rotateY(0deg) rotateZ(0deg)',opacity:1,offset:1}
  ],{duration:1300,easing:'cubic-bezier(.2,.06,.2,1)',fill:'forwards'});
  const wash=lensWash.animate([{opacity:0,offset:0},{opacity:0,offset:.82},{opacity:.18,offset:.94},{opacity:.62,offset:1}],{duration:1300,fill:'forwards'});
  await Promise.race([Promise.all([animation.finished.catch(()=>{}),wash.finished.catch(()=>{})]),new Promise(resolve=>setTimeout(resolve,1600))]);
  wash.cancel();
  animation.cancel();
 }finally{glasses.remove();lensWash.remove();cinemaTransitionBusy=false}
 return true;
}
async function playIptvBallTransition(tile){
 if(iptvTransitionBusy)return false;
 iptvTransitionBusy=true;
 if(window.matchMedia('(prefers-reduced-motion: reduce)').matches){iptvTransitionBusy=false;return true}
 const ball=document.createElement('span');
 ball.className='abajIptvFlyingBall';
 ball.innerHTML='<svg viewBox="0 0 100 100" width="100%" height="100%" xmlns="http://www.w3.org/2000/svg" aria-hidden="true"><defs><radialGradient id="abajBallShade" cx="32%" cy="24%" r="78%"><stop offset="0" stop-color="#fff"/><stop offset=".53" stop-color="#f5f7f9"/><stop offset=".8" stop-color="#b6c0c9"/><stop offset="1" stop-color="#263748"/></radialGradient><clipPath id="abajBallClip"><circle cx="50" cy="50" r="48"/></clipPath></defs><circle cx="50" cy="50" r="48" fill="url(#abajBallShade)"/><g clip-path="url(#abajBallClip)" fill="#101821" stroke="#283541" stroke-width="1.2"><polygon points="48,30 66,38 63,57 43,64 31,47"/><polygon points="6,15 25,8 34,23 20,39 3,34"/><polygon points="77,7 96,19 96,38 80,36 68,21"/><polygon points="8,71 27,65 36,84 25,103 3,94"/><polygon points="73,74 93,63 106,77 92,99 72,95"/></g><g clip-path="url(#abajBallClip)" fill="none" stroke="#78818a" stroke-width="2.2"><path d="M31 47 20 39M48 30 34 23M66 38 80 36M63 57 73 74M43 64 36 84M27 65 20 39M68 21 48 30M93 63 63 57"/></g><ellipse cx="35" cy="20" rx="22" ry="11" fill="#fff" opacity=".28" transform="rotate(-25 35 20)"/></svg>';
 ball.setAttribute('aria-hidden','true');
 ball.style.perspective='550px';
 const r=tile.getBoundingClientRect();
 // The football is near the top centre of the TV screen in the original IPTV artwork.
 const x=r.left+r.width*.665,y=r.top+r.height*.285;
 ball.style.left=x+'px';ball.style.top=y+'px';
 document.body.appendChild(ball);
 try{
  const endX=window.innerWidth/2,endY=window.innerHeight/2;
  const dx=endX-x,dy=endY-y;
  const targetScale=Math.min(6,Math.max(3.5,Math.min(window.innerWidth,window.innerHeight)/76));
  const curtain=document.createElement('span');curtain.className='abajIptvFlightCurtain';document.body.appendChild(curtain);
  const spin=ball.firstElementChild.animate([{transform:'rotate(-12deg)'},{transform:'rotate(150deg)'}],{duration:1200,easing:'ease-out',fill:'forwards'});
  const anim=ball.animate([
   {transform:'translate(-50%,-50%) translate(0px,0px) scale(.12)',opacity:1,offset:0},
   {transform:'translate(-50%,-50%) translate('+dx*.18+'px,'+dy*.18+'px) scale(.48)',opacity:1,offset:.32},
   {transform:'translate(-50%,-50%) translate('+dx*.7+'px,'+dy*.7+'px) scale('+targetScale*.42+')',opacity:1,offset:.74},
   {transform:'translate(-50%,-50%) translate('+dx+'px,'+dy+'px) scale('+targetScale*.94+')',opacity:1,offset:.94},
   {transform:'translate(-50%,-50%) translate('+dx+'px,'+dy+'px) scale('+targetScale+')',opacity:1,offset:1}
  ],{duration:1200,easing:'cubic-bezier(.2,.06,.24,1)',fill:'forwards'});
  const cover=curtain.animate([{opacity:0,offset:0},{opacity:0,offset:.68},{opacity:1,offset:1}],{duration:1200,fill:'forwards'});
  await Promise.race([Promise.all([anim.finished.catch(()=>{}),cover.finished.catch(()=>{})]),new Promise(resolve=>setTimeout(resolve,1550))]);
  anim.cancel();spin.cancel();cover.cancel();curtain.remove();
 }finally{ball.remove();tile.classList.remove('abajIptvBallLaunching');document.querySelectorAll('.abajIptvFlightCurtain').forEach(el=>el.remove());iptvTransitionBusy=false}
 return true;
}
function show(){applyLauncherLanguage();try{if(typeof closeTvSettings==='function')closeTvSettings();if(typeof closeAdmin==='function')closeAdmin()}catch(e){}root.hidden=false;home.hidden=true;root.querySelector('button')?.focus({preventScroll:true})}
function hide(){root.hidden=true;home.hidden=true}
window.abajLauncherHome=show;
root.addEventListener('click',async e=>{const b=e.target.closest('[data-target]');if(!b)return;const target=b.dataset.target;try{if(target==='cinema'){if(cinemaTransitionBusy)return;await playCinemaGlassesTransition(b);if(!document.body.classList.contains('cinemaMode')&&typeof toggleCinemaMode==='function')await toggleCinemaMode();}if(target==='iptv'){if(iptvTransitionBusy)return;await playIptvBallTransition(b)}if(target==='iptv'&&document.body.classList.contains('cinemaMode')&&typeof toggleCinemaMode==='function')await toggleCinemaMode();if(target==='settings'&&typeof openTvSettings==='function')openTvSettings();if(target==='settings'||target==='iptv'||document.body.classList.contains('cinemaMode'))hide()}catch(err){console.error('ABAJ launcher navigation',err)}});
home.addEventListener('click',show);
root.addEventListener('keydown',e=>{const keys=['ArrowRight','ArrowLeft','ArrowUp','ArrowDown'];if(!keys.includes(e.key))return;const bs=[...root.querySelectorAll('[data-target]')];const i=Math.max(0,bs.indexOf(document.activeElement));const delta=(e.key==='ArrowRight'||e.key==='ArrowDown')?1:-1;bs[(i+delta+bs.length)%bs.length].focus({preventScroll:true});e.preventDefault()});
show();
}
if(document.readyState==='loading')document.addEventListener('DOMContentLoaded',()=>setTimeout(start,250));else setTimeout(start,250);
})();