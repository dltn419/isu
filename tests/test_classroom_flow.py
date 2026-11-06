"""Teacher day transitions and one connected record for each student decision."""
from concurrent.futures import ThreadPoolExecutor

from fastapi.testclient import TestClient
import pytest
import server


@pytest.fixture
def classroom(tmp_path, monkeypatch):
    monkeypatch.setattr(server, 'DB', tmp_path / 'flow.db')
    server.init()
    client = TestClient(server.app)
    room = client.post('/api/rooms', json={'name': '흐름 확인 교실', 'password': 'lesson123'}).json()
    teacher = {'Authorization': 'Bearer ' + room['token']}
    student = client.post('/api/join', json={'code': room['code'], 'name': '학생', 'pin': '1234'}).json()
    learner = {'Authorization': 'Bearer ' + student['token']}
    return client, teacher, learner


def advance(client, teacher, day, phase='trading'):
    return client.post('/api/admin/advance', headers=teacher,
                       json={'expected_day': day, 'expected_phase': phase})


def test_one_action_advance_pause_and_stale_requests(classroom):
    c, teacher, learner = classroom
    assert advance(c, learner, 1).status_code == 403
    assert c.post('/api/day/complete', headers=learner).status_code == 200
    assert advance(c, teacher, 1).json() == {'ok': True, 'day': 2, 'phase': 'trading'}
    assert advance(c, teacher, 1).status_code == 409
    state = c.get('/api/state', headers=learner).json()
    assert state['room']['day'] == 2
    assert state['player']['day_ready'] is False
    assert c.post('/api/admin/close', headers=teacher).status_code == 200
    assert advance(c, teacher, 2).status_code == 409
    assert advance(c, teacher, 2, 'closed').json()['day'] == 3
    assert advance(c, teacher, 2, 'closed').status_code == 409


def test_concurrent_advance_cannot_skip_a_day(classroom):
    c, teacher, learner = classroom
    with ThreadPoolExecutor(max_workers=2) as pool:
        statuses = sorted(pool.map(lambda _: advance(c, teacher, 1).status_code, range(2)))
    assert statuses == [200, 409]
    assert c.get('/api/state', headers=learner).json()['room']['day'] == 2


def test_advance_failure_rolls_back_close_and_prices(classroom, monkeypatch):
    c, teacher, learner = classroom
    before = c.get('/api/state', headers=learner).json()

    def fail(*args):
        raise RuntimeError('simulated price failure')

    monkeypatch.setattr(server, 'generate_prices', fail)
    with pytest.raises(RuntimeError, match='simulated price failure'):
        advance(c, teacher, 1)
    after = c.get('/api/state', headers=learner).json()
    assert before == after


