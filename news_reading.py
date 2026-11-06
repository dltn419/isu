"""Short Korean reading copies, derived only from already published information.

Stored articles, numeric evidence, event outcomes and pricing are never changed.
In particular, a later event result must not rewrite an earlier forecast.
"""
import re


TOPICS = {
    'HBEL': ('휴대폰·반도체 계약','휴대폰·가전 주문','부품·생산 비용','새 반도체 시험','반도체 부품 준비'),
    'NXDV': ('고급 전자기기 판매 계약','새 전자기기 예약','반도체 개발·생산 비용','새 전자기기 시험','화면·반도체 부품 준비'),
    'HBCP': ('전자제품 부품 판매 계약','전자회사 부품 주문','부품 생산·검사 비용','새 카메라 부품 시험','부품 재료 준비'),
    'SCNT': ('회사 보안 서비스 계약','보안 서비스 가입','서버·직원 운영 비용','해킹 탐지 기술 시험','고객사 보안 장비 준비'),
    'NURA': ('출장·항공화물 운송 계약','국제선 예약','연료·정비 비용','연료 절약 기술 시험','비행기 부품 준비'),
    'LTAI': ('여행사·항공 노선 계약','가까운 나라 항공권 예약','연료·공항 사용 비용','예약·운항 기술 시험','운항용 비행기 준비'),
    'NUTS': ('비행기 정비 계약','비행기 점검·수리 예약','정비 직원·장비 비용','비행기 고장 예측 시험','정비용 부품 준비'),
    'ARLG': ('해외 배송 계약','해외 배송 주문','배송·창고 운영 비용','화물 자동 분류 시험','배송 장비 준비'),
    'DDFF': ('라면·냉동식품 판매 계약','가공식품 주문','밀가루·포장 비용','새 식품 소비자 평가','식품 원료 준비'),
    'GRTB': ('건강식 매장 판매 계약','건강 간편식 주문','식재료·냉장 배송 비용','새 건강식 소비자 평가','식재료 준비'),
    'SWWV': ('디저트 판매 계약','디저트·음료 주문','설탕·우유 재료 비용','새 메뉴 소비자 평가','디저트 재료 준비'),
    'FMBR': ('농산물 판매 계약','농산물 주문','농산물 보관·배송 비용','농산물 신선도 유지 시험','농산물 수확·배송 준비'),
    'MDON': ('의약품 판매 계약','의약품 주문','의약품 생산·관리 비용','의약품 제조 개선 시험','의약품 원료 준비'),
    'NFBI': ('새 약 공동 연구 계약','새 약 기술을 사려는 회사','새 약 시험·연구 비용','새 약의 효과·안전성 시험','새 약 시험 재료 준비'),
    'MDBW': ('의약품 대신 생산하는 계약','의약품 생산 주문','의약품 공장 운영 비용','의약품 생산 방법 시험','공장 재료·장비 준비'),
    'CLMD': ('병원 검사장비 판매 계약','병원 검사장비 주문','검사장비 생산·관리 비용','새 검사장비 정확도 시험','검사 재료·부품 준비'),
    'BRCL': ('AI·인터넷 저장공간 서비스 계약','인터넷 저장공간 서비스 이용','서버 전기·운영 비용','기업용 AI 기술 시험','서버 장비 준비'),
    'MORB': ('창고 로봇 판매 계약','산업용 로봇 주문','로봇 부품·조립 비용','새 로봇 성능 시험','로봇 부품 준비'),
    'PWGR': ('전력 장비 판매 계약','전력 장비 주문','전력 장비 생산 비용','전기 저장장치 안전성 시험','전력 장비 재료 준비'),
    'COED': ('서버 냉각장비 판매 계약','전기 절약 냉각장비 주문','냉각장비 제작·설치 비용','새 냉각장비 성능 시험','냉각장비 부품 준비'),
}
KINDS=('contract','sales','cost','research','supply')
SIGNALS={
    '기술':('큰 기술 계약을 논의하고 있어요','주요 제품에 문제가 있는지 살펴보고 있어요'),
    '항공':('큰 운송 계약을 논의하고 있어요','추가 점검으로 비행이 늦어질 수 있어요'),
    '식품':('대형 매장에 제품을 팔 계약을 논의해요','주요 식품에 문제가 있는지 살펴보고 있어요'),
    '의료·제약':('새 약 연구에서 좋은 결과가 기대돼요','새 약 시험에 추가 확인이 필요해요'),
    '미래사업':('큰 장비 계약을 논의하고 있어요','주요 장비에 문제가 있는지 살펴보고 있어요'),
}
BREAKING={
    '초대형 기술 공급 계약 최종 체결':'아주 큰 기술 계약을 맺었어요',
    '핵심 제품 결함과 대규모 추가 비용 확인':'주요 제품에서 문제가 나와 큰 비용이 들어요',
    '대형 국제 운송 계약 최종 체결':'아주 큰 해외 운송 계약을 맺었어요',
    '주요 운항·정비 차질 긴급 확인':'비행·정비에 큰 문제가 생겼어요',
    '전국 유통망 초대형 공급 계약 체결':'전국 매장에 제품을 팔 큰 계약을 맺었어요',
    '주력 제품 판매 중단·회수 확인':'주요 제품 판매를 멈추고 거둬들여요',
    '핵심 연구 성공과 대형 기술 계약 확정':'주요 연구가 성공하고 큰 기술 계약을 맺었어요',
    '핵심 연구 중단과 추가 비용 확정':'주요 연구를 멈추고 비용도 더 들어요',
    '초대형 설비 공급 계약 최종 체결':'아주 큰 장비 판매 계약을 맺었어요',
    '핵심 설비 결함·납품 중단 확인':'주요 장비에 문제가 나와 판매를 멈춰요',
    '대형 기술 공급 계약 협상 결렬':'기대했던 큰 기술 계약이 무산됐어요',
    '대형 운송 계약 협상 결렬':'기대했던 큰 운송 계약이 무산됐어요',
    '전국 유통망 공급 협상 결렬':'전국 매장 판매 계약이 무산됐어요',
    '핵심 연구 최종 검증 차질 확인':'주요 연구의 마지막 시험에서 문제가 나왔어요',
    '초대형 설비 계약 협상 결렬':'기대했던 큰 장비 계약이 무산됐어요',
    '제품 추가 점검 통과·공급 차질 우려 해소':'제품 점검을 통과해 공급 걱정이 줄었어요',
    '정비 점검 통과·운항 정상화 확인':'정비 점검을 통과해 비행이 정상으로 돌아와요',
    '품질 점검 통과·판매 중단 우려 해소':'식품 점검을 통과해 판매 중단 걱정이 줄었어요',
    '추가 검증 통과·연구 재개 확인':'추가 시험을 통과해 연구를 다시 시작해요',
    '설비 검수 통과·납품 정상화 확인':'장비 점검을 통과해 제품을 다시 전달해요',
}


