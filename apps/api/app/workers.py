"""Persistent database job state with Celery delivery and bounded recovery."""
import os
from datetime import datetime, timezone, timedelta
from celery import Celery
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from .db import DB, User, Record, now
from .models import Job, Organization

celery=Celery('bankguard',broker=os.getenv('REDIS_URL','redis://127.0.0.1:6379/0'))
celery.conf.update(task_serializer='json',accept_content=['json'],result_serializer='json',timezone='America/Sao_Paulo',enable_utc=True,task_acks_late=True,task_reject_on_worker_lost=True,worker_prefetch_multiplier=1,broker_connection_retry_on_startup=True,task_soft_time_limit=280,task_time_limit=300,beat_schedule={'dispatch':{'task':'bankguard.dispatch','schedule':60.0}})


@celery.task(name='bankguard.dispatch')
def dispatch():
    current=datetime.now(timezone.utc)
    with DB() as db:
        for org in db.scalars(select(Organization)):
            if not org.settings.get('auto_sync'):
                continue
            for source,seconds in [('bcb',86400),('pncp',900),('cgu',14400),('risk',600),('digest',86400)]:
                if source=='cgu':
                    from .models import Credential
                    if not db.scalar(select(Credential).where(Credential.org==org.id,Credential.provider=='cgu')):
                        continue
                window=str(int(current.timestamp())//seconds)
                if not db.scalar(select(Job).where(Job.org==org.id,Job.source==source,Job.window==window)):
                    db.add(Job(org=org.id,source=source,window=window,state='queued',attempts=0,checkpoint={}))
        try:
            db.commit()
        except IntegrityError:
            db.rollback()
        cutoff=(current-timedelta(minutes=15)).isoformat()
        stale=db.scalars(select(Job).where(Job.state.in_(['running','dispatched']),Job.updated<cutoff)).all()
        for job in stale:
            job.state='queued' if job.attempts<5 else 'dead_letter'
            job.updated=now()
        db.commit()
        pending=db.scalars(select(Job).where(Job.state.in_(['queued','retry'])).with_for_update(skip_locked=True).limit(25)).all()
        keys=[]
        for job in pending:
            if job.state=='retry' and job.updated>(current-timedelta(seconds=min(3600,30*2**job.attempts))).isoformat():
                continue
            job.state='dispatched'
            job.updated=now()
            keys.append(job.id)
        db.commit()
        for key in keys:
            execute.delay(key)
        tick=db.scalar(select(Record).where(Record.org=='system',Record.kind=='heartbeat',Record.external_id=='scheduler'))
        if tick:
            tick.data={'last_tick':now()}
        else:
            db.add(Record(org='system',kind='heartbeat',external_id='scheduler',data={'last_tick':now()}))
        db.commit()
    return {'dispatched':len(keys)}


@celery.task(name='bankguard.execute')
def execute(key):
    from .connectors import collect
    from .synchronization import synchronize
    from .risk_service import run_risk
    from .main import write, audit
    with DB() as db:
        job=db.scalar(select(Job).where(Job.id==key).with_for_update())
        if not job or job.state not in ('dispatched','queued'):
            return {'skipped':True}
        job.state='running'
        job.attempts+=1
        job.updated=now()
        db.commit()
        user=db.scalar(select(User).where(User.org==job.org,User.role=='admin'))
        if not user:
            job.state='dead_letter'
            job.error='Organização sem administrador ativo'
            db.commit()
            return {'failed':True}
        try:
            if job.source in ('bcb','pncp','cgu'):
                result=synchronize(job.source,user,db,collect)
            elif job.source=='risk':
                result=run_risk(db,user)
            elif job.source=='digest':
                from sqlalchemy import func
                count=db.scalar(select(func.count()).select_from(Record).where(Record.org==job.org,Record.kind=='alerts'))
                result={'title':'Resumo diário','alerts_total':count,'reference_date':now()[:10],'notice':'Contagem de indícios; revisão humana obrigatória.'}
                if not db.scalar(select(Record).where(Record.org==job.org,Record.kind=='reports',Record.external_id=='digest:'+job.window)):
                    write(db,user,'reports',result,'digest:'+job.window)
            else:
                raise ValueError('Tipo de tarefa inválido')
            job.state='completed'
            job.checkpoint=result
            job.error=None
            job.updated=now()
            audit(db,user,'job_completed',{'job':key,'source':job.source})
            db.commit()
            return result
        except Exception:
            db.rollback()
            job=db.get(Job,key)
            job.state='retry' if job.attempts<5 else 'dead_letter'
            job.error='Falha de integração ou processamento; detalhes sensíveis não são registrados.'
            job.updated=now()
            db.commit()
            return {'failed':True,'state':job.state}

@celery.task(name='bankguard.backup')
def backup_database():
    if os.getenv('BACKUP_ENABLED')!='true':
        return {'enabled':False}
    from .backup import backup_to, verified_frames
    from pathlib import Path
    target=Path(os.getenv('BACKUP_DIR','/data/backups'))/('bankguard-'+datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%S')+'.enc')
    result=backup_to(target)
    result['verified_rows']=sum(1 for _ in verified_frames(target))
    with DB() as db:
        db.add(Record(org='system',kind='backup_history',external_id=target.name,data=result))
        db.commit()
    return {'verified':result['rows']==result['verified_rows']}

celery.conf.beat_schedule['daily-encrypted-backup']={'task':'bankguard.backup','schedule':86400.0}
