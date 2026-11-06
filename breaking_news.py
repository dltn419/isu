"""Private, seeded schedules for rare news; publish facts and opening prices together."""
import itertools
import json
import random

import classroom_engine as engine
import market_expectations as expectations

FIRST_BY = 15
LAST_DAY = 22
MIN_GAP = 4

# These are fictional business events, not instructions or real-company news.
STORIES = {
    '기술': (('초대형 기술 공급 계약 최종 체결', 'contract'), ('핵심 제품 결함과 대규모 추가 비용 확인', 'cost')),
    '항공': (('대형 국제 운송 계약 최종 체결', 'contract'), ('주요 운항·정비 차질 긴급 확인', 'supply')),
    '식품': (('전국 유통망 초대형 공급 계약 체결', 'contract'), ('주력 제품 판매 중단·회수 확인', 'cost')),
    '의료·제약': (('핵심 연구 성공과 대형 기술 계약 확정', 'research'), ('핵심 연구 중단과 추가 비용 확정', 'research')),
    '미래사업': (('초대형 설비 공급 계약 최종 체결', 'contract'), ('핵심 설비 결함·납품 중단 확인', 'supply')),
}


def ensure_plan(c, rid, seed, not_before=2):
    saved = c.execute('SELECT dates FROM breaking_plans WHERE room_id=?', (rid,)).fetchone()
    if saved:
        return json.loads(saved['dates'])
    rng = random.Random(seed + 739391)
    count = rng.choices((1,2,3), weights=(50,35,15))[0]
    eligible = [d for d in range(max(4,not_before),LAST_DAY+1) if d not in (6,12,18)]
    # An older game already beyond the deadline can only receive future news.
    if not eligible and not_before <= 24:
        eligible = [not_before]
    dates = []
    for n in range(min(count,len(eligible)),0,-1):
        choices = [ds for ds in itertools.combinations(eligible,n)
                   if (not_before > FIRST_BY or ds[0] <= FIRST_BY)
                   and all(b-a >= MIN_GAP for a,b in zip(ds,ds[1:]))]
        if choices:
            dates = list(rng.choice(choices))
            break
    c.execute('INSERT INTO breaking_plans(room_id,seed,dates,not_before) VALUES(?,?,?,?)',
              (rid, seed, json.dumps(dates), not_before))
    return dates


def publish_open(c, rid, day, seed, mood, assets):
    """Caller owns the transaction, including the resulting current-day quote."""
    released = [dict(r) for r in c.execute('SELECT * FROM breaking_releases WHERE room_id=? ORDER BY slot', (rid,))]
    today = {r['asset']: r['shock'] for r in released if r['day'] == day}
    if today or day > 24:
        return today
    if len(released) >= 3:
        return {}
    dates = ensure_plan(c,rid,seed,not_before=day)
    used = {r['slot'] for r in released}
    due = next((i for i,d in enumerate(dates) if i not in used and d <= day), None)
    if due is None or (released and day-max(r['day'] for r in released) < MIN_GAP):
        return {}
    rng = random.Random(seed + 999983 + due*15485863 + day*131)
    used_assets = {r['asset'] for r in released}
    a = rng.choice([a for a in assets if a['type']=='stock' and a['id'] not in used_assets])
    positive = rng.random() < {'positive':.68,'neutral':.5,'negative':.3}[mood]
    direction = 1 if positive else -1
    title, kind = STORIES[a['sector']][0 if positive else 1]
    magnitude = rng.uniform(.18,.30)
    metrics = expectations.target_metrics(kind,direction,magnitude)
    metrics['status'] = 'confirmed'
    end = min(24,day+5)
    event = c.execute('''INSERT INTO business_events(room_id,asset,kind,direction,magnitude,start_day,due_day,
                        stage,title,result,resolved_day,horizon,expected_start,expected_end,
                        model_version,target_revenue_delta,target_margin_delta)
                        VALUES(?,?,?,?,?,?,?,'confirmed',?,?,?,'short',?,?,2,?,?)''',
                      (rid,a['id'],kind,direction,magnitude,day,day,title,title,day,day,end,
                       metrics['revenue_pct']/100,metrics['margin_pp']/100)).lastrowid
    engine.add_operating_effect(c,rid,event,a['id'],day,end,metrics['revenue_pct']/100,
                                metrics['margin_pp']/100,'사업 운영 효과',ramp=1)
    reference = c.execute('''SELECT revenue,margin FROM financials WHERE room_id=? AND asset=?
                             AND day<=? ORDER BY quarter DESC LIMIT 1''', (rid,a['id'],day)).fetchone()
    metrics['reference_revenue'] = reference['revenue']
    metrics['reference_margin_pct'] = reference['margin']
    # Record these now-public facts so later earnings do not reward the same news again.
    expectations.revise_event(c,rid,event,a['id'],day,metrics,day,end,'short',weight=1,
                              reference_margin=reference['margin']/100,ramp_days=1,fade_days=0)
    body = (f"{a['name']}의 중대한 사업 변화가 긴급 공시로 확인됐습니다. {title}. "
            '속보와 큰 가격 반응은 오늘 시작 가격에 함께 반영됐습니다. '
            + expectations.metric_sentence(metrics,confirmed=True)
            + f'{day}~{end}일차 실제 영업에 적용되며 해당 기간의 분기 실적과 함께 확인할 수 있습니다. '
            '가격이 크게 움직였다는 사실만으로 다음 날도 같은 방향일 것이라고 단정할 수 없습니다.')
    nid = engine.article(c,rid,day,f"{a['name']}, {title}",body,a['id'],0,
                         source='시장 속보센터',certainty='사실 확인',event_id=event,related=[a['id']],
                         lens='갑작스러운 변화가 내 투자 이유와 위험을 어떻게 바꾸었나요?',
                         expected_start=day,expected_end=end,metrics=metrics)
    c.execute('UPDATE news SET is_breaking=1 WHERE id=?', (nid,))
    shock = round(direction*rng.uniform(20,30),4)
    c.execute('INSERT INTO breaking_releases VALUES(?,?,?,?,?,?)', (rid,due,day,nid,a['id'],shock))
    return {a['id']:shock}
