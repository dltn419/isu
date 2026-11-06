"""Cash conservation, complete investment episodes and ETF-aware style awards."""
import json
from concurrent.futures import ThreadPoolExecutor

import pytest
import server
import game_finale
import etf_portfolio
from test_classroom_flow import classroom, advance


def state(c, who):
    return c.get('/api/state', headers=who).json()


def trade(c, who, aid, side='buy', qty=1):
    result = c.post('/api/orders', headers=who, json={
        'asset': aid, 'side': side, 'qty': qty, 'reason': '가격과 보유 비중을 확인했어요'})
    assert result.status_code == 200, result.text
    return result.json()


def quote(rid, aid, value):
    with server.conn() as db:
        db.execute('UPDATE prices SET price=? WHERE room_id=? AND day=1 AND asset=?', (value, rid, aid))


def finish(c, teacher):
    day = state(c, teacher)['room']['day']
    for d in range(day, 25):
        result = advance(c, teacher, d)
        assert result.status_code == 200, result.text


def flat_prices(db, rid, day, *args):
    db.execute('''INSERT INTO prices(room_id,day,asset,price,change,open_price,high_price,low_price)
                  SELECT room_id,?,asset,price,0,price,price,price FROM prices WHERE room_id=? AND day=?''',
               (day, rid, day - 1))


def test_public_etf_weights_match_the_price_index_and_distinguish_leverage(classroom):
    c, teacher, learner = classroom
    assets = {a['id']: a for a in state(c, learner)['assets']}
    for aid in ('MKT', 'TECH', 'AIR', 'FOOD', 'HEAL', 'FUTR', 'LEV2', 'INV2'):
        composition = assets[aid]['etf_composition']
        assert sum(h['weight'] for h in composition['holdings']) == pytest.approx(1)
        assert sum(h['weight'] for h in composition['sectors']) == pytest.approx(1)
        assert composition['holdings'] == next(a for a in state(c, teacher)['assets'] if a['id'] == aid)['etf_composition']['holdings']
    assert assets['MKT']['etf_composition']['company_count'] == 20
    assert len(assets['MKT']['etf_composition']['sectors']) == 5
    assert [h['weight'] for h in assets['TECH']['etf_composition']['holdings']] == [.35, .35, .15, .15]
    assert assets['LEV2']['etf_composition']['multiplier'] == 2
    assert assets['INV2']['etf_composition']['multiplier'] == -2
    returns = {a['id']: (100, 10 if a['id'] == 'HBEL' else 0) for a in server.ASSETS}
    assert etf_portfolio.index_return(returns, server.ASSETS) == pytest.approx(.7)
    assert etf_portfolio.index_return(returns, server.ASSETS, '기술') == pytest.approx(3.5)
    assert etf_portfolio.index_return(returns, server.ASSETS, '항공') == 0


def test_final_cash_includes_last_coupon_fees_and_deposit_and_runs_once(classroom):
    c, teacher, learner = classroom
    assert c.post('/api/deposits', headers=learner, json={'term': 24, 'principal': 10000}).status_code == 200
    for aid, qty in [('MKT', 4), ('GOV', 2), ('GOLD', 1)]:
        trade(c, learner, aid, qty=qty)
    for day in range(1, 24):
        assert advance(c, teacher, day).status_code == 200
    before = state(c, learner)
    prices = {a['id']: a['price'] for a in before['assets']}
    sales = [h['qty'] * prices[h['asset']] for h in before['holdings']]
    final_fees = sum(server.trading_fee(v) for v in sales)
    expected = before['player']['cash'] + sum(sales) - final_fees + before['bond_income']['unpaid'] + 100
    with ThreadPoolExecutor(max_workers=2) as pool:
        statuses = sorted(pool.map(lambda _: advance(c, teacher, 24).status_code, range(2)))
    assert statuses == [200, 409]
    after = state(c, learner)
    assert after['holdings'] == []
    assert after['player']['cash'] == after['player']['net'] == expected
    assert after['bond_income']['paid'] == 2400
    assert after['bond_income']['unpaid'] == 0
    assert after['deposits'][0]['status'] == 'matured'
    assert after['deposits'][0]['paid'] == 11000
    assert len([o for o in after['orders'] if o['is_final_liquidation']]) == 3
    assert after['learning']['note_count'] == before['learning']['note_count']
    report = after['finale']
    assert report['settled'] is True
    assert report['liquidation_count'] == 3
    assert report['liquidation_fees'] == final_fees
    assert report['standings'][0]['net'] == expected
    assert report == state(c, teacher)['finale']
    with server.conn() as db:
        r = db.execute('SELECT * FROM rooms').fetchone()
        players = {p['id']: dict(p) for p in db.execute('SELECT * FROM players')}
        cards, _ = game_finale._analyse(db, r, server.ASSETS, players)
    bond = next(card for card in cards if card['asset'] == 'GOV')
    assert bond['interest'] == 2400
    assert bond['profit'] == bond['proceeds'] + 2400 - bond['invested']
    turnover = next(a for a in report['awards'] if a['id'] == 'turnover')
    assert turnover['winners'][0]['detail'] == '자발적 매수·매도 3건'
    server.init()
    assert state(c, learner)['finale'] == report
    assert state(c, learner)['player']['cash'] == expected
    automatic = next(o for o in after['orders'] if o['is_final_liquidation'])
    assert c.post(f'/api/orders/{automatic["id"]}/note', headers=learner).status_code == 404


