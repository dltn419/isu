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
  c.execute('INSERT INTO news(room_id,day,title,body,sector,impact) VALUES(?,?,?,?,?,0)',(rid,1,'모의 금융시장 개장','20개 기업과 다양한 금융상품의 거래가 시작되었습니다.','전체'))
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
@app.get('/api/history/{asset}')
def history(asset:str,authorization:str|None=Header(None)):
 s=session(authorization)
 if asset not in AMAP:err('상품을 찾을 수 없습니다.',404)
 with conn() as c:
  return rows(c,'SELECT day,price,change FROM prices WHERE room_id=? AND asset=? ORDER BY day',(s['room_id'],asset))

@app.post('/api/orders')
def place_order(b:OrderIn,authorization:str|None=Header(None)):
 s=session(authorization)
 if s['role']!='player':err('학생 계정이 필요합니다.',403)
 if b.asset not in AMAP or b.side not in ('buy','sell'):err('주문 정보가 올바르지 않습니다.')
 with conn() as c:
  c.execute('BEGIN IMMEDIATE')
  rid=s['room_id'];pid=s['player_id'];r=one(c,'SELECT * FROM rooms WHERE id=?',(rid,))
  if r['phase']!='trading':err('현재 주문 가능한 상태가 아닙니다.')
  price=one(c,'SELECT price FROM prices WHERE room_id=? AND day=? AND asset=?',(rid,r['day'],b.asset))['price']
  pending=rows(c,"SELECT asset,side,qty,price FROM orders WHERE player_id=? AND status='pending'",(pid,))
  if b.side=='buy':
   reserved=sum(x['price']*x['qty'] for x in pending if x['side']=='buy')
   cash=one(c,'SELECT cash FROM players WHERE id=?',(pid,))['cash']
   if b.qty*price>cash-reserved:err('현금이 부족합니다. 다른 대기 주문도 고려하세요.')
  else:
   h=one(c,'SELECT qty FROM holdings WHERE player_id=? AND asset=?',(pid,b.asset))
   reserved=sum(x['qty'] for x in pending if x['side']=='sell' and x['asset']==b.asset)
   if b.qty>(h['qty'] if h else 0)-reserved:err('매도할 수량이 부족합니다.')
  cur=c.execute('INSERT INTO orders(room_id,player_id,asset,side,qty,price,status,reason,created) VALUES(?,?,?,?,?, ?,?,?,?)',(rid,pid,b.asset,b.side,b.qty,price,'pending',b.reason.strip(),now()))
 return {'ok':True,'order_id':cur.lastrowid,'message':'주문이 접수됐습니다. 마감 시 체결됩니다.'}
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
  c.execute('INSERT INTO prices VALUES(?,?,?,?,?)',(rid,day,asset,price,round(change,4)))

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
  samples=[('오늘의 시장 흐름','기업마다 뉴스와 수급에 따라 주가가 다르게 움직이고 있습니다.','전체'),('성장 산업 동향','미래 성장 산업의 투자 기대와 위험이 함께 주목받고 있습니다.','미래사업'),('소비 동향','식품 기업의 매출과 비용을 비교해 보세요.','식품'),('금리와 채권','금리 변화는 채권 가격에도 영향을 줄 수 있습니다.','전체')]
  title,body,sector=samples[day%len(samples)]
  c.execute('INSERT INTO news(room_id,day,title,body,sector,impact) VALUES(?,?,?,?,?,0)',(rid,day,title,body,sector))
  if day in (7,13,19):
   c.execute('INSERT INTO news(room_id,day,title,body,sector,impact) VALUES(?,?,?,?,?,0)',(rid,day,'분기 실적 발표','직전 분기 가격 변화와 투자 판단을 점검해보세요.','전체'))
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