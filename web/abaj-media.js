(()=>{'use strict';
const strings={
ru:{media:'Медиа',desc:'Ваши фото и видео',sections:'Разделы на главной',all:'Все',photo:'Фото',video:'Видео',folders:'Папки',device:'С устройства',choose:'Выбрать фото и видео',cloud:'Облака',connect:'Подключить',disconnect:'Отключить',confirm:'Подтвердить аккаунт',empty:'Здесь появятся ваши фото и видео',localHint:'Выберите фотографии или видео из галереи телефона.',notReady:'Вход в облако ещё не настроен администратором.',loading:'Загрузка…',error:'Не удалось загрузить. Попробуйте ещё раз.',retry:'Повторить',back:'Назад',close:'Закрыть',search:'Поиск в папке',more:'Показать ещё',slide:'Слайд-шоу',stop:'Остановить',full:'Полный экран',unsupported:'Этот формат не поддерживается устройством. Попробуйте MP4 с H.264.',qr:'Отсканируйте QR-код телефоном и войдите в облако. После входа подтвердите аккаунт здесь.',open:'Открыть вход в браузере',cancel:'Отмена',clear:'Убрать выбранные файлы',previous:'Предыдущее',next:'Следующее',cinema:'Кинотеатр',iptv:'IPTV',google:'Google Диск',yandex:'Яндекс Диск'},
en:{media:'Media',desc:'Your photos and videos',sections:'Home screen sections',all:'All',photo:'Photos',video:'Videos',folders:'Folders',device:'This device',choose:'Choose photos and videos',cloud:'Cloud storage',connect:'Connect',disconnect:'Disconnect',confirm:'Confirm account',empty:'Your photos and videos will appear here',localHint:'Choose photos or videos from your phone gallery.',notReady:'Cloud sign-in has not been configured by the administrator.',loading:'Loading…',error:'Could not load. Please try again.',retry:'Retry',back:'Back',close:'Close',search:'Search this folder',more:'Load more',slide:'Slideshow',stop:'Stop',full:'Fullscreen',unsupported:'This format is not supported on this device. Try an H.264 MP4 file.',qr:'Scan this QR code with your phone and sign in. Then confirm the account here.',open:'Open sign-in in browser',cancel:'Cancel',clear:'Clear selected files',previous:'Previous',next:'Next',cinema:'Cinema',iptv:'IPTV',google:'Google Drive',yandex:'Yandex Disk'},
hy:{media:'Մեդիա',desc:'Ձեր լուսանկարներն ու տեսանյութերը',sections:'Գլխավոր էջի բաժիններ',all:'Բոլորը',photo:'Լուսանկարներ',video:'Տեսանյութեր',folders:'Պանակներ',device:'Սարքից',choose:'Ընտրել լուսանկարներ և տեսանյութեր',cloud:'Ամպային պահոցներ',connect:'Միացնել',disconnect:'Անջատել',confirm:'Հաստատել հաշիվը',empty:'Այստեղ կլինեն ձեր լուսանկարներն ու տեսանյութերը',localHint:'Ընտրեք լուսանկարներ կամ տեսանյութեր սարքից։',notReady:'Ադմինիստրատորը դեռ չի կարգավորել ամպի մուտքը։',loading:'Բեռնվում է…',error:'Չհաջողվեց բեռնել։ Փորձեք կրկին։',retry:'Կրկնել',back:'Հետ',close:'Փակել',search:'Որոնել պանակում',more:'Բեռնել ավելին',slide:'Սլայդշոու',stop:'Կանգնեցնել',full:'Ամբողջ էկրան',unsupported:'Այս ձևաչափը չի աջակցվում։ Փորձեք H.264 MP4 ֆայլ։',qr:'Սկանավորեք QR կոդը հեռախոսով և մուտք գործեք։ Այնուհետև այստեղ հաստատեք հաշիվը։',open:'Բացել մուտքը դիտարկիչում',cancel:'Չեղարկել',clear:'Հեռացնել ընտրված ֆայլերը',previous:'Նախորդը',next:'Հաջորդը',cinema:'Կինոթատրոն',iptv:'IPTV',google:'Google Drive',yandex:'Яндекс Диск'}
};
let prefs={cinema:true,iptv:true,media:true};
try{const saved=JSON.parse(localStorage.getItem('abaj_home_sections')||'{}');for(const key of Object.keys(prefs))if(typeof saved[key]==='boolean')prefs[key]=saved[key]}catch(e){}
const t=()=>strings[localStorage.getItem('abaj_tv_lang')]||strings.ru;
const style=document.createElement('style');style.textContent=`
#abajLauncher .abajLaunchTile[hidden]{display:none!important}
#abajLauncher[data-visible="4"] .abajLaunchTiles{grid-template-columns:repeat(2,minmax(0,1fr));gap:14px}
#abajLauncher[data-visible="1"] .abajLaunchTiles{grid-template-columns:1fr}
#abajLauncher[data-visible="2"] .abajLaunchTiles{grid-template-columns:repeat(2,minmax(0,1fr))}
#abajLauncher[data-visible="4"] .abajLaunchTile{min-height:180px}
.abajSectionHeading{display:flex;align-items:center;justify-content:space-between;width:100%;border:0;background:transparent;color:inherit;text-align:left;cursor:pointer;padding:8px 2px}.abajSectionHeading:after{content:'▾';transition:transform .2s}.abajSectionHeading[aria-expanded="true"]:after{transform:rotate(180deg)}.abajSectionHeading:focus-visible{outline:3px solid #09baff;outline-offset:2px}.abajSectionSwitch[hidden]{display:none!important}.abajSectionSwitch{display:flex;width:100%;align-items:center;justify-content:space-between;gap:16px;border:1px solid #a7cce2;border-radius:12px;padding:12px 14px;margin:7px 0;background:#eaf6ff;color:#174866;font:inherit;font-weight:700;cursor:pointer}
.abajSectionSwitch i{position:relative;width:44px;height:26px;flex-shrink:0;border-radius:20px;background:#738b9a;transition:background .2s}
.abajSectionSwitch i:before{content:'';position:absolute;left:3px;top:3px;width:20px;height:20px;background:#fff;border-radius:50%;transition:transform .2s}
.abajSectionSwitch[aria-checked="true"] i{background:#008dc6}.abajSectionSwitch[aria-checked="true"] i:before{transform:translateX(18px)}
body.darkMode .abajSectionSwitch{background:#142a40;color:#eff8ff;border-color:#365574}
#abajMedia,#abajMedia *{box-sizing:border-box}
#abajMedia{position:fixed;inset:0;z-index:10000;background:#edf5fc;color:#153b57;font:16px Arial,sans-serif;overflow:auto;padding:20px max(16px,env(safe-area-inset-right)) max(22px,env(safe-area-inset-bottom))}
#abajMedia[hidden],#abajMedia [hidden]{display:none!important}
#abajMedia.abajMediaPicking{visibility:hidden}
#abajMedia.abajMediaPicking #abajMediaViewer{visibility:visible}
body.darkMode #abajMedia{background:#061426;color:#eff8ff}
#abajMedia button,#abajMedia input{font:inherit;color:inherit;border:1px solid #8ebbd7;background:#e4f2fc;border-radius:12px;padding:11px 14px;min-height:44px;cursor:pointer}
body.darkMode #abajMedia button,body.darkMode #abajMedia input{background:#102b43;border-color:#345a77}
#abajMedia button:focus-visible,#abajMedia input:focus-visible,.abajSectionSwitch:focus-visible{outline:3px solid #09baff!important;outline-offset:3px;box-shadow:0 0 16px #00afff70!important}
#abajMedia button[aria-pressed="true"]{background:#007aaf;color:#fff;border-color:#00bfff}
.abajMediaTop,.abajMediaTools,.abajMediaTabs,.abajMediaAccounts{display:flex;gap:10px;align-items:center;flex-wrap:wrap;margin-bottom:16px}
.abajMediaTop h1{margin:0 auto 0 0;font-size:28px}.abajMediaAccounts{align-items:stretch}.abajMediaAccount{flex:1 1 240px;padding:16px;border:1px solid #7ba4bf65;border-radius:16px;background:#4996c20c;display:flex;flex-direction:column;gap:10px}.abajMediaAccount strong{font-size:19px}.abajMediaAccount small{overflow-wrap:anywhere;opacity:.8}.abajMediaAccount div{display:flex;gap:8px;flex-wrap:wrap}
#abajMediaSearch{flex:1;min-width:150px}.abajMediaPath{font-size:15px;opacity:.8;overflow-wrap:anywhere;margin:4px 0 18px}
.abajMediaGrid{display:grid;grid-template-columns:repeat(auto-fill,minmax(145px,1fr));gap:14px}
#abajMedia .abajMediaItem{display:flex;flex-direction:column;padding:0;overflow:hidden;text-align:left;min-width:0}.abajMediaItem img,.abajMediaThumb{height:125px;width:100%;object-fit:cover;background:linear-gradient(135deg,#103b65,#056b91);display:flex;align-items:center;justify-content:center;font-size:44px;color:#fff}.abajMediaItem span:last-child{padding:11px;white-space:nowrap;overflow:hidden;text-overflow:ellipsis;width:100%;font-size:14px}
.abajMediaNotice{margin:24px auto;max-width:620px;text-align:center;line-height:1.6;opacity:.85}
#abajMediaViewer{position:fixed;inset:0;z-index:11000;background:#020810;display:flex;flex-direction:column;color:#fff;padding:max(10px,env(safe-area-inset-top)) 12px max(10px,env(safe-area-inset-bottom))}
#abajMediaViewer .abajMediaTools{flex-shrink:0;margin:0;justify-content:center}#abajMediaViewer button{background:#102b43;color:#fff;border-color:#345a77;padding:8px 12px;font-size:15px}
.abajMediaStage{display:flex;align-items:center;justify-content:center;flex:1;min-height:0;overflow:hidden}.abajMediaStage img,.abajMediaStage video{max-width:100%;max-height:100%;width:100%;height:100%;object-fit:contain}
#abajMediaCaption{font-size:14px;white-space:nowrap;overflow:hidden;text-overflow:ellipsis;text-align:center;padding:10px}
#abajMediaLogin{position:fixed;inset:0;z-index:12000;background:#020c1df5;display:flex;align-items:center;justify-content:center;padding:20px;color:#fff}.abajMediaLoginCard{width:min(500px,100%);max-height:94vh;overflow:auto;text-align:center}.abajMediaLoginCard img{width:210px;height:210px;max-width:70vw}.abajMediaLoginCard p{line-height:1.5}
@media(max-width:650px){#abajLauncher[data-visible="4"] .abajLaunchTiles{min-height:615px;gap:9px}#abajLauncher[data-visible="4"] .abajLaunchTile{min-height:150px;padding:14px 18px}#abajLauncher[data-visible="4"] .abajLaunchName{font-size:clamp(27px,7.3vw,36px)}#abajLauncher[data-visible="4"] .abajLaunchDesc{font-size:clamp(12px,3.4vw,16px)}.abajMediaGrid{grid-template-columns:repeat(2,minmax(0,1fr))}#abajMedia{padding-top:12px}.abajMediaAccount{flex-basis:100%}}
@media(orientation:landscape) and (max-height:520px){#abajLauncher[data-visible="4"] .abajLaunchTiles{grid-template-columns:repeat(4,minmax(0,1fr));min-height:180px}#abajLauncher[data-visible="4"] .abajLaunchTile{min-height:180px}.abajMediaLoginCard img{width:140px;height:140px}}
#abajLauncher .abajLaunchTile[data-target="media"].abajMediaSceneReady{background-image:linear-gradient(0deg,#03152e 0%,#06223bdb 22%,#06305040 65%),url('/static/launcher-header-20261014.webp');background-position:center,center 58%;background-size:cover}
body:not(.darkMode) #abajLauncher .abajLaunchTile[data-target="media"].abajMediaSceneReady{background-image:linear-gradient(0deg,#f7fbff 0%,#f7fbfff5 24%,#e9f7ff65 55%,#bce4f52b 100%),url('/static/launcher-header-20261014.webp')}
.abajMediaCardScene{position:absolute;inset:0;overflow:hidden;pointer-events:none;z-index:1;perspective:800px}
.abajMediaCardScene svg{position:absolute;overflow:hidden;filter:drop-shadow(0 8px 8px #001b3d55);transform-box:fill-box}
.abajMediaPhotoBack{left:57%;top:5%;width:37%;height:62%;animation:abajMediaBackFloat 10s ease-in-out infinite}
.abajMediaPhotoFront{left:36%;top:1%;width:43%;height:66%;animation:abajMediaFrontFloat 8s ease-in-out infinite}
.abajMediaCloud{left:68%;top:32%;width:25%;height:34%;animation:abajMediaCloudFloat 7s ease-in-out infinite}
.abajMediaPlay{left:57%;top:44%;width:16%;height:26%;animation:abajMediaPlayFloat 6s ease-in-out infinite}
.abajMediaCardScene .abajMediaPicture{transform-origin:var(--photo-center);animation:abajMediaPicturePan 15s ease-in-out infinite alternate}
.abajMediaPhotoBack .abajMediaPicture{animation-duration:18s;animation-direction:alternate-reverse}
.abajMediaCardScene .abajMediaWater{animation:abajMediaWater 4s linear infinite;opacity:.13}
.abajMediaCardScene .abajMediaGlint{animation:abajMediaGlassGlint 8s ease-in-out infinite;opacity:0}
.abajMediaPhotoBack .abajMediaGlint{animation-delay:-4s}
.abajMediaCardGlow{position:absolute;left:52%;top:21%;width:47%;height:62%;background:radial-gradient(ellipse,#b9f8ff70,transparent 67%);animation:abajMediaCloudGlow 5s ease-in-out infinite;opacity:.25}
@keyframes abajMediaFrontFloat{0%,100%{transform:translate(0,1%) rotate(-7deg) rotateY(-3deg)}50%{transform:translate(-2%,-5%) rotate(-4deg) rotateY(3deg)}}
@keyframes abajMediaBackFloat{0%,100%{transform:translate(0,-2%) rotate(8deg) rotateY(4deg)}50%{transform:translate(3%,4%) rotate(5deg) rotateY(-3deg)}}
@keyframes abajMediaCloudFloat{0%,100%{transform:translate(0,2%) scale(.98)}50%{transform:translate(-4%,-8%) scale(1.04)}}
@keyframes abajMediaPlayFloat{0%,100%{transform:translate(0,0) rotate(-3deg)}50%{transform:translate(3%,-7%) rotate(2deg)}}
@keyframes abajMediaPicturePan{from{transform:translate(-2px,0) scale(1.01)}to{transform:translate(3px,-2px) scale(1.055)}}
@keyframes abajMediaWater{from{transform:translateY(0)}to{transform:translateY(8px)}}
@keyframes abajMediaGlassGlint{0%,18%,80%,100%{opacity:0;transform:translateX(-400px)}34%,48%{opacity:.65}65%{opacity:0;transform:translateX(450px)}}
@keyframes abajMediaCloudGlow{0%,100%{opacity:.2;transform:scale(.96)}50%{opacity:.55;transform:scale(1.07)}}
#abajLauncher[hidden] .abajMediaCardScene *,#abajLauncher .abajLaunchTile[hidden] .abajMediaCardScene *,body.abajMediaOpen .abajMediaCardScene *,html.abajMediaMotionPaused .abajMediaCardScene *{animation-play-state:paused!important}
@media(prefers-reduced-motion:reduce){.abajMediaCardScene *{animation:none!important}.abajMediaPhotoFront{transform:rotate(-6deg)}.abajMediaPhotoBack{transform:rotate(7deg)}}
`;document.head.appendChild(style);
let root,panel,viewer,login,grid,notice,search,accounts,tabs,path,more;
let source='device',filter='all',rows=[],localRows=[],trail=[],nextPage='',loading=false,loadVersion=0,viewIndex=-1,slideshow=0,poll=0,returnFocus=null;
const make=(tag,cls,text)=>{const e=document.createElement(tag);if(cls)e.className=cls;if(text)e.textContent=text;return e};
const button=(label,fn)=>{const b=make('button','',label);b.type='button';b.onclick=fn;return b};
async function api(url,options={}){
 const response=await fetch('/api/media/'+url,{...options,headers:{...(typeof authHeaders==='function'?authHeaders():{}),...(options.headers||{})},cache:'no-store'});
 let data;try{data=await response.json()}catch(e){data={}}
 if(!response.ok)throw new Error(data.error||(response.status===401?(t()===strings.ru?'Войдите в ABAJ TV':'Please sign in to ABAJ TV'):t().error));
 return data;
}
function mountMediaCard(tile){
 if(tile.querySelector('.abajMediaCardScene'))return;
 const scene=make('span','abajMediaCardScene');scene.setAttribute('aria-hidden','true');
 const atlas='/static/media-glass-atlas.webp',ns='http://www.w3.org/2000/svg';
 function sprite(className,viewBox,inside){
  const svg=document.createElementNS(ns,'svg');svg.setAttribute('viewBox',viewBox);svg.setAttribute('class',className);svg.setAttribute('focusable','false');
  const img=()=>{const image=document.createElementNS(ns,'image');image.setAttribute('href',atlas);image.setAttribute('width','1000');image.setAttribute('height','1000');return image};svg.appendChild(img());
  if(inside){
   const [x,y,w,h]=inside,id='abajMediaClip'+className;const defs=document.createElementNS(ns,'defs');
   const clip=document.createElementNS(ns,'clipPath');clip.id=id;
   const rect=document.createElementNS(ns,'rect');for(const [name,value] of Object.entries({x,y,width:w,height:h,rx:8}))rect.setAttribute(name,String(value));clip.appendChild(rect);defs.appendChild(clip);
   const gradient=document.createElementNS(ns,'linearGradient');gradient.id=id+'Shine';
   for(const [offset,opacity] of [['0','0'],['.5','.65'],['1','0']]){const stop=document.createElementNS(ns,'stop');stop.setAttribute('offset',offset);stop.setAttribute('stop-color','#eaffff');stop.setAttribute('stop-opacity',opacity);gradient.appendChild(stop)}defs.appendChild(gradient);svg.appendChild(defs);
   const clipped=document.createElementNS(ns,'g');clipped.setAttribute('clip-path','url(#'+id+')');
   const picture=img();picture.setAttribute('class','abajMediaPicture');picture.style.setProperty('--photo-center',(x+w/2)+'px '+(y+h/2)+'px');clipped.appendChild(picture);
   const water=document.createElementNS(ns,'g');water.setAttribute('class','abajMediaWater');
   for(let i=0;i<9;i++){const line=document.createElementNS(ns,'path');const yy=y+h*.66+i*8;line.setAttribute('d','M'+x+' '+yy+'q'+w*.25+' -3 '+w*.5+' 0t'+w*.5+' 0');line.setAttribute('stroke','#b9f5ff');line.setAttribute('stroke-width','1.3');line.setAttribute('fill','none');water.appendChild(line)}clipped.appendChild(water);
   const glint=document.createElementNS(ns,'rect');for(const [name,value] of Object.entries({x:x-60,y,width:120,height:h,fill:'url(#'+id+'Shine)'}))glint.setAttribute(name,String(value));glint.setAttribute('class','abajMediaGlint');clipped.appendChild(glint);svg.appendChild(clipped);
  }
  scene.appendChild(svg);
 }
 scene.appendChild(make('i','abajMediaCardGlow'));
 sprite('abajMediaPhotoBack','500 128 480 352',[545,182,390,255]);
 sprite('abajMediaPhotoFront','12 128 470 352',[51,182,389,255]);
 sprite('abajMediaCloud','20 565 470 325');
 sprite('abajMediaPlay','590 600 310 290');
 tile.insertBefore(scene,tile.firstChild);
 const image=new Image();image.onload=()=>tile.classList.add('abajMediaSceneReady');image.onerror=()=>scene.remove();image.src=atlas;
}
function apply(){
 root=document.getElementById('abajLauncher');if(!root)return;
 for(const key of Object.keys(prefs)){const tile=root.querySelector('[data-target="'+key+'"]');if(tile)tile.hidden=!prefs[key]}
 root.dataset.visible=String(root.querySelectorAll('.abajLaunchTile:not([hidden])').length);
 const media=root.querySelector('[data-target="media"]');if(media){mountMediaCard(media);media.querySelector('.abajLaunchName').textContent=t().media;media.querySelector('.abajLaunchDesc').textContent=t().desc}
 const switches=document.getElementById('abajSectionSwitches');if(switches){switches.querySelector('.settingsLabel').textContent=t().sections;for(const b of switches.querySelectorAll('[data-section]')){b.firstChild.textContent=t()[b.dataset.section];b.setAttribute('aria-checked',String(prefs[b.dataset.section]))}}
}
window.abajApplyHomeSections=apply;
function setPreference(key,value){prefs[key]=value;try{localStorage.setItem('abaj_home_sections',JSON.stringify(prefs))}catch(e){}apply()}
function init(){
 if(panel)return;
 const settings=document.querySelector('#tvSettingsModal .settingsCard');
 if(settings&&!document.getElementById('abajSectionSwitches')){
  const section=make('div');section.id='abajSectionSwitches';const heading=button(t().sections,()=>{const expanded=heading.getAttribute('aria-expanded')==='true';heading.setAttribute('aria-expanded',String(!expanded));for(const row of section.querySelectorAll('[data-section]'))row.hidden=expanded});heading.className='settingsLabel abajSectionHeading';heading.setAttribute('aria-expanded','false');heading.setAttribute('aria-controls','abajSectionOptions');section.appendChild(heading);
  for(const key of Object.keys(prefs)){const b=button(t()[key],()=>setPreference(key,!prefs[key]));b.className='abajSectionSwitch';b.dataset.section=key;b.setAttribute('role','switch');b.setAttribute('aria-checked',String(prefs[key]));const knob=make('i');knob.setAttribute('aria-hidden','true');b.appendChild(knob);b.hidden=true;section.appendChild(b)}
  settings.insertBefore(section,document.getElementById('settingsLangLabel'));
 }
 createPanel();apply();
 new MutationObserver(apply).observe(document.getElementById('tvSettingsModal'),{attributes:true,attributeFilter:['class']});
 document.addEventListener('click',e=>{if(e.target.closest('#langHyBtn,#langRuBtn,#langEnBtn'))queueMicrotask(apply)});
 window.addEventListener('storage',e=>{if(e.key==='abaj_home_sections'){try{const v=JSON.parse(e.newValue||'{}');for(const k of Object.keys(prefs))if(typeof v[k]==='boolean')prefs[k]=v[k]}catch(err){}apply()}if(e.key==='abaj_tv_lang')apply()});
}
function createPanel(){
 panel=make('section');panel.id='abajMedia';panel.hidden=true;panel.setAttribute('aria-label',t().media);
 const top=make('div','abajMediaTop');top.append(button('‹ '+t().back,()=>back()),make('h1','',t().media));
 const picker=make('input');picker.type='file';picker.accept='image/*,video/*';picker.multiple=true;picker.style.position='absolute';picker.style.width='1px';picker.style.height='1px';picker.style.opacity='0';picker.style.pointerEvents='none';
 picker.onchange=()=>{const selected=Array.from(picker.files||[]).filter(file=>/^(image|video)\//.test(file.type)||/\.(jpe?g|png|gif|webp|bmp|heic|heif|mp4|m4v|mov|webm|mkv)$/i.test(file.name));picker.value='';if(!selected.length){panel.classList.remove('abajMediaPicking');showMessage(t().error);return}panel.classList.remove('abajMediaPicking');closeViewer();for(const item of localRows)URL.revokeObjectURL(item.url);localRows=selected.map(file=>({id:secretsId(),name:file.name,kind:file.type.startsWith('video/')||/\.(mp4|m4v|mov|webm|mkv)$/i.test(file.name)?'video':'photo',url:URL.createObjectURL(file)}));loadVersion++;loading=false;source='device';trail=[];filter='all';search.value='';rows=localRows;render();openViewer(0)};
 picker.addEventListener('cancel',()=>{panel.classList.remove('abajMediaPicking');if(localRows.length){rows=localRows;openViewer(0)}else showMessage(t().error)});
 const choose=button(t().choose,()=>picker.click());choose.dataset.i18n='choose';top.firstChild.dataset.i18n='back';top.appendChild(choose);top.appendChild(picker);panel.appendChild(top);
 accounts=make('div','abajMediaAccounts');accounts.hidden=true;
 const tools=make('div','abajMediaTools');const device=button(t().device,()=>selectSource('device'));device.dataset.i18n='device';tools.appendChild(device);
 search=make('input');search.id='abajMediaSearch';search.type='search';search.placeholder=t().search;search.oninput=renderGrid;tools.appendChild(search);panel.appendChild(tools);
 tabs=make('div','abajMediaTabs');for(const key of ['all','photo','video','folders']){const b=button(t()[key],()=>{filter=key;renderGrid()});b.dataset.filter=key;tabs.appendChild(b)}panel.appendChild(tabs);
 path=make('div','abajMediaPath');panel.appendChild(path);grid=make('div','abajMediaGrid');panel.appendChild(grid);notice=make('div','abajMediaNotice');notice.setAttribute('role','status');panel.appendChild(notice);
 more=button(t().more,()=>loadFiles(true));more.hidden=true;more.dataset.i18n='more';panel.appendChild(more);
 const clear=button(t().clear,()=>{closeViewer();for(const item of localRows)URL.revokeObjectURL(item.url);localRows=[];if(source==='device'){rows=localRows;render()}});clear.dataset.localClear='';clear.dataset.i18n='clear';panel.appendChild(clear);
 viewer=make('div');viewer.id='abajMediaViewer';viewer.hidden=true;viewer.setAttribute('role','dialog');viewer.setAttribute('aria-modal','true');
 login=make('div');login.id='abajMediaLogin';login.hidden=true;login.setAttribute('role','dialog');login.setAttribute('aria-modal','true');
 panel.append(viewer,login);document.body.appendChild(panel);
}
function secretsId(){return 'local-'+Date.now()+'-'+Math.random().toString(36).slice(2)}
function translatePanel(){const s=t();panel.setAttribute('aria-label',s.media);panel.querySelector('h1').textContent=s.media;search.placeholder=s.search;for(const b of panel.querySelectorAll('[data-i18n]'))b.textContent=s[b.dataset.i18n];for(const b of tabs.children)b.textContent=s[b.dataset.filter]}
async function loadAccounts(){
 try{
  const data=await api('status');if(panel.hidden)return;accounts.replaceChildren();
  for(const provider of data.providers){const card=make('div','abajMediaAccount');card.appendChild(make('strong','',t()[provider.id]));
   if(provider.pending){card.appendChild(make('small','',provider.pending));card.appendChild(button(t().confirm,async()=>{try{await api('confirm/'+provider.id,{method:'POST'});closeLogin();selectSource(provider.id)}catch(e){notice.textContent=e.message}loadAccounts()}))}
   else if(provider.connected){card.appendChild(make('small','',provider.account));const controls=make('div');controls.append(button(t()[provider.id],()=>selectSource(provider.id)),button(t().disconnect,async()=>{try{await api('disconnect/'+provider.id,{method:'POST'});if(source===provider.id)selectSource('device');loadAccounts()}catch(e){notice.textContent=e.message}}));card.appendChild(controls)}
   else{card.appendChild(button(t().connect,()=>provider.configured?connect(provider.id):showMessage(t().notReady)));if(!provider.configured)card.appendChild(make('small','',t().notReady))}
   accounts.appendChild(card);
  }
 }catch(e){accounts.replaceChildren(make('div','abajMediaNotice',e.message))}
}
function showMessage(message){notice.textContent=message;notice.scrollIntoView({block:'nearest'})}
function selectSource(name){closeViewer();loadVersion++;loading=false;source=name;trail=[];filter='all';search.value='';rows=name==='device'?localRows:[];nextPage='';render()}
async function loadFiles(append=false){
 if(loading&&append)return;const version=++loadVersion;loading=true;more.disabled=true;notice.textContent=t().loading;
 const folder=trail.length?trail[trail.length-1].id:(source==='google'?'root':'disk:/');
 try{const data=await api('files/'+source+'?'+new URLSearchParams({folder,page:append?nextPage:''}));if(version!==loadVersion||panel.hidden)return;rows=append?rows.concat(data.items):data.items;nextPage=data.next||'';render()}
 catch(e){if(version===loadVersion){notice.replaceChildren(make('p','',e.message),button(t().retry,()=>loadFiles(append)))}}
 finally{if(version===loadVersion){loading=false;more.disabled=false}}
}
function visibleRows(){const needle=search.value.trim().toLocaleLowerCase();return rows.filter(row=>(filter==='all'||(filter==='folders'?row.kind==='folder':row.kind===filter))&&(!needle||row.name.toLocaleLowerCase().includes(needle)))}
function render(){accounts.hidden=true;path.textContent=[source==='device'?t().device:t()[source],...trail.map(x=>x.name)].join(' / ');panel.querySelector('[data-local-clear]').hidden=source!=='device'||!localRows.length;renderGrid()}
function renderGrid(){
 grid.replaceChildren();const items=visibleRows();for(const row of items){const b=button('',()=>{if(row.kind==='folder'){trail.push(row);rows=[];search.value='';render();loadFiles()}else openViewer(rows.indexOf(row))});b.className='abajMediaItem';b.title=row.name;
  if(row.kind==='photo'||row.thumbnail){const image=make('img');image.src=row.thumbnail||row.url;image.loading='lazy';image.alt='';image.onerror=()=>{image.replaceWith(make('span','abajMediaThumb','▧'))};b.appendChild(image)}else b.appendChild(make('span','abajMediaThumb',row.kind==='folder'?'▰':'▶'));
  b.appendChild(make('span','',row.name));grid.appendChild(b)}
 for(const b of tabs.children)b.setAttribute('aria-pressed',String(filter===b.dataset.filter));
 notice.textContent=items.length?'':(source==='device'&&!localRows.length?t().localHint:t().empty);more.hidden=!nextPage||source==='device';
}
function stopSlides(){clearInterval(slideshow);slideshow=0}
function closeViewer(){stopSlides();const video=viewer.querySelector('video');if(video){video.pause();video.removeAttribute('src');video.load()}viewer.hidden=true;viewer.replaceChildren();if(document.fullscreenElement===viewer)document.exitFullscreen().catch(()=>{});returnFocus?.focus({preventScroll:true})}
function viewNext(delta,photosOnly=false){const candidates=visibleRows().filter(x=>x.kind!=='folder'&&(!photosOnly||x.kind==='photo'));if(!candidates.length)return;const current=rows[viewIndex];const pos=candidates.indexOf(current);openViewer(rows.indexOf(candidates[(pos+delta+candidates.length)%candidates.length]),true)}
function openViewer(index,keepSlides=false){
 const row=rows[index];if(!row||row.kind==='folder')return;if(!keepSlides){stopSlides();returnFocus=document.activeElement}
 const old=viewer.querySelector('video');if(old){old.pause();old.removeAttribute('src');old.load()}viewer.replaceChildren();viewIndex=index;viewer.hidden=false;
 const tools=make('div','abajMediaTools');const close=button(t().close,closeViewer);tools.append(button('‹',()=>viewNext(-1)),close,button('›',()=>viewNext(1)));tools.firstChild.setAttribute('aria-label',t().previous);tools.lastChild.setAttribute('aria-label',t().next);
 const slide=button(slideshow?t().stop:t().slide,()=>{if(slideshow){stopSlides();slide.textContent=t().slide}else{viewNext(1,true);slideshow=setInterval(()=>viewNext(1,true),5000);viewer.querySelector('[data-slide]').textContent=t().stop}});slide.dataset.slide='';tools.append(slide,button(t().full,()=>{if(document.fullscreenElement)document.exitFullscreen().catch(()=>{});else viewer.requestFullscreen?.().catch(()=>{})}));viewer.appendChild(tools);
 const stage=make('div','abajMediaStage');const element=make(row.kind==='video'?'video':'img');element.src=row.url;if(row.kind==='video'){element.controls=true;element.playsInline=true;element.preload='metadata';element.onended=()=>{if(slideshow)viewNext(1,true)}}else element.alt=row.name;
 element.onerror=()=>{stage.replaceChildren(make('p','abajMediaNotice',t().unsupported))};stage.appendChild(element);viewer.appendChild(stage);const caption=make('div','',row.name);caption.id='abajMediaCaption';viewer.appendChild(caption);if(!keepSlides)close.focus();
}
async function connect(provider){
 try{const data=await api('connect/'+provider,{method:'POST'});login.replaceChildren();const card=make('div','abajMediaLoginCard');card.append(make('h2','',t()[provider]),make('p','',t().qr));const image=make('img');image.src=data.qr;image.alt='QR';card.appendChild(image);
 const open=button(t().open,()=>{if(window.Telegram?.WebApp?.openLink)window.Telegram.WebApp.openLink(data.url);else window.open(data.url,'_blank','noopener,noreferrer')});card.append(make('p'),open,make('p'),button(t().cancel,closeLogin));login.appendChild(card);login.hidden=false;open.focus();const expires=Date.now()+data.expires_in*1000;clearInterval(poll);poll=setInterval(async()=>{if(Date.now()>expires){closeLogin();showMessage(t().retry);return}await loadAccounts();if(accounts.textContent.includes(t().confirm))closeLogin()},3000)}catch(e){showMessage(e.message)}
}
function closeLogin(){clearInterval(poll);poll=0;login.hidden=true;login.replaceChildren();panel.querySelector('.abajMediaTop button')?.focus()}
function back(){if(!login.hidden){closeLogin();return true}if(!viewer.hidden){closeViewer();return true}if(trail.length){trail.pop();rows=[];search.value='';render();loadFiles();return true}close();return true}
function close(){document.body.classList.remove('abajMediaOpen');loadVersion++;loading=false;closeViewer();closeLogin();panel.hidden=true;panel.classList.remove('abajMediaPicking');window.abajLauncherHome?.();document.querySelector('#abajLauncher [data-target="media"]:not([hidden])')?.focus({preventScroll:true})}
window.abajOpenMedia=()=>{if(!panel)return;document.body.classList.add('abajMediaOpen');translatePanel();panel.hidden=false;panel.classList.add('abajMediaPicking');loadVersion++;loading=false;source='device';rows=localRows;render();panel.querySelector('input[type=file]')?.click()};
window.abajMediaBack=()=>panel&&!panel.hidden?back():false;
window.addEventListener('keydown',e=>{
 if(!panel||panel.hidden)return;const key=e.key,code=e.keyCode;const isBack=['Escape','Backspace','BrowserBack'].includes(key)||code===4;
 if(document.activeElement===search&&(!isBack||key==='Backspace'))return;
 if(isBack){e.preventDefault();e.stopImmediatePropagation();back();return}
 const delta=key==='ArrowLeft'?-1:key==='ArrowRight'?1:key==='ArrowUp'?-1:key==='ArrowDown'?1:0;
 if(!viewer.hidden&&['ArrowLeft','ArrowRight'].includes(key)&&document.activeElement?.tagName!=='VIDEO'){e.preventDefault();e.stopImmediatePropagation();viewNext(delta);return}
 const container=!login.hidden?login:!viewer.hidden?viewer:panel;
 const bs=[...container.querySelectorAll('button,input:not([type="file"]),video')].filter(b=>!b.disabled&&!b.closest('[hidden]')&&b.getClientRects().length);
 if(delta){e.preventDefault();e.stopImmediatePropagation();const active=document.activeElement;let next=null;const a=active?.getBoundingClientRect();if(a){const horizontal=key==='ArrowLeft'||key==='ArrowRight';let best=Infinity;for(const b of bs){if(b===active)continue;const r=b.getBoundingClientRect(),dx=r.left+r.width/2-a.left-a.width/2,dy=r.top+r.height/2-a.top-a.height/2;const primary=(horizontal?dx:dy)*delta,secondary=Math.abs(horizontal?dy:dx);if(primary>4){const score=primary+secondary*3;if(score<best){best=score;next=b}}}}(next||bs[0])?.focus();return}
 if(['Enter','NumpadEnter',' '].includes(key)||code===23||code===66){if(document.activeElement?.tagName==='VIDEO')return;e.preventDefault();e.stopImmediatePropagation();document.activeElement?.click()}
},true);
document.addEventListener('visibilitychange',()=>{document.documentElement.classList.toggle('abajMediaMotionPaused',document.hidden);if(document.hidden){stopSlides();viewer?.querySelector('video')?.pause()}});
if(document.readyState==='loading')document.addEventListener('DOMContentLoaded',init);else init();
})();
