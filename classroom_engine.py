"""Persistent business simulation. Published evidence and private outcomes stay separate."""
import json
import math
import random
import market_expectations as expectations

SECTORS = ['기술', '항공', '식품', '의료·제약', '미래사업']
MOOD_NAMES = {'positive': '긍정', 'neutral': '중립', 'negative': '부정'}
PROFILES = {
    '기술': ('스마트기기·반도체 공급 계약', '전자제품·서비스 주문', '부품·생산 비용', '차세대 기술 검증', '핵심 반도체 공급'),
    '항공': ('항공·물류 서비스 계약', '여객·화물 예약', '연료·운항 비용', '운항·정비 신기술 검증', '항공기·정비 부품 공급'),
    '식품': ('유통업체 입점 계약', '식품·원료 주문', '농산물·포장재 비용', '신제품 소비자 시험', '원재료 납품'),
    '의료·제약': ('병원·제약사 공급 계약', '의약품·의료장비 주문', '연구·생산 비용', '의료 기술·신약 검증', '의약품 원료 공급'),
    '미래사업': ('AI·자동화 설비 계약', '데이터센터·자동화 주문', '전력·설비 운영 비용', '차세대 장비 성능 검증', '핵심 장비 납품'),
}
COMPANY_PROFILES = {
    'HBEL': ('스마트기기·반도체 공급 계약', '스마트폰·가전 주문', '부품·생산 비용', '차세대 반도체 성능 검증', '핵심 반도체 부품 공급'),
    'NXDV': ('고급 기기 판매 제휴', '프리미엄 기기 예약 판매', '자체 칩 개발·생산 비용', '신형 기기 시제품 검증', '디스플레이·칩 공급'),
    'HBCP': ('센서·카메라 모듈 납품 계약', '전자회사 부품 주문', '센서 생산·검사 비용', '차세대 카메라 센서 검증', '센서 소재 공급'),
    'SCNT': ('기업 보안 서비스 계약', '보안 서비스 신규 가입', '서버·보안 인력 운영 비용', '위협 탐지 기술 검증', '고객사 보안 시스템 구축'),
    'NURA': ('기업 출장·항공화물 운송 계약', '국제선 여객·화물 예약', '항공유·정비 비용', '운항 효율화 기술 검증', '항공기 정비 부품 확보'),
    'LTAI': ('관광상품·단거리 노선 제휴', '단거리 항공권 예약', '항공유·공항 사용 비용', '예약·운항 효율화 시험', '운항용 항공기 확보'),
    'NUTS': ('항공기 정비 계약', '항공기 점검·수리 예약', '정비 인력·장비 비용', '항공기 고장 예측 기술 검증', '정비용 부품 확보'),
    'ARLG': ('국제화물 배송 계약', '해외 배송 물량', '운송·물류센터 운영 비용', '화물 분류 자동화 시험', '운송용 장비 확보'),
    'DDFF': ('라면·냉동식품 유통 계약', '가공식품 판매 주문', '밀가루·포장재 비용', '신제품 소비자 평가', '곡물·식품 원료 확보'),
    'GRTB': ('건강식 유통업체 입점 계약', '고단백 간편식 주문', '식재료·냉장 유통 비용', '건강식 신제품 평가', '고단백 식재료 확보'),
    'SWWV': ('디저트 브랜드 판매 제휴', '디저트·음료 주문', '설탕·유제품 비용', '신메뉴 소비자 평가', '디저트 원료 납품'),
    'FMBR': ('식품회사 농산물 납품 계약', '농산물 원료 주문', '농산물 보관·운송 비용', '농산물 신선도 보존 시험', '계약 농가 수확·출하'),
    'MDON': ('기존 의약품 공급 계약', '치료제·일반약 주문', '의약품 생산·관리 비용', '기존 약품 제조 개선 시험', '의약품 원료 확보'),
    'NFBI': ('신약 공동연구 제휴', '후보물질 기술이전 협의', '신약 임상·연구 비용', '신약 후보물질 임상 검증', '임상시험용 원료 확보'),
    'MDBW': ('바이오의약품 위탁생산 계약', '제약사 위탁생산 주문', '바이오 공장 가동 비용', '바이오의약품 생산공정 검증', '배양 원료·생산 장비 공급'),
    'CLMD': ('병원 진단장비 납품 계약', '검사장비·소모품 주문', '진단장비 생산·유지 비용', '새 진단장비 정확도 검증', '진단 센서·검사 시약 확보'),
    'BRCL': ('기업용 AI·클라우드 계약', '클라우드 서비스 이용량', '데이터센터 전력·서버 비용', '기업용 AI 기술 검증', '데이터센터 서버 확보'),
    'MORB': ('물류창고 자동화 로봇 계약', '산업용 로봇 주문', '로봇 부품·조립 비용', '차세대 로봇 성능 검증', '로봇용 모터·센서 공급'),
    'PWGR': ('전력망·저장장치 공급 계약', '전력설비·저장장치 주문', '구리·전력설비 생산 비용', '에너지저장장치 안전성 검증', '전력장비 핵심 소재 공급'),
    'COED': ('데이터센터 냉각장비 계약', '고효율 냉각장비 주문', '냉각장비 제작·설치 비용', '신형 냉각장비 효율 검증', '냉각장비 핵심 부품 공급'),
}
KINDS = ['contract', 'sales', 'cost', 'research', 'supply']
DEPOSIT_RATE = .10
TRADING_INTERVALS = 23  # Day 1 is the entry price, day 24 is the final valuation.
MARKET_ANNUAL_CARRY = .16  # Calibration assumption, never a promised return.
HORIZONS = {'short': '단기', 'next_quarter': '다음 분기', 'year_end': '연말'}
LENSES = {
    'contract': '계약 발표만으로 매출이 잡히지는 않아요. 실제 납품과 계약 규모를 확인해 보세요.',
    'sales': '판매가 늘어도 비용이 더 빠르게 늘면 이익은 줄 수 있어요.',
    'cost': '같은 매출을 올려도 비용이 줄면 회사에 남는 이익이 늘어요.',
    'research': '연구 성과는 사업 기회예요. 상용화 시점과 추가 연구비도 함께 살펴보세요.',
    'supply': '원료나 부품이 제때 도착해야 주문을 실제 매출로 바꿀 수 있어요.',
}


