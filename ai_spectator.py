"""Isolated, reproducible games for a public spectator replay.

The web process only caches JSON. A separate process imports the real game with
HARU_DB set to a temporary directory before import. Agent policies receive an
explicit public-information projection; they never receive seeds or future data.
"""
from collections import OrderedDict
import json
import math
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import threading

BOT_PROFILES = [
    {'id': 'news', 'name': '하루', 'style': '뉴스 판단형', 'color': '#28664f',
     'description': '매출·이익 전망과 발표된 실적을 비교해요. 한 기업에 새로 넣는 돈은 총자산의 35% 이내로 정해요.'},
    {'id': 'balanced', 'name': '모아', 'style': '분산 투자형', 'color': '#376e9a',
     'description': '시장 ETF 50%·국채 20%·금 10%·예금 20%를 목표로 해요. 정수 수량으로 사고 분기가 지나면 비중을 점검해요.'},
    {'id': 'swing', 'name': '번개', 'style': '단기 매매형', 'color': '#a46930',
     'description': '최근 이틀의 가격 흐름을 살펴요. 3일 보유·수익 10%·손실 8% 중 조건이 먼저 닿으면 정리해요.'},
]
_cache = OrderedDict()
_cache_lock = threading.Lock()
_build_lock = threading.Lock()


class SpectatorBusy(Exception):
    pass


class SpectatorFailure(Exception):
    pass


def get_replay(scenario=0, mood='neutral'):
    """At most one bounded worker, eight cached games, no persistent room writes."""
    if type(scenario) is not int or not 0 <= scenario < 64 or mood not in ('neutral', 'positive', 'negative'):
        raise ValueError('Invalid spectator scenario')
    key = (scenario, mood)
    with _cache_lock:
        if key in _cache:
            _cache.move_to_end(key)
            return _cache[key]
    if not _build_lock.acquire(blocking=False):
        raise SpectatorBusy()
    try:
        with _cache_lock:
            if key in _cache:
                return _cache[key]
        with tempfile.TemporaryDirectory(prefix='24days-spectator-job-') as directory:
            worker = subprocess.run([sys.executable, str(Path(__file__).resolve()), str(scenario), mood],
                                    capture_output=True, text=True, encoding='utf-8', timeout=45,
                                    cwd=str(Path(__file__).resolve().parent),
                                    env={**os.environ, 'TMPDIR': directory})
        if worker.returncode or len(worker.stdout.encode('utf-8')) > 4_000_000:
            raise SpectatorFailure('Simulation worker failed')
        result = json.loads(worker.stdout)
        if len(result.get('frames', [])) != 24 or result.get('scenario') != scenario:
            raise SpectatorFailure('Incomplete simulation')
        with _cache_lock:
            _cache[key] = result
            _cache.move_to_end(key)
            while len(_cache) > 8:
                _cache.popitem(last=False)
        return result
    except (subprocess.TimeoutExpired, json.JSONDecodeError, OSError) as exc:
        raise SpectatorFailure('Simulation unavailable') from exc
    finally:
        _build_lock.release()


def public_view(state, histories):
    """The full server state can contain teaching internals. Policies get only these."""
    day = state['room']['day']
    return {
        'day': day, 'cash': state['player']['cash'], 'net': state['player']['net'],
        'holdings': [{k: h[k] for k in ('asset', 'qty', 'cost')} for h in state['holdings']],
        'deposits': [{k: d[k] for k in ('principal', 'term', 'status')} for d in state['deposits']],
        'assets': [{k: a[k] for k in ('id', 'name', 'sector', 'type', 'risk', 'price', 'change')}
                   for a in state['assets']],
        'news': [{k: n.get(k) for k in ('id', 'day', 'title', 'body', 'sector', 'kind', 'certainty',
                  'event_id', 'related_assets', 'metrics', 'horizon', 'expected_start', 'is_signal', 'reading')}
                 for n in state['news'] if n['day'] <= day],
        'reports': [{k: r.get(k) for k in ('asset', 'quarter', 'day', 'profit_growth', 'market_verdict', 'evidence_ids')}
                    for r in state.get('reports', []) if r['day'] <= day],
        'histories': {aid: [dict(bar) for bar in bars if bar['day'] <= day] for aid, bars in histories.items()},
    }


def article_title(news):
    return (news.get('reading') or {}).get('title') or news['title']


