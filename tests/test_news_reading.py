"""Easy articles preserve numeric evidence, uncertainty and historical knowledge."""
from copy import deepcopy
import pytest
import server
import classroom_engine as engine
import news_reading
from test_classroom_flow import classroom


def test_automatic_titles_are_specific_and_bodies_are_short_without_changing_sources():
    data=deepcopy(server.demo_state())
    original=[{k:v for k,v in n.items() if k!='reading'} for n in data['news']]
    news_reading.enrich(data,engine.COMPANY_PROFILES)
    forecasts=[n for n in data['news'] if n['certainty']=='전망·미확정' and n['metrics']]
    assert len(forecasts)>=20
    for n in forecasts:
        easy=n['reading']
        assert len(easy['body'])<180 and len(easy['body'])<len(n['body'])
        assert len(easy['lines']) in (3,4)
        assert not any(word in easy['title'] for word in ('불확실성 확대','기대 커져','차질 확인','진전 확인'))
        assert '수 있어요' in easy['title'] or '기대돼요' in easy['title']
        assert f"{abs(n['metrics']['revenue_pct']):.1f}%" in easy['body']
        assert f"{abs(n['metrics']['margin_pp']):.2f}원" in easy['body']
        assert str(n['expected_start']) in easy['body'] and str(n['expected_end']) in easy['body']
        if n['metrics'].get('preparation_margin_pp',0)<0:assert '준비 비용' in easy['body']
    assert [{k:v for k,v in n.items() if k!='reading'} for n in data['news']]==original


def test_old_forecast_never_borrows_a_later_outcome_or_private_price_direction():
    data=deepcopy(server.demo_state());old=deepcopy(data['news'])
    for event in data['events']:
        event.update(stage='reversed',result='파산 확정',direction=-1,magnitude=999,due_day=24)
    for article in data['news']:article['impact']=-999
    news_reading.enrich(data,engine.COMPANY_PROFILES)
    for before,after in zip(old,data['news']):
        if before['certainty']=='전망·미확정':assert after['reading']==before['reading']
        assert '파산' not in after['reading']['body']


@pytest.mark.parametrize('margin,word',((1.2,'줄 수 있어요'),(-1.2,'늘 수 있어요')))
def test_cost_headline_uses_profit_direction_and_keeps_won_per_hundred_meaning(margin,word):
    article={'title':'한빛전자, 부품·생산 비용 기대 커져','body':'5일차 전후에 진행 상황을 점검합니다.',
             'sector':'HBEL','day':2,'kind':'company','certainty':'전망·미확정','event_id':1,
             'metrics':{'revenue_pct':2 if margin>0 else -2,'margin_pp':margin,'status':'target'},
             'expected_start':5,'expected_end':8,'horizon':'short'}
    copy=news_reading.reading_copy(article,{'name':'한빛전자','sector':'기술'},
                                  {'kind':'cost','title':engine.COMPANY_PROFILES['HBEL'][2]},engine.COMPANY_PROFILES)
    assert copy['title']=='한빛전자, 부품·생산 비용이 '+word
    assert '100원 팔 때 남는 이익은 1.20원' in copy['lines'][0]


def test_positive_result_can_still_explain_falling_expectations():
    article={'title':'한빛전자, 스마트폰·가전 주문 진전 확인',
             'body':'새로 확인된 수치와 일정은 기존 기대를 낮추는 내용입니다.',
             'sector':'HBEL','day':5,'kind':'followup','certainty':'사실 확인',
             'metrics':{'revenue_pct':2,'margin_pp':.2,'status':'confirmed'},'expected_start':5,'expected_end':8,'horizon':'short'}
    copy=news_reading.reading_copy(article,{'name':'한빛전자'},
                                  {'kind':'sales','title':engine.COMPANY_PROFILES['HBEL'][1]},engine.COMPANY_PROFILES)
    assert copy['title'].endswith('주문이 늘었어요')
    assert '처음 기대보다 사업 전망이 나빠졌어요.' in copy['lines']


def test_signal_and_manual_text_keep_their_original_status():
    signal={'title':'한빛전자, 대형 기술 공급 계약 협상 진전 보도','body':'사업 확대 가능성이 커졌습니다.',
            'sector':'HBEL','day':2,'kind':'signal','is_signal':1,'metrics':{}}
    first=news_reading.reading_copy(signal,{'name':'한빛전자','sector':'기술'},{},engine.COMPANY_PROFILES)
    later=news_reading.reading_copy(signal,{'name':'한빛전자','sector':'기술'},
                                   {'kind':'cost','title':'제품 결함 확정','stage':'confirmed'},engine.COMPANY_PROFILES)
    assert first==later and '논의' in first['title'] and any('반대로' in line for line in first['lines'])
    manual={**signal,'is_signal':0,'kind':'company','title':'선생님이 적은 뉴스','body':'확정이라고 쓰지 않은 원래 문장. '+('긴 글. '*80)}
    copy=news_reading.reading_copy(manual,{}, {},engine.COMPANY_PROFILES)
    assert copy['title']==manual['title'] and copy['lines']==[manual['body']]


def test_reading_is_public_for_both_roles_and_never_rewrites_stored_news(classroom):
    c,teacher,learner=classroom
    with server.conn() as db:before=[tuple(r) for r in db.execute('SELECT * FROM news ORDER BY id')]
    student=c.get('/api/state',headers=learner).json();admin=c.get('/api/state',headers=teacher).json()
    assert student['news']==admin['news'] and all(n.get('reading') for n in student['news'])
    with server.conn() as db:after=[tuple(r) for r in db.execute('SELECT * FROM news ORDER BY id')]
    assert before==after
    assert server.app.title=='24일'
