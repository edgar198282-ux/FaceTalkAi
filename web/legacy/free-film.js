(()=>{"use strict";const a=document.createElement("style");a.textContent=`
#cinemaPosterGrid .cinemaPosterCard{position:relative!important}
#cinemaPosterGrid.abajProLocked .cinemaPosterCard::before{
 content:"PRO"!important;position:absolute!important;top:9px!important;right:9px!important;
 z-index:30!important;padding:3px 10px!important;border-radius:9px!important;
 background:#421b55!important;color:#fff!important;font:900 13px/1.5 system-ui,sans-serif!important;
 letter-spacing:.04em!important;box-shadow:0 2px 10px #0009!important;pointer-events:none!important;
 width:auto!important;height:auto!important;opacity:1!important;
}
#cinemaPosterGrid .cinemaPosterCard .abajFilmBadge{display:none!important}
`,document.head.appendChild(a);function n(t){var o;const e=document.getElementById("cinemaPosterGrid");e&&e.classList.toggle("abajProLocked",((o=t==null?void 0:t.detail)==null?void 0:o.allowed)===!1)}function r(){document.querySelectorAll('#cinemaPosterGrid .cinemaPosterCard[data-abaj-free="1"],#freeCinemaAccess,#freeCinemaModal').forEach(t=>t.remove())}document.addEventListener("DOMContentLoaded",()=>{r(),document.addEventListener("abaj-cinema-access-change",n);const t=document.getElementById("cinemaPosterGrid");t&&new MutationObserver(()=>{const e=t.querySelector('.cinemaPosterCard[data-abaj-free="1"]');e&&e.remove()}).observe(t,{childList:!0})})})();
