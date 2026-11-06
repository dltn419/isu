"""Compare v12 coupons and v13 bond balance with identical 24-day price seeds.

Uses the live price function. Company news does not enter bond returns or alter
the fixed number of price RNG draws. Coupons stay in cash; there is no sale or
reinvestment. Returns include the day-1 purchase fee and day-24 marked value.
"""
import argparse
import json
import sqlite3
import sys
from pathlib import Path
from statistics import mean, pstdev

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import server

BONDS = ('GOV', 'CORP', 'JUNK')


def percentile(values, p):
    values = sorted(values)
    at = (len(values) - 1) * p
    lo = int(at)
    return values[lo] + (values[min(lo + 1, len(values) - 1)] - values[lo]) * (at - lo)


def paths(games, volatility, limit):
    original = server.BOND_PRICE_PARAMETERS['JUNK']
    server.BOND_PRICE_PARAMETERS['JUNK'] = {'volatility': volatility, 'limit': limit}
    c = sqlite3.connect(':memory:')
    c.row_factory = sqlite3.Row
    c.executescript('''CREATE TABLE prices(room_id INTEGER,day INTEGER,asset TEXT,price INTEGER,
      change REAL,open_price INTEGER,high_price INTEGER,low_price INTEGER,PRIMARY KEY(room_id,day,asset));
      CREATE TABLE news(room_id INTEGER,day INTEGER,sector TEXT,impact REAL,title TEXT,active INTEGER);''')
    try:
        result = []
        for i in range(games):
            c.execute('DELETE FROM prices')
            c.executemany('INSERT INTO prices(room_id,day,asset,price,change) VALUES(1,1,?,?,0)',
                          [(a['id'], a['initial']) for a in server.ASSETS])
            for day in range(2,25):
                server.generate_prices(c, 1, day, 104729 + 7919 * i)
            result.append({r['asset']: r['price'] for r in c.execute(
                "SELECT asset,price FROM prices WHERE day=24 AND asset IN ('GOV','CORP','JUNK')")})
        return result
    finally:
        c.close()
        server.BOND_PRICE_PARAMETERS['JUNK'] = original


def summarize(data, rates):
    result = {}
    cost = 10000 + server.trading_fee(10000)
    for aid, rate in zip(BONDS, rates):
        values = [100 * ((r[aid] + round(10000 * rate)) / cost - 1) for r in data]
        result[aid] = {'mean': round(mean(values),2), 'p10': round(percentile(values,.1),2),
                       'p90': round(percentile(values,.9),2), 'sd': round(pstdev(values),2),
                       'loss_pct': round(100 * mean(v < 0 for v in values),1),
                       'beat_deposit_pct': round(100 * mean(v > 10 for v in values),1)}
    return result


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('--games', type=int, default=1000)
    parser.add_argument('--output')
    args = parser.parse_args()
    if args.games < 1:
        parser.error('--games must be positive')
    old = paths(args.games, 4, 40)
    settings = server.BOND_PRICE_PARAMETERS['JUNK']
    new = paths(args.games, settings['volatility'], settings['limit'])
    assert all(a[k] == b[k] for a,b in zip(old,new) for k in ('GOV','CORP'))
    rates = [server.AMAP[aid]['yield'] for aid in BONDS]
    result = {'games': args.games, 'deposit_return': 10,
              'method': 'one share bought day1 including fee; day24 close marked value plus full coupons; no sale or reinvestment',
              'old_10_14_22': summarize(old, (.10,.14,.22)),
              'rates_only': summarize(old, rates), 'rates_and_risk': summarize(new, rates)}
    payload = json.dumps(result, ensure_ascii=False, indent=2)
    if args.output:
        Path(args.output).write_text(payload)
    print(payload)
