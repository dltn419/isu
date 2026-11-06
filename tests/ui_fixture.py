"""Create isolated UI fixtures: python tests/ui_fixture.py /tmp/ui-fixture.json."""
import json
import os
from pathlib import Path
import sys
import tempfile


def main(output):
    sys.path[:0]=[str(Path(__file__).resolve().parents[1]),str(Path(__file__).resolve().parent)]
    with tempfile.TemporaryDirectory(prefix='24days-ui-') as directory:
        os.environ['HARU_DB']=str(Path(directory)/'ui.db')
        from fastapi.testclient import TestClient
        import server
        from test_breaking_news import force_plan
        c=TestClient(server.app)

        def new(name):
            room=c.post('/api/rooms',json={'name':name,'password':'test1234'}).json()
            teacher={'Authorization':'Bearer '+room['token']}
            joined=c.post('/api/join',json={'code':room['code'],'name':'연구 학생','pin':'1234'}).json()
            return teacher,{'Authorization':'Bearer '+joined['token']},room['code']

        def advance(teacher,day):
            result=c.post('/api/admin/advance',headers=teacher,json={'expected_day':day,'expected_phase':'trading'})
            assert result.status_code==200,result.text

        def buy(student,asset,qty):
            result=c.post('/api/orders',headers=student,json={'asset':asset,'side':'buy','qty':qty,'reason':'뉴스와 다음 실적을 비교해 보겠다'})
            assert result.status_code==200,result.text

        teacher,student,code=new('뉴스로 보는 우리 반')
        for name in ('수익 비교 가','수익 비교 나'):c.post('/api/join',json={'code':code,'name':name,'pin':'1234'})
        buy(student,'HBEL',2)
        for day in range(1,6):advance(teacher,day)
        fixture={'student':c.get('/api/state',headers=student).json(),'teacher':c.get('/api/state',headers=teacher).json(),
                 'history':c.get('/api/history/HBEL',headers=student).json(),'demo':c.get('/api/demo').json()}
        pid=fixture['student']['player']['id']
        fixture['preview']=c.get('/api/admin/student/'+str(pid),headers=teacher).json()
        teacher,student,_=new('채권 이자 확인');buy(student,'GOV',1)
        for day in range(1,6):advance(teacher,day)
        fixture['bond_student']=c.get('/api/state',headers=student).json()
        teacher,student,_=new('속보와 취재 단서');force_plan(c,teacher,(4,))
        for day in (1,2):advance(teacher,day)
        fixture['clue_student']=c.get('/api/state',headers=student).json()
        advance(teacher,3);fixture['breaking_student']=c.get('/api/state',headers=student).json()
        Path(output).write_text(json.dumps(fixture,ensure_ascii=False))
        print('Created eight isolated UI fixtures.')


if __name__=='__main__':main(sys.argv[1])
