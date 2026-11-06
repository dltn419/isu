"""Periodic coupons follow closing share-days, including sells and legacy games."""
import pytest
import server
from test_classroom_flow import classroom, advance


def trade(c, learner, side='buy', qty=1, asset='GOV'):
    r = c.post('/api/orders', headers=learner, json={
        'asset': asset, 'side': side, 'qty': qty, 'reason': '보유 기간과 이자 확인'})
    assert r.status_code == 200, r.text
    return r.json()


def state(c, learner):
    return c.get('/api/state', headers=learner).json()


@pytest.mark.parametrize('asset,coupon', [('GOV',150), ('CORP',175), ('JUNK',200)])
def test_three_day_coupon_and_no_duplicate_or_cost_change(classroom, asset, coupon):
    c, teacher, learner = classroom
    trade(c, learner, asset=asset)
    original_cost = state(c, learner)['holdings'][0]['average_cost']
    for day in (1,2):
        assert advance(c, teacher, day).status_code == 200
        assert state(c, learner)['bond_income']['paid'] == 0
    before = state(c, learner)['player']['cash']
    assert c.post('/api/admin/close', headers=teacher).status_code == 200
    after = state(c, learner)
    assert after['player']['cash'] == before + coupon
    assert after['bond_income'] == {'unpaid':0, 'paid':coupon,
                                   'items':[{'asset':asset, 'unpaid':0, 'paid':coupon}]}
    assert after['bond_policy']['next_payment_day'] == 6
    assert after['holdings'][0]['average_cost'] == original_cost
    assert c.post('/api/admin/close', headers=teacher).status_code == 400
    assert state(c, learner) == after


def test_variable_quantities_and_earned_interest_survives_complete_sale(classroom):
    c, teacher, learner = classroom
    trade(c, learner, qty=2)
    assert advance(c, teacher, 1).status_code == 200
    assert state(c, learner)['bond_income']['unpaid'] == 100
    trade(c, learner)
    assert advance(c, teacher, 2).status_code == 200
    assert state(c, learner)['bond_income']['unpaid'] == 250
    trade(c, learner, 'sell', 2)
    assert advance(c, teacher, 3).status_code == 200
    assert state(c, learner)['bond_income']['paid'] == 300  # 2+3+1 share-days
    assert advance(c, teacher, 4).status_code == 200
    trade(c, learner, 'sell')
    before = state(c, learner)
    assert before['holdings'] == []
    assert before['bond_income']['unpaid'] == 50
    assert before['player']['net'] == before['player']['cash'] + 50
    assert advance(c, teacher, 5).status_code == 200
    assert c.post('/api/admin/close', headers=teacher).status_code == 200
    after = state(c, learner)
    assert after['player']['cash'] == before['player']['cash'] + 50
    assert after['player']['net'] == before['player']['net']
    assert after['bond_income']['unpaid'] == 0
    assert after['bond_income']['paid'] == 350
    preview = c.get('/api/admin/student/'+str(after['player']['id']),headers=teacher).json()
    assert preview['bond_income'] == after['bond_income']
    assert preview['player']['net'] == after['player']['net']


def test_late_purchase_roundtrip_and_fractional_won_carry(classroom):
    c, teacher, learner = classroom
    assert advance(c, teacher, 1).status_code == 200
    assert advance(c, teacher, 2).status_code == 200
    trade(c, learner, asset='CORP')
    assert advance(c, teacher, 3).status_code == 200
    assert state(c, learner)['bond_income']['paid'] == 58
    trade(c, learner, 'sell', asset='CORP')
    trade(c, learner, asset='CORP')
    trade(c, learner, 'sell', asset='CORP')  # Day 4 ends at zero, so it earns no interest.
    assert advance(c, teacher, 4).status_code == 200
    trade(c, learner, asset='CORP')
    assert advance(c, teacher, 5).status_code == 200
    trade(c, learner, 'sell', asset='CORP')
    assert c.post('/api/admin/close', headers=teacher).status_code == 200
    after = state(c, learner)
    # Two distinct one-day holdings earn round(1400 * 2/24)=117 total, not 58+58.
    assert after['bond_income']['paid'] == 117
    assert after['bond_income']['unpaid'] == 0
    assert sorted(x['amount'] for x in after['ledger'] if x['note'].startswith('채권 이자')) == [58,59]


def test_final_day_purchase_only_earns_one_day(classroom):
    c, teacher, learner = classroom
    for day in range(1,24):
        assert advance(c, teacher, day).status_code == 200
    trade(c, learner)
    before = state(c, learner)['player']['cash']
    last_price = next(a['price'] for a in state(c, learner)['assets'] if a['id'] == 'GOV')
    assert advance(c, teacher, 24).status_code == 200
    after = state(c, learner)
    assert after['player']['cash'] == before + 50 + last_price - server.trading_fee(last_price)
    assert after['holdings'] == []
    assert after['bond_income']['paid'] == 50
    assert after['bond_policy']['next_payment_day'] is None


