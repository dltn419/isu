"""24일 - classroom financial simulator (FastAPI + SQLite)."""
import os, json, secrets, hashlib, sqlite3, random, math, datetime, io, base64, asyncio, logging
from pathlib import Path
from contextlib import contextmanager, asynccontextmanager, suppress
from fastapi import FastAPI, HTTPException, Header, Request
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field
import classroom_engine as engine
import classroom_guides as guides
import game_reset
import bond_income
import breaking_news
import classroom_progression as progression
import news_reading
import etf_portfolio
import game_finale
from functools import lru_cache

ROOT=Path(__file__).resolve().parent
DB=Path(os.getenv('HARU_DB', str(ROOT/'haru.db')))
@asynccontextmanager
async def lifespan(app):
 task=asyncio.create_task(progression_loop())
 try:yield
 finally:
  task.cancel()
  with suppress(asyncio.CancelledError):await task

app=FastAPI(title='24일', docs_url='/api/docs',lifespan=lifespan)
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
 {'id':'GOV','name':'든든 국채','sector':'채권','type':'bond','risk':'low','initial':10000,'yield':0.12},
 {'id':'CORP','name':'튼튼 기업채','sector':'채권','type':'bond','risk':'medium','initial':10000,'yield':0.14},
 {'id':'JUNK','name':'도전 고수익채','sector':'채권','type':'bond','risk':'high','initial':10000,'yield':0.16},
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

BOND_DESCRIPTIONS={
 'GOV':'정부에 돈을 빌려주는 채권입니다. 세 채권 중 가격 변동이 작지만, 중간에 팔면 손실이 날 수 있습니다.',
 'CORP':'우량 기업에 돈을 빌려주는 채권입니다. 국채보다 이자가 높고 가격 변동도 더 큽니다.',
 'JUNK':'높은 이자를 주는 고위험 채권입니다. 가격 변동이 커서 이자를 받아도 전체 수익은 마이너스일 수 있습니다.'}
for a in ASSETS:
 if a['id'] in BOND_DESCRIPTIONS:a['description']=BOND_DESCRIPTIONS[a['id']]
