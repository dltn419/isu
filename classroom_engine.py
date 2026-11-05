"""Persistent business simulation. Published evidence and private outcomes stay separate."""
import json
import math
import random

SECTORS = ['기술', '항공', '식품', '의료·제약', '미래사업']
MOOD_NAMES = {'positive': '긍정', 'neutral': '중립', 'negative': '부정'}
PROFILES = {
    '기술': ('스마트기기·반도체 공급 계약', '전자제품·서비스 주문', '부품·생산 비용', '차세대 기술 검증', '핵심 반도체 공급'),
    '항공': ('항공·물류 서비스 계약', '여객·화물 예약', '연료·운항 비용', '운항·정비 신기술 검증', '항공기·정비 부품 공급'),
    '식품': ('유통업체 입점 계약', '식품·원료 주문', '농산물·포장재 비용', '신제품 소비자 시험', '원재료 납품'),
    '의료·제약': ('병원·제약사 공급 계약', '의약품·의료장비 주문', '연구·생산 비용', '의료 기술·신약 검증', '의약품 원료 공급'),
    '미래사업': ('AI·자동화 설비 계약', '데이터센터·자동화 주문', '전력·설비 운영 비용', '차세대 장비 성능 검증', '핵심 장비 납품'),
}
KINDS = ['contract', 'sales', 'cost', 'research', 'supply']
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
    ''')
    columns = {x[1] for x in c.execute('PRAGMA table_info(news)')}
    for col, ddl in {
        'kind': "TEXT NOT NULL DEFAULT 'manual'", 'source': "TEXT NOT NULL DEFAULT '교사 편집국'",
        'certainty': "TEXT NOT NULL DEFAULT '보도'", 'event_id': 'INTEGER',
        'related_assets': "TEXT NOT NULL DEFAULT '[]'", 'lens': "TEXT NOT NULL DEFAULT ''"
    }.items():
        if col not in columns:
            c.execute(f'ALTER TABLE news ADD COLUMN {col} {ddl}')
    if 'evidence_ids' not in {x[1] for x in c.execute('PRAGMA table_info(orders)')}:
        c.execute("ALTER TABLE orders ADD COLUMN evidence_ids TEXT NOT NULL DEFAULT '[]'")
    c.execute('CREATE INDEX IF NOT EXISTS idx_news_room_day ON news(room_id,day)')
    c.execute('CREATE INDEX IF NOT EXISTS idx_events_due ON business_events(room_id,due_day,stage)')


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
        growth = rng.uniform(-.008, .025) + (.012 if a['risk'] == 'growth' else 0)
        cash, debt = rev * rng.uniform(.25, .65), rev * rng.uniform(.2, .9)
        c.execute('INSERT INTO businesses VALUES(?,?,?,?,?,?,?,?,?)',
                  (rid, a['id'], rev, 1, margin, cash, debt, growth, day))
        profit = round(rev * margin)
        c.execute('INSERT OR IGNORE INTO financials VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)',
                  (rid, a['id'], 0, day, rev, profit, round(margin * 100, 2), round(cash), round(debt),
                   rev, profit, 0, 0, 0, '기준 실적', '이후 뉴스와 실적을 비교해 보세요.',
                   '게임 시작 시 공개된 비교 기준입니다. 재무 수치의 단위는 가상 억원입니다.', '[]'))
        expected_rev = round(rev * (1 + growth * 5) * rng.uniform(.97, 1.05))
        expected_profit = round(expected_rev * margin * rng.uniform(.96, 1.08))
        c.execute('INSERT OR IGNORE INTO forecasts VALUES(?,?,?,?,?,?)',
                  (rid, a['id'], quarter, day, expected_rev, expected_profit))


def article(c, rid, day, title, body, target, impact=0, *, kind='company',
            source='하루경제', certainty='전망', event_id=None, related=None, lens=''):
    cur = c.execute('''INSERT INTO news(room_id,day,title,body,sector,impact,kind,source,certainty,event_id,related_assets,lens)
                       VALUES(?,?,?,?,?,?,?,?,?,?,?,?)''',
                    (rid, day, title, body, target, round(impact, 3), kind, source,
                     certainty, event_id, json.dumps(related or [], ensure_ascii=False), lens))
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


def resolve_events(c, rid, day, seed, assets):
    amap = {a['id']: a for a in assets}
    for e in query(c, "SELECT * FROM business_events WHERE room_id=? AND due_day<=? AND stage IN ('developing','delayed') ORDER BY id", (rid, day)):
        rng = random.Random(seed + e['id'] * 431 + day * 7727)
        a = amap[e['asset']]
        if not e['delayed'] and day < 23 and rng.random() < .17:
            c.execute("UPDATE business_events SET stage='delayed',delayed=1,due_day=? WHERE id=?", (min(24, day + 2), e['id']))
            article(c, rid, day, f'{a["name"]}, {e["title"]} 결과 확인 늦어진다',
                    '당초 예정했던 점검 일정이 늦어졌습니다. 회사는 추가 검토가 필요하다고 설명했습니다. 아직 성공이나 실패로 판단할 수 없고, 확정 전까지 기존 기대를 다시 점검할 필요가 있습니다.',
                    a['id'], -.35, kind='followup', certainty='진행 확인', event_id=e['id'], related=[a['id']], lens=LENSES[e['kind']])
            continue
        realized = rng.random() < (.74 if e['direction'] < 0 else .67)
        direction = e['direction'] if realized else -e['direction']
        # Failed optimistic plans have a smaller negative operating effect; mitigated risks a smaller positive effect.
        magnitude = e['magnitude'] * (1 if realized else .5)
        revenue_delta = direction * magnitude * (.65 if e['kind'] == 'research' else 1)
        margin_delta = direction * magnitude * (.23 if e['kind'] == 'cost' else .075)
        if e['kind'] == 'cost':
            revenue_delta *= .16
        c.execute('''UPDATE businesses SET revenue_index=MAX(.22,MIN(4.5,revenue_index*(1+?))),
                     margin=MAX(-.08,MIN(.33,margin+?)) WHERE room_id=? AND asset=?''',
                  (revenue_delta, margin_delta, rid, a['id']))
        outcome = '진전 확인' if direction > 0 else '차질 확인'
        result = ('실제 주문·납품 또는 운영 개선이 확인됐습니다.' if direction > 0 else
                  '주문·납품 또는 운영 계획에 차질이 확인됐습니다.')
        body = (f'{e["start_day"]}일차에 보도한 {e["title"]}의 후속 소식입니다. {result} '
                + ('매출이나 이익 개선에 기여할 것으로 예상되지만, 다른 비용도 함께 확인해야 합니다.' if direction > 0 else
                   '매출 성장이나 이익률에 부담이 생겼습니다. 다른 사업이 이를 메울 수 있는지는 분기 실적에서 확인해야 합니다.'))
        if not realized:
            body += ' 최초 보도 때의 예상과 다른 결과가 나온 사례입니다.'
        c.execute("UPDATE business_events SET stage=?,result=?,resolved_day=? WHERE id=?",
                  ('confirmed' if realized else 'reversed', result, day, e['id']))
        article(c, rid, day, f'{a["name"]}, {e["title"]} {outcome}', body, a['id'], direction * magnitude * 36,
                kind='followup', certainty='사실 확인', event_id=e['id'], related=[a['id']], lens=LENSES[e['kind']])


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
        subject = PROFILES[a['sector']][KINDS.index(kind)]
        positive_prob = {'positive': .68, 'neutral': .5, 'negative': .3}[mood]
        direction = 1 if rng.random() < positive_prob else -1
        mixed = rng.random() < .2
        magnitude = rng.uniform(.035, .10) * {'stable': .75, 'growth': 1, 'high': 1.45}[a['risk']]
        due = min(24, day + rng.randint(2, 4))
        if day < 22:
            cur = c.execute('''INSERT INTO business_events(room_id,asset,kind,direction,magnitude,start_day,due_day,title)
                               VALUES(?,?,?,?,?,?,?,?)''', (rid, a['id'], kind, direction, magnitude, day, due, subject))
            event_id = cur.lastrowid
            strength = rng.randint(6, 18)
            if kind == 'cost':
                signal = f'비용을 약 {strength}% 줄일 수 있는 방안을 검토 중' if direction > 0 else f'관련 비용이 약 {strength}% 늘어날 가능성을 점검 중'
            else:
                signal = f'관련 사업 규모가 약 {strength}% 확대될 가능성을 검토 중' if direction > 0 else f'관련 사업 진행이 예상보다 약 {strength}% 부진할 가능성을 점검 중'
            title = f'{a["name"]}, {subject} ' + ('기대 커져' if direction > 0 else '불확실성 확대')
            body = (f'{a["name"]}은(는) {signal}이라고 밝혔습니다. 아직 확정 실적이 아닌 회사의 전망입니다. '
                    f'{due}일차 전후에 진행 상황을 다시 확인할 예정이며, 일정이 늦어지거나 예상과 다른 결과가 나올 수 있습니다. ')
            body += ('성장 기회가 있지만 초기 비용이 늘 수 있다는 반론도 나왔습니다.' if mixed else LENSES[kind])
            article(c, rid, day, title, body, a['id'], direction * magnitude * 15,
                    source=rng.choice(['하루경제', '기업리포트', '산업포커스']),
                    certainty='전망·미확정', event_id=event_id, related=[a['id']], lens=LENSES[kind])
        else:
            # Late-year operating evidence has an immediate fundamental effect and no unresolved future schedule.
            c.execute('''UPDATE businesses SET revenue_index=MAX(.22,MIN(4.5,revenue_index*(1+?))),
                         margin=MAX(-.08,MIN(.33,margin+?)) WHERE room_id=? AND asset=?''',
                      (direction * magnitude * .22, direction * magnitude * .025, rid, a['id']))
            article(c, rid, day, f'{a["name"]}, 연말 {subject} 점검',
                    f'회사는 {subject}의 최근 현황을 공개했습니다. ' +
                    ('운영 지표가 이전보다 개선됐다고 설명했습니다.' if direction > 0 else '운영 지표가 이전보다 약해졌다고 설명했습니다.') +
                    ' 매출과 이익이 같은 방향으로 움직이는지는 최신 분기 보고서와 함께 비교해 보세요.',
                    a['id'], direction * magnitude * 12, certainty='운영 현황', related=[a['id']], lens=LENSES[kind])
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
    title, body = tips[(day - 1) % len(tips)]
    article(c, rid, day, title, body, '전체', kind='briefing', source='투자 교실', certainty='생각해 보기')


def release_earnings(c, rid, day, seed, assets):
    """Reports become public at the open on days 6/12/18/24; prices react at that same open."""
    if day not in (6, 12, 18, 24):
        return {}
    quarter = day // 6
    if c.execute('SELECT 1 FROM financials WHERE room_id=? AND quarter=?', (rid, quarter)).fetchone():
        return {}
    rng = random.Random(seed + quarter * 49003)
    reactions = {}
    for a in [a for a in assets if a['type'] == 'stock']:
        b = dict(c.execute('SELECT * FROM businesses WHERE room_id=? AND asset=?', (rid, a['id'])).fetchone())
        prev = dict(c.execute('SELECT * FROM financials WHERE room_id=? AND asset=? ORDER BY quarter DESC LIMIT 1', (rid, a['id'])).fetchone())
        forecast = c.execute('SELECT * FROM forecasts WHERE room_id=? AND asset=? AND quarter=?', (rid, a['id'], quarter)).fetchone()
        expected_rev = forecast['revenue'] if forecast else prev['revenue']
        expected_profit = forecast['profit'] if forecast else prev['profit']
        revenue = max(1, round(b['base_revenue'] * b['revenue_index']))
        # Margin already includes business events. Financing and research can reduce profits even with growing sales.
        profit = round(revenue * b['margin'])
        margin = round(profit / revenue * 100, 2)
        surprise = round((profit - expected_profit) / max(abs(expected_profit), expected_rev * .035) * 100, 2)
        rev_growth = round((revenue / prev['revenue'] - 1) * 100, 2)
        profit_growth = round((profit - prev['profit']) / max(abs(prev['profit']), prev['revenue'] * .035) * 100, 2)
        cash = max(1, round(b['cash'] + profit * .48 - revenue * .025))
        debt = max(0, round(b['debt'] - max(profit, 0) * .09 + max(-profit, 0) * .4))
        verdict = '예상 상회' if surprise > 7 else '예상 하회' if surprise < -7 else '예상 부합'
        evidence = query(c, "SELECT id,title FROM news WHERE room_id=? AND day>=? AND day<=? AND sector=? AND kind IN ('company','followup') ORDER BY day DESC,id DESC LIMIT 6",
                         (rid, max(1, day - 5), day, a['id']))
        driver = ' / '.join(x['title'] for x in evidence[:2]) or '분기 중 수요와 비용의 변화'
        explanation = (f'매출은 기준 분기 대비 {rev_growth:+.1f}%, 영업이익은 {profit_growth:+.1f}% 변했습니다. '
                       f'사전에 공개된 영업이익 예상 {expected_profit:,}억원과 비교하면 {verdict}입니다. '
                       f'분기 중 확인할 단서: {driver}.')
        outlook = ('주문과 비용 개선이 이어질지 후속 보도를 확인하세요.' if profit > expected_profit else
                   '이익률 회복과 추가 비용 발생 여부를 살펴보세요.')
        c.execute('INSERT INTO financials VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)',
                  (rid, a['id'], quarter, day, revenue, profit, margin, cash, debt, expected_rev, expected_profit,
                   rev_growth, profit_growth, surprise, verdict, outlook, explanation, json.dumps([x['id'] for x in evidence])))
        c.execute('UPDATE businesses SET cash=?,debt=? WHERE room_id=? AND asset=?', (cash, debt, rid, a['id']))
        reactions[a['id']] = clamp(surprise * .105, -9, 9)
        if quarter < 4:
            # Freeze next-quarter expectations now; they are visible before subsequent news and results.
            next_rev = max(1, round(revenue * (1 + b['growth'] * 6) * rng.uniform(.96, 1.08)))
            next_profit = round(next_rev * clamp(b['margin'] + rng.uniform(-.012, .018), -.08, .33))
            c.execute('INSERT OR IGNORE INTO forecasts VALUES(?,?,?,?,?,?)', (rid, a['id'], quarter + 1, day, next_rev, next_profit))
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
    events = query(c, '''SELECT id,asset,kind,start_day,stage,title,result,resolved_day FROM business_events
                         WHERE room_id=? AND start_day<=? ORDER BY start_day DESC,id DESC LIMIT 100''', (rid, day))
    forecasts = query(c, 'SELECT asset,quarter,published_day,revenue,profit FROM forecasts WHERE room_id=? AND published_day<=? ORDER BY quarter,asset', (rid, day))
    return {'reports': reports, 'forecasts': forecasts, 'events': events,
            'calendar': [{'quarter': q, 'day': q * 6, 'released': day >= q * 6 and any(r['quarter'] == q for r in reports)} for q in range(1, 5)],
            'financial_unit': '가상 억원'}