def query(c, sql, args=()):
    return [dict(x) for x in c.execute(sql, args).fetchall()]


def clamp(n, lo, hi):
    return max(lo, min(hi, n))


def initialize_schema(c):
    c.executescript('''
    CREATE TABLE IF NOT EXISTS businesses(
      room_id INTEGER NOT NULL, asset TEXT NOT NULL, base_revenue REAL NOT NULL,
      revenue_index REAL NOT NULL DEFAULT 1, margin REAL NOT NULL,
      cash REAL NOT NULL, debt REAL NOT NULL, growth REAL NOT NULL,
      last_day INTEGER NOT NULL, PRIMARY KEY(room_id,asset));
    CREATE TABLE IF NOT EXISTS financials(
      room_id INTEGER NOT NULL, asset TEXT NOT NULL, quarter INTEGER NOT NULL,
      day INTEGER NOT NULL, revenue INTEGER NOT NULL, profit INTEGER NOT NULL,
      margin REAL NOT NULL, cash INTEGER NOT NULL, debt INTEGER NOT NULL,
      expected_revenue INTEGER NOT NULL, expected_profit INTEGER NOT NULL,
      revenue_growth REAL NOT NULL, profit_growth REAL NOT NULL,
      surprise REAL NOT NULL, verdict TEXT NOT NULL, outlook TEXT NOT NULL,
      explanation TEXT NOT NULL, evidence_ids TEXT NOT NULL DEFAULT '[]',
      PRIMARY KEY(room_id,asset,quarter));
    CREATE TABLE IF NOT EXISTS forecasts(
      room_id INTEGER NOT NULL, asset TEXT NOT NULL, quarter INTEGER NOT NULL,
      published_day INTEGER NOT NULL, revenue INTEGER NOT NULL,
      profit INTEGER NOT NULL, PRIMARY KEY(room_id,asset,quarter));
    CREATE TABLE IF NOT EXISTS business_events(
      id INTEGER PRIMARY KEY, room_id INTEGER NOT NULL, asset TEXT NOT NULL,
      kind TEXT NOT NULL, direction INTEGER NOT NULL, magnitude REAL NOT NULL,
      start_day INTEGER NOT NULL, due_day INTEGER NOT NULL,
      stage TEXT NOT NULL DEFAULT 'developing', delayed INTEGER NOT NULL DEFAULT 0,
      title TEXT NOT NULL, result TEXT NOT NULL DEFAULT '', resolved_day INTEGER);
    CREATE TABLE IF NOT EXISTS reading_log(
      player_id INTEGER NOT NULL, room_id INTEGER NOT NULL, news_id INTEGER NOT NULL,
      day INTEGER NOT NULL, PRIMARY KEY(player_id,news_id));
    CREATE TABLE IF NOT EXISTS watchlist(
      player_id INTEGER NOT NULL, asset TEXT NOT NULL, PRIMARY KEY(player_id,asset));
    CREATE TABLE IF NOT EXISTS investment_notes(
      id INTEGER PRIMARY KEY, room_id INTEGER NOT NULL, player_id INTEGER NOT NULL,
      day INTEGER NOT NULL, asset TEXT NOT NULL, thesis TEXT NOT NULL,
      risk TEXT NOT NULL, horizon TEXT NOT NULL, evidence_ids TEXT NOT NULL DEFAULT '[]',
      reflection TEXT NOT NULL DEFAULT '', created TEXT NOT NULL);
    CREATE TABLE IF NOT EXISTS operating_effects(
      id INTEGER PRIMARY KEY,room_id INTEGER NOT NULL,event_id INTEGER,asset TEXT NOT NULL,
      start_day INTEGER NOT NULL,end_day INTEGER NOT NULL,revenue_delta REAL NOT NULL,
      margin_delta REAL NOT NULL,ramp_days INTEGER NOT NULL DEFAULT 1,fade_days INTEGER NOT NULL DEFAULT 0,
      label TEXT NOT NULL,UNIQUE(event_id,label));
    CREATE TABLE IF NOT EXISTS business_daily(
      room_id INTEGER NOT NULL,asset TEXT NOT NULL,day INTEGER NOT NULL,
      revenue REAL NOT NULL,margin REAL NOT NULL,profit REAL NOT NULL,
      PRIMARY KEY(room_id,asset,day));
    CREATE TABLE IF NOT EXISTS breaking_plans(
      room_id INTEGER PRIMARY KEY,seed INTEGER NOT NULL,dates TEXT NOT NULL,not_before INTEGER NOT NULL);
    CREATE TABLE IF NOT EXISTS breaking_releases(
      room_id INTEGER NOT NULL,slot INTEGER NOT NULL,day INTEGER NOT NULL,news_id INTEGER NOT NULL,
      asset TEXT NOT NULL,shock REAL NOT NULL,PRIMARY KEY(room_id,slot),UNIQUE(room_id,day));
    ''')
    columns = {x[1] for x in c.execute('PRAGMA table_info(news)')}
    for col, ddl in {
        'kind': "TEXT NOT NULL DEFAULT 'manual'", 'source': "TEXT NOT NULL DEFAULT '교사 편집국'",
        'certainty': "TEXT NOT NULL DEFAULT '보도'", 'event_id': 'INTEGER',
        'related_assets': "TEXT NOT NULL DEFAULT '[]'", 'lens': "TEXT NOT NULL DEFAULT ''",
        'horizon': "TEXT NOT NULL DEFAULT 'short'", 'expected_start': 'INTEGER', 'expected_end': 'INTEGER',
        'is_breaking': 'INTEGER NOT NULL DEFAULT 0'
    }.items():
        if col not in columns:
            c.execute(f'ALTER TABLE news ADD COLUMN {col} {ddl}')
    if 'evidence_ids' not in {x[1] for x in c.execute('PRAGMA table_info(orders)')}:
        c.execute("ALTER TABLE orders ADD COLUMN evidence_ids TEXT NOT NULL DEFAULT '[]'")
    event_columns = {x[1] for x in c.execute('PRAGMA table_info(business_events)')}
    for col, ddl in {'horizon': "TEXT NOT NULL DEFAULT 'short'", 'expected_start': 'INTEGER',
                     'expected_end': 'INTEGER', 'checkpoint_count': 'INTEGER NOT NULL DEFAULT 0'}.items():
        if col not in event_columns:
            c.execute(f'ALTER TABLE business_events ADD COLUMN {col} {ddl}')
    c.execute('CREATE INDEX IF NOT EXISTS idx_news_room_day ON news(room_id,day)')
    c.execute('CREATE INDEX IF NOT EXISTS idx_events_due ON business_events(room_id,due_day,stage)')
    c.execute('CREATE INDEX IF NOT EXISTS idx_operating_window ON operating_effects(room_id,start_day,end_day)')
    expectations.initialize(c)


