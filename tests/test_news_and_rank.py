"""Causal news pricing, imperfect advance clues, and private live class ranks."""
import json
import sqlite3

import pytest
import server
import breaking_news
import bond_income
import classroom_engine as engine
from test_classroom_flow import classroom, advance
from test_breaking_news import force_plan, inspect_public


@pytest.mark.parametrize('day', (1,21,22,23,24))
@pytest.mark.parametrize('impact', (-1.2,0,1.2))
def test_new_information_is_spread_once_and_finishes_by_year_end(day,impact):
    n={'day':day,'impact':impact,'pricing_version':2,'pricing_end':None}
    parts=[server.news_contribution(n,d) for d in range(day,day+5)]
    assert parts[0]==0 and parts[-1]==0
    assert sum(parts)==pytest.approx(impact*2.5 if day<24 else 0)
    assert all(server.news_contribution(n,d)==0 for d in range(25,29))
    if day<=21:
        assert parts[1:4]==pytest.approx([impact*1.5,impact*.625,impact*.375])


def test_legacy_news_is_not_replayed_after_upgrade_and_resolved_clue_stops():
    old={'day':8,'impact':1.2,'pricing_version':1,'pricing_end':None}
    assert [server.news_contribution(old,d) for d in range(8,13)]==[0,1.2,0,0,0]
    clue={**old,'pricing_version':2,'pricing_end':9}
    assert server.news_contribution(clue,9)==pytest.approx(1.8)
    assert server.news_contribution(clue,10)==0


def test_public_price_explanation_reconciles_and_uses_only_published_articles(classroom):
    c,teacher,learner=classroom
    assert advance(c,teacher,1).status_code==200
    s=c.get('/api/state',headers=learner).json()
    ids={n['id']:n for n in s['news']}
    assert all(a.get('price_context') for a in s['assets'] if a['type']=='stock')
    for a in s['assets']:
        p=a.get('price_context')
        if not p:continue
        assert sum(p[k] for k in ('news','earnings','other'))==pytest.approx(a['change'],abs=.00006)
        assert all(ids[n]['day']<s['room']['day'] for n in p['news_ids'])
    inspect_public(s)


def test_warning_precedes_same_company_breaking_and_is_linked_to_later_earnings(classroom):
    c,teacher,learner=classroom
    rid=force_plan(c,teacher,(4,))
    for day in (1,2):
        current=c.get('/api/state',headers=learner).json()
        today_clues=[n for n in current['news'] if n['is_signal'] and n['day']==day]
        assert all(n['id'] in {h['id'] for h in current['highlights']} for n in today_clues)
        assert advance(c,teacher,day).status_code==200
    before=c.get('/api/state',headers=learner).json()
    warnings=[n for n in before['news'] if n['is_signal']]
    assert len(warnings)==1
    warning=warnings[0]
    assert 2<=4-warning['day']<=3
    assert warning['certainty']=='취재·미확정'
    assert warning['metrics']=={} and warning['expected_start'] is None
    assert '반대로' in warning['body']
    inspect_public(before)
    assert advance(c,teacher,3).status_code==200
    after=c.get('/api/state',headers=learner).json()
    breaking=next(n for n in after['news'] if n['is_breaking'])
    linked=next(n for n in after['news'] if n['id']==warning['id'])
    assert breaking['sector']==warning['sector'] and linked['event_id']==breaking['event_id']
    assert linked['body']==warning['body'] and linked['metrics']==warning['metrics']
    price=next(a for a in after['assets'] if a['id']==breaking['sector'])
    assert price['price_context']['breaking']
    assert price['price_context']['news_ids']==[breaking['id']]
    with server.conn() as db:
        saved=dict(db.execute('SELECT * FROM news WHERE id=?',(warning['id'],)).fetchone())
        assert server.news_contribution(saved,5)==0
        cases=[dict(r) for r in db.execute('SELECT * FROM breaking_cases WHERE room_id=?',(rid,))]
    server.init()
    with server.conn() as db:
        assert [dict(r) for r in db.execute('SELECT * FROM breaking_cases WHERE room_id=?',(rid,))]==cases
    for day in (4,5):assert advance(c,teacher,day).status_code==200
    final=c.get('/api/state',headers=learner).json()
    report=next(r for r in final['reports'] if r['asset']==breaking['sector'] and r['quarter']==1)
    assert warning['id'] in report['evidence_ids'] and breaking['id'] in report['evidence_ids']


