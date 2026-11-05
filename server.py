"""하루금융 - classroom financial simulator (FastAPI + SQLite)."""
import os, json, secrets, hashlib, sqlite3, random, math, datetime, io, base64
from pathlib import Path
from contextlib import contextmanager
from fastapi import FastAPI, HTTPException, Header, Request
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field

ROOT=Path(__file__).resolve().parent
DB=Path(os.getenv('HARU_DB', str(ROOT/'haru.db')))
app=FastAPI(title='하루금융', docs_url='/api/docs')
app.mount('/static', StaticFiles(directory=str(ROOT/'static')), name='static')

COMPANIES=[
('HBEL','한빛전자','기술',10000,'stable'),('NXDV','넥스디바이스','기술',7800,'growth'),('HBCP','한빛컴포넌트','기술',3400,'growth'),('SCNT','시큐어넷','기술',1900,'high'),
('NURA','누리항공','항공',7000,'stable'),('LTAI','라이트에어','항공',3600,'growth'),('NUTS','누리테크서비스','항공',4200,'growth'),('ARLG','에어링크로지스','항공',2600,'high'),
('DDFF','든든식품','식품',7600,'stable'),('GRTB','그린테이블','식품',4600,'growth'),('SWWV','스윗웨이브','식품',2400,'high'),('FMBR','팜브릿지','식품',3800,'growth'),
('MDON','메디온제약','의료·제약',8600,'stable'),('NFBI','뉴핏바이오','의료·제약',2700,'high'),('MDBW','메디온바이오웍스','의료·제약',5100,'growth'),('CLMD','클리어메디컬','의료·제약',4100,'growth'),
('BRCL','브레인클라우드','미래사업',6100,'growth'),('MORB','모션로보틱스','미래사업',4100,'growth'),('PWGR','파워그리드솔루션','미래사업',4900,'growth'),('COED','쿨링엣지','미래사업',2200,'high')]
ASSETS=[{'id':code,'name':name,'sector':sector,'type':'stock','risk':risk,'initial':price} for code,name,sector,price,risk in COMPANIES]
ASSETS += [{'id':'MKT','name':'전체시장 ETF','sector':'전체','type':'etf','risk':'medium','initial':5000}]
for sector,code in [('기술','TECH'),('항공','AIR'),('식품','FOOD'),('의료·제약','HEAL'),('미래사업','FUTR')]:
 ASSETS.append({'id':code,'name':sector+' ETF','sector':sector,'type':'etf','risk':'medium','initial':5000})
ASSETS += [
 {'id':'LEV2','name':'전체시장 2배 ETF','sector':'전체','type':'etf','risk':'high','initial':5000},
 {'id':'INV2','name':'전체시장 -2배 ETF','sector':'전체','type':'etf','risk':'high','initial':5000},
 {'id':'GOLD','name':'금 1g','sector':'원자재','type':'gold','risk':'medium','initial':6500},
 {'id':'GOV','name':'든든 국채','sector':'채권','type':'bond','risk':'low','initial':10000,'yield':0.10},
 {'id':'CORP','name':'튼튼 기업채','sector':'채권','type':'bond','risk':'medium','initial':10000,'yield':0.14},
 {'id':'JUNK','name':'도전 고수익채','sector':'채권','type':'bond','risk':'high','initial':10000,'yield':0.22},
]

COMPANY_DESCRIPTIONS = {
 "HBEL": "스마트폰·가전·반도체를 만드는 대기업입니다. 매출이 비교적 안정적이지만 세계 경기에 영향을 받습니다.",
 "NXDV": "고급 스마트기기와 자체 설계 반도체를 개발합니다. 신제품 성공에 따라 주가가 크게 움직일 수 있습니다.",
 "HBCP": "한빛전자에 센서와 카메라 부품을 공급하는 자회사입니다. 주요 고객의 판매량이 실적에 중요합니다.",
 "SCNT": "기업의 정보보안과 클라우드 서비스를 제공합니다. 신규 계약이 성장 기회지만 보안 사고가 큰 위험입니다.",
 "NURA": "국제선과 항공화물을 운영하는 대형 항공사입니다. 여행객 수, 유가, 환율에 민감합니다.",
 "LTAI": "저렴한 단거리 항공권을 판매합니다. 관광 수요가 늘면 성장하지만 비용과 경쟁이 부담입니다.",
 "NUTS": "항공기를 점검하고 수리하는 정비 기업입니다. 항공편이 늘면 정비 수요도 증가합니다.",
 "ARLG": "항공화물과 국제 배송을 맡습니다. 해외 교역이 활발할 때 유리하지만 운송비에 민감합니다.",
 "DDFF": "라면과 냉동식품을 판매하는 식품회사입니다. 꾸준한 수요가 강점이고 밀가루 가격이 중요합니다.",
 "GRTB": "건강식과 고단백 간편식을 개발합니다. 새 식품의 유행과 원가 관리가 성장을 좌우합니다.",
 "SWWV": "디저트와 음료를 판매하는 브랜드입니다. 인기 상품이 나오면 급성장하지만 유행이 빨리 바뀝니다.",
 "FMBR": "식품회사에 농산물 원료를 공급합니다. 작황과 원재료 가격 변동이 수익에 영향을 줍니다.",
 "MDON": "오랫동안 사용되는 치료제와 일반의약품을 판매합니다. 기존 약품 판매가 안정적인 편입니다.",
 "NFBI": "비만·대사질환 신약을 연구합니다. 임상 성공 가능성이 크지만 실패하면 손실이 커질 수 있습니다.",
 "MDBW": "다른 제약회사의 바이오의약품을 대신 생산합니다. 공장 가동률과 계약 체결이 중요합니다.",
 "CLMD": "병원용 진단장비와 검사 소모품을 공급합니다. 의료기관의 장비 투자에 영향을 받습니다.",
 "BRCL": "기업용 인공지능과 데이터센터 서비스를 제공합니다. AI 투자 확대가 성장 기회입니다.",
 "MORB": "공장과 물류창고에 자동화 로봇을 공급합니다. 기업 설비투자와 기술 경쟁이 중요합니다.",
 "PWGR": "전력망과 에너지저장장치 장비를 생산합니다. 전력 공급 확대 사업의 영향을 받습니다.",
 "COED": "데이터센터에 필요한 냉각장비를 개발합니다. AI 데이터센터 수요와 대형 계약에 따라 크게 변동합니다."
}
for a in ASSETS:
 a['description']=COMPANY_DESCRIPTIONS.get(a['id'], '여러 기업에 분산 투자하는 상품입니다.' if a['type']=='etf' else '가격과 위험이 변할 수 있는 가상 금융상품입니다.')

