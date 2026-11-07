/* Before joining, A/B is a local preview. A live room owns its shared design. */
const designOptions=['classic','editorial'];
let roomDesignDraft='classic',roomDesignAdminDraft=null,roomDesignSaving=false,roomCreationDraft=null,designRoomId=null;
function currentDesign(){return document.documentElement.dataset.design||'classic'}
function applyDesignTheme(design){
 if(!designOptions.includes(design))return;
 document.documentElement.dataset.design=design;
 document.querySelector('meta[name="theme-color"]')?.setAttribute('content',design==='editorial'?'#f5f3ed':'#142f36');
 document.querySelectorAll('[data-design-choice]').forEach(button=>button.setAttribute('aria-pressed',String(button.dataset.designChoice===design)));
 const label=document.querySelector('#design-current');if(label)label.textContent=design==='editorial'?'B · 신문형':'A · 기존';
}
function setDesignPreview(design){
 if(!designOptions.includes(design))return;
 if(typeof S!=='undefined'&&S&&!S.demo)return;
 applyDesignTheme(design);roomDesignDraft=design;syncRoomDesignRadios('create',design);
 const url=new URL(window.location.href);url.searchParams.set('design',design);url.searchParams.set('compare','1');
 window.history.replaceState(null,'',url.pathname+url.search+url.hash);
}
function syncRoomDesign(data){
 if(!data||data.demo)return;
 if(designRoomId!==data.room?.id){designRoomId=data.room?.id;roomDesignAdminDraft=null}
 const design=designOptions.includes(data.room?.design)?data.room.design:'classic';
 applyDesignTheme(design);
 const current=document.querySelector('.room-design-current');if(current)current.textContent='현재 '+(design==='editorial'?'B · 신문형':'A · 기존')+' 디자인을 사용하고 있어요.';
 if(roomDesignAdminDraft===null)syncRoomDesignRadios('admin',design);
 document.querySelector('#design-comparison')?.remove();delete document.documentElement.dataset.designComparison;
 const url=new URL(window.location.href);
 if(url.searchParams.has('design')||url.searchParams.has('compare')){
  url.searchParams.delete('design');url.searchParams.delete('compare');
  window.history.replaceState(null,'',url.pathname+url.search+url.hash);
 }
}
function selectedRoomDesign(){return document.querySelector('input[name="room-design-create"]:checked')?.value||roomDesignDraft}
function syncRoomDesignRadios(scope,design){document.querySelectorAll('input[name="room-design-'+scope+'"]').forEach(input=>input.checked=input.value===design)}
function selectRoomDesign(design,scope){
 if(!designOptions.includes(design))return;
 if(scope==='create'){roomDesignDraft=design;applyDesignTheme(design)}
 else if(scope==='admin'&&!roomDesignSaving)roomDesignAdminDraft=design;
 else return;
 syncRoomDesignRadios(scope,design);
}
function roomDesignPicker(scope){
 const design=scope==='create'?roomDesignDraft:roomDesignAdminDraft??S.room.design??'classic';
 return `<fieldset class="room-design-picker"><legend>게임방 디자인</legend><div class="room-design-options">${[['classic','A · 기존','부드러운 초록색 · 카드 중심'],['editorial','B · 신문형','종이색 바탕 · 선으로 나눈 기사']].map(([key,label,desc])=>`<label class="room-design-choice"><input type="radio" name="room-design-${scope}" value="${key}" ${design===key?'checked':''} ${scope==='admin'&&roomDesignSaving?'disabled':''} onchange="selectRoomDesign(this.value,'${scope}')"><span class="design-choice-sample ${key}" aria-hidden="true"><i></i><span><b></b><b></b><b></b></span></span><span class="design-choice-copy"><b>${label}</b><small>${desc}</small></span></label>`).join('')}</div><p class="hint">${scope==='create'?'선택한 디자인을 바로 미리 볼 수 있어요. 학생들도 같은 디자인으로 입장해요.':'선택 후 적용하면 학생과 교사의 화면이 함께 바뀌어요.'}</p></fieldset>`;
}
function roomDesignControls(){
 return `<section class="card room-design-settings"><h2>게임방 디자인</h2><p class="sub room-design-current">현재 ${S.room.design==='editorial'?'B · 신문형':'A · 기존'} 디자인을 사용하고 있어요.</p>${roomDesignPicker('admin')}<button type="button" class="btn secondary" id="room-design-save" onclick="saveRoomDesign()" ${roomDesignSaving?'disabled':''}>${roomDesignSaving?'적용 중…':'선택한 디자인 적용'}</button><p class="hint">디자인만 바뀌며 게임 날짜와 투자 기록은 유지돼요.</p></section>`;
}
async function saveRoomDesign(){
 if(roomDesignSaving||S?.role!=='admin'||S.demo)return;
 const roomId=S.room.id,design=roomDesignAdminDraft??S.room.design??'classic';if(!designOptions.includes(design))return;
 roomDesignSaving=true;document.querySelectorAll('.room-design-settings input,.room-design-settings button').forEach(el=>el.disabled=true);
 const button=document.querySelector('#room-design-save');if(button)button.textContent='적용 중…';
 try{const result=await api('/admin/design',{method:'POST',body:{design}});if(S?.room?.id===roomId){S.room.design=result.design;roomDesignAdminDraft=null;syncRoomDesign(S);toast('게임방 디자인을 적용했어요. 학생 화면에도 반영돼요.')}}
 catch(e){toast(e.message)}finally{roomDesignSaving=false;document.querySelectorAll('.room-design-settings input,.room-design-settings button').forEach(el=>el.disabled=false);const button=document.querySelector('#room-design-save');if(button)button.textContent='선택한 디자인 적용'}
}
function captureRoomCreationDraft(){
 if(typeof authMode==='undefined'||authMode!=='create'||!document.querySelector('#roomName'))return;
 roomCreationDraft={name:document.querySelector('#roomName').value,password:document.querySelector('#pw').value,cash:document.querySelector('#startCash').value};
}
function restoreRoomCreationDraft(){
 if(!roomCreationDraft||typeof authMode==='undefined'||authMode!=='create'||!document.querySelector('#roomName'))return;
 document.querySelector('#roomName').value=roomCreationDraft.name;document.querySelector('#pw').value=roomCreationDraft.password;document.querySelector('#startCash').value=roomCreationDraft.cash;
 roomCreationDraft=null;
}
function clearRoomCreationDraft(){roomCreationDraft=null}
function closeDesignComparison(){
 document.querySelector('#design-comparison')?.remove();delete document.documentElement.dataset.designComparison;
 const url=new URL(window.location.href);
 if(currentDesign()==='classic'){url.searchParams.delete('design');url.searchParams.delete('compare')}
 else url.searchParams.set('compare','0');
 window.history.replaceState(null,'',url.pathname+url.search+url.hash);
}
function mountDesignComparison(){
 if(typeof S!=='undefined'&&S&&!S.demo)return;
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
 roomDesignDraft=currentDesign();
 document.querySelector('meta[name="theme-color"]')?.setAttribute('content',currentDesign()==='editorial'?'#f5f3ed':'#142f36');
 if(designOptions.includes(design)&&query.get('compare')!=='0')document.documentElement.dataset.designComparison='';
 if(document.readyState==='loading')document.addEventListener('DOMContentLoaded',mountDesignComparison,{once:true});else mountDesignComparison();
}
