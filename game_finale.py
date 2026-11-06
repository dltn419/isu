"""Atomic final cash settlement and a frozen, room-scoped classroom retrospective.

Trade cards use complete position episodes (flat -> buys/partial sells -> flat),
including both fees and earned bond coupons. Style awards use daily closing
portfolios before compulsory liquidation and never count that sale as activity.
"""
import json
from collections import defaultdict

import bond_income
import etf_portfolio


def initialize(c):
    if 'is_final_liquidation' not in {r[1] for r in c.execute('PRAGMA table_info(orders)')}:
        c.execute('ALTER TABLE orders ADD COLUMN is_final_liquidation INTEGER NOT NULL DEFAULT 0')
    if 'closed_day' not in {r[1] for r in c.execute('PRAGMA table_info(deposits)')}:
        c.execute('ALTER TABLE deposits ADD COLUMN closed_day INTEGER')
    c.execute('''CREATE TABLE IF NOT EXISTS final_settlements(
        room_id INTEGER PRIMARY KEY, generation INTEGER NOT NULL,
        created TEXT NOT NULL, report TEXT NOT NULL)''')


def settle(c, room, assets, fee_for, timestamp):
    """Caller owns BEGIN IMMEDIATE; any failure rolls back coupons, sales and report."""
    rid, day = room['id'], room['day']
    if day != 24:
        raise ValueError('최종 정산은 24일차에만 가능합니다.')
    previous = c.execute('SELECT report FROM final_settlements WHERE room_id=? AND generation=?',
                         (rid, room['generation'])).fetchone()
    if previous:
        return json.loads(previous['report'])
    prices = {r['asset']: r['price'] for r in c.execute(
        'SELECT asset,price FROM prices WHERE room_id=? AND day=?', (rid, day))}
    holdings = c.execute('''SELECT h.* FROM holdings h JOIN players p ON p.id=h.player_id
                            WHERE p.room_id=? ORDER BY h.player_id,h.asset''', (rid,)).fetchall()
    fees = 0
    for h in holdings:
        price = prices[h['asset']]  # Missing prices must fail, never sell for zero.
        gross = h['qty'] * price
        fee = fee_for(gross)
        fees += fee
        c.execute('''INSERT INTO orders(room_id,player_id,asset,side,qty,price,status,
                     reason,created,filled_day,fee,is_final_liquidation)
                     VALUES(?,?,?,'sell',?,?,'filled',?,?,24,?,1)''',
                  (rid, h['player_id'], h['asset'], h['qty'], price,
                   '24일차 게임 종료 · 마지막 시세로 자동 정산', timestamp, fee))
        c.execute('UPDATE players SET cash=cash+? WHERE id=? AND room_id=?',
                  (gross - fee, h['player_id'], rid))
        c.execute('DELETE FROM holdings WHERE player_id=? AND asset=?', (h['player_id'], h['asset']))
        c.executemany('''INSERT INTO ledgers(room_id,player_id,day,kind,amount,note)
                         VALUES(?,?,?,?,?,?)''',
                      [(rid, h['player_id'], day, 'trade', gross,
                        f"게임 종료 자동 매도 · {h['asset']} {h['qty']}주"),
                       (rid, h['player_id'], day, 'fee', -fee, '게임 종료 자동 매도 수수료')])
    # Normally every permitted deposit has already matured by day 24. Also handle
    # older deposits safely: compulsory termination earns the accrued contract rate,
    # without the voluntary early-withdrawal discount.
    for d in c.execute("SELECT * FROM deposits WHERE room_id=? AND status='active'", (rid,)).fetchall():
        fraction = min(1, max(0, day - d['start_day'] + 1) / d['term'])
        paid = d['principal'] + round(d['principal'] * d['rate'] * fraction)
        status = 'matured' if fraction == 1 else 'settled'
        c.execute('UPDATE deposits SET status=?,paid=?,closed_day=? WHERE id=?', (status, paid, day, d['id']))
        c.execute('UPDATE players SET cash=cash+? WHERE id=?', (paid, d['player_id']))
        c.execute('INSERT INTO ledgers(room_id,player_id,day,kind,amount,note) VALUES(?,?,?,?,?,?)',
                  (rid, d['player_id'], day, 'interest', paid, '게임 종료 예금 정산 · 약정 이자 반영'))
    report = build_report(c, room, assets, settled=True)
    report.update(liquidation_count=len(holdings), liquidation_fees=fees)
    c.execute('INSERT INTO final_settlements VALUES(?,?,?,?)',
              (rid, room['generation'], timestamp, json.dumps(report, ensure_ascii=False)))
    return report


