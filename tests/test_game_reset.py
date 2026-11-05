"""Room isolation, atomic reset, retained accounts and stale-client protection."""
import json
from concurrent.futures import ThreadPoolExecutor

import pytest
from fastapi.testclient import TestClient

import server
import game_reset


@pytest.fixture
def game(tmp_path, monkeypatch):
    monkeypatch.setattr(server, 'DB', tmp_path / 'reset.db')
    server.init()
    c = TestClient(server.app)
    room = c.post('/api/rooms', json={'name':'초기화 검증 교실','password':'teacher123'}).json()
    teacher = {'Authorization':'Bearer '+room['token']}
    student = c.post('/api/join', json={'code':room['code'],'name':'학생','pin':'1234'}).json()
    learner = {'Authorization':'Bearer '+student['token']}
    return c, room, teacher, learner


def reset(c, teacher, day, generation=0, confirmation='초기화'):
    return c.post('/api/admin/reset', headers={**teacher,'X-Haru-Game-Generation':str(generation)},
                  json={'confirmation':confirmation,'expected_day':day,'expected_generation':generation})


def populate(c, teacher, learner):
    state = c.get('/api/state', headers=learner).json()
    nid = state['news'][0]['id']
    assert c.post('/api/orders', headers=learner, json={
        'asset':'HBEL','side':'buy','qty':2,'reason':'계약과 이익을 확인한다','evidence_ids':[nid]}).status_code == 200
    assert c.post('/api/deposits', headers=learner, json={'term':12,'principal':10000}).status_code == 200
    assert c.post('/api/watchlist', headers=learner, json={'asset':'HBEL'}).status_code == 200
    assert c.post(f'/api/news/{nid}/read', headers=learner).status_code == 200
    for day in range(1,6):
        assert c.post('/api/admin/advance', headers=teacher,
                      json={'expected_day':day,'expected_phase':'trading'}).status_code == 200
    assert c.post('/api/day/complete', headers=learner).status_code == 200


def test_reset_starts_a_consistent_new_year_and_keeps_accounts(game):
    c, room, teacher, learner = game
    populate(c,teacher,learner)
    with server.conn() as db:
        before_room = dict(db.execute('SELECT * FROM rooms').fetchone())
        before_player = dict(db.execute('SELECT * FROM players').fetchone())
    assert reset(c,teacher,6,confirmation='확인').status_code == 400
    result = reset(c,teacher,6)
    assert result.status_code == 200, result.text
    assert result.json()['players_preserved'] == 1
    state = c.get('/api/state', headers=learner).json()
    assert state['room']['day'] == 1
    assert state['room']['generation'] == 1
    assert state['room']['phase'] == 'trading'
    assert state['room']['mood'] == 'neutral'
    assert state['room']['code'] == room['code']
    assert state['player']['cash'] == state['player']['net'] == 100000
    assert state['player']['profit'] == state['player']['fees_paid'] == 0
    assert state['player']['day_ready'] is False
    for key in ['holdings','orders','deposits','ledger','notes','watchlist','read_ids']:
        assert state[key] == [], key
    assert all(a['price'] == a['initial'] for a in state['assets'])
    assert len(state['reports']) == 20
    assert all(r['quarter'] == 0 for r in state['reports'])
    assert all(n['day'] == 1 for n in state['news'])
    assert state['values'] == [{'day':1,'net':100000,'cash':100000}]
    with server.conn() as db:
        after_room = dict(db.execute('SELECT * FROM rooms').fetchone())
        after_player = dict(db.execute('SELECT * FROM players').fetchone())
    assert before_room['admin_hash'] == after_room['admin_hash']
    assert before_room['seed'] != after_room['seed']
    assert before_player['pin_hash'] == after_player['pin_hash']
    assert before_player['id'] == after_player['id']
    assert c.post('/api/admin/login', json={'code':room['code'],'password':'teacher123'}).status_code == 200
    assert c.post('/api/join', json={'code':room['code'],'name':'학생','pin':'1234'}).status_code == 200
    backup = c.get('/api/admin/reset-backup', headers=teacher)
    assert backup.status_code == 200
    data = backup.json()
    assert data['room']['day'] == 6
    assert len(data['tables']['orders']) == 1
    assert len(data['tables']['deposits']) == 1
    assert len(data['tables']['investment_notes']) == 1
    assert not any(word in backup.text for word in ['pin_hash','admin_hash','token_hash'])
    assert c.get('/api/admin/reset-backup', headers=learner).status_code == 403


def test_reset_does_not_touch_another_room_and_rejects_students(game):
    c, room, teacher, learner = game
    other = c.post('/api/rooms', json={'name':'보존할 교실','password':'other123'}).json()
    other_teacher = {'Authorization':'Bearer '+other['token']}
    before = c.get('/api/state', headers=other_teacher).json()
    assert reset(c,learner,1).status_code == 403
    assert reset(c,teacher,1).status_code == 200
    assert c.get('/api/state', headers=other_teacher).json() == before
    assert c.get('/api/admin/reset-backup', headers=other_teacher).status_code == 404