def test_bond_episode_interest_rounding_matches_actual_cumulative_payments(classroom):
    c, teacher, learner = classroom
    assert advance(c, teacher, 1).status_code == 200
    assert advance(c, teacher, 2).status_code == 200
    trade(c, learner, 'CORP')
    assert advance(c, teacher, 3).status_code == 200
    trade(c, learner, 'CORP', 'sell')
    trade(c, learner, 'CORP')
    trade(c, learner, 'CORP', 'sell')
    assert advance(c, teacher, 4).status_code == 200
    trade(c, learner, 'CORP')
    assert advance(c, teacher, 5).status_code == 200
    trade(c, learner, 'CORP', 'sell')
    assert c.post('/api/admin/close', headers=teacher).status_code == 200
    with server.conn() as db:
        room = db.execute('SELECT * FROM rooms').fetchone()
        players = {p['id']: dict(p) for p in db.execute('SELECT * FROM players')}
        cards, _ = game_finale._analyse(db, room, server.ASSETS, players)
    assert [card['interest'] for card in cards] == [58, 0, 59]
    assert sum(card['interest'] for card in cards) == state(c, learner)['bond_income']['paid'] == 117


def test_retrospective_reads_all_fills_beyond_recent_order_limit(classroom, monkeypatch):
    c, teacher, learner = classroom
    monkeypatch.setattr(server, 'generate_prices', flat_prices)
    rid = state(c, learner)['room']['id']
    trade(c, learner, 'HBEL')
    quote(rid, 'HBEL', 15000)
    trade(c, learner, 'HBEL', 'sell')
    for _ in range(36):
        trade(c, learner, 'MKT')
        trade(c, learner, 'MKT', 'sell')
    assert len(state(c, learner)['orders']) == 70
    finish(c, teacher)
    report = state(c, learner)['finale']
    assert report['highlights']['gains'][0]['asset'] == 'HBEL'
    assert report['highlights']['gains'][0]['profit'] == 4996
    assert report['liquidation_count'] == 0
    assert next(a for a in report['awards'] if a['id'] == 'turnover')['winners'][0]['detail'] == '자발적 매수·매도 74건'


def test_split_purchases_and_partial_sales_form_one_fee_inclusive_card(classroom):
    c, teacher, learner = classroom
    rid = state(c, teacher)['room']['id']
    trade(c, learner, 'HBEL', qty=3)
    quote(rid, 'HBEL', 11000)
    trade(c, learner, 'HBEL', qty=2)
    quote(rid, 'HBEL', 12000)
    trade(c, learner, 'HBEL', 'sell', 2)
    quote(rid, 'HBEL', 13000)
    trade(c, learner, 'HBEL')
    quote(rid, 'HBEL', 8000)
    trade(c, learner, 'HBEL', 'sell', 4)
    trade(c, learner, 'MKT', qty=3)
    quote(rid, 'MKT', 6000)
    trade(c, learner, 'MKT', 'sell', 3)
    with server.conn() as db:
        room = db.execute('SELECT * FROM rooms WHERE id=?', (rid,)).fetchone()
        report = game_finale.build_report(db, room, server.ASSETS)
    loss = report['highlights']['reviews'][0]
    assert loss['quantity'] == 6 and loss['peak_quantity'] == 5
    assert loss['invested'] == 65010
    assert loss['proceeds'] == 55991
    assert loss['profit'] == -9019 and loss['fees'] == 19
    assert loss['holding_days'] == 1
    assert len(report['highlights']['reviews']) == 1
    assert report['highlights']['gains'][0]['profit'] == 2995
    # Later teacher cash grants affect cash but never the investment-return ranking.
    with server.conn() as db:
        pid = state(c, learner)['player']['id']
        db.execute('UPDATE players SET cash=cash+5000 WHERE id=?', (pid,))
        db.execute("INSERT INTO ledgers(room_id,player_id,day,kind,amount,note) VALUES(?,?,1,'teacher',5000,'수업 지급')", (rid, pid))
    assert state(c, learner)['player']['profit'] == -9019 + 2995


