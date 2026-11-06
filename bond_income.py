"""Daily closing holdings earn simple interest, paid every three game days.

Integer units retain fractional won between payouts. Selling a bond does not
erase interest already earned. All calls that write run in the caller's transaction.
"""
YEAR_DAYS = 24
INTERVAL = 3
DENOMINATOR = YEAR_DAYS * 10000


def initialize(c):
    if 'bond_interest_version' not in {r[1] for r in c.execute('PRAGMA table_info(rooms)')}:
        c.execute('ALTER TABLE rooms ADD COLUMN bond_interest_version INTEGER NOT NULL DEFAULT 1')
    c.executescript('''
      CREATE TABLE IF NOT EXISTS bond_accruals(
        room_id INTEGER NOT NULL,player_id INTEGER NOT NULL,asset TEXT NOT NULL,
        day INTEGER NOT NULL,qty INTEGER NOT NULL,units INTEGER NOT NULL,
        PRIMARY KEY(room_id,player_id,asset,day));
      CREATE TABLE IF NOT EXISTS bond_payments(
        room_id INTEGER NOT NULL,player_id INTEGER NOT NULL,asset TEXT NOT NULL,
        day INTEGER NOT NULL,amount INTEGER NOT NULL,
        PRIMARY KEY(room_id,player_id,asset,day));
      CREATE INDEX IF NOT EXISTS idx_bond_accrual_player ON bond_accruals(player_id,asset);
      CREATE INDEX IF NOT EXISTS idx_bond_payment_player ON bond_payments(player_id,asset);
    ''')


def rounded(units):
    return (units + DENOMINATOR // 2) // DENOMINATOR


def policy(room):
    legacy = room['bond_interest_version'] == 1
    day, phase = room['day'], room['phase']
    next_day = ((day - 1) // INTERVAL + 1) * INTERVAL
    if phase == 'closed' and next_day == day:
        next_day += INTERVAL
    return {'mode': 'legacy_annual' if legacy else 'periodic',
            'interval_days': INTERVAL, 'year_days': YEAR_DAYS,
            'payment_days': list(range(INTERVAL, YEAR_DAYS + 1, INTERVAL)),
            'next_payment_day': None if phase == 'finished' or next_day > YEAR_DAYS else next_day,
            'holding_basis': 'daily_close', 'rounding': 'cumulative_half_up'}


def summary(c, pid):
    earned = c.execute('SELECT asset,SUM(units) units FROM bond_accruals WHERE player_id=? GROUP BY asset', (pid,)).fetchall()
    paid = {r['asset']: r['amount'] for r in c.execute(
        'SELECT asset,SUM(amount) amount FROM bond_payments WHERE player_id=? GROUP BY asset', (pid,))}
    items = [{'asset': r['asset'], 'unpaid': rounded(r['units']) - paid.get(r['asset'], 0),
              'paid': paid.get(r['asset'], 0)} for r in earned]
    return {'unpaid': sum(r['unpaid'] for r in items),
            'paid': sum(paid.values()), 'items': items}


def accrue(c, rid, pid, asset, day, qty):
    if qty <= 0:
        return
    units = qty * asset['initial'] * round(asset['yield'] * 10000)
    c.execute('INSERT OR IGNORE INTO bond_accruals VALUES(?,?,?,?,?,?)',
              (rid, pid, asset['id'], day, qty, units))


def pay(c, rid, day, assets, *, ledger_day=None, migrated=False):
    if day % INTERVAL:
        return
    bonds = {a['id']: a for a in assets if a['type'] == 'bond'}
    entries = c.execute('''SELECT player_id,asset,SUM(units) units FROM bond_accruals
                           WHERE room_id=? AND day<=? GROUP BY player_id,asset''', (rid, day)).fetchall()
    for r in entries:
        previous = c.execute('''SELECT COALESCE(SUM(amount),0) FROM bond_payments
                                WHERE room_id=? AND player_id=? AND asset=?''',
                             (rid, r['player_id'], r['asset'])).fetchone()[0]
        amount = rounded(r['units']) - previous
        inserted = c.execute('INSERT OR IGNORE INTO bond_payments VALUES(?,?,?,?,?)',
                             (rid, r['player_id'], r['asset'], day, amount)).rowcount
        if inserted and amount:
            c.execute('UPDATE players SET cash=cash+? WHERE id=? AND room_id=?', (amount, r['player_id'], rid))
            note = f"채권 이자 · {bonds[r['asset']]['name']} ({day-INTERVAL+1}~{day}일차)"
            if migrated:
                note += ' · 지급방식 변경 정산'
            c.execute('INSERT INTO ledgers(room_id,player_id,day,kind,amount,note) VALUES(?,?,?,?,?,?)',
                      (rid, r['player_id'], ledger_day if ledger_day is not None else day, 'interest', amount, note))


def close_day(c, room, assets):
    if room['bond_interest_version'] == 1:
        return
    bonds = {a['id']: a for a in assets if a['type'] == 'bond'}
    for h in c.execute('''SELECT h.player_id,h.asset,h.qty FROM holdings h JOIN players p ON p.id=h.player_id
                          WHERE p.room_id=?''', (room['id'],)).fetchall():
        if h['asset'] in bonds:
            accrue(c, room['id'], h['player_id'], bonds[h['asset']], room['day'], h['qty'])
    pay(c, room['id'], room['day'], assets)


def migrate_room(c, room, assets):
    """Rebuild closed-day holdings once; completed legacy games remain untouched."""
    if room['bond_interest_version'] != 1 or room['phase'] == 'finished':
        return
    rid = room['id']
    last_closed = room['day'] - (room['phase'] == 'trading')
    bonds = {a['id']: a for a in assets if a['type'] == 'bond'}
    players = c.execute('SELECT id,cash FROM players WHERE room_id=?', (rid,)).fetchall()
    for p in players:
        holdings = {h['asset']: h['qty'] for h in c.execute('SELECT asset,qty FROM holdings WHERE player_id=?', (p['id'],))}
        orders = c.execute("""SELECT asset,side,qty,COALESCE(filled_day,1) day FROM orders
                              WHERE room_id=? AND player_id=? AND status='filled' ORDER BY id""", (rid, p['id'])).fetchall()
        for aid, a in bonds.items():
            trades = [o for o in orders if o['asset'] == aid]
            # Preserve any legacy starting holdings without an originating order.
            qty = holdings.get(aid, 0) - sum(o['qty'] * (1 if o['side'] == 'buy' else -1) for o in trades)
            for day in range(1, last_closed + 1):
                qty += sum(o['qty'] * (1 if o['side'] == 'buy' else -1) for o in trades if o['day'] == day)
                accrue(c, rid, p['id'], a, day, qty)
    for day in range(INTERVAL, last_closed + 1, INTERVAL):
        pay(c, rid, day, assets, ledger_day=room['day'], migrated=True)
    for p in players:
        cash = c.execute('SELECT cash FROM players WHERE id=?', (p['id'],)).fetchone()[0]
        extra = cash - p['cash'] + summary(c, p['id'])['unpaid']
        c.execute('UPDATE daily_values SET net=net+?,cash=? WHERE player_id=? AND day=?',
                  (extra, cash, p['id'], room['day']))
    c.execute('UPDATE rooms SET bond_interest_version=2 WHERE id=?', (rid,))