etf_portfolio.attach(ASSETS)
AMAP={a['id']:a for a in ASSETS}
# 0.015% per fill, integer half-up rounding, at least 1 game won.
# A common teaching rate for traded assets; deposits and taxes are excluded.
FEE_POLICY={'rate':0.00015,'percent':0.015,'minimum':1,'rounding':'half_up','numerator':15,'denominator':100000}
def trading_fee(gross):return max(1,(gross*15+50000)//100000)
BOND_PRICE_PARAMETERS={'GOV':{'volatility':.65,'limit':5},'CORP':{'volatility':1.3,'limit':8},'JUNK':{'volatility':2,'limit':12}}
NEWS_PRICING={'gain':2.5,'weights':(.6,.25,.15),'noise_scale':.75}
DEPOSIT_RATES={6:.02,12:.045,18:.07,24:.10}
DEPOSIT_POLICY={'unit':10000,'minimum':10000,'early_interest_factor':.5,
                'products':[{'term':term,'rate':rate} for term,rate in DEPOSIT_RATES.items()]}

def deposit_details(d,day):
 item=dict(d)
 item['maturity_day']=d['start_day']+d['term']-1
 item['maturity_paid']=round(d['principal']*(1+d['rate']))
 elapsed=max(0,day-d['start_day'])
 ratio=0 if elapsed==0 else .5*min(1,elapsed/d['term'])
 item['early_interest']=round(d['principal']*d['rate']*ratio)
 item['early_paid']=d['principal']+item['early_interest']
 return item

def paid_fees(c,pid):
 return -one(c,"SELECT COALESCE(SUM(amount),0) n FROM ledgers WHERE player_id=? AND kind='fee'",(pid,))['n']


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
  if 'drivers' not in columns:c.execute('ALTER TABLE prices ADD COLUMN drivers TEXT')
  if 'mood' not in {row[1] for row in c.execute('PRAGMA table_info(rooms)')}:
   c.execute("ALTER TABLE rooms ADD COLUMN mood TEXT NOT NULL DEFAULT 'neutral'")
  engine.initialize_schema(c)
  game_reset.initialize(c)
  bond_income.initialize(c)
  progression.initialize(c)
  game_finale.initialize(c)
  if 'fee' not in {row[1] for row in c.execute('PRAGMA table_info(orders)')}:
   c.execute('ALTER TABLE orders ADD COLUMN fee INTEGER NOT NULL DEFAULT 0')
  if 'order_id' not in {row[1] for row in c.execute('PRAGMA table_info(investment_notes)')}:
   c.execute('ALTER TABLE investment_notes ADD COLUMN order_id INTEGER')
  c.execute('CREATE UNIQUE INDEX IF NOT EXISTS idx_note_order ON investment_notes(order_id) WHERE order_id IS NOT NULL')
  c.execute('CREATE INDEX IF NOT EXISTS idx_activity_orders ON orders(room_id,status,filled_day)')
  for existing in c.execute('SELECT id,seed,day FROM rooms').fetchall():
   engine.ensure_room(c,existing['id'],existing['seed'],existing['day'],ASSETS)
   engine.record_business_day(c,existing['id'],existing['day'],ASSETS)
  c.execute('BEGIN IMMEDIATE')
  for room in c.execute('SELECT * FROM rooms WHERE bond_interest_version=1').fetchall():
   bond_income.migrate_room(c,room,ASSETS)
  for room in c.execute("SELECT * FROM rooms WHERE phase!='finished'").fetchall():
   breaking_news.ensure_plan(c,room['id'],room['seed'],not_before=room['day']+1)
   breaking_news.publish_clues(c,room['id'],room['day'],room['seed'],room['mood'],ASSETS)
  # Preserve game progress; only earned bond interest is added by the one-time migration.
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

def holding_rows(c,pid):
 data=rows(c,'SELECT asset,qty,cost FROM holdings WHERE player_id=? ORDER BY asset',(pid,))
 for h in data:h['average_cost']=h['cost']/h['qty'] if h['qty'] else 0
 return data

def snapshot_value(c,pid,rid,day):
 p=one(c,'SELECT cash FROM players WHERE id=?',(pid,))
 h=rows(c,'SELECT * FROM holdings WHERE player_id=?',(pid,))
 val=sum(v['qty']*(one(c,'SELECT price FROM prices WHERE room_id=? AND day=? AND asset=?',(rid,day,v['asset'])) or {'price':0})['price'] for v in h)
 dep=one(c,"SELECT COALESCE(SUM(principal),0) AS total FROM deposits WHERE player_id=? AND status='active'",(pid,))['total']
 return p['cash']+val+dep+bond_income.summary(c,pid)['unpaid']

def record_all(c,rid,day):
 for p in rows(c,'SELECT id,cash FROM players WHERE room_id=?',(rid,)):
  c.execute('INSERT OR REPLACE INTO daily_values(room_id,player_id,day,net,cash) VALUES(?,?,?,?,?)',(rid,p['id'],day,snapshot_value(c,p['id'],rid,day),p['cash']))

def room_rankings(c,r):
 scores={}
 for p in rows(c,'SELECT id FROM players WHERE room_id=?',(r['id'],)):
  adjustment=one(c,"SELECT COALESCE(SUM(amount),0) amount FROM ledgers WHERE player_id=? AND kind='teacher'",(p['id'],))['amount']
  scores[p['id']]=snapshot_value(c,p['id'],r['id'],r['day'])-r['start_cash']-adjustment
 return {pid:{'rank':1+sum(other>score for other in scores.values()),'total':len(scores),
               'tied':sum(other==score for other in scores.values())>1,'basis':'investment_return'} for pid,score in scores.items()}


# Business events, public news and quarterly accounts share one persistent model.
MOODS=engine.MOOD_NAMES

def publish_dynamic_news(c,rid,day,seed,mood):
 engine.publish_news(c,rid,day,seed,mood,ASSETS)
 breaking_news.publish_clues(c,rid,day,seed,mood,ASSETS)

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

class OrderIn(BaseModel):
 asset:str
 side:str
 qty:int=Field(ge=1,le=100000)
 reason:str=Field(min_length=2,max_length=500)
 expected_day:int|None=Field(default=None,ge=1,le=24)
 expected_price:int|None=Field(default=None,ge=1)
 evidence_ids:list[int]=Field(default_factory=list,max_length=5)
class DepositIn(BaseModel): principal:int=Field(le=100000000); term:int
class NewsIn(BaseModel): title:str=Field(min_length=2,max_length=120); body:str=Field(min_length=2,max_length=400); sector:str='전체'; impact:float=Field(default=0,ge=-12,le=12)
class CashEdit(BaseModel): player_id:int; amount:int=Field(ge=-100000000,le=100000000); reason:str=Field(min_length=2,max_length=120)

@app.get('/')
def index(): return FileResponse(ROOT/'static'/'index.html')

@app.get('/health')
def health():
 return {'ok': True,'version':'22.0-design-comparison'}

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
  c.execute('BEGIN IMMEDIATE')
  for i in range(12):
   code=secrets.token_hex(3).upper()
   if not one(c,'SELECT id FROM rooms WHERE code=?',(code,)):break
  secret=secrets.token_urlsafe(32)
  cur=c.execute('INSERT INTO rooms(name,code,admin_hash,start_cash,seed,created,bond_interest_version) VALUES(?,?,?,?,?,?,2)',(b.name.strip(),code,digest(b.password),b.start_cash,secrets.randbelow(1000000000),now()))
  rid=cur.lastrowid
  c.execute('INSERT INTO room_progression(room_id) VALUES(?)',(rid,))
  c.executemany('INSERT INTO prices(room_id,day,asset,price,change) VALUES(?,1,?,?,0)',[(rid,a['id'],a['initial']) for a in ASSETS])
  c.execute('INSERT INTO sessions(token_hash,room_id,player_id,role,created) VALUES(?,?,NULL,?,?)',(digest(secret),rid,'admin',now()))
  publish_dynamic_news(c,rid,1,one(c,'SELECT seed FROM rooms WHERE id=?',(rid,))['seed'],'neutral')
  breaking_news.ensure_plan(c,rid,one(c,'SELECT seed FROM rooms WHERE id=?',(rid,))['seed'])
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
  c.execute('BEGIN')
  r=dict(one(c,'SELECT id,name,code,day,phase,start_cash,mood,generation,bond_interest_version FROM rooms WHERE id=?',(s['room_id'],)))
  engine.ensure_room(c,r['id'],one(c,'SELECT seed FROM rooms WHERE id=?',(r['id'],))['seed'],r['day'],ASSETS)
  prices=rows(c,'SELECT asset,price,change,drivers FROM prices WHERE room_id=? AND day=?',(r['id'],r['day']))
  for price in prices:price['price_context']=json.loads(price.pop('drivers') or 'null')
  price_map={x['asset']:x for x in prices}
  out={'room':r,'role':s['role'],'assets':[{**a,**price_map.get(a['id'],{})} for a in ASSETS],
       'news':rows(c,'SELECT id,day,title,body,sector,kind,source,certainty,event_id,related_assets,lens,horizon,expected_start,expected_end,metrics,is_breaking,is_signal FROM news WHERE room_id=? AND day<=? AND active=1 ORDER BY day DESC,id DESC LIMIT 500',(r['id'],r['day'])),
       'players_count':one(c,'SELECT COUNT(*) n FROM players WHERE room_id=?',(r['id'],))['n']}
  out['fee_policy']=FEE_POLICY
  out['deposit_policy']=DEPOSIT_POLICY
  out['progression']=progression.snapshot(c,r)
  out['bond_policy']=bond_income.policy(r)
  out['finale']=game_finale.public_report(c,r,ASSETS)
  rankings=room_rankings(c,r)
  out.update(engine.public_data(c,r['id'],r['day']))
  for n in out['news']:
   n['related_assets']=json.loads(n['related_assets'])
   n['metrics']=json.loads(n['metrics'])
  if s['role']=='player':
   pid=s['player_id']; p=dict(one(c,'SELECT id,name,cash FROM players WHERE id=?',(pid,)))
   holdings=holding_rows(c,pid)
   deposits=[deposit_details(d,r['day']) for d in rows(c,'SELECT * FROM deposits WHERE player_id=? ORDER BY id DESC',(pid,))]
   orders=rows(c,'SELECT id,asset,side,qty,price,fee,status,reason,evidence_ids,created,filled_day,is_final_liquidation FROM orders WHERE player_id=? ORDER BY id DESC LIMIT 70',(pid,))
   out.update(learning_data(c,pid,r['id']))
   out['bond_income']=bond_income.summary(c,pid)
   out['ranking']=rankings[pid]
   p['fees_paid']=paid_fees(c,pid)
   p['day_ready']=bool(one(c,'SELECT 1 FROM day_ready WHERE room_id=? AND player_id=? AND day=?',(r['id'],pid,r['day'])))
   p['net']=snapshot_value(c,pid,r['id'],r['day']); p['profit']=p['net']-r['start_cash']-one(c,"SELECT COALESCE(SUM(amount),0) v FROM ledgers WHERE player_id=? AND kind='teacher'",(pid,))['v']
   out.update(player=p,holdings=holdings,deposits=deposits,orders=orders,
              ledger=rows(c,'SELECT day,kind,amount,note FROM ledgers WHERE player_id=? ORDER BY id DESC LIMIT 50',(pid,)),
              values=rows(c,'SELECT day,net,cash FROM daily_values WHERE player_id=? ORDER BY day',(pid,)))
  else:
   out['participants']=rows(c,'SELECT id,name,cash FROM players WHERE room_id=? ORDER BY id',(r['id'],))
   for p in out['participants']:
    p['ranking']=rankings[p['id']]
    p['fees_paid']=paid_fees(c,p['id'])
    p['net']=snapshot_value(c,p['id'],r['id'],r['day'])
    p['profit']=p['net']-r['start_cash']-one(c,"SELECT COALESCE(SUM(amount),0) v FROM ledgers WHERE player_id=? AND kind='teacher'",(p['id'],))['v']
    p['day_ready']=bool(one(c,'SELECT 1 FROM day_ready WHERE room_id=? AND player_id=? AND day=?',(r['id'],p['id'],r['day'])))
    p.update(learning_summary(c,p['id']))
    p['pending']=one(c,"SELECT COUNT(*) n FROM orders WHERE player_id=? AND status='pending'",(p['id'],))['n']
   out['ready_count']=sum(p['day_ready'] for p in out['participants'])
   out['all_ready']=bool(out['participants']) and out['ready_count']==len(out['participants'])
   out['reset_backup']=dict(backup) if (backup:=one(c,'SELECT id,created,from_day FROM game_reset_backups WHERE room_id=? ORDER BY created DESC,rowid DESC LIMIT 1',(r['id'],))) else None
   out['logs']=rows(c,'SELECT day,event,detail FROM logs WHERE room_id=? ORDER BY id DESC LIMIT 40',(r['id'],))
   out['all_orders']=rows(c,'SELECT o.id,p.name,o.asset,o.side,o.qty,o.price,o.fee,o.status,o.reason,o.evidence_ids,o.is_final_liquidation FROM orders o JOIN players p ON p.id=o.player_id WHERE o.room_id=? ORDER BY o.id DESC LIMIT 60',(r['id'],))
  news_reading.enrich(out,engine.COMPANY_PROFILES)
  out.update(guides.public_guides(out,guides.market_activity(c,r['id'],r['day'])))
  return out
@app.get('/api/admin/student/{pid}')
def admin_student(pid:int,authorization:str|None=Header(None)):
 s=admin(authorization)
 with conn() as c:
  c.execute('BEGIN')
  r=one(c,'SELECT * FROM rooms WHERE id=?',(s['room_id'],))
  p=one(c,'SELECT id,name,cash FROM players WHERE id=? AND room_id=?',(pid,s['room_id']))
  if not p:err('해당 학생을 찾을 수 없습니다.',404)
  player=dict(p)
  player['day_ready']=bool(one(c,'SELECT 1 FROM day_ready WHERE room_id=? AND player_id=? AND day=?',(r['id'],pid,r['day'])))
  player['fees_paid']=paid_fees(c,pid)
  player['net']=snapshot_value(c,pid,r['id'],r['day'])
  player['profit']=player['net']-r['start_cash']-one(c,"SELECT COALESCE(SUM(amount),0) v FROM ledgers WHERE player_id=? AND kind='teacher'",(pid,))['v']
  return {**learning_data(c,pid,r['id']),'player':player,'holdings':holding_rows(c,pid),'bond_income':bond_income.summary(c,pid),'ranking':room_rankings(c,r)[pid],
    'deposits':[deposit_details(d,r['day']) for d in rows(c,'SELECT * FROM deposits WHERE player_id=? ORDER BY id DESC',(pid,))],
    'orders':rows(c,'SELECT id,asset,side,qty,price,fee,status,reason,evidence_ids,created,filled_day,is_final_liquidation FROM orders WHERE player_id=? ORDER BY id DESC LIMIT 70',(pid,)),
    'ledger':rows(c,'SELECT day,kind,amount,note FROM ledgers WHERE player_id=? ORDER BY id DESC LIMIT 50',(pid,)),
    'values':rows(c,'SELECT day,net,cash FROM daily_values WHERE player_id=? ORDER BY day',(pid,))}

@app.post('/api/day/complete')
def day_complete(authorization:str|None=Header(None),x_haru_game_generation:int|None=Header(None),x_haru_expected_day:int|None=Header(None)):
 s=session(authorization)
 if s['role']!='player':err('학생 계정이 필요합니다.',403)
 with conn() as c:
  c.execute('BEGIN IMMEDIATE')
  check_game_generation(c,s,x_haru_game_generation,x_haru_expected_day)
  r=one(c,'SELECT * FROM rooms WHERE id=?',(s['room_id'],))
  if r['phase']!='trading':err('오늘은 선택 완료를 표시할 수 없습니다.')
  c.execute('INSERT OR IGNORE INTO day_ready(room_id,player_id,day,created) VALUES(?,?,?,?)',(s['room_id'],s['player_id'],r['day'],now()))
  advanced=progression.maybe_advance(c,r,advance_room)
  if advanced:return {**advanced,'day_ready':False,'advanced':True}
 return {'ok':True,'day_ready':True}

@app.post('/api/day/reopen')
def day_reopen(authorization:str|None=Header(None),x_haru_game_generation:int|None=Header(None),x_haru_expected_day:int|None=Header(None)):
 s=session(authorization)
 if s['role']!='player':err('학생 계정이 필요합니다.',403)
 with conn() as c:
  c.execute('BEGIN IMMEDIATE')
  check_game_generation(c,s,x_haru_game_generation,x_haru_expected_day)
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
def place_order(b:OrderIn,authorization:str|None=Header(None),x_haru_game_generation:int|None=Header(None),x_haru_expected_day:int|None=Header(None)):
 s=session(authorization)
 if s['role']!='player':err('학생 계정이 필요합니다.',403)
 if b.asset not in AMAP or b.side not in ('buy','sell'):err('주문 정보가 올바르지 않습니다.')
 with conn() as c:
  c.execute('BEGIN IMMEDIATE')
  check_game_generation(c,s,x_haru_game_generation,x_haru_expected_day)
  rid=s['room_id'];pid=s['player_id'];r=one(c,'SELECT * FROM rooms WHERE id=?',(rid,))
  if r['phase']!='trading':err('현재 주문 가능한 상태가 아닙니다.')
  evidence=validate_evidence(c,rid,r['day'],b.evidence_ids)
  if len(b.reason.strip())<2:err('투자 이유를 2자 이상 적어주세요.')
  price=one(c,'SELECT price FROM prices WHERE room_id=? AND day=? AND asset=?',(rid,r['day'],b.asset))['price'];value=price*b.qty
  if (b.expected_day is not None and b.expected_day!=r['day']) or (b.expected_price is not None and b.expected_price!=price):err('거래일이나 가격이 바뀌었습니다. 새 결제 금액을 확인한 뒤 다시 거래하세요.',409)
  fee=trading_fee(value);settlement=value+fee if b.side=='buy' else value-fee
  h=one(c,'SELECT * FROM holdings WHERE player_id=? AND asset=?',(pid,b.asset))
  cash=one(c,'SELECT cash FROM players WHERE id=?',(pid,))['cash']
  if b.side=='buy':
   if settlement>cash:err('수수료를 포함한 결제 금액보다 현금이 부족합니다.')
   c.execute('UPDATE players SET cash=cash-? WHERE id=?',(settlement,pid))
   if h:c.execute('UPDATE holdings SET qty=qty+?,cost=cost+? WHERE player_id=? AND asset=?',(b.qty,settlement,pid,b.asset))
   else:c.execute('INSERT INTO holdings(player_id,asset,qty,cost) VALUES(?,?,?,?)',(pid,b.asset,b.qty,settlement))
  else:
   if not h or b.qty>h['qty']:err('매도할 수량이 부족합니다.')
   c.execute('UPDATE players SET cash=cash+? WHERE id=?',(settlement,pid))
   remaining=h['qty']-b.qty;cost=round(h['cost']*remaining/h['qty'])
   if remaining:c.execute('UPDATE holdings SET qty=?,cost=? WHERE player_id=? AND asset=?',(remaining,cost,pid,b.asset))
   else:c.execute('DELETE FROM holdings WHERE player_id=? AND asset=?',(pid,b.asset))
  cur=c.execute('INSERT INTO orders(room_id,player_id,asset,side,qty,price,status,reason,created,filled_day,evidence_ids) VALUES(?,?,?,?,?,?,?,?,?,?,?)',(rid,pid,b.asset,b.side,b.qty,price,'filled',b.reason.strip(),now(),r['day'],json.dumps(evidence)))
  c.execute('UPDATE orders SET fee=? WHERE id=?',(fee,cur.lastrowid))
  c.execute('INSERT INTO ledgers(room_id,player_id,day,kind,amount,note) VALUES(?,?,?,?,?,?)',(rid,pid,r['day'],'trade',value*(-1 if b.side=='buy' else 1),f"{b.asset} {'매수' if b.side=='buy' else '매도'} {b.qty}주 (즉시 체결)"))
  c.execute('INSERT INTO ledgers(room_id,player_id,day,kind,amount,note) VALUES(?,?,?,?,?,?)',(rid,pid,r['day'],'fee',-fee,f"{AMAP[b.asset]['name']} {'매수' if b.side=='buy' else '매도'} 수수료 (0.015%)"))
  selection_resumed=resume_selection(c,s,r['day'])
  note_id=ensure_order_note(c,cur.lastrowid,rid,pid)
  record_all(c,rid,r['day'])
  log(c,rid,r['day'],'trade',f'{pid}번 학생 {b.asset} {b.side} {b.qty}주 즉시 체결')
 return {'ok':True,'order_id':cur.lastrowid,'filled':True,'price':price,'fee':fee,'settlement':settlement,'note_id':note_id,'selection_resumed':selection_resumed,'message':'거래와 판단 이유를 함께 저장했어요.'}

@app.post('/api/orders/{oid}/cancel')
def cancel_order(oid:int,authorization:str|None=Header(None),x_haru_game_generation:int|None=Header(None),x_haru_expected_day:int|None=Header(None)):
 s=session(authorization)
 if s['role']!='player':err('학생 계정이 필요합니다.',403)
 with conn() as c:
  c.execute('BEGIN IMMEDIATE')
  check_game_generation(c,s,x_haru_game_generation,x_haru_expected_day)
  r=one(c,'SELECT phase FROM rooms WHERE id=?',(s['room_id'],))
  if r['phase']!='trading':err('장 마감 후에는 취소할 수 없습니다.')
  cur=c.execute("UPDATE orders SET status='cancelled' WHERE id=? AND player_id=? AND status='pending'",(oid,s['player_id']))
  if cur.rowcount!=1:err('취소할 수 없는 주문입니다.')
 return {'ok':True}
@app.post('/api/deposits')
def deposit(b:DepositIn,authorization:str|None=Header(None),x_haru_game_generation:int|None=Header(None),x_haru_expected_day:int|None=Header(None)):
 s=session(authorization)
 if s['role']!='player':err('학생 계정이 필요합니다.',403)
 if b.term not in DEPOSIT_RATES:err('예금 기간이 올바르지 않습니다.')
 with conn() as c:
  c.execute('BEGIN IMMEDIATE')
  check_game_generation(c,s,x_haru_game_generation,x_haru_expected_day)
  if b.principal<DEPOSIT_POLICY['minimum'] or b.principal%DEPOSIT_POLICY['unit']:
   err('예금은 최소 10,000원이며 10,000원 단위로 가입해 주세요.')
  r=one(c,'SELECT * FROM rooms WHERE id=?',(s['room_id'],))
  if r['phase']!='trading' or r['day']+b.term-1>24:err('현재 가입할 수 없는 만기입니다.')
  pending=one(c,"SELECT COALESCE(SUM(qty*price),0) n FROM orders WHERE player_id=? AND side='buy' AND status='pending'",(s['player_id'],))['n']
  p=one(c,'SELECT cash FROM players WHERE id=?',(s['player_id'],))
  if b.principal>p['cash']-pending:err('사용 가능한 현금이 부족합니다.')
  c.execute('UPDATE players SET cash=cash-? WHERE id=?',(b.principal,s['player_id']))
  c.execute('INSERT INTO deposits(player_id,room_id,principal,start_day,term,rate) VALUES(?,?,?,?,?,?)',(s['player_id'],s['room_id'],b.principal,r['day'],b.term,DEPOSIT_RATES[b.term]))
  c.execute('INSERT INTO ledgers(room_id,player_id,day,kind,amount,note) VALUES(?,?,?,?,?,?)',(s['room_id'],s['player_id'],r['day'],'deposit',-b.principal,f'{b.term}일 예금 가입'))
  selection_resumed=resume_selection(c,s,r['day'])
  record_all(c,s['room_id'],r['day'])
 return {'ok':True,'selection_resumed':selection_resumed}
@app.post('/api/deposits/{did}/close')
def close_deposit(did:int,authorization:str|None=Header(None),x_haru_game_generation:int|None=Header(None),x_haru_expected_day:int|None=Header(None)):
 s=session(authorization)
 if s['role']!='player':err('학생 계정이 필요합니다.',403)
 with conn() as c:
  c.execute('BEGIN IMMEDIATE')
  check_game_generation(c,s,x_haru_game_generation,x_haru_expected_day)
  d=one(c,"SELECT * FROM deposits WHERE id=? AND player_id=? AND status='active'",(did,s['player_id']))
  if not d:err('해지할 수 없는 예금입니다.')
  r=one(c,'SELECT day,phase FROM rooms WHERE id=?',(s['room_id'],))
  if r['phase']!='trading':err('거래 가능한 시간에 해지하세요.')
  paid=deposit_details(d,r['day'])['early_paid']
  c.execute("UPDATE deposits SET status='early',paid=?,closed_day=? WHERE id=?",(paid,r['day'],did))
  c.execute('UPDATE players SET cash=cash+? WHERE id=?',(paid,s['player_id']))
  c.execute('INSERT INTO ledgers(room_id,player_id,day,kind,amount,note) VALUES(?,?,?,?,?,?)',(s['room_id'],s['player_id'],r['day'],'deposit',paid,'예금 중도해지'))
  selection_resumed=resume_selection(c,s,r['day'])
  record_all(c,s['room_id'],r['day'])
 return {'ok':True,'paid':paid,'selection_resumed':selection_resumed}

def close_trading_day(c,r):
 rid=r['id']
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
 progression.pause(c,rid,finished=r['day']==24)
 bond_income.close_day(c,r,ASSETS)
 if r['day']==24:
  # Freeze the last closing portfolio before automatic sales, including day-24 coupons.
  record_all(c,rid,r['day'])
  game_finale.settle(c,r,ASSETS,trading_fee,now())
 record_all(c,rid,r['day'])
 log(c,rid,r['day'],'close',f'마감: 체결 {filled}건, 거절 {rejected}건')
 return {'ok':True,'filled':filled,'rejected':rejected}

@app.post('/api/admin/close')
def close_market(authorization:str|None=Header(None),x_haru_game_generation:int|None=Header(None),x_haru_expected_day:int|None=Header(None)):
 s=admin(authorization)
 with conn() as c:
  c.execute('BEGIN IMMEDIATE')
  check_game_generation(c,s,x_haru_game_generation,x_haru_expected_day)
  r=one(c,'SELECT * FROM rooms WHERE id=?',(s['room_id'],))
  return close_trading_day(c,r)

def news_contribution(n,day):
 lag=day-n['day']
 if n['pricing_end'] is not None and day>n['pricing_end']:return 0
 if n['pricing_version']==1:return n['impact'] if lag==1 else 0
 weights=NEWS_PRICING['weights'][:max(0,min(3,24-n['day']))]
 return n['impact']*NEWS_PRICING['gain']*weights[lag-1]/sum(weights) if 1<=lag<=len(weights) else 0

def generate_prices(c,rid,day,seed,earnings=None,breaking=None):
 rng=random.Random(seed+day*10007)
 previous={p['asset']:p['price'] for p in rows(c,'SELECT asset,price FROM prices WHERE room_id=? AND day=?',(rid,day-1))}
 effects=rows(c,'SELECT id,day,sector,impact,pricing_version,pricing_end FROM news WHERE room_id=? AND day BETWEEN ? AND ? AND active=1',(rid,max(1,day-3),day-1))
 market=rng.gauss(0,1.5)
 # A quarter-long common shock preserves meaningful market risk after diversification.
 regime=random.Random(seed+((day-2)//6)*4721+16127).gauss(0,.72)
 sectors={s:rng.gauss(0,1.5) for s in ['기술','항공','식품','의료·제약','미래사업']}
 rets={};drivers={}
 for a in ASSETS:
  id=a['id'];risk=a['risk'];old=previous[id]
  if a['type']=='stock':
   vol={'stable':.85,'growth':1.9,'high':3.8}[risk]
   relevant=[e for e in effects if e['sector'] in ('전체',a['sector'],id) and news_contribution(e,day)]
   news=sum(news_contribution(e,day) for e in relevant)
   annual_carry=engine.MARKET_ANNUAL_CARRY+{'stable':-.02,'growth':.02,'high':.06}[risk]
   carry=((1+annual_carry)**(1/engine.TRADING_INTERVALS)-1)*100
   beta={'stable':.8,'growth':1,'high':1.15}[risk]
   noise=beta*(market+regime)+sectors[a['sector']]*.5+rng.gauss(0,vol)
   earned=(earnings or {}).get(id,0)
   ret=carry+NEWS_PRICING['noise_scale']*noise+news+earned
   cap={'stable':7,'growth':12,'high':20}[risk]
   ret=max(-cap,min(cap,ret))
   drivers[id]={'news':news,'earnings':earned,'news_ids':[e['id'] for e in relevant],'breaking':False}
   if id in (breaking or {}):
    ret=max(-35,min(35,breaking[id]))
    drivers[id]={'news':ret,'earnings':0,'news_ids':[n['id'] for n in rows(c,'SELECT id FROM news WHERE room_id=? AND day=? AND sector=? AND is_breaking=1',(rid,day,id))],'breaking':True}
  elif a['type']=='gold':
   ret=max(-10,min(10,rng.gauss(0,1.7)-market*.25))
  elif a['type']=='bond':
   vol=BOND_PRICE_PARAMETERS[id]['volatility']
   cap=BOND_PRICE_PARAMETERS[id]['limit']
   ret=max(-cap,min(cap,rng.gauss(0,vol)-market*.15))
  else: continue
  price=max(1,round(old*(1+ret/100)))
  rets[id]=(price,(price/old-1)*100)
 def etf_return(sec):return etf_portfolio.index_return(rets,ASSETS,sec)
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
  if asset in drivers:
   info=drivers[asset];info['other']=change-info['news']-info['earnings']
   c.execute('UPDATE prices SET drivers=? WHERE room_id=? AND day=? AND asset=?',(json.dumps(info),rid,day,asset))

def start_trading_day(c,r):
 rid=r['id']
 if r['phase']!='closed':err('먼저 하루 주문을 마감하세요.')
 if r['day']>=24:err('게임이 종료되었습니다.')
 day=r['day']+1
 engine.evolve_businesses(c,rid,day,r['seed'],ASSETS)
 engine.resolve_events(c,rid,day,r['seed'],ASSETS)
 breaking=breaking_news.publish_open(c,rid,day,r['seed'],r['mood'],ASSETS)
 earnings=engine.release_earnings(c,rid,day,r['seed'],ASSETS)
 generate_prices(c,rid,day,r['seed'],earnings,breaking)
 c.execute("UPDATE rooms SET day=?,phase='trading' WHERE id=?",(day,rid))
 for d in rows(c,"SELECT * FROM deposits WHERE room_id=? AND status='active' AND start_day+term-1<=?",(rid,day)):
  paid=d['principal']+round(d['principal']*d['rate'])
  c.execute("UPDATE deposits SET status='matured',paid=?,closed_day=? WHERE id=?",(paid,day,d['id']))
  c.execute('UPDATE players SET cash=cash+? WHERE id=?',(paid,d['player_id']))
  c.execute('INSERT INTO ledgers(room_id,player_id,day,kind,amount,note) VALUES(?,?,?,?,?,?)',(rid,d['player_id'],day,'interest',paid,f"{d['term']}일 예금 만기 수령"))
 publish_dynamic_news(c,rid,day,r['seed'],r['mood'])
 progression.start_day(c,rid)
 record_all(c,rid,day)
 log(c,rid,day,'next',f'{day}일차 시작 및 가격 갱신')
 return {'ok':True,'day':day,'phase':'trading'}

@app.post('/api/admin/next')
def next_day(authorization:str|None=Header(None),x_haru_game_generation:int|None=Header(None),x_haru_expected_day:int|None=Header(None)):
 s=admin(authorization)
 with conn() as c:
  c.execute('BEGIN IMMEDIATE')
  check_game_generation(c,s,x_haru_game_generation,x_haru_expected_day)
  r=one(c,'SELECT * FROM rooms WHERE id=?',(s['room_id'],))
  return start_trading_day(c,r)

class AdvanceIn(BaseModel):
 expected_day:int=Field(ge=1,le=24)
 expected_phase:str=Field(pattern='^(trading|closed)$')

def advance_room(c,r,reason=None):
 original_day=r['day']
 if r['phase']=='trading':
  close_trading_day(c,r)
  r=one(c,'SELECT * FROM rooms WHERE id=?',(r['id'],))
 result={'ok':True,'day':24,'phase':'finished'} if r['phase']=='finished' else start_trading_day(c,r)
 if reason:log(c,r['id'],original_day,'auto_advance','시간 종료로 자동 진행' if reason=='timer' else '모든 학생 선택 완료로 자동 진행')
 return result

def tick_progression():
 with conn() as c:
  ids=[r[0] for r in c.execute("""SELECT r.id FROM rooms r JOIN room_progression p ON p.room_id=r.id
      WHERE r.phase='trading' AND (p.auto_ready=1 OR (p.timer_enabled=1 AND p.deadline<=?))""",(progression.time.time(),))]
 for rid in ids:
  with conn() as c:
   c.execute('BEGIN IMMEDIATE')
   r=one(c,'SELECT * FROM rooms WHERE id=?',(rid,))
   if r:progression.maybe_advance(c,r,advance_room)

async def progression_loop():
 while True:
  try:await asyncio.to_thread(tick_progression)
  except Exception:logging.exception('자동 수업 진행 실패; 현재 날짜를 유지하고 다음 검사에서 재시도합니다.')
  await asyncio.sleep(.5)

class ProgressionIn(BaseModel):
 auto_ready:bool|None=None
 timer_action:str|None=Field(default=None,pattern='^(start|stop)$')
 minutes:int|None=Field(default=None,ge=1,le=120)
 expected_day:int=Field(ge=1,le=24)
 expected_phase:str=Field(pattern='^(trading|closed|finished)$')

@app.get('/api/progression')
def progression_state(authorization:str|None=Header(None)):
 s=session(authorization)
 with conn() as c:
  c.execute('BEGIN')
  r=one(c,'SELECT * FROM rooms WHERE id=?',(s['room_id'],))
  return progression.snapshot(c,r)

@app.post('/api/admin/progression')
def configure_progression(b:ProgressionIn,authorization:str|None=Header(None),x_haru_game_generation:int|None=Header(None),x_haru_expected_day:int|None=Header(None)):
 s=admin(authorization)
 with conn() as c:
  c.execute('BEGIN IMMEDIATE')
  check_game_generation(c,s,x_haru_game_generation,x_haru_expected_day)
  r=one(c,'SELECT * FROM rooms WHERE id=?',(s['room_id'],))
  if r['day']!=b.expected_day or r['phase']!=b.expected_phase:err('수업 날짜나 상태가 바뀌었습니다. 새 화면에서 다시 설정하세요.',409)
  if r['phase']=='finished':err('게임이 종료되었습니다.')
  if b.timer_action=='start' and (r['phase']!='trading' or b.minutes is None):err('거래 중에 1~120분을 설정하고 시작하세요.')
  progression.configure(c,r['id'],auto_ready=b.auto_ready,action=b.timer_action,minutes=b.minutes)
  log(c,r['id'],r['day'],'progression',f'자동 진행 설정: 전원 완료={progression.config(c,r["id"])["auto_ready"]}, 시간 모드={b.timer_action or "유지"}')
  progression.maybe_advance(c,r,advance_room)
  return {'ok':True,'progression':progression.snapshot(c,one(c,'SELECT * FROM rooms WHERE id=?',(r['id'],)))}

@app.post('/api/admin/advance')
def advance_day(b:AdvanceIn,authorization:str|None=Header(None),x_haru_game_generation:int|None=Header(None),x_haru_expected_day:int|None=Header(None)):
 s=admin(authorization)
 with conn() as c:
  c.execute('BEGIN IMMEDIATE')
  check_game_generation(c,s,x_haru_game_generation,x_haru_expected_day)
  r=one(c,'SELECT * FROM rooms WHERE id=?',(s['room_id'],))
  if r['day']!=b.expected_day or r['phase']!=b.expected_phase:
   err('수업 진행 상태가 바뀌었습니다. 현재 화면을 확인한 뒤 다시 진행하세요.',409)
  return advance_room(c,r)

def check_game_generation(c,s,expected,expected_day=None):
 room=one(c,'SELECT generation,day,phase FROM rooms WHERE id=?',(s['room_id'],));current=room['generation']
 if (expected is None and current>0) or (expected is not None and expected!=current):
  err('새 게임이 시작되었어요. 화면을 새로고침한 뒤 다시 선택하세요.',409)
 if expected_day is not None and expected_day!=room['day']:err('다음 날이 시작되었어요. 새 화면에서 다시 선택하세요.',409)
 settings=progression.config(c,s['room_id'])
 if s['role']=='player' and expected_day is None and (settings['auto_ready'] or settings['timer_enabled']):
  err('자동 진행 모드가 켜졌어요. 화면을 새로고침한 뒤 선택해 주세요.',409)
 if s['role']=='player' and room['phase']=='trading' and progression.expired(c,s['room_id']):
  err('선택 시간이 끝났어요. 다음 날 화면을 기다려 주세요.',409)

class ResetIn(BaseModel):
 confirmation:str
 expected_day:int=Field(ge=1,le=24)
 expected_generation:int=Field(ge=0)

@app.post('/api/admin/reset')
def reset_game(b:ResetIn,authorization:str|None=Header(None),x_haru_game_generation:int|None=Header(None),x_haru_expected_day:int|None=Header(None)):
 s=admin(authorization)
 if b.confirmation!='초기화':err('확인란에 초기화를 정확히 입력하세요.')
 with conn() as c:
  c.execute('BEGIN IMMEDIATE')
  check_game_generation(c,s,x_haru_game_generation,x_haru_expected_day)
  r=one(c,'SELECT * FROM rooms WHERE id=?',(s['room_id'],))
  if r['day']!=b.expected_day or r['generation']!=b.expected_generation:
   err('게임 진행 상태가 바뀌었습니다. 현재 화면을 확인한 뒤 다시 초기화하세요.',409)
  result=game_reset.reset_room(c,r,ASSETS,now())
 return result

@app.get('/api/admin/reset-backup')
def reset_backup(authorization:str|None=Header(None)):
 s=admin(authorization)
 with conn() as c:
  backup=one(c,'SELECT id,snapshot FROM game_reset_backups WHERE room_id=? ORDER BY created DESC,rowid DESC LIMIT 1',(s['room_id'],))
  if not backup:err('아직 초기화 백업이 없습니다.',404)
  return JSONResponse(json.loads(backup['snapshot']),headers={'Content-Disposition':f'attachment; filename="haru-play-backup-{backup["id"][:8]}.json"','Cache-Control':'no-store'})

class MoodIn(BaseModel):
 mood:str

@app.post('/api/admin/mood')
def set_mood(b:MoodIn,authorization:str|None=Header(None),x_haru_game_generation:int|None=Header(None),x_haru_expected_day:int|None=Header(None)):
 s=admin(authorization)
 if b.mood not in MOODS:err('긍정, 중립, 부정 중에서 선택하세요.')
 with conn() as c:
  c.execute('BEGIN IMMEDIATE')
  check_game_generation(c,s,x_haru_game_generation,x_haru_expected_day)
  r=one(c,'SELECT day,phase FROM rooms WHERE id=?',(s['room_id'],))
  if r['phase']=='finished':err('종료된 게임입니다.')
  c.execute('UPDATE rooms SET mood=? WHERE id=?',(b.mood,s['room_id']))
  log(c,s['room_id'],r['day'],'mood',f'다음 자동 뉴스 분위기: {MOODS[b.mood]}')
 return {'ok':True,'mood':b.mood,'effective':'다음 거래일에 생성되는 뉴스부터'}

@app.post('/api/admin/news')
def add_news(b:NewsIn,authorization:str|None=Header(None),x_haru_game_generation:int|None=Header(None),x_haru_expected_day:int|None=Header(None)):
 s=admin(authorization)
 if b.sector not in ['전체','기술','항공','식품','의료·제약','미래사업']+list(AMAP):err('잘못된 뉴스 대상입니다.')
 with conn() as c:
  c.execute('BEGIN IMMEDIATE')
  check_game_generation(c,s,x_haru_game_generation,x_haru_expected_day)
  r=one(c,'SELECT day,phase FROM rooms WHERE id=?',(s['room_id'],))
  if r['phase']=='finished':err('종료된 게임입니다.')
  c.execute('INSERT INTO news(room_id,day,title,body,sector,impact) VALUES(?,?,?,?,?,?)',(s['room_id'],r['day'],b.title,b.body,b.sector,b.impact))
  log(c,s['room_id'],r['day'],'news',f'{b.title} / {b.sector} / 다음날 영향 {b.impact:+g}%p')
 return {'ok':True}
@app.post('/api/admin/cash')
def edit_cash(b:CashEdit,authorization:str|None=Header(None),x_haru_game_generation:int|None=Header(None),x_haru_expected_day:int|None=Header(None)):
 s=admin(authorization)
 with conn() as c:
  c.execute('BEGIN IMMEDIATE')
  check_game_generation(c,s,x_haru_game_generation,x_haru_expected_day)
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
def health():return {'ok':True,'db':str(DB.name),'version':'22.0-design-comparison'}

# Completion follows actual activity; a failed trade leaves the signal unchanged.
def resume_selection(c,s,day):
 cur=c.execute('DELETE FROM day_ready WHERE room_id=? AND player_id=? AND day=?',(s['room_id'],s['player_id'],day))
 return cur.rowcount>0

def ensure_order_note(c,oid,rid,pid):
 existing=one(c,'SELECT id FROM investment_notes WHERE order_id=? AND room_id=? AND player_id=?',(oid,rid,pid))
 if existing:return existing['id']
 o=one(c,"SELECT * FROM orders WHERE id=? AND room_id=? AND player_id=? AND status='filled' AND is_final_liquidation=0",(oid,rid,pid))
 if not o:err('거래 기록을 찾을 수 없습니다.',404)
 cur=c.execute('INSERT INTO investment_notes(room_id,player_id,day,asset,thesis,risk,horizon,evidence_ids,created,order_id) VALUES(?,?,?,?,?,?,?,?,?,?)',
  (rid,pid,o['filled_day'],o['asset'],o['reason'],'','다음 실적 발표까지',o['evidence_ids'],o['created'],oid))
 return cur.lastrowid

@app.post('/api/orders/{oid}/note')
def trade_note(oid:int,authorization:str|None=Header(None),x_haru_game_generation:int|None=Header(None),x_haru_expected_day:int|None=Header(None)):
 s=session(authorization)
 if s['role']!='player':err('학생 계정이 필요합니다.',403)
 with conn() as c:
  c.execute('BEGIN IMMEDIATE')
  check_game_generation(c,s,x_haru_game_generation,x_haru_expected_day)
  return {'ok':True,'id':ensure_order_note(c,oid,s['room_id'],s['player_id'])}

# Reading, evidence and reflection are separate from financial performance.
def validate_evidence(c,rid,day,ids):
 ids=list(dict.fromkeys(ids))
 for nid in ids:
  if not one(c,'SELECT 1 FROM news WHERE id=? AND room_id=? AND day<=? AND active=1',(nid,rid,day)):
   err('근거 뉴스가 현재 게임방에 공개된 기사인지 확인하세요.')
 return ids

def learning_summary(c,pid):
 return {
  'read_count':one(c,'SELECT COUNT(*) n FROM reading_log WHERE player_id=?',(pid,))['n'],
  'note_count':one(c,'SELECT COUNT(*) n FROM investment_notes WHERE player_id=?',(pid,))['n'],
  'evidence_trades':one(c,"SELECT COUNT(*) n FROM orders WHERE player_id=? AND evidence_ids!='[]'",(pid,))['n'],
  'reflection_count':one(c,"SELECT COUNT(*) n FROM investment_notes WHERE player_id=? AND reflection!=''",(pid,))['n']}

def learning_data(c,pid,rid):
 notes=rows(c,'''SELECT n.id,n.day,n.asset,n.thesis,n.risk,n.horizon,n.evidence_ids,n.reflection,n.created,n.order_id,
                       o.side AS order_side,o.qty AS order_qty,o.price AS order_price,o.fee AS order_fee,
                       p.price AS entry_price FROM investment_notes n LEFT JOIN orders o ON o.id=n.order_id LEFT JOIN prices p
                       ON p.room_id=n.room_id AND p.day=n.day AND p.asset=n.asset
                       WHERE n.player_id=? AND n.room_id=? ORDER BY n.id DESC LIMIT 100''',(pid,rid))
 for n in notes:n['evidence_ids']=json.loads(n['evidence_ids'])
 return {'read_ids':[x['news_id'] for x in rows(c,'SELECT news_id FROM reading_log WHERE player_id=? AND room_id=?',(pid,rid))],
         'watchlist':[x['asset'] for x in rows(c,'SELECT asset FROM watchlist WHERE player_id=?',(pid,))],
         'notes':notes,'learning':learning_summary(c,pid)}

class WatchIn(BaseModel):
 asset:str
 enabled:bool=True

@app.post('/api/watchlist')
def update_watchlist(b:WatchIn,authorization:str|None=Header(None),x_haru_game_generation:int|None=Header(None),x_haru_expected_day:int|None=Header(None)):
 s=session(authorization)
 if s['role']!='player':err('학생 계정이 필요합니다.',403)
 if b.asset not in AMAP:err('상품을 찾을 수 없습니다.',404)
 with conn() as c:
  c.execute('BEGIN IMMEDIATE')
  check_game_generation(c,s,x_haru_game_generation,x_haru_expected_day)
  if b.enabled:c.execute('INSERT OR IGNORE INTO watchlist VALUES(?,?)',(s['player_id'],b.asset))
  else:c.execute('DELETE FROM watchlist WHERE player_id=? AND asset=?',(s['player_id'],b.asset))
 return {'ok':True}

@app.post('/api/news/{nid}/read')
def read_article(nid:int,authorization:str|None=Header(None),x_haru_game_generation:int|None=Header(None),x_haru_expected_day:int|None=Header(None)):
 s=session(authorization)
 if s['role']!='player':err('학생 계정이 필요합니다.',403)
 with conn() as c:
  c.execute('BEGIN IMMEDIATE')
  check_game_generation(c,s,x_haru_game_generation,x_haru_expected_day)
  day=one(c,'SELECT day FROM rooms WHERE id=?',(s['room_id'],))['day']
  validate_evidence(c,s['room_id'],day,[nid])
  c.execute('INSERT OR IGNORE INTO reading_log VALUES(?,?,?,?)',(s['player_id'],s['room_id'],nid,day))
 return {'ok':True}

class NoteIn(BaseModel):
 asset:str
 thesis:str=Field(min_length=5,max_length=700)
 risk:str=Field(default='',max_length=500)
 horizon:str=Field(default='다음 실적 발표까지',min_length=2,max_length=60)
 evidence_ids:list[int]=Field(default_factory=list,max_length=5)

@app.post('/api/notes')
def create_note(b:NoteIn,authorization:str|None=Header(None),x_haru_game_generation:int|None=Header(None),x_haru_expected_day:int|None=Header(None)):
 s=session(authorization)
 if s['role']!='player':err('학생 계정이 필요합니다.',403)
 if b.asset not in AMAP:err('상품을 찾을 수 없습니다.',404)
 if len(b.thesis.strip())<5:err('어떤 생각인지 5자 이상 적어주세요.')
 with conn() as c:
  c.execute('BEGIN IMMEDIATE')
  check_game_generation(c,s,x_haru_game_generation,x_haru_expected_day)
  r=one(c,'SELECT day,phase FROM rooms WHERE id=?',(s['room_id'],))
  if r['phase']!='trading':err('새 투자 가설은 거래일 중에 기록할 수 있어요. 기존 기록의 돌아보기는 언제든 가능합니다.')
  ids=validate_evidence(c,s['room_id'],r['day'],b.evidence_ids)
  cur=c.execute('INSERT INTO investment_notes(room_id,player_id,day,asset,thesis,risk,horizon,evidence_ids,created) VALUES(?,?,?,?,?,?,?,?,?)',
   (s['room_id'],s['player_id'],r['day'],b.asset,b.thesis.strip(),b.risk.strip(),b.horizon.strip(),json.dumps(ids),now()))
 return {'ok':True,'id':cur.lastrowid}

class ReflectIn(BaseModel):
 reflection:str=Field(min_length=5,max_length=1000)
 risk:str|None=Field(default=None,max_length=500)
 horizon:str|None=Field(default=None,min_length=2,max_length=60)

@app.patch('/api/notes/{nid}')
def reflect_note(nid:int,b:ReflectIn,authorization:str|None=Header(None),x_haru_game_generation:int|None=Header(None),x_haru_expected_day:int|None=Header(None)):
 s=session(authorization)
 if s['role']!='player':err('학생 계정이 필요합니다.',403)
 if len(b.reflection.strip())<5:err('돌아보기를 5자 이상 적어주세요.')
 with conn() as c:
  c.execute('BEGIN IMMEDIATE')
  check_game_generation(c,s,x_haru_game_generation,x_haru_expected_day)
  cur=c.execute('UPDATE investment_notes SET reflection=? WHERE id=? AND player_id=? AND room_id=?',
                (b.reflection.strip(),nid,s['player_id'],s['room_id']))
  if cur.rowcount!=1:err('기록을 찾을 수 없습니다.',404)
  if b.risk is not None:c.execute('UPDATE investment_notes SET risk=? WHERE id=?',(b.risk.strip(),nid))
  if b.horizon is not None:c.execute('UPDATE investment_notes SET horizon=? WHERE id=?',(b.horizon.strip(),nid))
 return {'ok':True}

@lru_cache(maxsize=1)
def demo_state():
 """A read-only, in-memory classroom. Never creates rooms or students in the live database."""
 c=sqlite3.connect(':memory:');c.row_factory=sqlite3.Row
 try:
  c.executescript('''
   CREATE TABLE news(id INTEGER PRIMARY KEY,room_id INTEGER,day INTEGER,title TEXT,body TEXT,sector TEXT,impact REAL DEFAULT 0,active INTEGER DEFAULT 1);
   CREATE TABLE orders(id INTEGER PRIMARY KEY);
   CREATE TABLE prices(room_id INTEGER,day INTEGER,asset TEXT,price INTEGER,change REAL DEFAULT 0,open_price INTEGER,high_price INTEGER,low_price INTEGER,drivers TEXT);
  ''')
  engine.initialize_schema(c)
  seed=62171;rid=1
  c.executemany('INSERT INTO prices(room_id,day,asset,price,change) VALUES(?,1,?,?,0)',[(rid,a['id'],a['initial']) for a in ASSETS])
  engine.publish_news(c,rid,1,seed,'neutral',ASSETS)
  breaking_news.ensure_plan(c,rid,seed)
  breaking_news.publish_clues(c,rid,1,seed,'neutral',ASSETS)
  for day in range(2,7):
   engine.evolve_businesses(c,rid,day,seed,ASSETS)
   engine.resolve_events(c,rid,day,seed,ASSETS)
   breaking=breaking_news.publish_open(c,rid,day,seed,'neutral',ASSETS)
   reactions=engine.release_earnings(c,rid,day,seed,ASSETS)
   generate_prices(c,rid,day,seed,reactions,breaking)
   engine.publish_news(c,rid,day,seed,'neutral',ASSETS)
   breaking_news.publish_clues(c,rid,day,seed,'neutral',ASSETS)
  price_map={x['asset']:{**dict(x),'price_context':json.loads(x['drivers'] or 'null')} for x in rows(c,'SELECT asset,price,change,drivers FROM prices WHERE day=6')}
  for p in price_map.values():p.pop('drivers',None)
  assets=[{**a,**price_map[a['id']]} for a in ASSETS]
  news=rows(c,'SELECT id,day,title,body,sector,kind,source,certainty,event_id,related_assets,lens,horizon,expected_start,expected_end,metrics,is_breaking,is_signal FROM news ORDER BY day DESC,id DESC')
  for n in news:
   n['related_assets']=json.loads(n['related_assets'])
   n['metrics']=json.loads(n['metrics'])
  holdings=[{'asset':'HBEL','qty':2,'cost':20000},{'asset':'GRTB','qty':3,'cost':13800},{'asset':'MKT','qty':2,'cost':10000}]
  net=56200+sum(h['qty']*price_map[h['asset']]['price'] for h in holdings)
  histories={a['id']:rows(c,'SELECT day,price,change,open_price AS open,high_price AS high,low_price AS low,price AS close FROM prices WHERE asset=? ORDER BY day',(a['id'],)) for a in ASSETS}
  for bars in histories.values():
   for bar in bars:
    for key in ('open','high','low'):bar[key]=bar[key] or bar['price']
    bar['reconstructed']=False
  out={'demo':True,'role':'player','room':{'id':0,'name':'24일 체험 교실','code':'DEMO06','day':6,'phase':'trading','start_cash':100000,'mood':'neutral','generation':0},
   'fee_policy':FEE_POLICY,'deposit_policy':DEPOSIT_POLICY,'assets':assets,'news':news,'players_count':6,'player':{'fees_paid':0,'id':0,'name':'투자연구원','cash':56200,'net':net,'profit':net-100000,'day_ready':False},
   'holdings':holdings,'deposits':[],'orders':[],'ledger':[],'values':[{'day':1,'net':100000,'cash':56200},{'day':6,'net':net,'cash':56200}],
   'read_ids':[],'watchlist':['HBEL','GRTB','MORB'],'notes':[],'learning':{'read_count':0,'note_count':0,'evidence_trades':0,'reflection_count':0},
   'histories':histories,**engine.public_data(c,rid,6)}
  out['bond_policy']=bond_income.policy({**out['room'],'bond_interest_version':2})
  out['bond_income']={'unpaid':0,'paid':0,'items':[]}
  out['ranking']={'rank':3,'total':6,'tied':False,'basis':'investment_return'}
  news_reading.enrich(out,engine.COMPANY_PROFILES)
  out.update(guides.public_guides(out,{'start_day':4,'end_day':6,'source':'우리 반 실제 체결','ranking':'체결금액','items':[]}))
  return out
 finally:c.close()

@app.get('/api/demo')
def demo():return demo_state()

# Optional, explicit one-time operator request for the user's current reset.
# The request ID is recorded in SQLite; a restart cannot apply it a second time.
def apply_reset_request():
 request_id=os.getenv('HARU_RESET_PLAY_ONCE','').strip()
 if not request_id:return
 if len(request_id)>100 or not all(ch.isalnum() or ch in '-_' for ch in request_id):
  raise ValueError('Invalid reset request identifier')
 with conn() as c:
  c.execute('BEGIN IMMEDIATE')
  result=game_reset.apply_operator_request(c,request_id,os.getenv('HARU_RESET_ROOM_CODE','').strip().upper(),ASSETS,now())
 print(json.dumps({'maintenance':'play_reset',**result},ensure_ascii=False),flush=True)

apply_reset_request()