def ensure_room(c, rid, seed, day, assets):
    """Additive migration: never replace prices, old news, or student balances."""
    if c.execute('SELECT 1 FROM businesses WHERE room_id=? LIMIT 1', (rid,)).fetchone():
        return
    rng = random.Random(seed + 61823)
    quarter = min(4, math.ceil(day / 6))
    for a in assets:
        if a['type'] != 'stock':
            continue
        rev = round(a['initial'] * rng.uniform(.8, 1.9))
        margin = rng.uniform(.08, .19) if a['risk'] != 'high' else rng.uniform(.015, .13)
        growth = rng.uniform(-.004, .012) + (.004 if a['risk'] == 'growth' else 0)
        cash, debt = rev * rng.uniform(.25, .65), rev * rng.uniform(.2, .9)
        c.execute('INSERT INTO businesses VALUES(?,?,?,?,?,?,?,?,?)',
                  (rid, a['id'], rev, 1, margin, cash, debt, growth, day))
        profit = round(rev * margin)
        c.execute('''INSERT OR IGNORE INTO financials(room_id,asset,quarter,day,revenue,profit,margin,cash,debt,
                     expected_revenue,expected_profit,revenue_growth,profit_growth,surprise,verdict,outlook,explanation,evidence_ids)
                     VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)''',
                  (rid, a['id'], 0, day, rev, profit, round(margin * 100, 2), round(cash), round(debt),
                   rev, profit, 0, 0, 0, '기준 실적', '이후 뉴스와 실적을 비교해 보세요.',
                   '게임 시작 시 공개된 비교 기준입니다. 재무 수치의 단위는 가상 억원입니다.', '[]'))
        expected_rev = round(rev * (1 + growth * 2.5) * rng.uniform(.97, 1.03))
        expected_profit = round(expected_rev * margin * rng.uniform(.96, 1.04))
        c.execute('''INSERT OR IGNORE INTO forecasts(room_id,asset,quarter,published_day,revenue,profit,base_revenue,base_margin)
                     VALUES(?,?,?,?,?,?,?,?)''',
                  (rid, a['id'], quarter, day, expected_rev, expected_profit, expected_rev, expected_profit/max(1,expected_rev)))


def article(c, rid, day, title, body, target, impact=0, *, kind='company',
            source='하루경제', certainty='전망', event_id=None, related=None, lens='',
            horizon='short', expected_start=None, expected_end=None, metrics=None):
    cur = c.execute('''INSERT INTO news(room_id,day,title,body,sector,impact,kind,source,certainty,event_id,related_assets,lens,horizon,expected_start,expected_end,metrics)
                       VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)''',
                    (rid, day, title, body, target, round(impact, 3), kind, source,
                     certainty, event_id, json.dumps(related or [], ensure_ascii=False), lens,
                     horizon, expected_start, expected_end,json.dumps(metrics or {},ensure_ascii=False)))
    return cur.lastrowid


def evolve_businesses(c, rid, day, seed, assets):
    """Small operating noise; event outcomes are the larger, explainable changes."""
    ensure_room(c, rid, seed, day - 1, assets)
    rng = random.Random(seed + day * 39971)
    for b in query(c, 'SELECT * FROM businesses WHERE room_id=?', (rid,)):
        if b['last_day'] >= day:
            continue
        idx = clamp(b['revenue_index'] * (1 + b['growth'] + rng.gauss(0, .006)), .22, 4.5)
        margin = clamp(b['margin'] + rng.gauss(0, .0018), -.08, .33)
        c.execute('UPDATE businesses SET revenue_index=?,margin=?,last_day=? WHERE room_id=? AND asset=?',
                  (idx, margin, day, rid, b['asset']))


