"""Administrative, investigative and operational product workflows."""
import base64
import hashlib
import hmac
import io
import os
import secrets
import uuid
from collections import Counter
from datetime import datetime, timezone, timedelta, date
from html import escape
from urllib.parse import quote
from fastapi import APIRouter, HTTPException, Request, Response, UploadFile
from pydantic import BaseModel, Field, HttpUrl
from sqlalchemy import select, func, delete
from sqlalchemy.exc import IntegrityError
import pyotp
from .main import Actor, Db, audit, write, hasher
from .db import User, Session, Record, now
from .models import Organization, Credential, Job, Attachment
from .security import encrypt, decrypt, cnpj, fingerprint, sign
from .risk_service import date_value

router = APIRouter(prefix='/api/v1')
STATES = {'Novo','Em análise','Aguardando informações','Confirmado como irregularidade após verificação','Falso positivo','Resolvido','Arquivado'}


def admin(user):
    if user.role != 'admin':
        raise HTTPException(403, 'Operação exclusiva do administrador da organização')


def owned(db, user, kind, key):
    row=db.scalar(select(Record).where(Record.org==user.org, Record.kind==kind, Record.id==key).with_for_update())
    if not row:
        raise HTTPException(404, 'Registro não encontrado nesta organização')
    return row


def serial(row):
    return {**row.data,'id':row.id,'created':row.created,'source_record_id':row.external_id}


@router.get('/auth/setup/status')
def setup_status(db: Db):
    return {'required':not bool(db.scalar(select(func.count()).select_from(User))), 'enabled':bool(os.getenv('BANKGUARD_BOOTSTRAP_TOKEN'))}


class Setup(BaseModel):
    token: str = Field(min_length=24,max_length=256)
    organization: str = Field(min_length=3,max_length=120)
    email: str = Field(min_length=5,max_length=254)
    password: str = Field(min_length=14,max_length=256)


@router.post('/auth/setup')
def setup(body: Setup, db: Db):
    expected=os.getenv('BANKGUARD_BOOTSTRAP_TOKEN','')
    if not expected or not hmac.compare_digest(expected,body.token):
        raise HTTPException(403,'Código de instalação inválido')
    if db.scalar(select(func.count()).select_from(User)):
        raise HTTPException(409,'A instalação inicial já foi concluída')
    if '@' not in body.email:
        raise HTTPException(422,'E-mail inválido')
    try:
        org=Organization(id='primary',name=body.organization,settings={'plan':'free','auto_sync':True,'auto_cases':False,'notifications':False})
        db.add(org)
        user=User(org=org.id,email=body.email.lower(),password=hasher.hash(body.password),role='admin')
        db.add(user)
        db.flush()
        audit(db,user,'installation_completed',org.id)
        db.commit()
    except IntegrityError:
        db.rollback()
        raise HTTPException(409,'A instalação já foi iniciada por outro processo')
    return {'ok':True,'next':'Faça login e cadastre seu autenticador.'}


@router.post('/auth/mfa/enroll')
def enroll(user: Actor, db: Db):
    if user.totp:
        raise HTTPException(409,'Autenticador já configurado')
    pending=db.scalar(select(Record).where(Record.org==user.org,Record.kind=='mfa_pending',Record.external_id==user.id))
    secret=pyotp.random_base32()
    data={'ciphertext':encrypt(secret),'expires':(datetime.now(timezone.utc)+timedelta(minutes=10)).isoformat()}
    if pending:
        pending.data=data
    else:
        write(db,user,'mfa_pending',data,user.id)
    db.commit()
    return {'secret':secret,'uri':pyotp.TOTP(secret).provisioning_uri(user.email,issuer_name='BankGuard AI')}


class OTP(BaseModel):
    code: str = Field(pattern=r'^\d{6}$')


@router.post('/auth/mfa/confirm')
def confirm_mfa(body: OTP, user: Actor, db: Db):
    pending=db.scalar(select(Record).where(Record.org==user.org,Record.kind=='mfa_pending',Record.external_id==user.id))
    if not pending or pending.data['expires']<now():
        raise HTTPException(400,'Cadastro do autenticador expirado')
    secret=decrypt(pending.data['ciphertext'])
    if not pyotp.TOTP(secret).verify(body.code,valid_window=1):
        raise HTTPException(400,'Código inválido')
    user.totp=encrypt(secret)
    db.delete(pending)
    audit(db,user,'mfa_enabled',user.id)
    # Existing sessions are revoked so the next login verifies the newly enrolled factor.
    db.execute(delete(Session).where(Session.user_id==user.id))
    db.commit()
    return {'ok':True,'login_required':True}


