"""Deposit contract compatibility and the real timing of teacher-added news."""
import pytest
import server
from test_classroom_flow import classroom, advance


@pytest.mark.parametrize('principal',(0,1,999,1000,9999,10500,15000,-10000))
def test_deposit_requires_clear_ten_thousand_won_units_without_changing_cash(classroom,principal):
    c,teacher,learner=classroom
    before=c.get('/api/state',headers=learner).json()
    result=c.post('/api/deposits',headers=learner,json={'principal':principal,'term':6})
    assert result.status_code==400 and '10,000원 단위' in result.json()['detail']
    after=c.get('/api/state',headers=learner).json()
    assert before==after


@pytest.mark.parametrize('term,rate,paid',((6,.02,10200),(12,.045,10450),(18,.07,10700),(24,.1,11000)))
def test_new_term_rates_and_actual_maturity_payout(classroom,term,rate,paid):
    c,teacher,learner=classroom
    assert c.post('/api/deposits',headers=learner,json={'principal':10000,'term':term}).status_code==200
    opened=c.get('/api/state',headers=learner).json()
    assert opened['deposits'][0]['rate']==rate
    assert opened['deposits'][0]['maturity_paid']==paid
    assert opened['deposits'][0]['early_paid']==10000
    for day in range(1,term):assert advance(c,teacher,day).status_code==200
    state=c.get('/api/state',headers=learner).json()
    assert state['deposits'][0]['status']=='matured'
    assert state['deposits'][0]['paid']==paid
    assert state['player']['cash']==90000+paid


@pytest.mark.parametrize('term,elapsed,interest',((24,0,0),(24,12,250),(12,6,112)))
def test_early_close_quote_and_payout_match_original_rule_including_rounding(classroom,term,elapsed,interest):
    c,teacher,learner=classroom
    assert c.post('/api/deposits',headers=learner,json={'principal':10000,'term':term}).status_code==200
    for day in range(1,elapsed+1):assert advance(c,teacher,day).status_code==200
    state=c.get('/api/state',headers=learner).json();deposit=state['deposits'][0]
    assert deposit['early_interest']==interest
    assert deposit['early_paid']==10000+interest
    preview=c.get('/api/admin/student/'+str(state['player']['id']),headers=teacher).json()
    assert preview['deposits'][0]['early_paid']==deposit['early_paid']
    result=c.post(f'/api/deposits/{deposit["id"]}/close',headers=learner)
    assert result.json()['paid']==deposit['early_paid']
    assert c.get('/api/state',headers=learner).json()['player']['cash']==100000+interest


def test_legacy_small_contract_keeps_original_rate_after_restart_and_can_mature(classroom):
    c,teacher,learner=classroom
    assert c.post('/api/deposits',headers=learner,json={'principal':10000,'term':6}).status_code==200
    state=c.get('/api/state',headers=learner).json();deposit=state['deposits'][0]
    with server.conn() as db:
        db.execute('UPDATE deposits SET principal=1000,rate=.025 WHERE id=?',(deposit['id'],))
        db.execute('UPDATE players SET cash=cash+9000 WHERE id=?',(state['player']['id'],))
    server.init()
    for day in range(1,6):assert advance(c,teacher,day).status_code==200
    state=c.get('/api/state',headers=learner).json()
    assert state['deposits'][0]['rate']==.025
    assert state['deposits'][0]['paid']==1025 and state['player']['cash']==100025


def test_period_rates_reward_duration_without_short_rollover_advantage():
    rates=server.DEPOSIT_RATES
    annual=[rate*24/term for term,rate in rates.items()]
    assert annual==sorted(annual) and len(set(annual))==4 and rates[24]==.1
    assert (1+rates[6])**4<1.1 and (1+rates[12])**2<1.1


def test_manual_news_publishes_today_then_prices_once_tomorrow(classroom):
    c,teacher,learner=classroom
    before=c.get('/api/state',headers=learner).json()
    payload={'title':'교사의 수업 보충 기사','body':'읽고 판단할 시간을 준 뒤 다음 날 진행합니다.','sector':'HBEL','impact':1.25}
    assert c.post('/api/admin/news',headers=teacher,json=payload).status_code==200
    public=c.get('/api/state',headers=learner).json()
    article=next(n for n in public['news'] if n['title']==payload['title'])
    assert article['day']==1 and article['event_id'] is None and article['metrics']=={}
    assert public['assets']==before['assets'] and public['reports']==before['reports']
    assert advance(c,teacher,1).status_code==200
    tomorrow=c.get('/api/state',headers=learner).json()
    price=next(a for a in tomorrow['assets'] if a['id']=='HBEL')
    assert article['id'] in price['price_context']['news_ids']
    with server.conn() as db:
        saved=db.execute('SELECT * FROM news WHERE id=?',(article['id'],)).fetchone()
        assert server.news_contribution(saved,2)==1.25
        assert server.news_contribution(saved,3)==0
    assert c.post('/api/admin/close',headers=teacher).status_code==200
    # Existing behavior is documented rather than silently changing publication rules.
    assert c.post('/api/admin/news',headers=teacher,json={**payload,'title':'마감 후 보충'}).status_code==200
    closed=c.get('/api/state',headers=learner).json()
    assert next(n for n in closed['news'] if n['title']=='마감 후 보충')['day']==2
    assert closed['assets']==tomorrow['assets']


def test_teacher_return_metric_excludes_cash_adjustment(classroom):
    c,teacher,learner=classroom
    pid=c.get('/api/state',headers=learner).json()['player']['id']
    assert c.post('/api/admin/cash',headers=teacher,json={'player_id':pid,'amount':20000,'reason':'수업 상점 지급'}).status_code==200
    p=c.get('/api/state',headers=teacher).json()['participants'][0]
    assert p['net']==120000 and p['profit']==0
