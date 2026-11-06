"""Server-owned clocks advance exactly once, even with no connected browser."""
from concurrent.futures import ThreadPoolExecutor
import threading
import time

from fastapi.testclient import TestClient
import pytest
import server
import classroom_progression as progression
from test_classroom_flow import classroom, advance


def configure(c,teacher,**change):
    s=c.get('/api/state',headers=teacher).json()
    return c.post('/api/admin/progression',headers={**teacher,'X-Haru-Expected-Day':str(s['room']['day'])},json={
        'expected_day':s['room']['day'],'expected_phase':s['room']['phase'],**change})


def current(c,auth):return c.get('/api/state',headers=auth).json()


def test_modes_default_off_and_empty_room_never_counts_as_everyone_ready(classroom):
    c,teacher,learner=classroom
    s=current(c,learner)
    assert not s['progression']['auto_ready'] and not s['progression']['timer_enabled']
    other=c.post('/api/rooms',json={'name':'빈 교실','password':'test1234'}).json()
    auth={'Authorization':'Bearer '+other['token']}
    assert configure(c,auth,auto_ready=True).status_code==200
    for _ in range(3):server.tick_progression()
    assert current(c,auth)['room']['day']==1


def test_everyone_ready_advances_once_and_new_day_starts_unready(classroom):
    c,teacher,first=classroom
    code=current(c,first)['room']['code']
    joined=c.post('/api/join',json={'code':code,'name':'두 번째','pin':'1234'}).json()
    second={'Authorization':'Bearer '+joined['token']}
    assert configure(c,teacher,auto_ready=True).status_code==200
    assert c.post('/api/day/complete',headers={**first,'X-Haru-Expected-Day':'1'}).status_code==200
    assert current(c,first)['room']['day']==1
    result=c.post('/api/day/complete',headers={**second,'X-Haru-Expected-Day':'1'}).json()
    assert result['advanced'] and result['day']==2
    for _ in range(3):server.tick_progression()
    s=current(c,first)
    assert s['room']['day']==2 and not s['player']['day_ready']
    assert current(c,teacher)['ready_count']==0


def test_enabling_after_everyone_is_done_and_concurrent_double_click(classroom):
    c,teacher,learner=classroom
    assert c.post('/api/day/complete',headers=learner).status_code==200
    assert configure(c,teacher,auto_ready=True).json()['progression']['day']==2
    with ThreadPoolExecutor(max_workers=2) as pool:
        statuses=list(pool.map(lambda _:c.post('/api/day/complete',headers={**learner,'X-Haru-Expected-Day':'2'}).status_code,range(2)))
    assert sorted(statuses)==[200,409]
    assert current(c,learner)['room']['day']==3


def test_clock_starts_now_repeats_from_new_open_and_has_no_catch_up_cascade(classroom,monkeypatch):
    c,teacher,learner=classroom
    clock=[1000.0];monkeypatch.setattr(progression.time,'time',lambda:clock[0])
    assert configure(c,teacher,timer_action='start',minutes=2).status_code==200
    rid=current(c,learner)['room']['id']
    p=c.get('/api/progression',headers=learner).json()
    assert p['deadline']==1120 and p['server_time']==1000
    clock[0]=1119;server.tick_progression();assert current(c,learner)['room']['day']==1
    clock[0]=9000
    with ThreadPoolExecutor(max_workers=2) as pool:list(pool.map(lambda _:server.tick_progression(),range(2)))
    s=current(c,learner)
    assert s['room']['day']==2 and s['progression']['deadline']==9120
    assert not s['player']['day_ready']
    with server.conn() as db:
        assert db.execute("SELECT COUNT(*) FROM logs WHERE room_id=? AND event='auto_advance'",(rid,)).fetchone()[0]==1


def test_pause_discussion_restart_stop_and_manual_next_rearm(classroom,monkeypatch):
    c,teacher,learner=classroom
    clock=[1000.0];monkeypatch.setattr(progression.time,'time',lambda:clock[0])
    configure(c,teacher,timer_action='start',minutes=1)
    assert c.post('/api/admin/close',headers=teacher).status_code==200
    clock[0]=2000;server.tick_progression()
    s=current(c,learner)
    assert s['room']['day']==1 and s['room']['phase']=='closed'
    assert s['progression']['timer_enabled'] and s['progression']['deadline'] is None
    assert advance(c,teacher,1,phase='closed').status_code==200
    assert current(c,learner)['progression']['deadline']==2060
    assert configure(c,teacher,timer_action='stop').status_code==200
    clock[0]=5000;server.tick_progression()
    assert current(c,learner)['room']['day']==2
    configure(c,teacher,timer_action='start',minutes=3)
    clock[0]=5010;configure(c,teacher,timer_action='start',minutes=2)
    assert current(c,learner)['progression']['deadline']==5130