@router.get('/users')
def list_users(user: Actor, db: Db):
    admin(user)
    return [{'id':u.id,'email':u.email,'role':u.role,'mfa':bool(u.totp)} for u in db.scalars(select(User).where(User.org==user.org))]


class Invite(BaseModel):
    email: str = Field(min_length=5,max_length=254)
    role: str


@router.post('/users/invitations')
def invitation(body: Invite, user: Actor, db: Db):
    admin(user)
    if body.role not in ('admin','analyst','auditor','viewer') or '@' not in body.email:
        raise HTTPException(422,'Perfil ou e-mail inválido')
    if db.scalar(select(User).where(User.email==body.email.lower())):
        raise HTTPException(409,'E-mail já cadastrado')
    token=secrets.token_urlsafe(32)
    write(db,user,'invitation',{'email':body.email.lower(),'role':body.role,'expires':(datetime.now(timezone.utc)+timedelta(hours=24)).isoformat()},hashlib.sha256(token.encode()).hexdigest())
    audit(db,user,'invitation_created',body.email.lower())
    db.commit()
    return {'token':token,'expires_in_hours':24,'notice':'Compartilhe o link com o destinatário por canal autorizado. Nenhum e-mail foi enviado.'}


class Acceptance(BaseModel):
    token: str = Field(min_length=24,max_length=256)
    password: str = Field(min_length=14,max_length=256)


@router.post('/users/invitations/accept')
def accept(body: Acceptance, db: Db):
    digest=hashlib.sha256(body.token.encode()).hexdigest()
    invite=db.scalar(select(Record).where(Record.kind=='invitation',Record.external_id==digest).with_for_update())
    if not invite or invite.data['expires']<now() or invite.data.get('used'):
        raise HTTPException(400,'Convite inválido ou expirado')
    u=User(org=invite.org,email=invite.data['email'],password=hasher.hash(body.password),role=invite.data['role'])
    db.add(u)
    invite.data={**invite.data,'used':True}
    try:
        db.flush()
        audit(db,u,'invitation_accepted',u.id)
        db.commit()
    except IntegrityError:
        db.rollback()
        raise HTTPException(409,'Convite já utilizado')
    return {'ok':True}


class Role(BaseModel):
    role: str


@router.post('/users/{key}/role')
def update_role(key: str, body: Role, user: Actor, db: Db):
    admin(user)
    target=db.scalar(select(User).where(User.id==key,User.org==user.org).with_for_update())
    if not target:
        raise HTTPException(404)
    if key==user.id or body.role not in ('admin','analyst','auditor','viewer'):
        raise HTTPException(422,'Não é possível alterar seu próprio perfil')
    target.role=body.role
    db.execute(delete(Session).where(Session.user_id==target.id))
    audit(db,user,'role_updated',{'user':key,'role':body.role})
    db.commit()
    return {'ok':True}


@router.post('/users/{key}/revoke-sessions')
def revoke(key: str, user: Actor, db: Db):
    admin(user)
    target=db.scalar(select(User).where(User.id==key,User.org==user.org))
    if not target:
        raise HTTPException(404)
    db.execute(delete(Session).where(Session.user_id==key))
    audit(db,user,'sessions_revoked',key)
    db.commit()
    return {'ok':True}


@router.get('/organization')
def organization(user: Actor, db: Db):
    org=db.get(Organization,user.org)
    return {'id':user.org,'name':org.name if org else 'Minha organização','settings':org.settings if org else {'plan':'free','auto_sync':False,'auto_cases':False,'notifications':False}}


class Preferences(BaseModel):
    name: str = Field(min_length=3,max_length=120)
    auto_sync: bool = False
    auto_cases: bool = False
    notifications: bool = False
    retention_days: int = Field(default=365,ge=30,le=3650)