def add_operating_effect(c, rid, event_id, asset, start, end, revenue, margin, label, ramp=1, fade=0):
    if start > 24 or end < start:
        return
    c.execute('''INSERT OR IGNORE INTO operating_effects(room_id,event_id,asset,start_day,end_day,revenue_delta,margin_delta,ramp_days,fade_days,label)
                 VALUES(?,?,?,?,?,?,?,?,?,?)''', (rid,event_id,asset,start,min(24,end),revenue,margin,ramp,fade,label))


def effect_weight(effect, day):
    if day < effect['start_day'] or day > effect['end_day']:
        return 0
    ramp = min(1, (day - effect['start_day'] + 1) / max(1, effect['ramp_days']))
    fade = min(1, (effect['end_day'] - day + 1) / (effect['fade_days'] + 1)) if effect['fade_days'] else 1
    return min(ramp, fade)


def record_business_day(c, rid, day, assets):
    """Quarterly accounts average the six operating days, including temporary and recurring effects."""
    active = query(c, 'SELECT * FROM operating_effects WHERE room_id=? AND start_day<=? AND end_day>=?', (rid, day, day))
    for b in query(c, 'SELECT * FROM businesses WHERE room_id=?', (rid,)):
        effects = [e for e in active if e['asset'] == b['asset']]
        revenue_delta = clamp(sum(e['revenue_delta'] * effect_weight(e, day) for e in effects), -.55, 1.2)
        margin_delta = sum(e['margin_delta'] * effect_weight(e, day) for e in effects)
        revenue = b['base_revenue'] * b['revenue_index'] * (1 + revenue_delta)
        margin = clamp(b['margin'] + margin_delta, -.12, .36)
        c.execute('INSERT OR IGNORE INTO business_daily VALUES(?,?,?,?,?,?)', (rid,b['asset'],day,revenue,margin,revenue*margin))


def choose_horizon(rng, day, kind):
    """Only dates inside this school year are promised; the schedule is public, the outcome is not."""
    q = math.ceil(day / 6)
    roll = rng.random()
    long_bias = kind in ('research', 'contract', 'supply')
    if day <= 13 and roll < (.32 if long_bias else .12):
        start = 19 + rng.randrange(2)
        return 'year_end', start, 24
    if q < 4 and roll < (.76 if long_bias else .48):
        start = q * 6 + 1
        return 'next_quarter', start, min(24, start + (11 if kind == 'contract' else 5))
    start = min(24, day + rng.randint(2, 4))
    return 'short', start, min(24, start + 3)


def horizon_sentence(horizon, start, end):
    if horizon == 'year_end':
        return f'연말인 {start}~{end}일차에 가동·성과 확인을 목표로 합니다.'
    if horizon == 'next_quarter':
        return f'다음 분기 {start}일차부터 시작해 {end}일차까지 사업 영향이 이어질 것으로 예상합니다.'
    return f'{start}일차 전후의 단기 운영 결과를 확인할 예정입니다.'


