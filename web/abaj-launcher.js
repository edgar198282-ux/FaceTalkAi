/* ABAJ TV Premium Dark launcher — isolated UI layer */
(()=>{'use strict';
const css=`
#abajLauncher{position:fixed;inset:0;z-index:9000;overflow-y:auto;display:flex;flex-direction:column;padding:clamp(20px,3vw,46px);color:#f6fbff;background:linear-gradient(180deg,#01071633 0%,#020c26e8 34%,#020917 100%),url('/static/launcher-header.svg') center top / 100% auto no-repeat,#020917;font-family:Arial,sans-serif}
#abajLauncher[hidden],#abajLaunchHome[hidden]{display:none!important}
#abajLauncher *{box-sizing:border-box}
.abajLaunchTop{display:flex;align-items:center;justify-content:space-between;gap:12px}
.abajLaunchBrand{font-size:clamp(31px,5vw,66px);font-weight:950;letter-spacing:2px;white-space:nowrap;color:#fff;text-shadow:0 0 12px #b4d9ff,0 0 28px #1269ff,0 0 48px #038aff}
.abajLaunchBrand b{color:#03baff;text-shadow:0 0 16px #04caff,0 0 35px #0259ff}
.abajLaunchTime{color:#d8e9ff;font-size:clamp(16px,1.8vw,22px)}
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
`;
function start(){
if(document.getElementById('abajLauncher'))return;
const style=document.createElement('style');style.textContent=css;document.head.appendChild(style);
const root=document.createElement('section');root.id='abajLauncher';root.setAttribute('aria-label','ABAJ TV — главная');root.innerHTML=`<div class="abajLaunchTop"><div class="abajLaunchBrand">▶ ABAJ <b>TV</b></div><div class="abajLaunchTime" id="abajLaunchClock"></div></div><div class="abajLaunchTitle">ВАШ МИР КИНО И ТЕЛЕВИДЕНИЯ</div><div class="abajLaunchTiles"><button class="abajLaunchTile" data-target="cinema" style="--tile-bg:url('/static/launcher-cinema.svg')"><span class="abajLaunchIcon">🎞</span><span class="abajLaunchText"><span class="abajLaunchName">Кинотеатр</span><span class="abajLaunchDesc">Фильмы, сериалы, мультфильмы</span></span></button><button class="abajLaunchTile" data-target="iptv" style="--tile-bg:url('/static/launcher-iptv.svg')"><span class="abajLaunchIcon">▣</span><span class="abajLaunchText"><span class="abajLaunchName">IPTV</span><span class="abajLaunchDesc">Каналы и прямые эфиры</span></span></button><button class="abajLaunchTile" data-target="settings" style="--tile-bg:url('/static/launcher-settings.svg')"><span class="abajLaunchIcon">⚙</span><span class="abajLaunchText"><span class="abajLaunchName">Настройки</span><span class="abajLaunchDesc">Параметры и управление</span></span></button></div><div class="abajLaunchFoot"></div>`;
document.body.appendChild(root);
const home=document.createElement('button');home.id='abajLaunchHome';home.textContent='⌂';home.title='Главная ABAJ TV';home.setAttribute('aria-label','Главная ABAJ TV');home.hidden=true;document.body.appendChild(home);
const clock=document.getElementById('abajLaunchClock');function tick(){clock.textContent=new Date().toLocaleTimeString('ru-RU',{hour:'2-digit',minute:'2-digit'})}tick();setInterval(tick,60000);
function show(){try{if(typeof closeTvSettings==='function')closeTvSettings()}catch(e){}root.hidden=false;home.hidden=true;if(document.body.classList.contains('nativeTv'))root.querySelector('button')?.focus({preventScroll:true})}
function hide(){root.hidden=true;home.hidden=false}
root.addEventListener('click',async e=>{const b=e.target.closest('[data-target]');if(!b)return;const target=b.dataset.target;try{if(target==='cinema'&&!document.body.classList.contains('cinemaMode')&&typeof toggleCinemaMode==='function')await toggleCinemaMode();if(target==='iptv'&&document.body.classList.contains('cinemaMode')&&typeof toggleCinemaMode==='function')await toggleCinemaMode();if(target==='settings'&&typeof openTvSettings==='function')openTvSettings();if(target==='settings'||target==='iptv'||document.body.classList.contains('cinemaMode'))hide()}catch(err){console.error('ABAJ launcher navigation',err)}});
home.addEventListener('click',show);
root.addEventListener('keydown',e=>{const keys=['ArrowRight','ArrowLeft','ArrowUp','ArrowDown'];if(!keys.includes(e.key))return;const bs=[...root.querySelectorAll('[data-target]')];const i=Math.max(0,bs.indexOf(document.activeElement));const delta=(e.key==='ArrowRight'||e.key==='ArrowDown')?1:-1;bs[(i+delta+bs.length)%bs.length].focus({preventScroll:true});e.preventDefault()});
show();
}
if(document.readyState==='loading')document.addEventListener('DOMContentLoaded',()=>setTimeout(start,250));else setTimeout(start,250);
})();