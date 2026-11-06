/* ETF composition and the shared classroom ending. Data comes from the server. */
function etfCompositionPanel(a){
 const c=a.etf_composition;if(!c)return emptyState('구성 정보를 불러오지 못했어요. 새로고침해 주세요.');
 const leveraged=c.multiplier!==1,h=(S.holdings||[]).find(x=>x.asset===a.id),weight=n=>(n*100).toFixed(1).replace(/\.0$/,'')+'%';
 return `<div class="etf-composition"><div class="section-title"><div><h2>${leveraged?'기준지수 구성 종목·비중':'ETF 구성 종목·비중'}</h2><p class="sub no-margin">${c.company_count}개 기업 · ${c.sectors.length}개 업종 · 매일 같은 목표 비중 적용</p></div><span class="tag">합계 100%</span></div>
 ${leveraged?`<p class="notice">이 표는 따라가는 <b>기준지수</b>의 구성이에요. ${c.multiplier===2?'하루 지수 수익률의 약 2배':'하루 지수 수익률의 약 −2배'}를 목표로 가격이 움직여요. 여러 날의 누적 수익률은 단순한 ${c.multiplier===2?'2배':'−2배'}와 달라질 수 있어요.</p>`:'<p class="hint">ETF를 사면 아래 기업들의 가격 움직임을 이 비중으로 함께 따라가요. 소폭의 추적 오차와 게임 내 운용비용도 가격에 반영돼요.</p>'}
 ${h&&S.player?.net?`<div class="etf-my-weight"><span>내 총자산 중 이 ETF의 비중</span><b>${weight(h.qty*a.price/S.player.net)}</b></div>`:''}
 <div class="etf-sector-weights" aria-label="업종별 구성 비중">${c.sectors.map(s=>{const color=sectorColors[s.sector]?.[1]||'#6b8b72';return `<div><div><span>${esc(s.sector)}</span><b>${weight(s.weight)}</b></div><div class="weight-track"><i style="width:${s.weight*100}%;background:${color}"></i></div></div>`}).join('')}</div>
 <div class="tablewrap etf-holdings"><table><thead><tr><th>구성 기업</th><th>업종</th><th>${leveraged?'기준지수 내 비중':'ETF 안의 비중'}</th></tr></thead><tbody>${c.holdings.map(h=>`<tr><td><button class="text-btn" onclick="detail('${h.asset}')">${esc(h.name)} ${icon('chevron')}</button></td><td>${esc(h.sector)}</td><td><b>${weight(h.weight)}</b></td></tr>`).join('')}</tbody></table></div><p class="hint">분산왕을 정할 때도 이 구성으로 펼쳐서 계산해요. 같은 기업이 여러 ETF에 들어 있으면 그 비중을 합쳐요.</p></div>`;
}

function newsAssetRelation(n,a){
 if(!a||n.day>S.room.day||n.active===0)return null;
 const ids=new Set([n.sector,...(n.related_assets||[])]);
 if(ids.has(a.id))return {kind:'direct',priority:4,label:'이 상품에 직접 연결된 소식'};
 if(a.type!=='etf')return null;
 if(n.sector==='전체')return {kind:'market',priority:1,label:'시장 전체에 관한 소식'};
 const composition=a.etf_composition;if(!composition)return null;
 const basis=composition.multiplier===1?'ETF':'기준지수';
 const percent=w=>(w*100).toFixed(1).replace(/\.0$/,'')+'%';
 const sector=composition.sectors.find(s=>s.sector===n.sector);
 if(sector)return {kind:'sector',priority:2,label:`${sector.sector} 업종 · ${basis} 구성 ${percent(sector.weight)}`};
 const primary=composition.holdings.find(h=>h.asset===n.sector);
 const companies=primary?[primary]:composition.holdings.filter(h=>ids.has(h.asset));
 if(!companies.length)return null;
 const weight=companies.reduce((sum,h)=>sum+h.weight,0),name=companies[0].name+(companies.length>1?` 외 ${companies.length-1}개 기업`:'');
 return {kind:'company',priority:3,label:`${name} · ${basis} 구성 ${percent(weight)}`};
}
function newsMatchesAsset(n,a){return !!newsAssetRelation(n,a)}
function relatedAssetNews(a,limit=12){
 const seen=new Set();
 const list=(S.news||[]).filter(n=>{if(seen.has(n.id)||!newsMatchesAsset(n,a)||(a.type!=='etf'&&n.kind==='earnings'))return false;seen.add(n.id);return true});
 list.sort((x,y)=>y.day-x.day||Number(!!y.is_breaking)-Number(!!x.is_breaking)||Number(y.kind==='earnings')-Number(x.kind==='earnings')||newsAssetRelation(y,a).priority-newsAssetRelation(x,a).priority||y.id-x.id);
 return limit===null?list:list.slice(0,limit);
}
function etfNewsBadge(n,a){
 const relation=a?.type==='etf'?newsAssetRelation(n,a):null;
 return relation?`<div class="etf-news-context">${icon('link')}<span>${esc(relation.label)}</span></div>`:'';
}
function etfNewsIntro(a){
 const multiplier=a.etf_composition?.multiplier||1;
 return `<p class="notice etf-news-intro">${esc(a.name)}에 담긴 기업과 업종, 시장 전체의 소식을 모았어요. 기업 비중과 다른 기업의 움직임이 함께 작용해요.${multiplier<0?'<br><b>인버스는 기준지수와 반대 방향을 목표로 해요.</b> 구성 기업의 호재가 이 ETF에는 하락 요인이 될 수 있어요.':multiplier>1?'<br>2배 상품은 하루 지수 수익률의 약 2배를 목표로 해요. 여러 날의 누적 수익률은 단순한 2배와 달라질 수 있어요.':''}</p>`;
}
function etfRelatedNewsPanel(a){
 const all=relatedAssetNews(a,null),recent=all.slice(0,12);
 return `<div class="section-title"><div><h2>이 ETF의 관련 뉴스</h2><p class="sub no-margin">최근 ${recent.length}건 · 구성 기업·업종·시장 소식</p></div><button class="text-btn" onclick="showAssetNews('${a.id}')">관련 뉴스 ${all.length}건 모아보기 ${icon('arrow')}</button></div>${etfNewsIntro(a)}${newsCards(recent,true,a)}`;
}
function showAssetNews(aid){
 newsFocus=aid;newsScope='all';newsSector='전체';newsHorizon='all';newsMode='all';newsLayout='all';newsAdvanced=false;go('news');
}
function currentEtfNewsContext(n){
 const a=currentView()==='detail'?asset(selected):currentView()==='news'?asset(newsFocus):null;
 return a?.type==='etf'&&newsMatchesAsset(n,a)?a:null;
}

