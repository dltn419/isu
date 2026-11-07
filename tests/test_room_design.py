"""Room-owned appearance: migration, shared reads and teacher-only updates."""
import json

import pytest
import server
from test_classroom_flow import classroom, advance


def state(c, auth):
    return c.get('/api/state', headers=auth).json()


def test_creation_default_and_shared_selected_design(classroom):
    c, teacher, learner = classroom
    assert state(c, teacher)['room']['design'] == 'classic'
    room = c.post('/api/rooms', json={
        'name': '신문을 읽는 교실', 'password': 'lesson123', 'design': 'editorial'}).json()
    owner = {'Authorization': 'Bearer ' + room['token']}
    for name in ('첫째', '둘째'):
        joined = c.post('/api/join', json={'code': room['code'], 'name': name, 'pin': '1234'}).json()
        student = {'Authorization': 'Bearer ' + joined['token']}
        assert state(c, student)['room']['design'] == 'editorial'
        assert c.get('/api/progression', headers=student).json()['design'] == 'editorial'
    server.init()
    assert state(c, owner)['room']['design'] == 'editorial'
    assert state(c, learner)['room']['design'] == 'classic'


@pytest.mark.parametrize('design', ['unknown', None, 1])
def test_invalid_design_rejected_on_creation_and_update(classroom, design):
    c, teacher, learner = classroom
    assert c.post('/api/rooms', json={
        'name': '잘못된 디자인', 'password': 'lesson123', 'design': design}).status_code == 422
    assert c.post('/api/admin/design', headers=teacher, json={'design': design}).status_code == 422
    assert state(c, learner)['room']['design'] == 'classic'


def test_teacher_changes_own_room_without_changing_play(classroom):
    c, teacher, learner = classroom
    other = c.post('/api/rooms', json={'name': '다른 교실', 'password': 'lesson123'}).json()
    other_teacher = {'Authorization': 'Bearer ' + other['token']}
    assert c.post('/api/orders', headers=learner, json={
        'asset': 'HBEL', 'side': 'buy', 'qty': 1, 'reason': '사업 전망을 읽었어요'}).status_code == 200
    assert c.post('/api/day/complete', headers=learner).status_code == 200
    before = state(c, learner)
    assert c.post('/api/admin/design', headers=learner, json={'design': 'editorial'}).status_code == 403
    assert c.post('/api/admin/design', headers={**teacher, 'X-Haru-Game-Generation': '1'},
                  json={'design': 'editorial'}).status_code == 409
    assert c.post('/api/admin/design', headers=teacher, json={'design': 'editorial'}).json() == {
        'ok': True, 'design': 'editorial'}
    after = state(c, learner)
    assert after['room']['design'] == 'editorial'
    assert c.get('/api/progression', headers=learner).json()['design'] == 'editorial'
    for key in ('day', 'phase', 'generation', 'mood'):
        assert after['room'][key] == before['room'][key]
    for key in ('player', 'holdings', 'orders', 'deposits'):
        assert after[key] == before[key]
    assert [(a['id'], a['price']) for a in after['assets']] == [(a['id'], a['price']) for a in before['assets']]
    assert state(c, other_teacher)['room']['design'] == 'classic'
    assert c.post('/api/admin/design', headers=teacher, json={'design': 'classic'}).status_code == 200
    assert state(c, learner)['room']['design'] == 'classic'


def test_design_survives_day_changes_and_play_reset(classroom):
    c, teacher, learner = classroom
    assert c.post('/api/admin/design', headers=teacher, json={'design': 'editorial'}).status_code == 200
    assert advance(c, teacher, 1).status_code == 200
    assert state(c, learner)['room']['design'] == 'editorial'
    result = c.post('/api/admin/reset', headers=teacher, json={
        'confirmation': '초기화', 'expected_day': 2, 'expected_generation': 0})
    assert result.status_code == 200, result.text
    current = state(c, learner)
    assert current['room']['day'] == 1 and current['room']['generation'] == 1
    assert current['room']['design'] == 'editorial'
    with server.conn() as db:
        backup = json.loads(db.execute('SELECT snapshot FROM game_reset_backups WHERE id=?',
                                      (result.json()['backup_id'],)).fetchone()[0])
    assert backup['room']['design'] == 'editorial'


def test_old_room_migration_is_idempotent_and_preserves_data(classroom):
    c, teacher, learner = classroom
    before = state(c, learner)
    with server.conn() as db:
        db.execute('ALTER TABLE rooms DROP COLUMN design')
    server.init()
    server.init()
    after = state(c, learner)
    assert after['room']['design'] == 'classic'
    for key in ('player', 'holdings', 'orders', 'deposits'):
        assert after[key] == before[key]
    assert {k: v for k, v in after['room'].items() if k != 'design'} == {
        k: v for k, v in before['room'].items() if k != 'design'}
