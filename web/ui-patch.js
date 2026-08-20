(() => {
  const tg = window.Telegram?.WebApp;
  const qs = new URLSearchParams(location.search);
  const nativeAndroid = qs.get('source') === 'android' || /FaceTalkAI-Android\//i.test(navigator.userAgent);
  const APK_URL = new URL('/downloads/FaceTalkAI-latest.apk', location.origin).toString();

  const style = document.createElement('style');
  style.textContent = `
    .logo,.brand-splash-logo,.start-logo{object-fit:contain!important;background:#070916!important;padding:3px!important}
    .lang-splash,.lang-switch{display:none!important}
    #ftSettingsModal{position:fixed;inset:0;z-index:2000;background:#030611e8;display:none;align-items:flex-end;justify-content:center}
    #ftSettingsModal.show{display:flex}
    #ftSettingsSheet{width:100%;max-width:700px;background:#0d1528;border:1px solid #263457;border-radius:25px 25px 0 0;padding:22px 18px calc(22px + env(safe-area-inset-bottom));color:#fff}
    #ftSettingsSheet h2{margin:0 0 18px}.ftSettingLabel{font-size:12px;color:#93a4c7;margin:13px 0 8px}.ftLangGrid{display:grid;grid-template-columns:repeat(3,1fr);gap:9px}.ftLang{border:1px solid #34476f;background:#101a30;color:#fff;border-radius:14px;padding:13px 8px;font-weight:800}.ftLang.active{border-color:#a642ff;background:#25113f}.ftInstall{display:block;width:100%;box-sizing:border-box;margin-top:16px;border:0;border-radius:15px;padding:14px;background:linear-gradient(135deg,#7d3eff,#169eff);color:white;font-weight:900;font-size:15px;text-align:center;text-decoration:none}.ftClose{width:100%;margin-top:10px;border:1px solid #34476f;border-radius:15px;padding:13px;background:#10192c;color:#dbe6ff;font-weight:800}
    #ftAdminSettings{width:100%;margin:10px 0 14px;border:1px solid #6840a5;border-radius:14px;padding:11px;background:#20143a;color:#fff;font-weight:800}
  `;
  document.head.appendChild(style);

  const appAction = nativeAndroid
    ? '<button id="ftCheckUpdate" class="ftInstall">🔄 Проверить обновление</button>'
    : '<a id="ftInstallApp" class="ftInstall" href="'+APK_URL+'" target="_blank" rel="external noopener">📲 Скачать приложение APK</a>';

  const modal = document.createElement('div');
  modal.id = 'ftSettingsModal';
  modal.innerHTML = `<div id="ftSettingsSheet"><h2>⚙️ Настройки</h2><div class="ftSettingLabel">Язык приложения</div><div class="ftLangGrid"><button class="ftLang" data-ft-lang="ru">Русский</button><button class="ftLang" data-ft-lang="hy">Հայերեն</button><button class="ftLang" data-ft-lang="en">English</button></div>${appAction}<button id="ftSettingsClose" class="ftClose">Закрыть</button></div>`;
  document.body.appendChild(modal);

  function currentLang(){ return localStorage.getItem('facetalk_lang') || 'ru'; }
  function paintLang(){ modal.querySelectorAll('[data-ft-lang]').forEach(b=>b.classList.toggle('active', b.dataset.ftLang===currentLang())); }
  function openSettings(){ paintLang(); modal.classList.add('show'); }
  function closeSettings(){ modal.classList.remove('show'); }

  modal.querySelectorAll('[data-ft-lang]').forEach(btn => btn.addEventListener('click', () => {
    const lang = btn.dataset.ftLang;
    const original = document.querySelector(`[data-lang="${lang}"]`);
    if (original) original.click();
    else { localStorage.setItem('facetalk_lang', lang); location.reload(); }
    paintLang();
  }));
  document.getElementById('ftSettingsClose').addEventListener('click', closeSettings);
  modal.addEventListener('click', e => { if(e.target===modal) closeSettings(); });

  function authHeaders(){
    const headers = {};
    if(tg?.initData) headers['X-Telegram-Init-Data'] = tg.initData;
    if(qs.get('ft_uid')) headers['X-FaceTalk-Uid'] = qs.get('ft_uid');
    if(qs.get('ft_ts')) headers['X-FaceTalk-Ts'] = qs.get('ft_ts');
    if(qs.get('ft_sig')) headers['X-FaceTalk-Sig'] = qs.get('ft_sig');
    return headers;
  }

  const install = document.getElementById('ftInstallApp');
  if(install){
    install.addEventListener('click', e => {
      if(tg?.openLink){
        e.preventDefault();
        try { tg.openLink(APK_URL, {try_instant_view:false}); }
        catch(_) { window.open(APK_URL, '_blank', 'noopener'); }
      }
    });
  }

  document.getElementById('ftCheckUpdate')?.addEventListener('click', () => {
    location.href = 'facetalk://check-update';
  });

  async function getMe(){
    try { const r=await fetch('/api/me',{headers:authHeaders(),cache:'no-store'}); return r.ok ? await r.json() : null; } catch(_){ return null; }
  }

  function makeSettingsNav(nav){
    nav.classList.add('show'); nav.style.display='block'; nav.dataset.go='settings';
    nav.innerHTML='<strong>⚙️</strong><span>Настройки</span>';
    nav.onclick = e => { e.preventDefault(); e.stopPropagation(); openSettings(); };
  }

  async function configureRoleNav(){
    const nav = document.querySelector('[data-go="admin"]') || document.querySelector('.admin-nav') || document.querySelector('[data-go="settings"]');
    if(!nav) return false;
    const me = await getMe();
    if(me?.is_admin){
      nav.classList.add('show'); nav.style.display='block'; nav.dataset.go='admin';
      nav.innerHTML='<strong>🛡️</strong><span>Админ</span>';
      setTimeout(() => {
        const panel=document.getElementById('adminPanel');
        if(panel && !document.getElementById('ftAdminSettings')){
          const b=document.createElement('button'); b.id='ftAdminSettings'; b.textContent='⚙️ Настройки'; b.onclick=openSettings;
          panel.insertBefore(b,panel.firstChild);
        }
      },500);
    } else makeSettingsNav(nav);
    return true;
  }

  function removeLanguageFromMain(){
    document.getElementById('langSplash')?.classList.remove('show');
    const switcher=document.getElementById('langSwitch'); if(switcher) switcher.style.display='none';
  }

  removeLanguageFromMain();
  let tries=0;
  const timer=setInterval(async()=>{ removeLanguageFromMain(); if(await configureRoleNav() || ++tries>30) clearInterval(timer); },300);
})();