function finaleInvestmentCard(card,gain,index){
 const label=gain?'수익을 남긴 투자':'돌아볼 투자';
 if(!card)return `<article class="finale-investment finale-empty"><span class="finale-kicker">${label} ${index+1}</span><p>${gain?'수익':'손실'}이 확정된 다른 투자 기록이 없어요.</p></article>`;
 const qtyUnit=asset(card.asset)?.type==='gold'?'g':'주';
 const quantity=card.kind==='deposit'?'정기예금':card.peak_quantity===card.quantity?`보유 ${number(card.quantity)}${qtyUnit}`:`누적 매수 ${number(card.quantity)}${qtyUnit} · 최대 보유 ${number(card.peak_quantity)}${qtyUnit}`;
 return `<article class="finale-investment ${gain?'gain':'review'}"><div class="flex"><span class="finale-kicker">${label} ${index+1}</span><span class="tag">${card.automatic?'종료 자동 정산':card.kind==='deposit'?'예금 정산':'기간 중 매도'}</span></div><h3>${esc(card.name)}<span>의 ${esc(card.asset_name)} 투자</span></h3><p class="sub">${card.start_day}~${card.end_day}일차 · ${card.holding_days===1?'당일 투자':card.holding_days+'일간'} · ${quantity}</p><div class="finale-profit ${card.profit>=0?'up':'down'}">${card.profit>0?'+':''}${money(card.profit)}<small>${pct(card.return_pct)}</small></div><div class="finale-card-numbers"><span>${card.kind==='deposit'?'예치 원금':'총 매수금액'} <b>${money(card.invested)}</b></span><span>수수료 <b>${money(card.fees)}</b></span>${card.interest?`<span>보유 중 발생 이자 <b>${money(card.interest)}</b></span>`:''}</div><p class="hint no-margin">${card.kind==='deposit'?'받은 이자를 반영한 최종 손익이에요.':'매수·매도 수수료'+(card.interest?'와 보유 중 발생한 채권 이자':'')+'를 반영한 실현손익이에요.'}</p></article>`;
}