AMAP={a['id']:a for a in ASSETS}

@contextmanager
def conn():
 c=sqlite3.connect(str(DB), timeout=15, isolation_level=None)
 c.row_factory=sqlite3.Row
 c.execute('PRAGMA foreign_keys=ON')
 c.execute('PRAGMA busy_timeout=15000')
 try:
  yield c
  c.commit()
 except Exception:
  c.rollback()
  raise
 finally: c.close()

def init():
 DB.parent.mkdir(parents=True,exist_ok=True)
 with conn() as c:
  c.executescript('''
  PRAGMA journal_mode=WAL;
  CREATE TABLE IF NOT EXISTS rooms(id INTEGER PRIMARY KEY, name TEXT NOT NULL, code TEXT UNIQUE NOT NULL, admin_hash TEXT NOT NULL, day INTEGER NOT NULL DEFAULT 1, phase TEXT NOT NULL DEFAULT 'trading', start_cash INTEGER NOT NULL DEFAULT 100000, seed INTEGER NOT NULL, created TEXT NOT NULL);
  CREATE TABLE IF NOT EXISTS players(id INTEGER PRIMARY KEY, room_id INTEGER NOT NULL, name TEXT NOT NULL, pin_hash TEXT NOT NULL, cash INTEGER NOT NULL, created TEXT NOT NULL, UNIQUE(room_id,name));
  CREATE TABLE IF NOT EXISTS sessions(token_hash TEXT PRIMARY KEY, room_id INTEGER NOT NULL, player_id INTEGER, role TEXT NOT NULL, created TEXT NOT NULL);
  CREATE TABLE IF NOT EXISTS prices(room_id INTEGER NOT NULL, day INTEGER NOT NULL, asset TEXT NOT NULL, price INTEGER NOT NULL, change REAL NOT NULL DEFAULT 0, PRIMARY KEY(room_id,day,asset));
  CREATE TABLE IF NOT EXISTS holdings(player_id INTEGER NOT NULL, asset TEXT NOT NULL, qty INTEGER NOT NULL, cost INTEGER NOT NULL, PRIMARY KEY(player_id,asset));
  CREATE TABLE IF NOT EXISTS orders(id INTEGER PRIMARY KEY, room_id INTEGER NOT NULL, player_id INTEGER NOT NULL, asset TEXT NOT NULL, side TEXT NOT NULL, qty INTEGER NOT NULL, price INTEGER NOT NULL, status TEXT NOT NULL DEFAULT 'pending', reason TEXT NOT NULL, created TEXT NOT NULL, filled_day INTEGER);
  CREATE TABLE IF NOT EXISTS deposits(id INTEGER PRIMARY KEY, player_id INTEGER NOT NULL, room_id INTEGER NOT NULL, principal INTEGER NOT NULL, start_day INTEGER NOT NULL, term INTEGER NOT NULL, rate REAL NOT NULL, status TEXT NOT NULL DEFAULT 'active', paid INTEGER NOT NULL DEFAULT 0);
  CREATE TABLE IF NOT EXISTS news(id INTEGER PRIMARY KEY, room_id INTEGER NOT NULL, day INTEGER NOT NULL, title TEXT NOT NULL, body TEXT NOT NULL, sector TEXT NOT NULL DEFAULT '전체', impact REAL NOT NULL DEFAULT 0, active INTEGER NOT NULL DEFAULT 1);
  CREATE TABLE IF NOT EXISTS ledgers(id INTEGER PRIMARY KEY, room_id INTEGER NOT NULL, player_id INTEGER NOT NULL, day INTEGER NOT NULL, kind TEXT NOT NULL, amount INTEGER NOT NULL, note TEXT NOT NULL);
  CREATE TABLE IF NOT EXISTS logs(id INTEGER PRIMARY KEY, room_id INTEGER NOT NULL, day INTEGER NOT NULL, event TEXT NOT NULL, detail TEXT NOT NULL);
  CREATE TABLE IF NOT EXISTS daily_values(room_id INTEGER NOT NULL, player_id INTEGER NOT NULL, day INTEGER NOT NULL, net INTEGER NOT NULL, cash INTEGER NOT NULL, PRIMARY KEY(player_id,day));
  CREATE TABLE IF NOT EXISTS day_ready(room_id INTEGER NOT NULL, player_id INTEGER NOT NULL, day INTEGER NOT NULL, created TEXT NOT NULL, PRIMARY KEY(player_id,day));
  ''')
  columns={row[1] for row in c.execute('PRAGMA table_info(prices)')}
  for col in ('open_price','high_price','low_price'):
   if col not in columns:c.execute(f'ALTER TABLE prices ADD COLUMN {col} INTEGER')
  if 'mood' not in {row[1] for row in c.execute('PRAGMA table_info(rooms)')}:
   c.execute("ALTER TABLE rooms ADD COLUMN mood TEXT NOT NULL DEFAULT 'neutral'")
  # Existing games keep their original closing prices. Historic candles are reconstructed from adjacent closes.
init()

def now(): return datetime.datetime.now(datetime.timezone.utc).isoformat()
def digest(v): return hashlib.sha256(v.encode()).hexdigest()
def err(msg,status=400): raise HTTPException(status_code=status, detail=msg)
def one(c,q,args=()): return c.execute(q,args).fetchone()
def rows(c,q,args=()): return [dict(x) for x in c.execute(q,args).fetchall()]
def log(c,rid,day,event,detail): c.execute('INSERT INTO logs(room_id,day,event,detail) VALUES(?,?,?,?)',(rid,day,event,detail))
def session(auth):
 token=(auth or '').removeprefix('Bearer ').strip()
 with conn() as c:
  s=one(c,'SELECT * FROM sessions WHERE token_hash=?',(digest(token),)) if token else None
  if not s: err('로그인이 필요합니다.',401)
  return dict(s)
def admin(auth):
 s=session(auth)
 if s['role']!='admin':err('관리자만 가능합니다.',403)
 return s

def snapshot_value(c,pid,rid,day):
 p=one(c,'SELECT cash FROM players WHERE id=?',(pid,))
 h=rows(c,'SELECT * FROM holdings WHERE player_id=?',(pid,))
 val=sum(v['qty']*(one(c,'SELECT price FROM prices WHERE room_id=? AND day=? AND asset=?',(rid,day,v['asset'])) or {'price':0})['price'] for v in h)
 dep=one(c,"SELECT COALESCE(SUM(principal),0) AS total FROM deposits WHERE player_id=? AND status='active'",(pid,))['total']
 return p['cash']+val+dep

