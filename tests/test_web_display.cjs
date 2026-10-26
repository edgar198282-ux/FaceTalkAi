const {chromium}=require('playwright');
const fs=require('fs'),path=require('path');
(async()=>{const browser=await chromium.launch({headless:true,executablePath:process.env.CHROMIUM_EXECUTABLE_PATH||undefined,args:['--no-sandbox','--disable-gpu']});
for(const legacy of [false,true])for(const size of [[1280,720],[1920,1080],[720,1280],[390,844]]){
 const page=await browser.newPage({viewport:{width:size[0],height:size[1]},hasTouch:true});const errors=[];page.on('pageerror',e=>errors.push(e.message));
 await page.route('**/*',route=>{const u=new URL(route.request().url());if(u.hostname!=='byd.test')return route.abort();
 let name=u.pathname==='/'?(legacy?'legacy/index.html':'index.html'):u.pathname.replace(/^\/static\//,'');
 const file=path.join(process.cwd(),'web',name);
 if(fs.existsSync(file)&&fs.statSync(file).isFile())return route.fulfill({path:file,contentType:file.endsWith('.js')?'application/javascript':file.endsWith('.css')?'text/css':file.endsWith('.html')?'text/html':undefined});
 return route.fulfill({json:{channels:[],items:[],ok:true}});});
 await page.goto('http://byd.test/');await page.waitForTimeout(800);
 const state=await page.evaluate(()=>({height:document.querySelector('.app').getBoundingClientRect().height,width:document.documentElement.scrollWidth,inner:innerWidth,launcher:!!document.getElementById('abajLauncher'),touch:document.documentElement.classList.contains('abajTouchScreen')}));
 console.log(JSON.stringify({legacy,size,state,errors}));if(state.height!==size[1]||state.width>size[0]||errors.some(x=>/Unexpected token|SyntaxError|is not a function/.test(x)))process.exitCode=1;
 await page.close();
}await browser.close();})();