def test_clues_sometimes_reverse_and_do_not_expose_future_results():
    db=sqlite3.connect(':memory:');db.row_factory=sqlite3.Row
    db.executescript('CREATE TABLE news(id INTEGER PRIMARY KEY,room_id INTEGER,day INTEGER,title TEXT,body TEXT,sector TEXT,impact REAL DEFAULT 0,active INTEGER DEFAULT 1);CREATE TABLE orders(id INTEGER PRIMARY KEY);')
    engine.initialize_schema(db)
    matched=0
    for seed in range(100):
        rid=seed+1;engine.ensure_room(db,rid,seed,1,server.ASSETS)
        breaking_news.ensure_plan(db,rid,seed)
        db.execute('UPDATE breaking_plans SET dates=? WHERE room_id=?',('[4]',rid))
        for day in (1,2,3):breaking_news.publish_clues(db,rid,day,seed,'neutral',server.ASSETS)
        case=db.execute('SELECT * FROM breaking_cases WHERE room_id=?',(rid,)).fetchone()
        warning=db.execute('SELECT * FROM news WHERE id=?',(case['clue_news_id'],)).fetchone()
        assert warning['is_signal'] and warning['event_id'] is None
        assert warning['expected_start'] is None and json.loads(warning['metrics'])=={}
        result=breaking_news.publish_open(db,rid,4,seed,'neutral',server.ASSETS)
        matched+=next(iter(result.values()))*case['signal_direction']>0
    assert 60<matched<90  # An informative clue, with real counterexamples.
    db.close()


def test_live_rank_ties_fees_teacher_adjustments_and_room_isolation(classroom):
    c,teacher,learner=classroom
    s=c.get('/api/state',headers=learner).json();code=s['room']['code'];rid=s['room']['id']
    learners=[learner]
    for name in ('비교 가','비교 나','현금 보유'):
        token=c.post('/api/join',json={'code':code,'name':name,'pin':'1234'}).json()['token']
        learners.append({'Authorization':'Bearer '+token})
    for auth,qty in zip(learners,(2,1,1)):
        assert c.post('/api/orders',headers=auth,json={'asset':'HBEL','side':'buy','qty':qty,'reason':'뉴스 비교 후 투자'}).status_code==200
    assert c.get('/api/state',headers=learners[-1]).json()['ranking']['rank']==1
    with server.conn() as db:db.execute("UPDATE prices SET price=10500 WHERE room_id=? AND day=1 AND asset='HBEL'",(rid,))
    ranks=[c.get('/api/state',headers=a).json()['ranking'] for a in learners]
    assert [r['rank'] for r in ranks]==[1,2,2,4]
    assert [r['tied'] for r in ranks]==[False,True,True,False]
    assert all(r['total']==4 for r in ranks)
    pid=c.get('/api/state',headers=learners[-1]).json()['player']['id']
    for amount in (50000,-20000):
        assert c.post('/api/admin/cash',headers=teacher,json={'player_id':pid,'amount':amount,'reason':'교사 상벌점'}).status_code==200
        assert c.get('/api/state',headers=learners[-1]).json()['ranking']==ranks[-1]
    assert c.get(f'/api/admin/student/{pid}',headers=teacher).json()['ranking']==ranks[-1]
    other=c.post('/api/rooms',json={'name':'별도 교실','password':'other123'}).json()
    outsider=c.post('/api/join',json={'code':other['code'],'name':'외부','pin':'1234'}).json()
    assert c.get('/api/state',headers={'Authorization':'Bearer '+outsider['token']}).json()['ranking']['total']==1
    student=c.get('/api/state',headers=learner).json()
    assert 'participants' not in student and student['ranking']==ranks[0]
    assert c.get(f'/api/admin/student/{pid}',headers=learner).status_code==403
    server.init()
    assert c.get('/api/state',headers=learner).json()['ranking']==ranks[0]


def test_rank_includes_unpaid_bond_interest_and_does_not_double_count_payout(classroom):
    c,teacher,learner=classroom
    s=c.get('/api/state',headers=learner).json();rid=s['room']['id'];pid=s['player']['id']
    token=c.post('/api/join',json={'code':s['room']['code'],'name':'비교 학생','pin':'1234'}).json()['token']
    idle={'Authorization':'Bearer '+token}
    assert c.post('/api/orders',headers=learner,json={'asset':'GOV','side':'buy','qty':1,'reason':'국채 이자 확인'}).status_code==200
    assert c.get('/api/state',headers=learner).json()['ranking']['rank']==2
    assert c.post('/api/admin/close',headers=teacher).status_code==200
    earned=c.get('/api/state',headers=learner).json()
    assert earned['bond_income']['unpaid']==50 and earned['ranking']['rank']==1
    # The same accrued amount changing from a receivable to cash cannot alter rank.
    with server.conn() as db:bond_income.pay(db,rid,3,server.ASSETS)
    paid=c.get('/api/state',headers=learner).json()
    assert paid['player']['net']==earned['player']['net']
    assert paid['ranking']==earned['ranking']
    assert c.get('/api/state',headers=idle).json()['ranking']['rank']==2
