/* ABAJ TV Premium Dark launcher — isolated UI layer */
(()=>{'use strict';
const css=`
#abajLauncher{position:fixed;inset:0;z-index:9000;overflow-y:auto;display:flex;flex-direction:column;padding:clamp(20px,3vw,46px);color:#f6fbff;background:linear-gradient(180deg,#01071633 0%,#020c26e8 34%,#020917 100%),url('/static/launcher-header.svg?v=5') center top / 100% auto no-repeat,#020917;font-family:Arial,sans-serif}
#abajLauncher[hidden],#abajLaunchHome[hidden]{display:none!important}
#abajLauncher *{box-sizing:border-box}
.abajLaunchTop{display:flex;align-items:center;justify-content:space-between;gap:12px}
.abajLaunchBrand{font-size:clamp(31px,5vw,66px);font-weight:950;letter-spacing:2px;white-space:nowrap;color:#fff;text-shadow:0 0 12px #b4d9ff,0 0 28px #1269ff,0 0 48px #038aff}
.abajLaunchBrand b{color:#03baff;text-shadow:0 0 16px #04caff,0 0 35px #0259ff}
.abajLaunchTime{display:none!important}
.abajLaunchTitle{font-size:clamp(12px,1.6vw,18px);letter-spacing:4px;font-weight:650;text-transform:uppercase;color:#d4e7ff;margin:4px 0 clamp(20px,4vh,40px);text-shadow:0 0 12px #3085ff}
.abajLaunchTiles{display:grid;grid-template-columns:repeat(3,minmax(0,1fr));gap:clamp(16px,2vw,28px);flex:1}
.abajLaunchTile{position:relative;isolation:isolate;min-height:260px;display:flex;align-items:flex-end;text-align:left;padding:clamp(18px,2.5vw,32px);border-radius:24px;border:2px solid #14aaff;background-image:linear-gradient(0deg,#02071bf7 0%,#02071b8a 35%,#02071b0b 75%),var(--tile-bg);background-size:cover;background-position:center;color:#fff;box-shadow:0 0 10px #01aaff,0 0 24px #006bff70,inset 0 0 20px #009cff66;cursor:pointer;transition:transform .18s,box-shadow .18s}
.abajLaunchTile:before{content:'';position:absolute;inset:-2px;border-radius:inherit;pointer-events:none;box-shadow:inset 0 0 12px #07baff66;animation:abajPulse 3s ease-in-out infinite}@keyframes abajPulse{0%,100%{opacity:.5}50%{opacity:1}}\n.abajLaunchTile:after{content:'›';position:absolute;right:16px;bottom:21px;color:#e7f8ff;font-size:45px;line-height:1;text-shadow:0 0 12px #18aaff}
.abajLaunchTile:hover,.abajLaunchTile:focus-visible{outline:none;transform:scale(1.018);border-color:#d8faff;box-shadow:0 0 0 2px #54dfff,0 0 33px #009cff,0 0 60px #126cff,inset 0 0 22px #00baff66}
.abajLaunchText{display:flex;flex-direction:column;gap:9px;max-width:calc(100% - 26px);position:relative;z-index:1}
.abajLaunchIcon{display:none}
.abajLaunchName{font-size:clamp(25px,3.2vw,47px);font-weight:950;line-height:1.06;text-shadow:0 2px 7px #000,0 0 12px #007bff}
.abajLaunchDesc{font-size:clamp(13px,1.5vw,20px);line-height:1.25;color:#e2ecff;text-shadow:0 2px 7px #000}
.abajLaunchFoot{display:none}
#abajLaunchHome{position:fixed;bottom:18px;left:18px;z-index:8000;background:#041b3ae8;color:#fff;border:2px solid #12baff;border-radius:50%;width:49px;height:49px;font-size:26px;box-shadow:0 0 18px #039bff}
@media(max-width:650px){#abajLauncher{padding:18px 15px 25px}.abajLaunchTop{margin-top:0}.abajLaunchBrand{font-size:clamp(30px,9vw,48px)}.abajLaunchTitle{font-size:11px;letter-spacing:2.5px;margin:6px 0 24px}.abajLaunchTime{font-size:16px}.abajLaunchTiles{display:flex;flex-direction:column;gap:17px;flex:initial}.abajLaunchTile{min-height:clamp(185px,26vh,265px);padding:18px 20px;border-radius:23px}.abajLaunchName{font-size:clamp(29px,7.2vw,40px)}.abajLaunchDesc{font-size:clamp(14px,3.7vw,18px)}.abajLaunchTile:after{bottom:21px;font-size:38px}}

/* Refined cinematic home: readable typography, layered lighting and precise mobile spacing */
#abajLauncher{overscroll-behavior:contain;background-image:linear-gradient(180deg,#01081900 0%,#010b22dd 29%,#020b1d 100%),url('/static/launcher-header.svg?v=5');background-position:center top;background-size:100% auto;background-repeat:no-repeat;background-color:#020b1d}
.abajLaunchTop{min-height:clamp(78px,11vh,128px);align-items:center}
.abajLaunchBrand{font-family:Arial,sans-serif;font-size:clamp(40px,5.7vw,74px);letter-spacing:3px;line-height:1.08}
.abajLaunchTitle{margin:0 0 clamp(21px,3vh,38px);font-size:clamp(12px,1.6vw,19px);font-weight:750;letter-spacing:3px;white-space:normal}
.abajLaunchTiles{align-items:stretch}
.abajLaunchTile{overflow:hidden;border:2px solid #0ebaff;border-radius:28px;background-image:linear-gradient(180deg,#02081a00 8%,#02081a20 38%,#020817f2 100%),var(--tile-bg);background-position:center center;box-shadow:0 0 0 1px #74e8ff77,0 0 19px #00c2ffdd,0 0 42px #0074ff99,inset 0 0 20px #00bfff66}
.abajLaunchTile:before{inset:0;border-radius:inherit;box-shadow:inset 0 0 14px #5cdfffaa;animation:abajPulse 4s ease-in-out infinite}
.abajLaunchTile:after{right:20px;bottom:28px;font-size:54px;font-weight:300}
.abajLaunchName{font-size:clamp(29px,3.6vw,52px);letter-spacing:-.7px;text-shadow:0 2px 9px #000,0 0 18px #000}
.abajLaunchDesc{font-size:clamp(15px,1.6vw,23px);color:#e6f2ff;text-shadow:0 2px 9px #000}
.abajLaunchTile:active{transform:scale(.988)}
@media(max-width:650px){
#abajLauncher{padding:16px 17px max(26px,env(safe-area-inset-bottom));background-size:100% auto}
.abajLaunchTop{min-height:clamp(72px,9vh,96px)}
.abajLaunchBrand{font-size:clamp(37px,9vw,54px);letter-spacing:1.2px}
.abajLaunchTitle{font-size:clamp(11px,2.9vw,14px);letter-spacing:2.1px;margin:0 0 14px;line-height:1.4}
.abajLaunchTiles{gap:12px}
.abajLaunchTile{min-height:clamp(155px,20vh,210px);padding:16px 20px 20px;border-radius:26px;background-position:center 43%;background-size:cover}
.abajLaunchText{gap:9px;max-width:calc(100% - 38px)}
.abajLaunchName{font-size:clamp(29px,7.6vw,41px)}
.abajLaunchDesc{font-size:clamp(14px,3.8vw,19px)}
.abajLaunchTile:after{right:16px;bottom:22px;font-size:43px}
}
@media(min-width:651px) and (max-width:1050px){.abajLaunchTile{min-height:330px}.abajLaunchTiles{gap:18px}}
/* Fit all three cards and header to the actual viewport; retain animated neon focus. */
@media(max-width:650px){
#abajLauncher{height:100dvh;max-height:100dvh;overflow:hidden;display:flex;flex-direction:column;padding:clamp(10px,1.5dvh,18px) 17px clamp(10px,1.5dvh,20px)}
.abajLaunchTop{flex:0 0 auto;min-height:clamp(62px,8dvh,96px)}
.abajLaunchTitle{flex:0 0 auto;margin:0 0 clamp(8px,1.2dvh,16px)}
.abajLaunchTiles{display:flex;flex:1 1 0;min-height:0;flex-direction:column;gap:clamp(9px,1.4dvh,16px)}
.abajLaunchTile{flex:1 1 0;min-height:0;height:auto;padding:clamp(10px,1.8dvh,20px) 20px;border-radius:26px}
.abajLaunchName{font-size:clamp(25px,6.9vw,41px)}
.abajLaunchDesc{font-size:clamp(12px,3.5vw,19px)}
.abajLaunchTile:after{bottom:clamp(12px,2dvh,22px)}
}
.abajLaunchTile:focus-visible{animation:abajNeonFocus 2.4s ease-in-out infinite}
@keyframes abajNeonFocus{0%,100%{box-shadow:0 0 0 2px #b8f6ff,0 0 18px #00baff,0 0 32px #007bff}50%{box-shadow:0 0 0 3px #e3ffff,0 0 28px #00d9ff,0 0 52px #007bff}}
@media(prefers-reduced-motion:reduce){.abajLaunchTile,.abajLaunchTile:before{animation:none!important;transition:none!important}}
`;
function start(){
if(document.getElementById('abajLauncher'))return;
const style=document.createElement('style');style.textContent=css;document.head.appendChild(style);
const root=document.createElement('section');root.id='abajLauncher';root.setAttribute('aria-label','ABAJ TV — главная');root.innerHTML=`<div class="abajLaunchTop"><div class="abajLaunchBrand">▶ ABAJ <b>TV</b></div></div><div class="abajLaunchTitle">ВАШ МИР КИНО И ТЕЛЕВИДЕНИЯ</div><div class="abajLaunchTiles"><button class="abajLaunchTile" data-target="cinema" style="--tile-bg:url('/static/launcher-cinema.svg?v=5')"><span class="abajLaunchIcon">🎞</span><span class="abajLaunchText"><span class="abajLaunchName">Кинотеатр</span><span class="abajLaunchDesc">Фильмы, сериалы, мультфильмы</span></span></button><button class="abajLaunchTile" data-target="iptv" style="--tile-bg:url('/static/launcher-iptv.svg?v=5')"><span class="abajLaunchIcon">▣</span><span class="abajLaunchText"><span class="abajLaunchName">IPTV</span><span class="abajLaunchDesc">Каналы и прямые эфиры</span></span></button><button class="abajLaunchTile" data-target="settings" style="--tile-bg:url('/static/launcher-settings.svg?v=5')"><span class="abajLaunchIcon">⚙</span><span class="abajLaunchText"><span class="abajLaunchName">Настройки</span><span class="abajLaunchDesc">Параметры и управление</span></span></button></div><div class="abajLaunchFoot"></div>`;
document.body.appendChild(root);
const home=document.createElement('button');home.id='abajLaunchHome';home.textContent='⌂';home.title='Главная ABAJ TV';home.setAttribute('aria-label','Главная ABAJ TV');home.hidden=true;document.body.appendChild(home);

function show(){try{if(typeof closeTvSettings==='function')closeTvSettings();if(typeof closeAdmin==='function')closeAdmin()}catch(e){}root.hidden=false;home.hidden=true;root.querySelector('button')?.focus({preventScroll:true})}
function hide(){root.hidden=true;home.hidden=true}
window.abajLauncherHome=show;
root.addEventListener('click',async e=>{const b=e.target.closest('[data-target]');if(!b)return;const target=b.dataset.target;try{if(target==='cinema'&&!document.body.classList.contains('cinemaMode')&&typeof toggleCinemaMode==='function')await toggleCinemaMode();if(target==='iptv'&&document.body.classList.contains('cinemaMode')&&typeof toggleCinemaMode==='function')await toggleCinemaMode();if(target==='settings'&&typeof openTvSettings==='function')openTvSettings();if(target==='settings'||target==='iptv'||document.body.classList.contains('cinemaMode'))hide()}catch(err){console.error('ABAJ launcher navigation',err)}});
home.addEventListener('click',show);
root.addEventListener('keydown',e=>{const keys=['ArrowRight','ArrowLeft','ArrowUp','ArrowDown'];if(!keys.includes(e.key))return;const bs=[...root.querySelectorAll('[data-target]')];const i=Math.max(0,bs.indexOf(document.activeElement));const delta=(e.key==='ArrowRight'||e.key==='ArrowDown')?1:-1;bs[(i+delta+bs.length)%bs.length].focus({preventScroll:true});e.preventDefault()});
show();
}
if(document.readyState==='loading')document.addEventListener('DOMContentLoaded',()=>setTimeout(start,250));else setTimeout(start,250);
})();