@router.post('/organization')
def preferences(body: Preferences, user: Actor, db: Db):
    admin(user)
    org=db.get(Organization,user.org)
    if not org:
        org=Organization(id=user.org,name=body.name,settings={})
        db.add(org)
    org.name=body.name
    org.settings={**org.settings,**body.model_dump(exclude={'name'})}
    audit(db,user,'preferences_updated',body.model_dump())
    db.commit()
    return {'ok':True}


@router.get('/plans')
def plans(user: Actor):
    return {'billing_enabled':False,'plans':[{'id':'free','name':'Gratuito','limit':1000},{'id':'professional','name':'Profissional','limit':100000},{'id':'enterprise','name':'Empresarial','limit':1000000},{'id':'institutional','name':'Institucional','limit':10000000}],'notice':'Catálogo administrativo. Nenhuma assinatura paga é ativada.'}


class Company(BaseModel):
    cnpj: str
    name: str = Field(min_length=3,max_length=200)
    uf: str = Field(pattern=r'^[A-Z]{2}$')
    municipality: str = Field(default='',max_length=120)
    purpose: str = Field(min_length=10,max_length=1000)


@router.post('/companies')
def company(body: Company, user: Actor, db: Db):
    try:
        identifier=cnpj(body.cnpj)
    except ValueError as exc:
        raise HTTPException(422,str(exc))
    old=db.scalar(select(Record).where(Record.org==user.org,Record.kind=='companies',Record.external_id==identifier))
    if old:
        raise HTTPException(409,'Empresa já monitorada')
    record=write(db,user,'companies',{**body.model_dump(),'cnpj':identifier,'origin':'Cadastro autorizado pelo cliente','official_verified':False,'reference_date':now()[:10]},identifier)
    audit(db,user,'company_added',record.id)
    db.commit()
    return serial(record)


class ManualAlert(BaseModel):
    title: str = Field(min_length=5,max_length=200)
    category: str = Field(min_length=3,max_length=80)
    severity: str
    source_url: HttpUrl
    reference_date: date
    evidence: str = Field(min_length=20,max_length=10000)


@router.post('/alerts')
def manual_alert(body: ManualAlert, user: Actor, db: Db):
    if body.severity not in ('Crítico','Alto','Médio','Baixo','Informativo'):
        raise HTTPException(422,'Severidade inválida')
    row=write(db,user,'alerts',{**body.model_dump(mode='json'),'status':'Novo','human_review':True,'origin':'analista','owner':user.id,'score':None,'timeline':[{'at':now(),'actor':user.id,'note':'Alerta manual registrado'}]})
    write(db,user,'notifications',{'title':body.title,'alert_id':row.id,'read':False},'alert:'+row.id)
    audit(db,user,'alert_created',row.id)
    db.commit()
    return serial(row)


class AlertEvent(BaseModel):
    status: str
    note: str = Field(min_length=10,max_length=10000)
    owner: str | None = None


@router.post('/alerts/{key}/events')
def alert_event(key: str, body: AlertEvent, user: Actor, db: Db):
    if body.status not in STATES:
        raise HTTPException(422,'Estado inválido')
    row=owned(db,user,'alerts',key)
    if body.owner and not db.scalar(select(User).where(User.id==body.owner,User.org==user.org)):
        raise HTTPException(422,'Responsável fora da organização')
    row.data={**row.data,'status':body.status,'owner':body.owner or row.data.get('owner',user.id),'timeline':row.data.get('timeline',[])+[{'at':now(),'actor':user.id,'status':body.status,'note':body.note}]}
    audit(db,user,'alert_updated',key)
    db.commit()
    return serial(row)


@router.post('/notifications/{key}/read')
def read_notification(key: str, user: Actor, db: Db):
    row=owned(db,user,'notifications',key)
    row.data={**row.data,'read':True}
    db.commit()
    return {'ok':True}


@router.get('/investigations/{key}')
def case_detail(key: str, user: Actor, db: Db):
    row=owned(db,user,'investigations',key)
    docs=db.scalars(select(Attachment).where(Attachment.org==user.org,Attachment.case_id==key)).all()
    return {**serial(row),'attachments':[{'id':a.id,'name':a.name,'digest':a.digest,'created':a.created} for a in docs]}


