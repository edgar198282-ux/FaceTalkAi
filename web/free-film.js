(() => {
'use strict';
const endpoint='/api/cinema/free-film';
const css=`
#freeCinemaFeature{margin:34px 0 0;border:1px solid #6ad9fa77;border-radius:20px;background:linear-gradient(125deg,#102c42,#162038);padding:26px}
#freeCinemaFeature h3{font-size:26px;margin:7px 0}
#freeCinemaFeature video{width:100%;max-height:65vh;background:#03080e;border-radius:15px;margin-top:15px}
#freeCinemaFeature .freeSub{color:#bad7e9}
#freeCinemaAccess{display:none;align-items:center;justify-content:center;background:#063e60;color:#fff;border:1px solid #54e4ff;border-radius:12px;padding:8px 12px;font-weight:800;cursor:pointer}
body.cinemaMode #freeCinemaAccess{display:inline-flex}
#freeCinemaModal{position:fixed;inset:0;background:#010712ed;z-index:999999;display:none;align-items:center;justify-content:center;padding:20px}
#freeCinemaModal.isOpen{display:flex}
#freeCinemaModal .freeBox{background:#102238;border:1px solid #5bdcf8;border-radius:18px;max-width:960px;width:100%;padding:18px;max-height:95vh;overflow:auto;color:#fff}
#freeCinemaModal video{width:100%;max-height:70vh;background:#000;border-radius:12px}
#freeCinemaModal .freeClose{float:right;background:#264c65;color:white;border:0;border-radius:8px;padding:6px 13px;font-size:19px;cursor:pointer}
`;
const style=document.createElement('style');style.textContent=css;document.head.appendChild(style);
async function loadFilm(){
 const response=await fetch(endpoint,{cache:'no-store'});if(!response.ok)throw Error('free film unavailable');return response.json();
}
function details(data, root){
 const film=data.film;
 root.querySelector('.freeTitle').textContent=film.title+' ('+film.year+')';
 root.querySelector('.freeGenre').textContent=film.genre+' · '+film.license+' · '+film.credit;
 const v=root.querySelector('video'); v.pause();v.removeAttribute('src');v.load();v.src=film.url;
 const next=new Date(data.changes_at*1000);root.querySelector('.freeNext').textContent='Следующий фильм: '+next.toLocaleDateString('ru-RU');
}
function markup(){return '<h3 class="freeTitle">Загрузка фильма…</h3><p class="freeGenre freeSub"></p><p class="freeNext freeSub"></p><video controls playsinline preload="metadata" controlsList="nodownload">Ваш браузер не поддерживает видео.</video>';}
document.addEventListener('DOMContentLoaded',()=>{
 if(document.getElementById('connect')){
   const section=document.createElement('section');section.id='free-film';section.className='wrap';
   const box=document.createElement('div');box.id='freeCinemaFeature';
   box.innerHTML='<div style="color:#6ae6fc;font-weight:850">🎁 Бесплатный фильм · меняется каждые 3 дня</div>'+markup();
   section.appendChild(box);
   document.getElementById('connect').before(section);
   loadFilm().then(d=>details(d,box)).catch(()=>{box.querySelector('.freeTitle').textContent='Бесплатный фильм временно недоступен';});
 }
 const toggle=document.getElementById('cinemaToggleBtn');
 if(!toggle)return;
 const button=document.createElement('button');button.id='freeCinemaAccess';button.type='button';button.textContent='🎁 Фильм Free';button.title='Бесплатный фильм, меняется каждые 3 дня';
 toggle.insertAdjacentElement('afterend',button);
 const modal=document.createElement('div');modal.id='freeCinemaModal';
 modal.innerHTML='<div class="freeBox"><button type="button" class="freeClose" aria-label="Закрыть">✕</button><strong>🎁 Бесплатный фильм · меняется каждые 3 дня</strong>'+markup()+'</div>';
 document.body.appendChild(modal);
 const close=()=>{modal.querySelector('video').pause();modal.classList.remove('isOpen');};
 modal.querySelector('.freeClose').onclick=close;
 modal.addEventListener('click',e=>{if(e.target===modal)close();});
 button.onclick=async()=>{
   modal.classList.add('isOpen');
   try{details(await loadFilm(),modal);}
   catch(_){modal.querySelector('.freeTitle').textContent='Бесплатный фильм временно недоступен';}
 };
 document.addEventListener('keydown',e=>{if(e.key==='Escape'&&modal.classList.contains('isOpen')){e.preventDefault();e.stopPropagation();close();}},true);
});
})();