def test_earlier_all_ready_restarts_timer_for_new_day(classroom,monkeypatch):
    c,teacher,learner=classroom
    clock=[1000.0];monkeypatch.setattr(progression.time,'time',lambda:clock[0])
    assert configure(c,teacher,auto_ready=True,timer_action='start',minutes=2).status_code==200
    clock[0]=1040
    assert c.post('/api/day/complete',headers={**learner,'X-Haru-Expected-Day':'1'}).status_code==200
    s=current(c,learner)
    assert s['room']['day']==2 and s['progression']['deadline']==1160
    clock[0]=1120;server.tick_progression();assert current(c,learner)['room']['day']==2


def test_expiry_blocks_student_mutations_and_previous_day_requests(classroom,monkeypatch):
    c,teacher,learner=classroom
    clock=[1000.0];monkeypatch.setattr(progression.time,'time',lambda:clock[0])
    configure(c,teacher,timer_action='start',minutes=1)
    assert c.post('/api/deposits',headers=learner,json={'principal':10000,'term':6}).status_code==409
    clock[0]=1060
    for path,body in [('/api/deposits',{'principal':10000,'term':6}),('/api/day/complete',{}),
                      ('/api/orders',{'asset':'HBEL','side':'buy','qty':1,'reason':'늦은 주문'})]:
        assert c.post(path,headers={**learner,'X-Haru-Expected-Day':'1'},json=body).status_code==409
    server.tick_progression()
    assert c.post('/api/deposits',headers={**learner,'X-Haru-Expected-Day':'1'},json={'principal':10000,'term':6}).status_code==409
    assert current(c,learner)['deposits']==[]


def test_restart_preserves_deadline_and_reset_disarms_without_affecting_other_room(classroom):
    c,teacher,learner=classroom
    configure(c,teacher,auto_ready=True,timer_action='start',minutes=3)
    before=c.get('/api/progression',headers=learner).json()
    server.init()
    after=c.get('/api/progression',headers=learner).json()
    assert after['deadline']==before['deadline'] and after['revision']==before['revision']
    other=c.post('/api/rooms',json={'name':'다른 시계','password':'test1234'}).json()
    other_auth={'Authorization':'Bearer '+other['token']}
    configure(c,other_auth,timer_action='start',minutes=5)
    other_clock=current(c,other_auth)['progression']['deadline']
    assert c.post('/api/admin/reset',headers=teacher,json={'confirmation':'초기화','expected_day':1,'expected_generation':0}).status_code==200
    fresh=current(c,learner)
    assert not fresh['progression']['auto_ready'] and not fresh['progression']['timer_enabled']
    assert fresh['progression']['deadline'] is None
    assert current(c,other_auth)['progression']['deadline']==other_clock


def test_final_day_settles_once_and_auto_failure_rolls_back_clock_and_prices(classroom,monkeypatch):
    c,teacher,learner=classroom
    rid=current(c,learner)['room']['id']
    configure(c,teacher,timer_action='start',minutes=1)
    with server.conn() as db:db.execute('UPDATE room_progression SET deadline=1 WHERE room_id=?',(rid,))
    with monkeypatch.context() as patch:
        patch.setattr(server,'generate_prices',lambda *args,**kwargs:(_ for _ in ()).throw(RuntimeError('broken quote')))
        with pytest.raises(RuntimeError,match='broken quote'):server.tick_progression()
    assert current(c,learner)['room']['day']==1
    assert current(c,learner)['room']['phase']=='trading'
    assert current(c,learner)['progression']['deadline']==1
    server.tick_progression();configure(c,teacher,timer_action='stop')
    for day in range(2,24):assert advance(c,teacher,day).status_code==200
    configure(c,teacher,timer_action='start',minutes=1)
    with server.conn() as db:db.execute('UPDATE room_progression SET deadline=1 WHERE room_id=?',(rid,))
    server.tick_progression();server.tick_progression()
    final=current(c,learner)
    assert final['room']['day']==24 and final['room']['phase']=='finished'
    assert not final['progression']['timer_enabled']
    with server.conn() as db:
        assert db.execute("SELECT COUNT(*) FROM logs WHERE room_id=? AND day=24 AND event='close'",(rid,)).fetchone()[0]==1


def test_teacher_only_validated_settings_and_background_task_without_state_polling(classroom):
    c,teacher,learner=classroom
    payload={'expected_day':1,'expected_phase':'trading','timer_action':'start','minutes':1}
    assert c.post('/api/admin/progression',headers=learner,json=payload).status_code==403
    for invalid in (0,121):assert c.post('/api/admin/progression',headers=teacher,json={**payload,'minutes':invalid}).status_code==422
    assert c.post('/api/admin/progression',headers=teacher,json={**payload,'expected_day':2}).status_code==409
    rid=current(c,teacher)['room']['id']
    with TestClient(server.app) as background_client:
        assert background_client.post('/api/admin/progression',headers=teacher,json=payload).status_code==200
        with server.conn() as db:db.execute('UPDATE room_progression SET deadline=1 WHERE room_id=?',(rid,))
        # Read SQLite only: no client poll can be responsible for this transition.
        deadline=time.monotonic()+3
        while time.monotonic()<deadline:
            with server.conn() as db:day=db.execute('SELECT day FROM rooms WHERE id=?',(rid,)).fetchone()[0]
            if day==2:break
            threading.Event().wait(.05)
        assert day==2
