"""Offline calibration using the same SQLite/news/earnings/price code as live games."""
import argparse
import json
import math
import sqlite3
import sys
from collections import defaultdict
from pathlib import Path
from statistics import mean, pstdev

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import server
import classroom_engine as engine
import breaking_news


def percentile(values, p):
    values = sorted(values)
    at = (len(values) - 1) * p
    lo = math.floor(at)
    return values[lo] + (values[min(lo + 1, len(values) - 1)] - values[lo]) * (at - lo)


def simulate(seed, mood='neutral'):
    c = sqlite3.connect(':memory:')
    c.row_factory = sqlite3.Row
    c.executescript('''
      CREATE TABLE news(id INTEGER PRIMARY KEY,room_id INTEGER,day INTEGER,title TEXT,body TEXT,sector TEXT,impact REAL DEFAULT 0,active INTEGER DEFAULT 1);
      CREATE TABLE orders(id INTEGER PRIMARY KEY);
      CREATE TABLE prices(room_id INTEGER,day INTEGER,asset TEXT,price INTEGER,change REAL DEFAULT 0,open_price INTEGER,high_price INTEGER,low_price INTEGER,drivers TEXT);
    ''')
    engine.initialize_schema(c)
    c.executemany('INSERT INTO prices(room_id,day,asset,price,change) VALUES(1,1,?,?,0)', [(a['id'], a['initial']) for a in server.ASSETS])
    engine.publish_news(c, 1, 1, seed, mood, server.ASSETS)
    breaking_news.publish_clues(c,1,1,seed,mood,server.ASSETS)
    for day in range(2, 25):
        engine.evolve_businesses(c, 1, day, seed, server.ASSETS)
        engine.resolve_events(c, 1, day, seed, server.ASSETS)
        breaking = breaking_news.publish_open(c,1,day,seed,mood,server.ASSETS)
        reactions = engine.release_earnings(c, 1, day, seed, server.ASSETS)
        server.generate_prices(c, 1, day, seed, reactions,breaking)
        engine.publish_news(c, 1, day, seed, mood, server.ASSETS)
        breaking_news.publish_clues(c,1,day,seed,mood,server.ASSETS)
    result = {}
    for a in server.ASSETS:
        bars = c.execute('SELECT price,change FROM prices WHERE asset=? ORDER BY day', (a['id'],)).fetchall()
        peak = bars[0]['price']
        drawdown = 0
        for bar in bars:
            peak = max(peak, bar['price'])
            drawdown = min(drawdown, 100 * (bar['price'] / peak - 1))
        result[a['id']] = {'return': 100 * (bars[-1]['price'] / bars[0]['price'] - 1),
                           'daily': [b['change'] for b in bars[1:]], 'drawdown': drawdown}
    c.close()
    return result


def summarize(games):
    grouped = defaultdict(list)
    daily = defaultdict(list)
    drawdowns = defaultdict(list)
    for game in games:
        for a in server.ASSETS:
            key = a['risk'] if a['type'] == 'stock' else a['id']
            grouped[key].append(game[a['id']]['return'])
            daily[key].extend(game[a['id']]['daily'])
            drawdowns[key].append(game[a['id']]['drawdown'])
        grouped['equal_stock_basket'].append(mean(game[a['id']]['return'] for a in server.ASSETS if a['type'] == 'stock'))
    summary = {}
    for key, values in grouped.items():
        summary[key] = {'mean': round(mean(values), 3), 'median': round(percentile(values, .5), 3),
                        'p10': round(percentile(values, .1), 3), 'p90': round(percentile(values, .9), 3),
                        'sd': round(pstdev(values), 3), 'loss_pct': round(100 * mean(v < 0 for v in values), 2),
                        'beat_deposit_pct': round(100 * mean(v > 10 for v in values), 2)}
        if daily[key]:
            summary[key].update(daily_sd=round(pstdev(daily[key]), 3), daily_abs_p95=round(percentile([abs(x) for x in daily[key]], .95), 3),
                                median_drawdown=round(percentile(drawdowns[key], .5), 3))
    return summary


if __name__ == '__main__':
    p = argparse.ArgumentParser()
    p.add_argument('--games', type=int, default=300)
    p.add_argument('--moods', nargs='+', default=['neutral'])
    p.add_argument('--output')
    args = p.parse_args()
    results = {'games_per_mood': args.games, 'days': 24, 'price_intervals': 23,
               'deposit_return': 10, 'method': 'day-1 purchase, day-24 price valuation; fractional buy-and-hold, no market timing; stocks and ETFs have no dividends'}
    for mood in args.moods:
        results[mood] = summarize([simulate(7919 * i + 104729, mood) for i in range(args.games)])
    payload = json.dumps(results, ensure_ascii=False, indent=2)
    if args.output:
        Path(args.output).write_text(payload)
    print(payload)