def record_all(c,rid,day):
 for p in rows(c,'SELECT id,cash FROM players WHERE room_id=?',(rid,)):
  c.execute('INSERT OR REPLACE INTO daily_values(room_id,player_id,day,net,cash) VALUES(?,?,?,?,?)',(rid,p['id'],day,snapshot_value(c,p['id'],rid,day),p['cash']))


# Procedural newsroom: news published on day N influences day N+1 prices.
MOODS={'positive':'긍정','neutral':'중립','negative':'부정'}
NEWS_TEMPLATES={
 'contract': [('신규 납품 계약 협의가 진전', '신규 납품 협상에 진전이 있다고 밝혔다. 다만 계약 금액과 실제 수익은 아직 확정되지 않았다.'),('대형 계약 조건을 재검토', '거래 상대방과 가격·납기 조건을 다시 협의한다. 계약 확정이 지연될 경우 매출 계획에도 영향이 있을 수 있다.'),('계약 발표 전 신중론 확산', '신규 계약에 대한 추측이 퍼졌지만 회사는 확정된 내용이 없다고 밝혔다. 시장은 실제 공시를 기다리고 있다.')],
 'sales': [('제품·서비스 주문량 증가', '고객 주문이 늘었다고 전했다. 판매 증가가 이익으로 연결되는지는 원가와 비용을 확인해야 한다.'),('판매 기대에 못 미쳤다는 분석', '최근 수요가 예상보다 약하다는 평가가 나왔다. 회사는 판매 전략을 조정할 계획이다.'),('수요 전망을 둘러싼 의견 엇갈려', '일부 분석가는 고객층 확대를 기대하지만 다른 쪽은 일시적 유행일 가능성을 제기한다.')],
 'cost': [('생산·운영 비용 절감 추진', '비용을 줄일 새로운 방법을 검토한다. 효과가 실제 실적에 반영되려면 시간이 필요하다.'),('예상 밖 비용 증가에 부담', '원재료와 인건비 부담이 커졌다고 설명했다. 매출이 같아도 이익은 감소할 수 있다.'),('운영비 변동성에 시장 주목', '비용 수준이 앞으로 어떻게 변할지 불확실하다. 회사는 효율화 계획을 검토 중이다.')],
 'research': [('신기술 시험에서 긍정적 신호', '기술 검증에서 일부 개선 결과가 관찰됐다. 정식 상용화까지는 추가 시험이 필요하다.'),('개발 일정 지연 가능성 제기', '신기술 검증 과정에서 보완 사항이 발견됐다. 추가 연구비와 일정 조정이 필요할 수 있다.'),('신제품 평가 앞두고 기대와 우려', '시제품 평가가 진행 중이다. 결과가 나올 때까지 성공 여부를 단정하기 어렵다.')],
 'finance': [('자금 여력 개선 기대', '현금 관리와 자금 조달 여건이 나아지고 있다는 평가가 나왔다. 정확한 결과는 다음 실적 발표에서 확인된다.'),('자금 조달 비용 부담 확대', '사업 확장에 필요한 자금의 비용이 늘어날 수 있다는 지적이 나왔다. 회사는 투자 규모를 점검 중이다.'),('재무 안정성 재평가', '투자자들이 매출 성장뿐 아니라 현금 보유액과 부채 수준을 함께 살피고 있다.')],
 'competition': [('경쟁사보다 유리한 입지 확보', '경쟁사와의 가격·품질 비교에서 호평을 얻었다는 시장 평가가 나왔다. 실제 점유율 변화는 더 지켜봐야 한다.'),('경쟁 심화로 수익성 압박', '경쟁사의 공격적인 판매 전략 때문에 가격 방어가 어려워질 수 있다는 분석이 나왔다.'),('업계 경쟁 구도 변화 가능성', '경쟁사들이 신제품과 서비스를 준비하고 있어 기업별 성과 차이가 벌어질 수 있다.')],
 'supply': [('공급망 개선으로 출하 기대', '부품·원료 공급이 비교적 안정되면서 납기 개선 가능성이 제기됐다.'),('부품·원료 수급 차질 경고', '핵심 공급업체의 납기가 불안정해 생산 계획에 차질이 생길 수 있다고 밝혔다.'),('공급망 점검 나서', '거래처를 다양화하는 방안을 검토 중이다. 초기 비용과 장기 안정성 사이에서 선택이 필요하다.')],
}
NEWS_TOPICS=list(NEWS_TEMPLATES)

def publish_dynamic_news(c,rid,day,seed,mood):
 """Deterministic per room/day, company-specific, assorted, non-scripted, persisted."""
 if one(c,'SELECT 1 FROM news WHERE room_id=? AND day=?',(rid,day)):return
 rng=random.Random(seed+day*9187+103)
 stocks=[a for a in ASSETS if a['type']=='stock']
 rng.shuffle(stocks)
 chosen=[]
 for sector in ['기술','항공','식품','의료·제약','미래사업']:
  pool=[a for a in stocks if a['sector']==sector]
  chosen.append(pool[0])
 chosen.append(next(a for a in stocks if a['id'] not in {x['id'] for x in chosen}))
 rng.shuffle(chosen)
 topics=rng.sample(NEWS_TOPICS,len(chosen))
 # Mood changes the PROBABILITY of favorable/unfavorable developments, not a guaranteed return.
 weight={'positive':[.64,.13,.23],'neutral':[.33,.34,.33],'negative':[.22,.14,.64]}[mood]
 for i,(a,topic) in enumerate(zip(chosen,topics)):
  roll=rng.random(); variant=0 if roll<weight[0] else (2 if roll<weight[0]+weight[2] else 1)
  # Template index: positive=0, negative=1, mixed=2.
  variant={0:0,1:2,2:1}[variant]
  subject,body=NEWS_TEMPLATES[topic][variant]
  previous=one(c,'SELECT title,impact FROM news WHERE room_id=? AND day<? AND sector=? ORDER BY day DESC,id DESC LIMIT 1',(rid,day,a['id']))
  follow=('최근 해당 기업을 둘러싼 보도가 이어지는 가운데, ' if previous else '')
  # Volatile firms get stronger but capped effects. Articles act the *next* day.
  magnitude=rng.uniform(1.2,2.8)*({'stable':.75,'growth':1.0,'high':1.4}[a['risk']])
  impact=round((1 if variant==0 else -1 if variant==1 else rng.choice([-1,1])*.15)*magnitude,2)
  title=f'{a["name"]}, {subject}'
  body=f'{follow}{a["name"]}은(는) {body} 시장 관계자들은 확정된 결과와 전망을 구별해야 한다고 설명했다.'
  c.execute('INSERT INTO news(room_id,day,title,body,sector,impact) VALUES(?,?,?,?,?,?)',(rid,day,title,body,a['id'],impact))
 # Add an independent sector outlook with weaker spillover and a non-directional brief.
 focus=rng.choice(['기술','항공','식품','의료·제약','미래사업'])
 level={'positive':'완만한 개선 기대','neutral':'엇갈리는 전망','negative':'불확실성 확대'}[mood]
 sector_impact=round(rng.uniform(.2,1.0)*(1 if mood=='positive' else -1 if mood=='negative' else rng.choice([-1,1])*.25),2)
 c.execute('INSERT INTO news(room_id,day,title,body,sector,impact) VALUES(?,?,?,?,?,?)',(rid,day,f'{focus} 업종, {level}',f'{focus} 업종에서는 기업별 계약 상황과 비용 부담을 둘러싸고 다양한 평가가 나온다. 오늘 뉴스가 미래 주가를 반드시 보장하지는 않는다.',focus,sector_impact))
 c.execute('INSERT INTO news(room_id,day,title,body,sector,impact) VALUES(?,?,?,?,?,0)',(rid,day,'오늘의 투자 체크: 같은 업종도 결과는 다를 수 있다',f'시장은 전반적으로 {MOODS[mood]} 분위기다. 개별 기업의 호재·악재와 가격 변동을 따로 살펴보고 분산투자를 고민해 보자.','전체'))
 log(c,rid,day,'auto_news',f'{MOODS[mood]} 분위기 · 자동 뉴스 8건 · 다음 거래일에 영향')

