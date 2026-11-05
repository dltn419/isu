"""Publicly announced business scenarios and incremental market expectations.

Only announced targets/results enter this ledger. Private future draws never do.
The initial quarterly forecast stays immutable; evolving estimates are separate.
"""
def clamp(n, lo, hi):
    return max(lo, min(hi, n))


def initialize(c):
    c.executescript('''
      CREATE TABLE IF NOT EXISTS event_expectations(
        event_id INTEGER PRIMARY KEY,room_id INTEGER NOT NULL,asset TEXT NOT NULL,
        announced_day INTEGER NOT NULL,updated_day INTEGER NOT NULL,
        revenue_delta REAL NOT NULL,margin_delta REAL NOT NULL,weight REAL NOT NULL,
        start_day INTEGER NOT NULL,end_day INTEGER NOT NULL,ramp_days INTEGER NOT NULL,
        fade_days INTEGER NOT NULL,prep_start INTEGER NOT NULL,prep_end INTEGER NOT NULL,
        prep_margin REAL NOT NULL,reference_margin REAL NOT NULL,priced_level REAL NOT NULL);
      CREATE TABLE IF NOT EXISTS market_estimates(
        room_id INTEGER NOT NULL,asset TEXT NOT NULL,quarter INTEGER NOT NULL,
        published_day INTEGER NOT NULL,revenue INTEGER NOT NULL,profit INTEGER NOT NULL,
        PRIMARY KEY(room_id,asset,quarter,published_day));
      CREATE INDEX IF NOT EXISTS idx_estimate_date ON market_estimates(room_id,quarter,published_day);
    ''')
    additions = {
        'news': {'metrics': "TEXT NOT NULL DEFAULT '{}'"},
        'business_events': {
            'model_version': 'INTEGER NOT NULL DEFAULT 1',
            'target_revenue_delta': 'REAL', 'target_margin_delta': 'REAL',
            'preparation_margin_delta': 'REAL NOT NULL DEFAULT 0',
        },
        'forecasts': {'base_revenue': 'REAL', 'base_margin': 'REAL'},
        'financials': {
            'market_expected_revenue': 'INTEGER', 'market_expected_profit': 'INTEGER',
            'market_surprise': 'REAL', 'market_verdict': 'TEXT', 'market_expectation_day': 'INTEGER',
        },
    }
    for table, fields in additions.items():
        known = {r[1] for r in c.execute(f'PRAGMA table_info({table})')}
        for field, ddl in fields.items():
            if field not in known:
                c.execute(f'ALTER TABLE {table} ADD COLUMN {field} {ddl}')


def target_metrics(kind, direction, magnitude, preparation=False):
    """Round the published numbers FIRST; those exact numbers drive operations."""
    revenue = direction * magnitude * (.65 if kind == 'research' else .16 if kind == 'cost' else 1)
    margin = direction * magnitude * (.23 if kind == 'cost' else .075)
    prep = -magnitude * (.07 if kind == 'research' else .025) if preparation else 0
    return {'revenue_pct': round(revenue * 100, 1), 'margin_pp': round(margin * 100, 2),
            'preparation_margin_pp': round(prep * 100, 2), 'status': 'target'}


def metric_sentence(metrics, confirmed=False):
    # Amounts describe this project at full operation, not the entire quarter.
    return (f'완전 가동 시 회사 전체 매출 {metrics["revenue_pct"]:+.1f}%, '
            f'영업이익률 {metrics["margin_pp"]:+.2f}%p의 ' +
            ('영업 효과를 확인했습니다. ' if confirmed else '변화를 목표로 합니다. ') +
            '분기 전체 수치는 실제 운영 일수와 가동 초기 반영률, 다른 사업의 영향을 함께 합산합니다. ')