@router.post('/investigations/{key}/attachments')
async def attach(key: str, file: UploadFile, user: Actor, db: Db):
    case=owned(db,user,'investigations',key)
    raw=await file.read(5_000_001)
    name=os.path.basename((file.filename or '').replace('\\','/'))[:180]
    suffix=name.lower().rsplit('.',1)[-1]
    allowed={'pdf':'application/pdf','txt':'text/plain','csv':'text/csv','png':'image/png','jpg':'image/jpeg','jpeg':'image/jpeg'}
    if len(raw)>5_000_000 or not raw or suffix not in allowed:
        raise HTTPException(422,'Documento inválido. PDF, texto, CSV ou imagem até 5 MB.')
    if suffix=='pdf' and not raw.startswith(b'%PDF-') or suffix=='png' and not raw.startswith(b'\x89PNG\r\n\x1a\n') or suffix in ('jpg','jpeg') and not raw.startswith(b'\xff\xd8\xff'):
        raise HTTPException(422,'Conteúdo incompatível com a extensão')
    if suffix in ('txt','csv'):
        try:
            raw.decode('utf-8-sig')
        except UnicodeError:
            raise HTTPException(422,'Texto precisa estar em UTF-8')
    digest=hashlib.sha256(raw).hexdigest()
    a=Attachment(org=user.org,case_id=key,name=name,media_type=allowed[suffix],ciphertext=encrypt(base64.b64encode(raw).decode()),digest=digest)
    db.add(a)
    db.flush()
    case.data={**case.data,'timeline':case.data.get('timeline',[])+[{'at':now(),'actor':user.id,'note':'Documento anexado: '+name,'sha256':digest}]}
    audit(db,user,'document_attached',{'case':key,'id':a.id,'sha256':digest})
    db.commit()
    return {'id':a.id,'name':name,'sha256':digest}


@router.get('/attachments/{key}')
def download(key: str, user: Actor, db: Db):
    doc=db.scalar(select(Attachment).where(Attachment.id==key,Attachment.org==user.org))
    if not doc:
        raise HTTPException(404)
    content=base64.b64decode(decrypt(doc.ciphertext))
    if hashlib.sha256(content).hexdigest()!=doc.digest:
        raise HTTPException(500,'Integridade do documento inválida')
    audit(db,user,'document_downloaded',key)
    db.commit()
    return Response(content,media_type=doc.media_type,headers={'Content-Disposition':"attachment; filename*=UTF-8''"+quote(doc.name),'Content-Security-Policy':"sandbox; default-src 'none'"})


@router.get('/investigations/{key}/report.pdf')
def pdf(key: str, user: Actor, db: Db):
    case=owned(db,user,'investigations',key)
    from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer
    from reportlab.lib.styles import getSampleStyleSheet
    from reportlab.lib import colors
    styles=getSampleStyleSheet()
    stream=io.BytesIO()
    doc=SimpleDocTemplate(stream,title='BankGuard AI — Dossiê de investigação',author='BankGuard AI')
    story=[]
    def paragraph(text, style='Normal'):
        story.append(Paragraph(escape(str(text)).replace('\n','<br/>'),styles[style]))
        story.append(Spacer(1,10))
    paragraph('BANKGUARD AI — DOSSIÊ','Title')
    paragraph(case.data['title'],'Heading1')
    paragraph('Caso: '+key+' | Emitido: '+now()+' | Estado: '+case.data['status'])
    paragraph('Responsável: '+str(case.data.get('owner','Não atribuído')))
    paragraph('Objetivo e metodologia','Heading2')
    paragraph('Relatório descritivo de registros, documentos e eventos inseridos na organização. Regras determinísticas priorizam revisão humana; não produzem conclusão criminal.')
    paragraph('Cronologia e notas','Heading2')
    for event in case.data.get('timeline',[]):
        paragraph(event.get('at','')+' — '+event.get('note','')[:10000])
    paragraph('Evidências e fontes','Heading2')
    for evidence in case.data.get('evidence',[]):
        paragraph(str(evidence)[:12000])
    for a in db.scalars(select(Attachment).where(Attachment.org==user.org,Attachment.case_id==key)):
        paragraph(a.name+' | SHA-256: '+a.digest+' | '+a.created)
    paragraph('Limitações e recomendações','Heading2')
    paragraph('Verificar autenticidade, vigência, abrangência das sanções, contexto contratual e justificativas. Campos ausentes não são presumidos. Um indício ou score não confirma irregularidade ou crime. Revisão humana e fundamento documental são obrigatórios.')
    paragraph('Revisão e integridade','Heading2')
    paragraph('Emitido por '+user.email+'. Hash do conteúdo do caso: '+fingerprint(case.data))
    doc.build(story)
    audit(db,user,'case_pdf_exported',key)
    db.commit()
    return Response(stream.getvalue(),media_type='application/pdf',headers={'Content-Disposition':f'attachment; filename="bankguard-caso-{key}.pdf"'})


