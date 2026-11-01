"""PostgreSQL API smoke test, only permitted in a dedicated CI database."""
import os
import secrets
from fastapi.testclient import TestClient
from sqlalchemy import select,create_engine,func,text
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
    from cryptography.fernet import Fernet
    from tempfile import TemporaryDirectory
    from pathlib import Path
    from .db import engine
    from .backup import backup_to,restore_to_empty,verified_frames
    os.environ['BANKGUARD_ENCRYPTION_KEY']=Fernet.generate_key().decode()
    with engine.connect().execution_options(isolation_level='AUTOCOMMIT') as connection:
        connection.exec_driver_sql('CREATE DATABASE bankguard_ci_restore')
    target=create_engine(engine.url.set(database='bankguard_ci_restore'),hide_parameters=True)
    with TemporaryDirectory() as folder:
        archive=Path(folder)/'snapshot.enc'
        backup=backup_to(archive)
        assert sum(1 for _ in verified_frames(archive))==backup['rows']
        restored=restore_to_empty(archive,target)
        assert restored['restored_rows']==backup['rows']
        with target.connect() as connection:
            assert connection.execute(select(func.count()).select_from(User)).scalar()==2
            assert connection.execute(text('SELECT version_num FROM alembic_version')).scalar()=='002'
    print('PostgreSQL: backup cifrado, integridade, restauração isolada e versão de migração aprovados.')


if __name__=='__main__':
    main()
