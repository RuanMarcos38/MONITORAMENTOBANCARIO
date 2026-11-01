import csv
import hashlib
import io
import json
import secrets
import uuid
from datetime import datetime, timezone, timedelta
from decimal import Decimal, InvalidOperation
from typing import Annotated
from argon2 import PasswordHasher
from argon2.exceptions import VerificationError, InvalidHashError
from fastapi import FastAPI, Depends, HTTPException, UploadFile, Request, Response
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, Field
from sqlalchemy import select, func
from sqlalchemy.orm import Session as SQLSession
import pyotp
from .db import DB, User, Session, Record, database, now
from .connectors import SOURCES, collect
from .risk import evaluate

app = FastAPI(title='BankGuard AI', version='0.1.0')
app.add_middleware(CORSMiddleware, allow_origins=[], allow_credentials=False, allow_methods=['GET','POST'], allow_headers=['Content-Type'])
Db = Annotated[SQLSession, Depends(database)]
hasher = PasswordHasher()

@app.middleware('http')
async def security(request, call_next):
    response = await call_next(request)
    response.headers.update({'X-Content-Type-Options':'nosniff','X-Frame-Options':'DENY','Referrer-Policy':'no-referrer','Cache-Control':'no-store'})
    return response

def actor(request: Request, db: Db):
    token = request.cookies.get('bankguard_session', '')
    session = db.get(Session, hashlib.sha256(token.encode()).hexdigest())
    if not session or session.expires < now():
        raise HTTPException(401, 'Sessão inválida ou expirada')
    user = db.get(User, session.user_id)
    if not user:
        raise HTTPException(401)
    if request.method != 'GET':
        origin = request.headers.get('origin')
        if origin and origin != str(request.base_url).rstrip('/'):
            raise HTTPException(403, 'Origem não autorizada')
        if user.role not in ('admin','analyst'):
            raise HTTPException(403, 'Sem permissão de escrita')
    return user

Actor = Annotated[User, Depends(actor)]

def write(db, user, kind, data, external=None):
    record = Record(org=user.org, kind=kind, external_id=external or str(uuid.uuid4()), data=data)
    db.add(record)
    db.flush()
    return record

def audit(db, user, action, target):
    write(db, user, 'audit', {'actor':user.id, 'action':action, 'target':target, 'at':now()})

class Login(BaseModel):
    email: str = Field(min_length=3, max_length=254)
    password: str = Field(min_length=12, max_length=256)
    otp: str = ''

@app.post('/api/v1/auth/login')
def login(body: Login, request: Request, response: Response, db: Db):
    # Persist failed attempts, keyed by account and client; never log passwords.
    cutoff = (datetime.now(timezone.utc)-timedelta(minutes=15)).isoformat()
    key = hashlib.sha256((body.email.lower()+'|'+str(request.client.host if request.client else '')).encode()).hexdigest()
    attempts = db.scalar(select(func.count()).select_from(Record).where(Record.org=='auth', Record.kind==key, Record.created>=cutoff))
    if attempts >= 5:
        raise HTTPException(429, 'Tente novamente após 15 minutos')
    user = db.scalar(select(User).where(User.email==body.email.lower()))
    valid = False
    try:
        valid = hasher.verify(user.password if user else hasher.hash(secrets.token_hex(32)), body.password)
    except (VerificationError, InvalidHashError):
        pass
    if not user or not valid or (user.totp and not pyotp.TOTP(user.totp).verify(body.otp, valid_window=1)):
        db.add(Record(org='auth',kind=key,external_id=str(uuid.uuid4()),data={}))
        db.commit()
        raise HTTPException(401, 'Credenciais inválidas')
    token = secrets.token_urlsafe(48)
    db.add(Session(token=hashlib.sha256(token.encode()).hexdigest(), user_id=user.id, expires=(datetime.now(timezone.utc)+timedelta(hours=8)).isoformat()))
    audit(db,user,'login',user.id)
    db.commit()
    response.set_cookie('bankguard_session',token,httponly=True,secure=request.url.scheme=='https',samesite='strict',max_age=28800,path='/')
    return {'role':user.role, 'organization':user.org}

