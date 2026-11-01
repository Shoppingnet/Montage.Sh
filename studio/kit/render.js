const {chromium}=require('playwright');(async()=>{const b=await chromium.launch();const p=await b.newPage({viewport:{width:1080,height:1920}});
for(const n of process.argv.slice(2)){await p.goto('file:///home/claude/kit/'+n+'.html');await p.waitForTimeout(500);await p.screenshot({path:'/home/claude/kit/'+n+'.png',omitBackground:true});}await b.close()})();