def test_failed_day_advance_rolls_back_interest_and_payout(classroom, monkeypatch):
    c, teacher, learner = classroom
    trade(c, learner)
    for day in (1,2):
        assert advance(c, teacher, day).status_code == 200
    before = state(c, learner)
    def fail(*args):
        raise RuntimeError('price failure after coupon')
    with monkeypatch.context() as patch:
        patch.setattr(server, 'generate_prices', fail)
        with pytest.raises(RuntimeError, match='price failure'):
            advance(c, teacher, 3)
    assert state(c, learner) == before
    assert advance(c, teacher, 3).status_code == 200
    assert state(c, learner)['bond_income']['paid'] == 150


def test_rate_change_preserves_earned_interest_and_past_cash(classroom, monkeypatch):
    c, teacher, learner = classroom
    # A running v12 game already earned three days at the original 10% rate.
    with monkeypatch.context() as patch:
        patch.setitem(server.AMAP['GOV'], 'yield', .10)
        trade(c, learner)
        for day in (1,2,3):
            assert advance(c, teacher, day).status_code == 200
    before = state(c, learner)
    assert before['bond_income']['paid'] == 125
    with server.conn() as db:
        old_units = [dict(r) for r in db.execute('SELECT * FROM bond_accruals WHERE day<=3')]
    server.init()
    assert state(c, learner)['player']['cash'] == before['player']['cash']
    for day in (4,5,6):
        assert advance(c, teacher, day).status_code == 200
    after = state(c, learner)
    assert after['bond_income']['paid'] == 125 + 150
    assert after['bond_income']['unpaid'] == 0
    with server.conn() as db:
        assert [dict(r) for r in db.execute('SELECT * FROM bond_accruals WHERE day<=3')] == old_units


def test_legacy_migration_reconstructs_closed_holdings_once_and_preserves_game(classroom):
    c, teacher, learner = classroom
    trade(c, learner, qty=2)
    assert advance(c, teacher, 1).status_code == 200
    trade(c, learner, 'sell')
    assert advance(c, teacher, 2).status_code == 200
    trade(c, learner, 'sell')
    assert advance(c, teacher, 3).status_code == 200
    trade(c, learner, qty=2)
    assert advance(c, teacher, 4).status_code == 200
    before = state(c, learner)
    assert before['bond_income']['paid'] == 150
    assert before['bond_income']['unpaid'] == 100
    # Represent an unchanged v11 game: trades exist but periodic income did not.
    with server.conn() as db:
        db.execute('DELETE FROM bond_accruals')
        db.execute('DELETE FROM bond_payments')
        db.execute("DELETE FROM ledgers WHERE note LIKE '채권 이자%'")
        db.execute('UPDATE players SET cash=cash-150')
        db.execute('UPDATE daily_values SET net=net-250,cash=cash-150 WHERE day=5')
        db.execute('UPDATE rooms SET bond_interest_version=1')
    server.init()
    migrated = state(c, learner)
    assert migrated['bond_income'] == before['bond_income']
    assert migrated['player'] == before['player']
    assert migrated['holdings'] == before['holdings']
    assert migrated['assets'] == before['assets']
    assert migrated['room']['day'] == 5
    assert migrated['room']['generation'] == before['room']['generation']
    assert migrated['room']['code'] == before['room']['code']
    server.init()
    assert state(c, learner) == migrated


def test_finished_legacy_game_keeps_annual_payment_and_reset_uses_new_model(classroom):
    c, teacher, learner = classroom
    with server.conn() as db:
        db.execute("UPDATE rooms SET day=24,phase='finished',bond_interest_version=1")
        db.execute('UPDATE players SET cash=101000')
        db.execute("INSERT INTO ledgers(room_id,player_id,day,kind,amount,note) SELECT room_id,id,24,'interest',1000,'연말 채권 이자' FROM players")
    server.init()
    after = state(c, learner)
    assert after['player']['cash'] == 101000
    assert after['bond_policy']['mode'] == 'legacy_annual'
    result = c.post('/api/admin/reset', headers=teacher, json={
        'confirmation':'초기화','expected_day':24,'expected_generation':0})
    assert result.status_code == 200
    assert state(c, learner)['bond_policy']['mode'] == 'periodic'


def test_reset_archives_and_clears_interest_without_touching_other_rooms(classroom):
    c, teacher, learner = classroom
    trade(c, learner)
    for day in range(1,5):
        assert advance(c, teacher, day).status_code == 200
    before = state(c, learner)
    assert before['bond_income']['paid'] == 150 and before['bond_income']['unpaid'] == 50
    other = c.post('/api/rooms',json={'name':'다른 교실','password':'other123'}).json()
    other_teacher = {'Authorization':'Bearer '+other['token']}
    untouched = c.get('/api/state',headers=other_teacher).json()
    assert c.post('/api/admin/reset',headers=teacher,json={
        'confirmation':'초기화','expected_day':5,'expected_generation':0}).status_code == 200
    after = state(c, learner)
    assert after['bond_income'] == {'unpaid':0,'paid':0,'items':[]}
    assert after['player']['cash'] == after['player']['net'] == 100000
    backup = c.get('/api/admin/reset-backup',headers=teacher).json()
    assert len(backup['tables']['bond_accruals']) == 4
    assert len(backup['tables']['bond_payments']) == 1
    assert c.get('/api/state',headers=other_teacher).json() == untouched
