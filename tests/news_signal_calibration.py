"""Compare published company forecasts with later prices, excluding rare news.

Run: python tests/news_signal_calibration.py 120 /tmp/news_signal.json
This selects initial company forecasts with >=0.5pp model reaction, not every
headline, student trades, causal treatment effects, or a profitable strategy.
"""
import json
import sqlite3
import sys
from pathlib import Path
from statistics import mean

sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
import server
import classroom_engine as engine


def calibrate(games):
    stats={key:[] for key in ('next_day','three_day','relative_three_day',
                             'positive_next_day','negative_next_day')}
    for i in range(games):
        db=sqlite3.connect(':memory:');db.row_factory=sqlite3.Row
        db.executescript('''
          CREATE TABLE news(id INTEGER PRIMARY KEY,room_id INTEGER,day INTEGER,title TEXT,
            body TEXT,sector TEXT,impact REAL DEFAULT 0,active INTEGER DEFAULT 1);
          CREATE TABLE orders(id INTEGER PRIMARY KEY);
          CREATE TABLE prices(room_id INTEGER,day INTEGER,asset TEXT,price INTEGER,
            change REAL DEFAULT 0,open_price INTEGER,high_price INTEGER,low_price INTEGER,drivers TEXT);
        ''')
        engine.initialize_schema(db)
        seed=104729+7919*i
        db.executemany('INSERT INTO prices(room_id,day,asset,price,change) VALUES(1,1,?,?,0)',
                       [(a['id'],a['initial']) for a in server.ASSETS])
        engine.publish_news(db,1,1,seed,'neutral',server.ASSETS)
        for day in range(2,25):
            engine.evolve_businesses(db,1,day,seed,server.ASSETS)
            engine.resolve_events(db,1,day,seed,server.ASSETS)
            earnings=engine.release_earnings(db,1,day,seed,server.ASSETS)
            server.generate_prices(db,1,day,seed,earnings)
            engine.publish_news(db,1,day,seed,'neutral',server.ASSETS)
        prices={(r['asset'],r['day']):r['price'] for r in db.execute('SELECT asset,day,price FROM prices')}
        selected=db.execute("SELECT * FROM news WHERE kind='company' AND certainty='전망·미확정' AND day<=21 AND ABS(impact)>=.5")
        for article in selected:
            aid,day=article['sector'],article['day'];sign=1 if article['impact']>0 else -1
            one=prices[aid,day+1]/prices[aid,day]-1
            three=prices[aid,day+3]/prices[aid,day]-1
            market=prices['MKT',day+3]/prices['MKT',day]-1
            stats['next_day'].append(sign*one>0)
            stats['three_day'].append(sign*three>0)
            stats['relative_three_day'].append(sign*(three-market)>0)
            stats['positive_next_day' if sign>0 else 'negative_next_day'].append(sign*one>0)
        db.close()
    return {'games':games,'articles':len(stats['next_day']),
            'method':'initial company forecasts with |model reaction|>=0.5pp; same seeds; ordinary news and earnings only, breaking news excluded; direction of new information vs subsequent price',
            'agreement_pct':{key:round(100*mean(values),2) for key,values in stats.items()}}


if __name__=='__main__':
    result=calibrate(int(sys.argv[1]))
    Path(sys.argv[2]).write_text(json.dumps(result,ensure_ascii=False,indent=2))
    print(json.dumps(result,ensure_ascii=False))