class CreateRoom(BaseModel):
 name:str=Field(min_length=2,max_length=50)
 password:str=Field(min_length=4,max_length=100)
 start_cash:int=Field(default=100000,ge=1000,le=100000000)
class Join(BaseModel):
 code:str
 name:str=Field(min_length=1,max_length=24)
 pin:str=Field(min_length=4,max_length=30)
class AdminLogin(BaseModel):
 code:str
 password:str

class OrderIn(BaseModel): asset:str; side:str; qty:int=Field(ge=1,le=100000); reason:str=Field(min_length=2,max_length=500)
class DepositIn(BaseModel): principal:int=Field(ge=1000,le=100000000); term:int
class NewsIn(BaseModel): title:str=Field(min_length=2,max_length=120); body:str=Field(min_length=2,max_length=400); sector:str='전체'; impact:float=Field(default=0,ge=-12,le=12)
class CashEdit(BaseModel): player_id:int; amount:int=Field(ge=-100000000,le=100000000); reason:str=Field(min_length=2,max_length=120)

@app.get('/')
def index(): return FileResponse(ROOT/'static'/'index.html')

@app.get('/health')
def health():
 return {'ok': True}

@app.get('/api/share')
def share(authorization:str|None=Header(None)):
 s=admin(authorization)
 with conn() as c:
  r=one(c,'SELECT code FROM rooms WHERE id=?',(s['room_id'],))
 public_url=os.getenv('PUBLIC_BASE_URL','').strip().rstrip('/')
 if not public_url.startswith('https://'):
  return {'url':'','qr':'','status':'offline','message':'배포 주소를 PUBLIC_BASE_URL 환경변수에 https:// 로 설정하세요.'}
 target=public_url+'/?join='+r['code']
 import qrcode
 output=io.BytesIO()
 qrcode.make(target,box_size=7,border=3).save(output,format='PNG')
 qr='data:image/png;base64,'+base64.b64encode(output.getvalue()).decode('ascii')
 return {'url':target,'qr':qr,'status':'ready','message':'학생용 공개 접속 주소입니다.'}

@app.post('/api/rooms')
def create_room(b:CreateRoom):
 with conn() as c:
  for i in range(12):
   code=secrets.token_hex(3).upper()
   if not one(c,'SELECT id FROM rooms WHERE code=?',(code,)):break
  secret=secrets.token_urlsafe(32)
  cur=c.execute('INSERT INTO rooms(name,code,admin_hash,start_cash,seed,created) VALUES(?,?,?,?,?,?)',(b.name.strip(),code,digest(b.password),b.start_cash,secrets.randbelow(1000000000),now()))
  rid=cur.lastrowid
  c.executemany('INSERT INTO prices(room_id,day,asset,price,change) VALUES(?,1,?,?,0)',[(rid,a['id'],a['initial']) for a in ASSETS])
  c.execute('INSERT INTO sessions(token_hash,room_id,player_id,role,created) VALUES(?,?,NULL,?,?)',(digest(secret),rid,'admin',now()))
  publish_dynamic_news(c,rid,1,one(c,'SELECT seed FROM rooms WHERE id=?',(rid,))['seed'],'neutral')
  log(c,rid,1,'create','교사가 게임방 생성')
 return {'token':secret,'code':code,'role':'admin'}
@app.post('/api/admin/login')
def admin_login(b:AdminLogin):
 with conn() as c:
  r=one(c,'SELECT * FROM rooms WHERE code=?',(b.code.upper().strip(),))
  if not r or digest(b.password)!=r['admin_hash']:err('방 코드 또는 비밀번호가 틀렸습니다.',401)
  token=secrets.token_urlsafe(32)
  c.execute('INSERT INTO sessions VALUES(?,?,?,?,?)',(digest(token),r['id'],None,'admin',now()))
 return {'token':token,'role':'admin','code':r['code']}
@app.post('/api/join')
def join(b:Join):
 with conn() as c:
  c.execute('BEGIN IMMEDIATE')
  r=one(c,'SELECT * FROM rooms WHERE code=?',(b.code.upper().strip(),))
  if not r:err('게임방을 찾을 수 없습니다.',404)
  if r['phase']=='finished':err('종료된 게임방입니다.')
  name=b.name.strip(); p=one(c,'SELECT * FROM players WHERE room_id=? AND name=?',(r['id'],name))
  if p:
   if p['pin_hash']!=digest(b.pin):err('이름이 이미 사용 중입니다. PIN을 확인하세요.',403)
   pid=p['id']
  else:
   cur=c.execute('INSERT INTO players(room_id,name,pin_hash,cash,created) VALUES(?,?,?,?,?)',(r['id'],name,digest(b.pin),r['start_cash'],now()))
   pid=cur.lastrowid
   c.execute('INSERT INTO daily_values VALUES(?,?,?,?,?)',(r['id'],pid,r['day'],r['start_cash'],r['start_cash']))
  token=secrets.token_urlsafe(32)
  c.execute('INSERT INTO sessions VALUES(?,?,?,?,?)',(digest(token),r['id'],pid,'player',now()))
 return {'token':token,'role':'player','code':r['code'],'name':name}