def resolve_events(c, rid, day, seed, assets):
    amap = {a['id']: a for a in assets}
    pending = query(c, "SELECT * FROM business_events WHERE room_id=? AND due_day<=? AND stage IN ('developing','delayed','tracking') ORDER BY id", (rid, day))
    for e in pending:
        rng = random.Random(seed + e['id'] * 431 + day * 7727)
        a = amap[e['asset']]
        horizon = e['horizon']
        expected = e['expected_start'] or e['due_day']
        end = e['expected_end'] or min(24, expected + 3)
        meta = dict(horizon=horizon, expected_start=expected, expected_end=end,
                    event_id=e['id'], related=[a['id']], lens=LENSES[e['kind']])
        quantitative = e['model_version'] >= 2
        metrics = {'revenue_pct': round((e['target_revenue_delta'] or 0)*100,1),
                   'margin_pp': round((e['target_margin_delta'] or 0)*100,2),
                   'preparation_margin_pp': round(e['preparation_margin_delta']*100,2),
                   'status':'target'}
        if horizon != 'short' and day < expected:
            due = min(expected, day + rng.randint(3, 5))
            c.execute("UPDATE business_events SET stage='tracking',checkpoint_count=checkpoint_count+1,due_day=? WHERE id=?", (due, e['id']))
            caution = rng.random() < .28
            title = f'{a["name"]}, {e["title"]} ' + ('중간 비용·일정 점검' if caution else '진행 상황 공개')
            body = (f'{e["start_day"]}일차에 보도한 사업의 중간 점검입니다. '
                    + ('추가 비용과 일정 위험을 점검하고 있습니다. ' if caution else '협의·준비 작업은 계속되고 있지만 아직 최종 결과나 매출 확정은 아닙니다. ')
                    + horizon_sentence(horizon, expected, end)
                    + ' 지금의 주가 반응과 나중에 발표할 실적을 구분해서 살펴보세요.')
            if quantitative:
                body += ' 전망 수치와 일정은 이전 보도와 같습니다. 아직 새 영업 성과가 확인된 것은 아닙니다. '
                metrics['status'] = 'unchanged'
            article(c, rid, day, title, body, a['id'], 0 if quantitative else (-.25 if caution else e['direction'] * e['magnitude'] * 4),
                    kind='followup', certainty='중간 점검', metrics=metrics if quantitative else None, **meta)
            continue
        if not e['delayed'] and day < 23 and rng.random() < .16:
            revised = min(24, day + 2)
            revised_end = min(24, end + revised - expected)
            c.execute("UPDATE business_events SET stage='delayed',delayed=1,due_day=?,expected_start=?,expected_end=? WHERE id=?", (revised,revised,revised_end,e['id']))
            impact = -.35
            if quantitative:
                metrics['status'] = 'delayed'
                old_state = c.execute('SELECT * FROM event_expectations WHERE event_id=?',(e['id'],)).fetchone()
                impact = expectations.revise_event(c,rid,e['id'],a['id'],day,metrics,revised,revised_end,horizon,
                          weight=old_state['weight'],prep_start=old_state['prep_start'],
                          prep_end=revised-1 if old_state['prep_start'] else 0)
                c.execute("UPDATE operating_effects SET end_day=? WHERE event_id=? AND label='준비 비용'", (revised-1,e['id']))
            article(c, rid, day, f'{a["name"]}, {e["title"]} 확인 일정 조정',
                    f'예정했던 사업 확인이 {revised}일차 전후로 늦어졌습니다. 추가 준비와 검토가 필요하며, 당초 기대했던 매출이 늦게 반영되거나 줄어들 수 있습니다. 성공·실패는 아직 확정되지 않았습니다.',
                    a['id'], impact, kind='followup', certainty='일정 조정', metrics=metrics if quantitative else None,
                    **{**meta,'expected_start':revised,'expected_end':revised_end})
            continue
        realized = rng.random() < (.72 if e['direction'] < 0 else .68)
        direction = e['direction'] if realized else -e['direction']
        magnitude = e['magnitude'] * (1 if realized else .5)
        revenue_delta = direction * magnitude * (.65 if e['kind'] == 'research' else 1)
        margin_delta = direction * magnitude * (.23 if e['kind'] == 'cost' else .075)
        if e['kind'] == 'cost':
            revenue_delta *= .16
        if quantitative:
            # An improving business can still deliver less than the original target.
            scale = rng.uniform(.35,1.2) if realized else -rng.uniform(.25,.65)
            metrics.update(revenue_pct=round(metrics['revenue_pct']*scale,1),
                           margin_pp=round(metrics['margin_pp']*scale,2),status='confirmed')
            revenue_delta,margin_delta = metrics['revenue_pct']/100,metrics['margin_pp']/100
        actual_end = min(24, max(day, end))
        add_operating_effect(c, rid, e['id'], a['id'], day, actual_end,
                             revenue_delta, margin_delta, '사업 운영 효과',
                             ramp=2 if horizon != 'short' else 1,
                             fade=1 if horizon == 'short' else 0)
        results = {
            'contract': ('주요 계약 조건과 납품 일정이 확인됐습니다.', '계약이나 납품 계획에 차질이 확인됐습니다.'),
            'sales': ('관련 사업 수요가 개선됐다는 운영 자료가 나왔습니다.', '관련 사업 수요가 기대에 미치지 못했습니다.'),
            'cost': ('비용 부담을 줄이는 운영 개선이 확인됐습니다.', '예상보다 비용 부담이 커졌습니다.'),
            'research': ('기술 검증과 사업화 준비에서 진전이 확인됐습니다.', '추가 기술 검증에서 보완 사항이 발견됐습니다.'),
            'supply': ('원료·부품 확보와 납품 일정이 개선됐습니다.', '원료·부품 확보나 납품 일정에 차질이 생겼습니다.'),
        }
        result = results[e['kind']][0 if direction > 0 else 1]
        body = (f'{e["start_day"]}일차에 보도한 사업의 결과입니다. {result} '
                f'{day}~{actual_end}일차의 영업에 영향을 주며, 해당 기간이 포함된 분기 실적에 반영됩니다. '
                '분기 실적은 하루의 결과가 아니라 분기 전체 영업 기록을 모아 계산합니다. ')
        if not realized:
            body += '처음 보도 때의 예상과 다른 결과가 나왔습니다. '
        impact = direction * magnitude * 19
        if quantitative:
            body += expectations.metric_sentence(metrics,confirmed=True)
            body += (f'처음 제시한 전망은 매출 {e["target_revenue_delta"]*100:+.1f}%, '
                     f'이익률 {e["target_margin_delta"]*100:+.2f}%p였습니다. '
                     '사업이 개선되어도 이미 기대했던 수준보다 부족하면 가격 반응은 약하거나 반대일 수 있습니다. ')
            old_state = c.execute('SELECT * FROM event_expectations WHERE event_id=?',(e['id'],)).fetchone()
            impact = expectations.revise_event(c,rid,e['id'],a['id'],day,metrics,day,actual_end,horizon,
                      weight=1,prep_start=old_state['prep_start'],prep_end=min(day-1,old_state['prep_end']))
        body += '다른 주문과 비용도 함께 작용하므로 이 소식 하나만으로 이익이나 주가를 단정할 수 없습니다.'
        c.execute("UPDATE business_events SET stage=?,result=?,resolved_day=? WHERE id=?", ('confirmed' if realized else 'reversed',result,day,e['id']))
        article(c, rid, day, f'{a["name"]}, {e["title"]} ' + ('진전 확인' if direction > 0 else '차질 확인'),
                body, a['id'], impact, kind='followup', certainty='사실 확인',metrics=metrics if quantitative else None,
                **{**meta,'expected_start':day,'expected_end':actual_end})


