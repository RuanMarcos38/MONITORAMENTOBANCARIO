"""PostgreSQL API smoke test, only permitted in a dedicated CI database."""
import os
import secrets
from fastapi.testclient import TestClient
from sqlalchemy import select
from .main import app, hasher
from .db import DB, User
from .models import Organization


def main():
    if os.getenv('BANKGUARD_CI')!='1' or not os.getenv('DATABASE_URL','').split('?')[0].endswith('/bankguard_ci'):
        raise SystemExit('Este teste exige um banco CI exclusivo.')
    password=secrets.token_urlsafe(24)
    with DB() as db:
        for key in ('ci-alpha','ci-beta'):
            db.add(Organization(id=key,name='Organização de teste isolada',settings={}))
            db.add(User(org=key,email=key+'@example.test',password=hasher.hash(password),role='admin'))
        db.commit()
    a,b=TestClient(app),TestClient(app)
    for client,key in [(a,'ci-alpha'),(b,'ci-beta')]:
        assert client.post('/api/v1/auth/login',json={'email':key+'@example.test','password':password}).status_code==200
    case=a.post('/api/v1/investigations',json={'title':'Teste PostgreSQL isolado','note':'Verificação de persistência e isolamento.'}).json()
    assert len(a.get('/api/v1/records/investigations').json())==1
    assert b.get('/api/v1/records/investigations').json()==[]
    assert b.get('/api/v1/investigations/'+case['id']).status_code==404
    print('PostgreSQL: autenticação, gravação e isolamento entre organizações aprovados.')


if __name__=='__main__':
    main()
