"""Replay integrity, public-only policy input and production DB isolation."""
import copy
import json
from pathlib import Path
import subprocess
from collections import defaultdict

import pytest
import ai_spectator as spectator
import server
from test_classroom_flow import classroom


@pytest.fixture(scope='module')
def replay():
    return spectator.get_replay(0, 'neutral')


@pytest.fixture(scope='module', params=[1000, 56789, 500000, 100000000])
def funded_replay(request):
    return spectator.get_replay(0, 'neutral', request.param)


def test_starting_cash_drives_actual_game_and_deposits(funded_replay):
    cash = funded_replay['initial_cash']
    opening = funded_replay['frames'][0]['opening']
    assert all(p['cash'] == p['net'] == cash and p['profit'] == 0 for p in opening)
    assert len(funded_replay['frames']) == 24
    deposits = [e for e in funded_replay['frames'][0]['events'] if e['type'] == 'deposit']
    principal = cash // 5 // 10000 * 10000
    assert [e['amount'] for e in deposits] == ([principal] if principal else [])
    for p in funded_replay['final']:
        assert p['holdings'] == [] and p['net'] == p['cash']
        assert p['profit'] == p['net'] - cash
        assert p['return_pct'] == round(p['profit'] / cash * 100, 2)
        assert p['cash'] >= 0
    assert spectator.get_replay(0, 'neutral', cash) is funded_replay
    if cash == 500000:
        event = next(e for e in funded_replay['frames'][0]['events'] if e['type'] == 'buy' and e['bot_id'] == 'news')
        assert event['qty'] > 9


def test_real_fills_use_current_quotes_and_fees_and_finish_in_cash(replay):
    assert replay['agent_kind'] == 'rule-based' and replay['information'] == 'published-only'
    assert len(replay['frames']) == 24
    assert len(replay['bots']) == 3
    fees, trades, event_ids = defaultdict(int), defaultdict(int), []
    news = {n['id']: n for n in replay['news']}
    for day, frame in enumerate(replay['frames'], 1):
        assert frame['day'] == day
        assert len(frame['opening']) == len(frame['closing']) == 3
        cash = {p['id']: p['cash'] for p in frame['opening']}
        for e in frame['events']:
            event_ids.append(e['id'])
            assert 2 <= len(e['reason']) <= 500
            assert e['day'] == day
            assert all(news[nid]['day'] <= day for nid in e['evidence_ids'])
            if e['type'] in ('buy', 'sell'):
                assert type(e['qty']) is int and e['qty'] > 0
                assert e['price'] == frame['prices'][e['asset']]['price']
                assert e['gross'] == e['qty'] * e['price']
                assert e['fee'] == server.trading_fee(e['gross'])
                assert e['settlement'] == e['gross'] + (e['fee'] if e['type'] == 'buy' else -e['fee'])
                expected = cash[e['bot_id']] + (-e['settlement'] if e['type'] == 'buy' else e['settlement'])
                assert e['after']['cash'] == expected and expected >= 0
                fees[e['bot_id']] += e['fee']
                trades[e['bot_id']] += 1
            elif e['type'] == 'deposit':
                assert e['amount'] % 10000 == 0 and e['term'] == 24
                assert e['after']['cash'] == cash[e['bot_id']] - e['amount']
            elif e['type'] == 'settlement':
                assert day == 24 and e['automatic']
                assert sum(f['fee'] for f in e['fills']) == e['fee']
                for fill in e['fills']:
                    assert fill['fee'] == server.trading_fee(fill['qty'] * fill['price'])
                fees[e['bot_id']] += e['fee']
            cash[e['bot_id']] = e['after']['cash']
    assert event_ids == list(range(1, len(event_ids) + 1))
    assert trades['swing'] > trades['balanced']
    assert len({tuple(p['id'] for p in f['closing']) for f in replay['frames']}) == 1
    for p in replay['final']:
        assert p['holdings'] == [] and p['net'] == p['cash']
        assert p['profit'] == p['net'] - replay['initial_cash']
        assert p['fees_paid'] == fees[p['id']]
        assert p['trades'] == trades[p['id']]
    balanced = next(p for p in replay['final'] if p['id'] == 'balanced')
    assert balanced['deposits'][0]['status'] == 'matured'
    assert balanced['deposits'][0]['paid'] == 22000
    assert balanced['income'] > 2000


def test_worker_exposes_no_sessions_or_hidden_simulation_state(replay):
    forbidden = {'token', 'token_hash', 'admin_hash', 'pin_hash', 'seed', 'auth', 'memory', 'future_prices'}
    def walk(value):
        if isinstance(value, dict):
            assert forbidden.isdisjoint(value)
            for child in value.values():
                walk(child)
        elif isinstance(value, list):
            for child in value:
                walk(child)
    walk(replay)


