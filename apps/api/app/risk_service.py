"""Versioned risk publication and documented public-source screening."""
from datetime import datetime
from decimal import Decimal
from sqlalchemy import select
from .db import Record, now
from .models import Organization
from .security import fingerprint
from .risk import evaluate


def publish(db,user,data,key):
    from .main import write
    old=db.scalar(select(Record).where(Record.org==user.org,Record.kind=='alerts',Record.external_id==key))
    if old:
        return old,False
    alert=write(db,user,'alerts',{**data,'detected_at':now(),'human_review':True,'status':'Novo','owner':user.id},key)
    write(db,user,'notifications',{'title':data['title'],'alert_id':alert.id,'read':False},'alert:'+key)
    org=db.get(Organization,user.org)
    if org and org.settings.get('auto_cases'):
        write(db,user,'investigations',{'title':data['title'],'status':'Em análise','owner':user.id,'evidence':[{'alert_id':alert.id,'snapshot':alert.data}],'timeline':[{'at':now(),'actor':'risk-engine','note':'Caso aberto automaticamente para revisão humana.'}]},'auto:'+key)
    return alert,True


def date_value(value):
    if not value:
        return None
    text=str(value)
    for fmt in ('%Y-%m-%d','%d/%m/%Y'):
        try:
            return datetime.strptime(text[:10],fmt).date()
        except ValueError:
            continue
    return None


def run_risk(db,user):
    transactions=db.scalars(select(Record).where(Record.org==user.org,Record.kind=='transactions').order_by(Record.created,Record.external_id)).all()
    created=0
    for alert in evaluate([r.data for r in transactions]):
        _,fresh=publish(db,user,alert,'risk-v1:'+alert['transaction_id'])
        created+=int(fresh)
    sanctions=db.scalars(select(Record).where(Record.org==user.org,Record.kind=='sanctions')).all()
    contracts=db.scalars(select(Record).where(Record.org==user.org,Record.kind=='contracts')).all()
    for contract in contracts:
        original=contract.data.get('original',{})
        supplier=str(original.get('niFornecedor',''))
        signed=date_value(original.get('dataAssinatura'))
        if not supplier or not signed:
            continue
        for sanction in sanctions:
            if supplier!=sanction.data.get('company_cnpj'):
                continue
            s=sanction.data.get('original',{})
            start=date_value(s.get('dataInicioSancao'))
            end=date_value(s.get('dataFimSancao'))
            if not start or signed<start or (end and signed>end):
                continue
            data={'title':'Contrato e sanção com coincidência de CNPJ e período','category':'Sanções e contratos','severity':'Alto','score':60,'version':'public-1.0.0','confidence':'limitada à correspondência documental','data_quality':'fontes oficiais com abrangência jurídica ainda não verificada','false_positive_risk':'Escopo territorial, efeitos da sanção, recursos e exceções podem afastar incompatibilidade.','scope_verified':False,'factors':[{'rule':'cnpj_date_overlap','points':60,'reason':'Mesmo identificador empresarial e data de assinatura dentro do período disponível da sanção.'}],'evidence':[{'record_id':contract.id,'source_url':contract.data.get('source_url'),'original':original},{'record_id':sanction.id,'source_url':sanction.data.get('source_url'),'original':s}],'reference_date':signed.isoformat(),'recommendation':'Verificar vigência, abrangência, objeto e efeitos jurídicos antes de concluir irregularidade.'}
            _,fresh=publish(db,user,data,'public-1:'+contract.id+':'+sanction.id)
            created+=int(fresh)
    return {'created':created,'transactions_evaluated':len(transactions),'contracts_evaluated':len(contracts),'sanctions_available':len(sanctions)}
