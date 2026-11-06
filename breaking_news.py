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
CLUES = {
    '기술': ('대형 기술 공급 계약 협상 진전 보도','대형 기술 공급 계약 협상 결렬','핵심 제품 품질 문제 추가 점검','제품 추가 점검 통과·공급 차질 우려 해소'),
    '항공': ('대형 운송 계약 막바지 협상 보도','대형 운송 계약 협상 결렬','정비 추가 점검·운항 차질 우려','정비 점검 통과·운항 정상화 확인'),
    '식품': ('전국 유통망 공급 협상 진전 보도','전국 유통망 공급 협상 결렬','주력 제품 품질 점검 확대','품질 점검 통과·판매 중단 우려 해소'),
    '의료·제약': ('핵심 연구 검증 진전·기술 협상 보도','핵심 연구 최종 검증 차질 확인','추가 검증 요구·연구 중단 우려','추가 검증 통과·연구 재개 확인'),
    '미래사업': ('초대형 설비 계약 막바지 협상 보도','초대형 설비 계약 협상 결렬','핵심 설비 추가 검수·납품 차질 우려','설비 검수 통과·납품 정상화 확인'),
}


def prepare_cases(c,rid,seed,assets):
    dates=ensure_plan(c,rid,seed)
    releases={r['slot']:r['asset'] for r in c.execute('SELECT slot,asset FROM breaking_releases WHERE room_id=?',(rid,))}
    used={r['asset'] for r in c.execute('SELECT asset FROM breaking_cases WHERE room_id=?',(rid,))}|set(releases.values())
    for slot,date in enumerate(dates):
        if slot in releases or c.execute('SELECT 1 FROM breaking_cases WHERE room_id=? AND slot=?',(rid,slot)).fetchone():
            continue
        rng=random.Random(seed+slot*15485863+3266489917)
        a=rng.choice([a for a in assets if a['type']=='stock' and a['id'] not in used]);used.add(a['id'])
        warning=max(1,date-rng.randint(2,4))
        c.execute('INSERT INTO breaking_cases VALUES(?,?,?,?,?,NULL,NULL)',
                  (rid,slot,a['id'],warning,int(slot==0 or rng.random()<.8)))
    return dates


def publish_clues(c,rid,day,seed,mood,assets):
    dates=prepare_cases(c,rid,seed,assets)
    amap={a['id']:a for a in assets}
    for case in c.execute('SELECT * FROM breaking_cases WHERE room_id=? ORDER BY slot',(rid,)).fetchall():
        if not case['has_hint'] or case['clue_news_id'] or case['warning_day']>day or dates[case['slot']]<=day:
            continue
        rng=random.Random(seed+case['slot']*15485863+433494437)
        direction=1 if rng.random()<{'positive':.68,'neutral':.5,'negative':.3}[mood] else -1
        a=amap[case['asset']];title=CLUES[a['sector']][0 if direction>0 else 2]
        body=(f"{a['name']}에 대해 {title}가 나왔습니다. "
              + ('사업 확대 가능성이 커지고 있다는 취재 내용입니다. ' if direction>0 else '추가 비용이나 사업 차질 가능성을 살펴야 한다는 취재 내용입니다. ')
              + '아직 최종 계약이나 조사 결과가 확정된 공시는 아닙니다. 가까운 시일의 후속 발표와 기존 실적을 함께 확인하세요. '
              + '처음의 기대나 우려와 반대로 결론 날 수도 있으므로 한 기사만으로 투자를 확신하지 마세요.')
        nid=engine.article(c,rid,day,f"{a['name']}, {title}",body,a['id'],direction*1.2,
                           kind='signal',source='산업 취재팀',certainty='취재·미확정',related=[a['id']],
                           lens='이 단서가 맞다면 무엇이 바뀌고, 반대 결과가 나오면 어떻게 할까요?')
        c.execute('UPDATE news SET is_signal=1 WHERE id=?',(nid,))
        c.execute('UPDATE breaking_cases SET signal_direction=?,clue_news_id=? WHERE room_id=? AND slot=?',
                  (direction,nid,rid,case['slot']))


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
    prepare_cases(c,rid,seed,assets)
    case=c.execute('SELECT * FROM breaking_cases WHERE room_id=? AND slot=?',(rid,due)).fetchone()
    a=next(a for a in assets if a['id']==case['asset'])
    if case['clue_news_id']:
        direction=case['signal_direction']*(1 if rng.random()<.75 else -1)
        title,kind=STORIES[a['sector']][0 if case['signal_direction']>0 else 1]
        if direction!=case['signal_direction']:
            title=CLUES[a['sector']][1 if case['signal_direction']>0 else 3]
    else:
        direction=1 if rng.random()<{'positive':.68,'neutral':.5,'negative':.3}[mood] else -1
        title,kind=STORIES[a['sector']][0 if direction>0 else 1]
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
    if case['clue_news_id']:
        body+=' 앞서 보도한 취재 단서의 후속 확인입니다. '+('당초 단서와 같은 방향으로 확인됐습니다.' if direction==case['signal_direction'] else '당초 단서와 반대인 결과가 확인됐습니다.')
        c.execute('UPDATE news SET event_id=?,pricing_end=? WHERE id=?',(event,day-1,case['clue_news_id']))
    nid = engine.article(c,rid,day,f"{a['name']}, {title}",body,a['id'],0,
                         source='시장 속보센터',certainty='사실 확인',event_id=event,related=[a['id']],
                         lens='갑작스러운 변화가 내 투자 이유와 위험을 어떻게 바꾸었나요?',
                         expected_start=day,expected_end=end,metrics=metrics)
    c.execute('UPDATE news SET is_breaking=1 WHERE id=?', (nid,))
    shock = round(direction*rng.uniform(20,30),4)
    c.execute('INSERT INTO breaking_releases VALUES(?,?,?,?,?,?)', (rid,due,day,nid,a['id'],shock))
    return {a['id']:shock}
