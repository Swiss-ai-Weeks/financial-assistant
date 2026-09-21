/* Optional browser acceptance: NODE_PATH=<Playwright installation>/node_modules node tests/pythia.browser.cjs.
   Serves an isolated production build on an ephemeral port; all APIs are local fixtures. */
process.env.PLAYWRIGHT_BROWSERS_PATH ??= '/tmp/pythia-browser/browsers';
const {chromium} = require(process.env.PYTHIA_PLAYWRIGHT_MODULE ?? '/tmp/pythia-browser/node_modules/playwright');
const http = require('node:http');
const fs = require('node:fs');
const path = require('node:path');
const assert = require('node:assert/strict');
const root=path.resolve(__dirname,'..');
const graph=JSON.parse(fs.readFileSync(path.join(root,'public/investigation_review_demo.json')));
const models=[{id:'a',provider:'fixture',model:'alpha',label:'Analysis Alpha',roles:['analysis'],locality:'local',available:true},
{id:'b',provider:'fixture',model:'beta',label:'Analysis Beta',roles:['analysis'],locality:'local',available:true}];
const counts={};
const server=http.createServer((req,res)=>{
  const url=new URL(req.url,'http://localhost');
  const send=(body,status=200)=>{res.writeHead(status,{'content-type':'application/json'});res.end(JSON.stringify(body));};
  if(url.pathname.startsWith('/api/')) {
    counts[url.pathname]=(counts[url.pathname]??0)+1;
    if(url.pathname==='/api/investigations/models') return send({models});
    if(url.pathname==='/api/replays') return send({replays:[]});
    if(url.pathname==='/api/bookreader/source-links') return send({base_url:''});
    if(url.pathname==='/api/health') return send({as_of:'2026-09-18',market_as_of:'2026-09-18'});
    if(url.pathname==='/api/instruments/search') return send({securities:[{identity:'CRWV',ticker:'CRWV',name:'CoreWeave',universes:[],catalogued:false,dynamically_resolved:true,coverage:{market_cache:false,precomputed_pairs:false}}],limitation:'Current snapshots only'});
    if(url.pathname.endsWith('/candles')) return send({source:'Synthetic browser test prices',last_session:'2026-09-18',candles:Array.from({length:30},(_,i)=>({date:`2026-08-${String(i+1).padStart(2,'0')}`,close:100+i+Math.sin(i)*4}))});
    if(url.pathname.startsWith('/api/microscope/')) return send({ticks:['1d','1w','1m','3m','1y'].map(horizon=>({horizon,status:'available',return_pct:2,benchmark_return_pct:1,abnormal_return_pct:1,z_score:1,volume_multiple:1,unusual:false})),peers:{}});
    if(url.pathname==='/api/market/tape') return send({as_of:'2026-09-18',quotes:[]});
    if(url.pathname==='/api/news') return send({cutoff:'2026-09-18T23:59:59+00:00',availability:{COHU:{'yahoo-finance':'unavailable'}},admissible:[
      {news_id:'n1',title:'Company announces results',published_at:'2026-08-01T10:00:00+00:00',publisher:'Archive Wire',summary:'Revenue summary',source:'archive',url:'https://example.com/1',cutoff_availability:'published_by_cutoff'},
      {news_id:'n2',title:'Company expands production',published_at:'2026-08-02T10:00:00+00:00',publisher:'Yahoo Wire',summary:'Expansion summary',source:'yahoo-finance',url:'https://example.com/2',cutoff_availability:'published_by_cutoff'}],
      hindsight:[{news_id:'n3',title:'Later company update',published_at:'2026-09-19T10:00:00+00:00',source:'yahoo-finance',url:'https://example.com/3',cutoff_availability:'hindsight'}]});
    if(url.pathname.endsWith('/signals')) return send({signals:[],status:'available'});
    if(url.pathname==='/api/portfolio/analysis') return send({status:'unavailable',reason:'Synthetic browser test — no portfolio prices'});
    if(url.pathname==='/api/anomalies/scan' || url.pathname==='/api/anomalies/historical-scan') return send({as_of:'2026-03-20',cache:{price_securities:2},candidate_count:1,elapsed_ms:1,candidates:[{pair:'COHU/PDFS',ticker_a:'COHU',ticker_b:'PDFS',signal_date:'2026-03-20',z_score:2,correlation:.8,cointegration_p:.01}]});
    if(url.pathname==='/api/copilot') return send({answer:'Advisory fixture',route:'interaction',model:models[0],ui_action:{type:'none'},executions:[]});
    return send({error:'Unexpected test API'},404);
  }
  let file=path.join(root,'dist',url.pathname);
  if(!file.startsWith(path.join(root,'dist'))) {res.writeHead(403);return res.end();}
  if(!fs.existsSync(file) || fs.statSync(file).isDirectory()) file=path.join(root,'dist/index.html');
  res.writeHead(200,{'content-type':file.endsWith('.js')?'text/javascript':file.endsWith('.css')?'text/css':file.endsWith('.json')?'application/json':'text/html'});
  res.end(fs.readFileSync(file));
});
(async()=>{
 await new Promise(resolve=>server.listen(0,'127.0.0.1',resolve));
 const browser=await chromium.launch({headless:true});
 try {
  const page=await browser.newPage({viewport:{width:1440,height:1000}});
  const errors=[];page.on('pageerror',e=>errors.push(e.message));
  const base=`http://127.0.0.1:${server.address().port}`;
  await page.goto(base+'/now');
  await page.getByRole('heading',{name:'COHU What is unusual?'}).waitFor();
  await page.getByRole('tab',{name:'Monitors'}).click();
  await page.getByRole('tab',{name:'Peers',exact:true}).click();
  await page.getByRole('tab',{name:/^News/}).click();
  await page.getByText('Company announces results',{exact:true}).waitFor();
  await page.getByText('Later company update',{exact:true}).waitFor();
  await page.getByText('Yahoo news unavailable for COHU;', {exact:false}).waitFor();
  await page.locator('.market-desk:visible .price-history select').selectOption('2026-08-01');
  assert.equal(await page.getByText('Company expands production',{exact:true}).count(),0);
  assert.equal(await page.getByText('Later company update',{exact:true}).count(),0);
  await page.getByText('Company announces results',{exact:true}).waitFor();
  await page.getByRole('button',{name:/Clear session/}).click();
  await page.getByText('Company expands production',{exact:true}).waitFor();
  await page.screenshot({path:'/tmp/pythia-now.png',fullPage:true});
  await page.getByRole('navigation',{name:'Main navigation'}).getByRole('button',{name:'Past',exact:true}).click();
  await page.getByRole('heading',{name:'COHU What was knowable?'}).waitFor();
  await page.getByRole('button',{name:'TRAVEL TO DATE'}).click();
  await page.getByRole('button',{name:/COHU\/PDFS/}).first().waitFor();
  await page.getByRole('navigation',{name:'Main navigation'}).getByRole('button',{name:'Explore',exact:true}).click();
  await page.getByRole('heading',{name:'Explore opportunities'}).waitFor();
  await page.getByPlaceholder('Ticker or company name').filter({visible:true}).fill('CRWV');
  await page.getByRole('button',{name:/CRWV CoreWeave/}).click();
  await page.getByRole('heading',{name:'CRWV What was knowable?'}).waitFor();
  await page.getByRole('button',{name:'Investigate CRWV →'}).click();
  assert((await page.evaluate(()=>JSON.parse(localStorage.getItem('claimgraph:workspace:v1')))).workspaces[0].candidate.mode==='security');
  // Install two completed canonical investigations to test model/tab/graph preservation without inference.
  await page.evaluate(({graph,models})=>{
    const state=JSON.parse(localStorage.getItem('claimgraph:workspace:v1'));
    state.workspaces=[{id:'a',label:'COHU',model:models[0],graph,as_of:'2026-09-16'}, {id:'b',label:'BAC',model:models[1],graph:{...graph,investigation_id:'second-investigation'},as_of:'2026-09-16'}];
    state.activeWorkspaceId='a';localStorage.setItem('claimgraph:workspace:v1',JSON.stringify(state));
  },{graph,models});
  await page.goto(base+'/investigate/a');
  await page.locator('.investigation-page:not([hidden]) .react-flow__node').first().waitFor();
  await page.locator('.investigation-page:not([hidden]) .react-flow__node').first().click();
  await page.getByRole('button',{name:'Close inspector ×'}).waitFor();
  await page.screenshot({path:'/tmp/pythia-investigate.png',fullPage:true});
  await page.getByRole('button',{name:'Close inspector ×'}).click();
  const aSection=page.locator('.investigation-page:not([hidden])');
  await aSection.locator('.workspace-settings>summary').click();
  await aSection.getByLabel('Model/provider for the next investigation').selectOption({label:'Analysis Beta · local'});
  await page.getByRole('navigation',{name:'Main navigation'}).getByRole('button',{name:'Portfolio',exact:true}).click();
  await page.getByRole('heading',{name:'Sample research portfolio (fictional allocation)'}).waitFor();
  await page.getByRole('navigation',{name:'Main navigation'}).getByRole('button',{name:'Investigate',exact:true}).click();
  assert(page.url().endsWith('/investigate/a'));
  const state=await page.evaluate(()=>JSON.parse(localStorage.getItem('claimgraph:workspace:v1')));
  assert.equal(state.workspaces[0].model.id,'b'); assert.equal(state.workspaces[1].model.id,'b');
  assert.equal(state.workspaces[0].graph.investigation_id,graph.investigation_id);
  await page.getByRole('button',{name:/BAC investigation/}).click();
  await page.locator('.investigation-page:not([hidden]) .workspace-settings>summary').click();
  await page.locator('.investigation-page:not([hidden])').getByLabel('Model/provider for the next investigation').selectOption({label:'Analysis Alpha · local'});
  const isolated=await page.evaluate(()=>JSON.parse(localStorage.getItem('claimgraph:workspace:v1')));
  assert.equal(isolated.workspaces[0].model.id,'b');assert.equal(isolated.workspaces[1].model.id,'a');
  const beforeCommentary=await page.evaluate(()=>JSON.stringify(JSON.parse(localStorage.getItem('claimgraph:workspace:v1')).workspaces.map(w=>w.graph)));
  const panel=page.locator('.investigation-page:not([hidden]) .copilot-panel');
  await panel.locator('summary').first().click();
  await panel.getByLabel('Ask about this view').fill('Explain the current view');
  await panel.getByRole('button',{name:'Ask',exact:true}).click();
  await panel.getByText('Advisory fixture',{exact:true}).waitFor();
  assert.equal(await page.evaluate(()=>JSON.stringify(JSON.parse(localStorage.getItem('claimgraph:workspace:v1')).workspaces.map(w=>w.graph))),beforeCommentary);
  await panel.locator('summary').first().click();
  await page.getByRole('button',{name:'Prepare report'}).click();
  await page.getByRole('region',{name:'Investigation report'}).waitFor();
  await page.screenshot({path:'/tmp/pythia-report.png',fullPage:true});
  for(const name of ['JSON','Markdown','Printable HTML / PDF']) {
    const waiting=page.waitForEvent('download');await page.getByRole('button',{name,exact:true}).click();
    const download=await waiting; const content=fs.readFileSync(await download.path(),'utf8');
    assert(content.includes('second-investigation'));assert(content.includes('calculation:CALC-EXPOSURE'));
  }
  await page.getByRole('button',{name:'Back to graph',exact:true}).click();
  await page.reload();
  assert.equal((await page.evaluate(()=>JSON.parse(localStorage.getItem('claimgraph:workspace:v1')))).workspaces.length,2);
  await page.setViewportSize({width:390,height:844});await page.goto(base+'/now');
  await page.screenshot({path:'/tmp/pythia-mobile.png',fullPage:true});
  assert.equal(counts['/api/investigations']??0,0);assert.equal(counts['/api/investigations/followup']??0,0);
  assert.deepEqual(errors,[]);
  console.log('PASS: Now/Past/Explore/Portfolio/Investigate; security handoff; graph inspector; persistent tabs; isolated models; reload; HTML/Markdown/JSON exports; mobile rendering. No inference called.');
 } finally {await browser.close();server.close();}
})().catch(e=>{console.error(e);server.close();process.exitCode=1;});
