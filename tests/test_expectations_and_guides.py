"""Causal accounting, incremental expectations, public-only NPCs and room isolation."""
import json
import pytest
import classroom_engine as engine
import market_expectations as expectations
import server
from test_horizons import laboratory
from test_classroom import school, advance


def test_public_target_and_confirmed_numbers_are_the_operating_inputs():
    c = laboratory()
    engine.publish_news(c,1,1,42,'neutral',server.ASSETS)
    for n in c.execute("SELECT * FROM news WHERE kind='company'"):
        m = json.loads(n['metrics'])
        e = c.execute('SELECT * FROM business_events WHERE id=?',(n['event_id'],)).fetchone()
        assert m['revenue_pct']/100 == pytest.approx(e['target_revenue_delta'])
        assert m['margin_pp']/100 == pytest.approx(e['target_margin_delta'])
        assert f'{m["revenue_pct"]:+.1f}%' in n['body']
        assert f'{m["margin_pp"]:+.2f}%p' in n['body']
    for day in range(2,25):
        engine.evolve_businesses(c,1,day,42,server.ASSETS)
        engine.resolve_events(c,1,day,42,server.ASSETS)
        engine.release_earnings(c,1,day,42,server.ASSETS)
        engine.publish_news(c,1,day,42,'neutral',server.ASSETS)
    confirmations = c.execute("SELECT * FROM news WHERE certainty='사실 확인'").fetchall()
    assert confirmations
    for n in confirmations:
        m = json.loads(n['metrics'])
        actual = c.execute("SELECT * FROM operating_effects WHERE event_id=? AND label='사업 운영 효과'",(n['event_id'],)).fetchone()
        assert actual['revenue_delta'] == pytest.approx(m['revenue_pct']/100)
        assert actual['margin_delta'] == pytest.approx(m['margin_pp']/100)
    assert c.execute("SELECT COUNT(*) FROM news WHERE day=24 AND kind='company' AND impact!=0").fetchone()[0] == 0
    c.close()


def test_unchanged_long_term_checkpoint_does_not_repeat_price_reward():
    c = laboratory()
    eid = c.execute("""INSERT INTO business_events(room_id,asset,kind,direction,magnitude,start_day,due_day,title,
        horizon,expected_start,expected_end,model_version,target_revenue_delta,target_margin_delta)
        VALUES(1,'HBEL','contract',1,.1,1,3,'연말 납품','year_end',19,24,2,.1,.01)""").lastrowid
    metrics = {'revenue_pct':10,'margin_pp':1,'preparation_margin_pp':0,'status':'target'}
    original = expectations.revise_event(c,1,eid,'HBEL',1,metrics,19,24,'year_end')
    assert original>0
    engine.resolve_events(c,1,3,42,server.ASSETS)
    update = c.execute('SELECT * FROM news WHERE event_id=?',(eid,)).fetchone()
    assert json.loads(update['metrics'])['status']=='unchanged'
    assert update['impact']==0
    assert expectations.revise_event(c,1,eid,'HBEL',3,metrics,19,24,'year_end')==0
    c.close()


def test_positive_business_result_can_disappoint_and_same_result_is_not_repaid():
    c = laboratory()
    target = {'revenue_pct':10,'margin_pp':1,'preparation_margin_pp':0}
    first = expectations.revise_event(c,1,100,'HBEL',1,target,7,12,'next_quarter',weight=.536)
    actual = {'revenue_pct':2,'margin_pp':.1,'preparation_margin_pp':0}
    change = expectations.revise_event(c,1,100,'HBEL',7,actual,7,12,'next_quarter',weight=1)
    assert first>0 and actual['revenue_pct']>0 and change<0
    assert expectations.revise_event(c,1,100,'HBEL',8,actual,7,12,'next_quarter',weight=1)==0
    c.close()