def publish_news(c, rid, day, seed, mood, assets):
    if c.execute("SELECT 1 FROM news WHERE room_id=? AND day=? AND kind='briefing'", (rid, day)).fetchone():
        return
    ensure_room(c, rid, seed, day, assets)
    rng = random.Random(seed + day * 9187 + 103)
    stocks = [a for a in assets if a['type'] == 'stock']
    chosen = []
    for i, sector in enumerate(SECTORS):
        pool = [a for a in stocks if a['sector'] == sector]
        offset = random.Random(seed + i * 311).randrange(4)
        chosen.append(pool[(day - 1 + offset) % 4])
    chosen.append(rng.choice([a for a in stocks if a not in chosen]))
    for i, a in enumerate(chosen):
        kind = KINDS[(day + i) % len(KINDS)]
        subject = COMPANY_PROFILES.get(a['id'], PROFILES[a['sector']])[KINDS.index(kind)]
        positive_prob = {'positive': .68, 'neutral': .5, 'negative': .3}[mood]
        direction = 1 if rng.random() < positive_prob else -1
        mixed = rng.random() < .2
        magnitude = rng.uniform(.035, .10) * {'stable': .75, 'growth': 1, 'high': 1.45}[a['risk']]
        horizon, expected, end = choose_horizon(rng, day, kind)
        due = min(expected, day + rng.randint(2, 4))
        if day < 22:
            cur = c.execute('''INSERT INTO business_events(room_id,asset,kind,direction,magnitude,start_day,due_day,title,horizon,expected_start,expected_end)
                               VALUES(?,?,?,?,?,?,?,?,?,?,?)''', (rid, a['id'], kind, direction, magnitude, day, due, subject, horizon, expected, end))
            event_id = cur.lastrowid
            preparation = horizon != 'short' and kind in ('research','contract','supply')
            metrics = expectations.target_metrics(kind,direction,magnitude,preparation)
            c.execute('''UPDATE business_events SET model_version=2,target_revenue_delta=?,target_margin_delta=?,preparation_margin_delta=?
                         WHERE id=?''',(metrics['revenue_pct']/100,metrics['margin_pp']/100,metrics['preparation_margin_pp']/100,event_id))
            if preparation:
                add_operating_effect(c,rid,event_id,a['id'],day+1,expected-1,0,metrics['preparation_margin_pp']/100,'준비 비용')
            reference = c.execute('SELECT revenue,margin FROM financials WHERE room_id=? AND asset=? AND day<=? ORDER BY quarter DESC LIMIT 1',(rid,a['id'],day)).fetchone()
            metrics['reference_revenue'] = reference['revenue']
            metrics['reference_margin_pct'] = reference['margin']
            impact = expectations.revise_event(c,rid,event_id,a['id'],day,metrics,expected,end,horizon,
                      reference_margin=reference['margin']/100,weight=.536 if direction>0 else .594,
                      prep_start=day+1 if preparation else 0,prep_end=expected-1 if preparation else 0)
            title = f'{a["name"]}, {subject} ' + ('기대 커져' if direction > 0 else '불확실성 확대')
            body = (f'{a["name"]}이(가) 새로운 사업 전망을 공개했습니다. ' + expectations.metric_sentence(metrics) + '아직 확정 실적이 아닌 회사의 전망입니다. '
                    f'{due}일차 전후에 진행 상황을 점검합니다. ' + horizon_sentence(horizon,expected,end) + ' 일정이나 결과는 달라질 수 있습니다. ')
            body += ('성장 기회가 있지만 초기 비용이 늘 수 있다는 반론도 나왔습니다.' if mixed else LENSES[kind])
            if horizon != 'short' and kind in ('research','contract','supply'):
                body += f' 준비 기간인 {day+1}~{expected-1}일차에는 이익률 {metrics["preparation_margin_pp"]:+.2f}%p의 준비·연구 비용이 먼저 발생할 수 있습니다.'
            article(c, rid, day, title, body, a['id'], impact,
                    source=rng.choice(['하루경제', '기업리포트', '산업포커스']),
                    certainty='전망·미확정', event_id=event_id, related=[a['id']], lens=LENSES[kind],
                    horizon=horizon,expected_start=expected,expected_end=end,metrics=metrics)
        else:
            # Late news never rewrites the report that was already published this morning.
            metrics = {'revenue_pct':round(direction*magnitude*.22*100,1) if day<24 else 0,
                       'margin_pp':round(direction*magnitude*.025*100,2) if day<24 else 0,
                       'preparation_margin_pp':0,'status':'operating'}
            event_id,impact = None,0
            if day < 24:
                cur = c.execute('''INSERT INTO business_events(room_id,asset,kind,direction,magnitude,start_day,due_day,
                    stage,title,result,resolved_day,horizon,expected_start,expected_end,model_version,target_revenue_delta,target_margin_delta)
                    VALUES(?,?,?,?,?,?,?,'confirmed',?,?,?,'short',?,24,2,?,?)''',
                    (rid,a['id'],kind,direction,magnitude,day,day,subject,'연말 운영 현황 공개',day,day+1,metrics['revenue_pct']/100,metrics['margin_pp']/100))
                event_id = cur.lastrowid
                add_operating_effect(c,rid,event_id,a['id'],day+1,24,metrics['revenue_pct']/100,metrics['margin_pp']/100,'연말 운영 현황')
                reference = c.execute('SELECT margin FROM financials WHERE room_id=? AND asset=? ORDER BY quarter DESC LIMIT 1',(rid,a['id'])).fetchone()
                impact = expectations.revise_event(c,rid,event_id,a['id'],day,metrics,day+1,24,'short',weight=1,
                          reference_margin=reference['margin']/100,ramp_days=1,fade_days=0)
            article(c, rid, day, f'{a["name"]}, 연말 {subject} 점검',
                    f'회사는 {subject}의 최근 현황을 공개했습니다. ' +
                    ('운영 지표가 이전보다 개선됐다고 설명했습니다.' if direction > 0 else '운영 지표가 이전보다 약해졌다고 설명했습니다.') +
                    (' '+expectations.metric_sentence(metrics,confirmed=True) if day<24 else ' 올해 영업은 마감됐으며 오늘 확정한 분기 실적을 바꾸지 않습니다.')+
                    ' 매출과 이익이 같은 방향으로 움직이는지는 최신 분기 보고서와 함께 비교해 보세요.',
                    a['id'], impact, certainty='운영 현황', related=[a['id']],lens=LENSES[kind],
                    event_id=event_id,metrics=metrics,expected_start=min(24,day+1),expected_end=24)
    focus = SECTORS[(day + seed) % 5]
    names = [a['name'] for a in stocks if a['sector'] == focus]
    sector_direction = {'positive': 1, 'neutral': 0, 'negative': -1}[mood]
    article(c, rid, day, f'{focus} 산업, ' + {'positive': '수요 회복 기대와 비용 과제', 'neutral': '기업별 실적 차이 주목', 'negative': '수요 둔화 속 대응책 모색'}[mood],
            f'{", ".join(names)} 등이 속한 {focus} 산업에서 주문과 비용 전망이 엇갈립니다. 같은 산업이어도 계약 구조와 부채 규모가 달라 결과가 같지는 않습니다. 개별 기업의 후속 발표를 확인해 보세요.',
            focus, sector_direction * .6, kind='sector', source='산업포커스', certainty='산업 전망',
            related=[a['id'] for a in stocks if a['sector'] == focus])
    tips = [
        ('매출과 이익, 무엇이 다를까?', '매출은 물건과 서비스를 팔아 번 금액이고, 영업이익은 사업 비용을 빼고 남은 금액이에요. 매출이 커져도 이익은 줄 수 있어요.'),
        ('좋은 실적에도 주가가 떨어질 수 있을까?', '시장 예상보다 더 좋을 것이라는 기대가 가격에 먼저 반영될 수 있어요. 실제 실적과 사전에 공개된 예상치를 함께 비교해 보세요.'),
        ('투자하지 않고 기다리는 것도 선택', '읽은 뉴스의 결과가 아직 불확실하다면 현금이나 예금을 유지하며 후속 발표를 기다릴 수도 있어요.'),
        ('한 회사에만 투자한다면?', '예상이 맞을 때 성과가 크지만, 예상이 틀릴 때 손실도 집중돼요. 여러 기업과 다른 상품을 함께 살펴보세요.'),
        ('부채가 늘었다는 것은?', '투자 자금을 마련한 것일 수도 있지만 이자 부담도 커져요. 현금과 이익이 충분한지 같이 확인해야 해요.'),
        ('처음 생각을 남기는 이유', '결과를 본 뒤에는 처음부터 알았다고 느끼기 쉬워요. 투자 전에 근거와 걱정거리를 적으면 판단 과정을 돌아보기 좋아요.'),
    ]
    if day == 1:
        record_business_day(c,rid,day,assets)
    title, body = tips[(day - 1) % len(tips)]
    article(c, rid, day, title, body, '전체', kind='briefing', source='투자 교실', certainty='생각해 보기')
    expectations.refresh_estimates(c,rid,day)