def news_signal(view, asset):
    articles = [n for n in view['news'] if asset['id'] in (n.get('related_assets') or []) or n['sector'] == asset['id']]
    score, seen, evidence, explanation, signal_key = 0.0, set(), [], '', None
    for n in sorted(articles, key=lambda n: (n['day'], n['id']), reverse=True):
        key = n.get('event_id') or ('article', n['id'])
        if key in seen or view['day'] - n['day'] > 8:
            continue
        seen.add(key)
        metrics = n.get('metrics') or {}
        effect = float(metrics.get('revenue_pct', 0)) * .4 + float(metrics.get('margin_pp', 0)) * 6
        if metrics.get('status') in ('failed', 'cancelled'):
            effect = -max(2, abs(effect))
        if metrics.get('status') == 'delayed':
            effect -= 1
        if not effect:
            continue
        certainty = .8 if n.get('certainty') == '전망·미확정' else 1
        score += effect * certainty * max(.25, 1 - (view['day'] - n['day']) / 10)
        if not explanation:
            explanation = f'「{article_title(n)[:65]}」에서 매출 {metrics.get("revenue_pct", 0):+.1f}%, 100원 팔 때 남는 이익 {metrics.get("margin_pp", 0):+.2f}원 변화 정보를 확인했어요.'
            signal_key = ('news', n['id'])
        evidence.append(n['id'])
    reports = sorted((r for r in view['reports'] if r['asset'] == asset['id'] and r['quarter'] > 0),
                     key=lambda r: r['quarter'], reverse=True)
    if reports:
        report = reports[0]
        score += {'예상 상회': 1.4, '예상 하회': -1.4}.get(report.get('market_verdict'), 0)
        score += max(-1, min(1, float(report.get('profit_growth') or 0) / 15))
        if not explanation:
            explanation = f'{report["quarter"]}분기 실적의 영업이익은 이전보다 {report.get("profit_growth", 0):+.1f}% 변했고, 시장 예상과 비교하면 {report.get("market_verdict") or "예상 부합"}이었어요.'
            signal_key = ('report', report['quarter'])
            evidence = list(report.get('evidence_ids') or [])
    return {'score': score, 'ids': evidence[:5], 'reason': explanation, 'key': signal_key,
            'unconfirmed': any(n.get('is_signal') and view['day'] - n['day'] < 3 for n in articles)}