def _deposit_end(d):
    if d['closed_day'] is not None:
        return d['closed_day']
    if d['status'] == 'matured':
        return d['start_day'] + d['term'] - 1
    return None


def _analyse(c, room, assets, players):
    rid, last = room['id'], room['day']
    amap = {a['id']: a for a in assets}
    trades = [dict(r) for r in c.execute("""SELECT * FROM orders WHERE room_id=? AND status='filled'
        ORDER BY COALESCE(filled_day,1),id""", (rid,))]
    by_day = defaultdict(list)
    net_qty = defaultdict(int)
    turnover = defaultdict(int)
    trade_count = defaultdict(int)
    for t in trades:
        by_day[t['filled_day'] or 1].append(t)
        key = t['player_id'], t['asset']
        net_qty[key] += t['qty'] * (1 if t['side'] == 'buy' else -1)
        if not t['is_final_liquidation']:
            turnover[t['player_id']] += t['qty'] * t['price']
            trade_count[t['player_id']] += 1
    present = {(r['player_id'], r['asset']): r['qty'] for r in c.execute(
        '''SELECT h.* FROM holdings h JOIN players p ON p.id=h.player_id WHERE p.room_id=?''', (rid,))}
    # Unrecorded legacy starting holdings may explain exposure, but cannot support
    # invented acquisition costs or realized-profit cards.
    positions = defaultdict(lambda: {'qty': 0, 'episode': None})
    episodes = []
    for key in present.keys() | net_qty.keys():
        qty = present.get(key, 0) - net_qty.get(key, 0)
        if qty > 0:
            episode = {'id': f'legacy:{key}', 'player_id': key[0], 'asset': key[1], 'start_day': 1,
                       'invested': 0, 'proceeds': 0, 'buy_qty': 0, 'peak_qty': qty, 'fees': 0,
                       'units': 0, 'known': False, 'end_day': None, 'automatic': False}
            positions[key] = {'qty': qty, 'episode': episode}
            episodes.append(episode)

    def apply(t):
        key = t['player_id'], t['asset']
        p = positions[key]
        gross, fee = t['qty'] * t['price'], t['fee']
        if t['side'] == 'buy':
            if p['qty'] == 0:
                p['episode'] = {'id': f"trade:{t['id']}", 'player_id': key[0], 'asset': key[1],
                    'start_day': t['filled_day'] or 1, 'invested': 0, 'proceeds': 0, 'buy_qty': 0,
                    'peak_qty': 0, 'fees': 0, 'units': 0, 'known': True, 'end_day': None, 'automatic': False}
                episodes.append(p['episode'])
            e = p['episode']
            p['qty'] += t['qty']
            e['invested'] += gross + fee
            e['fees'] += fee
            e['buy_qty'] += t['qty']
            e['peak_qty'] = max(e['peak_qty'], p['qty'])
        else:
            e = p['episode']
            if e is None:
                return
            if t['qty'] > p['qty']:
                e['known'] = False
            p['qty'] = max(0, p['qty'] - t['qty'])
            e['proceeds'] += gross - fee
            e['fees'] += fee
            e['automatic'] |= bool(t['is_final_liquidation'])
            if p['qty'] == 0:
                e['end_day'] = t['filled_day'] or 1
                p['episode'] = None

    prices = {(r['day'], r['asset']): r['price'] for r in c.execute(
        'SELECT day,asset,price FROM prices WHERE room_id=?', (rid,))}
    values = {(r['player_id'], r['day']): r['net'] for r in c.execute(
        'SELECT player_id,day,net FROM daily_values WHERE room_id=?', (rid,))}
    accruals = {(r['player_id'], r['asset'], r['day']): r['units'] for r in c.execute(
        'SELECT * FROM bond_accruals WHERE room_id=?', (rid,))}
    deposits = [dict(d) for d in c.execute('SELECT * FROM deposits WHERE room_id=?', (rid,))]
    metrics = {pid: {'concentration': 0, 'concentration_day': None, 'concentration_target': '',
                     'longest': 0, 'long_target': '', 'long_start': None, 'long_end': None,
                     'diversity': 0, 'invested_share': 0, 'wealth': 0,
                     'trade_count': trade_count[pid]} for pid in players}
    streaks = {}
    etfs = {a['id']: etf_portfolio.components(assets, a['sector']) for a in assets if a['type'] == 'etf'}
    for day in range(1, last + 1):
        for t in by_day[day]:
            if not t['is_final_liquidation']:
                apply(t)
        buckets = {pid: defaultdict(float) for pid in players}
        sectors = {pid: defaultdict(float) for pid in players}
        equity = {pid: defaultdict(float) for pid in players}
        equity_sectors = {pid: defaultdict(float) for pid in players}
        invested = defaultdict(float)
        today_streaks = {}
        for (pid, aid), pos in positions.items():
            if pos['qty'] <= 0 or pid not in players or aid not in amap:
                continue
            a = amap[aid]
            value = pos['qty'] * prices.get((day, aid), a['initial'])
            invested[pid] += value
            net = max(1, values.get((pid, day), room['start_cash']))
            if pos['episode']:
                e = pos['episode']
                e['units'] += accruals.get((pid, aid, day), 0)
                # A round-trip and repurchase resets the streak, even on the same day.
                key = e['id']
                if value >= net * .1:
                    start = streaks.get(key, day)
                    today_streaks[key] = start
                    length = day - start + 1
                    if length > metrics[pid]['longest']:
                        metrics[pid].update(longest=length, long_target=a['name'], long_start=start, long_end=day)
            if a['type'] == 'etf':
                multiplier = abs({'LEV2': 2, 'INV2': -2}.get(aid, 1))
                for h in etfs[aid]:
                    amount = value * multiplier * h['weight']
                    buckets[pid][h['asset']] += amount
                    sectors[pid][h['sector']] += amount
                    equity[pid][h['asset']] += amount
                    equity_sectors[pid][h['sector']] += amount
            else:
                buckets[pid][aid] += value
                sectors[pid][a['sector']] += value
                if a['type'] == 'stock':
                    equity[pid][aid] += value
                    equity_sectors[pid][a['sector']] += value
        streaks = today_streaks
        for d in deposits:
            end = _deposit_end(d)
            if d['start_day'] <= day and (d['status'] == 'active' or (end is not None and day < end)):
                invested[d['player_id']] += d['principal']
                buckets[d['player_id']]['deposit'] += d['principal']
                sectors[d['player_id']]['예금'] += d['principal']
        for pid, m in metrics.items():
            net = max(1, values.get((pid, day), room['start_cash']))
            m['wealth'] += net
            share = min(1, invested[pid] / net)
            m['invested_share'] += share
            gross = sum(buckets[pid].values())
            if gross:
                company_hhi = sum((amount / gross) ** 2 for amount in buckets[pid].values())
                sector_hhi = sum((amount / gross) ** 2 for amount in sectors[pid].values())
                # Gross look-through prevents offsetting inverse products from
                # claiming spurious diversification; leverage also reduces this score.
                m['diversity'] += 100 * (1 - (company_hhi + sector_hhi) / 2) * share / max(1, gross / net)
            candidates = [(v / net, amap[k]['name']) for k, v in equity[pid].items()]
            candidates += [(v / net, k + ' 업종') for k, v in equity_sectors[pid].items()]
            if candidates:
                concentration, target = max(candidates, key=lambda x: x[0])
                if concentration > m['concentration']:
                    m.update(concentration=concentration, concentration_day=day, concentration_target=target)
        # Compulsory liquidation comes after the final coupon and closing portfolio.
        for t in by_day[day]:
            if t['is_final_liquidation']:
                apply(t)

    cards = []
    coupon_units = defaultdict(int)
    for e in episodes:
        key = e['player_id'], e['asset']
        previous = bond_income.rounded(coupon_units[key])
        coupon_units[key] += e['units']
        interest = bond_income.rounded(coupon_units[key]) - previous
        if e['end_day'] is None or not e['known'] or not e['invested']:
            continue
        profit = e['proceeds'] + interest - e['invested']
        cards.append({'id': e['id'], 'player_id': e['player_id'], 'name': players[e['player_id']]['name'],
            'asset': e['asset'], 'asset_name': amap[e['asset']]['name'], 'kind': 'trade',
            'start_day': e['start_day'], 'end_day': e['end_day'],
            'holding_days': e['end_day'] - e['start_day'] + 1, 'quantity': e['buy_qty'],
            'peak_quantity': e['peak_qty'], 'invested': e['invested'], 'proceeds': e['proceeds'],
            'fees': e['fees'], 'interest': interest, 'profit': profit,
            'return_pct': round(profit / e['invested'] * 100, 4), 'automatic': e['automatic']})
    for d in deposits:
        end = _deposit_end(d)
        if d['status'] == 'active' or end is None:
            continue
        profit = d['paid'] - d['principal']
        cards.append({'id': f"deposit:{d['id']}", 'player_id': d['player_id'], 'name': players[d['player_id']]['name'],
            'asset': None, 'asset_name': f"{d['term']}일 정기예금", 'kind': 'deposit',
            'start_day': d['start_day'], 'end_day': end, 'holding_days': end - d['start_day'] + 1,
            'quantity': None, 'peak_quantity': None, 'invested': d['principal'], 'proceeds': d['paid'],
            'fees': 0, 'interest': profit, 'profit': profit,
            'return_pct': round(profit / d['principal'] * 100, 4), 'automatic': d['status'] == 'settled'})
    for pid, m in metrics.items():
        m['diversity'] /= last
        m['invested_share'] /= last
        m['turnover'] = turnover[pid] / max(1, m['wealth'] / last) * 100
    return cards, metrics


