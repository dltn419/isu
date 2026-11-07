/* Amount entry is a budget-to-integer-quantity conversion. The server still
 * verifies the current quote, cash, holdings and fee before every fill. */
const MAX_ORDER_QTY=100000;
let tradeSubmitting=false;
function tradeUnit(a){return a?.type==='gold'?'g':'주'}
function quantityForAmount({amount,price,side,cash=0,held=0}){
 if(!Number.isSafeInteger(amount)||amount<1||!Number.isSafeInteger(price)||price<1)return 0;
 if(side==='sell')return Math.max(0,Math.min(MAX_ORDER_QTY,Math.floor(amount/price),held));
 if(side!=='buy')return 0;
 const budget=Math.max(0,Math.min(amount,cash));
 let low=0,high=Math.min(MAX_ORDER_QTY,Math.floor(budget/price));
 while(low<high){const mid=Math.ceil((low+high)/2),gross=mid*price;if(gross+quoteFee(gross)<=budget)low=mid;else high=mid-1}
 return low;
}
function tradeEntryFields(a){
 const draft=tradeDrafts[a.id]||{},amountMode=draft.entryMode==='amount';
 return `<div class="trade-entry-mode" role="group" aria-label="주문 입력 방식"><button type="button" data-entry-mode="quantity" aria-pressed="${!amountMode}" class="${amountMode?'':'active'}" onclick="setTradeEntryMode('quantity')">수량으로</button><button type="button" data-entry-mode="amount" aria-pressed="${amountMode}" class="${amountMode?'active':''}" onclick="setTradeEntryMode('amount')">금액으로</button></div>
 <div id="quantity-order-fields" class="trade-input-fields" ${amountMode?'hidden':''}><label for="qty">수량 · ${tradeUnit(a)}</label><input class="input" id="qty" type="number" min="1" max="${MAX_ORDER_QTY}" step="1" value="1" oninput="updateOrderTotal()" ${amountMode?'readonly':''}></div>
 <div id="amount-order-fields" class="trade-input-fields" ${amountMode?'':'hidden'}><label id="orderAmountLabel" for="orderAmount">${currentSide==='buy'?'매수 예산':'매도 금액'} · 원</label><div class="trade-amount-input"><input class="input" id="orderAmount" type="number" min="1" step="1" inputmode="numeric" placeholder="예: 100000" aria-describedby="amount-order-rule amount-order-hint" oninput="updateOrderTotal()"><span>원</span></div><p id="amount-order-rule" class="hint"></p><div class="amount-conversion" aria-live="polite"><span>계산된 수량</span><strong id="amount-order-quantity">0${tradeUnit(a)}</strong></div><p id="amount-order-hint" class="hint" aria-live="polite"></p></div>`;
}
function captureTradeDraft(){
 const meta=$('#trade-meta');if(!meta||!$('#qty')||!$('#reason'))return;
 tradeDrafts[meta.dataset.asset]={qty:$('#qty').value,amount:$('#orderAmount')?.value||'',entryMode:meta.dataset.entryMode||'quantity',reason:$('#reason').value,ids:pickedEvidence('trade-evidence')};
}
function restoreTradeDraft(){
 if(!$('#trade-meta')||!$('#qty'))return;
 const draft=tradeDrafts[selected]||{};
 $('#qty').value=draft.qty??1;
 if($('#orderAmount'))$('#orderAmount').value=draft.amount??'';
 $('#reason').value=draft.reason||'';
 document.querySelectorAll('#trade-evidence input').forEach(el=>el.checked=(draft.ids||[]).includes(+el.value));
 updateOrderTotal();
}
function setTradeEntryMode(mode){
 if(!['quantity','amount'].includes(mode)||!$('#trade-meta')||!$('#qty'))return;
 captureTradeDraft();
 if(mode==='amount'&&!$('#orderAmount').value){
  const a=asset(selected),q=Number($('#qty').value);
  if(a&&Number.isSafeInteger(q)&&q>0){const gross=q*a.price;$('#orderAmount').value=gross+(currentSide==='buy'?quoteFee(gross):0)}
 }
 $('#trade-meta').dataset.entryMode=mode;
 $('#quantity-order-fields').hidden=mode==='amount';$('#amount-order-fields').hidden=mode!=='amount';$('#qty').readOnly=mode==='amount';
 document.querySelectorAll('.trade-entry-mode button').forEach(el=>{const active=el.dataset.entryMode===mode;el.classList.toggle('active',active);el.setAttribute('aria-pressed',String(active))});
 updateOrderTotal();captureTradeDraft();
}
function tradeOrderQuote(){
 const a=asset(selected),mode=$('#trade-meta')?.dataset.entryMode||'quantity',data=myData(),cash=data?.player?.cash||0,held=(data?.holdings||[]).find(h=>h.asset===selected)?.qty||0;
 const amount=Number($('#orderAmount')?.value),manualQty=Number($('#qty')?.value),qty=mode==='amount'?quantityForAmount({amount,price:a?.price,side:currentSide,cash,held}):manualQty;
 let error='';
 if(!a||!Number.isSafeInteger(a.price)||a.price<1)error='현재 가격을 다시 확인해 주세요.';
 else if(mode==='amount'&&(!Number.isSafeInteger(amount)||amount<1))error='금액은 1원 이상의 정수로 입력해 주세요.';
 else if(!Number.isSafeInteger(qty)||qty<1||qty>MAX_ORDER_QTY){
  error=mode!=='amount'?'수량은 1~100,000 사이의 정수로 입력하세요.':currentSide==='sell'&&held<1?'매도할 보유 수량이 없어요.':currentSide==='buy'&&cash<a.price+quoteFee(a.price)?`가용 현금 ${money(cash)}으로는 1${tradeUnit(a)}를 살 수 없어요. 수수료 포함 ${money(a.price+quoteFee(a.price))}이 필요해요.`:`1${tradeUnit(a)} ${currentSide==='buy'?'매수에는 수수료 포함 '+money(a.price+quoteFee(a.price)):'매도 금액은 '+money(a.price)} 이상이 필요해요.`;
 }
 const usable=Number.isSafeInteger(qty)&&qty>0&&qty<=MAX_ORDER_QTY&&a?qty:0,gross=usable*(a?.price||0),fee=quoteFee(gross),settlement=gross+(currentSide==='buy'?fee:-fee);
 return {mode,amount,qty:usable,gross,fee,settlement,error,cash,held,cashCapped:mode==='amount'&&currentSide==='buy'&&amount>cash,holdingCapped:mode==='amount'&&currentSide==='sell'&&Math.floor(amount/(a?.price||1))>held};
}
function updateTradeQuote(){
 if(!$('#qty')||!$('#trade-meta'))return;
 const q=tradeOrderQuote(),a=asset(selected),amountMode=q.mode==='amount';
 if(amountMode)$('#qty').value=q.qty;
 if($('#orderAmountLabel'))$('#orderAmountLabel').textContent=(currentSide==='buy'?'매수 예산':'매도 금액')+' · 원';
 if($('#amount-order-rule'))$('#amount-order-rule').textContent=currentSide==='buy'?'수수료를 포함해 예산 안에서 살 수 있는 수량으로 내림 계산해요.':'수수료 전 거래금액이 입력 금액을 넘지 않도록 내림 계산해요. 수수료는 받을 금액에서 차감돼요.';
 if($('#amount-order-quantity'))$('#amount-order-quantity').textContent=number(q.qty)+tradeUnit(a);
 if($('#amount-order-hint')){
  let hint=q.error;
  if(!hint&&amountMode){hint=currentSide==='buy'?`실제 결제 ${money(q.settlement)} · 거래 후 현금 ${money(q.cash-q.settlement)}`:`실제 매도 ${money(q.gross)} · 수수료를 빼고 ${money(q.settlement)} 받아요.`;if(q.cashCapped)hint=`가용 현금 ${money(q.cash)}을 기준으로 계산했어요. `+hint;if(q.holdingCapped)hint=`보유한 ${number(q.held)}${tradeUnit(a)}까지만 매도해요. `+hint;if(q.qty===MAX_ORDER_QTY)hint=`한 번에 최대 ${number(MAX_ORDER_QTY)}${tradeUnit(a)}까지 주문할 수 있어요. `+hint;}
  $('#amount-order-hint').textContent=hint;$('#amount-order-hint').classList.toggle('trade-input-error',!!q.error);
 }
 if($('#orderAmount'))$('#orderAmount').setAttribute('aria-invalid',String(amountMode&&!!q.error));
 if($('#orderGross'))$('#orderGross').textContent=money(q.gross);if($('#orderFee'))$('#orderFee').textContent=money(q.fee);if($('#settlementLabel'))$('#settlementLabel').textContent=currentSide==='buy'?'총 결제액':'받을 금액';if($('#orderTotal'))$('#orderTotal').textContent=money(q.settlement);
 const button=$('.trade-submit');if(button)button.disabled=tradeSubmitting||S.role!=='player'||S.demo||S.room.phase!=='trading'||!!q.error;
 return q;
}