def subject(word):
    last=ord(word[-1])-0xAC00
    return word+('이' if 0<=last<11172 and last%28 else '가')


def metric_line(metrics,confirmed=False):
    rev,margin=metrics['revenue_pct'],metrics['margin_pp']
    r=f'{abs(rev):.1f}% '+('늘고' if rev>0 else '줄고' if rev<0 else '그대로이고')
    p=f'{abs(margin):.2f}원 '+('늘어나는' if margin>0 else '줄어드는' if margin<0 else '그대로인')
    return f'사업이 자리 잡으면 매출은 {r}, 100원 팔 때 남는 이익은 {p} '+('효과예요.' if confirmed else '것으로 예상해요.')


def period(n):
    start,end=n.get('expected_start'),n.get('expected_end')
    if start is None:return ''
    label={'year_end':'연말','next_quarter':'다음 분기','short':'단기'}.get(n.get('horizon'),'단기')
    return f'사업 영향: {start}~{end or start}일차({label}).'


def headline(name,topic,kind,positive,confirmed):
    if kind=='research':
        action=('좋은 결과가 나왔어요' if positive else '문제가 나왔어요') if confirmed else ('좋은 결과가 기대돼요' if positive else '문제가 나올 수 있어요')
        return f'{name}, {topic}에서 {action}'
    actions={
        'contract':(('성사됐어요','어려워졌어요'),('성사될 수 있어요','어려워질 수 있어요')),
        'sales':(('늘었어요','줄었어요'),('늘 수 있어요','줄 수 있어요')),
        'cost':(('줄었어요','늘었어요'),('줄 수 있어요','늘 수 있어요')),
        'supply':(('잘됐어요','늦어졌어요'),('잘될 수 있어요','늦어질 수 있어요')),
    }
    return f'{name}, {subject(topic)} {actions[kind][0 if confirmed else 1][0 if positive else 1]}'