@app.get('/api/state')
def state(authorization:str|None=Header(None)):
 s=session(authorization)
 with conn() as c:
  r=dict(one(c,'SELECT id,name,code,day,phase,start_cash,mood FROM rooms WHERE id=?',(s['room_id'],)))
  prices=rows(c,'SELECT asset,price,change FROM prices WHERE room_id=? AND day=?',(r['id'],r['day']))
  price_map={x['asset']:x for x in prices}
  out={'room':r,'role':s['role'],'assets':[{**a,**price_map.get(a['id'],{})} for a in ASSETS],
       'news':rows(c,'SELECT id,day,title,body,sector FROM news WHERE room_id=? AND day<=? AND active=1 ORDER BY day DESC,id DESC LIMIT 140',(r['id'],r['day'])),
       'players_count':one(c,'SELECT COUNT(*) n FROM players WHERE room_id=?',(r['id'],))['n']}
  if s['role']=='player':
   pid=s['player_id']; p=dict(one(c,'SELECT id,name,cash FROM players WHERE id=?',(pid,)))
   holdings=rows(c,'SELECT asset,qty,cost FROM holdings WHERE player_id=? ORDER BY asset',(pid,))
   deposits=rows(c,'SELECT * FROM deposits WHERE player_id=? ORDER BY id DESC',(pid,))
   orders=rows(c,'SELECT id,asset,side,qty,price,status,reason,created,filled_day FROM orders WHERE player_id=? ORDER BY id DESC LIMIT 70',(pid,))
   p['day_ready']=bool(one(c,'SELECT 1 FROM day_ready WHERE room_id=? AND player_id=? AND day=?',(r['id'],pid,r['day'])))
   p['net']=snapshot_value(c,pid,r['id'],r['day']); p['profit']=p['net']-r['start_cash']-one(c,"SELECT COALESCE(SUM(amount),0) v FROM ledgers WHERE player_id=? AND kind='teacher'",(pid,))['v']
   out.update(player=p,holdings=holdings,deposits=deposits,orders=orders,
              ledger=rows(c,'SELECT day,kind,amount,note FROM ledgers WHERE player_id=? ORDER BY id DESC LIMIT 50',(pid,)),
              values=rows(c,'SELECT day,net,cash FROM daily_values WHERE player_id=? ORDER BY day',(pid,)))
  else:
   out['participants']=rows(c,'SELECT id,name,cash FROM players WHERE room_id=? ORDER BY id',(r['id'],))
   for p in out['participants']:
    p['net']=snapshot_value(c,p['id'],r['id'],r['day'])
    p['day_ready']=bool(one(c,'SELECT 1 FROM day_ready WHERE room_id=? AND player_id=? AND day=?',(r['id'],p['id'],r['day'])))
    p['pending']=one(c,"SELECT COUNT(*) n FROM orders WHERE player_id=? AND status='pending'",(p['id'],))['n']
   out['ready_count']=sum(p['day_ready'] for p in out['participants'])
   out['all_ready']=bool(out['participants']) and out['ready_count']==len(out['participants'])
   out['logs']=rows(c,'SELECT day,event,detail FROM logs WHERE room_id=? ORDER BY id DESC LIMIT 40',(r['id'],))
   out['all_orders']=rows(c,'SELECT o.id,p.name,o.asset,o.side,o.qty,o.status,o.reason FROM orders o JOIN players p ON p.id=o.player_id WHERE o.room_id=? ORDER BY o.id DESC LIMIT 60',(r['id'],))
  return out
@app.get('/api/admin/student/{pid}')
def admin_student(pid:int,authorization:str|None=Header(None)):
 s=admin(authorization)
 with conn() as c:
  r=one(c,'SELECT * FROM rooms WHERE id=?',(s['room_id'],))
  p=one(c,'SELECT id,name,cash FROM players WHERE id=? AND room_id=?',(pid,s['room_id']))
  if not p:err('해당 학생을 찾을 수 없습니다.',404)
  player=dict(p)
  player['net']=snapshot_value(c,pid,r['id'],r['day'])
  player['profit']=player['net']-r['start_cash']-one(c,"SELECT COALESCE(SUM(amount),0) v FROM ledgers WHERE player_id=? AND kind='teacher'",(pid,))['v']
  return {'player':player,'holdings':rows(c,'SELECT asset,qty,cost FROM holdings WHERE player_id=? ORDER BY asset',(pid,)),
    'deposits':rows(c,'SELECT * FROM deposits WHERE player_id=? ORDER BY id DESC',(pid,)),
    'orders':rows(c,'SELECT id,asset,side,qty,price,status,reason,created,filled_day FROM orders WHERE player_id=? ORDER BY id DESC LIMIT 70',(pid,)),
    'ledger':rows(c,'SELECT day,kind,amount,note FROM ledgers WHERE player_id=? ORDER BY id DESC LIMIT 50',(pid,)),
    'values':rows(c,'SELECT day,net,cash FROM daily_values WHERE player_id=? ORDER BY day',(pid,))}

@app.post('/api/day/complete')
def day_complete(authorization:str|None=Header(None)):
 s=session(authorization)
 if s['role']!='player':err('학생 계정이 필요합니다.',403)
 with conn() as c:
  c.execute('BEGIN IMMEDIATE')
  r=one(c,'SELECT day,phase FROM rooms WHERE id=?',(s['room_id'],))
  if r['phase']!='trading':err('오늘은 선택 완료를 표시할 수 없습니다.')
  c.execute('INSERT OR IGNORE INTO day_ready(room_id,player_id,day,created) VALUES(?,?,?,?)',(s['room_id'],s['player_id'],r['day'],now()))
 return {'ok':True,'day_ready':True}

@app.post('/api/day/reopen')
def day_reopen(authorization:str|None=Header(None)):
 s=session(authorization)
 if s['role']!='player':err('학생 계정이 필요합니다.',403)
 with conn() as c:
  c.execute('BEGIN IMMEDIATE')
  r=one(c,'SELECT day,phase FROM rooms WHERE id=?',(s['room_id'],))
  if r['phase']!='trading':err('이미 장이 마감되었습니다.')
  c.execute('DELETE FROM day_ready WHERE room_id=? AND player_id=? AND day=?',(s['room_id'],s['player_id'],r['day']))
 return {'ok':True,'day_ready':False}

