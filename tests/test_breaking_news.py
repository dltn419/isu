"""Rare events have hard count/deadline guarantees and no stale-price entry."""
import json
import sqlite3

import pytest
import server
import breaking_news
import classroom_engine as engine
from test_classroom_flow import classroom, advance


def force_plan(c, teacher, dates=(4,9,15)):
    rid = c.get('/api/state',headers=teacher).json()['room']['id']
    with server.conn() as db:
        # Tests may replace dates only before play; real games retain their private plan.
        db.execute('DELETE FROM news WHERE room_id=? AND is_signal=1',(rid,))
        db.execute('DELETE FROM breaking_cases WHERE room_id=?',(rid,))
        db.execute('UPDATE breaking_plans SET dates=? WHERE room_id=?', (json.dumps(dates),rid))
        room=db.execute('SELECT * FROM rooms WHERE id=?',(rid,)).fetchone()
        breaking_news.publish_clues(db,rid,room['day'],room['seed'],room['mood'],server.ASSETS)
    return rid


def inspect_public(value):
    private = {'seed','dates','not_before','shock','slot','breaking_plans','breaking_releases',
               'breaking_cases','warning_day','signal_direction','has_hint','clue_news_id'}
    if isinstance(value,dict):
        assert not private.intersection(value)
        for item in value.values():
            inspect_public(item)
    elif isinstance(value,list):
        for item in value:
            inspect_public(item)


def test_thousand_schedules_guarantee_one_to_three_first_before_day_sixteen():
    db = sqlite3.connect(':memory:')
    db.row_factory = sqlite3.Row
    db.execute('CREATE TABLE breaking_plans(room_id INTEGER PRIMARY KEY,seed INTEGER,dates TEXT,not_before INTEGER)')
    counts = set()
    for seed in range(1000):
        dates = breaking_news.ensure_plan(db,seed+1,seed)
        assert 1 <= len(dates) <= 3
        assert 4 <= dates[0] <= 15
        assert dates[-1] <= 22
        assert set(dates).isdisjoint({6,12,18,24})
        assert all(b-a>=4 for a,b in zip(dates,dates[1:]))
        assert breaking_news.ensure_plan(db,seed+1,seed,not_before=20) == dates
        counts.add(len(dates))
    assert counts == {1,2,3}


def test_opening_news_price_and_current_quote_are_one_public_result(classroom):
    c, teacher, learner = classroom
    rid = force_plan(c,teacher)
    for day in (1,2):
        assert advance(c,teacher,day).status_code == 200
    old = c.get('/api/state',headers=learner).json()
    assert not any(n['is_breaking'] for n in old['news'])
    inspect_public(old)
    assert advance(c,teacher,3).status_code == 200
    fresh = c.get('/api/state',headers=learner).json()
    news = [n for n in fresh['news'] if n['is_breaking']]
    assert len(news) == 1 and news[0]['day'] == 4
    aid = news[0]['sector']
    a = next(a for a in fresh['assets'] if a['id']==aid)
    previous = next(a for a in old['assets'] if a['id']==aid)
    assert 19.9 <= abs(a['change']) <= 30.1
    assert fresh['highlights'][0]['id'] == news[0]['id']
    assert '오늘 시작 가격에 함께 반영' in news[0]['body']
    assert c.post('/api/orders',headers=learner,json={
        'asset':aid,'side':'buy','qty':1,'reason':'옛 가격 주문',
        'expected_day':4,'expected_price':previous['price']}).status_code == 409
    result = c.post('/api/orders',headers=learner,json={
        'asset':aid,'side':'buy','qty':1,'reason':'속보와 실제 수치 확인',
        'expected_day':4,'expected_price':a['price'],'evidence_ids':[news[0]['id']]}).json()
    assert result['price'] == a['price']
    with server.conn() as db:
        assert db.execute('SELECT impact FROM news WHERE id=?',(news[0]['id'],)).fetchone()[0] == 0
        seed = db.execute('SELECT seed FROM rooms WHERE id=?',(rid,)).fetchone()[0]
        original = [dict(r) for r in db.execute('SELECT * FROM business_events WHERE id=?',(news[0]['event_id'],))]
        assert breaking_news.publish_open(db,rid,4,seed,'neutral',server.ASSETS)
        assert [dict(r) for r in db.execute('SELECT * FROM business_events WHERE id=?',(news[0]['event_id'],))] == original
    server.init()
    inspect_public(c.get('/api/state',headers=teacher).json())
    assert len([n for n in c.get('/api/state',headers=learner).json()['news'] if n['is_breaking']]) == 1
    assert advance(c,teacher,4).status_code == 200
    next_state = c.get('/api/state',headers=learner).json()
    a = next(a for a in next_state['assets'] if a['id']==aid)
    assert abs(a['change']) <= {'stable':7,'growth':12,'high':20}[a['risk']] + .1


@pytest.mark.parametrize('dates', ((4,), (15,), (4,22), (4,13,22)))
def test_full_year_publishes_exact_scheduled_count_and_earnings_evidence(classroom,dates):
    c, teacher, learner = classroom
    count = len(dates)
    rid = force_plan(c,teacher,dates)
    for day in range(1,24):
        assert advance(c,teacher,day).status_code == 200
        s = c.get('/api/state',headers=learner).json()
        assert len([n for n in s['news'] if n['is_breaking']]) == sum(d<=day+1 for d in dates)
    final = c.get('/api/state',headers=learner).json()
    news = [n for n in final['news'] if n['is_breaking']]
    assert sorted(n['day'] for n in news) == list(dates)
    assert len({n['sector'] for n in news}) == count
    assert min(n['day'] for n in news) <= 15
    for n in news:
        reports = [r for r in final['reports'] if r['quarter']>0 and n['id'] in r['evidence_ids']]
        assert reports
        with server.conn() as db:
            effect = db.execute("SELECT * FROM operating_effects WHERE event_id=? AND label='사업 운영 효과'", (n['event_id'],)).fetchone()
            assert effect['revenue_delta'] == pytest.approx(n['metrics']['revenue_pct']/100)
            assert effect['margin_delta'] == pytest.approx(n['metrics']['margin_pp']/100)
    assert advance(c,teacher,24).status_code == 200
    with server.conn() as db:
        assert db.execute('SELECT COUNT(*) FROM breaking_releases WHERE room_id=?',(rid,)).fetchone()[0] == count