def test_etf_overlap_does_not_create_extra_diversity_and_tiny_positions_cannot_win_longest(classroom, monkeypatch):
    c, teacher, learner = classroom
    monkeypatch.setattr(server, 'generate_prices', flat_prices)
    initial = state(c, teacher)
    code, rid = initial['room']['code'], initial['room']['id']

    def student(name):
        joined = c.post('/api/join', json={'code': code, 'name': name, 'pin': '1234'}).json()
        return {'Authorization': 'Bearer ' + joined['token']}

    mixed, tech, tiny = student('시장과 업종 혼합'), student('기술에 집중'), student('작은 한 주')
    # 80,000 won each; the mixed portfolio has exactly the same underlying weights.
    trade(c, learner, 'MKT', qty=16)
    trade(c, mixed, 'MKT', qty=6)
    for aid in ('TECH', 'AIR', 'FOOD', 'HEAL', 'FUTR'):
        trade(c, mixed, aid, qty=2)
    trade(c, tech, 'TECH', qty=16)
    trade(c, tiny, 'SCNT')
    finish(c, teacher)
    f = state(c, teacher)['finale']
    concentrated = next(a for a in f['awards'] if a['id'] == 'concentration')
    assert [w['name'] for w in concentrated['winners']] == ['기술에 집중']
    long = next(a for a in f['awards'] if a['id'] == 'longest')
    assert '작은 한 주' not in [w['name'] for w in long['winners']]
    assert all(w['value'] == 24 for w in long['winners'])
    diversified = next(a for a in f['awards'] if a['id'] == 'diversity')
    assert all(w['name'] in ('학생', '시장과 업종 혼합') for w in diversified['winners'])
    with server.conn() as db:
        room = db.execute('SELECT * FROM rooms WHERE id=?', (rid,)).fetchone()
        players = {p['id']: dict(p) for p in db.execute('SELECT * FROM players WHERE room_id=?', (rid,))}
        _, metrics = game_finale._analyse(db, room, server.ASSETS, players)
    by_name = {players[pid]['name']: m for pid, m in metrics.items()}
    assert abs(by_name['학생']['diversity'] - by_name['시장과 업종 혼합']['diversity']) < .01
    assert by_name['작은 한 주']['invested_share'] < .1


def test_settlement_failure_rolls_back_cash_coupons_orders_and_phase(classroom, monkeypatch):
    c, teacher, learner = classroom
    trade(c, learner, 'GOV')
    for day in range(1, 24):
        assert advance(c, teacher, day).status_code == 200
    before = state(c, learner)

    def fail(*args, **kwargs):
        raise RuntimeError('report failed after liquidation')

    with monkeypatch.context() as patch:
        patch.setattr(game_finale, 'build_report', fail)
        with pytest.raises(RuntimeError, match='report failed'):
            advance(c, teacher, 24)
    after = state(c, learner)
    for key in ('room', 'player', 'holdings', 'orders', 'bond_income', 'finale'):
        assert after[key] == before[key]
    assert advance(c, teacher, 24).status_code == 200


def test_legacy_finished_game_is_readonly_and_new_game_archives_and_clears_report(classroom):
    c, teacher, learner = classroom
    trade(c, learner, 'MKT', qty=4)
    before = state(c, learner)
    rid = before['room']['id']
    with server.conn() as db:
        db.execute("UPDATE rooms SET phase='finished' WHERE id=?", (rid,))
    server.init()
    legacy = state(c, learner)
    assert legacy['finale']['settled'] is False
    assert legacy['player']['cash'] == before['player']['cash']
    assert legacy['holdings'] == before['holdings']
    # Finish a normal game, then verify that reset backs up the report too.
    with server.conn() as db:
        db.execute("UPDATE rooms SET phase='trading' WHERE id=?", (rid,))
    finish(c, teacher)
    final = state(c, teacher)
    with server.conn() as db:
        room = db.execute('SELECT * FROM rooms WHERE id=?', (rid,)).fetchone()
        result = server.game_reset.reset_room(db, room, server.ASSETS, server.now())
        backup = json.loads(db.execute('SELECT snapshot FROM game_reset_backups WHERE id=?', (result['backup_id'],)).fetchone()[0])
        assert len(backup['tables']['final_settlements']) == 1
        assert not db.execute('SELECT 1 FROM final_settlements WHERE room_id=?', (rid,)).fetchone()
    fresh = state(c, learner)
    assert fresh['room']['day'] == 1 and fresh['finale'] is None
    assert fresh['player']['cash'] == fresh['room']['start_cash']
    other = c.post('/api/rooms', json={'name': '다른 게임', 'password': 'test1234'}).json()
    assert state(c, {'Authorization': 'Bearer ' + other['token']})['finale'] is None
