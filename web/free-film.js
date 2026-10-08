(()=>{'use strict';
const style=document.createElement('style');
style.textContent=`
#cinemaPosterGrid .cinemaPosterCard{position:relative!important}
#cinemaPosterGrid.abajProLocked .cinemaPosterCard::before{
 content:"PRO"!important;position:absolute!important;top:9px!important;right:9px!important;
 z-index:30!important;padding:3px 10px!important;border-radius:9px!important;
 background:#421b55!important;color:#fff!important;font:900 13px/1.5 system-ui,sans-serif!important;
 letter-spacing:.04em!important;box-shadow:0 2px 10px #0009!important;pointer-events:none!important;
 width:auto!important;height:auto!important;opacity:1!important;
}
#cinemaPosterGrid .cinemaPosterCard .abajFilmBadge{display:none!important}
`;
document.head.appendChild(style);
function syncBadges(event){
 const grid=document.getElementById('cinemaPosterGrid');if(!grid)return;
 // This flag is populated from the server-verified subscription state in the main app.
 grid.classList.toggle('abajProLocked',event?.detail?.allowed===false);
}
function cleanup(){
 document.querySelectorAll('#cinemaPosterGrid .cinemaPosterCard[data-abaj-free="1"],#freeCinemaAccess,#freeCinemaModal').forEach(e=>e.remove());
}
document.addEventListener('DOMContentLoaded',()=>{
 cleanup();
 // Wait for the authenticated server response; never flash PRO badges to admins.
 document.addEventListener('abaj-cinema-access-change',syncBadges);
 const grid=document.getElementById('cinemaPosterGrid');
 if(grid)new MutationObserver(()=>{const old=grid.querySelector('.cinemaPosterCard[data-abaj-free="1"]');if(old)old.remove()}).observe(grid,{childList:true});
});
})();