@app.post('/api/v1/auth/logout')
def logout(request: Request, response: Response, user: Actor, db: Db):
    session = db.get(Session, hashlib.sha256(request.cookies['bankguard_session'].encode()).hexdigest())
    db.delete(session)
    db.commit()
    response.delete_cookie('bankguard_session')
    return {'ok':True}

@app.get('/api/v1/health')
def health(db: Db):
    db.execute(select(1))
    return {'status':'ok','version':'0.1.0'}

@app.get('/api/v1/auth/me')
def me(user: Actor):
    return {'email':user.email,'role':user.role,'organization':user.org}

@app.get('/api/v1/dashboard')
def dashboard(user: Actor, db: Db):
    counts = dict(db.execute(select(Record.kind,func.count()).where(Record.org==user.org).group_by(Record.kind)).all())
    return {'counts': counts, 'calculated_at':now(), 'notice':'Indícios exigem revisão humana. Score não representa probabilidade de crime.'}

@app.get('/api/v1/sources')
def sources(user: Actor, db: Db):
    result=[]
    for source in SOURCES:
        state=db.scalar(select(Record).where(Record.org==user.org,Record.kind=='source_state',Record.external_id==source['id']))
        result.append({**source, **(state.data if state else {})})
    return result

@app.post('/api/v1/sources/{source}/sync')
def sync(source: str, user: Actor, db: Db):
    if user.role != 'admin':
        raise HTTPException(403)
    if source not in ('bcb','pncp'):
        raise HTTPException(409,'Integração pendente de implementação ou credenciamento')
    state=db.scalar(select(Record).where(Record.org==user.org,Record.kind=='source_state',Record.external_id==source))
    if not state:
        state=write(db,user,'source_state',{},source)
    try:
        rows=collect(source)
        inserted=0
        for row in rows:
            kind='indicators' if source=='bcb' else 'contracts'
            old=db.scalar(select(Record).where(Record.org==user.org,Record.kind==kind,Record.external_id==row['external_id']))
            if not old:
                write(db,user,kind,{**row,'collected_at':now(),'version':1,'hash':hashlib.sha256(json.dumps(row,sort_keys=True).encode()).hexdigest()},row['external_id'])
                inserted+=1
        state.data={'status':'OPERACIONAL' if rows else 'SEM DADOS','last_query':now(),'last_success':now(),'received':len(rows),'inserted':inserted,'scope':'Últimos 30 dias' if source=='bcb' else 'Publicações de hoje, primeira página (máximo 10); cobertura parcial'}
        audit(db,user,'source_sync',source)
        db.commit()
        return state.data
    except Exception:
        state.data={**state.data,'status':'INDISPONÍVEL','last_query':now(),'error':'Falha na consulta oficial; nenhum sucesso simulado.'}
        db.commit()
        raise HTTPException(502,'Fonte indisponível ou resposta incompatível')

KINDS={'companies','contracts','sanctions','transactions','alerts','investigations','relationships','indicators','audit'}

@app.get('/api/v1/records/{kind}')
def records(kind: str, user: Actor, db: Db, page: int=1, size: int=50, q: str=''):
    if kind not in KINDS or page<1 or not 1<=size<=100:
        raise HTTPException(422)
    query=select(Record).where(Record.org==user.org,Record.kind==kind).order_by(Record.created.desc())
    if q:
        from sqlalchemy import cast, String
        query=query.where(cast(Record.data,String).icontains(q,autoescape=True))
    rows=db.scalars(query.offset((page-1)*size).limit(size)).all()
    return [{'id':r.id,'created':r.created,**r.data} for r in rows]

class Case(BaseModel):
    title: str = Field(min_length=5,max_length=200)
    note: str = Field(min_length=10,max_length=10000)
    alert_id: str | None = None

@app.post('/api/v1/investigations')
def create_case(body: Case, user: Actor, db: Db):
    evidence=[]
    if body.alert_id:
        alert=db.scalar(select(Record).where(Record.org==user.org,Record.kind=='alerts',Record.id==body.alert_id))
        if not alert:
            raise HTTPException(404)
        evidence=[{'alert_id':alert.id,'snapshot':alert.data}]
    record=write(db,user,'investigations',{'title':body.title,'status':'Em análise','owner':user.id,'evidence':evidence,'timeline':[{'at':now(),'actor':user.id,'note':body.note}]})
    audit(db,user,'case_created',record.id)
    db.commit()
    return {'id':record.id,**record.data}

