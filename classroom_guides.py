"""NPC guides built solely from the same public evidence students can inspect."""
import json


def metrics_of(article):
    value = article.get('metrics') or {}
    return json.loads(value) if isinstance(value,str) else value


def summarize(article, names):
    m = metrics_of(article)
    name = names.get(article['sector'],article['sector'])
    if m:
        status = m.get('status')
        if status == 'unchanged':
            return f'{name}의 준비가 이어지고 있어요. 전망 수치와 일정은 그대로이며, 새 영업 성과는 아직 확인되지 않았어요.'
        if status == 'delayed':
            return f'{name}의 확인 일정이 {article.get("expected_start")}일차로 늦어졌어요. 매출 반영 시점과 준비 비용을 다시 살펴보세요.'
        result = '확인된 영업 효과' if status in ('confirmed','operating') else '회사가 제시한 전망'
        topic = '는' if status in ('confirmed','operating') else '은'
        period = f'{article["expected_start"]}~{article.get("expected_end") or article["expected_start"]}일차' if article.get('expected_start') else '후속 발표'
        expectation=next((s.strip() for s in article['body'].split('. ') if '새로 확인된 수치와 일정은' in s or '새로 확인된 내용은 기존 기대와' in s),'')
        return (f'{name}: {result}{topic} 완전 가동 시 매출 {m["revenue_pct"]:+.1f}%, '
                f'이익률 {m["margin_pp"]:+.2f}%p예요. {period}의 실제 운영과 분기 실적을 함께 확인해요.'
                + (' '+expectation.rstrip('.')+'.' if expectation else ''))
    if article.get('is_signal'):
        return f'{name}의 협상·검토에 관한 미확정 취재예요. 가까운 시일의 후속 발표를 확인하고, 기대나 우려와 반대로 결론 날 가능성도 살펴보세요.'
    if article['kind'] == 'earnings':
        return '20개 기업의 분기 실적이 공개됐어요. 당초 예상, 발표 직전 기대, 실제 이익을 나란히 비교해 보세요.'
    text = article['body'].split('. ')[0]
    return text if len(text)<=125 else text[:122]+'…'


def digest(data, limit=5):
    day = data['room']['day']
    candidates = [n for n in data['news'] if n['day']==day and n['kind']!='briefing']
    def priority(n):
        return (100 if n.get('is_breaking') else 50 if n['kind']=='earnings' else 40 if n.get('is_signal') else 35 if n['certainty']=='사실 확인' else
                25 if n['certainty']=='일정 조정' else 20 if n['kind']=='company' else 5, n['id'])
    chosen, seen, companies = [], set(), set()
    for n in sorted(candidates,key=priority,reverse=True):
        key = ('event',n['event_id']) if n.get('event_id') else ('article',n['id'])
        if key in seen or n['sector'] in companies:
            continue
        chosen.append(n)
        seen.add(key)
        companies.add(n['sector'])
        if len(chosen)==limit:
            break
    names = {a['id']:a['name'] for a in data['assets']}
    return [{'id':n['id'],'summary':summarize(n,names)} for n in chosen]


def market_activity(c, rid, day):
    start = max(1,day-2)
    items = [dict(r) for r in c.execute('''SELECT asset,COUNT(*) trade_count,SUM(qty) quantity,
       SUM(qty*price) amount,SUM(CASE WHEN side='buy' THEN qty ELSE 0 END) buy_quantity,
       SUM(CASE WHEN side='sell' THEN qty ELSE 0 END) sell_quantity
       FROM orders WHERE room_id=? AND status='filled' AND filled_day BETWEEN ? AND ?
       GROUP BY asset ORDER BY amount DESC,trade_count DESC,asset LIMIT 5''', (rid,start,day))]
    return {'start_day':start,'end_day':day,'source':'우리 반 실제 체결','ranking':'체결금액', 'items':items}


def public_guides(data, activity):
    highlights = digest(data)
    names = {a['id']:a['name'] for a in data['assets']}
    day = data['room']['day']
    first = highlights[0] if highlights else None
    news = {n['id']:n for n in data['news']}
    reporter = {'id':'reporter','name':'모아','role':'경제 기자','title':'핵심 소식을 모아 왔어요.',
                'text':first['summary'] if first else '오늘 공개된 소식이 아직 없어요. 앞서 나온 기업 기사와 실적을 먼저 살펴봐요.',
                'question':'처음의 계획에서 새로 바뀐 숫자나 일정이 있나요?',
                'evidence_ids':[first['id']] if first else [],
                'asset':news[first['id']]['sector'] if first and news[first['id']]['sector'] in names else None}
    reports = [r for r in data.get('reports',[]) if r['quarter']>0]
    if reports:
        newest = max(r['quarter'] for r in reports)
        r = max((r for r in reports if r['quarter']==newest),key=lambda r:abs(r.get('market_surprise') or r['surprise']))
        market = r.get('market_expected_profit') if r.get('market_expected_profit') is not None else r['expected_profit']
        research_text = (f'{names[r["asset"]]} {r["quarter"]}분기 이익은 {r["profit"]:,}억원이에요. '
                         f'당초 예상 {r["expected_profit"]:,}억원, 발표 직전 기대 {market:,}억원과 비교해 보세요.')
        research_asset,quarter,ids = r['asset'],r['quarter'],r['evidence_ids'][:3]
    else:
        target = next((n['sector'] for n in data['news'] if n['sector'] in names),None)
        f = next((f for f in data.get('market_estimates',[]) if f['asset']==target),None)
        research_text = (f'첫 실적 발표는 6일차예요. {names[target]}의 현재 예상 이익은 {f["profit"]:,}억원이에요. '
                         '목표와 실제 영업 성과를 구분해 읽어 봐요.') if f else '첫 실적 발표는 6일차예요. 기업이 제시한 매출 목표와 먼저 발생할 비용을 함께 읽어 봐요.'
        research_asset,quarter,ids = target,0,[]
    researcher = {'id':'researcher','name':'다온','role':'기업 연구원','title':'기대와 결과를 비교해요.',
                  'text':research_text,'question':'매출이 늘어도 이익이 줄거나, 성장해도 기대에 못 미칠 수 있을까요?',
                  'evidence_ids':ids,'asset':research_asset,'quarter':quarter}
    top = activity['items'][0] if activity['items'] else None
    observer = {'id':'observer','name':'누리','role':'시장 관찰자','title':'우리 반 거래 흐름을 살펴봐요.',
                'text':(f'{activity["start_day"]}~{day}일차 우리 반 실제 거래에서 {names[top["asset"]]}의 체결금액이 가장 컸어요. '
                        f'{top["trade_count"]}건, {top["quantity"]}주, {top["amount"]:,}원이에요.') if top else
                       '최근 3거래일에 체결된 거래가 아직 없어요. 거래가 쌓이면 실제 집계를 알려 줄게요.',
                'question':'거래가 많다는 것과 기업의 이익이 좋아진다는 것은 어떻게 다를까요?',
                'evidence_ids':[],'asset':top['asset'] if top else None}
    return {'highlights':highlights,'guides':[reporter,researcher,observer],'market_activity':activity}