def earnings_evidence(c,rid,asset,day):
    # Include an old announcement if its actual operating effect belongs to this quarter.
    return query(c,'''SELECT DISTINCT n.id,n.title FROM news n WHERE n.room_id=? AND n.sector=? AND n.day<=?
                     AND n.kind IN ('company','followup') AND (n.day>=? OR n.event_id IN (
                       SELECT event_id FROM operating_effects WHERE room_id=? AND asset=?
                       AND start_day<=? AND end_day>=? AND event_id IS NOT NULL))
                     ORDER BY n.day DESC,n.id DESC LIMIT 8''', (rid,asset,day,day-5,rid,asset,day,day-5))


def release_earnings(c, rid, day, seed, assets):
    """Reports become public at the open on days 6/12/18/24; prices react at that same open."""
    record_business_day(c,rid,day,assets)
    if day not in (6, 12, 18, 24):
        return {}
    quarter = day // 6
    if c.execute('SELECT 1 FROM financials WHERE room_id=? AND quarter=?', (rid, quarter)).fetchone():
        return {}
    # Include publicly confirmed morning updates; do not pay for them again as an earnings surprise.
    expectations.refresh_estimates(c,rid,day)
    rng = random.Random(seed + quarter * 49003)
    reactions = {}
    for a in [a for a in assets if a['type'] == 'stock']:
        b = dict(c.execute('SELECT * FROM businesses WHERE room_id=? AND asset=?', (rid, a['id'])).fetchone())
        prev = dict(c.execute('SELECT * FROM financials WHERE room_id=? AND asset=? ORDER BY quarter DESC LIMIT 1', (rid, a['id'])).fetchone())
        forecast = c.execute('SELECT * FROM forecasts WHERE room_id=? AND asset=? AND quarter=?', (rid, a['id'], quarter)).fetchone()
        expected_rev = forecast['revenue'] if forecast else prev['revenue']
        expected_profit = forecast['profit'] if forecast else prev['profit']
        market = expectations.latest(c,rid,a['id'],quarter,day)
        market_rev = market['revenue'] if market else expected_rev
        market_profit = market['profit'] if market else expected_profit
        daily = c.execute('SELECT AVG(revenue) revenue,AVG(profit) profit,COUNT(*) n FROM business_daily WHERE room_id=? AND asset=? AND day BETWEEN ? AND ?', (rid,a['id'],day-5,day)).fetchone()
        revenue = max(1,round(daily['revenue'] if daily['n'] else b['base_revenue']*b['revenue_index']))
        profit = round(daily['profit'] if daily['n'] else revenue*b['margin'])
        margin = round(profit / revenue * 100, 2)
        surprise = round((profit - expected_profit) / max(abs(expected_profit), expected_rev * .035) * 100, 2)
        market_surprise = round((profit-market_profit)/max(abs(market_profit),market_rev*.035)*100,2)
        market_verdict = '예상 상회' if market_surprise>7 else '예상 하회' if market_surprise< -7 else '예상 부합'
        rev_growth = round((revenue / prev['revenue'] - 1) * 100, 2)
        profit_growth = round((profit - prev['profit']) / max(abs(prev['profit']), prev['revenue'] * .035) * 100, 2)
        cash = max(1, round(b['cash'] + profit * .48 - revenue * .025))
        debt = max(0, round(b['debt'] - max(profit, 0) * .09 + max(-profit, 0) * .4))
        verdict = '예상 상회' if surprise > 7 else '예상 하회' if surprise < -7 else '예상 부합'
        evidence = earnings_evidence(c,rid,a['id'],day)
        driver = ' / '.join(x['title'] for x in evidence[:2]) or '분기 중 수요와 비용의 변화'
        comparison = '기준 실적' if prev['quarter'] == 0 else f'{prev["quarter"]}분기'
        explanation = (f'매출은 {comparison} 대비 {rev_growth:+.1f}%, 영업이익은 {profit_growth:+.1f}% 변했습니다. '
                       f'당초 공개한 영업이익 예상 {expected_profit:,}억원과 비교하면 {verdict}입니다. '
                       f'공개 뉴스로 바뀐 발표 직전 기대는 {market_profit:,}억원이며, 이 기준으로는 {market_verdict}입니다. '
                       f'영업 기간과 연결된 단서: {driver}. 분기 영업 기록 {daily["n"]}일을 평균해 계산했습니다.')
        outlook = ('주문과 비용 개선이 이어질지 후속 보도를 확인하세요.' if profit > expected_profit else
                   '이익률 회복과 추가 비용 발생 여부를 살펴보세요.')
        c.execute('''INSERT INTO financials(room_id,asset,quarter,day,revenue,profit,margin,cash,debt,
                     expected_revenue,expected_profit,revenue_growth,profit_growth,surprise,verdict,outlook,explanation,evidence_ids)
                     VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)''',
                  (rid, a['id'], quarter, day, revenue, profit, margin, cash, debt, expected_rev, expected_profit,
                   rev_growth, profit_growth, surprise, verdict, outlook, explanation, json.dumps([x['id'] for x in evidence])))
        c.execute('UPDATE businesses SET cash=?,debt=? WHERE room_id=? AND asset=?', (cash, debt, rid, a['id']))
        c.execute('''UPDATE financials SET market_expected_revenue=?,market_expected_profit=?,market_surprise=?,
                     market_verdict=?,market_expectation_day=? WHERE room_id=? AND asset=? AND quarter=?''',
                  (market_rev,market_profit,market_surprise,market_verdict,market['published_day'] if market else day,rid,a['id'],quarter))
        reactions[a['id']] = clamp(market_surprise * .085, -7, 7)
        if quarter < 4:
            # Freeze next-quarter expectations now; they are visible before subsequent news and results.
            public_rev,public_margin = expectations.quarter_factors(c,rid,a['id'],quarter,0)
            base_rev = max(1,revenue/public_rev*(1+b['growth']*6)*rng.uniform(.97,1.03))
            base_margin = clamp(margin/100-public_margin/public_rev+rng.uniform(-.008,.008),-.08,.33)
            next_rev,next_profit = expectations.estimate(c,rid,a['id'],quarter+1,base_rev,base_margin)
            c.execute('''INSERT OR IGNORE INTO forecasts(room_id,asset,quarter,published_day,revenue,profit,base_revenue,base_margin)
                         VALUES(?,?,?,?,?,?,?,?)''', (rid,a['id'],quarter+1,day,next_rev,next_profit,base_rev,base_margin))
    article(c, rid, day, f'{quarter}분기 실적 발표 · 20개 기업 성적표 공개',
            '매출·영업이익·이익률·현금·부채와 사전 예상치가 공개됐습니다. 뉴스 속 기대가 실제 숫자로 이어졌는지 실적센터에서 비교해 보세요. 이번 발표에 대한 시장 반응은 오늘 가격에 함께 반영됐습니다.',
            '전체', kind='earnings', source='기업 공시센터', certainty='실적 확정', related=[a['id'] for a in assets if a['type'] == 'stock'])
    return reactions


