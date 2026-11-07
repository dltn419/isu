/* Spectator playback: deterministic clock, no browser and no classroom writes. */
const {JSDOM,VirtualConsole}=require('jsdom');
const fs=require('node:fs'),path=require('node:path'),assert=require('node:assert/strict');
const root=path.resolve(__dirname,'../static'),replay=JSON.parse(fs.readFileSync(process.argv[2],'utf8')),fixture=JSON.parse(fs.readFileSync(process.argv[3],'utf8')),fundedReplay=JSON.parse(fs.readFileSync(process.argv[4],'utf8'));
const tick=()=>new Promise(resolve=>setTimeout(resolve,0));
async function build({teacher=false,url='http://localhost/',roomCash=100000,delayState=false}={}){
 const errors=[],calls=[],vc=new VirtualConsole();vc.on('jsdomError',e=>errors.push(e.message));
 const dom=new JSDOM('<div id="app"></div><div id="toast"></div><div id="modal-root"></div>',{url,runScripts:'dangerously',virtualConsole:vc});
 const w=dom.window;w.scrollTo=()=>{};w.structuredClone=structuredClone;w.setInterval=()=>0;w.confirm=()=>true;
 Object.defineProperty(w.document,'visibilityState',{configurable:true,get:()=> 'visible'});
 if(teacher)w.localStorage.setItem('haru_token','teacher-test');
 w.fetch=async(url,options={})=>{calls.push({url,options});if(url==='/api/state'&&delayState)await new Promise(resolve=>setTimeout(resolve,20));let data=url.startsWith('/api/spectator')?(new URL(url,'http://localhost').searchParams.get('start_cash')==='500000'?fundedReplay:replay):url==='/api/state'?{...fixture.teacher,room:{...fixture.teacher.room,start_cash:roomCash}}:url==='/api/demo'?fixture.demo:{ok:true,status:'offline'};return{ok:true,status:200,json:async()=>structuredClone(data)}};
 for(const name of ['design.js','core.js','guides.js','trade.js','ending.js','spectator.js','research.js']){const el=w.document.createElement('script');el.textContent=fs.readFileSync(path.join(root,name),'utf8');w.document.body.appendChild(el)}
 await tick();return{dom,w,errors,calls};
}
(async()=>{
 {
  const {dom,w,errors,calls}=await build(),d=w.document;
  assert.ok([...d.querySelectorAll('button')].some(b=>b.textContent.includes('AI 3명 투자 구경하기')));
  w.openSpectator();await tick();
  assert.equal(w.spectatorActive(),true);assert.equal(w.eval('spectator.loading'),false);
  assert.equal(d.querySelectorAll('.watch-bot').length,3);assert.equal(w.eval('spectator.dayIndex'),0);
  assert.equal(d.querySelector('.watch-chart polyline').getAttribute('points').split(' ').length,2,'do not draw future performance');
  assert.equal(w.eval('spectator.seen.length'),0);
  w.nextSpectatorChoice();assert.equal(w.eval('spectator.seen.length'),1);assert.equal(w.eval('spectator.playing'),false);
  const event=replay.frames[0].events[0];assert.ok(d.querySelector('#watch-latest').textContent.includes(event.reason));
  if(event.fee)assert.ok(d.querySelector('#watch-latest').textContent.includes(event.fee+'원'));
  const unseen=replay.news.find(n=>n.day>1);w.openSpectatorNews(unseen.id);assert.equal(d.querySelector('.modal'),null);
  const source=replay.news.find(n=>n.day===1);w.openSpectatorNews(source.id);assert.ok(d.querySelector('.modal').textContent.includes(source.reading?.title||source.title));
  assert.equal(w.eval('spectator.playing'),false);w.closeModal();
  w.openSpectatorBot('news');assert.ok(d.querySelector('.modal').textContent.includes('보유 상품'));w.closeModal();
  const speed=d.querySelector('#watch-speed');speed.value='5';speed.dispatchEvent(new w.Event('change'));
  assert.equal(w.eval('spectator.seconds'),5);w.toggleSpectator();
  for(let i=0;i<5;i++)w.tickSpectator(w.eval('spectator.lastTick')+1000);
  assert.equal(w.eval('spectator.dayIndex'),1);assert.equal(w.eval('spectator.seen.length'),replay.frames[0].events.length);
  assert.equal(new Set(w.eval('spectator.seen.map(e=>e.id)')).size,w.eval('spectator.seen.length'));
  w.setSpectatorMood('positive');assert.equal(w.eval('spectator.data.mood'),'neutral');assert.ok(d.querySelector('#watch-setting-note').textContent.includes('새 경기'));
  let guard=0;while(!w.eval('spectator.finished')&&guard++<30)w.nextSpectatorDay();
  assert.equal(w.eval('spectator.finished'),true);assert.equal(w.eval('spectator.dayIndex'),23);assert.equal(d.querySelector('#watch-play').disabled,true);
  assert.equal(w.spectatorRank([{net:100},{net:100},{net:90}],{net:100}),'공동 1위');
  assert.ok(d.querySelector('.watch-final').textContent.includes('110,000원'));
  for(const p of replay.final)assert.equal(w.eval(`spectator.players.find(p=>p.id==='${p.id}').net`),p.net);
  assert.equal(w.eval('spectator.seen.length'),replay.frames.reduce((n,f)=>n+f.events.length,0));
  w.moreSpectatorLog();assert.equal(d.querySelectorAll('#watch-log .watch-event').length,48);
  w.setSpectatorFilter('swing');assert.ok([...d.querySelectorAll('#watch-log h3')].every(h=>h.textContent.includes('번개')));
  w.restartSpectator();assert.equal(w.eval('spectator.seen.length'),0);assert.equal(w.eval('spectator.finished'),false);
  assert.equal(calls.filter(c=>c.options.method==='POST').length,0);
  await w.exitSpectator();assert.equal(d.querySelector('#watch-root'),null);assert.ok(d.body.textContent.includes('학생 참가'));
  assert.deepEqual(errors,[]);dom.window.close();
  console.log('spectator: event reasons, fee display, evidence, no future UI data, speed, pause, steps, final settlement and restart passed');
 }
 {
  const {dom,w,errors,calls}=await build({teacher:true}),d=w.document;
  const room=w.eval('S.room.id'),token=w.localStorage.getItem('haru_token');
  w.openSpectator();await tick();w.nextSpectatorDay();
  assert.equal(w.eval('S.room.id'),room);assert.equal(w.localStorage.getItem('haru_token'),token);
  const before=calls.length;await w.pollProgression();assert.equal(calls.length,before,'do not poll the real classroom while viewing the replay');
  await w.exitSpectator();assert.ok(d.body.textContent.includes('수업 진행'));assert.equal(w.eval('S.room.id'),room);
  assert.equal(calls.filter(c=>c.options.method==='POST').length,0);
  assert.deepEqual(errors,[]);dom.window.close();
  console.log('spectator: classroom state/token preserved and no classroom mutations passed');
 }
 {
  const {dom,w,errors}=await build(),d=w.document;
  w.eval("authMode='create';render()");d.querySelector('#roomName').value='관전하고 돌아올 교실';
  w.openSpectator();await tick();await w.exitSpectator();assert.equal(d.querySelector('#roomName').value,'관전하고 돌아올 교실');
  let release;const original=w.fetch;w.fetch=async(url,opt)=>url.startsWith('/api/spectator')?new Promise(resolve=>{release=()=>resolve({ok:true,status:200,json:async()=>structuredClone(replay)})}):original(url,opt);
  w.openSpectator();assert.equal(w.eval('spectator.loading'),true);await w.exitSpectator();release();await tick();
  assert.equal(w.spectatorActive(),false);assert.equal(w.eval('spectator.loading'),false);
  w.fetch=original;w.openSpectator();await tick();assert.equal(w.eval('spectator.loading'),false);assert.equal(d.querySelectorAll('.watch-bot').length,3);
  assert.deepEqual(errors,[]);dom.window.close();
  console.log('spectator: create-form preservation, cancelled loading and reopening passed');
 }
 {
  const {dom,w,errors,calls}=await build(),d=w.document;
  w.eval("authMode='create';render()");d.querySelector('#startCash').value='500000';
  await w.openSpectator();
  assert.ok(calls.at(-1).url.includes('start_cash=500000'));
  assert.equal(w.eval('spectator.data.initial_cash'),500000);
  assert.equal(d.querySelector('.watch-start-cash strong').textContent,'500,000원');
  assert.ok(d.querySelector('.watch-chart-section .sub').textContent.includes('500,000원'));
  assert.ok([...d.querySelectorAll('.watch-bot>strong')].every(el=>el.textContent==='500,000원'));
  await w.startSpectatorGame();assert.ok(calls.at(-1).url.includes('start_cash=500000'));
  w.pauseSpectator();let guard=0;while(!w.eval('spectator.finished')&&guard++<30)w.nextSpectatorDay();
  assert.ok(d.querySelector('.watch-final').textContent.includes('550,000원'));
  w.eval('spectator.data.initial_cash=56789');assert.ok(w.spectatorDepositBenchmark().includes('61,789원'));assert.ok(w.spectatorDepositBenchmark().includes('6,789원'));
  w.eval('spectator.data.initial_cash=1000');assert.ok(w.spectatorDepositBenchmark().includes('최소 가입액'));
  await w.exitSpectator();assert.equal(d.querySelector('#startCash').value,'500000');
  assert.equal(new URL(w.location.href).searchParams.has('start_cash'),false);
  for(const value of ['','999','100000001','1000.5']){d.querySelector('#startCash').value=value;const before=calls.length;await w.openSpectator();assert.equal(w.spectatorActive(),false);assert.equal(calls.length,before)}
  assert.deepEqual(errors,[]);dom.window.close();console.log('spectator: creation amount, actual replay, amounts, benchmark, new game and invalid input passed');
 }
 {
  const {dom,w,errors,calls}=await build({teacher:true,roomCash:500000});
  await w.openSpectator();assert.ok(calls.at(-1).url.includes('start_cash=500000'));assert.equal(w.eval('spectator.data.initial_cash'),500000);
  const snapshot=w.eval('JSON.stringify(S)');await w.exitSpectator();assert.equal(w.eval('JSON.stringify(S)'),snapshot);
  assert.equal(calls.filter(c=>c.options.method==='POST').length,0);
  assert.deepEqual(errors,[]);dom.window.close();console.log('spectator: existing room amount applied without classroom mutations');
 }
 {
  const {dom,w,errors,calls}=await build({teacher:true,roomCash:500000,delayState:true,url:'http://localhost/?watch=1&start_cash=100000'});
  await new Promise(resolve=>setTimeout(resolve,50));
  assert.equal(w.eval('spectator.data.initial_cash'),500000);assert.ok(calls.find(c=>c.url.startsWith('/api/spectator')).url.includes('start_cash=500000'));
  assert.deepEqual(errors,[]);dom.window.close();console.log('spectator: direct link waits for room amount before starting');
 }
 {
  const {dom,w,errors}=await build({url:'http://localhost/?watch=1'});await tick();
  assert.equal(w.spectatorActive(),true);assert.equal(w.eval('spectator.loading'),false);
  assert.deepEqual(errors,[]);dom.window.close();console.log('spectator: direct watch link passed');
 }
 {
  const {dom,w,errors}=await build({url:'http://localhost/?watch=1&start_cash=500000'});await tick();
  assert.equal(w.eval('spectator.data.initial_cash'),500000);
  assert.deepEqual(errors,[]);dom.window.close();console.log('spectator: shared link retains starting cash');
 }
})().catch(e=>{console.error(e);process.exitCode=1});
