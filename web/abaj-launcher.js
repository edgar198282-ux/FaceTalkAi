/* ABAJ TV Premium Dark launcher — isolated UI layer */
(()=>{'use strict';
const css=`
#abajLauncher{position:fixed;inset:0;z-index:9000;display:flex;flex-direction:column;padding:clamp(18px,3vw,48px);color:#f5fbff;background:linear-gradient(180deg,#02091688,#03122af0 88%),radial-gradient(ellipse at 67% 9%,#177bd1 0%,transparent 45%),linear-gradient(140deg,#020818,#0a2d57 58%,#010711);font-family:Arial,sans-serif;overflow:auto}
#abajLauncher[hidden]{display:none!important}
#abajLauncher *{box-sizing:border-box}
.abajLaunchTop{display:flex;align-items:center;justify-content:space-between;gap:16px}
.abajLaunchBrand{font-size:clamp(27px,4vw,52px);font-weight:900;letter-spacing:2px;color:#fff;text-shadow:0 0 18px #068eff}
.abajLaunchBrand b{color:#32b5ff}
.abajLaunchTime{font-size:clamp(15px,1.7vw,23px);color:#c5e6ff}
.abajLaunchTitle{font-size:clamp(18px,2.3vw,29px);font-weight:750;margin:clamp(20px,5vh,65px) 0 24px}
.abajLaunchTiles{display:grid;grid-template-columns:repeat(3,minmax(0,1fr));gap:clamp(12px,2vw,28px);flex:1;min-height:0}
.abajLaunchTile{position:relative;min-height:260px;max-height:520px;display:flex;flex-direction:column;justify-content:flex-end;text-align:left;gap:8px;padding:clamp(17px,2.5vw,35px);border-radius:14px;border:2px solid #28a8ec;color:white;background:linear-gradient(0deg,#010814fa 0%,#06152b7a 38%,#0b37650b 85%),var(--tile-bg);background-size:cover;background-position:center;box-shadow:inset 0 0 30px #001c44,0 16px 30px #0008,0 0 12px #0076cf55;transition:transform .15s,border-color .15s,box-shadow .15s;cursor:pointer}
.abajLaunchTile:hover,.abajLaunchTile:focus-visible{outline:none;border-color:#b7f3ff;box-shadow:0 0 0 3px #057aff,0 0 32px #00aeff,inset 0 0 30px #04487a;transform:scale(1.015)}
.abajLaunchIcon{display:none}
.abajLaunchName{font-size:clamp(22px,2.8vw,38px);font-weight:900;text-shadow:0 3px 10px #000,0 0 14px #0077ff}
.abajLaunchDesc{font-size:clamp(13px,1.3vw,19px);color:#c4d7e8}
.abajLaunchFoot{display:flex;gap:12px;justify-content:center;margin-top:22px;color:#a7c8e5;font-size:14px}
#abajLaunchHome{position:fixed;left:12px;bottom:12px;z-index:8000;background:#061b36eb;border:1px solid #20a7ff;color:#fff;border-radius:50%;width:45px;height:45px;font-size:24px;box-shadow:0 0 14px #0075c477;cursor:pointer}
#abajLaunchHome[hidden]{display:none!important}
@media(max-width:650px){#abajLauncher{padding:20px 15px 26px}.abajLaunchTitle{margin:22px 0 15px}.abajLaunchTiles{grid-template-columns:1fr;gap:12px;flex:initial}.abajLaunchTile{min-height:170px;max-height:none;flex-direction:row;align-items:flex-end;justify-content:flex-start;gap:16px;padding:18px;border-radius:16px}.abajLaunchIcon{display:none}.abajLaunchName{font-size:24px}.abajLaunchDesc{font-size:13px}.abajLaunchText{display:flex;flex-direction:column;gap:4px}.abajLaunchFoot{margin-top:18px}}
`;
function start(){
if(document.getElementById('abajLauncher'))return;
const style=document.createElement('style');style.textContent=css;document.head.appendChild(style);
const root=document.createElement('section');root.id='abajLauncher';root.setAttribute('aria-label','ABAJ TV — главная');root.innerHTML=`<div class="abajLaunchTop"><div class="abajLaunchBrand">▶ ABAJ <b>TV</b></div><div class="abajLaunchTime" id="abajLaunchClock"></div></div><div class="abajLaunchTitle">Кино и телевидение нового уровня</div><div class="abajLaunchTiles"><button class="abajLaunchTile" data-target="cinema" style="--tile-bg:url('/static/launcher-cinema.svg')"><span class="abajLaunchIcon">🎞</span><span class="abajLaunchText"><span class="abajLaunchName">Кинотеатр</span><span class="abajLaunchDesc">Фильмы, сериалы, мультфильмы</span></span></button><button class="abajLaunchTile" data-target="iptv" style="--tile-bg:url('/static/launcher-iptv.svg')"><span class="abajLaunchIcon">▣</span><span class="abajLaunchText"><span class="abajLaunchName">IPTV</span><span class="abajLaunchDesc">Каналы и прямые эфиры</span></span></button><button class="abajLaunchTile" data-target="settings" style="--tile-bg:url('/static/launcher-settings.svg')"><span class="abajLaunchIcon">⚙</span><span class="abajLaunchText"><span class="abajLaunchName">Настройки</span><span class="abajLaunchDesc">Параметры и управление</span></span></button></div><div class="abajLaunchFoot">◈ &nbsp; Кино &nbsp; · &nbsp; IPTV &nbsp; · &nbsp; Настройки</div>`;
document.body.appendChild(root);
const home=document.createElement('button');home.id='abajLaunchHome';home.textContent='⌂';home.title='Главная ABAJ TV';home.setAttribute('aria-label','Главная ABAJ TV');home.hidden=true;document.body.appendChild(home);
const clock=document.getElementById('abajLaunchClock');function tick(){clock.textContent=new Date().toLocaleTimeString('ru-RU',{hour:'2-digit',minute:'2-digit'})}tick();setInterval(tick,60000);
function show(){try{if(typeof closeTvSettings==='function')closeTvSettings()}catch(e){}root.hidden=false;home.hidden=true;if(document.body.classList.contains('nativeTv'))root.querySelector('button')?.focus({preventScroll:true})}
function hide(){root.hidden=true;home.hidden=false}
root.addEventListener('click',async e=>{const b=e.target.closest('[data-target]');if(!b)return;const target=b.dataset.target;try{if(target==='cinema'&&!document.body.classList.contains('cinemaMode')&&typeof toggleCinemaMode==='function')await toggleCinemaMode();if(target==='iptv'&&document.body.classList.contains('cinemaMode')&&typeof toggleCinemaMode==='function')await toggleCinemaMode();if(target==='settings'&&typeof openTvSettings==='function')openTvSettings();if(target!=='cinema'||document.body.classList.contains('cinemaMode'))hide()}catch(err){console.error('ABAJ launcher navigation',err)}});
home.addEventListener('click',show);
root.addEventListener('keydown',e=>{if(e.key==='ArrowRight'||e.key==='ArrowLeft'){const bs=[...root.querySelectorAll('[data-target]')];const i=bs.indexOf(document.activeElement);bs[(i+(e.key==='ArrowRight'?1:bs.length-1))%bs.length].focus();e.preventDefault()}});
show();
}
if(document.readyState==='loading')document.addEventListener('DOMContentLoaded',()=>setTimeout(start,250));else setTimeout(start,250);
})();