def public_data(c, rid, day):
    reports = query(c, 'SELECT * FROM financials WHERE room_id=? AND day<=? ORDER BY quarter DESC,asset', (rid, day))
    for r in reports:
        r.pop('room_id', None)
        r['evidence_ids'] = json.loads(r['evidence_ids'])
    # Never expose private business state, event direction, magnitude or future outcome dates.
    events = query(c, '''SELECT id,asset,kind,start_day,stage,title,result,resolved_day,horizon,expected_start,expected_end FROM business_events
                         WHERE room_id=? AND start_day<=? ORDER BY start_day DESC,id DESC LIMIT 250''', (rid, day))
    forecasts = query(c, 'SELECT asset,quarter,published_day,revenue,profit FROM forecasts WHERE room_id=? AND published_day<=? ORDER BY quarter,asset', (rid, day))
    return {'reports': reports, 'forecasts': forecasts, 'events': events,
            'market_estimates':expectations.public_estimates(c,rid,day),
            'calendar': [{'quarter': q, 'day': q * 6, 'released': day >= q * 6 and any(r['quarter'] == q for r in reports)} for q in range(1, 5)],
            'financial_unit': '가상 억원',
            'benchmark': {'deposit_rate':DEPOSIT_RATE,'term':24,'progress_rate':DEPOSIT_RATE*(day-1)/TRADING_INTERVALS}}