def test_old_tabs_cannot_trade_or_advance_the_new_game(game):
    c, room, teacher, learner = game
    assert reset(c,teacher,1).status_code == 200
    fresh = c.get('/api/state', headers=learner).json()
    pid = fresh['player']['id']
    for auth,path,body in [
        (learner,'/api/orders',{'asset':'HBEL','side':'buy','qty':1,'reason':'이전 게임의 주문'}),
        (learner,'/api/deposits',{'term':6,'principal':1000}),
        (learner,'/api/day/complete',{}),
        (learner,'/api/notes',{'asset':'HBEL','thesis':'이전 게임의 판단'}),
        (learner,'/api/watchlist',{'asset':'HBEL'}),
        (teacher,'/api/admin/advance',{'expected_day':1,'expected_phase':'trading'}),
        (teacher,'/api/admin/cash',{'player_id':pid,'amount':500,'reason':'예전 조정 요청'}),
        (teacher,'/api/admin/mood',{'mood':'positive'}),
    ]:
        assert c.post(path, headers={**auth,'X-Haru-Game-Generation':'0'}, json=body).status_code == 409, path
    assert c.post('/api/day/complete', headers=learner).status_code == 409
    assert c.get('/api/state', headers=learner).json() == fresh
    new_auth = {**learner,'X-Haru-Game-Generation':'1'}
    assert c.post('/api/orders', headers=new_auth, json={
        'asset':'HBEL','side':'buy','qty':1,'reason':'새 게임에서 확인한 판단'}).status_code == 200
    assert c.get('/api/state', headers=learner).json()['player']['cash'] == 89998


def test_reset_failure_rolls_back_every_table_and_backup(game, monkeypatch):
    c, room, teacher, learner = game
    populate(c,teacher,learner)
    before = c.get('/api/state', headers=learner).json()
    def fail(*args):
        raise RuntimeError('simulated new-game failure')
    monkeypatch.setattr(server.engine,'publish_news',fail)
    with pytest.raises(RuntimeError,match='simulated new-game failure'):
        reset(c,teacher,6)
    assert c.get('/api/state', headers=learner).json() == before
    assert c.get('/api/admin/reset-backup', headers=teacher).status_code == 404


def test_concurrent_resets_do_not_create_two_new_games(game):
    c, room, teacher, learner = game
    with ThreadPoolExecutor(max_workers=2) as pool:
        statuses = sorted(pool.map(lambda _:reset(c,teacher,1).status_code,range(2)))
    assert statuses == [200,409]
    assert c.get('/api/state', headers=learner).json()['room']['generation'] == 1
    with server.conn() as db:
        assert db.execute('SELECT COUNT(*) FROM game_reset_backups').fetchone()[0] == 1


def test_operator_reset_is_applied_once_even_after_game_progresses(game):
    c, room, teacher, learner = game
    with server.conn() as db:
        db.execute('BEGIN IMMEDIATE')
        result = game_reset.apply_operator_request(db,'reset-once-test','',server.ASSETS,server.now())
    assert result['status'] == 'reset'
    auth = {**teacher,'X-Haru-Game-Generation':'1'}
    assert c.post('/api/admin/advance', headers=auth,
                  json={'expected_day':1,'expected_phase':'trading'}).status_code == 200
    with server.conn() as db:
        db.execute('BEGIN IMMEDIATE')
        again = game_reset.apply_operator_request(db,'reset-once-test','',server.ASSETS,server.now())
    assert again['already_applied'] is True
    assert c.get('/api/state', headers=learner).json()['room']['day'] == 2


def test_operator_does_not_guess_between_multiple_rooms(game):
    c, room, teacher, learner = game
    other = c.post('/api/rooms', json={'name':'다른 교실','password':'another123'}).json()
    with server.conn() as db:
        db.execute('BEGIN IMMEDIATE')
        blocked = game_reset.apply_operator_request(db,'choose-room-test','',server.ASSETS,server.now())
    assert blocked['status'] == 'needs_room_code'
    assert len(blocked['rooms']) == 2
    assert c.get('/api/state', headers=learner).json()['room']['generation'] == 0
    with server.conn() as db:
        db.execute('BEGIN IMMEDIATE')
        done = game_reset.apply_operator_request(db,'choose-room-test',room['code'],server.ASSETS,server.now())
    assert done['status'] == 'reset'
    assert c.get('/api/state', headers=learner).json()['room']['generation'] == 1
    other_auth = {'Authorization':'Bearer '+other['token']}
    assert c.get('/api/state', headers=other_auth).json()['room']['generation'] == 0