function finaleView(){
 const f=S.finale;if(!f)return emptyState('최종 결산을 불러오는 중이에요. 새로고침해 주세요.');
 const me=f.standings.find(p=>p.player_id===S.player?.id),teacher=S.role==='admin';
 return `<section class="finale-hero"><div><div class="eyebrow">24 DAYS, YOUR INVESTMENT STORY</div><h2>24일의 투자,<br>어떤 이야기가 남았나요?</h2><p>${f.settled?'마지막 시세로 보유 상품을 모두 정산했어요. 수수료와 이자까지 반영한 결과예요.':'이전에 종료한 게임의 기록이에요. 당시 자산 평가와 실제 매도 기록을 그대로 보여줘요.'}</p></div>${me?`<div class="finale-my-result"><span>나의 최종 ${f.settled?'현금':'자산'}</span><strong>${money(me.net)}</strong><span>투자 손익 <b>${me.profit>0?'+':''}${money(me.profit)} · ${pct(me.return_pct)}</b></span><span>최종 <b>${me.rank}위</b> / ${f.standings.length}명</span></div>`:`<div class="finale-class-result"><strong>${f.standings.length}<small>명의 투자 이야기</small></strong><p>수익을 만든 선택과<br>다시 살펴볼 선택을 함께 찾아보세요.</p></div>`}</section>
 <div class="finale-section-title"><div><span class="eyebrow">OUR FOUR MOMENTS</span><h2>우리 반 투자 돌아보기</h2></div><span class="sub">수익 2건 · 손실 2건 · 실현손익 금액 기준</span></div><div class="finale-highlights">${[0,1].map(i=>finaleInvestmentCard(f.highlights.gains[i],true,i)).join('')}${[0,1].map(i=>finaleInvestmentCard(f.highlights.reviews[i],false,i)).join('')}</div>
 <p class="hint">결과와 함께 당시 뉴스와 판단 이유도 다시 살펴보세요. 수익이나 손실만으로 판단의 좋고 나쁨을 정하지 않아요.</p>
 <div class="finale-section-title"><div><span class="eyebrow">EVERY INVESTOR HAS A STYLE</span><h2>우리 반 투자 스타일</h2></div><span class="sub">재미 칭호 · 점수 보너스 없음</span></div><div class="finale-awards">${f.awards.map(a=>`<article class="card finale-award"><span class="award-emoji" aria-hidden="true">${a.emoji}</span><div><h3>${esc(a.title)}</h3>${a.winners.length?`<p class="award-names">${a.winners.map(w=>esc(w.name)).join(' · ')}${a.winners.length>1?'<small> 공동 수상</small>':''}</p>${a.winners.map(w=>`<div class="award-metric"><b>${a.id==='longest'?number(w.value)+'일':a.id==='diversity'?w.value.toFixed(1)+'점':w.value.toFixed(1)+'%'}</b><span>${esc(w.detail)}</span></div>`).join('')}`:'<p class="sub">이번에는 기준을 충족한 기록이 없어요.</p>'}<details class="disclosure"><summary>선정 기준</summary><p class="hint">${esc(a.rule)}</p></details></div></article>`).join('')}</div>
 <section class="card finale-standings"><div class="section-title"><h2>최종 순위</h2><span class="sub">교사 현금 지급·차감 제외 · 동률은 공동 순위</span></div><div class="tablewrap"><table><thead><tr><th>순위</th><th>학생</th><th>최종 ${f.settled?'현금':'자산'}</th><th>투자 손익</th><th>수익률</th><th>누적 수수료</th></tr></thead><tbody>${f.standings.map(p=>`<tr class="${p.player_id===me?.player_id?'my-final-row':''}"><td>${p.rank}위</td><td>${esc(p.name)}${p.player_id===me?.player_id?' · 나':''}</td><td>${money(p.net)}</td><td class="${p.profit>=0?'up':'down'}">${p.profit>0?'+':''}${money(p.profit)}</td><td class="${p.profit>=0?'up':'down'}">${pct(p.return_pct)}</td><td>${money(p.fees)}</td></tr>`).join('')}</tbody></table></div>${!f.standings.length?emptyState('참가한 학생이 없어요.'):''}</section>
 <details class="disclosure finale-rules"><summary>결산과 집계 기준 보기</summary>${f.settled?`<p>주식·ETF·채권·금은 24일차 마지막 시세로 자동 매도했어요. 자동 매도도 ${feeRateLabel()} · 최소 1원 수수료가 적용돼요. 채권은 마지막 날 이자를 먼저 적립·지급하고, 예금은 약정에 따라 정산해요.</p><p>자동 매도 ${number(f.liquidation_count)}건 · 해당 매도 수수료 합계 ${money(f.liquidation_fees)}</p>`:'<p>이전 결산 금액을 바꾸지 않았어요. 자동 현금 정산은 이 기능을 적용한 뒤 종료하는 게임부터 사용해요.</p>'}${f.rules.map(rule=>`<p>${esc(rule)}</p>`).join('')}</details>
 <div class="finale-actions"><button class="btn dark" onclick="${teacher?"goTeacher('players')":"go('journal')"}">${icon('journal')} ${teacher?'학생들의 판단 기록 보기':'나의 판단 기록 보기'}</button><button class="btn secondary" onclick="${teacher?"goTeacher('market')":"go('market')"}">마지막 시장 살펴보기 ${icon('arrow')}</button>${teacher?'<button class="text-btn" onclick="goTeacher(\'admin\')">새 게임은 운영 설정에서 시작해요 →</button>':''}</div>`;
}
