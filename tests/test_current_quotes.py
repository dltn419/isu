"""Orders use the executable quote; weighted cost is independent of valuation."""
import pytest

import server
from test_classroom_flow import classroom


def test_execution_uses_current_quote_not_chart_open_and_updates_weighted_average(classroom):
    c, teacher, learner = classroom
    order = {'asset':'HBEL','side':'buy','qty':2,'reason':'첫 매수 근거',
             'expected_day':1,'expected_price':10000}
    first = c.post('/api/orders',headers=learner,json=order).json()
    assert first['price'] == 10000
    assert first['fee'] == 3
    assert c.post('/api/admin/advance',headers=teacher,
                  json={'expected_day':1,'expected_phase':'trading'}).status_code == 200
    with server.conn() as db:
        db.execute('UPDATE prices SET price=12000,open_price=10000,high_price=12500,low_price=9900 '
                   "WHERE asset='HBEL' AND day=2")
    quote = c.get('/api/state',headers=learner).json()
    assert next(a['price'] for a in quote['assets'] if a['id']=='HBEL') == 12000
    history = c.get('/api/history/HBEL',headers=learner).json()
    assert history[-1]['open'] == 10000
    assert history[-1]['close'] == 12000
    assert c.post('/api/orders',headers=learner,json={
        **order,'qty':1,'expected_day':2,'expected_price':10000}).status_code == 409
    assert c.get('/api/state',headers=learner).json() == quote
    second = c.post('/api/orders',headers=learner,json={
        **order,'qty':1,'expected_day':2,'expected_price':12000}).json()
    assert second['price'] == 12000
    assert second['settlement'] == 12002
    bought = c.get('/api/state',headers=learner).json()
    holding = bought['holdings'][0]
    assert holding['qty'] == 3
    assert holding['cost'] == 20003 + 12002
    assert holding['average_cost'] == pytest.approx(32005/3)
    assert bought['player']['cash'] == 100000 - 32005
    sold = c.post('/api/orders',headers=learner,json={
        **order,'side':'sell','qty':1,'expected_day':2,'expected_price':12000}).json()
    assert sold['price'] == 12000
    assert sold['settlement'] == 11998
    after = c.get('/api/state',headers=learner).json()
    assert after['player']['cash'] == bought['player']['cash'] + 11998
    assert after['holdings'][0]['qty'] == 2
    assert after['holdings'][0]['cost'] == round(32005*2/3)
    assert after['holdings'][0]['average_cost'] == pytest.approx(round(32005*2/3)/2)
    pid = c.get('/api/state',headers=teacher).json()['participants'][0]['id']
    preview = c.get(f'/api/admin/student/{pid}',headers=teacher).json()
    assert preview['holdings'] == after['holdings']
    assert c.post('/api/admin/advance',headers=teacher,
                  json={'expected_day':2,'expected_phase':'trading'}).status_code == 200
    with server.conn() as db:
        db.execute("UPDATE prices SET price=9000 WHERE asset='HBEL' AND day=3")
    moved = c.get('/api/state',headers=learner).json()
    assert moved['holdings'][0]['average_cost'] == after['holdings'][0]['average_cost']
    assert moved['player']['net'] != after['player']['net']


def test_teacher_can_read_quotes_and_history_without_a_student_account(classroom):
    c, teacher, learner = classroom
    state = c.get('/api/state',headers=teacher).json()
    assert 'player' not in state
    assert len(state['assets']) == 32
    assert c.get('/api/history/HBEL',headers=teacher).status_code == 200
    assert c.get('/api/history/GOV',headers=teacher).status_code == 200
    assert c.post('/api/orders',headers=teacher,json={
        'asset':'HBEL','side':'buy','qty':1,'reason':'교사의 시장 보기'}).status_code == 403