def test_policies_only_receive_published_information(classroom):
    c, teacher, learner = classroom
    state = c.get('/api/state', headers=learner).json()
    state['seed'] = 123456
    future = copy.deepcopy(state['news'][0]);future['id'] = 999999;future['day'] = 24
    state['news'].append(future)
    state['reports'].append({'asset': 'HBEL', 'quarter': 4, 'day': 24, 'profit_growth': 900})
    state['assets'][0]['hidden_result'] = 'success'
    histories = {'HBEL': [{'day': 1, 'price': 10000}, {'day': 24, 'price': 999999}]}
    view = spectator.public_view(state, histories)
    assert 'seed' not in view and 'hidden_result' not in view['assets'][0]
    assert all(n['day'] <= 1 for n in view['news'])
    assert all(r['day'] <= 1 for r in view['reports'])
    assert [p['day'] for p in view['histories']['HBEL']] == [1]
    assert spectator.plan_actions('swing', view, {'bought': {}, 'signals': {}})[0]['type'] == 'wait'


def test_spectator_endpoint_isolated_from_real_room_and_preserves_future_run(classroom, monkeypatch):
    c, teacher, learner = classroom
    monkeypatch.setenv('HARU_DB', str(server.DB))
    def snapshot():
        with server.conn() as db:
            return {table: [tuple(r) for r in db.execute('SELECT * FROM '+table)] for table in (
                'rooms', 'players', 'holdings', 'orders', 'ledgers', 'prices', 'deposits', 'sessions')}
    before = snapshot()
    response = c.get('/api/spectator', params={'scenario': 1, 'mood': 'positive', 'start_cash': 500000})
    assert response.status_code == 200, response.text
    assert response.json()['mood'] == 'positive' and len(response.json()['frames']) == 24
    assert response.json()['initial_cash'] == 500000
    assert all(p['cash'] == 500000 for p in response.json()['frames'][0]['opening'])
    assert snapshot() == before
    assert c.get('/api/state', headers=learner).json()['room']['day'] == 1


def test_cache_does_not_spawn_a_worker_for_same_game(replay, monkeypatch):
    def unexpected(*args, **kwargs):
        pytest.fail('Cached game spawned another worker')
    monkeypatch.setattr(spectator.subprocess, 'run', unexpected)
    assert spectator.get_replay(0, 'neutral') is replay


def test_busy_worker_and_failure_are_recoverable(classroom, monkeypatch):
    c, teacher, learner = classroom
    spectator._build_lock.acquire()
    try:
        response = c.get('/api/spectator', params={'scenario': 63, 'mood': 'negative'})
        assert response.status_code == 429 and response.headers['retry-after'] == '2'
    finally:
        spectator._build_lock.release()
    def broken(*args):
        raise spectator.SpectatorFailure()
    monkeypatch.setattr(spectator, 'get_replay', broken)
    assert c.get('/api/spectator').status_code == 503


@pytest.mark.parametrize('query', ['scenario=-1', 'scenario=64', 'scenario=abc', 'mood=unknown',
                                'start_cash=999', 'start_cash=100000001', 'start_cash=abc', 'start_cash=1000.5'])
def test_invalid_scenarios_never_start_a_worker(classroom, query, monkeypatch):
    c, teacher, learner = classroom
    def unexpected(*args):
        pytest.fail('Invalid parameters reached worker')
    monkeypatch.setattr(spectator, 'get_replay', unexpected)
    assert c.get('/api/spectator?'+query).status_code == 422


def test_fee_inclusive_integer_budget_boundaries():
    assert spectator.affordable_quantity(100000, 100000, 45000, server.trading_fee) == 2
    assert spectator.affordable_quantity(90000, 90000, 45000, server.trading_fee) == 1
    assert spectator.affordable_quantity(90014, 90014, 45000, server.trading_fee) == 2


def test_timed_out_worker_releases_lock_and_removes_temporary_files(monkeypatch):
    captured = {}
    def timeout(*args, **kwargs):
        directory = Path(kwargs['env']['TMPDIR'])
        captured['directory'] = directory
        (directory/'unfinished.db').write_text('isolated temporary data')
        raise subprocess.TimeoutExpired(args[0], 45)
    monkeypatch.setattr(spectator.subprocess, 'run', timeout)
    with pytest.raises(spectator.SpectatorFailure):
        spectator.get_replay(62, 'negative')
    assert not captured['directory'].exists()
    assert not spectator._build_lock.locked()
