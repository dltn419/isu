"""Timing tests: a news promise must not become revenue before its operating window."""
import sqlite3
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import classroom_engine as engine
import server
from test_classroom import school, advance


def laboratory():
    c = sqlite3.connect(':memory:')
    c.row_factory = sqlite3.Row
    c.executescript('''
      CREATE TABLE news(id INTEGER PRIMARY KEY,room_id INTEGER,day INTEGER,title TEXT,body TEXT,sector TEXT,impact REAL DEFAULT 0,active INTEGER DEFAULT 1);
      CREATE TABLE orders(id INTEGER PRIMARY KEY);
    ''')
    engine.initialize_schema(c)
    engine.ensure_room(c, 1, 42, 1, server.ASSETS)
    c.execute('UPDATE businesses SET base_revenue=1000,revenue_index=1,margin=.1,growth=0 WHERE room_id=1')
    engine.record_business_day(c, 1, 1, server.ASSETS)
    return c


def test_year_end_project_has_checkpoints_and_no_early_revenue():
    c = laboratory()
    cur = c.execute('''INSERT INTO business_events(room_id,asset,kind,direction,magnitude,start_day,due_day,title,horizon,expected_start,expected_end,delayed)
                       VALUES(1,'HBEL','contract',1,.2,1,3,'연말 공장 납품','year_end',19,24,1)''')
    eid = cur.lastrowid
    source = engine.article(c,1,1,'연말 공장 계획','연말부터 납품을 기대합니다.','HBEL',event_id=eid,horizon='year_end',expected_start=19,expected_end=24)
    engine.add_operating_effect(c,1,eid,'HBEL',2,18,0,-.01,'준비 비용')
    for day in range(2,19):
        engine.evolve_businesses(c,1,day,42,server.ASSETS)
        engine.resolve_events(c,1,day,42,server.ASSETS)
        engine.release_earnings(c,1,day,42,server.ASSETS)
    assert c.execute('SELECT checkpoint_count FROM business_events WHERE id=?',(eid,)).fetchone()[0] >= 2
    assert c.execute("SELECT COUNT(*) FROM operating_effects WHERE label='사업 운영 효과'").fetchone()[0] == 0
    q1 = c.execute("SELECT * FROM financials WHERE room_id=1 AND asset='HBEL' AND quarter=1").fetchone()
    assert q1['margin'] < 10  # Preparation expense, not anticipated future sales.
    for day in range(19,25):
        engine.evolve_businesses(c,1,day,42,server.ASSETS)
        engine.resolve_events(c,1,day,42,server.ASSETS)
        engine.release_earnings(c,1,day,42,server.ASSETS)
    effect = c.execute("SELECT * FROM operating_effects WHERE label='사업 운영 효과'").fetchone()
    assert effect['start_day'] == 19
    assert effect['end_day'] == 24
    q4 = c.execute("SELECT * FROM financials WHERE room_id=1 AND asset='HBEL' AND quarter=4").fetchone()
    import json
    assert source in json.loads(q4['evidence_ids'])  # An old article still explains the final quarter.
    public = engine.public_data(c,1,24)
    assert all('revenue_delta' not in e and 'magnitude' not in e for e in public['events'])
    c.close()


def test_quarter_uses_operating_days_and_short_effect_expires():
    c = laboratory()
    engine.add_operating_effect(c,1,1,'HBEL',6,6,.6,0,'하루 주문 급증')
    for day in range(2,13):
        # Hold the operating baseline still to isolate accounting, not random motion.
        engine.release_earnings(c,1,day,42,server.ASSETS)
    q1 = c.execute("SELECT revenue FROM financials WHERE asset='HBEL' AND quarter=1").fetchone()[0]
    q2 = c.execute("SELECT revenue FROM financials WHERE asset='HBEL' AND quarter=2").fetchone()[0]
    assert q1 == 1100  # Five 1,000 days and one 1,600 day, rather than a 1,600 final-day snapshot.
    assert q2 == 1000
    c.close()


def test_full_term_deposit_is_exactly_ten_percent_and_same_day_has_no_interest(school):
    client, room, teacher, learner = school
    assert client.post('/api/deposits',headers=learner,json={'principal':100000,'term':24}).status_code == 200
    for _ in range(23):
        advance(client,teacher)
    s = client.get('/api/state',headers=learner).json()
    assert s['player']['cash'] == 110000
    assert s['player']['profit'] == 10000
    assert s['benchmark']['progress_rate'] == .1


def test_same_day_early_close_cannot_create_risk_free_money(school):
    client, room, teacher, learner = school
    for _ in range(3):
        assert client.post('/api/deposits',headers=learner,json={'principal':100000,'term':6}).status_code == 200
        did = client.get('/api/state',headers=learner).json()['deposits'][0]['id']
        r = client.post(f'/api/deposits/{did}/close',headers=learner)
        assert r.json()['paid'] == 100000
    assert client.get('/api/state',headers=learner).json()['player']['cash'] == 100000


def test_horizon_dates_are_public_but_outcomes_are_not(school):
    client,room,teacher,learner = school
    for _ in range(4):
        advance(client,teacher)
    s = client.get('/api/state',headers=learner).json()
    long_news = [n for n in s['news'] if n['horizon'] in ('next_quarter','year_end')]
    assert long_news
    assert all(n['expected_start'] and n['expected_end']<=24 for n in long_news)
    assert 'operating_effects' not in s and 'business_daily' not in s
    assert all(not {'direction','magnitude','due_day','revenue_delta','margin_delta'} & e.keys() for e in s['events'])