def test_both_directions_exist_and_restart_does_not_redraw():
    db = sqlite3.connect(':memory:');db.row_factory = sqlite3.Row
    db.executescript('CREATE TABLE news(id INTEGER PRIMARY KEY,room_id INTEGER,day INTEGER,title TEXT,body TEXT,sector TEXT,impact REAL DEFAULT 0,active INTEGER DEFAULT 1);CREATE TABLE orders(id INTEGER PRIMARY KEY);')
    engine.initialize_schema(db)
    signs = set()
    for seed in range(24):
        rid = seed+1
        engine.ensure_room(db,rid,seed,1,server.ASSETS)
        breaking_news.ensure_plan(db,rid,seed)
        db.execute('UPDATE breaking_plans SET dates=? WHERE room_id=?', ('[4]',rid))
        result = breaking_news.publish_open(db,rid,4,seed,'neutral',server.ASSETS)
        signs.add(next(iter(result.values()))>0)
        assert breaking_news.publish_open(db,rid,4,seed,'positive',server.ASSETS) == result
    assert signs == {False,True}


def test_failed_open_rolls_back_news_prices_and_business_effects(classroom,monkeypatch):
    c, teacher, learner = classroom
    rid = force_plan(c,teacher)
    for day in (1,2):
        assert advance(c,teacher,day).status_code == 200
    before = c.get('/api/state',headers=learner).json()
    def fail(*args):
        raise RuntimeError('failure after breaking publication')
    with monkeypatch.context() as patch:
        patch.setattr(server,'generate_prices',fail)
        with pytest.raises(RuntimeError,match='failure after breaking'):
            advance(c,teacher,3)
    assert c.get('/api/state',headers=learner).json() == before
    with server.conn() as db:
        assert db.execute('SELECT COUNT(*) FROM breaking_releases WHERE room_id=?',(rid,)).fetchone()[0] == 0
    assert advance(c,teacher,3).status_code == 200
    assert len([n for n in c.get('/api/state',headers=learner).json()['news'] if n['is_breaking']]) == 1


def test_reset_archives_and_rerolls_private_plan_without_cross_room_changes(classroom):
    c, teacher, learner = classroom
    rid = force_plan(c,teacher)
    for day in (1,2,3):
        assert advance(c,teacher,day).status_code == 200
    other = c.post('/api/rooms',json={'name':'다른 교실','password':'other123'}).json()
    other_auth = {'Authorization':'Bearer '+other['token']}
    other_state = c.get('/api/state',headers=other_auth).json()
    with server.conn() as db:
        other_plan = dict(db.execute('SELECT * FROM breaking_plans WHERE room_id!=?',(rid,)).fetchone())
    assert c.post('/api/admin/reset',headers=teacher,json={
        'confirmation':'초기화','expected_day':4,'expected_generation':0}).status_code == 200
    after = c.get('/api/state',headers=learner).json()
    assert not any(n['is_breaking'] for n in after['news'])
    backup = c.get('/api/admin/reset-backup',headers=teacher).json()
    assert len(backup['tables']['breaking_releases']) == 1
    assert len(backup['tables']['breaking_plans']) == 1
    with server.conn() as db:
        dates = json.loads(db.execute('SELECT dates FROM breaking_plans WHERE room_id=?',(rid,)).fetchone()[0])
        assert 1 <= len(dates) <= 3 and dates[0] <= 15
        assert dict(db.execute('SELECT * FROM breaking_plans WHERE room_id!=?',(rid,)).fetchone()) == other_plan
    assert c.get('/api/state',headers=other_auth).json() == other_state


@pytest.mark.parametrize('day',(14,16))
def test_existing_games_get_future_slots_without_rewriting_history(classroom,monkeypatch,day):
    c, teacher, learner = classroom
    with monkeypatch.context() as patch:
        patch.setattr(breaking_news,'publish_open',lambda *args:{})
        for d in range(1,day):
            assert advance(c,teacher,d).status_code == 200
    before = c.get('/api/state',headers=learner).json()
    rid = before['room']['id']
    with server.conn() as db:
        db.execute('DELETE FROM breaking_plans WHERE room_id=?',(rid,))
        db.execute('DELETE FROM breaking_cases WHERE room_id=?',(rid,))
    server.init()
    after=c.get('/api/state',headers=learner).json()
    # Existing history is immutable; an eligible warning can be added only today.
    old_ids={n['id'] for n in before['news']}
    assert [n for n in after['news'] if n['id'] in old_ids] == before['news']
    assert all(n['day']==day and n['is_signal'] for n in after['news'] if n['id'] not in old_ids)
    assert after['assets']==before['assets'] and after['player']==before['player']
    with server.conn() as db:
        dates = json.loads(db.execute('SELECT dates FROM breaking_plans WHERE room_id=?',(rid,)).fetchone()[0])
    assert dates[0] > day
    if day == 14:
        assert dates[0] == 15
