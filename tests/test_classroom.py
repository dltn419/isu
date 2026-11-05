"""Lifecycle and isolation checks for the classroom experience."""
import sys
from pathlib import Path
from concurrent.futures import ThreadPoolExecutor

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import pytest
from fastapi.testclient import TestClient
import server


@pytest.fixture
def school(tmp_path, monkeypatch):
    monkeypatch.setattr(server, 'DB', tmp_path / 'school.db')
    server.init()
    client = TestClient(server.app)
    room = client.post('/api/rooms', json={'name': '연구하는 교실', 'password': 'lesson123'}).json()
    teacher = {'Authorization': 'Bearer ' + room['token']}
    student = client.post('/api/join', json={'code': room['code'], 'name': '테스트 학생', 'pin': '1234'}).json()
    learner = {'Authorization': 'Bearer ' + student['token']}
    return client, room, teacher, learner


def advance(client, teacher):
    assert client.post('/api/admin/close', headers=teacher).status_code == 200
    response = client.post('/api/admin/next', headers=teacher)
    assert response.status_code == 200, response.text


def test_full_year_reports_and_fixed_expectations(school):
    c, room, teacher, learner = school
    first = c.get('/api/state', headers=learner).json()
    expected = first['forecasts']
    assert len(first['reports']) == 20
    assert len(first['news']) >= 8
    for day in range(2, 25):
        advance(c, teacher)
        s = c.get('/api/state', headers=learner).json()
        assert s['room']['day'] == day
        assert len(s['assets']) == 32
        assert len(s['reports']) == 20 * (1 + day // 6)
        assert [f for f in s['forecasts'] if f['quarter'] == 1] == expected
        assert all(n['day'] <= day for n in s['news'])
        assert all('impact' not in n for n in s['news'])
        assert all(not {'direction', 'magnitude', 'due_day'} & e.keys() for e in s['events'])
        if day % 6 == 0:
            r = next(x for x in s['reports'] if x['asset'] == 'HBEL' and x['quarter'] == day // 6)
            f = next(x for x in s['forecasts'] if x['asset'] == 'HBEL' and x['quarter'] == day // 6)
            assert (r['expected_revenue'], r['expected_profit']) == (f['revenue'], f['profit'])
            assert r['margin'] == round(r['profit'] / r['revenue'] * 100, 2)
            assert any(n['kind'] == 'earnings' and n['day'] == day for n in s['news'])
    assert c.post('/api/admin/close', headers=teacher).status_code == 200
    assert c.get('/api/state', headers=learner).json()['room']['phase'] == 'finished'
    assert c.post('/api/admin/next', headers=teacher).status_code == 400
    assert c.post('/api/orders', headers=learner, json={'asset': 'HBEL', 'side': 'buy', 'qty': 1, 'reason': '실적 확인'}).status_code == 400


def test_evidence_immediate_trade_ready_and_reflection(school):
    c, room, teacher, learner = school
    s = c.get('/api/state', headers=learner).json()
    news_id = s['news'][1]['id']
    for _ in range(2):
        assert c.post(f'/api/news/{news_id}/read', headers=learner).status_code == 200
    order = {'asset': 'HBEL', 'side': 'buy', 'qty': 2, 'reason': '계약과 이익률을 비교했어요', 'evidence_ids': [news_id]}
    assert c.post('/api/orders', headers=learner, json=order).status_code == 200
    after = c.get('/api/state', headers=learner).json()
    assert after['player']['cash'] == 80000
    assert after['holdings'][0]['qty'] == 2
    assert after['player']['net'] == 100000
    assert after['learning']['read_count'] == 1
    assert after['learning']['evidence_trades'] == 1
    note = c.post('/api/notes', headers=learner, json={'asset': 'HBEL', 'thesis': '실제 납품으로 이어질 것 같다', 'risk': '원가 상승', 'evidence_ids': [news_id]}).json()
    assert note['id']
    assert c.patch(f'/api/notes/{note["id"]}', headers=learner, json={'reflection': '매출뿐 아니라 이익률도 확인해야 한다'}).status_code == 200
    assert c.post('/api/day/complete', headers=learner).status_code == 200
    assert c.post('/api/orders', headers=learner, json=order).status_code == 400
    admin = c.get('/api/state', headers=teacher).json()
    assert admin['all_ready'] is True
    assert admin['participants'][0]['note_count'] == 1
    assert admin['participants'][0]['reflection_count'] == 1
    assert c.post('/api/day/reopen', headers=learner).status_code == 200
    assert c.post('/api/orders', headers=learner, json={**order, 'side': 'sell', 'qty': 1}).status_code == 200


def test_cross_room_isolation_and_teacher_readonly(school):
    c, room, teacher, learner = school
    other = c.post('/api/rooms', json={'name': '다른 교실', 'password': 'another123'}).json()
    other_admin = {'Authorization': 'Bearer ' + other['token']}
    other_news = c.get('/api/state', headers=other_admin).json()['news'][0]['id']
    assert c.post(f'/api/news/{other_news}/read', headers=learner).status_code == 400
    assert c.post('/api/orders', headers=learner, json={'asset': 'HBEL', 'side': 'buy', 'qty': 1, 'reason': '다른 방 기사', 'evidence_ids': [other_news]}).status_code == 400
    assert c.post('/api/admin/next', headers=learner).status_code == 403
    assert c.post('/api/orders', headers=teacher, json={'asset': 'HBEL', 'side': 'buy', 'qty': 1, 'reason': '교사 미리보기'}).status_code == 403
    pid = c.get('/api/state', headers=teacher).json()['participants'][0]['id']
    assert c.get(f'/api/admin/student/{pid}', headers=other_admin).status_code == 404
    assert c.get('/api/state').status_code == 401


def test_concurrent_orders_cannot_overspend(school):
    c, room, teacher, learner = school
    def buy(_):
        return c.post('/api/orders', headers=learner, json={'asset': 'HBEL', 'side': 'buy', 'qty': 8, 'reason': '동시 요청 점검'}).status_code
    with ThreadPoolExecutor(max_workers=2) as pool:
        results = sorted(pool.map(buy, range(2)))
    assert results == [200, 400]
    s = c.get('/api/state', headers=learner).json()
    assert s['player']['cash'] == 20000
    assert s['holdings'][0]['qty'] == 8


def test_restart_preserves_data_and_demo_never_writes_live_rooms(school):
    c, room, teacher, learner = school
    advance(c, teacher)
    before = c.get('/api/state', headers=learner).json()
    server.init()
    after = c.get('/api/state', headers=learner).json()
    assert before == after
    with server.conn() as db:
        count = db.execute('SELECT COUNT(*) FROM rooms').fetchone()[0]
    demo = c.get('/api/demo')
    assert demo.status_code == 200
    assert demo.json()['demo'] is True
    assert len(demo.json()['reports']) == 40
    with server.conn() as db:
        assert db.execute('SELECT COUNT(*) FROM rooms').fetchone()[0] == count
