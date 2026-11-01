import pytest
import pyotp
from cryptography.fernet import Fernet
from sqlalchemy import select
from test_flows import clients
from app.db import Record, User
from app.models import Attachment, Credential
from app.security import cnpj, decrypt


@pytest.fixture(autouse=True)
def keys(monkeypatch):
    monkeypatch.setenv('BANKGUARD_ENCRYPTION_KEY',Fernet.generate_key().decode())
    monkeypatch.setenv('BANKGUARD_AUDIT_KEY','test-only-audit-key-'+('a'*32))


def test_cnpj_official_alphanumeric_example():
    assert cnpj('12.ABC.345/01DE-35')=='12ABC34501DE35'
    with pytest.raises(ValueError):
        cnpj('12.ABC.345/01DE-36')


def test_company_manual_alert_and_investigation(clients):
    a,b,_=clients
    company=a.post('/api/v1/companies',json={'cnpj':'12.ABC.345/01DE-35','name':'Fixture isolada','uf':'SP','purpose':'Monitoramento de teste autorizado'})
    assert company.status_code==200,company.text
    assert company.json()['official_verified'] is False
    assert b.get('/api/v1/records/companies').json()==[]
    payload={'title':'Indício para revisão','category':'Documental','severity':'Médio','source_url':'https://pncp.gov.br/','reference_date':'2026-10-01','evidence':'Documento de teste isolado com contexto para revisão.'}
    alert=a.post('/api/v1/alerts',json=payload)
    assert alert.status_code==200,alert.text
    key=alert.json()['id']
    assert b.post('/api/v1/alerts/'+key+'/events',json={'status':'Resolvido','note':'Tentativa de outra organização'}).status_code==404
    assert a.post('/api/v1/alerts/'+key+'/events',json={'status':'Falso positivo','note':'Análise documental concluiu ausência do sinal.'}).status_code==200
    analytics=a.get('/api/v1/analytics').json()
    assert analytics['false_positive_rate']==1
    result=a.get('/api/v1/audit/verify')
    assert result.status_code==200,result.text
    assert result.json()['invalid']==[]


def test_document_encryption_pdf_and_tenant_isolation(clients):
    a,b,factory=clients
    case=a.post('/api/v1/investigations',json={'title':'Caso de teste documental','note':'Anexar evidência de teste isolada.'}).json()['id']
    raw=b'Evidencia autorizada para teste.'
    result=a.post(f'/api/v1/investigations/{case}/attachments',files={'file':('documento.txt',raw,'text/plain')})
    assert result.status_code==200,result.text
    key=result.json()['id']
    with factory() as db:
        doc=db.get(Attachment,key)
        assert doc.ciphertext.startswith('enc:')
        assert raw.decode() not in doc.ciphertext
    assert a.get('/api/v1/attachments/'+key).content==raw
    assert b.get('/api/v1/attachments/'+key).status_code==404
    pdf=a.get(f'/api/v1/investigations/{case}/report.pdf')
    assert pdf.status_code==200,pdf.text[:300]
    assert pdf.content.startswith(b'%PDF-')
    assert b.get(f'/api/v1/investigations/{case}/report.pdf').status_code==404
    assert a.post(f'/api/v1/investigations/{case}/attachments',files={'file':('falso.pdf',b'not pdf','application/pdf')}).status_code==422


def test_mfa_enrollment_revokes_sessions_and_requires_factor(clients):
    a,_,factory=clients
    secret=a.post('/api/v1/auth/mfa/enroll').json()['secret']
    with factory() as db:
        assert db.scalar(select(User).where(User.org=='alpha')).totp is None
    assert a.post('/api/v1/auth/mfa/confirm',json={'code':pyotp.TOTP(secret).now()}).status_code==200
    assert a.get('/api/v1/auth/me').status_code==401
    with factory() as db:
        stored=db.scalar(select(User).where(User.org=='alpha')).totp
        assert stored.startswith('enc:') and secret not in stored
        assert decrypt(stored)==secret
    credentials={'email':'alpha@example.test','password':'Test-only-password-2026'}
    assert a.post('/api/v1/auth/login',json=credentials).status_code==401
    assert a.post('/api/v1/auth/login',json={**credentials,'otp':pyotp.TOTP(secret).now()}).status_code==200