def reading_copy(n,asset,event,profiles):
    title,body=n['title'],n['body'];metrics=n.get('metrics') or {}
    name=asset.get('name',n['sector']);sector=asset.get('sector',n['sector'])
    if n.get('is_signal'):
        positive='사업 확대 가능성' in body
        text=SIGNALS.get(sector,('새 계약을 논의하고 있어요','사업에 문제가 있는지 살펴보고 있어요'))[0 if positive else 1]
        return {'title':f'{name}, {text}','lines':['아직 확인 중인 소식이에요.','가까운 시일의 후속 발표를 살펴보세요.','처음 예상과 반대로 결론 날 수도 있어요.']}
    if n.get('is_breaking'):
        original=title.split(', ',1)[-1]
        lines=['이 소식은 오늘 시작 가격에 이미 반영됐어요.']
        if metrics:lines.append(metric_line(metrics,True))
        if '당초 단서와 반대' in body:lines.append('앞서 나온 예상과 반대 결과예요.')
        lines.append(period(n))
        return {'title':f'{name}, {BREAKING.get(original,original)}','lines':lines}
    if n['kind']=='earnings':
        return {'title':title.replace('실적 발표 · 20개 기업 성적표 공개','회사 20곳의 성적표가 나왔어요'),
                'lines':['회사가 번 돈과 남긴 이익을 확인해요.','발표 전 예상보다 잘했는지도 비교해 보세요.','실적에 대한 반응은 오늘 가격에 반영됐어요.']}
    if n['kind']=='sector':
        action='주문이 늘 수 있어요' if '수요 회복' in title else '주문이 줄 수 있어요' if '수요 둔화' in title else '회사마다 상황이 달라요'
        return {'title':f'{n["sector"]} 업종, {action}',
                'lines':['같은 종류의 사업을 하는 회사들의 소식이에요.','회사마다 비용과 계약이 다르니 따로 살펴보세요.']}
    kind=event.get('kind')
    if n['day']==24 and n.get('certainty')=='운영 현황':
        return {'title':f'{name}, 올해 사업을 마쳤어요','lines':['올해 영업은 끝났어요.','오늘 발표한 회사 성적표를 확인해요.']}
    if not metrics or kind not in KINDS:
        # Teacher-authored text and unrecognised historical articles are not invented or cut.
        return {'title':title,'lines':[body]}
    source_topic=event.get('title','')
    topics=profiles.get(n['sector'],())
    if not topics:return {'title':title,'lines':[body]}
    if source_topic and source_topic not in topics:
        return {'title':title,'lines':[body]}
    topic=TOPICS.get(n['sector'],topics)[KINDS.index(kind)] if topics else source_topic
    status=metrics.get('status');confirmed=status in ('confirmed','operating')
    positive=(metrics['margin_pp']>=0) if kind=='cost' else metrics['revenue_pct']>=0
    if status=='unchanged':
        return {'title':f'{name}, {topic} 계속 준비 중','lines':['처음 알린 숫자와 일정은 그대로예요.','아직 결과가 나온 것은 아니에요.',period(n)]}
    if status=='delayed':
        return {'title':f'{name}, {topic} 확인이 늦어졌어요',
                'lines':[f'{n["expected_start"]}일차 전후에 결과를 다시 확인해요.','준비에 시간이 더 필요해요.',period(n)]}
    lines=[metric_line(metrics,confirmed)]
    if confirmed:
        comparison=('처음 기대보다 사업 전망이 좋아졌어요.' if '기존 기대를 높이는' in body else
                    '처음 기대보다 사업 전망이 나빠졌어요.' if '기존 기대를 낮추는' in body else
                    '처음 기대와 큰 차이가 없어요.' if '기존 기대와 큰 차이가 없' in body else
                    '이전 기사와 이번 숫자를 비교해 보세요.')
        lines.append(comparison)
    else:
        check=re.search(r'(\d+)일차 전후에 진행 상황을 점검',body)
        lines.append(f'{check[1]}일차 전후에 진행 상황을 확인해요.' if check else '아직 예상이어서 결과는 달라질 수 있어요.')
    if metrics.get('preparation_margin_pp',0)<0:lines.append('준비 비용이 먼저 들어요.')
    if period(n):lines.append(period(n))
    if n['day']==24:lines=['올해 영업은 끝났어요. 오늘 발표한 성적표를 확인해요.']
    return {'title':headline(name,topic,kind,positive,confirmed),'lines':lines}


def enrich(data,profiles):
    """Use the public article snapshot; never look at a future draw or current outcome."""
    assets={a['id']:a for a in data['assets']};events={e['id']:e for e in data.get('events',[])}
    for article in data['news']:
        copy=reading_copy(article,assets.get(article['sector'],{}),events.get(article.get('event_id'),{}),profiles)
        copy['lines']=[line for line in copy['lines'] if line]
        copy['body']='\n'.join(copy['lines'])
        copy['summary']=' '.join(copy['lines'][:2])
        article['reading']=copy