@router.get('/relationships/graph')
def graph(user: Actor, db: Db):
    nodes={}
    edges=[]
    for r in db.scalars(select(Record).where(Record.org==user.org,Record.kind=='contracts').limit(1000)):
        original=r.data.get('original',{})
        supplier=original.get('niFornecedor')
        agency=original.get('orgaoEntidade',{}).get('cnpj')
        if not supplier or not agency:
            continue
        ids=['contract:'+r.id,'supplier:'+supplier,'agency:'+agency]
        for key,label,kind in zip(ids,[original.get('numeroContratoEmpenho') or r.external_id,original.get('nomeRazaoSocialFornecedor') or supplier,original.get('orgaoEntidade',{}).get('razaoSocial') or agency],['Contrato','Fornecedor','Órgão']):
            nodes[key]={'id':key,'label':str(label),'kind':kind}
        for entity in ids[1:]:
            edges.append({'source':entity,'target':ids[0],'documented':True,'source_url':r.data.get('source_url'),'record_id':r.id})
    return {'nodes':list(nodes.values()),'edges':edges,'limit':1000,'notice':'Somente vínculos explicitamente documentados nos contratos coletados. Sem inferência pessoal.'}


@router.get('/analytics')
def analytics(user: Actor, db: Db):
    alerts=db.scalars(select(Record).where(Record.org==user.org,Record.kind=='alerts')).all()
    by_day=Counter(r.created[:10] for r in alerts)
    by_status=Counter(r.data.get('status','Novo') for r in alerts)
    by_severity=Counter(r.data.get('severity','Não classificado') for r in alerts)
    by_category=Counter(r.data.get('category','Transacional') for r in alerts)
    uf=Counter(r.data.get('uf') for r in db.scalars(select(Record).where(Record.org==user.org,Record.kind=='companies')) if r.data.get('uf'))
    reviewed=sum(by_status[s] for s in ('Falso positivo','Resolvido','Confirmado como irregularidade após verificação'))
    return {'days':[{'date':k,'count':v} for k,v in sorted(by_day.items())],'severity':dict(by_severity),'categories':dict(by_category),'status':dict(by_status),'uf':dict(uf),'false_positive_rate':round(by_status['Falso positivo']/reviewed,4) if reviewed else None,'reviewed':reviewed,'calculated_at':now()}


@router.get('/audit/verify')
def verify_audit(user: Actor, db: Db):
    admin(user)
    checked=0
    legacy=0
    invalid=[]
    for r in db.scalars(select(Record).where(Record.org==user.org,Record.kind=='audit')):
        payload=dict(r.data)
        signature=payload.pop('signature',None)
        if not signature:
            legacy+=1
        else:
            checked+=1
            if not hmac.compare_digest(signature,sign(payload)):
                invalid.append(r.id)
    return {'verified':checked,'legacy_unsigned':legacy,'invalid':invalid,'valid':not invalid,'notice':'Assinatura detecta alteração do conteúdo; não comprova ausência de exclusão. Exporte auditoria para armazenamento imutável.'}


class Secret(BaseModel):
    value: str = Field(min_length=8,max_length=10000)


@router.post('/connectors/{provider}/credential')
def credential(provider: str, body: Secret, user: Actor, db: Db):
    admin(user)
    if provider not in ('cgu','webhook'):
        raise HTTPException(422,'Provedor não suportado')
    row=db.scalar(select(Credential).where(Credential.org==user.org,Credential.provider==provider))
    if row:
        row.ciphertext=encrypt(body.value)
        row.updated=now()
    else:
        db.add(Credential(org=user.org,provider=provider,ciphertext=encrypt(body.value)))
    audit(db,user,'credential_configured',provider)
    db.commit()
    return {'ok':True,'provider':provider,'stored_encrypted':True}


