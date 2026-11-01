"""Synthetic fixtures exclusively for disposable CI E2E databases."""
import os
from sqlalchemy import select
from .db import DB,User,Record
from .main import hasher
from .models import Organization

if os.getenv('BANKGUARD_CI')!='1' or not os.getenv('DATABASE_URL','').endswith('bankguard_e2e.db'):
    raise SystemExit('Este comando exige um banco descartável de testes E2E.')
with DB() as db:
    if db.scalar(select(User)):
        raise SystemExit('Banco de teste precisa estar vazio.')
    for role,org in [('analyst','ci-alpha'),('viewer','ci-beta')]:
        db.add(Organization(id=org,name='Organização de teste E2E',settings={}))
        db.add(User(email=role+'@example.test',org=org,password=hasher.hash('isolated-e2e-test-password-2026'),role=role))
    db.add(Record(org='ci-alpha',kind='investigations',external_id='ci-private',data={'title':'Confidencial CI Alpha','status':'Em análise','owner':'ci-fixture','timeline':[],'evidence':[]}))
    db.commit()
print('Fixtures E2E criadas exclusivamente no banco descartável.')
