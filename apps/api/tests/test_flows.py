import os
os.environ['DATABASE_URL']='sqlite://'
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, select, func
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool
from app.main import app, hasher
from app.db import Base, User, Record, database
import pytest

@pytest.fixture()
def clients():
    engine=create_engine('sqlite://',connect_args={'check_same_thread':False},poolclass=StaticPool)
    Base.metadata.create_all(engine)
    factory=sessionmaker(engine,expire_on_commit=False)
    def override():
        with factory() as db:
            yield db
    app.dependency_overrides[database]=override
    password='Test-only-password-2026'
    with factory() as db:
        for org in ['alpha','beta']:
            db.add(User(email=org+'@example.test',password=hasher.hash(password),org=org))
        db.commit()
    a,b=TestClient(app),TestClient(app)
    for client,org in [(a,'alpha'),(b,'beta')]:
        assert client.post('/api/v1/auth/login',json={'email':org+'@example.test','password':password}).status_code==200
    yield a,b,factory
    app.dependency_overrides.clear()
    engine.dispose()

def upload(client, data):
    return client.post('/api/v1/transactions/import',files={'file':('data.csv',data,'text/csv')})

def test_auth_and_logout(clients):
    a,b,_=clients
    assert TestClient(app).get('/api/v1/dashboard').status_code==401
    assert a.post('/api/v1/auth/logout').status_code==200
    assert a.get('/api/v1/dashboard').status_code==401
    assert b.get('/api/v1/dashboard').status_code==200

def test_tenant_case_isolation(clients):
    a,b,_=clients
    case=a.post('/api/v1/investigations',json={'title':'Caso documental','note':'Verificar evidências autorizadas.'}).json()
    assert len(a.get('/api/v1/records/investigations').json())==1
    assert b.get('/api/v1/records/investigations').json()==[]
    assert b.post('/api/v1/investigations/'+case['id']+'/events',json={'status':'Arquivado','note':'Tentativa sem permissão'}).status_code==404
    assert a.post('/api/v1/investigations/'+case['id']+'/events',json={'status':'Resolvido','note':'Verificação concluída com documentos.'}).status_code==200
    assert 'Caso documental' not in b.get('/api/v1/reports/investigations.csv').text

def test_import_atomicity_and_idempotency(clients):
    a,_,factory=clients
    data='id,date,amount,beneficiary\n1,2026-10-01,100.00,Empresa teste\n2,2026-10-01,100.00,Empresa teste\n'
    result=upload(a,data)
    assert result.status_code==200,result.text
    assert result.json()['inserted']==2
    assert len(a.get('/api/v1/records/alerts').json())==1
    assert upload(a,data).json()['inserted']==0
    assert len(a.get('/api/v1/records/alerts').json())==1
    assert upload(a,'id,date,amount,beneficiary\n3,2026-10-01,1.00,A\n4,invalid,2.00,B').status_code==422
    assert len(a.get('/api/v1/records/transactions').json())==2
    assert upload(a,data.replace('100.00','101.00')).status_code==409
    assert upload(a,data.replace('100.00','NaN')).status_code==422

def test_csrf_and_readonly(clients):
    a,_,factory=clients
    assert a.post('/api/v1/investigations',headers={'Origin':'https://evil.example'},json={'title':'Teste caso','note':'Origem não autorizada'}).status_code==403
    with factory() as db:
        user=db.scalar(select(User).where(User.org=='alpha'))
        user.role='viewer'
        db.commit()
    assert upload(a,'id,date,amount,beneficiary\n1,2026-10-01,1.00,A').status_code==403

def test_source_failure_is_truthful(clients,monkeypatch):
    a,_,_=clients
    def fail(_):
        raise RuntimeError('not exposed')
    monkeypatch.setattr('app.main.collect',fail)
    assert a.post('/api/v1/sources/bcb/sync').status_code==502
    source=next(s for s in a.get('/api/v1/sources').json() if s['id']=='bcb')
    assert source['status']=='INDISPONÍVEL'
    assert 'last_success' not in source
    assert a.post('/api/v1/sources/dict/sync').status_code==409

def test_real_connector_shape_and_dedup(clients,monkeypatch):
    a,_,_=clients
    monkeypatch.setattr('app.main.collect',lambda _: [{'external_id':'432:01/10/2026','value':'10.0','source':'bcb','source_url':'https://api.bcb.gov.br','reference_date':'01/10/2026'}])
    assert a.post('/api/v1/sources/bcb/sync').json()['inserted']==1
    assert a.post('/api/v1/sources/bcb/sync').json()['inserted']==0
    assert len(a.get('/api/v1/records/indicators').json())==1

def test_login_throttle(clients):
    a,_,_=clients
    client=TestClient(app)
    for _ in range(5):
        assert client.post('/api/v1/auth/login',json={'email':'alpha@example.test','password':'incorrect-password'}).status_code==401
    assert client.post('/api/v1/auth/login',json={'email':'alpha@example.test','password':'incorrect-password'}).status_code==429