def test_full_year_advance_keeps_reports_maturities_and_eight_bond_payments(classroom):
    c, teacher, learner = classroom
    assert c.post('/api/deposits', headers=learner, json={'term': 24, 'principal': 10000}).status_code == 200
    assert c.post('/api/orders', headers=learner, json={
        'asset': 'GOV', 'side': 'buy', 'qty': 1, 'reason': '3일 간격 이자 확인'}).status_code == 200
    for day in range(1, 24):
        assert advance(c, teacher, day).status_code == 200
        state = c.get('/api/state', headers=learner).json()
        assert len(state['reports']) == 20 * (1 + (day + 1) // 6)
    assert state['deposits'][0]['status'] == 'matured'
    assert state['deposits'][0]['paid'] == 11000
    cash_before = state['player']['cash']
    assert advance(c, teacher, 24).json()['phase'] == 'finished'
    assert advance(c, teacher, 24).status_code == 409
    final = c.get('/api/state', headers=learner).json()
    assert final['room']['phase'] == 'finished'
    assert final['player']['cash'] == cash_before + 125
    payments = [x for x in final['ledger'] if x['note'].startswith('채권 이자') ]
    assert sorted(x['day'] for x in payments) == list(range(3,25,3))
    assert sum(x['amount'] for x in payments) == 1000
    assert final['bond_income']['paid'] == 1000
    assert final['bond_income']['unpaid'] == 0


def test_successful_activity_resumes_choice_and_failed_activity_keeps_it(classroom):
    c, teacher, learner = classroom
    assert c.post('/api/day/complete', headers=learner).status_code == 200
    bad = c.post('/api/orders', headers=learner, json={
        'asset': 'HBEL', 'side': 'buy', 'qty': 100, 'reason': '현금 부족 확인'})
    assert bad.status_code == 400
    assert c.get('/api/state', headers=learner).json()['player']['day_ready'] is True
    assert c.post('/api/deposits', headers=learner, json={'term': 6, 'principal': 10000}).json()['selection_resumed'] is True
    assert c.get('/api/state', headers=teacher).json()['all_ready'] is False
    state = c.get('/api/state', headers=learner).json()
    did = state['deposits'][0]['id']
    c.post('/api/day/complete', headers=learner)
    assert c.post(f'/api/deposits/{did}/close', headers=learner).json()['selection_resumed'] is True
    assert c.get('/api/state', headers=learner).json()['player']['day_ready'] is False


def test_trade_reason_becomes_one_record_with_original_evidence_and_reflection(classroom):
    c, teacher, learner = classroom
    news = c.get('/api/state', headers=learner).json()['news'][0]['id']
    result = c.post('/api/orders', headers=learner, json={
        'asset': 'HBEL', 'side': 'buy', 'qty': 1,
        'reason': '계약 이후 이익을 확인하겠다', 'evidence_ids': [news]}).json()
    state = c.get('/api/state', headers=learner).json()
    assert len(state['notes']) == 1
    note = state['notes'][0]
    assert note['id'] == result['note_id']
    assert note['order_id'] == result['order_id']
    assert note['thesis'] == state['orders'][0]['reason']
    assert note['evidence_ids'] == [news]
    for _ in range(2):
        assert c.post(f'/api/orders/{result["order_id"]}/note', headers=learner).json()['id'] == note['id']
    assert c.patch(f'/api/notes/{note["id"]}', headers=learner, json={
        'reflection': '매출 외에 준비 비용도 확인해야겠다', 'risk': '원재료 가격 상승',
        'horizon': '후속 뉴스가 나올 때'}).status_code == 200
    saved = c.get('/api/state', headers=learner).json()['notes']
    assert len(saved) == 1
    assert saved[0]['thesis'] == note['thesis']
    assert saved[0]['risk'] == '원재료 가격 상승'
    server.init()
    assert c.get('/api/state', headers=learner).json()['notes'] == saved


def test_legacy_trade_can_be_reflected_on_without_duplicate_or_cross_account_access(classroom):
    c, teacher, learner = classroom
    trade = c.post('/api/orders', headers=learner, json={
        'asset': 'HBEL', 'side': 'buy', 'qty': 1, 'reason': '기존 거래 기록'}).json()
    with server.conn() as db:
        db.execute('DELETE FROM investment_notes WHERE order_id=?', (trade['order_id'],))
    assert advance(c, teacher, 1).status_code == 200
    note = c.post(f'/api/orders/{trade["order_id"]}/note', headers=learner).json()
    saved = c.get('/api/state', headers=learner).json()['notes'][0]
    assert saved['day'] == 1
    assert saved['entry_price'] == 10000
    assert saved['id'] == note['id']
    assert c.post(f'/api/orders/{trade["order_id"]}/note', headers=teacher).status_code == 403
    outsider = c.post('/api/rooms', json={'name': '별도 교실', 'password': 'different123'}).json()
    other = c.post('/api/join', json={'code': outsider['code'], 'name': '다른 학생', 'pin': '1234'}).json()
    auth = {'Authorization': 'Bearer ' + other['token']}
    assert c.post(f'/api/orders/{trade["order_id"]}/note', headers=auth).status_code == 404
    assert c.patch(f'/api/notes/{saved["id"]}', headers=auth,
                   json={'reflection': '다른 학생 기록은 수정 불가'}).status_code == 404


@pytest.mark.parametrize('asset', ['HBEL', 'MKT', 'GOV', 'GOLD'])
def test_fee_is_paid_on_both_sides_and_reconciles_cash_and_records(classroom, asset):
    c, teacher, learner = classroom
    first = c.get('/api/state', headers=learner).json()
    price = next(a['price'] for a in first['assets'] if a['id'] == asset)
    fee = server.trading_fee(price * 2)
    order = {'asset': asset, 'side': 'buy', 'qty': 2, 'reason': '공개 자료로 매수 판단'}
    bought = c.post('/api/orders', headers=learner, json=order).json()
    assert bought['fee'] == fee
    assert bought['settlement'] == price * 2 + fee
    state = c.get('/api/state', headers=learner).json()
    assert state['player']['cash'] == first['player']['cash'] - bought['settlement']
    assert state['player']['net'] == first['player']['net'] - fee
    assert state['holdings'][0]['cost'] == bought['settlement']
    sold = c.post('/api/orders', headers=learner, json={**order, 'side': 'sell'}).json()
    assert sold['fee'] == fee
    assert sold['settlement'] == price * 2 - fee
    final = c.get('/api/state', headers=learner).json()
    assert final['holdings'] == []
    assert final['player']['cash'] == first['player']['cash'] - fee * 2
    assert final['player']['fees_paid'] == fee * 2
    assert all(o['fee'] == fee for o in final['orders'])
    assert sum(x['amount'] for x in final['ledger']) == -fee * 2
    assert len([x for x in final['ledger'] if x['kind'] == 'fee']) == 2


def test_fee_rounding_exact_cash_rejection_and_stale_quote(classroom):
    c, teacher, learner = classroom
    assert [server.trading_fee(v) for v in [1, 1000, 10000, 20000, 100000]] == [1, 1, 2, 3, 15]
    before = c.get('/api/state', headers=learner).json()
    order = {'asset': 'HBEL', 'side': 'buy', 'qty': 10, 'reason': '수수료 포함 한도 확인'}
    assert c.post('/api/orders', headers=learner, json=order).status_code == 400
    assert before == c.get('/api/state', headers=learner).json()
    assert advance(c, teacher, 1).status_code == 200
    current = c.get('/api/state', headers=learner).json()
    stale = c.post('/api/orders', headers=learner, json={
        **order, 'qty': 1, 'expected_day': 1, 'expected_price': 10000})
    assert stale.status_code == 409
    assert current == c.get('/api/state', headers=learner).json()