@router.get('/connectors/credentials')
def credentials(user: Actor, db: Db):
    admin(user)
    return [{'provider':r.provider,'updated':r.updated,'configured':True} for r in db.scalars(select(Credential).where(Credential.org==user.org))]


@router.get('/jobs')
def jobs(user: Actor, db: Db):
    admin(user)
    return [{'id':j.id,'source':j.source,'state':j.state,'attempts':j.attempts,'checkpoint':j.checkpoint,'updated':j.updated,'error':j.error} for j in db.scalars(select(Job).where(Job.org==user.org).order_by(Job.updated.desc()).limit(100))]


@router.post('/jobs/{key}/retry')
def retry_job(key: str, user: Actor, db: Db):
    admin(user)
    job=db.scalar(select(Job).where(Job.id==key,Job.org==user.org).with_for_update())
    if not job:
        raise HTTPException(404)
    if job.state not in ('dead_letter','failed'):
        raise HTTPException(409,'A tarefa não está em falha')
    job.state='queued'
    job.attempts=0
    job.error=None
    job.updated=now()
    audit(db,user,'job_requeued',key)
    db.commit()
    return {'queued':True}

@router.post('/risk/run')
def risk_run(user: Actor, db: Db):
    from .risk_service import run_risk
    result=run_risk(db,user)
    audit(db,user,'risk_evaluated',result)
    db.commit()
    return result


@router.get('/operations')
def operations(user: Actor, db: Db):
    admin(user)
    import redis
    redis_status='INDISPONÍVEL'
    try:
        client=redis.Redis.from_url(os.getenv('REDIS_URL','redis://127.0.0.1:6379/0'),socket_connect_timeout=2,socket_timeout=2)
        redis_status='OPERACIONAL' if client.ping() else 'INDISPONÍVEL'
    except Exception:
        pass
    heartbeat=db.scalar(select(Record).where(Record.org=='system',Record.kind=='heartbeat',Record.external_id=='scheduler'))
    last_tick=heartbeat.data.get('last_tick') if heartbeat else None
    status='OPERACIONAL' if last_tick and last_tick>(datetime.now(timezone.utc)-timedelta(minutes=3)).isoformat() else 'SEM SINAL'
    states=dict(db.execute(select(Job.state,func.count()).where(Job.org==user.org).group_by(Job.state)).all())
    backup=db.scalar(select(Record).where(Record.org=='system',Record.kind=='backup_history').order_by(Record.created.desc()).limit(1))
    backup_state={'at':backup.created,'verified':backup.data.get('rows')==backup.data.get('verified_rows')} if backup else None
    return {'last_backup':backup_state,'database':'OPERACIONAL','redis':redis_status,'scheduler':status,'last_tick':last_tick,'jobs':states,'checked_at':now()}


class Consent(BaseModel):
    institution: str = Field(min_length=3,max_length=120)
    purpose: str = Field(min_length=20,max_length=2000)
    valid_until: str = Field(pattern=r'^\d{4}-\d{2}-\d{2}$')
    authorized: bool


@router.post('/consents')
def consent(body: Consent, user: Actor, db: Db):
    admin(user)
    if not body.authorized or date_value(body.valid_until) is None or body.valid_until<now()[:10]:
        raise HTTPException(422,'Consentimento ou validade inválidos')
    row=write(db,user,'consents',{**body.model_dump(),'status':'Registrado','institutional_status':'Aguardando credenciamento','origin':'Declaração do administrador; não concede acesso bancário','registered_by':user.id})
    audit(db,user,'consent_registered',row.id)
    db.commit()
    return serial(row)


@router.post('/consents/{key}/revoke')
def revoke_consent(key: str, user: Actor, db: Db):
    admin(user)
    row=owned(db,user,'consents',key)
    row.data={**row.data,'status':'Revogado','revoked_at':now(),'revoked_by':user.id}
    audit(db,user,'consent_revoked',key)
    db.commit()
    return {'ok':True}


@router.post('/institutional/events')
def institutional_event():
    # No private banking event is accepted without an institution-specific approved adapter.
    raise HTTPException(409,'Aguardando credenciamento e homologação institucional. Nenhuma transação privada aceita.')
