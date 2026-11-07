/* A visual comparison only. The normal game keeps its existing design.
 * Theme selection lives in this tab's URL, never in a room or player record. */
const designOptions=['classic','editorial'];
function currentDesign(){return document.documentElement.dataset.design||'classic'}
function setDesignPreview(design){
 if(!designOptions.includes(design))return;
 document.documentElement.dataset.design=design;
 const url=new URL(window.location.href);url.searchParams.set('design',design);url.searchParams.set('compare','1');
 window.history.replaceState(null,'',url.pathname+url.search+url.hash);
 document.querySelector('meta[name="theme-color"]')?.setAttribute('content',design==='editorial'?'#f5f3ed':'#142f36');
 document.querySelectorAll('[data-design-choice]').forEach(button=>button.setAttribute('aria-pressed',String(button.dataset.designChoice===design)));
 const label=document.querySelector('#design-current');if(label)label.textContent=design==='editorial'?'B · 신문형':'A · 기존';
}
function closeDesignComparison(){
 document.querySelector('#design-comparison')?.remove();delete document.documentElement.dataset.designComparison;
 const url=new URL(window.location.href);
 if(currentDesign()==='classic'){url.searchParams.delete('design');url.searchParams.delete('compare')}
 else url.searchParams.set('compare','0');
 window.history.replaceState(null,'',url.pathname+url.search+url.hash);
}
function mountDesignComparison(){
 if(!document.documentElement.hasAttribute('data-design-comparison')||document.querySelector('#design-comparison'))return;
 const bar=document.createElement('aside');bar.id='design-comparison';bar.setAttribute('aria-label','디자인 비교');
 bar.innerHTML='<div class="design-compare-title"><b>디자인 비교</b><span id="design-current" aria-live="polite"></span></div><div class="design-compare-options" role="group" aria-label="화면 디자인"><button type="button" data-design-choice="classic" onclick="setDesignPreview(\'classic\')">A · 기존</button><button type="button" data-design-choice="editorial" onclick="setDesignPreview(\'editorial\')">B · 신문형</button></div><span class="design-compare-note">같은 뉴스 · 같은 투자 기능</span><button type="button" class="design-compare-close" onclick="closeDesignComparison()" aria-label="디자인 비교 닫기">닫기 ×</button>';
 document.body.appendChild(bar);
 const design=currentDesign();bar.querySelector('#design-current').textContent=design==='editorial'?'B · 신문형':'A · 기존';
 bar.querySelectorAll('[data-design-choice]').forEach(button=>button.setAttribute('aria-pressed',String(button.dataset.designChoice===design)));
}
function editorialAuthStory(){return `<div class="editorial-auth-story"><div class="edition-kicker">우리 반 금융 수업 · 24일</div><h1>24일 동안,<br>뉴스를 읽고<br>투자해 보세요.</h1><p>하루가 지나면 새 가격이 열리고,<br>6일마다 회사의 실적이 발표돼요.</p><div class="edition-calendar" aria-label="24일 게임의 분기 실적 발표 일정">${[1,2,3,4].map(q=>`<div><span>${q}분기</span><b>${q*6}일차</b><small>실적 발표</small></div>`).join('')}</div><div class="edition-footnote"><span>뉴스 읽기 → 판단하기 → 결과 돌아보기</span><span>가상 기업 20곳 · 실제 돈 사용 없음</span></div></div>`}
{
 const query=new URLSearchParams(window.location.search),design=query.get('design');
 document.documentElement.dataset.design=designOptions.includes(design)?design:'classic';
 document.querySelector('meta[name="theme-color"]')?.setAttribute('content',currentDesign()==='editorial'?'#f5f3ed':'#142f36');
 if(designOptions.includes(design)&&query.get('compare')!=='0')document.documentElement.dataset.designComparison='';
 if(document.readyState==='loading')document.addEventListener('DOMContentLoaded',mountDesignComparison,{once:true});else mountDesignComparison();
}
