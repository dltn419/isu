"""Persistent classroom clocks; mutations share the game's transaction."""
import time


def initialize(c):
    c.execute('''CREATE TABLE IF NOT EXISTS room_progression(
      room_id INTEGER PRIMARY KEY,auto_ready INTEGER NOT NULL DEFAULT 0,
      timer_enabled INTEGER NOT NULL DEFAULT 0,timer_seconds INTEGER NOT NULL DEFAULT 180,
      deadline REAL,revision INTEGER NOT NULL DEFAULT 0)''')
    c.execute('INSERT OR IGNORE INTO room_progression(room_id) SELECT id FROM rooms')


def config(c,rid):
    row=c.execute('SELECT * FROM room_progression WHERE room_id=?',(rid,)).fetchone()
    return dict(row) if row else {'room_id':rid,'auto_ready':0,'timer_enabled':0,
                                'timer_seconds':180,'deadline':None,'revision':0}


def snapshot(c,room,at=None):
    settings=config(c,room['id'])
    return {key:settings[key] for key in ('auto_ready','timer_enabled','timer_seconds','deadline','revision')} | {
        'day':room['day'],'phase':room['phase'],'generation':room['generation'],
        'server_time':(time.time() if at is None else at) if settings['timer_enabled'] else None}


def configure(c,rid,*,auto_ready=None,action=None,minutes=None,at=None):
    c.execute('INSERT OR IGNORE INTO room_progression(room_id) VALUES(?)',(rid,))
    if auto_ready is not None:
        c.execute('UPDATE room_progression SET auto_ready=?,revision=revision+1 WHERE room_id=?',
                  (int(auto_ready),rid))
    if action=='start':
        seconds=minutes*60
        c.execute('''UPDATE room_progression SET timer_enabled=1,timer_seconds=?,deadline=?,
                     revision=revision+1 WHERE room_id=?''',(seconds,(time.time() if at is None else at)+seconds,rid))
    elif action=='stop':
        c.execute('UPDATE room_progression SET timer_enabled=0,deadline=NULL,revision=revision+1 WHERE room_id=?',(rid,))


def pause(c,rid,finished=False):
    c.execute('''UPDATE room_progression SET deadline=NULL,timer_enabled=CASE WHEN ? THEN 0 ELSE timer_enabled END,
                 revision=revision+1 WHERE room_id=?''',(int(finished),rid))


def start_day(c,rid,at=None):
    # Start from the real new opening, not an old overdue deadline (no catch-up cascade).
    c.execute('''UPDATE room_progression SET deadline=CASE WHEN timer_enabled=1 THEN ?+timer_seconds ELSE NULL END,
                 revision=revision+1 WHERE room_id=?''',(time.time() if at is None else at,rid))


def expired(c,rid,at=None):
    settings=config(c,rid)
    return bool(settings['timer_enabled'] and settings['deadline'] is not None
                and settings['deadline']<=(time.time() if at is None else at))


def maybe_advance(c,room,advance,at=None):
    if room['phase']!='trading':return None
    settings=config(c,room['id']);reason=None
    if expired(c,room['id'],at):reason='timer'
    elif settings['auto_ready']:
        count=c.execute('''SELECT COUNT(*) total,SUM(EXISTS(SELECT 1 FROM day_ready d
                         WHERE d.player_id=p.id AND d.room_id=p.room_id AND d.day=?)) ready
                         FROM players p WHERE p.room_id=?''',(room['day'],room['id'])).fetchone()
        if count['total']>0 and count['ready']==count['total']:reason='all_ready'
    return advance(c,room,reason) if reason else None