def plan_actions(bot_id, view, memory):
    assets = {a['id']: a for a in view['assets']}
    held = {h['asset']: h for h in view['holdings']}
    day, net = view['day'], view['net']
    actions = []
    if bot_id == 'news':
        signals = {a['id']: news_signal(view, a) for a in view['assets'] if a['type'] == 'stock'}
        for aid, h in held.items():
            signal = signals.get(aid, {'score': 0, 'ids': [], 'reason': ''})
            gain = (assets[aid]['price'] * h['qty'] - h['cost']) / h['cost']
            if signal['score'] < -1.5 or gain <= -.25:
                reason = signal['reason'] + (' 기대를 지지하는 정보가 약해져 보유분을 정리해요.' if signal['score'] < -1.5 else ' 매수 비용보다 25% 이상 내려 손실 제한 기준에 따라 정리해요.')
                actions.append({'type': 'sell', 'asset': aid, 'qty': h['qty'], 'reason': reason, 'evidence_ids': signal['ids']})
                break
        if day < 24:
            for aid, signal in sorted(signals.items(), key=lambda x: (-x[1]['score'], x[0])):
                if any(a.get('asset') == aid and a['type'] == 'sell' for a in actions):
                    continue
                value = held.get(aid, {}).get('qty', 0) * assets[aid]['price']
                if signal['score'] <= .7 or value >= net * .18 or memory.get('signals', {}).get(aid) == signal['key']:
                    continue
                if len(held) >= 3 and aid not in held and not actions:
                    continue
                budget = min(net * (.25 if signal['unconfirmed'] else .35), max(0, net * .35 - value))
                if budget < assets[aid]['price'] + 1:
                    continue
                caution = ' 아직 확인되지 않은 취재도 있어 이번 매수 예산을 25% 이내로 낮췄어요.' if signal['unconfirmed'] else ' 전망은 바뀔 수 있어 이번 매수는 총자산의 35% 이내로 정했어요.'
                actions.append({'type': 'buy', 'asset': aid, 'budget': int(budget), 'reason': signal['reason'] + caution,
                                'evidence_ids': signal['ids'], 'signal_key': signal['key']})
                break
        waiting = '새로 비중을 늘릴 만한 근거가 부족하거나 이미 정한 비중을 채워 오늘은 보유 상태를 유지해요.'
    elif bot_id == 'balanced':
        weights = {'MKT': .5, 'GOV': .2, 'GOLD': .1}
        if day == 1:
            actions.append({'type': 'deposit', 'principal': 20000, 'term': 24, 'reason': '시작 자금의 20%는 24일 예금에 맡겨요. 끝까지 유지하면 10% 이자를 받는 안전한 몫으로 정했어요.', 'evidence_ids': []})
        if day <= 2 or day in (7, 13, 19):
            for aid, weight in weights.items():
                h = held.get(aid)
                if h and h['qty'] * assets[aid]['price'] > net * (weight + .1):
                    qty = h['qty'] - math.floor(net * weight / assets[aid]['price'])
                    actions.append({'type': 'sell', 'asset': aid, 'qty': qty,
                                    'reason': f'분기가 지나 비중을 점검했어요. {assets[aid]["name"]} 비중이 목표 {weight:.0%}보다 10%p 넘게 커져 일부를 줄여요.', 'evidence_ids': []})
                    break
            gaps = sorted(weights, key=lambda aid: -(net * weights[aid] - held.get(aid, {}).get('qty', 0) * assets[aid]['price']))
            for aid in gaps:
                qty = math.floor((net * weights[aid] - held.get(aid, {}).get('qty', 0) * assets[aid]['price']) / assets[aid]['price'])
                if qty < 1:
                    continue
                reasons = {'MKT': '전체시장 ETF는 여러 기업을 함께 담아요. 특정 기업 하나에 결과가 몰리지 않게 전체시장을 따라가요.',
                           'GOV': '국채를 함께 보유해 주식에만 투자하지 않아요. 가격은 바뀔 수 있지만 3일마다 지급되는 이자도 함께 살펴요.',
                           'GOLD': '금은 기업 주식과 다른 자산이에요. 자산 일부를 금으로 나눠 보유해요.'}
                actions.append({'type': 'buy', 'asset': aid, 'qty': qty, 'reason': reasons[aid], 'evidence_ids': []})
                if sum(a['type'] in ('buy', 'sell') for a in actions) >= 2:
                    break
        waiting = '분산한 자산을 이어 보유해요. 매일 바꾸기보다 분기가 지난 7·13·19일차에 비중을 점검하기로 했어요.'
    else:
        for aid, h in held.items():
            price = assets[aid]['price']
            gross = price * h['qty']
            fee = max(1, (gross * 15 + 50000) // 100000)
            gain = (gross - fee - h['cost']) / h['cost'] * 100
            age = day - memory.get('bought', {}).get(aid, day)
            if gain >= 10 or gain <= -8 or age >= 3:
                condition = '목표 수익 10%' if gain >= 10 else '손실 제한 8%' if gain <= -8 else '최대 보유 3일'
                actions.append({'type': 'sell', 'asset': aid, 'qty': h['qty'],
                                'reason': f'{assets[aid]["name"]}을 {age}일 보유했고, 매도 수수료까지 고려한 수익률은 {gain:+.1f}%예요. 미리 정한 {condition} 조건에 닿아 정리해요.', 'evidence_ids': []})
                break
        if day < 24 and (len(held) < 3 or actions):
            candidates = []
            for a in view['assets']:
                bars = view['histories'].get(a['id'], [])
                if a['type'] != 'stock' or a['id'] in held or len(bars) < 3:
                    continue
                change = (bars[-1]['price'] / bars[-3]['price'] - 1) * 100
                if change > .7:
                    candidates.append((change + a['change'] * .3, a['id'], change))
            if candidates:
                _, aid, change = max(candidates)
                actions.append({'type': 'buy', 'asset': aid, 'budget': int(net * .3),
                                'reason': f'{assets[aid]["name"]} 가격이 최근 이틀 동안 {change:+.1f}% 움직였어요. 단기 상승 흐름을 보고 들어가되, 3일 보유·수익 10%·손실 8% 기준으로 다시 판단해요.', 'evidence_ids': []})
        waiting = '최근 이틀의 상승 흐름을 더 확인하거나, 이미 가진 상품이 매도 기준에 닿는지 기다려요.'
    if not actions:
        return [{'type': 'wait', 'reason': '오늘은 마지막 투자일이에요. 새로 사서 수수료를 더 내기보다 마감 때 최종 정산을 기다려요.' if day == 24 else waiting, 'evidence_ids': []}]
    return actions


def compact_player(state, bot_id):
    prices = {a['id']: a for a in state['assets']}
    p = state['player']
    return {'id': bot_id, 'cash': p['cash'], 'net': p['net'], 'profit': p['profit'],
            'return_pct': round(p['profit'] / state['room']['start_cash'] * 100, 2),
            'fees_paid': p['fees_paid'], 'trades': sum(not o.get('is_final_liquidation') for o in state['orders']),
            'income': state['bond_income']['paid'] + sum(max(0, d.get('paid', 0) - d['principal']) for d in state['deposits'] if d['status'] == 'matured'),
            'holdings': [{'asset': h['asset'], 'name': prices[h['asset']]['name'], 'qty': h['qty'],
                          'price': prices[h['asset']]['price'], 'value': h['qty'] * prices[h['asset']]['price'],
                          'average_cost': h['cost'] / h['qty']} for h in state['holdings']],
            'deposits': [{k: d.get(k) for k in ('principal', 'term', 'rate', 'status', 'paid')} for d in state['deposits']]}


def affordable_quantity(cash, budget, price, fee):
    low, high = 0, min(100000, max(0, min(cash, budget)) // price)
    while low < high:
        mid = (low + high + 1) // 2
        if mid * price + fee(mid * price) <= min(cash, budget):
            low = mid
        else:
            high = mid - 1
    return low


def run_game(srv, scenario, mood):
    from unittest.mock import patch
    seed = 104729 + scenario * 7919
    with patch.object(srv.secrets, 'randbelow', side_effect=lambda n: seed % n):
        room = srv.create_room(srv.CreateRoom(name='AI 관전 전용 경기', password='spectator-local-only'))
    auth = 'Bearer ' + room['token']
    srv.set_mood(srv.MoodIn(mood=mood), authorization=auth, x_haru_game_generation=None, x_haru_expected_day=None)
    bots = []
    for profile in BOT_PROFILES:
        joined = srv.join(srv.Join(code=room['code'], name=profile['name'], pin='spectator-only'))
        bots.append({**profile, 'auth': 'Bearer ' + joined['token'], 'memory': {'bought': {}, 'signals': {}}})
    rid = srv.state(auth)['room']['id']
    frames, news, histories = [], {}, {a['id']: [] for a in srv.ASSETS}
    event_id = 0
    last_closing = {}
    for day in range(1, 25):
        states = {b['id']: srv.state(b['auth']) for b in bots}
        shared = states['news']
        for a in shared['assets']:
            histories[a['id']].append({'day': day, 'price': a['price'], 'change': a['change']})
        for n in shared['news']:
            news[n['id']] = {k: n.get(k) for k in ('id', 'day', 'title', 'body', 'reading', 'source', 'certainty', 'kind', 'related_assets', 'horizon', 'is_breaking')}
        opening = [compact_player(states[b['id']], b['id']) for b in bots]
        frame = {'day': day, 'quarter': (day - 1) // 6 + 1, 'earnings': day % 6 == 0,
                 'news_ids': [n['id'] for n in shared['news'] if n['day'] == day],
                 'prices': {a['id']: {'price': a['price'], 'change': a['change']} for a in shared['assets']},
                 'opening': opening, 'events': []}

        def emit(bot, kind, reason, state, **details):
            nonlocal event_id
            event_id += 1
            event = {'id': event_id, 'day': day, 'bot_id': bot['id'], 'type': kind, 'reason': reason[:490],
                     'evidence_ids': [], 'automatic': False, 'after': compact_player(state, bot['id']), **details}
            frame['events'].append(event)

        for bot in bots:
            current = states[bot['id']]
            start = compact_player(current, bot['id'])
            old = last_closing.get(bot['id'])
            if old and start['income'] > old['income']:
                emit(bot, 'income', '예금 만기 또는 채권 이자가 계좌에 반영됐어요.', current,
                     amount=start['income'] - old['income'], automatic=True)
            perception = public_view(current, histories)
            for action in plan_actions(bot['id'], perception, bot['memory']):
                current = srv.state(bot['auth'])
                reason, kind = action['reason'], action['type']
                evidence = [nid for nid in action.get('evidence_ids', []) if nid in news and news[nid]['day'] <= day][:5]
                if kind == 'wait':
                    emit(bot, kind, reason, current)
                    continue
                if kind == 'deposit':
                    srv.deposit(srv.DepositIn(principal=action['principal'], term=action['term']),
                                authorization=bot['auth'], x_haru_game_generation=None, x_haru_expected_day=None)
                    emit(bot, kind, reason, srv.state(bot['auth']), amount=action['principal'], term=action['term'])
                    continue
                asset = next(a for a in current['assets'] if a['id'] == action['asset'])
                held = next((h['qty'] for h in current['holdings'] if h['asset'] == asset['id']), 0)
                qty = min(held, action.get('qty', held)) if kind == 'sell' else affordable_quantity(
                    current['player']['cash'], action.get('budget', action.get('qty', 0) * asset['price'] + srv.trading_fee(action.get('qty', 0) * asset['price'])), asset['price'], srv.trading_fee)
                if qty < 1:
                    emit(bot, 'wait', f'{asset["name"]}을 검토했지만 정한 예산과 남은 현금으로는 수수료를 포함해 1주를 살 수 없어 이번 선택은 건너뛰어요.', current)
                    continue
                result = srv.place_order(srv.OrderIn(asset=asset['id'], side=kind, qty=qty, reason=reason[:490],
                    evidence_ids=evidence, expected_day=day, expected_price=asset['price']),
                    authorization=bot['auth'], x_haru_game_generation=None, x_haru_expected_day=None)
                after = srv.state(bot['auth'])
                emit(bot, kind, reason, after, asset=asset['id'], asset_name=asset['name'], qty=qty,
                     price=result['price'], gross=qty * result['price'], fee=result['fee'], settlement=result['settlement'], evidence_ids=evidence)
                if kind == 'buy':
                    bot['memory']['bought'].setdefault(asset['id'], day)
                    if action.get('signal_key'):
                        bot['memory']['signals'][asset['id']] = action['signal_key']
                elif not any(h['asset'] == asset['id'] for h in after['holdings']):
                    bot['memory']['bought'].pop(asset['id'], None)
        before_close = {b['id']: srv.state(b['auth']) for b in bots}
        with srv.conn() as c:
            c.execute('BEGIN IMMEDIATE')
            srv.close_trading_day(c, srv.one(c, 'SELECT * FROM rooms WHERE id=?', (rid,)))
        closing = []
        for bot in bots:
            after = srv.state(bot['auth'])
            summary = compact_player(after, bot['id'])
            prior = compact_player(before_close[bot['id']], bot['id'])
            if summary['income'] > prior['income'] and day < 24:
                emit(bot, 'income', '보유한 채권에서 쌓인 이자가 현금으로 지급됐어요.', after,
                     amount=summary['income'] - prior['income'], automatic=True)
            if day == 24:
                fills = [{k: o[k] for k in ('asset', 'qty', 'price', 'fee')} for o in after['orders'] if o.get('is_final_liquidation')]
                emit(bot, 'settlement', '24일이 끝나 게임 규칙에 따라 남은 상품을 자동 매도하고 수수료·예금·이자를 최종 정산했어요. AI의 매매 판단과는 별개인 결산이에요.', after,
                     fills=fills, fee=summary['fees_paid'] - prior['fees_paid'], automatic=True)
            closing.append(summary)
            last_closing[bot['id']] = summary
        frame['closing'] = closing
        frames.append(frame)
        if day < 24:
            with srv.conn() as c:
                c.execute('BEGIN IMMEDIATE')
                srv.advance_room(c, srv.one(c, 'SELECT * FROM rooms WHERE id=?', (rid,)))
    return {'version': 1, 'scenario': scenario, 'mood': mood, 'days': 24, 'initial_cash': 100000,
            'agent_kind': 'rule-based', 'information': 'published-only', 'fee_policy': srv.FEE_POLICY,
            'bots': BOT_PROFILES, 'assets': [{k: a[k] for k in ('id', 'name', 'sector', 'type')} for a in srv.ASSETS],
            'news': list(news.values()), 'frames': frames,
            'final': sorted(frames[-1]['closing'], key=lambda p: (-p['net'], p['id']))}


def worker_main():
    scenario, mood = int(sys.argv[1]), sys.argv[2]
    if not 0 <= scenario < 64 or mood not in ('neutral', 'positive', 'negative'):
        raise ValueError('Invalid spectator scenario')
    with tempfile.TemporaryDirectory(prefix='24days-spectator-') as directory:
        db = Path(directory) / 'spectator.db'
        os.environ['HARU_DB'] = str(db)
        os.environ.pop('HARU_RESET_PLAY_ONCE', None)
        import server
        if server.DB.resolve() != db.resolve():
            raise RuntimeError('Spectator database isolation failed')
        result = run_game(server, scenario, mood)
    print(json.dumps(result, ensure_ascii=False, separators=(',', ':')))


if __name__ == '__main__':
    worker_main()