@app.get('/api/history/{asset}')
def history(asset:str,authorization:str|None=Header(None)):
 s=session(authorization)
 if asset not in AMAP:err('상품을 찾을 수 없습니다.',404)
 with conn() as c:
  data=rows(c,'SELECT day,price,change,open_price,high_price,low_price FROM prices WHERE room_id=? AND asset=? ORDER BY day',(s['room_id'],asset))
  prev=None
  for bar in data:
   o=bar['open_price'] or prev or bar['price'];cl=bar['price']
   bar['open']=o;bar['high']=bar['high_price'] or max(o,cl);bar['low']=bar['low_price'] or min(o,cl);bar['close']=cl
   bar['reconstructed']=bar['open_price'] is None
   del bar['open_price'];del bar['high_price'];del bar['low_price']
   prev=cl
  return data

@app.post('/api/orders')
def place_order(b:OrderIn,authorization:str|None=Header(None)):
 s=session(authorization)
 if s['role']!='player':err('학생 계정이 필요합니다.',403)
 if b.asset not in AMAP or b.side not in ('buy','sell'):err('주문 정보가 올바르지 않습니다.')
 with conn() as c:
  c.execute('BEGIN IMMEDIATE')
  rid=s['room_id'];pid=s['player_id'];r=one(c,'SELECT * FROM rooms WHERE id=?',(rid,))
  if r['phase']!='trading':err('현재 주문 가능한 상태가 아닙니다.')
  if one(c,'SELECT 1 FROM day_ready WHERE room_id=? AND player_id=? AND day=?',(rid,pid,r['day'])):err('오늘 선택을 완료했어요. 거래하려면 선택 완료를 취소하세요.')
  price=one(c,'SELECT price FROM prices WHERE room_id=? AND day=? AND asset=?',(rid,r['day'],b.asset))['price'];value=price*b.qty
  h=one(c,'SELECT * FROM holdings WHERE player_id=? AND asset=?',(pid,b.asset))
  cash=one(c,'SELECT cash FROM players WHERE id=?',(pid,))['cash']
  if b.side=='buy':
   if value>cash:err('현금이 부족합니다.')
   c.execute('UPDATE players SET cash=cash-? WHERE id=?',(value,pid))
   if h:c.execute('UPDATE holdings SET qty=qty+?,cost=cost+? WHERE player_id=? AND asset=?',(b.qty,value,pid,b.asset))
   else:c.execute('INSERT INTO holdings(player_id,asset,qty,cost) VALUES(?,?,?,?)',(pid,b.asset,b.qty,value))
  else:
   if not h or b.qty>h['qty']:err('매도할 수량이 부족합니다.')
   c.execute('UPDATE players SET cash=cash+? WHERE id=?',(value,pid))
   remaining=h['qty']-b.qty;cost=round(h['cost']*remaining/h['qty'])
   if remaining:c.execute('UPDATE holdings SET qty=?,cost=? WHERE player_id=? AND asset=?',(remaining,cost,pid,b.asset))
   else:c.execute('DELETE FROM holdings WHERE player_id=? AND asset=?',(pid,b.asset))
  cur=c.execute('INSERT INTO orders(room_id,player_id,asset,side,qty,price,status,reason,created,filled_day) VALUES(?,?,?,?,?,?,?,?,?,?)',(rid,pid,b.asset,b.side,b.qty,price,'filled',b.reason.strip(),now(),r['day']))
  c.execute('INSERT INTO ledgers(room_id,player_id,day,kind,amount,note) VALUES(?,?,?,?,?,?)',(rid,pid,r['day'],'trade',value*(-1 if b.side=='buy' else 1),f"{b.asset} {'매수' if b.side=='buy' else '매도'} {b.qty}주 (즉시 체결)"))
  record_all(c,rid,r['day'])
  log(c,rid,r['day'],'trade',f'{pid}번 학생 {b.asset} {b.side} {b.qty}주 즉시 체결')
 return {'ok':True,'order_id':cur.lastrowid,'filled':True,'price':price,'message':'거래가 즉시 체결되어 내 자산에 반영됐습니다.'}

@app.post('/api/orders/{oid}/cancel')
def cancel_order(oid:int,authorization:str|None=Header(None)):
 s=session(authorization)
 if s['role']!='player':err('학생 계정이 필요합니다.',403)
 with conn() as c:
  c.execute('BEGIN IMMEDIATE')
  r=one(c,'SELECT phase FROM rooms WHERE id=?',(s['room_id'],))
  if r['phase']!='trading':err('장 마감 후에는 취소할 수 없습니다.')
  cur=c.execute("UPDATE orders SET status='cancelled' WHERE id=? AND player_id=? AND status='pending'",(oid,s['player_id']))
  if cur.rowcount!=1:err('취소할 수 없는 주문입니다.')
 return {'ok':True}
@app.post('/api/deposits')
def deposit(b:DepositIn,authorization:str|None=Header(None)):
 s=session(authorization)
 if s['role']!='player':err('학생 계정이 필요합니다.',403)
 if b.term not in (6,12,18,24):err('예금 기간이 올바르지 않습니다.')
 with conn() as c:
  c.execute('BEGIN IMMEDIATE')
  r=one(c,'SELECT * FROM rooms WHERE id=?',(s['room_id'],))
  if r['phase']!='trading' or r['day']+b.term-1>24:err('현재 가입할 수 없는 만기입니다.')
  if one(c,'SELECT 1 FROM day_ready WHERE room_id=? AND player_id=? AND day=?',(s['room_id'],s['player_id'],r['day'])):err('오늘 선택을 완료했어요. 예금 가입 전 선택 완료를 취소하세요.')
  pending=one(c,"SELECT COALESCE(SUM(qty*price),0) n FROM orders WHERE player_id=? AND side='buy' AND status='pending'",(s['player_id'],))['n']
  p=one(c,'SELECT cash FROM players WHERE id=?',(s['player_id'],))
  if b.principal>p['cash']-pending:err('사용 가능한 현금이 부족합니다.')
  c.execute('UPDATE players SET cash=cash-? WHERE id=?',(b.principal,s['player_id']))
  c.execute('INSERT INTO deposits(player_id,room_id,principal,start_day,term,rate) VALUES(?,?,?,?,?,?)',(s['player_id'],s['room_id'],b.principal,r['day'],b.term,0.1*b.term/24))
  c.execute('INSERT INTO ledgers(room_id,player_id,day,kind,amount,note) VALUES(?,?,?,?,?,?)',(s['room_id'],s['player_id'],r['day'],'deposit',-b.principal,f'{b.term}일 예금 가입'))
  record_all(c,s['room_id'],r['day'])
 return {'ok':True}
