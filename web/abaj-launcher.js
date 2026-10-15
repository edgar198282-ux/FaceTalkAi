/* ABAJ TV Premium Dark launcher — isolated UI layer */
(()=>{'use strict';
const css=`
#abajLauncher{position:fixed;inset:0;z-index:9000;box-sizing:border-box;overflow-y:auto;display:flex;flex-direction:column;padding:18px 28px 28px;color:#f6fbff;background:#020b18 url('/static/launcher-header-20261014.webp') center top / 100% auto no-repeat;font-family:Arial,sans-serif;overscroll-behavior:contain;scrollbar-width:none}
#abajLauncher[hidden],#abajLaunchHome[hidden]{display:none!important}
#abajLauncher::-webkit-scrollbar{display:none}
#abajLauncher *{box-sizing:border-box}
.abajLaunchTop{display:flex;align-items:flex-end;justify-content:center;flex-shrink:0;min-height:112px}
.abajLaunchBrand{font-size:clamp(46px,6vw,76px);font-weight:900;line-height:1.12;letter-spacing:1px;white-space:nowrap;color:#fff;text-shadow:0 3px 24px #00112780}
.abajLaunchBrand b{color:#08bbef}
.abajLaunchBrand{position:relative;isolation:isolate}
.abajBrandSpark{position:absolute;width:5px;height:5px;border-radius:50%;background:#fff;box-shadow:0 0 5px 2px #fff,0 0 12px 4px #63dfff,0 0 22px 7px #0af;pointer-events:none;opacity:0;animation:abajSparkBlink var(--spark-speed,2.5s) ease-in-out infinite;animation-delay:var(--spark-delay,0s)}
@keyframes abajSparkBlink{0%,12%,36%,100%{opacity:0;transform:scale(.3)}19%,25%{opacity:1;transform:scale(1.2)}29%{opacity:.45;transform:scale(.7)}}
@media(prefers-reduced-motion:reduce){.abajBrandSpark{animation:none;opacity:.65}}

.abajLaunchTitle{flex-shrink:0;text-align:center;font-size:clamp(11px,1.45vw,17px);line-height:1.5;font-weight:500;letter-spacing:4px;color:#b9e8ff;margin:12px 0 24px}
#abajLauncher[data-launch-lang="hy"] .abajLaunchTitle{max-width:100%;width:100%;padding:0 6px;white-space:normal;overflow-wrap:normal;text-align:center;letter-spacing:1px;font-size:clamp(10px,2.5vw,15px);line-height:1.35}
.abajLaunchTiles{display:grid;grid-template-columns:repeat(3,minmax(0,1fr));gap:20px;flex:1;min-height:0}
.abajLaunchTile{position:relative;isolation:isolate;overflow:hidden;min-width:0;min-height:250px;display:flex;align-items:flex-end;text-align:left;padding:24px;border-radius:24px;border:1.5px solid #55b8ed;background-color:#031020;background-image:linear-gradient(0deg,#010b19b3,transparent 42%),var(--tile-bg);background-size:cover;background-position:center;color:#fff;box-shadow:inset 0 0 0 1px #9bdbff26,0 6px 22px #0005;cursor:pointer;transition:border-color .18s,box-shadow .18s,transform .18s;-webkit-tap-highlight-color:transparent}
#abajLauncher .abajLaunchTile:after{inset:auto;animation:none;-webkit-mask:none;mask:none;z-index:0;content:'';position:absolute;right:20px;bottom:26px;width:38px;height:38px;border:1.5px solid #4ab9f0;border-radius:50%;background:radial-gradient(circle at 50% 100%,#0b355b99,#020d1ba6);box-shadow:inset 0 0 12px #1a82ba33,0 0 14px #0879b52b;pointer-events:none}
#abajLauncher .abajLaunchTile:before{content:'';position:absolute;z-index:1;right:35px;bottom:40px;width:10px;height:10px;border-top:2.5px solid #f4fbff;border-right:2.5px solid #f4fbff;transform:rotate(45deg);pointer-events:none}
.abajLaunchTile:hover{border-color:#b5eaff;box-shadow:0 0 18px #16a9ef42}
#abajLauncher .abajLaunchTile:focus-visible{outline:2px solid #b5efff!important;outline-offset:3px;border-color:#d5f5ff;box-shadow:0 0 20px #12bdff80!important}
.abajLaunchTile:active{transform:scale(.992)}
/* Lightweight animated scene accents: only composited transforms/opacity. */
.abajLaunchTile .abajSceneMotion{position:absolute;inset:0;z-index:1;overflow:hidden;pointer-events:none;border-radius:inherit}
/* Subtle camera movement of the original artwork, without duplicate figures. */
#abajLauncher .abajLaunchTile[data-target="cinema"]{animation:abajCinemaPan 22s ease-in-out infinite alternate}
#abajLauncher .abajLaunchTile[data-target="iptv"]{animation:abajIptvPan 26s ease-in-out infinite alternate}
@keyframes abajCinemaPan{from{background-position:center,49% 50%}to{background-position:center,53% 48%}}
@keyframes abajIptvPan{from{background-position:center,49% 50%}to{background-position:center,52% 51%}}
@media(prefers-reduced-motion:reduce){#abajLauncher .abajLaunchTile[data-target="cinema"],#abajLauncher .abajLaunchTile[data-target="iptv"]{animation:none!important}}
#abajLauncher[hidden] .abajLaunchTile{animation-play-state:paused!important}

.abajSceneMotion i{position:absolute;display:block;pointer-events:none}
.abajLaunchTile[data-target="cinema"] .abajSceneSun{left:35%;top:19%;width:26%;aspect-ratio:1;border-radius:50%;background:radial-gradient(circle,#fff5b34d 0%,#ffbf4440 15%,#ffb12a16 39%,transparent 69%);mix-blend-mode:screen;animation:abajSunDrift 32s ease-in-out infinite}
#abajLauncher .abajLaunchTile[data-target="cinema"].abajCinemaSceneReady{animation:none}
.abajCinemaScene{position:absolute;inset:0;width:100%;height:100%;z-index:0;pointer-events:none}
.abajCinemaScene[hidden],.abajIptvScenes[hidden]{display:none}
.abajIptvScenes{position:absolute;inset:0;width:100%;height:100%;z-index:0;pointer-events:none}
.abajCinemaSceneReady .abajSceneSun{display:none}
.abajLaunchTile[data-target="iptv"] .abajSceneWater{left:47%;top:37%;width:18%;height:17%;border-radius:50%;background:radial-gradient(ellipse,#64d9ff25,transparent 72%);mix-blend-mode:screen;animation:abajWaterSwim 9s ease-in-out infinite alternate}
/* Subtle blue TV backlight, confined to the right-side TV artwork. */
.abajLaunchTile[data-target="iptv"] .abajTvBacklight{position:absolute;z-index:2;left:45%;top:1%;width:53%;height:70%;pointer-events:none;background:radial-gradient(ellipse 70% 56% at 64% 42%,rgba(14,150,255,.35) 0%,rgba(0,100,225,.17) 49%,transparent 80%);mix-blend-mode:screen;opacity:.38;will-change:opacity;animation:abajTvBacklightBreathe 5.5s ease-in-out infinite alternate}
@keyframes abajTvBacklightBreathe{from{opacity:.18}to{opacity:.66}}
#abajLauncher[hidden] .abajTvBacklight{animation-play-state:paused}
@media(prefers-reduced-motion:reduce){.abajLaunchTile[data-target="iptv"] .abajTvBacklight{animation:none;opacity:.28}}
.abajLaunchTile .abajFootballScreen{position:absolute;left:0;top:0;width:134px;height:133px;transform-origin:0 0;pointer-events:none;z-index:0}
/* Subtle drifting cloud haze confined to the upper-left mountain picture.
   Transparent overlay: the original mountains remain visible, with no duplicate imagery. */
/* Keep the lighting layers over the artwork but behind the IPTV title. */
#abajLauncher .abajLaunchTile[data-target="iptv"] .abajSceneMotion{z-index:1;isolation:isolate}
#abajLauncher .abajLaunchTile[data-target="iptv"] .abajLaunchText{z-index:3}

.abajTransitionStage{position:fixed;inset:0;z-index:2147483647;display:block;width:100%;height:100%;touch-action:none;pointer-events:auto}
.abajLaunchTile[data-target="iptv"] .abajIptvMotionVideo{position:absolute;inset:0;width:100%;height:100%;object-fit:cover;pointer-events:none;z-index:1;border-radius:inherit}
.abajLaunchTile[data-target="iptv"].abajIptvVideoReady{background-image:linear-gradient(0deg,#010b19b3,transparent 42%),var(--tile-bg)!important}
body:not(.darkMode) #abajLauncher .abajLaunchTile[data-target="iptv"].abajIptvVideoReady .abajIptvMotionVideo{opacity:.82}
.abajLaunchTile[data-target="settings"].abajGearReady{background-image:linear-gradient(0deg,#010b19b3,transparent 42%),url('/static/launcher-settings-background.webp')!important;background-size:cover,cover!important;background-position:center,center!important}
.abajLaunchTile[data-target="settings"].abajGearReady .abajSceneMotion:before{content:'';position:absolute;inset:0;pointer-events:none;background:radial-gradient(ellipse 37% 68% at 75% 42%,#031b34e8 0%,#04203aa8 52%,transparent 100%);opacity:.42}
.abajLaunchTile[data-target="settings"].abajGearReady .abajSceneGear{display:none}
.abajLaunchTile[data-target="settings"] .abajGearForeground{display:none;position:absolute;z-index:1;left:55.34%;top:4.39%;width:35.81%;height:69.01%;background:none;pointer-events:none;transform-origin:center center}
.abajLaunchTile[data-target="settings"].abajGearReady .abajGearForeground{display:block;animation:none}
@media(prefers-reduced-motion:reduce){.abajLaunchTile[data-target="settings"].abajGearReady .abajGearForeground{animation:none!important}}
#abajLauncher[hidden] .abajGearForeground{animation-play-state:paused!important}
.abajLaunchTile[data-target="settings"] .abajSceneGear{display:block;left:51%;top:6%;width:44%;height:72%;border-radius:50%;background:conic-gradient(from 0deg,transparent 0deg,transparent 275deg,#b8ecff00 295deg,#c8edff24 316deg,transparent 340deg,transparent 360deg);mix-blend-mode:screen;opacity:.4;animation:abajGearLight 18s linear infinite}
@keyframes abajGearLight{to{transform:rotate(360deg)}}
@keyframes abajSunDrift{0%{transform:translate(-8%,20%) scale(.7);opacity:.12}25%{transform:translate(-2%,3%) scale(.95);opacity:.55}50%{transform:translate(5%,-13%) scale(1.16);opacity:.9}75%{transform:translate(10%,4%) scale(.94);opacity:.5}100%{transform:translate(14%,20%) scale(.7);opacity:.12}}
@keyframes abajWaterSwim{from{transform:translate(-25%,7%) scale(.85);opacity:.22}to{transform:translate(48%,-14%) scale(1.3);opacity:.7}}
@keyframes abajGearTurn{to{transform:rotate(360deg)}}
@media(prefers-reduced-motion:reduce){.abajSceneMotion i,.abajSceneDolphin,.abajSceneGearOverlay{animation:none!important}}

.abajLaunchText{display:flex;flex-direction:column;gap:7px;max-width:calc(100% - 48px);position:relative;z-index:2}
.abajLaunchName{font-size:clamp(28px,3.25vw,44px);font-weight:800;line-height:1.08;letter-spacing:-.7px;text-shadow:0 2px 8px #0008}
.abajLaunchDesc{font-size:clamp(13px,1.5vw,19px);line-height:1.35;font-weight:400;color:#b8ccdf;text-shadow:0 1px 5px #0009}
.abajLaunchIcon,.abajLaunchFoot{display:none}
#abajLaunchHome{position:fixed;bottom:18px;left:18px;z-index:8000;background:#041b3ae8;color:#fff;border:2px solid #12baff;border-radius:50%;width:49px;height:49px;font-size:26px;box-shadow:0 0 18px #039bff}
@media(min-width:651px){.abajLaunchTile[data-target="settings"]{background-size:cover,auto 90%;background-repeat:no-repeat;background-position:center,85% top}}
@media(max-width:650px){
#abajLauncher{height:100vh;height:100dvh;padding:0 13px max(14px,env(safe-area-inset-bottom));background-size:100% auto}
.abajLaunchTop{min-height:90px;min-height:clamp(85px,12dvh,132px)}
.abajLaunchBrand{font-size:clamp(42px,11.4vw,67px);letter-spacing:.5px}
.abajLaunchTitle{font-size:clamp(9px,2.8vw,14px);letter-spacing:clamp(1px,.5vw,2.5px);margin:9px 0 14px;white-space:nowrap}
.abajLaunchTiles{display:flex;flex-direction:column;gap:10px;flex:1 0 auto;min-height:555px}
.abajLaunchTile{flex:1.26 1 0;min-height:185px;padding:16px 20px;border-radius:18px;background-position:center}
.abajLaunchTile[data-target="settings"]{flex:1 1 0;min-height:165px}
.abajLaunchName{font-size:clamp(27px,8vw,40px)}
.abajLaunchDesc{font-size:clamp(12px,3.7vw,18px)}
.abajLaunchText{gap:6px;max-width:calc(100% - 38px)}
#abajLauncher .abajLaunchTile:after{width:34px;height:34px;right:17px;bottom:21px}
#abajLauncher .abajLaunchTile:before{right:30px;bottom:33px;width:9px;height:9px}
}
@media(max-height:620px) and (max-width:650px) and (orientation:portrait){
.abajLaunchTop{min-height:65px}.abajLaunchBrand{font-size:39px}.abajLaunchTitle{margin:5px 0 10px;font-size:9px}.abajLaunchTiles{min-height:430px;gap:8px}.abajLaunchTile{min-height:145px;padding:12px 16px}.abajLaunchTile[data-target="settings"]{min-height:124px}.abajLaunchName{font-size:26px}.abajLaunchDesc{font-size:12px}
}
@media(orientation:landscape) and (max-height:520px){
#abajLauncher{padding:8px 18px 16px}.abajLaunchTop{min-height:48px}.abajLaunchBrand{font-size:40px}.abajLaunchTitle{font-size:10px;margin:6px 0 12px}.abajLaunchTiles{display:grid;grid-template-columns:repeat(3,minmax(0,1fr));gap:12px;min-height:180px}.abajLaunchTile,.abajLaunchTile[data-target="settings"]{min-height:180px;padding:14px}.abajLaunchName{font-size:25px}.abajLaunchDesc{font-size:12px}.abajLaunchText{max-width:100%;padding-right:0}#abajLauncher .abajLaunchTile:after,#abajLauncher .abajLaunchTile:before{display:none}
}
body:not(.darkMode) #abajLauncher{color:#102b46;background-color:#edf5fc;background-size:100% 34.4vw;background-image:linear-gradient(180deg,#edf6ff80 0%,#edf5fca8 70%,#edf5fc 100%),url('/static/launcher-header-20261014.webp')}
body:not(.darkMode) #abajLauncher .abajLaunchBrand{color:#103a5c;text-shadow:0 2px 16px #ffffffb3}
body:not(.darkMode) #abajLauncher .abajLaunchBrand b{color:#008fc8}
body:not(.darkMode) #abajLauncher .abajLaunchTitle{color:#386681}
body:not(.darkMode) #abajLauncher .abajLaunchTile{color:#102b46;background-color:#f7fbff;background-image:linear-gradient(0deg,#f7fbff 0%,#f7fbfff7 26%,#f7fbff59 48%,transparent 68%),var(--tile-bg);border-color:#88bddc;box-shadow:inset 0 0 0 1px #ffffffb3,0 7px 24px #245b8226}
body:not(.darkMode) #abajLauncher .abajLaunchTile[data-target="settings"].abajGearReady{background-image:linear-gradient(0deg,#f7fbff 0%,#f7fbfff7 26%,#f7fbff59 48%,transparent 68%),url('/static/launcher-settings-background.webp')!important}
body:not(.darkMode) #abajLauncher .abajLaunchName{color:#10314d;text-shadow:0 1px 6px #ffffffb3}
body:not(.darkMode) #abajLauncher .abajLaunchDesc{color:#3e607a;text-shadow:0 1px 4px #ffffffb3}
body:not(.darkMode) #abajLauncher .abajLaunchTile:after{border-color:#58a7d2;background:linear-gradient(145deg,#ffffffed,#e0f2ffed);box-shadow:inset 0 0 0 1px #fff,0 3px 12px #25678926}
body:not(.darkMode) #abajLauncher .abajLaunchTile:before{border-color:#17608a}
body:not(.darkMode) #abajLauncher .abajLaunchTile:hover{border-color:#198fc6;box-shadow:0 7px 24px #167eb833}
body:not(.darkMode) #abajLauncher .abajLaunchTile:focus-visible{outline-color:#087fb9!important;border-color:#087fb9;box-shadow:0 0 20px #159bdb59!important}
body:not(.darkMode) #abajLaunchHome{background:#f3faff;color:#12628f;border-color:#58a7d2;box-shadow:0 3px 14px #25678926}
@media(prefers-reduced-motion:reduce){.abajLaunchTile{animation:none!important;transition:none!important}}
`;
function createFootballPainter(ctx,radius){
 const faces=[];
 const unit=v=>{const n=Math.hypot(...v);return v.map(x=>x/n)};
 const dot=(a,b)=>a.reduce((s,x,i)=>s+x*b[i],0);
 const cross=(a,b)=>[a[1]*b[2]-a[2]*b[1],a[2]*b[0]-a[0]*b[2],a[0]*b[1]-a[1]*b[0]];
 const phi=(1+Math.sqrt(5))/2,vertices=[];
 for(const a of [-1,1])for(const b of [-phi,phi])vertices.push([0,a,b],[a,b,0],[b,0,a]);
 const adjacent=vertices.map(v=>vertices.map((w,i)=>Math.abs(Math.hypot(...v.map((x,j)=>x-w[j]))-2)<.001?i:-1).filter(i=>i>=0));
 const cut=(a,b)=>unit(a.map((x,i)=>(2*x+b[i])/3));
 function face(points,black){
  const normal=unit(points.reduce((sum,p)=>sum.map((v,i)=>v+p[i]),[0,0,0]));
  const u=unit(cross(normal,Math.abs(normal[0])<.9?[1,0,0]:[0,1,0])),v=cross(normal,u);
  points.sort((a,b)=>Math.atan2(dot(a,v),dot(a,u))-Math.atan2(dot(b,v),dot(b,u)));
  const outline=[];
  points.forEach((p,i)=>{const q=points[(i+1)%points.length];for(let j=0;j<8;j++)outline.push(unit(p.map((x,k)=>x+(q[k]-x)*j/8)))});
  faces.push({outline,black});
 }
 vertices.forEach((v,i)=>face(adjacent[i].map(j=>cut(v,vertices[j])),true));
 for(let i=0;i<12;i++)for(const j of adjacent[i])for(const k of adjacent[j]){
  if(i<j&&j<k&&adjacent[k].includes(i)){
   const a=vertices[i],b=vertices[j],c=vertices[k];
   face([cut(a,b),cut(b,a),cut(b,c),cut(c,b),cut(c,a),cut(a,c)],false);
  }
 }
 function drawBall(x,y,angle){
  ctx.save();ctx.translate(x,y);ctx.scale(radius,radius);
  ctx.beginPath();ctx.arc(0,0,1,0,Math.PI*2);ctx.clip();ctx.fillStyle='#e7e7da';ctx.fillRect(-1,-1,2,2);
  const ca=Math.cos(angle),sa=Math.sin(angle),tilt=.25,ct=Math.cos(tilt),st=Math.sin(tilt);
  for(const face of faces){
   const points=face.outline.map(([x,y,z])=>{const rx=x*ca+z*sa,rz=z*ca-x*sa;return [rx,y*ct-rz*st,y*st+rz*ct]});
   const front=[];
   points.forEach((p,i)=>{
    const q=points[(i+1)%points.length];if(p[2]>=0)front.push(p);
    if((p[2]>=0)!==(q[2]>=0)){const t=p[2]/(p[2]-q[2]);front.push(unit([p[0]+t*(q[0]-p[0]),p[1]+t*(q[1]-p[1]),0]))}
   });
   if(front.length<3)continue;
   ctx.beginPath();front.forEach((p,i)=>i?ctx.lineTo(p[0],p[1]):ctx.moveTo(p[0],p[1]));ctx.closePath();
   ctx.fillStyle=face.black?'#101c20':'#e7e7da';ctx.fill();ctx.strokeStyle='#596460';ctx.lineWidth=.015;ctx.stroke();
  }
  const shade=ctx.createRadialGradient(-.35,-.45,.08,0,0,1.12);
  shade.addColorStop(0,'#ffffff55');shade.addColorStop(.48,'#ffffff00');shade.addColorStop(.85,'#09221870');shade.addColorStop(1,'#06140dd9');
  ctx.fillStyle=shade;ctx.fillRect(-1,-1,2,2);ctx.restore();
 }
 return drawBall;
}
function drawCinemaGlasses(ctx,w,h,origin,p){
 const smooth=p*p*(3-2*p),focal=Math.min(w,h)*1.65,distance=1800*Math.pow(1-p,1.7)+45;
 const cx=origin.x+(w*.5-origin.x)*smooth,cy=origin.y+(h*.5-origin.y)*smooth;
 const yaw=-.32*(1-smooth),pitch=-.16*(1-smooth),roll=-.08*(1-smooth);
 function project(x,y,z){
  const eye=Math.max(0,Math.min(1,(p-.6)/.4)),viewX=x-76*eye*eye*(3-2*eye);
  const a=viewX*Math.cos(yaw)+z*Math.sin(yaw),b=z*Math.cos(yaw)-viewX*Math.sin(yaw);
  const c=y*Math.cos(pitch)-b*Math.sin(pitch),d=y*Math.sin(pitch)+b*Math.cos(pitch);
  const rx=a*Math.cos(roll)-c*Math.sin(roll),ry=a*Math.sin(roll)+c*Math.cos(roll);
  const scale=focal/Math.max(24,distance-d);
  return [cx+rx*scale,cy+ry*scale];
 }
 function outline(center,rx,ry,z){
  const points=[];
  for(let i=0;i<64;i++){
   const angle=i*Math.PI/32,co=Math.cos(angle),si=Math.sin(angle);
   points.push(project(center+Math.sign(co)*Math.pow(Math.abs(co),.48)*rx,Math.sign(si)*Math.pow(Math.abs(si),.58)*ry,z));
  }
  return points;
 }
 function path(points){ctx.beginPath();points.forEach(([x,y],i)=>i?ctx.lineTo(x,y):ctx.moveTo(x,y));ctx.closePath()}
 function ring(outer,inner){path(outer);inner.forEach(([x,y],i)=>i?ctx.lineTo(x,y):ctx.moveTo(x,y));ctx.closePath()}
 function arm(side){
  const opening=Math.min(1,p*3),tip=side*(146+16*opening),depth=24+68*opening;
  const points=[project(side*146,-26,0),project(tip,-22,depth),project(tip-side*8,2,depth+16),project(tip-side*15,8,depth+12),project(tip-side*10,-16,depth),project(side*140,-18,0)];
  path(points);const g=ctx.createLinearGradient(points[0][0],points[0][1],points[1][0],points[1][1]);
  g.addColorStop(0,'#4a515e');g.addColorStop(.35,'#171c25');g.addColorStop(.7,'#5e6874');g.addColorStop(1,'#10151e');ctx.fillStyle=g;ctx.fill();ctx.strokeStyle='#7d87927a';ctx.lineWidth=Math.max(.5,focal/distance*.7);ctx.stroke();
 }
 ctx.save();ctx.globalAlpha=Math.min(1,p*12);arm(-1);arm(1);
 for(const center of [-76,76]){
  const outer=outline(center,71,49,0),inner=outline(center,58,37,5),back=outline(center,71,49,-9);
  ring(back,outline(center,58,37,-9));ctx.fillStyle='#04070c';ctx.fill('evenodd');
  for(let i=0;i<outer.length;i++){
   const j=(i+1)%outer.length;path([back[i],back[j],outer[j],outer[i]]);
   ctx.fillStyle=i<32?'#101722':'#434c59';ctx.fill();
  }
  ring(outer,inner);const rim=ctx.createLinearGradient(cx,cy-55*focal/distance,cx,cy+55*focal/distance);
  rim.addColorStop(0,'#727d8a');rim.addColorStop(.12,'#262d38');rim.addColorStop(.6,'#080d15');rim.addColorStop(1,'#343e4b');ctx.fillStyle=rim;ctx.fill('evenodd');
  path(inner);const left=center<0,lens=ctx.createLinearGradient(inner[20][0],inner[20][1],inner[50][0],inner[50][1]);
  lens.addColorStop(0,left?'#f6577459':'#49cfff66');lens.addColorStop(.45,left?'#b20c397d':'#0767bb80');lens.addColorStop(1,left?'#ff7b855c':'#9cecff59');ctx.fillStyle=lens;ctx.fill();
  ctx.strokeStyle=left?'#ff9ba98a':'#96e4ff99';ctx.lineWidth=Math.max(.6,focal/distance*.8);ctx.stroke();
  ctx.save();ctx.clip();const highlight=ctx.createLinearGradient(cx-w,cy-h,cx+w,cy+h);
  highlight.addColorStop(0,'#ffffff00');highlight.addColorStop(.45,'#ffffff00');highlight.addColorStop(.48,'#ffffff38');highlight.addColorStop(.51,'#ffffff06');highlight.addColorStop(1,'#ffffff00');ctx.fillStyle=highlight;ctx.fillRect(0,0,w,h);ctx.restore();
 }
 const bridge=[project(-17,-23,4),project(-10,-35,4),project(10,-35,4),project(17,-23,4),project(12,-16,6),project(6,-23,6),project(-6,-23,6),project(-12,-16,6)];
 path(bridge);ctx.fillStyle='#252d38';ctx.fill();ctx.strokeStyle='#7b8790';ctx.lineWidth=Math.max(.6,focal/distance*.65);ctx.stroke();
 ctx.restore();
 if(p>.86){
  ctx.save();ctx.globalAlpha=(p-.86)/.14*.32;
  const tint=ctx.createLinearGradient(0,0,w,0);tint.addColorStop(0,'#e92b4c');tint.addColorStop(.48,'#bd2445');tint.addColorStop(.52,'#089ed8');tint.addColorStop(1,'#37c8f2');ctx.fillStyle=tint;ctx.fillRect(0,0,w,h);ctx.restore();
 }
}

function drawLauncherGear(ctx,cx,cy,radius,angle,opening=0){
 const depth=radius*.105,yaw=-.24,pitch=.13,points=[],count=10;
 function project(x,y,z){
  const a=x*Math.cos(yaw)+z*Math.sin(yaw),b=z*Math.cos(yaw)-x*Math.sin(yaw);
  return [cx+a,cy+y*Math.cos(pitch)-b*Math.sin(pitch)];
 }
 for(let i=0;i<count;i++)for(const [fraction,r] of [[-.5,.79],[-.32,.79],[-.22,1],[.22,1],[.32,.79],[.5,.79]]){
  const a=angle+(i+fraction)*Math.PI*2/count;points.push([Math.cos(a)*radius*r,Math.sin(a)*radius*r]);
 }
 const raw=points.splice(0);
 raw.forEach((point,i)=>{
  const prev=raw[(i+raw.length-1)%raw.length],next=raw[(i+1)%raw.length],a=[(prev[0]+point[0])/2,(prev[1]+point[1])/2],b=[(next[0]+point[0])/2,(next[1]+point[1])/2];
  for(let j=0;j<4;j++){const t=j/4;points.push([a[0]*(1-t)*(1-t)+2*point[0]*t*(1-t)+b[0]*t*t,a[1]*(1-t)*(1-t)+2*point[1]*t*(1-t)+b[1]*t*t])}
 });
 const front=points.map(([x,y])=>project(x,y,depth*.5)),back=points.map(([x,y])=>project(x,y,-depth*.5));
 function contour(outline){ctx.moveTo(...outline[0]);for(let i=1;i<outline.length;i++)ctx.lineTo(...outline[i]);ctx.closePath()}
 function ring(outline,hole){ctx.beginPath();contour(outline);ctx.moveTo(cx+hole*Math.cos(yaw),cy);ctx.ellipse(cx,cy,hole*Math.cos(yaw),hole*Math.cos(pitch),0,0,Math.PI*2);ctx.closePath()}
 ctx.save();ctx.lineJoin='round';ctx.beginPath();contour(back);ctx.fillStyle='#052e4c';ctx.fill();
 for(let i=0;i<front.length;i++){
  const j=(i+1)%front.length,dx=points[j][0]-points[i][0],dy=points[j][1]-points[i][1],n=Math.hypot(dx,dy)||1,light=Math.max(0,(-dy*.7+dx*.6)/n);
  ctx.beginPath();ctx.moveTo(...back[i]);ctx.lineTo(...back[j]);ctx.lineTo(...front[j]);ctx.lineTo(...front[i]);ctx.closePath();
  ctx.fillStyle='rgb('+Math.round(16+light*65)+','+Math.round(42+light*110)+','+Math.round(65+light*145)+')';ctx.fill();
 }
 const hole=radius*(.48+opening*.24);ring(front,hole);
 const steel=ctx.createLinearGradient(cx-radius,cy-radius,cx+radius,cy+radius);
 steel.addColorStop(0,'#c1d2e1');steel.addColorStop(.17,'#71899f');steel.addColorStop(.3,'#e0e9ef');steel.addColorStop(.43,'#788fa5');steel.addColorStop(.58,'#253d54');steel.addColorStop(.76,'#66849e');steel.addColorStop(1,'#152d43');ctx.fillStyle=steel;ctx.fill('evenodd');
 ctx.save();ctx.clip('evenodd');
 for(let i=0;i<110;i++){
  const r=radius*(.47+i*.0049);ctx.beginPath();ctx.ellipse(cx,cy,r*Math.cos(yaw),r*Math.cos(pitch),0,0,Math.PI*2);
  ctx.strokeStyle=i%3===0?'#e4f1ff24':'#03132426';ctx.lineWidth=Math.max(.35,radius*.0014);ctx.stroke();
 }
 const glint=ctx.createLinearGradient(cx-radius,cy-radius,cx+radius,cy+radius);
 glint.addColorStop(0,'#ffffff00');glint.addColorStop(.24,'#ffffff00');glint.addColorStop(.32,'#f6fbff58');glint.addColorStop(.4,'#ffffff00');glint.addColorStop(1,'#ffffff00');ctx.fillStyle=glint;ctx.fillRect(cx-radius*1.2,cy-radius*1.2,radius*2.4,radius*2.4);ctx.restore();
 ctx.beginPath();contour(front);ctx.strokeStyle='#d1edff99';ctx.lineWidth=Math.max(.8,radius*.005);ctx.stroke();
 const hub=radius*.48;ctx.beginPath();ctx.ellipse(cx,cy,hub*Math.cos(yaw),hub*Math.cos(pitch),0,0,Math.PI*2);ctx.strokeStyle='#020d19';ctx.lineWidth=radius*.025;ctx.stroke();
 if(opening<1){
  ctx.save();ctx.globalAlpha=1-opening;
  const bearing=ctx.createRadialGradient(cx-radius*.14,cy-radius*.17,radius*.03,cx,cy,hub);
  bearing.addColorStop(0,'#8da9bc');bearing.addColorStop(.45,'#31485c');bearing.addColorStop(.61,'#071321');bearing.addColorStop(.84,'#0b1826');bearing.addColorStop(1,'#738da0');
  ctx.beginPath();ctx.ellipse(cx,cy,hub*Math.cos(yaw),hub*Math.cos(pitch),0,0,Math.PI*2);ctx.fillStyle=bearing;ctx.fill();
  ctx.beginPath();ctx.ellipse(cx,cy,radius*.29*Math.cos(yaw),radius*.29*Math.cos(pitch),0,0,Math.PI*2);ctx.fillStyle=steel;ctx.fill();ctx.strokeStyle='#b9d9ee99';ctx.lineWidth=radius*.008;ctx.stroke();
  ctx.beginPath();ctx.ellipse(cx,cy,radius*.245*Math.cos(yaw),radius*.245*Math.cos(pitch),0,0,Math.PI*2);
  const cap=ctx.createLinearGradient(cx,cy-radius*.24,cx,cy+radius*.24);cap.addColorStop(0,'#20394f');cap.addColorStop(1,'#061422');ctx.fillStyle=cap;ctx.fill();ctx.strokeStyle='#020b16';ctx.lineWidth=radius*.014;ctx.stroke();ctx.restore();
 }
 ctx.restore();
}
function createSettingsGear(tile,root){
 const gear=document.createElement('canvas'),ctx=gear.getContext('2d');if(!ctx)return null;
 gear.className='abajGearForeground';gear.setAttribute('aria-hidden','true');gear.width=550;gear.height=555;
 const reduced=window.matchMedia('(prefers-reduced-motion: reduce)');
 let frame=0,last=0,elapsed=0,painted=0,visible=true,suspended=false,departing=false;
 function align(){
  const w=tile.clientWidth,h=tile.clientHeight;if(!w||!h)return;
  const scale=Math.max(w/1536,h/797),ox=(w-1536*scale)/2,oy=(h-797*scale)/2;
  gear.style.left=(ox+850*scale)+'px';gear.style.top=(oy+35*scale)+'px';gear.style.width=(550*scale)+'px';gear.style.height=(555*scale)+'px';
 }
 function draw(){ctx.clearRect(0,0,550,555);drawLauncherGear(ctx,275,277.5,245,elapsed/18000*Math.PI*2)}
 function active(){return visible&&!suspended&&!departing&&!root.hidden&&!document.hidden&&root.isConnected}
 function tick(now){frame=0;if(!active()){last=0;return}if(last)elapsed+=Math.min(80,now-last);last=now;if(now-painted>=32){draw();painted=now}frame=requestAnimationFrame(tick)}
 function sync(){if(frame)cancelAnimationFrame(frame);frame=0;last=0;align();if(!departing)draw();if(active()&&!reduced.matches)frame=requestAnimationFrame(tick)}
 const background=new Image();background.onload=()=>{
  if(background.naturalWidth!==1536||background.naturalHeight!==797||!tile.isConnected)return;
  tile.insertBefore(gear,tile.querySelector('.abajLaunchText'));tile.classList.add('abajGearReady');sync();
 };
 background.src='/static/launcher-settings-background.webp';
 new MutationObserver(sync).observe(root,{attributes:true,attributeFilter:['hidden']});
 if(typeof ResizeObserver!=='undefined')new ResizeObserver(sync).observe(tile);else window.addEventListener('resize',sync,{passive:true});
 if(typeof IntersectionObserver!=='undefined')new IntersectionObserver(entries=>{visible=entries[0].isIntersecting;sync()}).observe(tile);
 document.addEventListener('visibilitychange',sync);window.addEventListener('pagehide',()=>{suspended=true;sync()});window.addEventListener('pageshow',()=>{suspended=false;sync()});
 if(reduced.addEventListener)reduced.addEventListener('change',sync);else reduced.addListener(sync);
 return {
  takeOff(){const rect=gear.getBoundingClientRect();if(!rect.width)return null;departing=true;sync();gear.style.visibility='hidden';return{x:rect.left+rect.width*.5,y:rect.top+rect.height*.5,radius:rect.width*245/550,angle:elapsed/18000*Math.PI*2}},
  reset(){departing=false;gear.style.visibility='';sync()}
 };
}

function createFootballScreen(tile,root){
 const canvas=document.createElement('canvas'),ctx=canvas.getContext('2d');
 if(!ctx)return null;
 canvas.className='abajFootballScreen';canvas.setAttribute('aria-hidden','true');
 canvas.width=268;canvas.height=266;
 const clean=new Image(),reduced=window.matchMedia('(prefers-reduced-motion: reduce)');
 let ready=false,visible=true,suspended=false,departing=false,frame=0,last=0,elapsed=0;
 let width=0,height=0,scale=1,offsetX=0,offsetY=0,ballX=486,ballY=147;
 const radius=19,drawBall=createFootballPainter(ctx,radius);
 function align(){
  const style=getComputedStyle(tile),position=style.backgroundPosition.split(',').pop().trim().split(/\s+/);
  width=tile.clientWidth;height=tile.clientHeight;if(!width||!height)return false;
  scale=Math.max(width/786,height/510);
  offsetX=(width-786*scale)*(parseFloat(position[0])/100);
  offsetY=(height-510*scale)*(parseFloat(position[1])/100);
  canvas.style.transform='translate('+(offsetX+452*scale)+'px,'+(offsetY+60*scale)+'px) scale('+scale+')';
  return true;
 }
 function draw(){
  if(!ready||!align())return;
  const phase=elapsed/7200*Math.PI*2,bounce=7*Math.pow(Math.sin(phase*3),2);
  const left=Math.max(486,-offsetX/scale+radius+4),right=Math.min(554,(width-offsetX)/scale-radius-4);
  ballX=left+(right-left)*(1-Math.cos(phase))/2;ballY=147-bounce;
  ctx.setTransform(2,0,0,2,0,0);ctx.clearRect(0,0,134,133);ctx.save();
  // Measured inside corners in the original 786 x 510 photograph.
  ctx.beginPath();ctx.moveTo(2,16);ctx.lineTo(132,1);ctx.lineTo(132,126);ctx.lineTo(2,130);ctx.closePath();ctx.clip();
  ctx.drawImage(clean,0,0);
  if(!departing){
   ctx.save();ctx.translate(ballX-452,106);ctx.scale(1, .23);
   const shadow=ctx.createRadialGradient(0,0,0,0,0,radius+5);
   shadow.addColorStop(0,'rgba(7,18,5,'+(.5-bounce*.025)+')');shadow.addColorStop(1,'rgba(7,18,5,0)');
   ctx.fillStyle=shadow;ctx.fillRect(-24,-24,48,48);ctx.restore();
   drawBall(ballX-452,ballY-60,-(ballX-486)/radius);
  }
  // Match the existing card gradient, including the light theme and cover crop.
  const gradient=ctx.createLinearGradient(0,-offsetY/scale-60,0,(height-offsetY)/scale-60);
  if(document.body.classList.contains('darkMode')){
   gradient.addColorStop(0,'#010b1900');gradient.addColorStop(.58,'#010b1900');gradient.addColorStop(1,'#010b19b3');
  }else{
   gradient.addColorStop(0,'#f7fbff00');gradient.addColorStop(.32,'#f7fbff00');gradient.addColorStop(.52,'#f7fbff59');gradient.addColorStop(.74,'#f7fbfff7');gradient.addColorStop(1,'#f7fbff');
  }
  ctx.fillStyle=gradient;ctx.fillRect(0,0,134,133);ctx.restore();
 }
 function active(){return ready&&visible&&!suspended&&!root.hidden&&!document.hidden&&root.isConnected}
 function tick(now){
  frame=0;if(!active()){last=0;return}
  if(last&&!departing&&!reduced.matches)elapsed+=Math.min(now-last,80);
  last=now;draw();
  if(!reduced.matches)frame=requestAnimationFrame(tick);
 }
 function sync(){
  if(frame)cancelAnimationFrame(frame);frame=0;last=0;
  if(active()){draw();if(!reduced.matches)frame=requestAnimationFrame(tick)}
 }
 clean.onload=()=>{
  if(clean.naturalWidth!==134||clean.naturalHeight!==133||!tile.isConnected)return;
  ready=true;tile.insertBefore(canvas,tile.firstChild);sync();
 };
 clean.src='/static/launcher-football-clean-20261015.png';
 new MutationObserver(sync).observe(root,{attributes:true,attributeFilter:['hidden']});
 new MutationObserver(()=>{if(active())draw()}).observe(document.body,{attributes:true,attributeFilter:['class']});
 if(typeof IntersectionObserver!=='undefined')new IntersectionObserver(entries=>{visible=entries[0].isIntersecting;sync()}).observe(tile);
 if(typeof ResizeObserver!=='undefined')new ResizeObserver(sync).observe(tile);
 else window.addEventListener('resize',sync,{passive:true});
 document.addEventListener('visibilitychange',sync);
 window.addEventListener('pagehide',()=>{suspended=true;sync()});
 window.addEventListener('pageshow',()=>{suspended=false;sync()});
 if(reduced.addEventListener)reduced.addEventListener('change',sync);else reduced.addListener(sync);
 return {
  takeOff(){
   if(!ready)return null;
   draw();const rect=tile.getBoundingClientRect();departing=true;draw();
   return {x:rect.left+tile.clientLeft+offsetX+ballX*scale,y:rect.top+tile.clientTop+offsetY+ballY*scale,radius:radius*scale,angle:-(ballX-486)/radius};
  },
  reset(){departing=false;sync()}
 };
}
function createIptvScenes(tile,root){
 const canvas=document.createElement('canvas'),ctx=canvas.getContext('2d');
 if(!ctx)return;
 canvas.className='abajIptvScenes';canvas.setAttribute('aria-hidden','true');
 const artwork=new Image(),reduced=window.matchMedia('(prefers-reduced-motion: reduce)');
 let ready=false,visible=true,suspended=false,frame=0,last=0,painted=0,elapsed=0;
 const panels=[
  {type:'lake',box:[294,76,153,119],corners:[294,94,447,76,447,191,294,195]},
  {type:'concert',box:[294,202,92,87],corners:[294,204,386,202,386,288,294,287]},
  {type:'dolphin',box:[394,198,98,94],corners:[394,201,492,198,492,291,394,289]},
  {type:'city',box:[500,197,109,100],corners:[500,199,609,197,609,296,500,293]},
  {type:'lion',box:[619,195,67,105],corners:[619,196,686,195,686,300,619,297]},
  {type:'forest',box:[696,192,44,110],corners:[696,194,740,192,740,302,696,300]},
  {type:'news',box:[593,44,147,142],corners:[593,63,740,44,740,181,593,186]}
 ];
 function clipPanel(p){
  ctx.beginPath();for(let i=0;i<8;i+=2)i?ctx.lineTo(p.corners[i],p.corners[i+1]):ctx.moveTo(p.corners[i],p.corners[i+1]);ctx.closePath();ctx.clip();
 }
 function displacement(type,x,y,t){
  if(type==='dolphin'){
   const weight=Math.exp(-Math.pow((x-441)/37,4)-Math.pow((y-244)/32,4));
   return [weight*(2.7*Math.sin(t*1.25)+1.7*Math.sin(t*2.5+(x-400)*.065)),weight*(-2.5*Math.sin(t*1.25)+1.8*Math.sin(t*2.5+(x-400)*.075))];
  }
  if(type==='lion'){
   const weight=Math.exp(-Math.pow((x-652)/25,4)-Math.pow((y-250)/42,4));
   return [weight*1.35*Math.sin(t*.85),weight*(.65*Math.sin(t*1.8)+(y-249)*.015*Math.sin(t*1.8))];
  }
  if(type==='forest')return [1.8*Math.sin(t*1.5+y*.075)*Math.max(0,1-(y-192)/65),.6*Math.sin(t+y*.06)];
  return [.75*Math.sin(t*2.1+y*1.1)*Math.max(0,(y-168)/27),.3*Math.sin(t*1.8+x*.16)*Math.max(0,(y-168)/27)];
 }
 function mesh(p,t){
  const [x0,y0,w,h]=p.box,n=6,points=[];
  for(let j=0;j<=n;j++)for(let i=0;i<=n;i++){
   const x=x0+w*i/n,y=y0+h*j/n,edge=Math.sin(Math.PI*i/n)*Math.sin(Math.PI*j/n),d=displacement(p.type,x,y,t);
   points.push([x,y,x+d[0]*edge,y+d[1]*edge]);
  }
  function triangle(a,b,c){
   const sx1=b[0]-a[0],sy1=b[1]-a[1],sx2=c[0]-a[0],sy2=c[1]-a[1],det=sx1*sy2-sx2*sy1;
   const dx1=b[2]-a[2],dy1=b[3]-a[3],dx2=c[2]-a[2],dy2=c[3]-a[3];
   const m0=(dx1*sy2-dx2*sy1)/det,m1=(dy1*sy2-dy2*sy1)/det,m2=(dx2*sx1-dx1*sx2)/det,m3=(dy2*sx1-dy1*sx2)/det;
   ctx.save();ctx.beginPath();ctx.moveTo(a[2],a[3]);ctx.lineTo(b[2],b[3]);ctx.lineTo(c[2],c[3]);ctx.closePath();ctx.clip();
   ctx.transform(m0,m1,m2,m3,a[2]-m0*a[0]-m2*a[1],a[3]-m1*a[0]-m3*a[1]);ctx.drawImage(artwork,0,0);ctx.restore();
  }
  for(let j=0;j<n;j++)for(let i=0;i<n;i++){
   const a=points[j*(n+1)+i],b=points[j*(n+1)+i+1],c=points[(j+1)*(n+1)+i],d=points[(j+1)*(n+1)+i+1];
   triangle(a,b,c);triangle(b,d,c);
  }
 }
 function draw(){
  const w=tile.clientWidth,h=tile.clientHeight;if(!ready||!w||!h)return;
  const dpr=Math.min(window.devicePixelRatio||1,2),scale=Math.max(w/786,h/510);
  if(canvas.width!==Math.round(w*dpr)||canvas.height!==Math.round(h*dpr)){canvas.width=Math.round(w*dpr);canvas.height=Math.round(h*dpr)}
  const pos=getComputedStyle(tile).backgroundPosition.split(',').pop().trim().split(/\s+/),ox=(w-786*scale)*parseFloat(pos[0])/100,oy=(h-510*scale)*parseFloat(pos[1])/100,t=elapsed/1000;
  ctx.setTransform(dpr,0,0,dpr,0,0);ctx.clearRect(0,0,w,h);ctx.save();ctx.translate(ox,oy);ctx.scale(scale,scale);
  for(const p of panels){
   ctx.save();clipPanel(p);
   if(['lake','dolphin','lion','forest'].includes(p.type))mesh(p,t);else ctx.drawImage(artwork,0,0);
   if(p.type==='lion'){
    const phase=t%5.7,blink=Math.max(0,1-Math.abs(phase-4.8)/.14);
    if(blink>0){
     const dx=1.2*Math.sin(t*.85),dy=.6*Math.sin(t*1.8);
     ctx.strokeStyle='#b68148';ctx.lineWidth=3.6*blink;ctx.lineCap='round';
     for(const x of [649,665]){ctx.beginPath();ctx.moveTo(x-2.6+dx,240+dy);ctx.quadraticCurveTo(x+dx,241+dy,x+2.5+dx,240+dy);ctx.stroke()}
    }
   }
   if(p.type==='dolphin'){
    ctx.fillStyle='#b9f4ff';
    for(let i=0;i<7;i++){
     const phase=(t*.12+i*.143)%1,x=400+i*13+1.4*Math.sin(t+i),y=292-phase*92;
     ctx.globalAlpha=Math.sin(phase*Math.PI)*.3;ctx.beginPath();ctx.arc(x,y,.7+(i%3)*.35,0,Math.PI*2);ctx.fill();
    }
    ctx.globalAlpha=1;
   }
   if(p.type==='concert'){
    ctx.globalCompositeOperation='screen';
    for(let i=0;i<3;i++){
     const x=335+Math.sin(t*.8+i*2)*34,g=ctx.createLinearGradient(335,258,x,204);
     g.addColorStop(0,'#9deaff00');g.addColorStop(1,['#b640ff90','#40ceff90','#ffa64680'][i]);
     ctx.fillStyle=g;ctx.beginPath();ctx.moveTo(335,258);ctx.lineTo(x-4,202);ctx.lineTo(x+5,202);ctx.closePath();ctx.fill();
    }
   }
   if(p.type==='city'||p.type==='news'){
    ctx.globalCompositeOperation='screen';
    const count=p.type==='city'?12:6;
    for(let i=0;i<count;i++){
     const x=p.type==='city'?505+(i*17)%99:600+(i*29)%130,y=p.type==='city'?238+(i*13)%45:70+(i*31)%94;
     if(p.type==='news'&&x>621&&x<700)continue;
     ctx.globalAlpha=.15+.35*(1+Math.sin(t*(.8+i*.11)+i*2))/2;ctx.fillStyle=p.type==='city'?'#ffd17c':'#41aaff';ctx.fillRect(x,y,1.3,2.4);
    }
   }
   ctx.restore();
  }
  ctx.restore();
  ctx.globalCompositeOperation='source-atop';const gradient=ctx.createLinearGradient(0,0,0,h);
  if(document.body.classList.contains('darkMode')){
   gradient.addColorStop(0,'#010b1900');gradient.addColorStop(.58,'#010b1900');gradient.addColorStop(1,'#010b19b3');
  }else{
   gradient.addColorStop(0,'#f7fbff00');gradient.addColorStop(.32,'#f7fbff00');gradient.addColorStop(.52,'#f7fbff59');gradient.addColorStop(.74,'#f7fbfff7');gradient.addColorStop(1,'#f7fbff');
  }
  ctx.fillStyle=gradient;ctx.fillRect(0,0,w,h);ctx.globalCompositeOperation='source-over';
 }
 function active(){return ready&&visible&&!suspended&&!root.hidden&&!document.hidden&&root.isConnected&&!reduced.matches}
 function tick(now){
  frame=0;if(!active()){last=0;return}
  if(last)elapsed+=Math.min(now-last,80);last=now;
  if(now-painted>=32){draw();painted=now}frame=requestAnimationFrame(tick);
 }
 function sync(){
  if(frame)cancelAnimationFrame(frame);frame=0;last=0;painted=0;canvas.hidden=reduced.matches;
  if(active()){draw();frame=requestAnimationFrame(tick)}
 }
 artwork.onload=()=>{
  if(artwork.naturalWidth!==786||artwork.naturalHeight!==510||!tile.isConnected)return;
  ready=true;tile.insertBefore(canvas,tile.firstChild);sync();
 };
 artwork.src='/static/launcher-iptv-20261014.webp';
 new MutationObserver(sync).observe(root,{attributes:true,attributeFilter:['hidden']});
 new MutationObserver(()=>{if(active())draw()}).observe(document.body,{attributes:true,attributeFilter:['class']});
 if(typeof ResizeObserver!=='undefined')new ResizeObserver(sync).observe(tile);else window.addEventListener('resize',sync,{passive:true});
 if(typeof IntersectionObserver!=='undefined')new IntersectionObserver(entries=>{visible=entries[0].isIntersecting;sync()}).observe(tile);
 document.addEventListener('visibilitychange',sync);
 window.addEventListener('pagehide',()=>{suspended=true;sync()});window.addEventListener('pageshow',()=>{suspended=false;sync()});
 if(reduced.addEventListener)reduced.addEventListener('change',sync);else reduced.addListener(sync);
}

function createCinemaScene(tile,root){
 const canvas=document.createElement('canvas'),ctx=canvas.getContext('2d');
 if(!ctx)return;
 canvas.className='abajCinemaScene';canvas.setAttribute('aria-hidden','true');
 const artwork=new Image(),reduced=window.matchMedia('(prefers-reduced-motion: reduce)');
 const sky=document.createElement('canvas'),skyCtx=sky.getContext('2d'),clouds=document.createElement('canvas'),cloudCtx=clouds.getContext('2d');
 if(!skyCtx||!cloudCtx)return;
 const ridge=new Path2D('M0 0H630V108L616 103 603 114 590 97 578 91 564 108 553 116 543 108 532 119 517 112 501 124 483 119 464 113 444 100 430 114 417 119 405 126 391 123 377 135 360 132 346 140 327 137 312 136 302 129 290 132 275 129 263 133 248 122 234 130 221 123 208 117 194 108 184 119 170 116 157 125 144 117 132 116 120 103 110 108 99 94 86 70 76 80 65 84 53 91 42 86 28 97 13 92 0 106Z');
 let ready=false,visible=true,suspended=false,frame=0,last=0,elapsed=0,w=0,h=0,dpr=1;
 const kernels=[[582,195,11,10],[602,191,12,11],[629,185,11,11],[644,190,12,11],[660,193,11,10],[679,196,11,10]].map(([x,y,kw,kh],i)=>({x,y,w:kw,h:kh,period:2.2+i*.19,delay:i*.37}));
 const film=document.createElement('canvas'),filmCtx=film.getContext('2d');
 const filmBands=[
  [[456,302,329],[476,304,334],[506,310,341],[531,316,347]],
  [[545,316,347],[579,321,352],[619,327,358],[655,333,363],[672,337,365]]
 ];
 function drawFilm(t){
  if(!filmCtx)return;
  for(const band of filmBands){
   ctx.save();ctx.beginPath();
   band.forEach(([x,top],i)=>i?ctx.lineTo(x,top):ctx.moveTo(x,top));
   for(let i=band.length-1;i>=0;i--)ctx.lineTo(band[i][0],band[i][2]);
   ctx.closePath();ctx.clip();ctx.globalAlpha=.78;
   for(let i=0;i<band.length-1;i++){
    const [x0,top0,bottom0]=band[i],[x1,top1,bottom1]=band[i+1];
    for(let x=x0;x<x1;x++){
     const p=(x-x0)/(x1-x0),top=top0+(top1-top0)*p,bottom=bottom0+(bottom1-bottom0)*p;
     const u=((x+t*17)%film.width+film.width)%film.width;
     ctx.save();ctx.transform(1,(top1-top0)/(x1-x0),0,(bottom-top)/32,x,top);
     ctx.drawImage(film,Math.floor(u),0,1,32,0,0,1.15,32);ctx.restore();
    }
   }
   ctx.globalAlpha=1;
   const sheen=ctx.createLinearGradient(band[0][0],0,band[band.length-1][0],0);
   sheen.addColorStop(0,'#ffc47532');sheen.addColorStop(.25,'#00000020');sheen.addColorStop(1,'#00000070');
   ctx.fillStyle=sheen;ctx.fill();ctx.restore();
  }
 }
 function align(){
  w=tile.clientWidth;h=tile.clientHeight;if(!w||!h)return false;
  dpr=Math.min(window.devicePixelRatio||1,2);
  if(canvas.width!==Math.round(w*dpr)||canvas.height!==Math.round(h*dpr)){
   canvas.width=Math.round(w*dpr);canvas.height=Math.round(h*dpr);
  }
  return true;
 }
 function draw(){
  if(!ready||!align())return;
  const t=elapsed/1000,scale=Math.max(w/786,h/506),ox=(w-786*scale)/2,oy=(h-506*scale)/2;
  ctx.setTransform(dpr,0,0,dpr,0,0);ctx.clearRect(0,0,w,h);
  ctx.save();ctx.translate(ox,oy);ctx.scale(scale,scale);ctx.drawImage(artwork,0,0);
  ctx.save();ctx.clip(ridge);
  ctx.drawImage(sky,0,0);
  // Fade the moving cloud band into the fixed horizon, below the clouds.
  ctx.save();
  const drift=22*Math.sin(t*Math.PI*2/26);
  ctx.drawImage(clouds,drift-630,0);ctx.drawImage(clouds,drift,0);ctx.drawImage(clouds,drift+630,0);
  ctx.restore();
  const sunY=132-24*Math.cos(t*Math.PI*2/14),strength=(1+Math.cos(t*Math.PI*2/14))/2;
  const glow=ctx.createRadialGradient(325,sunY,2,325,sunY,48);
  glow.addColorStop(0,'rgba(255,247,171,.95)');glow.addColorStop(.22,'rgba(255,211,87,.62)');glow.addColorStop(1,'rgba(255,165,42,0)');
  ctx.globalAlpha=.5+strength*.5;ctx.fillStyle=glow;ctx.fillRect(277,sunY-48,96,96);
  ctx.beginPath();ctx.arc(325,sunY,8.5,0,Math.PI*2);ctx.fillStyle='#fffbd3';ctx.fill();ctx.restore();
  drawFilm(t);
  for(const k of kernels){
   const phase=((t+k.delay)%k.period)/k.period;
   if(phase>.58)continue;
   const flight=phase/.58,lift=Math.sin(flight*Math.PI)*(16+k.delay*6),dx=Math.sin(flight*Math.PI*2)*(2+k.delay);
   ctx.save();ctx.translate(k.x+dx,k.y-lift);ctx.rotate(Math.sin(flight*Math.PI)*(k.delay-.8)*.6);
   ctx.beginPath();ctx.moveTo(-k.w*.48,k.h*.22);ctx.lineTo(-k.w*.5,-k.h*.16);ctx.lineTo(-k.w*.24,-k.h*.48);ctx.lineTo(k.w*.12,-k.h*.5);ctx.lineTo(k.w*.47,-k.h*.18);ctx.lineTo(k.w*.45,k.h*.25);ctx.lineTo(k.w*.12,k.h*.48);ctx.lineTo(-k.w*.25,k.h*.42);ctx.closePath();ctx.clip();
   ctx.drawImage(k.sprite,-k.w/2,-k.h/2);ctx.restore();
  }
  ctx.restore();
  const gradient=ctx.createLinearGradient(0,0,0,h);
  if(document.body.classList.contains('darkMode')){
   gradient.addColorStop(0,'#010b1900');gradient.addColorStop(.58,'#010b1900');gradient.addColorStop(1,'#010b19b3');
  }else{
   gradient.addColorStop(0,'#f7fbff00');gradient.addColorStop(.32,'#f7fbff00');gradient.addColorStop(.52,'#f7fbff59');gradient.addColorStop(.74,'#f7fbfff7');gradient.addColorStop(1,'#f7fbff');
  }
  ctx.fillStyle=gradient;ctx.fillRect(0,0,w,h);
 }
 function active(){return ready&&visible&&!suspended&&!root.hidden&&!document.hidden&&root.isConnected}
 function tick(now){
  frame=0;if(!active()){last=0;return}
  if(last)elapsed+=Math.min(now-last,80);last=now;draw();frame=requestAnimationFrame(tick);
 }
 function sync(){
  if(frame)cancelAnimationFrame(frame);frame=0;last=0;
  canvas.hidden=reduced.matches;
  if(active()&&!reduced.matches){draw();frame=requestAnimationFrame(tick)}
 }
 artwork.onload=()=>{
  if(artwork.naturalWidth!==786||artwork.naturalHeight!==506||!tile.isConnected)return;
  sky.width=630;sky.height=150;skyCtx.drawImage(artwork,0,0);
  // Replace the photographed sun once; the moving disk is clipped by the mountain ridge.
  const pixels=skyCtx.getImageData(0,0,630,150),data=pixels.data;
  for(let y=103;y<150;y++)for(let x=295;x<357;x++){
   const blend=Math.min(1,(x-295)/9,(357-x)/9,Math.max(0,(y-103)/7));
   for(let c=0;c<3;c++){
    const left=data[(y*630+285)*4+c],right=data[(y*630+365)*4+c],p=(y*630+x)*4+c;
    data[p]=data[p]*(1-blend)+(left+(right-left)*(x-285)/80)*blend;
   }
  }
  skyCtx.putImageData(pixels,0,0);
  clouds.width=630;clouds.height=110;cloudCtx.drawImage(sky,0,0);
  const fade=cloudCtx.createLinearGradient(0,65,0,110);
  fade.addColorStop(0,'#fff');fade.addColorStop(1,'#fff0');
  cloudCtx.globalCompositeOperation='destination-in';cloudCtx.fillStyle=fade;cloudCtx.fillRect(0,0,630,110);
  const edges=cloudCtx.createLinearGradient(0,0,630,0);
  edges.addColorStop(0,'#fff0');edges.addColorStop(.05,'#fff');edges.addColorStop(.95,'#fff');edges.addColorStop(1,'#fff0');
  cloudCtx.fillStyle=edges;cloudCtx.fillRect(0,0,630,110);
  const cloudMask=document.createElement('canvas');cloudMask.width=630;cloudMask.height=110;
  const maskCtx=cloudMask.getContext('2d');maskCtx.translate(0,-32);maskCtx.fillStyle='#fff';maskCtx.fill(ridge);
  cloudCtx.drawImage(cloudMask,0,0);
  for(const k of kernels){
   k.sprite=document.createElement('canvas');k.sprite.width=k.w;k.sprite.height=k.h;
   const c=k.sprite.getContext('2d');c.drawImage(artwork,k.x-k.w/2,k.y-k.h/2,k.w,k.h,0,0,k.w,k.h);
   const pixels=c.getImageData(0,0,k.w,k.h),rgba=pixels.data;
   for(let i=0;i<rgba.length;i+=4)rgba[i+3]*=Math.max(0,Math.min(1,(rgba[i]-75)/45,(rgba[i+1]-42)/28,(rgba[i]-rgba[i+2]-20)/25));
   c.putImageData(pixels,0,0);
  }
  if(filmCtx){
   const shots=[[0,65,220,150],[230,70,180,120],[55,190,230,153],[340,90,220,146],[240,200,180,120],[560,145,150,100]];
   film.width=shots.length*48;film.height=32;filmCtx.fillStyle='#090c10';filmCtx.fillRect(0,0,film.width,32);
   shots.forEach(([x,y,w,h],i)=>filmCtx.drawImage(artwork,x,y,w,h,i*48+2,0,44,32));
  }
  ready=true;tile.insertBefore(canvas,tile.firstChild);tile.classList.add('abajCinemaSceneReady');sync();
 };
 artwork.src='/static/launcher-cinema-20261014.webp';
 new MutationObserver(sync).observe(root,{attributes:true,attributeFilter:['hidden']});
 new MutationObserver(()=>{if(active()&&!reduced.matches)draw()}).observe(document.body,{attributes:true,attributeFilter:['class']});
 if(typeof ResizeObserver!=='undefined')new ResizeObserver(sync).observe(tile);
 else window.addEventListener('resize',sync,{passive:true});
 if(typeof IntersectionObserver!=='undefined')new IntersectionObserver(entries=>{visible=entries[0].isIntersecting;sync()}).observe(tile);
 document.addEventListener('visibilitychange',sync);
 window.addEventListener('pagehide',()=>{suspended=true;sync()});window.addEventListener('pageshow',()=>{suspended=false;sync()});
 if(reduced.addEventListener)reduced.addEventListener('change',sync);else reduced.addListener(sync);
}

function start(){
if(document.getElementById('abajLauncher'))return;
const style=document.createElement('style');style.textContent=css;document.head.appendChild(style);
const root=document.createElement('section');root.id='abajLauncher';root.setAttribute('aria-label','ABAJ TV — главная');root.innerHTML=`<div class="abajLaunchTop"><div class="abajLaunchBrand">ABAJ<b>TV</b></div></div><div class="abajLaunchTitle">ВАШ МИР КИНО И ТЕЛЕВИДЕНИЯ</div><div class="abajLaunchTiles"><button class="abajLaunchTile" data-target="cinema" style="--tile-bg:url('/static/launcher-cinema-20261014.webp')"><span class="abajLaunchIcon">🎞</span><span class="abajLaunchText"><span class="abajLaunchName">Кинотеатр</span><span class="abajLaunchDesc">Фильмы, сериалы, мультфильмы</span></span></button><button class="abajLaunchTile" data-target="iptv" style="--tile-bg:url('/static/launcher-iptv-20261014.webp')"><span class="abajLaunchIcon">▣</span><span class="abajLaunchText"><span class="abajLaunchName">IPTV</span><span class="abajLaunchDesc">Каналы и прямые эфиры</span></span></button><button class="abajLaunchTile" data-target="settings" style="--tile-bg:url('/static/launcher-settings-20261014.webp')"><span class="abajLaunchIcon">⚙</span><span class="abajLaunchText"><span class="abajLaunchName">Настройки</span><span class="abajLaunchDesc">Параметры и управление</span></span></button></div><div class="abajLaunchFoot"></div>`;
document.body.appendChild(root);
for(const tile of root.querySelectorAll('.abajLaunchTile')){
const motion=document.createElement('span');motion.className='abajSceneMotion';motion.setAttribute('aria-hidden','true');
const accent=document.createElement('i');accent.className=tile.dataset.target==='cinema'?'abajSceneSun':tile.dataset.target==='iptv'?'abajSceneWater':'abajSceneGear';
motion.appendChild(accent);
if(tile.dataset.target==='iptv'){const backlight=document.createElement('i');backlight.className='abajTvBacklight';motion.appendChild(backlight);}
tile.insertBefore(motion,tile.firstChild);
}
createCinemaScene(root.querySelector('[data-target="cinema"]'),root);
createIptvScenes(root.querySelector('[data-target="iptv"]'),root);
const footballScreen=createFootballScreen(root.querySelector('[data-target="iptv"]'),root);

const settingsGear=createSettingsGear(root.querySelector('[data-target="settings"]'),root);
const brand=root.querySelector('.abajLaunchBrand');
for(const [x,y,delay,speed] of [[5,22,0,2.7],[17,70,-1.3,3.2],[29,18,-.8,2.4],[42,77,-2.1,3.5],[54,25,-1.7,2.9],[67,69,-.4,3.1],[80,16,-2.5,2.6],[93,73,-1.1,3.4]]){
const spark=document.createElement('i');
spark.className='abajBrandSpark';
spark.style.cssText='left:'+x+'%;top:'+y+'%;--spark-delay:'+delay+'s;--spark-speed:'+speed+'s';
spark.setAttribute('aria-hidden','true');
brand.appendChild(spark);
}
const launcherTranslations={
ru:{title:'ВАШ МИР КИНО И ТЕЛЕВИДЕНИЯ',cinema:'Кинотеатр',cinemaDesc:'Фильмы, сериалы, мультфильмы',iptv:'IPTV',iptvDesc:'Каналы и прямые эфиры',settings:'Настройки',settingsDesc:'Параметры и управление',home:'Главная ABAJ TV'},
hy:{title:'ԿԻՆՈՅԻ ԵՎ ՀԵՌՈՒՍՏԱՏԵՍՈՒԹՅԱՆ ՁԵՐ ԱՇԽԱՐՀԸ',cinema:'Կինոթատրոն',cinemaDesc:'Ֆիլմեր, սերիալներ, մուլտֆիլմեր',iptv:'IPTV',iptvDesc:'Հեռուստաալիքներ և ուղիղ եթերներ',settings:'Կարգավորումներ',settingsDesc:'Կարգավորումներ և կառավարում',home:'ABAJ TV գլխավոր էջ'},
en:{title:'YOUR WORLD OF MOVIES AND TELEVISION',cinema:'Cinema',cinemaDesc:'Movies, series, cartoons',iptv:'IPTV',iptvDesc:'Channels and live TV',settings:'Settings',settingsDesc:'Preferences and controls',home:'ABAJ TV Home'}
};
let launcherLanguage='';
function applyLauncherLanguage(){
const selected=localStorage.getItem('abaj_tv_lang')||'ru';
const lang=launcherTranslations[selected]?selected:'ru';
if(lang===launcherLanguage)return;
launcherLanguage=lang;
root.dataset.launchLang=lang;
const t=launcherTranslations[lang];
root.querySelector('.abajLaunchTitle').textContent=t.title;
for(const [target,name,desc] of [['cinema',t.cinema,t.cinemaDesc],['iptv',t.iptv,t.iptvDesc],['settings',t.settings,t.settingsDesc]]){
const tile=root.querySelector('[data-target="'+target+'"]');
tile.querySelector('.abajLaunchName').textContent=name;
tile.querySelector('.abajLaunchDesc').textContent=desc;
}
root.setAttribute('aria-label',t.home);
if(typeof home!=='undefined'){home.title=t.home;home.setAttribute('aria-label',t.home)}
}
document.addEventListener('click',e=>{
if(e.target.closest('#langHyBtn,#langRuBtn,#langEnBtn'))queueMicrotask(applyLauncherLanguage);
});
window.addEventListener('storage',e=>{if(e.key==='abaj_tv_lang')applyLauncherLanguage()});
const home=document.createElement('button');home.id='abajLaunchHome';home.textContent='⌂';home.title='Главная ABAJ TV';home.setAttribute('aria-label','Главная ABAJ TV');home.hidden=true;document.body.appendChild(home);applyLauncherLanguage();

// IPTV transition: the football from the sports thumbnail flies towards the viewer.
let iptvTransitionBusy=false;
let cinemaTransitionBusy=false;
let settingsTransitionBusy=false;
let transitionStage=null;
async function runLaunchTransition(duration,paint){
 const canvas=document.createElement('canvas'),ctx=canvas.getContext('2d');
 if(!ctx)return;
 canvas.className='abajTransitionStage';canvas.setAttribute('aria-hidden','true');
 const w=window.innerWidth,h=window.innerHeight,dpr=Math.min(window.devicePixelRatio||1,2);
 canvas.width=Math.round(w*dpr);canvas.height=Math.round(h*dpr);document.body.appendChild(canvas);transitionStage=canvas;
 let frame=0,timer=0;
 try{
  await new Promise((resolve,reject)=>{
   let start=null,settled=false;
   function finish(){if(settled)return;settled=true;cancelAnimationFrame(frame);clearTimeout(timer);resolve()}
   function tick(now){
    if(settled)return;if(start===null)start=now;const p=Math.min(1,(now-start)/duration);
    try{
     ctx.setTransform(dpr,0,0,dpr,0,0);ctx.clearRect(0,0,w,h);paint(ctx,w,h,p);
     const cover=Math.max(0,(p-.94)/.06);ctx.fillStyle='rgba(4,17,38,'+cover+')';ctx.fillRect(0,0,w,h);
    }catch(err){settled=true;clearTimeout(timer);reject(err);return}
    if(p===1)finish();else frame=requestAnimationFrame(tick);
   }
   timer=setTimeout(()=>{
    ctx.setTransform(dpr,0,0,dpr,0,0);ctx.fillStyle='#041126';ctx.fillRect(0,0,w,h);finish();
   },duration+500);
   frame=requestAnimationFrame(tick);
  });
 }catch(err){canvas.remove();transitionStage=null;throw err}
 finally{cancelAnimationFrame(frame);clearTimeout(timer)}
}
async function revealLaunchDestination(){
 const stage=transitionStage;transitionStage=null;
 if(!stage)return;
 try{
  if(typeof stage.animate==='function'){
   const fade=stage.animate([{opacity:1},{opacity:0}],{duration:180,easing:'ease-out',fill:'forwards'});
   await Promise.race([fade.finished.catch(()=>{}),new Promise(resolve=>setTimeout(resolve,250))]);fade.cancel();
  }
 }finally{stage.remove()}
}
async function playSettingsGearTransition(tile){
 settingsTransitionBusy=true;
 if(window.matchMedia('(prefers-reduced-motion: reduce)').matches)return;
 const rect=tile.getBoundingClientRect(),origin=settingsGear?.takeOff()||{x:rect.left+rect.width*.75,y:rect.top+rect.height*.4,radius:rect.height*.3,angle:0};
 await runLaunchTransition(1350,(ctx,w,h,p)=>{
  const travel=p*p*(3-2*p),x=origin.x+(w*.5-origin.x)*travel,y=origin.y+(h*.5-origin.y)*travel;
  const depth=.075+.925*Math.pow(1-p,1.9),radius=origin.radius/depth,opening=Math.max(0,Math.min(1,(p-.57)/.36));
  ctx.fillStyle='rgba(4,17,38,'+(opening*.98)+')';ctx.fillRect(0,0,w,h);
  const glow=ctx.createRadialGradient(x,y,radius*.16,x,y,radius*1.2);
  glow.addColorStop(0,'#54dcff00');glow.addColorStop(.5,'rgba(55,195,255,'+(.12+opening*.28)+')');glow.addColorStop(1,'#148aff00');ctx.fillStyle=glow;ctx.fillRect(0,0,w,h);
  drawLauncherGear(ctx,x,y,radius,origin.angle+p*p*Math.PI*2,opening);
 });
}
async function playCinemaGlassesTransition(tile){
 cinemaTransitionBusy=true;
 if(window.matchMedia('(prefers-reduced-motion: reduce)').matches)return;
 const rect=tile.getBoundingClientRect(),origin={x:rect.left+rect.width*.5,y:rect.top+rect.height*.43};
 await runLaunchTransition(1450,(ctx,w,h,p)=>drawCinemaGlasses(ctx,w,h,origin,p));
}
async function playIptvBallTransition(tile){
 iptvTransitionBusy=true;
 if(window.matchMedia('(prefers-reduced-motion: reduce)').matches)return;
 const rect=tile.getBoundingClientRect(),origin=footballScreen?.takeOff()||{x:rect.left+rect.width*.665,y:rect.top+rect.height*.285,radius:rect.width*.024,angle:0};
 let painter=null;
 await runLaunchTransition(1250,(ctx,w,h,p)=>{
  if(!painter)painter=createFootballPainter(ctx,1);
  const near=origin.radius/(Math.hypot(w,h)*.8),depth=near+(1-near)*Math.pow(1-p,1.65),radius=origin.radius/depth;
  const travel=1-Math.pow(1-p,2),x=origin.x+(w*.5-origin.x)*travel,y=origin.y+(h*.48-origin.y)*travel-Math.sin(p*Math.PI)*Math.min(65,h*.08);
  ctx.fillStyle='rgba(2,11,24,'+(p*.2)+')';ctx.fillRect(0,0,w,h);
  ctx.save();ctx.translate(x,y);ctx.rotate(-.18*Math.sin(p*Math.PI));ctx.scale(radius,radius);painter(0,0,origin.angle+p*5.4);ctx.restore();
 });
}
function show(){settingsGear?.reset();applyLauncherLanguage();try{if(typeof closeTvSettings==='function')closeTvSettings();if(typeof closeAdmin==='function')closeAdmin()}catch(e){}root.hidden=false;footballScreen?.reset();home.hidden=true;root.querySelector('button')?.focus({preventScroll:true})}
function hide(){root.hidden=true;home.hidden=true}
window.abajLauncherHome=show;
root.addEventListener('click',async e=>{
 const b=e.target.closest('[data-target]');if(!b||iptvTransitionBusy||cinemaTransitionBusy||settingsTransitionBusy)return;
 const target=b.dataset.target;
 try{
  if(target==='cinema'){
   await playCinemaGlassesTransition(b);
   if(!document.body.classList.contains('cinemaMode')&&typeof toggleCinemaMode==='function')await toggleCinemaMode();
  }
  if(target==='iptv'){
   await playIptvBallTransition(b);
   if(document.body.classList.contains('cinemaMode')&&typeof toggleCinemaMode==='function')await toggleCinemaMode();
  }
  if(target==='settings'){
   await playSettingsGearTransition(b);
   if(typeof openTvSettings==='function')openTvSettings();
  }
  if(target==='settings'||target==='iptv'||document.body.classList.contains('cinemaMode'))hide();
 }catch(err){footballScreen?.reset();settingsGear?.reset();console.error('ABAJ launcher navigation',err)}
 finally{try{await revealLaunchDestination()}finally{iptvTransitionBusy=false;cinemaTransitionBusy=false;settingsTransitionBusy=false}}
});
home.addEventListener('click',show);
root.addEventListener('keydown',e=>{const keys=['ArrowRight','ArrowLeft','ArrowUp','ArrowDown'];if(!keys.includes(e.key))return;const bs=[...root.querySelectorAll('[data-target]')];const i=Math.max(0,bs.indexOf(document.activeElement));const delta=(e.key==='ArrowRight'||e.key==='ArrowDown')?1:-1;bs[(i+delta+bs.length)%bs.length].focus({preventScroll:true});e.preventDefault()});
show();
}
if(document.readyState==='loading')document.addEventListener('DOMContentLoaded',()=>setTimeout(start,250));else setTimeout(start,250);
})();