def test_secret_never_returned_and_invitations_single_use(clients):
    a,b,factory=clients
    secret='test-only-cgu-token-value'
    assert a.post('/api/v1/connectors/cgu/credential',json={'value':secret}).status_code==200
    response=a.get('/api/v1/connectors/credentials')
    assert secret not in response.text
    assert b.get('/api/v1/connectors/credentials').json()==[]
    with factory() as db:
        row=db.scalar(select(Credential).where(Credential.org=='alpha'))
        assert row.ciphertext.startswith('enc:') and secret not in row.ciphertext
    invite=a.post('/api/v1/users/invitations',json={'email':'new@example.test','role':'viewer'})
    assert invite.status_code==200,invite.text
    token=invite.json()['token']
    payload={'token':token,'password':'new-user-test-password-2026'}
    assert b.post('/api/v1/users/invitations/accept',json=payload).status_code==200
    assert b.post('/api/v1/users/invitations/accept',json=payload).status_code==400


def test_cross_batch_duplicate_and_decimal_normalization(clients):
    a,_,_=clients
    for identifier,amount in [('one','100'),('two','100.00')]:
        raw=f'id,date,amount,beneficiary\n{identifier},2026-10-01,{amount},Empresa fixture\n'
        response=a.post('/api/v1/transactions/import',files={'file':('data.csv',raw,'text/csv')})
        assert response.status_code==200,response.text
    assert len(a.get('/api/v1/records/alerts').json())==1


def test_source_snapshot_preserves_history(clients,monkeypatch):
    a,_,_=clients
    payload={'external_id':'432:2026-10-01','value':'10','source':'bcb','source_url':'https://api.bcb.gov.br','reference_date':'2026-10-01'}
    monkeypatch.setattr('app.main.collect',lambda *args:[dict(payload)])
    assert a.post('/api/v1/sources/bcb/sync').status_code==200
    payload['value']='11'
    assert a.post('/api/v1/sources/bcb/sync').json()['updated']==1
    snapshots=a.get('/api/v1/records/source_snapshots').json()
    assert len(snapshots)==1 and snapshots[0]['previous']['value']=='10'


def test_chunked_upload_rejected_before_parsing(clients):
    a,_,_=clients
    response=a.post('/api/v1/auth/login',content=(b'x'*1_000_000 for _ in range(7)),headers={'Content-Type':'application/json'})
    assert response.status_code==413

def test_public_bootstrap_never_creates_human_accounts(clients,monkeypatch):
    from sqlalchemy import delete,func
    from app.db import User,Session,Record
    from app.bootstrap_sources import bootstrap_public_data
    a,b,factory=clients
    monkeypatch.setenv('BANKGUARD_BOOTSTRAP_PUBLIC_DATA','true')
    monkeypatch.setattr('app.bootstrap_sources.DB',factory)
    assert bootstrap_public_data()['skipped']=='organization_already_configured'
    with factory() as db:
        db.execute(delete(Session))
        db.execute(delete(User))
        db.commit()
    monkeypatch.setattr('app.bootstrap_sources.collect',lambda source,*args:[{'external_id':source+':fixture','source':source,'source_url':'https://api.bcb.gov.br/','value':'test-fixture-only'}])
    result=bootstrap_public_data()
    assert result['bcb']['connected'] and result['pncp']['connected']
    with factory() as db:
        assert db.scalar(select(func.count()).select_from(User))==0
        assert db.scalar(select(func.count()).select_from(Record).where(Record.org=='primary',Record.kind.in_(['contracts','indicators'])))==2


def test_initial_setup_single_use(clients,monkeypatch):
    from sqlalchemy import delete
    from app.db import User,Session
    a,_,factory=clients
    token='test-only-bootstrap-'+('b'*32)
    monkeypatch.setenv('BANKGUARD_BOOTSTRAP_TOKEN',token)
    with factory() as db:
        db.execute(delete(Session))
        db.execute(delete(User))
        db.commit()
    payload={'token':token,'organization':'Organização teste isolada','email':'owner@example.test','password':'owner-test-password-2026'}
    assert a.post('/api/v1/auth/setup',json=payload).status_code==200
    assert a.post('/api/v1/auth/setup',json=payload).status_code==409
    assert a.post('/api/v1/auth/login',json={'email':payload['email'],'password':payload['password']}).status_code==200
    assert a.get('/api/v1/organization').json()['settings']['auto_sync'] is True