@app.post('/api/deposits/{did}/close')
def close_deposit(did:int,authorization:str|None=Header(None)):
 s=session(authorization)
 if s['role']!='player':err('학생 계정이 필요합니다.',403)
 with conn() as c:
  c.execute('BEGIN IMMEDIATE')
  d=one(c,"SELECT * FROM deposits WHERE id=? AND player_id=? AND status='active'",(did,s['player_id']))
  if not d:err('해지할 수 없는 예금입니다.')
  r=one(c,'SELECT day,phase FROM rooms WHERE id=?',(s['room_id'],))
  if r['phase']!='trading':err('거래 가능한 시간에 해지하세요.')
  if one(c,'SELECT 1 FROM day_ready WHERE room_id=? AND player_id=? AND day=?',(s['room_id'],s['player_id'],r['day'])):err('오늘 선택 완료를 취소한 뒤 예금을 해지하세요.')
  elapsed=max(0,r['day']-d['start_day'])
  ratio=0.15 if elapsed==0 else 0.5*min(1,elapsed/d['term'])
  paid=d['principal']+round(d['principal']*d['rate']*ratio)
  c.execute("UPDATE deposits SET status='early',paid=? WHERE id=?",(paid,did))
  c.execute('UPDATE players SET cash=cash+? WHERE id=?',(paid,s['player_id']))
  c.execute('INSERT INTO ledgers(room_id,player_id,day,kind,amount,note) VALUES(?,?,?,?,?,?)',(s['room_id'],s['player_id'],r['day'],'deposit',paid,'예금 중도해지'))
  record_all(c,s['room_id'],r['day'])
 return {'ok':True,'paid':paid}

@app.post('/api/admin/close')
def close_market(authorization:str|None=Header(None)):
 s=admin(authorization)
 with conn() as c:
  c.execute('BEGIN IMMEDIATE')
  rid=s['room_id'];r=one(c,'SELECT * FROM rooms WHERE id=?',(rid,))
  if r['phase']!='trading':err('이미 마감한 날입니다.')
  pending=rows(c,"SELECT * FROM orders WHERE room_id=? AND status='pending' ORDER BY id",(rid,))
  filled=0; rejected=0
  for o in pending:
   price=one(c,'SELECT price FROM prices WHERE room_id=? AND day=? AND asset=?',(rid,r['day'],o['asset']))['price']; value=price*o['qty']
   h=one(c,'SELECT * FROM holdings WHERE player_id=? AND asset=?',(o['player_id'],o['asset']))
   p=one(c,'SELECT cash FROM players WHERE id=?',(o['player_id'],))
   if o['side']=='buy' and p['cash']>=value:
    c.execute('UPDATE players SET cash=cash-? WHERE id=?',(value,o['player_id']))
    if h:c.execute('UPDATE holdings SET qty=qty+?,cost=cost+? WHERE player_id=? AND asset=?',(o['qty'],value,o['player_id'],o['asset']))
    else:c.execute('INSERT INTO holdings VALUES(?,?,?,?)',(o['player_id'],o['asset'],o['qty'],value))
   elif o['side']=='sell' and h and h['qty']>=o['qty']:
    c.execute('UPDATE players SET cash=cash+? WHERE id=?',(value,o['player_id']))
    remaining=h['qty']-o['qty']; cost=round(h['cost']*remaining/h['qty'])
    if remaining:c.execute('UPDATE holdings SET qty=?,cost=? WHERE player_id=? AND asset=?',(remaining,cost,o['player_id'],o['asset']))
    else:c.execute('DELETE FROM holdings WHERE player_id=? AND asset=?',(o['player_id'],o['asset']))
   else:
    c.execute("UPDATE orders SET status='rejected' WHERE id=?",(o['id'],));rejected+=1;continue
   c.execute("UPDATE orders SET status='filled',filled_day=? WHERE id=?",(r['day'],o['id']))
   c.execute('INSERT INTO ledgers(room_id,player_id,day,kind,amount,note) VALUES(?,?,?,?,?,?)',(rid,o['player_id'],r['day'],'trade',value*(-1 if o['side']=='buy' else 1),f"{o['asset']} {'매수' if o['side']=='buy' else '매도'} {o['qty']}주"))
   filled+=1
  c.execute("UPDATE rooms SET phase=? WHERE id=?",('finished' if r['day']==24 else 'closed',rid))
  # Bond coupons paid on the final day; simulate annual coupon on holdings.
  if r['day']==24:
   for p in rows(c,'SELECT id FROM players WHERE room_id=?',(rid,)):
    coupon=0
    for h in rows(c,'SELECT * FROM holdings WHERE player_id=?',(p['id'],)):
     a=AMAP[h['asset']]
     if a['type']=='bond':coupon+=round(10000*a['yield']*h['qty'])
    if coupon:
     c.execute('UPDATE players SET cash=cash+? WHERE id=?',(coupon,p['id']))
     c.execute('INSERT INTO ledgers(room_id,player_id,day,kind,amount,note) VALUES(?,?,?,?,?,?)',(rid,p['id'],24,'interest',coupon,'연말 채권 이자'))
  record_all(c,rid,r['day'])
  log(c,rid,r['day'],'close',f'마감: 체결 {filled}건, 거절 {rejected}건')
 return {'ok':True,'filled':filled,'rejected':rejected}

