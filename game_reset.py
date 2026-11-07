"""Room-scoped new games, archived play data and idempotent operator requests."""
import json
import secrets
import uuid

import classroom_engine as engine
import breaking_news


ROOM_TABLES = (
    'final_settlements',
    'room_progression',
    'breaking_cases',
    'breaking_releases', 'breaking_plans',
    'bond_accruals', 'bond_payments',
    'reading_log', 'investment_notes', 'day_ready', 'daily_values',
    'orders', 'deposits', 'ledgers', 'news', 'logs', 'prices',
    'event_expectations', 'market_estimates', 'operating_effects',
    'business_daily', 'business_events', 'financials', 'forecasts', 'businesses',
)
PLAYER_TABLES = ('holdings', 'watchlist')


def initialize(c):
    if 'generation' not in {r[1] for r in c.execute('PRAGMA table_info(rooms)')}:
        c.execute('ALTER TABLE rooms ADD COLUMN generation INTEGER NOT NULL DEFAULT 0')
    c.execute('''CREATE TABLE IF NOT EXISTS game_reset_backups(
        id TEXT PRIMARY KEY, room_id INTEGER NOT NULL, created TEXT NOT NULL,
        from_day INTEGER NOT NULL, snapshot TEXT NOT NULL)''')
    c.execute('CREATE INDEX IF NOT EXISTS idx_reset_backups_room ON game_reset_backups(room_id,created)')
    c.execute('''CREATE TABLE IF NOT EXISTS maintenance_runs(
        id TEXT PRIMARY KEY, created TEXT NOT NULL, result TEXT NOT NULL)''')


def collect_snapshot(c, room):
    rid = room['id']
    snapshot = {
        'format': 'haru-play-backup-v1',
        'room': {k: room[k] for k in ('id', 'name', 'code', 'day', 'phase', 'start_cash', 'seed', 'mood', 'generation', 'bond_interest_version', 'design')},
        'players': [dict(r) for r in c.execute('SELECT id,name,cash FROM players WHERE room_id=?', (rid,))],
        'tables': {},
    }
    for table in ROOM_TABLES:
        snapshot['tables'][table] = [dict(r) for r in c.execute(f'SELECT * FROM {table} WHERE room_id=?', (rid,))]
    for table in PLAYER_TABLES:
        snapshot['tables'][table] = [dict(r) for r in c.execute(
            f'SELECT * FROM {table} WHERE player_id IN (SELECT id FROM players WHERE room_id=?)', (rid,))]
    return snapshot


def reset_room(c, room, assets, timestamp):
    """Caller holds BEGIN IMMEDIATE; all deletion and generation are one commit."""
    rid = room['id']
    backup_id = uuid.uuid4().hex
    snapshot = collect_snapshot(c, room)
    c.execute('INSERT INTO game_reset_backups VALUES(?,?,?,?,?)',
              (backup_id, rid, timestamp, room['day'], json.dumps(snapshot, ensure_ascii=False)))
    for table in PLAYER_TABLES:
        c.execute(f'DELETE FROM {table} WHERE player_id IN (SELECT id FROM players WHERE room_id=?)', (rid,))
    for table in ROOM_TABLES:
        c.execute(f'DELETE FROM {table} WHERE room_id=?', (rid,))
    c.execute('INSERT INTO room_progression(room_id) VALUES(?)',(rid,))
    seed = secrets.randbelow(1000000000)
    if seed == room['seed']:
        seed = (seed + 1) % 1000000000
    generation = room['generation'] + 1
    c.execute("UPDATE rooms SET day=1,phase='trading',mood='neutral',seed=?,generation=?,bond_interest_version=2 WHERE id=?",
              (seed, generation, rid))
    c.execute('UPDATE players SET cash=? WHERE room_id=?', (room['start_cash'], rid))
    c.executemany('INSERT INTO prices(room_id,day,asset,price,change) VALUES(?,1,?,?,0)',
                  [(rid, a['id'], a['initial']) for a in assets])
    engine.publish_news(c, rid, 1, seed, 'neutral', assets)
    breaking_news.ensure_plan(c,rid,seed)
    breaking_news.publish_clues(c,rid,1,seed,'neutral',assets)
    c.execute('''INSERT INTO daily_values(room_id,player_id,day,net,cash)
                 SELECT room_id,id,1,cash,cash FROM players WHERE room_id=?''', (rid,))
    c.execute('INSERT INTO logs(room_id,day,event,detail) VALUES(?,1,?,?)',
              (rid, 'reset', f"{room['day']}일차 플레이를 백업하고 1일차 새 게임 시작 · 학생 계정 유지"))
    return {'ok': True, 'day': 1, 'phase': 'trading', 'generation': generation,
            'backup_id': backup_id, 'players_preserved': len(snapshot['players'])}


def apply_operator_request(c, request_id, room_code, assets, timestamp):
    """An explicit server-operator request; never guess among multiple rooms."""
    previous = c.execute('SELECT result FROM maintenance_runs WHERE id=?', (request_id,)).fetchone()
    if previous:
        result = json.loads(previous['result'])
        if result['status'] in ('reset', 'no_rooms'):
            return {**result, 'already_applied': True}
    rooms = c.execute('SELECT * FROM rooms ORDER BY id').fetchall()
    selected = [r for r in rooms if r['code'] == room_code] if room_code else rooms
    if not rooms:
        result = {'status': 'no_rooms', 'request_id': request_id}
    elif len(selected) != 1:
        result = {'status': 'needs_room_code', 'request_id': request_id,
                  'rooms': [{'id': r['id'], 'name': r['name'], 'code': r['code'], 'day': r['day']} for r in rooms]}
    else:
        room = selected[0]
        reset = reset_room(c, room, assets, timestamp)
        result = {'status': 'reset', 'request_id': request_id, 'room_id': room['id'],
                  'room_code': room['code'], **reset}
    c.execute('INSERT OR REPLACE INTO maintenance_runs VALUES(?,?,?)',
              (request_id, timestamp, json.dumps(result, ensure_ascii=False)))
    return result
