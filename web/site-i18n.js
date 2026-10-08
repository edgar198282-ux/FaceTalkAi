(()=>{
const translations={
ru:{nav:['Возможности','Смотреть','Подключение','Помощь','🤖 Бот'],eyebrow:['Телевидение и кино в одном месте','Возможности','Смотреть онлайн','Начало работы','Тарифы','Инструкции и поддержка'],h1:'Ваш экран. Ваш мир развлечений.',lead:'Каналы, фильмы, сериалы и избранное на Android TV, телефоне и в браузере. Удобное управление, быстрый поиск и единый сервис Abaj TV.',buttons:['▶ Смотреть онлайн','Как подключить →'],headings:['Все любимые развлечения','Веб-плеер Abaj TV','Подключение за три шага','Прозрачно и доступно','Частые вопросы'],stats:['каналов после активации','устройства','языки интерфейса'],cards:['Прямой эфир','Фильмы и сериалы','Просто управлять','Откройте бот','Выберите устройство','Активируйте доступ','Бесплатно','Полный доступ']},
hy:{nav:['Հնարավորություններ','Դիտել','Միացում','Օգնություն','🤖 Բոտ'],eyebrow:['Հեռուստատեսություն և կինո՝ մեկ վայրում','Հնարավորություններ','Դիտել առցանց','Ինչպես սկսել','Սակագներ','Հրահանգներ և աջակցություն'],h1:'Ձեր էկրանը։ Ձեր ժամանցի աշխարհը։',lead:'Ալիքներ, ֆիլմեր, սերիալներ և ընտրյալներ Android TV-ում, հեռախոսում և դիտարկիչում։ Հարմար կառավարում, արագ որոնում և Abaj TV միասնական ծառայություն։',buttons:['▶ Դիտել առցանց','Ինչպես միանալ →'],headings:['Ձեր սիրելի ժամանցը','Abaj TV վեբ նվագարկիչ','Միացեք երեք քայլով','Պարզ և մատչելի','Հաճախ տրվող հարցեր'],stats:['ալիք՝ ակտիվացումից հետո','սարք','միջերեսի լեզուներ'],cards:['Ուղիղ եթեր','Ֆիլմեր և սերիալներ','Հեշտ կառավարում','Բացեք բոտը','Ընտրեք սարքը','Ակտիվացրեք մուտքը','Անվճար','Ամբողջական մուտք']},
en:{nav:['Features','Watch','Setup','Help','🤖 Bot'],eyebrow:['Live TV and movies in one place','Features','Watch online','Getting started','Plans','Guides and support'],h1:'Your screen. Your world of entertainment.',lead:'Channels, movies, series and favorites on Android TV, phone and browser. Easy controls, quick search and one unified Abaj TV service.',buttons:['▶ Watch online','How to connect →'],headings:['All your favorite entertainment','Abaj TV web player','Connect in three steps','Simple and affordable','Frequently asked questions'],stats:['channels after activation','devices','interface languages'],cards:['Live TV','Movies and series','Easy to use','Open the bot','Choose a device','Activate access','Free','Full access']}
};
function setText(selector,values){document.querySelectorAll(selector).forEach((el,i)=>{if(values[i]!==undefined)el.textContent=values[i]})}
function apply(lang){
const t=translations[lang]||translations.ru;
document.documentElement.lang=lang==='hy'?'hy':lang;
setText('.navlinks a',t.nav);
setText('.eyebrow',t.eyebrow);
const h=document.querySelector('.hero h1');if(h){const pair=t.h1.split('. ');h.innerHTML=(lang==='ru'?'Ваш экран.<br><span class="gradient">Ваш мир развлечений.</span>':lang==='hy'?'Ձեր էկրանը։<br><span class="gradient">Ձեր ժամանցի աշխարհը։</span>':'Your screen.<br><span class="gradient">Your world of entertainment.</span>');}
setText('.hero .lead',[t.lead]);setText('.hero .actions a',t.buttons);setText('section h2',t.headings);setText('.stats span',t.stats);setText('.grid .card h3',t.cards);
document.querySelectorAll('.siteLangBtn').forEach(b=>{b.classList.toggle('active',b.dataset.lang===lang);b.setAttribute('aria-pressed',String(b.dataset.lang===lang))});
localStorage.setItem('abaj_site_lang',lang);
}
document.addEventListener('DOMContentLoaded',()=>{
const stats=document.querySelector('.stats');if(stats){
const group=document.createElement('div');group.className='siteLangSwitcher';group.setAttribute('aria-label','Language / Язык / Լեզու');
['ru','hy','en'].forEach((lang,i)=>{const b=document.createElement('button');b.type='button';b.className='siteLangBtn';b.dataset.lang=lang;b.textContent=['RU','AM','EN'][i];b.onclick=()=>apply(lang);group.appendChild(b)});
const languageStat=stats.children[2];if(languageStat){languageStat.querySelector('strong').replaceWith(group)}else stats.appendChild(group);
}
apply(localStorage.getItem('abaj_site_lang')||'ru');
});
})();