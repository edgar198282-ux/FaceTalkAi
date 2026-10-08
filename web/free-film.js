(()=>{
'use strict';
const css=`
.abajFilmBadge{position:absolute;top:8px;right:8px;z-index:10;padding:3px 9px;border-radius:8px;background:#391744;color:#fff;font:900 13px system-ui;letter-spacing:.06em;box-shadow:0 2px 10px #0009}
/* Every cinema card gets a badge, including cards added by pagination/search. */
#cinemaPosterGrid .cinemaPosterCard{position:relative!important;isolation:isolate}
#cinemaPosterGrid .cinemaPosterCard::before{
 content:"PRO"!important;position:absolute!important;top:9px!important;right:9px!important;
 z-index:30!important;display:block!important;padding:3px 10px!important;
 border-radius:9px!important;background:#421b55!important;color:#fff!important;
 font:900 13px/1.5 system-ui,sans-serif!important;letter-spacing:.04em!important;
 box-shadow:0 2px 10px #0009!important;pointer-events:none!important;
 width:auto!important;height:auto!important;opacity:1!important;
}
#cinemaPosterGrid .cinemaPosterCard[data-abaj-free="1"]::before{
 content:"FREE"!important;background:#05b990!important;color:#05291f!important;
}
#cinemaPosterGrid .cinemaPosterCard .abajFilmBadge{display:none!important}.abajFilmBadge.free{background:#03b68b;color:#021d19}
.abajFreePoster{height:100%;min-height:125px;display:flex;align-items:center;justify-content:center;background:linear-gradient(145deg,#14597b,#45277e);font-size:66px}
#freeCinemaModal{position:fixed;inset:0;background:#010712ec;z-index:999999;display:none;align-items:center;justify-content:center;padding:20px}
#freeCinemaModal.isOpen{display:flex}
#freeCinemaModal .freeBox{background:#102238;border:1px solid #5bdcf8;border-radius:18px;max-width:960px;width:100%;padding:18px;max-height:94vh;overflow:auto;color:#fff}
#freeCinemaModal .freeWatch{display:inline-flex;background:#23c9ec;color:#061a2a;border:0;border-radius:12px;padding:12px 25px;font-weight:900;margin:14px 0;cursor:pointer}#freeCinemaModal .freeDescription{color:#c3dbea;margin:12px 0}#freeCinemaModal video{width:100%;max-height:70vh;background:#000;border-radius:12px}
#freeCinemaModal .freeClose{float:right;background:#264c65;color:white;border:0;border-radius:8px;padding:6px 13px;font-size:19px;cursor:pointer}
`;
const style=document.createElement('style');style.textContent=css;document.head.appendChild(style);
let filmData=null;
async function getFilm(){
 const r=await fetch('/api/cinema/free-film',{cache:'no-store'});
 if(!r.ok)throw Error('film_unavailable');
 filmData=await r.json();return filmData;
}
function openFilm(){
 const modal=document.getElementById('freeCinemaModal');if(!modal)return;
 modal.classList.add('isOpen');
 const t=modal.querySelector('.freeTitle'),v=modal.querySelector('video'),info=modal.querySelector('.freeInfo'),description=modal.querySelector('.freeDescription');
 t.textContent='Загрузка…';
 getFilm().then(d=>{
  t.textContent=d.film.title+' ('+d.film.year+')';if(description)description.textContent=d.film.description||'';
  info.textContent=d.film.genre+' · '+d.film.license+' · '+d.film.credit;
  modal.querySelector(".freeWatch").onclick=()=>{v.src=d.film.url;v.load();v.play().catch(()=>{});modal.querySelector(".freeWatch").style.display="none";};modal.querySelector(".freeWatch").style.display="inline-flex";
 }).catch(()=>{t.textContent='Фильм временно недоступен';});
}
function closeFilm(){
 const modal=document.getElementById('freeCinemaModal');if(!modal)return;
 const v=modal.querySelector('video');v.pause();v.removeAttribute('src');v.load();modal.classList.remove('isOpen');
}
function decorateCinema(){
 const grid=document.getElementById('cinemaPosterGrid');if(!grid)return;
 grid.querySelectorAll('.cinemaPosterCard').forEach(card=>{
  if(card.dataset.abajFree==='1')return;
  if(!card.querySelector('.abajFilmBadge')){
   const badge=document.createElement('span');badge.className='abajFilmBadge';badge.textContent='PRO';card.appendChild(badge);
  }
 });
 let first=grid.querySelector('.cinemaPosterCard[data-abaj-free="1"]');
 if(!first){
  first=document.createElement('button');first.type='button';first.className='cinemaPosterCard';first.dataset.abajFree='1';
  first.innerHTML='<div class="abajFreePoster">🎬</div><span class="abajFilmBadge free">FREE</span><div class="cinemaPosterMeta"><div class="cinemaPosterTitle freeTitle">Бесплатный фильм</div><div class="cinemaPosterSub">Смена каждые 3 дня</div></div>';
  first.onclick=openFilm;
  grid.prepend(first);
 }
 if(filmData?.film){
 const film=filmData.film;
 first.querySelector('.freeTitle').textContent=film.title;
 const poster=first.querySelector('.abajFreePoster');
 if(poster&&film.poster)poster.innerHTML='<img class="cinemaPosterImg" src="'+film.poster+'" alt="" loading="eager" style="width:100%;height:100%;object-fit:cover">';
 const sub=first.querySelector('.cinemaPosterSub');if(sub)sub.textContent=film.year+' · '+film.genre;
}
}
document.addEventListener('DOMContentLoaded',()=>{
 const old=document.getElementById('freeCinemaAccess');if(old)old.remove();
 const modal=document.createElement('div');modal.id='freeCinemaModal';
 modal.innerHTML='<div class="freeBox"><button type="button" class="freeClose" aria-label="Закрыть">✕</button><h3 class="freeTitle">Бесплатный фильм</h3><p class="freeInfo"></p><div class="freeDescription">Нажмите «Смотреть» для просмотра бесплатного фильма.</div><button type="button" class="freeWatch">▶ Смотреть</button><video controls playsinline preload="metadata"></video></div>';
 document.body.appendChild(modal);
 modal.querySelector('.freeClose').onclick=closeFilm;
 modal.addEventListener('click',e=>{if(e.target===modal)closeFilm();});
 document.addEventListener('keydown',e=>{if(e.key==='Escape'&&modal.classList.contains('isOpen')){e.preventDefault();e.stopPropagation();closeFilm();}},true);
 if(document.getElementById('cinemaPosterGrid')){
  const grid=document.getElementById('cinemaPosterGrid');
  const observer=new MutationObserver(()=>{
    if(!grid.querySelector('.cinemaPosterCard[data-abaj-free="1"]')||[...grid.querySelectorAll('.cinemaPosterCard:not([data-abaj-free="1"])')].some(c=>!c.querySelector('.abajFilmBadge')))decorateCinema();
  });
  observer.observe(grid,{childList:true});
  if(typeof renderCinemaCatalog==='function'){
   const original=renderCinemaCatalog;
   renderCinemaCatalog=function(...args){const result=original.apply(this,args);decorateCinema();return result;};
  }
  decorateCinema();
  getFilm().then(()=>decorateCinema()).catch(()=>{});
 }
});
})();