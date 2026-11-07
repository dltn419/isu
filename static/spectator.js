/* Public, read-only replay. S and the current classroom token are never replaced. */
const spectator={active:false,loading:false,error:'',data:null,dayIndex:0,eventIndex:-1,elapsed:0,seconds:15,playing:false,finished:false,players:[],seen:[],scenario:0,mood:'neutral',startCash:100000,filter:'all',logLimit:24,lastTick:0,request:0,controller:null};
const spectatorProfiles=[{id:'news',name:'하루',style:'뉴스 판단형',color:'#28664f'},{id:'balanced',name:'모아',style:'분산 투자형',color:'#376e9a'},{id:'swing',name:'번개',style:'단기 매매형',color:'#a46930'}];
function spectatorActive(){return spectator.active}
function spectatorEntry(){return `<section class="spectator-entry"><div><b>AI 3명의 투자를 구경해 볼까요?</b><p>성향이 다른 자동 투자자들의 별도 경기예요. 우리 반 날짜와 자산에는 영향을 주지 않아요.</p></div><button type="button" class="btn secondary" onclick="openSpectator()">AI 투자 관전 ${icon('arrow')}</button></section>`}
function spectatorStartingCash(){
 const input=$('#startCash'),query=new URLSearchParams(location.search);
 const value=S&&!S.demo?S.room.start_cash:input?.value??roomCreationDraft?.cash??query.get('start_cash')??100000;
 const amount=Number(value);
 if(!Number.isSafeInteger(amount)||amount<1000||amount>100000000){toast('시작 자금은 1,000원부터 100,000,000원까지 원 단위로 입력해 주세요.');input?.focus();return null}
 return amount;
}
async function openSpectator(){
 if(spectator.active)return;
 if(token&&!S){await initialClassroomLoad;if(token&&!S){toast('게임방 정보를 불러온 뒤 관전을 시작해 주세요.');return}if(spectator.active)return}
 const startCash=spectatorStartingCash();if(startCash===null)return;spectator.startCash=startCash;
 captureRoomCreationDraft();captureTradeDraft();closeModal();spectator.active=true;
 const url=new URL(location.href);url.searchParams.set('watch','1');url.searchParams.set('start_cash',String(startCash));window.history.replaceState(null,'',url.pathname+url.search+url.hash);
 renderSpectator();await startSpectatorGame(false);
}
async function exitSpectator(){
 spectator.active=false;spectator.playing=false;spectator.loading=false;spectator.request++;spectator.controller?.abort();closeModal();
 const url=new URL(location.href);url.searchParams.delete('watch');url.searchParams.delete('start_cash');window.history.replaceState(null,'',url.pathname+url.search+url.hash);
 render();if(S&&!S.demo&&token)await refresh(true);
}
async function startSpectatorGame(next=true){
 if(!spectator.active||spectator.loading)return;
 if(next)spectator.scenario=(spectator.scenario+1)%64;
 spectator.loading=true;spectator.error='';spectator.playing=false;spectator.finished=false;spectator.data=null;spectator.seen=[];spectator.players=[];spectator.dayIndex=0;spectator.eventIndex=-1;spectator.elapsed=0;
 const request=++spectator.request;const controller=new AbortController();spectator.controller?.abort();spectator.controller=controller;
 updateSpectatorBoard();
 try{
  let response;
  for(let attempt=0;attempt<5;attempt++){
   response=await fetch('/api/spectator?scenario='+spectator.scenario+'&mood='+encodeURIComponent(spectator.mood)+'&start_cash='+spectator.startCash,{signal:controller.signal});
   if(response.status!==429||attempt===4)break;
   await new Promise(resolve=>setTimeout(resolve,2000));if(!spectator.active||request!==spectator.request)return;
  }
  let data;try{data=await response.json()}catch{throw Error('서버 응답을 확인하지 못했어요. 잠시 뒤 다시 시작해 주세요.')}if(!response.ok)throw Error(data.detail||'관전 경기를 준비하지 못했어요.');
  if(!spectator.active||request!==spectator.request)return;
  if(!Array.isArray(data.frames)||data.frames.length!==24||data.bots?.length!==3||data.initial_cash!==spectator.startCash)throw Error('관전 경기의 시작 자금과 데이터를 다시 확인해 주세요.');
  spectator.data=data;spectator.loading=false;restartSpectator();
 }catch(e){if(!spectator.active||request!==spectator.request||e.name==='AbortError')return;spectator.loading=false;spectator.error=e.message;updateSpectatorBoard()}
}
function restartSpectator(){
 if(!spectator.data)return;
 spectator.dayIndex=0;spectator.eventIndex=-1;spectator.elapsed=0;spectator.players=structuredClone(spectator.data.frames[0].opening);spectator.seen=[];spectator.logLimit=24;spectator.finished=false;spectator.playing=true;spectator.lastTick=Date.now();
 updateSpectatorBoard();
}
function spectatorFrame(){return spectator.data?.frames[spectator.dayIndex]}
function pauseSpectator(){spectator.playing=false;updateSpectatorClock()}
function toggleSpectator(){if(!spectator.data||spectator.loading||spectator.finished)return;spectator.playing=!spectator.playing;spectator.lastTick=Date.now();updateSpectatorClock()}
function setSpectatorSpeed(value){const seconds=Number(value);if(![5,15,60].includes(seconds))return;const fraction=spectator.elapsed/spectator.seconds;spectator.seconds=seconds;spectator.elapsed=fraction*seconds;spectator.lastTick=Date.now();updateSpectatorClock()}
function setSpectatorMood(value){if(['neutral','positive','negative'].includes(value))spectator.mood=value;updateSpectatorClock()}
function setSpectatorFilter(value){spectator.filter=['all','news','balanced','swing'].includes(value)?value:'all';spectator.logLimit=24;updateSpectatorLog()}
function moreSpectatorLog(){spectator.logLimit+=24;updateSpectatorLog()}
function applySpectatorEvent(index){
 const frame=spectatorFrame(),event=frame?.events[index];if(!event)return;
 spectator.eventIndex=index;spectator.players=spectator.players.map(p=>p.id===event.bot_id?structuredClone(event.after):p);
 spectator.seen.push(event);updateSpectatorBoard();
 const announcement=$('#spectator-live');if(announcement)announcement.textContent=spectatorEventTitle(event);
}
function finishSpectatorDay(){
 const frame=spectatorFrame();if(!frame)return;
 for(let i=spectator.eventIndex+1;i<frame.events.length;i++){
  const event=frame.events[i];spectator.seen.push(event);
 }
 spectator.players=structuredClone(frame.closing);
 if(spectator.dayIndex===23){spectator.finished=true;spectator.playing=false;spectator.eventIndex=frame.events.length-1;spectator.elapsed=spectator.seconds}
 else{spectator.dayIndex++;spectator.eventIndex=-1;spectator.elapsed=0;spectator.players=structuredClone(spectatorFrame().opening)}
 updateSpectatorBoard();
}
function nextSpectatorChoice(){
 if(!spectator.data||spectator.finished||spectator.loading)return;pauseSpectator();
 const frame=spectatorFrame();if(spectator.eventIndex+1<frame.events.length){const i=spectator.eventIndex+1;applySpectatorEvent(i);spectator.elapsed=spectator.seconds*(i+1)/(frame.events.length+1)}else finishSpectatorDay();updateSpectatorClock();
}
function nextSpectatorDay(){if(!spectator.data||spectator.finished||spectator.loading)return;pauseSpectator();finishSpectatorDay()}
function tickSpectator(now=Date.now()){
 if(!spectator.active||!spectator.playing||!spectator.data||spectator.finished||spectator.loading)return;
 if(document.visibilityState==='hidden'){pauseSpectator();return}
 const dt=Math.max(0,Math.min(1,(now-spectator.lastTick)/1000));spectator.lastTick=now;spectator.elapsed+=dt;
 const frame=spectatorFrame();
 while(spectator.eventIndex+1<frame.events.length&&spectator.elapsed>=spectator.seconds*(spectator.eventIndex+2)/(frame.events.length+1))applySpectatorEvent(spectator.eventIndex+1);
 if(spectator.elapsed>=spectator.seconds)finishSpectatorDay();else updateSpectatorClock();
}
function spectatorBot(id){return(spectator.data?.bots||spectatorProfiles).find(b=>b.id===id)}
function spectatorDepositBenchmark(){
 const cash=spectator.data.initial_cash,principal=Math.floor(cash/10000)*10000;
 if(!principal)return '시작 자금이 예금 최소 가입액 10,000원보다 적어 전액 예금 비교는 생략해요.';
 const total=cash+Math.round(principal*.1);
 return (principal===cash?'시작 자금을 24일 예금에 맡겼다면 ':`24일 예금에 ${money(principal)}, 남은 ${money(cash-principal)}을 현금으로 뒀다면 `)+money(total)+'이에요.';
}
function spectatorRank(players,p){return(players.filter(x=>x.net===p.net).length>1?'공동 ':'')+(players.filter(x=>x.net>p.net).length+1)+'위'}
function spectatorEventTitle(event){
 const name=spectatorBot(event.bot_id)?.name||'투자자',unit=spectator.data?.assets.find(a=>a.id===event.asset)?.type==='gold'?'g':'주';
 if(event.type==='buy'||event.type==='sell')return `${name}가 ${event.asset_name} ${number(event.qty)}${unit}${unit==='g'?'을':'를'} ${event.type==='buy'?'매수':'매도'}했어요.`;
 if(event.type==='deposit')return `${name}가 ${money(event.amount)}을 ${event.term}일 예금에 맡겼어요.`;
 if(event.type==='income')return `${name}가 이자 ${money(event.amount)}을 받았어요.`;
 if(event.type==='settlement')return `${name}의 24일 투자를 최종 정산했어요.`;
 return `${name}는 이번에는 기다려요.`;
}
function spectatorTradeCost(event){if(event.type==='buy'||event.type==='sell')return `${money(event.price)} × ${number(event.qty)} · 수수료 ${money(event.fee)} · ${event.type==='buy'?'결제':'수령'} ${money(event.settlement)}`;if(event.type==='deposit')return '24일 만기까지 유지하면 이자 10%';return ''}
function spectatorNewsTitle(n){return n?.reading?.title||n?.title||'관련 기사'}
function spectatorEvidence(event){return(event.evidence_ids||[]).map(id=>`<button type="button" class="text-btn" onclick="openSpectatorNews(${id})">근거 기사 #${id} ↗</button>`).join('')}
function spectatorEventMarkup(event,compact=false){const bot=spectatorBot(event.bot_id);return `<article class="watch-event ${compact?'compact':''}" style="--bot-color:${bot.color}"><div class="watch-event-meta"><b>${event.day}일차</b><span>${esc(bot.style)}</span>${event.automatic?'<span class="watch-auto">자동 처리</span>':''}</div><h3>${esc(spectatorEventTitle(event))}</h3>${spectatorTradeCost(event)?`<div class="watch-trade-cost">${esc(spectatorTradeCost(event))}</div>`:''}<p>${esc(event.reason)}</p>${spectatorEvidence(event)}</article>`}
function renderSpectator(){
 if(!spectator.active)return;
 $('#app').innerHTML=`<div class="watch-shell" id="watch-root"><header class="watch-header">${brand()}<div><span class="watch-readonly">별도 경기 · 읽기 전용</span><button type="button" class="text-btn" onclick="exitSpectator()">${S&&!S.demo?'우리 반으로 돌아가기':'입장 화면으로'} ${icon('arrow')}</button></div></header><main class="watch-main"><div class="watch-title"><div><p class="watch-kicker">세 가지 성향, 같은 시장</p><h1>AI 3명의 24일</h1><p>공개된 뉴스·실적·가격으로 판단하는 규칙형 자동 투자자예요. 누가 무엇을 선택하고 왜 그랬는지 함께 살펴보세요.</p></div><span class="watch-start-cash">각자 시작 자금<strong>${money(spectator.startCash)}</strong></span></div>
 ${S&&!S.demo&&S.progression?.timer_enabled?'<p class="notice">별도 관전 경기예요. 관전 중에도 우리 반 시간 모드는 계속 진행돼요.</p>':''}
 <section class="watch-controls" aria-label="관전 재생 설정"><div class="watch-play-buttons"><button type="button" class="btn dark" id="watch-play" onclick="toggleSpectator()">일시정지</button><button type="button" class="btn ghost" id="watch-next-choice" onclick="nextSpectatorChoice()">다음 선택</button><button type="button" class="btn ghost" id="watch-next-day" onclick="nextSpectatorDay()">다음 날</button></div><div class="watch-settings"><label for="watch-speed">하루 재생 시간<select class="input" id="watch-speed" onchange="setSpectatorSpeed(this.value)">${[[5,'5초'],[15,'15초'],[60,'1분']].map(([k,label])=>`<option value="${k}" ${spectator.seconds===k?'selected':''}>${label}</option>`).join('')}</select></label><label for="watch-mood">새 경기 뉴스 분위기<select class="input" id="watch-mood" onchange="setSpectatorMood(this.value)">${[['neutral','중립'],['positive','긍정'],['negative','부정']].map(([k,label])=>`<option value="${k}" ${spectator.mood===k?'selected':''}>${label}</option>`).join('')}</select></label><button type="button" class="btn secondary" id="watch-new" onclick="startSpectatorGame()">새 경기</button><button type="button" class="text-btn" id="watch-restart" onclick="restartSpectator()">처음부터</button></div><p id="watch-setting-note">속도는 재생에만 적용돼요. 분위기를 바꾸면 새 경기부터 적용해요.</p></section>
 <div id="spectator-live" class="watch-sr-only" role="status" aria-live="polite"></div><div id="watch-status"></div><div class="watch-layout"><div class="watch-stage"><section class="watch-time"><div><span id="watch-period">1분기 · 1일차</span><h2 id="watch-phase">AI의 선택을 준비하고 있어요.</h2></div><div><span id="watch-countdown-label">다음 날까지</span><b id="watch-countdown">00:15</b></div><div class="watch-progress" role="progressbar" aria-label="오늘의 진행" aria-valuemin="0" aria-valuemax="100" id="watch-progress"><i></i></div></section><div id="watch-latest"></div><div class="watch-bots" id="watch-bots"></div><section class="watch-chart-section"><div class="section-title"><h2>총자산이 어떻게 바뀌었을까?</h2><span class="sub">시작 ${money(spectator.startCash)} · 수수료 반영</span></div><div id="watch-chart"></div></section><section class="watch-news-section"><div class="section-title"><h2 id="watch-news-heading">오늘 나온 뉴스</h2><span class="sub">투자자도 이 정보까지 볼 수 있어요.</span></div><div id="watch-news"></div></section><div id="watch-ending"></div><details class="disclosure watch-method"><summary>AI는 어떤 기준으로 판단하나요?</summary><p>하루는 기사의 매출·이익 전망과 공개 실적을 비교해요. 모아는 시장 ETF·국채·금·예금에 나눠 담고 분기마다 비중을 점검해요. 번개는 최근 이틀의 가격과 미리 정한 보유·매도 기준을 살펴요.</p><p>실제 게임의 매매·수수료·예금·채권 이자·24일차 정산을 사용해 별도 경기를 계산한 뒤 재생합니다. 각 투자자는 당시 공개된 정보만 사용하며 미래 가격과 숨겨진 사건 결과를 보지 못해요. 시작 뉴스는 중립이고 선택한 분위기는 2일차부터 적용돼요.</p></details></div><aside class="watch-log-panel"><div class="section-title"><h2>선택 기록</h2><label class="watch-sr-only" for="watch-filter">투자자별 기록</label><select class="input" id="watch-filter" onchange="setSpectatorFilter(this.value)"><option value="all">세 명 모두</option>${spectatorProfiles.map(b=>`<option value="${b.id}" ${spectator.filter===b.id?'selected':''}>${b.name}</option>`).join('')}</select></div><div id="watch-log"></div></aside></div></main></div>`;
 updateSpectatorBoard();
}
function updateSpectatorClock(){
 if(!spectator.active||!$('#watch-root'))return;
 const ready=!!spectator.data&&!spectator.loading&&!spectator.error;
 const button=$('#watch-play');if(button){button.disabled=!ready||spectator.finished;button.textContent=spectator.finished?'관전 완료':spectator.playing?'일시정지':'이어서 보기'}
 ['#watch-next-choice','#watch-next-day'].forEach(id=>{if($(id))$(id).disabled=!ready||spectator.finished});
 if($('#watch-new'))$('#watch-new').disabled=spectator.loading;if($('#watch-restart'))$('#watch-restart').disabled=!ready;
 if($('#watch-mood'))$('#watch-mood').disabled=spectator.loading;
 if($('#watch-setting-note'))$('#watch-setting-note').textContent=spectator.data&&spectator.mood!==spectator.data.mood?'분위기를 바꿨어요. 새 경기를 누르면 선택한 분위기로 시작해요.':'속도는 재생에만 적용돼요. 분위기를 바꾸면 새 경기부터 적용해요.';
 const remaining=Math.max(0,Math.ceil(spectator.seconds-spectator.elapsed));
 if($('#watch-countdown'))$('#watch-countdown').textContent=spectator.finished?'완료':String(Math.floor(remaining/60)).padStart(2,'0')+':'+String(remaining%60).padStart(2,'0');
 if($('#watch-countdown-label'))$('#watch-countdown-label').textContent=spectator.finished?'24일 투자':spectator.playing?'다음 날까지':'일시정지';
 const progress=Math.min(100,Math.round(spectator.elapsed/spectator.seconds*100));if($('#watch-progress')){$('#watch-progress').setAttribute('aria-valuenow',String(progress));$('#watch-progress i').style.width=progress+'%'}
}
function updateSpectatorBoard(){
 if(!spectator.active||!$('#watch-root'))return;
 const data=spectator.data,frame=spectatorFrame();
 $('#watch-status').innerHTML=spectator.loading?'<div class="watch-loading" role="status"><i></i><div><b>세 투자자의 경기를 준비하고 있어요.</b><p>게임과 같은 규칙으로 뉴스·거래·이자를 계산하고 있어요.</p></div></div>':spectator.error?`<div class="watch-error" role="alert"><b>${esc(spectator.error)}</b><button type="button" class="btn secondary" onclick="startSpectatorGame(false)">다시 준비하기</button></div>`:'';
 $('#watch-period').textContent=frame?`${frame.quarter}분기 · ${frame.day}일차 / 24일`:'1분기 · 1일차 / 24일';
 $('#watch-phase').textContent=spectator.finished?'24일의 선택이 모두 끝났어요.':frame?.earnings?'오늘은 분기 실적 발표일이에요.':frame?'같은 소식을 보고도 선택은 달라요.':'AI의 선택을 준비하고 있어요.';
 const latest=spectator.seen.at(-1);$('#watch-latest').innerHTML=latest?`<div class="watch-latest-label">${latest.automatic?'방금 반영된 정산':'방금 한 선택'}</div>${spectatorEventMarkup(latest,true)}`:'<div class="watch-first-prompt">곧 첫 선택이 시작돼요. 일시정지하거나 ‘다음 선택’으로 한 번씩 살펴볼 수 있어요.</div>';
 $('#watch-bots').innerHTML=(data?.bots||spectatorProfiles).map(bot=>{const p=spectator.players.find(p=>p.id===bot.id),last=[...spectator.seen].reverse().find(e=>e.bot_id===bot.id&&!e.automatic);return `<article class="watch-bot" style="--bot-color:${bot.color}"><div class="watch-bot-heading"><span>${esc(bot.name.slice(0,1))}</span><div><h3>${esc(bot.name)}</h3><p>${esc(bot.style)}</p></div></div><strong>${money(p?p.net:spectator.startCash)}</strong><div class="watch-bot-return ${p?.profit<0?'down':'up'}">${p?pct(p.return_pct):'시작 자금'}</div><dl><div><dt>현금</dt><dd>${p?money(p.cash):'—'}</dd></div><div><dt>거래 수수료</dt><dd>${p?money(p.fees_paid):'—'}</dd></div><div><dt>직접 한 거래</dt><dd>${p?p.trades+'회':'—'}</dd></div></dl><p class="watch-bot-last">${last?esc(spectatorEventTitle(last)):'아직 선택 전이에요.'}</p><button type="button" class="text-btn" onclick="openSpectatorBot('${bot.id}')" ${!p?'disabled':''}>보유 자산·판단 보기 ${icon('chevron')}</button></article>`}).join('');
 $('#watch-chart').innerHTML=data?spectatorChart():'<p class="sub">경기가 시작되면 세 투자자의 총자산을 같은 차트에서 비교해요.</p>';
 $('#watch-news-heading').textContent=frame?`${frame.day}일차에 나온 뉴스`:'오늘 나온 뉴스';
 const daily=frame?(frame.news_ids||[]).map(id=>data.news.find(n=>n.id===id)).filter(Boolean):[];
 $('#watch-news').innerHTML=daily.length?daily.slice(0,6).map(n=>`<button type="button" class="watch-news-row" onclick="openSpectatorNews(${n.id})"><span>${esc(n.source||'하루경제')} · ${esc(n.certainty||'소식')}${n.is_breaking?' · 속보':''}</span><b>${esc(spectatorNewsTitle(n))}</b><p>${esc((n.reading?.summary||n.body).slice(0,190))}</p></button>`).join(''):'<p class="sub">이날 공개된 기사와 실적을 함께 보여줘요.</p>';
 $('#watch-ending').innerHTML=spectator.finished?`<section class="watch-final"><p class="watch-kicker">경기 ${data.scenario+1} · ${({neutral:'중립',positive:'긍정',negative:'부정'})[data.mood]} 분위기</p><h2>이번 경기의 최종 결과</h2><p>보유 상품 자동 매도와 수수료·예금·채권 이자까지 정산한 금액이에요.</p><div class="tablewrap"><table><thead><tr><th>순위</th><th>투자자</th><th>최종 자산</th><th>수익률</th><th>수수료</th></tr></thead><tbody>${[...spectator.players].sort((a,b)=>b.net-a.net).map((p,i)=>`<tr><td>${spectatorRank(spectator.players,p)}</td><td>${esc(spectatorBot(p.id).name)}</td><td><b>${money(p.net)}</b></td><td class="${p.profit<0?'down':'up'}">${pct(p.return_pct)}</td><td>${money(p.fees_paid)}</td></tr>`).join('')}</tbody></table></div><p class="hint">${spectatorDepositBenchmark()} 새 경기에서는 시장 흐름과 순위가 달라질 수 있어요.</p></section>`:'';
 updateSpectatorLog();updateSpectatorClock();
}
function updateSpectatorLog(){if(!$('#watch-log'))return;const all=spectator.seen.filter(e=>spectator.filter==='all'||e.bot_id===spectator.filter),events=all.slice(-spectator.logLimit).reverse();$('#watch-log').innerHTML=events.length?events.map(e=>spectatorEventMarkup(e)).join('')+(all.length>events.length?`<button type="button" class="btn secondary watch-log-more" onclick="moreSpectatorLog()">이전 선택 더 보기 · ${events.length}/${all.length}</button>`:''):'<p class="watch-log-empty">투자자가 선택하면 여기서 거래와 판단 이유를 바로 확인할 수 있어요.</p>'}
function spectatorChart(){
 const data=spectator.data,points=data.bots.map(bot=>({bot,values:[data.initial_cash,...data.frames.slice(0,spectator.dayIndex).map(f=>f.closing.find(p=>p.id===bot.id).net),spectator.players.find(p=>p.id===bot.id)?.net||data.initial_cash]}));
 const values=points.flatMap(p=>p.values),low=Math.min(...values)*.94,high=Math.max(...values)*1.06,spread=Math.max(1000,high-low),x=i=>48+i/24*474,y=v=>160-(v-low)/spread*132;
 return `<svg class="watch-chart" viewBox="0 0 540 190" role="img" aria-label="지금까지 공개된 세 투자자의 총자산 추이"><title>지금까지의 총자산 추이</title>${[low,(low+high)/2,high].map(v=>`<g><line x1="48" x2="522" y1="${y(v)}" y2="${y(v)}" stroke="#d9dfd3"/><text x="40" y="${y(v)+4}" text-anchor="end">${(v/10000).toFixed(1)}만</text></g>`).join('')}${[0,6,12,18,24].map(i=>`<text x="${x(i)}" y="181" text-anchor="middle">${i===0?'시작':i+'일'}</text>`).join('')}${points.map(({bot,values},i)=>`<polyline points="${values.map((v,j)=>x(j)+','+y(v)).join(' ')}" fill="none" stroke="${bot.color}" stroke-width="2.5" stroke-dasharray="${i===1?'7 3':i===2?'2 3':'none'}"/><circle cx="${x(values.length-1)}" cy="${y(values.at(-1))}" r="3.5" fill="${bot.color}"/>`).join('')}</svg><div class="watch-chart-legend">${data.bots.map(b=>`<span><i style="background:${b.color}"></i>${esc(b.name)} · ${esc(b.style)}</span>`).join('')}</div>`;
}
function openSpectatorNews(id){
 const n=spectator.data?.news.find(n=>n.id===id&&n.day<=spectatorFrame().day);if(!n)return;pauseSpectator();
 showModal(`<button type="button" class="modal-x" aria-label="닫기" onclick="closeModal()">${icon('close')}</button><p class="watch-kicker">${n.day}일차 · ${esc(n.source||'하루경제')} · ${esc(n.certainty||'소식')}</p><h2>${esc(spectatorNewsTitle(n))}</h2><div class="watch-article-body">${esc(n.reading?.body||n.body)}</div><p class="hint">투자자도 이 기사까지 공개된 상태에서 판단했어요.</p><button type="button" class="btn dark" onclick="closeModal();toggleSpectator()">${spectator.finished?'결과로 돌아가기':'관전 이어 보기'}</button>`,'관전 경기의 공개 기사');
}
function openSpectatorBot(id){
 const p=spectator.players.find(p=>p.id===id),bot=spectatorBot(id);if(!p)return;pauseSpectator();
 const events=spectator.seen.filter(e=>e.bot_id===id).slice(-12).reverse();
 showModal(`<button type="button" class="modal-x" aria-label="닫기" onclick="closeModal()">${icon('close')}</button><p class="watch-kicker">${esc(bot.style)} · ${spectatorFrame().day}일차 현재</p><h2>${esc(bot.name)}의 투자</h2><p class="sub">${esc(bot.description||'')}</p><div class="watch-modal-total"><b>${money(p.net)}</b><span class="${p.profit<0?'down':'up'}">${pct(p.return_pct)}</span><span>현금 ${money(p.cash)}</span></div><h3>보유 상품</h3>${p.holdings.length?`<div class="tablewrap"><table><thead><tr><th>상품</th><th>수량</th><th>평균 매수가</th><th>현재 가치</th></tr></thead><tbody>${p.holdings.map(h=>`<tr><td>${esc(h.name)}</td><td>${number(h.qty)}</td><td>${money(h.average_cost)}</td><td>${money(h.value)}</td></tr>`).join('')}</tbody></table></div>`:'<p class="sub">현재 보유한 거래 상품이 없어요.</p>'}${p.deposits.map(d=>`<p class="notice">${d.term}일 예금 · 원금 ${money(d.principal)} · ${d.status==='active'?'가입 중':'만기 정산 완료'}</p>`).join('')}<h3>최근 선택과 이유</h3>${events.map(e=>spectatorEventMarkup(e,true)).join('')||'<p class="sub">아직 선택 전이에요.</p>'}<button type="button" class="btn dark" onclick="closeModal();toggleSpectator()">${spectator.finished?'결과로 돌아가기':'관전 이어 보기'}</button>`,bot.name+'의 관전 자산과 판단');
}
setInterval(()=>tickSpectator(),200);
document.addEventListener('visibilitychange',()=>{if(document.visibilityState==='hidden'&&spectator.active)pauseSpectator()});
document.addEventListener('DOMContentLoaded',()=>{if(new URLSearchParams(location.search).get('watch')==='1')openSpectator()},{once:true});