def revise_event(c, rid, event_id, asset, day, metrics, start, end, horizon,
                 *, weight=.54, reference_margin=.1, prep_start=0, prep_end=0,ramp_days=None,fade_days=None):
    old = c.execute('SELECT * FROM event_expectations WHERE event_id=?', (event_id,)).fetchone()
    announced = old['announced_day'] if old else day
    margin = old['reference_margin'] if old else reference_margin
    rev, delta_margin = metrics['revenue_pct'] / 100, metrics['margin_pp'] / 100
    duration = clamp((end - start + 1) / 6, .25, 1.5) if start <= end else 0
    discount = .85 ** (max(0, start - announced) / 6)
    profit_change = ((1 + rev) * (margin + delta_margin) - margin) / max(.035, abs(margin))
    level = clamp(profit_change * weight * duration * discount * 10, -8, 8)
    previous_level = old['priced_level'] if old else 0
    # Same targets, dates and confidence => exactly zero repeated price reward.
    change = round(level - previous_level, 6)
    c.execute('''INSERT INTO event_expectations VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)
                 ON CONFLICT(event_id) DO UPDATE SET updated_day=excluded.updated_day,
                   revenue_delta=excluded.revenue_delta,margin_delta=excluded.margin_delta,
                   weight=excluded.weight,start_day=excluded.start_day,end_day=excluded.end_day,
                   ramp_days=excluded.ramp_days,fade_days=excluded.fade_days,
                   prep_start=excluded.prep_start,prep_end=excluded.prep_end,
                   prep_margin=excluded.prep_margin,priced_level=excluded.priced_level''',
              (event_id,rid,asset,announced,day,rev,delta_margin,weight,start,end,
               ramp_days if ramp_days is not None else (1 if horizon == 'short' else 2),
               fade_days if fade_days is not None else (1 if horizon == 'short' else 0),
               prep_start,prep_end,metrics.get('preparation_margin_pp',0)/100,margin,level))
    return change


def quarter_factors(c, rid, asset, quarter, base_margin):
    states = c.execute('SELECT * FROM event_expectations WHERE room_id=? AND asset=?', (rid,asset)).fetchall()
    revenues, profits = [], []
    for day in range(quarter * 6 - 5, quarter * 6 + 1):
        revenue, margin = 0, base_margin
        for e in states:
            if e['start_day'] <= day <= e['end_day']:
                ramp = min(1, (day-e['start_day']+1)/e['ramp_days'])
                fade = min(1, (e['end_day']-day+1)/(e['fade_days']+1)) if e['fade_days'] else 1
                w = min(ramp,fade) * e['weight']
                revenue += e['revenue_delta'] * w
                margin += e['margin_delta'] * w
            if e['prep_start'] <= day <= e['prep_end']:
                margin += e['prep_margin']
        factor = 1 + clamp(revenue, -.55, 1.2)
        revenues.append(factor)
        profits.append(factor * clamp(margin, -.12, .36))
    return sum(revenues)/6, sum(profits)/6


def estimate(c, rid, asset, quarter, base_revenue, base_margin):
    revenue_factor, profit_factor = quarter_factors(c,rid,asset,quarter,base_margin)
    return max(1,round(base_revenue*revenue_factor)), round(base_revenue*profit_factor)


def refresh_estimates(c, rid, day):
    """Snapshot information known now; never replace forecasts or released reports."""
    forecasts = c.execute('''SELECT * FROM forecasts f WHERE room_id=? AND published_day<=?
      AND NOT EXISTS(SELECT 1 FROM financials r WHERE r.room_id=f.room_id
                     AND r.asset=f.asset AND r.quarter=f.quarter)''', (rid,day)).fetchall()
    for f in forecasts:
        base_rev = f['base_revenue'] if f['base_revenue'] is not None else f['revenue']
        base_margin = f['base_margin'] if f['base_margin'] is not None else f['profit']/max(1,f['revenue'])
        rev, profit = estimate(c,rid,f['asset'],f['quarter'],base_rev,base_margin)
        c.execute('''INSERT INTO market_estimates VALUES(?,?,?,?,?,?)
          ON CONFLICT(room_id,asset,quarter,published_day) DO UPDATE SET
          revenue=excluded.revenue,profit=excluded.profit''', (rid,f['asset'],f['quarter'],day,rev,profit))


def latest(c, rid, asset, quarter, day):
    return c.execute('''SELECT asset,quarter,published_day,revenue,profit FROM market_estimates
                        WHERE room_id=? AND asset=? AND quarter=? AND published_day<=?
                        ORDER BY published_day DESC LIMIT 1''', (rid,asset,quarter,day)).fetchone()


def public_estimates(c, rid, day):
    return [dict(r) for r in c.execute('''SELECT m.asset,m.quarter,m.published_day,m.revenue,m.profit
      FROM market_estimates m WHERE m.room_id=? AND m.published_day=(
        SELECT MAX(x.published_day) FROM market_estimates x WHERE x.room_id=m.room_id
        AND x.asset=m.asset AND x.quarter=m.quarter AND x.published_day<=?)
      ORDER BY m.quarter,m.asset''', (rid,day))]