def build_report(c, room, assets, *, settled=False):
    rid = room['id']
    players = {p['id']: dict(p) for p in c.execute('SELECT id,name,cash FROM players WHERE room_id=? ORDER BY id', (rid,))}
    cards, metrics = _analyse(c, room, assets, players)
    standings = []
    for pid, p in players.items():
        adjustment = c.execute("SELECT COALESCE(SUM(amount),0) FROM ledgers WHERE player_id=? AND kind='teacher'", (pid,)).fetchone()[0]
        fees = -c.execute("SELECT COALESCE(SUM(amount),0) FROM ledgers WHERE player_id=? AND kind='fee'", (pid,)).fetchone()[0]
        net = p['cash']
        if not settled:
            net += c.execute('''SELECT COALESCE(SUM(h.qty*pr.price),0) FROM holdings h JOIN prices pr
                ON pr.asset=h.asset AND pr.room_id=? AND pr.day=? WHERE h.player_id=?''', (rid, room['day'], pid)).fetchone()[0]
            net += c.execute("SELECT COALESCE(SUM(principal),0) FROM deposits WHERE player_id=? AND status='active'", (pid,)).fetchone()[0]
            net += bond_income.summary(c, pid)['unpaid']
        profit = net - room['start_cash'] - adjustment
        standings.append({'player_id': pid, 'name': p['name'], 'net': net, 'profit': profit,
                          'return_pct': round(profit / room['start_cash'] * 100, 4), 'fees': fees})
    for p in standings:
        p['rank'] = 1 + sum(other['profit'] > p['profit'] for other in standings)
    standings.sort(key=lambda p: (-p['profit'], p['player_id']))

    def award(key, title, emoji, rule, score, eligible):
        candidates = [(pid, round(score(m), 4)) for pid, m in metrics.items() if eligible(m)]
        best = max((v for _, v in candidates), default=None)
        winners = []
        for pid, v in candidates:
            if v != best:
                continue
            m = metrics[pid]
            detail = {'concentration': f"{m['concentration_day']}일차 · {m['concentration_target']}",
                      'turnover': f"자발적 매수·매도 {m['trade_count']}건",
                      'longest': f"{m['long_target']} · {m['long_start']}~{m['long_end']}일차",
                      'diversity': '전체 기간 평균 · ETF 구성과 투자 비중 반영'}[key]
            winners.append({'player_id': pid, 'name': players[pid]['name'], 'value': v, 'detail': detail})
        return {'id': key, 'title': title, 'emoji': emoji, 'rule': rule, 'winners': winners}

    awards = [
        award('concentration', '몰빵왕', '🎯', '하루 마감 총자산 중 개별 기업·주식 업종의 최대 비중. ETF 속 기업까지 합산하며 50% 이상인 기록만 선정해요.',
              lambda m: m['concentration'] * 100, lambda m: m['concentration'] >= .5),
        award('turnover', '회전왕', '🔄', '자발적 누적 매수·매도금액 ÷ 전체 기간 평균 총자산. 마지막 자동 매도는 제외해요.',
              lambda m: m['turnover'], lambda m: m['trade_count'] > 0),
        award('longest', '장투왕', '🌳', '총자산의 10% 이상을 같은 거래상품에 연속 3일 이상 유지한 최장 기간. 완전히 팔고 다시 사면 새로 세고, 예금은 제외해요.',
              lambda m: m['longest'], lambda m: m['longest'] >= 3),
        award('diversity', '분산왕', '🧺', '매일 기업·업종 쏠림을 함께 계산한 분산점수에 투자 비중을 반영해 전체 기간 평균을 내요. ETF 중복을 합산하고 2배·인버스의 노출도 반영해요. 평균 투자 비중 20% 이상만 선정해요.',
              lambda m: m['diversity'], lambda m: m['diversity'] > 0 and m['invested_share'] >= .2),
    ]
    return {'version': 1, 'settled': settled, 'day': room['day'], 'generation': room['generation'],
            'standings': standings,
            'highlights': {'gains': sorted((x for x in cards if x['profit'] > 0), key=lambda x: (-x['profit'], x['id']))[:2],
                           'reviews': sorted((x for x in cards if x['profit'] < 0), key=lambda x: (x['profit'], x['id']))[:2]},
            'awards': awards,
            'rules': ['수익·손실 카드는 수수료와 보유 중 발생한 채권 이자를 포함한 실현손익 기준이에요.',
                      '한 상품을 처음 산 뒤 전부 팔 때까지를 한 투자로 묶어요. 나눠 사고팔아도 손익을 중복 집계하지 않아요.',
                      '수익률은 그 투자에서 누적 지출한 매수금액(수수료 포함) 기준이에요. 예금은 원금 기준이에요.',
                      '보유 구간은 시작일과 종료일을 포함해 세요. 매수·매도일이 같으면 당일 투자예요.',
                      '칭호는 투자 스타일을 돌아보는 재미용이며 점수 보너스가 없어요. 같은 기록은 공동 수상해요.',
                      '최종 순위는 시작 자금 대비 투자 손익 기준이며 교사의 현금 지급·차감은 제외해요.']}


def public_report(c, room, assets):
    if room['phase'] != 'finished':
        return None
    saved = c.execute('SELECT report FROM final_settlements WHERE room_id=? AND generation=?',
                      (room['id'], room['generation'])).fetchone()
    # Existing finished games are displayed with their original balances intact.
    return json.loads(saved['report']) if saved else build_report(c, room, assets, settled=False)