class Update(BaseModel):
    status: str
    note: str = Field(min_length=10,max_length=10000)

@app.post('/api/v1/investigations/{case_id}/events')
def case_event(case_id: str, body: Update, user: Actor, db: Db):
    allowed={'Novo','Em análise','Aguardando informações','Confirmado como irregularidade após verificação','Falso positivo','Resolvido','Arquivado'}
    if body.status not in allowed:
        raise HTTPException(422)
    record=db.scalar(select(Record).where(Record.org==user.org,Record.kind=='investigations',Record.id==case_id).with_for_update())
    if not record:
        raise HTTPException(404)
    record.data={**record.data,'status':body.status,'timeline':record.data['timeline']+[{'at':now(),'actor':user.id,'note':body.note,'status':body.status}]}
    audit(db,user,'case_updated',record.id)
    db.commit()
    return record.data

@app.post('/api/v1/transactions/import')
async def import_csv(file: UploadFile, user: Actor, db: Db):
    raw=await file.read(2_000_001)
    if len(raw)>2_000_000:
        raise HTTPException(413,'Limite de 2 MB')
    try:
        if not file.filename or not file.filename.lower().endswith('.csv'):
            raise ValueError()
        reader=csv.DictReader(io.StringIO(raw.decode('utf-8-sig')))
        if set(reader.fieldnames or []) != {'id','date','amount','beneficiary'}:
            raise ValueError()
        rows=list(reader)
        if not rows or len(rows)>10000 or len({r['id'] for r in rows}) != len(rows):
            raise ValueError()
        for r in rows:
            datetime.strptime(r['date'],'%Y-%m-%d')
            value=Decimal(r['amount'])
            if not value.is_finite() or abs(value)>Decimal('1e15') or value.as_tuple().exponent < -2:
                raise ValueError()
            if not r['id'] or not r['beneficiary'] or any(len(v)>500 for v in r.values()):
                raise ValueError()
    except (ValueError,UnicodeError,KeyError,TypeError,InvalidOperation):
        raise HTTPException(422,'CSV UTF-8 esperado: id,date,amount,beneficiary; data ISO e valor decimal com ponto. Lote rejeitado integralmente.')
    existing=set(db.scalars(select(Record.external_id).where(Record.org==user.org,Record.kind=='transactions')))
    for row in rows:
        if row['id'] in existing:
            old=db.scalar(select(Record).where(Record.org==user.org,Record.kind=='transactions',Record.external_id==row['id']))
            if any(old.data.get(k)!=v for k,v in row.items()):
                raise HTTPException(409,'Identificador já utilizado com conteúdo diferente')
    fresh=[r for r in rows if r['id'] not in existing]
    for row in fresh:
        write(db,user,'transactions',{**row,'origin':'CSV autorizado','collected_at':now()},row['id'])
    alerts=evaluate(rows)
    for alert in alerts:
        external='risk-v1:'+alert['transaction_id']
        if not db.scalar(select(Record).where(Record.org==user.org,Record.kind=='alerts',Record.external_id==external)):
            write(db,user,'alerts',alert,external)
    audit(db,user,'csv_import',{'inserted':len(fresh),'skipped':len(rows)-len(fresh)})
    db.commit()
    return {'inserted':len(fresh),'skipped':len(rows)-len(fresh),'flagged':len(alerts)}

@app.get('/api/v1/reports/{kind}.csv')
def export(kind: str, user: Actor, db: Db):
    if kind not in KINDS:
        raise HTTPException(404)
    stream=io.StringIO()
    writer=csv.writer(stream)
    writer.writerow(['id','created','data'])
    for record in db.scalars(select(Record).where(Record.org==user.org,Record.kind==kind)):
        writer.writerow([record.id,record.created,json.dumps(record.data,ensure_ascii=False)])
    audit(db,user,'export',kind)
    db.commit()
    return Response(stream.getvalue(),media_type='text/csv; charset=utf-8',headers={'Content-Disposition':f'attachment; filename="bankguard-{kind}.csv"'})