def generate_prices(c,rid,day,seed):
 rng=random.Random(seed+day*10007)
 previous={p['asset']:p['price'] for p in rows(c,'SELECT asset,price FROM prices WHERE room_id=? AND day=?',(rid,day-1))}
 effects=rows(c,'SELECT sector,impact,title FROM news WHERE room_id=? AND day=? AND active=1',(rid,day-1))
 market=rng.gauss(.2,1.2)
 sectors={s:rng.gauss(0,1.5) for s in ['기술','항공','식품','의료·제약','미래사업']}
 rets={}
 for a in ASSETS:
  id=a['id'];risk=a['risk'];old=previous[id]
  if a['type']=='stock':
   vol={'stable':1.35,'growth':3.5,'high':6.5}[risk]
   news=sum(e['impact'] for e in effects if e['sector'] in ('전체',a['sector'],id))
   ret=market*0.7+sectors[a['sector']]+news+rng.gauss(0,vol)
   cap={'stable':12,'growth':20,'high':35}[risk]
   ret=max(-cap,min(cap,ret))
  elif a['type']=='gold':
   ret=max(-10,min(10,rng.gauss(0,1.7)-market*.25))
  elif a['type']=='bond':
   vol={'GOV':.65,'CORP':1.3,'JUNK':4}[id]
   cap={'GOV':5,'CORP':8,'JUNK':40}[id]
   ret=max(-cap,min(cap,rng.gauss(0,vol)-market*.15))
  else: continue
  price=max(1,round(old*(1+ret/100)))
  rets[id]=(price,(price/old-1)*100)
 def etf_return(sec):
  inds=[x['id'] for x in ASSETS if x['type']=='stock' and (sec=='전체' or x['sector']==sec)]
  if sec=='전체':
   vals=[]
   for sector in ['기술','항공','식품','의료·제약','미래사업']:
    ids=[x['id'] for x in ASSETS if x['type']=='stock' and x['sector']==sector]
    vals.append(sum(rets[k][1]*w for k,w in zip(ids,[.35,.35,.15,.15])))
   return sum(vals)/5
  return sum(rets[k][1]*w for k,w in zip(inds,[.35,.35,.15,.15]))
 base=etf_return('전체')
 for a in ASSETS:
  if a['type']!='etf':continue
  id=a['id'];old=previous[id]
  if id in ('LEV2','INV2'): ret=max(-40,min(40,base*(2 if id=='LEV2' else -2)+rng.gauss(0,.1)-.025))
  else:ret=max(-10 if id=='MKT' else -12,min(10 if id=='MKT' else 12,etf_return(a['sector'])+rng.gauss(0,.07)-.01))
  price=max(1,round(old*(1+ret/100)))
  rets[id]=(price,(price/old-1)*100)
 for asset,(price,change) in rets.items():
  opening=previous[asset]
  wiggle=max(1,round(opening*(0.003 + abs(change)/100*0.12 + rng.random()*0.004)))
  high=max(opening,price)+wiggle
  low=max(1,min(opening,price)-wiggle)
  c.execute('INSERT INTO prices(room_id,day,asset,price,change,open_price,high_price,low_price) VALUES(?,?,?,?,?,?,?,?)',(rid,day,asset,price,round(change,4),opening,high,low))

@app.post('/api/admin/next')
def next_day(authorization:str|None=Header(None)):
 s=admin(authorization)
 with conn() as c:
  c.execute('BEGIN IMMEDIATE')
  rid=s['room_id'];r=one(c,'SELECT * FROM rooms WHERE id=?',(rid,))
  if r['phase']!='closed':err('먼저 하루 주문을 마감하세요.')
  if r['day']>=24:err('게임이 종료되었습니다.')
  day=r['day']+1
  generate_prices(c,rid,day,r['seed'])
  c.execute("UPDATE rooms SET day=?,phase='trading' WHERE id=?",(day,rid))
  for d in rows(c,"SELECT * FROM deposits WHERE room_id=? AND status='active' AND start_day+term-1<=?",(rid,day)):
   paid=d['principal']+round(d['principal']*d['rate'])
   c.execute("UPDATE deposits SET status='matured',paid=? WHERE id=?",(paid,d['id']))
   c.execute('UPDATE players SET cash=cash+? WHERE id=?',(paid,d['player_id']))
   c.execute('INSERT INTO ledgers(room_id,player_id,day,kind,amount,note) VALUES(?,?,?,?,?,?)',(rid,d['player_id'],day,'interest',paid,f"{d['term']}일 예금 만기 수령"))
  publish_dynamic_news(c,rid,day,r['seed'],r['mood'])
  if day in (7,13,19):
   c.execute('INSERT INTO news(room_id,day,title,body,sector,impact) VALUES(?,?,?,?,?,0)',(rid,day,'📊 분기 보고서: 이야기가 숫자로 이어졌을까?','지난 분기 주가의 흐름을 돌아보세요. 계약이 실제 매출과 이익으로 이어졌는지, 기대와 결과가 어떻게 달랐는지 토론해 보세요.','전체'))
  record_all(c,rid,day)
  log(c,rid,day,'next',f'{day}일차 시작 및 가격 갱신')
 return {'ok':True,'day':day}
class MoodIn(BaseModel):
 mood:str

@app.post('/api/admin/mood')
def set_mood(b:MoodIn,authorization:str|None=Header(None)):
 s=admin(authorization)
 if b.mood not in MOODS:err('긍정, 중립, 부정 중에서 선택하세요.')
 with conn() as c:
  c.execute('BEGIN IMMEDIATE')
  r=one(c,'SELECT day,phase FROM rooms WHERE id=?',(s['room_id'],))
  if r['phase']=='finished':err('종료된 게임입니다.')
  c.execute('UPDATE rooms SET mood=? WHERE id=?',(b.mood,s['room_id']))
  log(c,s['room_id'],r['day'],'mood',f'다음 자동 뉴스 분위기: {MOODS[b.mood]}')
 return {'ok':True,'mood':b.mood,'effective':'다음 거래일에 생성되는 뉴스부터'}

@app.post('/api/admin/news')
def add_news(b:NewsIn,authorization:str|None=Header(None)):
 s=admin(authorization)
 if b.sector not in ['전체','기술','항공','식품','의료·제약','미래사업']+list(AMAP):err('잘못된 뉴스 대상입니다.')
 with conn() as c:
  c.execute('BEGIN IMMEDIATE')
  r=one(c,'SELECT day,phase FROM rooms WHERE id=?',(s['room_id'],))
  if r['phase']=='finished':err('종료된 게임입니다.')
  c.execute('INSERT INTO news(room_id,day,title,body,sector,impact) VALUES(?,?,?,?,?,?)',(s['room_id'],r['day'],b.title,b.body,b.sector,b.impact))
  log(c,s['room_id'],r['day'],'news',f'{b.title} / {b.sector} / 다음날 영향 {b.impact:+g}%p')
 return {'ok':True}
@app.post('/api/admin/cash')
def edit_cash(b:CashEdit,authorization:str|None=Header(None)):
 s=admin(authorization)
 with conn() as c:
  c.execute('BEGIN IMMEDIATE')
  p=one(c,'SELECT * FROM players WHERE id=? AND room_id=?',(b.player_id,s['room_id']))
  if not p:err('학생을 찾을 수 없습니다.')
  if p['cash']+b.amount<0:err('현금이 음수가 됩니다.')
  r=one(c,'SELECT day FROM rooms WHERE id=?',(s['room_id'],))
  c.execute('UPDATE players SET cash=cash+? WHERE id=?',(b.amount,b.player_id))
  c.execute('INSERT INTO ledgers(room_id,player_id,day,kind,amount,note) VALUES(?,?,?,?,?,?)',(s['room_id'],b.player_id,r['day'],'teacher',b.amount,b.reason))
  record_all(c,s['room_id'],r['day'])
  log(c,s['room_id'],r['day'],'cash',f"{p['name']}: {b.amount:+,}원 - {b.reason}")
 return {'ok':True}
@app.get('/api/health')
def health():return {'ok':True,'db':str(DB.name)}