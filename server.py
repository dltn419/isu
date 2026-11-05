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
  ''')
  columns={row[1] for row in c.execute('PRAGMA table_info(prices)')}
  for col in ('open_price','high_price','low_price'):
   if col not in columns:c.execute(f'ALTER TABLE prices ADD COLUMN {col} INTEGER')
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


# Day-by-day fictional newsroom arcs; impacts take effect on the following trading day.
STORY_NEWS = {1: ('AI 도시 건설 발표, 다섯 기업의 기대가 엇갈리다', '정부가 가상의 신도시 ‘미래항’에 AI 데이터센터를 유치하겠다고 발표했다. 브레인클라우드는 클라우드 구축을, 쿨링엣지는 냉각 설비를 검토 중이다. 하지만 전력 공급과 비용을 누가 감당할지가 관건이다.', '미래사업', 2.5), 2: ('전력 부족 경고…미래항 계획에 첫 번째 장애물', '전력 전문가들이 데이터센터에 필요한 전기를 공급하려면 새로운 전력망이 필요하다고 지적했다. 파워그리드솔루션에는 공급 계약의 기회지만, 다른 AI 기업에는 공사 지연 위험이 생겼다.', '미래사업', -1.5), 3: ('파워그리드, 미래항 전력망 설계 경쟁에 참여', '파워그리드솔루션이 전력망 사업의 입찰에 참여했다. 경쟁사가 더 낮은 가격을 제시하면서 계약은 아직 확정되지 않았다. 시장은 수주 가능성과 공사 비용을 함께 평가하고 있다.', 'PWGR', 2.5), 4: ('냉각 기술 시범 운용 성공, 정식 계약은 미정', '쿨링엣지가 소형 냉각 시설 테스트를 성공했다고 발표했다. 효율은 좋아 보이지만 대규모 설치 경험이 부족하다는 분석도 나왔다. 정식 계약 여부는 다음 주 결정될 예정이다.', 'COED', 3), 5: ('건설비 예상보다 증가…데이터센터 협상 난항', '원자재 비용이 오르면서 미래항 데이터센터 사업비가 당초 예산을 넘어설 가능성이 커졌다. 브레인클라우드는 투자 규모를 다시 검토하고 있다. 사업 전망은 여전히 유망하지만 단기 부담도 커졌다.', 'BRCL', -3), 6: ('1분기 결산 앞두고 AI 사업의 첫 시험대', '미래항 사업의 전력 계획은 일부 진전됐지만 투자 비용 문제가 남았다. 기업들은 1분기 실적을 앞두고 계약 여부를 공개할 예정이다. 호재만 보고 매수한 투자자들은 위험도 점검할 시점이다.', '미래사업', -1), 7: ('2분기 시작: 항공 관광 붐, 예약이 급증하다', '연휴를 앞두고 여행 예약이 크게 늘었다. 누리항공과 라이트에어는 항공편 증편을 논의 중이다. 다만 여행 수요가 실제 이익으로 이어지려면 항공유 비용도 안정되어야 한다.', '항공', 3), 8: ('항공유 가격 급등…항공권 할인 경쟁에 부담', '세계 에너지 시장이 불안해지며 항공유 가격이 올랐다. 라이트에어는 고객 유치를 위해 할인 행사를 유지하지만, 운항할수록 이익이 줄 수 있다는 걱정이 나온다.', '항공', -3), 9: ('누리항공, 장거리 화물 운송 신규 계약 체결', '누리항공이 기업 고객의 장거리 화물 운송 계약을 따냈다. 여객 수익과 화물 수익을 모두 확보할 기회이지만, 계약에 필요한 항공기 정비 비용도 증가한다.', 'NURA', 3), 10: ('정비 기업 누리테크에 일감 몰린다', '항공편이 늘면서 누리테크서비스의 정비 공장 가동률이 높아졌다. 인력 부족으로 작업이 늦어질 가능성도 있어, 수주 증가가 곧 순이익 증가를 뜻하지는 않는다.', 'NUTS', 2), 11: ('저가항공, 예매는 늘었지만 수익성 논란', '라이트에어의 탑승객 수가 증가했지만 과도한 할인 때문에 수익이 기대에 못 미칠 수 있다는 분석이 나왔다. 소비자는 반겼지만 투자자들의 시선은 나뉘고 있다.', 'LTAI', -4), 12: ('항공 업계 실적 공개 예고, 매출보다 순이익 주목', '여행 붐 덕분에 매출은 늘었지만 유가와 인건비가 변수로 남았다. 다음 분기 시작과 함께 공개될 실적에 시장의 관심이 쏠린다.', '항공', 1), 13: ('3분기 시작: 새로운 건강식 열풍', '유명 가상 스포츠 축제에서 건강 간편식이 인기를 얻었다. 그린테이블은 신제품을 출시하고 든든식품은 고단백 냉동식품 개발을 검토 중이다. 유행이 지속될지는 아직 알 수 없다.', '식품', 2.5), 14: ('원재료 가격 상승…식품회사 원가 부담 커져', '이상 기후로 일부 농산물 생산량이 줄었다. 팜브릿지의 원료 조달비와 여러 식품회사의 제조원가가 상승할 수 있다. 판매가격을 올리면 소비자 수요가 줄 위험도 있다.', '식품', -2.5), 15: ('그린테이블 신제품 완판, 생산 확대 결정', '그린테이블의 신제품이 빠르게 품절됐다. 회사는 생산시설을 늘리기로 했지만 새로운 설비를 갖추는 데 돈이 많이 든다. 매출 성장과 투자 비용이 동시에 발생한다.', 'GRTB', 4), 16: ('스윗웨이브 신메뉴 인기, 온라인 후기는 엇갈려', '스윗웨이브가 출시한 디저트가 SNS에서 화제를 모았다. 첫날 매출은 높았지만 품질 편차와 높은 가격을 지적하는 후기까지 등장했다.', 'SWWV', 2), 17: ('식품 기업 가격 인상설에 소비자 반발', '원가 부담을 견디기 어려운 업체들이 판매가격 인상을 검토한다는 소식이 전해졌다. 소비자 반발로 판매량이 감소할 수 있어, 투자자들은 마진과 수요를 함께 살피고 있다.', '식품', -2), 18: ('3분기 마지막 날, 유행보다 실적이 중요한 시점', '그린테이블과 스윗웨이브의 매출 소식은 좋았지만 원재료 가격이 문제로 남았다. 기업별로 이익과 현금이 얼마나 남았는지 살펴보라는 분석이 나왔다.', '식품', 1), 19: ('4분기 시작: 신약 연구 성과 발표 예고', '뉴핏바이오가 신약 시험 결과 일부를 곧 공개하겠다고 밝혔다. 성공한다면 치료제 개발이 진전되지만, 시험 결과가 기대에 못 미치면 주가가 크게 흔들릴 수 있다.', 'NFBI', 3), 20: ('신약 시험 일정 지연, 투자자 긴장', '뉴핏바이오가 추가 안전성 자료를 확보하기 위해 발표를 연기했다. 연구가 실패했다는 뜻은 아니지만, 상용화까지 걸리는 시간이 길어질 수 있다.', 'NFBI', -5), 21: ('메디온제약, 기존 치료제 판매 호조', '메디온제약은 기존 의약품 판매가 예상보다 안정적이라고 밝혔다. 급격한 성장 소식은 없지만 불확실성이 큰 신약 개발사와 다른 사업 구조가 부각됐다.', 'MDON', 2), 22: ('바이오 생산 계약, 메디온바이오웍스에 호재', '메디온바이오웍스가 해외 기업과 위탁 생산 계약을 협의하고 있다. 계약이 성사되면 공장 가동률이 오를 전망이지만, 아직 확정된 매출은 아니다.', 'MDBW', 3), 23: ('뉴핏바이오 시험 결과 일부 공개…평가는 혼조', '뉴핏바이오는 치료 효과 가능성을 확인했다고 발표했으나 일부 지표는 기대에 못 미쳤다. 시장은 추가 시험이 필요하다는 점에 주목했다.', 'NFBI', -3), 24: ('가상 1년 마감: 네 산업 이야기의 결말', '미래항의 AI 투자, 항공 여행 붐, 식품 신제품, 바이오 신약의 결과가 서로 달랐다. 뉴스 한 줄보다 실제 계약과 비용, 위험을 함께 살핀 투자자가 무엇을 배웠는지 돌아볼 시간이다.', '전체', 0)}

class CreateRoom(BaseModel):
 name:str=Field(min_length=2,max_length=50)
 password:str=Field(min_length=4,max_length=100)
 start_cash:int=Field(default=100000,ge=1000,le=100000000)
class Join(BaseModel):
 code:str
 name:str=Field(min_length=1,max_length=24)
 pin:str=Field(min_length=4,max_length=30)
class AdminLogin(BaseModel): code:str; password:str
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
  headline,article,sector,effect=STORY_NEWS[1]
  c.execute('INSERT INTO news(room_id,day,title,body,sector,impact) VALUES(?,?,?,?,?,?)',(rid,1,headline,article,sector,effect))
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
  r=dict(one(c,'SELECT id,name,code,day,phase,start_cash FROM rooms WHERE id=?',(s['room_id'],)))
  prices=rows(c,'SELECT asset,price,change FROM prices WHERE room_id=? AND day=?',(r['id'],r['day']))
  price_map={x['asset']:x for x in prices}
  out={'room':r,'role':s['role'],'assets':[{**a,**price_map.get(a['id'],{})} for a in ASSETS],
       'news':rows(c,'SELECT id,day,title,body,sector FROM news WHERE room_id=? AND day<=? AND active=1 ORDER BY day DESC,id DESC LIMIT 35',(r['id'],r['day'])),
       'players_count':one(c,'SELECT COUNT(*) n FROM players WHERE room_id=?',(r['id'],))['n']}
  if s['role']=='player':
   pid=s['player_id']; p=dict(one(c,'SELECT id,name,cash FROM players WHERE id=?',(pid,)))
   holdings=rows(c,'SELECT asset,qty,cost FROM holdings WHERE player_id=? ORDER BY asset',(pid,))
   deposits=rows(c,'SELECT * FROM deposits WHERE player_id=? ORDER BY id DESC',(pid,))
   orders=rows(c,'SELECT id,asset,side,qty,price,status,reason,created,filled_day FROM orders WHERE player_id=? ORDER BY id DESC LIMIT 70',(pid,))
   p['net']=snapshot_value(c,pid,r['id'],r['day']); p['profit']=p['net']-r['start_cash']-one(c,"SELECT COALESCE(SUM(amount),0) v FROM ledgers WHERE player_id=? AND kind='teacher'",(pid,))['v']
   out.update(player=p,holdings=holdings,deposits=deposits,orders=orders,
              ledger=rows(c,'SELECT day,kind,amount,note FROM ledgers WHERE player_id=? ORDER BY id DESC LIMIT 50',(pid,)),
              values=rows(c,'SELECT day,net,cash FROM daily_values WHERE player_id=? ORDER BY day',(pid,)))
  else:
   out['participants']=rows(c,'SELECT id,name,cash FROM players WHERE room_id=? ORDER BY id',(r['id'],))
   for p in out['participants']:
    p['net']=snapshot_value(c,p['id'],r['id'],r['day'])
    p['pending']=one(c,"SELECT COUNT(*) n FROM orders WHERE player_id=? AND status='pending'",(p['id'],))['n']
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
  title,body,sector,impact=STORY_NEWS[day]
  c.execute('INSERT INTO news(room_id,day,title,body,sector,impact) VALUES(?,?,?,?,?,?)',(rid,day,title,body,sector,impact))
  if day in (7,13,19):
   c.execute('INSERT INTO news(room_id,day,title,body,sector,impact) VALUES(?,?,?,?,?,0)',(rid,day,'📊 분기 보고서: 이야기가 숫자로 이어졌을까?','지난 분기 주가의 흐름을 돌아보세요. 계약이 실제 매출과 이익으로 이어졌는지, 기대와 결과가 어떻게 달랐는지 토론해 보세요.','전체'))
  record_all(c,rid,day)
  log(c,rid,day,'next',f'{day}일차 시작 및 가격 갱신')
 return {'ok':True,'day':day}
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