def test_earnings_price_reaction_excludes_already_public_operating_effect():
    c = laboratory()
    c.execute("UPDATE forecasts SET revenue=1000,profit=100,base_revenue=1000,base_margin=.1 WHERE asset='HBEL'")
    original = dict(c.execute("SELECT * FROM forecasts WHERE asset='HBEL'").fetchone())
    m = {'revenue_pct':20,'margin_pp':2,'preparation_margin_pp':0}
    expectations.revise_event(c,1,100,'HBEL',1,m,1,6,'short',weight=1,ramp_days=1,fade_days=0)
    engine.add_operating_effect(c,1,100,'HBEL',1,6,.2,.02,'공개된 영업 효과')
    c.execute("DELETE FROM business_daily WHERE asset='HBEL'")
    for day in range(1,6):
        engine.record_business_day(c,1,day,server.ASSETS)
    expectations.refresh_estimates(c,1,5)
    assert expectations.latest(c,1,'HBEL',1,5)['profit']==144
    reactions = engine.release_earnings(c,1,6,42,server.ASSETS)
    r = c.execute("SELECT * FROM financials WHERE asset='HBEL' AND quarter=1").fetchone()
    assert r['profit']==r['market_expected_profit']==144
    assert r['expected_profit']==100
    assert r['surprise']==44 and r['market_surprise']==0
    assert reactions['HBEL']==0
    assert dict(c.execute("SELECT * FROM forecasts WHERE asset='HBEL' AND quarter=1").fetchone())==original
    c.close()


def test_legacy_event_resolves_without_rewriting_published_news():
    c = laboratory()
    eid = c.execute("""INSERT INTO business_events(room_id,asset,kind,direction,magnitude,start_day,due_day,title,delayed)
                        VALUES(1,'HBEL','sales',1,.1,1,2,'기존 주문 기사',1)""").lastrowid
    nid = engine.article(c,1,1,'기존 기사','이미 공개된 내용','HBEL',1.1,event_id=eid)
    before = dict(c.execute('SELECT * FROM news WHERE id=?',(nid,)).fetchone())
    engine.initialize_schema(c)
    engine.resolve_events(c,1,2,42,server.ASSETS)
    assert dict(c.execute('SELECT * FROM news WHERE id=?',(nid,)).fetchone())==before
    assert c.execute('SELECT model_version FROM business_events WHERE id=?',(eid,)).fetchone()[0]==1
    assert c.execute('SELECT COUNT(*) FROM operating_effects WHERE event_id=?',(eid,)).fetchone()[0]==1
    c.close()


def test_npc_activity_uses_only_own_room_real_fills_in_three_day_window(school):
    client,room,teacher,learner=school
    empty=client.get('/api/state',headers=learner).json()
    assert empty['market_activity']['items']==[]
    assert len(empty['guides'])==3 and len(empty['highlights'])==5
    order={'asset':'HBEL','qty':2,'side':'buy','reason':'숫자 비교'}
    assert client.post('/api/orders',headers=learner,json=order).status_code==200
    assert client.post('/api/orders',headers=learner,json={**order,'qty':1,'side':'sell'}).status_code==200
    another=client.post('/api/rooms',json={'name':'다른 반','password':'other123'}).json()
    other=client.post('/api/join',json={'code':another['code'],'name':'다른 학생','pin':'1234'}).json()
    assert client.post('/api/orders',headers={'Authorization':'Bearer '+other['token']},json=order).status_code==200
    s=client.get('/api/state',headers=learner).json()
    row=s['market_activity']['items'][0]
    assert row=={'asset':'HBEL','trade_count':2,'quantity':3,'amount':30000,'buy_quantity':2,'sell_quantity':1}
    assert '테스트 학생' not in json.dumps(s['guides'],ensure_ascii=False)
    assert 'player_id' not in json.dumps(s['market_activity'])
    assert client.get('/api/state',headers=teacher).json()['market_activity']==s['market_activity']
    for _ in range(3):advance(client,teacher)
    assert client.get('/api/state',headers=learner).json()['market_activity']['items']==[]


def test_public_summaries_cannot_expose_private_price_or_future_outcome(school):
    client,room,teacher,learner=school
    for _ in range(7):advance(client,teacher)
    s=client.get('/api/state',headers=learner).json()
    private={'impact','magnitude','direction','priced_level','weight','base_revenue','base_margin','outcome_scale','due_day'}
    def inspect(value):
        if isinstance(value,dict):
            assert not private & value.keys()
            for v in value.values():inspect(v)
        elif isinstance(value,list):
            for v in value:inspect(v)
    for key in ['news','events','market_estimates','highlights','guides','market_activity']:inspect(s[key])
    assert all(m['published_day']<=s['room']['day'] for m in s['market_estimates'])
    assert {h['id'] for h in s['highlights']} <= {n['id'] for n in s['news'] if n['day']==s['room']['day']}
    assert all(set(g['evidence_ids'])<={n['id'] for n in s['news']} for g in s['guides'])
