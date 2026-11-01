"""Transactional source synchronization, snapshots and provenance."""
from sqlalchemy import select, func
from fastapi import HTTPException
from .db import Record, now
from .models import Credential
from .security import decrypt, fingerprint


def synchronize(source,user,db,collector):
    from .main import write, audit
    if source not in ('bcb','pncp','cgu'):
        raise HTTPException(409,'Integração pendente de credenciamento ou importação oficial')
    if db.bind.dialect.name=='postgresql':
        lock=int(fingerprint([user.org,source])[:15],16)
        db.execute(select(func.pg_advisory_xact_lock(lock)))
    state=db.scalar(select(Record).where(Record.org==user.org,Record.kind=='source_state',Record.external_id==source).with_for_update())
    previous=dict(state.data) if state else {}
    config={'checkpoint':previous.get('checkpoint',{})}
    if source=='cgu':
        secret=db.scalar(select(Credential).where(Credential.org==user.org,Credential.provider=='cgu'))
        if not secret:
            raise HTTPException(409,'Configure o token oficial da CGU')
        config['token']=decrypt(secret.ciphertext)
        config['companies']=sorted(r.external_id for r in db.scalars(select(Record).where(Record.org==user.org,Record.kind=='companies')))
        if not config['companies']:
            raise HTTPException(409,'Cadastre as empresas a monitorar antes de consultar a CGU')
    try:
        batch=collector(source,config)
        if not state:
            state=write(db,user,'source_state',{},source)
        inserted=updated=0
        kind={'bcb':'indicators','pncp':'contracts','cgu':'sanctions'}[source]
        for row in batch:
            digest=fingerprint(row)
            old=db.scalar(select(Record).where(Record.org==user.org,Record.kind==kind,Record.external_id==row['external_id']))
            if old and old.data.get('hash')!=digest:
                snapshot_id=old.id+':'+old.data.get('hash',fingerprint(old.data))
                if not db.scalar(select(Record).where(Record.org==user.org,Record.kind=='source_snapshots',Record.external_id==snapshot_id)):
                    write(db,user,'source_snapshots',{'record_id':old.id,'previous':old.data,'snapshotted_at':now()},snapshot_id)
                old.data={**row,'collected_at':old.data.get('collected_at',now()),'last_validated':now(),'version':int(old.data.get('version',1))+1,'hash':digest}
                updated+=1
            elif not old:
                write(db,user,kind,{**row,'collected_at':now(),'last_validated':now(),'version':1,'hash':digest},row['external_id'])
                inserted+=1
        state.data={'status':'OPERACIONAL' if batch or previous.get('last_success') else 'SEM DADOS','last_query':now(),'last_success':now(),'received':len(batch),'inserted':inserted,'updated':updated,'checkpoint':getattr(batch,'checkpoint',{}),'complete':getattr(batch,'complete',True),'scope':getattr(batch,'scope','Consulta oficial validada')}
        audit(db,user,'source_sync',{'source':source,'received':len(batch),'inserted':inserted,'updated':updated})
        db.commit()
        return state.data
    except Exception as exc:
        db.rollback()
        state=db.scalar(select(Record).where(Record.org==user.org,Record.kind=='source_state',Record.external_id==source))
        failed={**previous,'status':'INDISPONÍVEL','last_query':now(),'error':'Falha na consulta oficial. Último sucesso preservado; dados não simulados.'}
        if state:
            state.data=failed
        else:
            write(db,user,'source_state',failed,source)
        db.commit()
        raise HTTPException(502,'Fonte indisponível ou resposta incompatível; tente novamente mais tarde') from exc
