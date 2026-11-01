"""Populate only real public records for the initial organization, without accounts or fixtures."""
import os
from types import SimpleNamespace
from sqlalchemy import select
from .db import DB, User, Record
from .connectors import collect
from .synchronization import synchronize


def bootstrap_public_data():
    if os.getenv('BANKGUARD_BOOTSTRAP_PUBLIC_DATA')!='true':
        return {'enabled':False}
    result={}
    with DB() as db:
        # Once a human has configured the platform, their preferences control all collection.
        if db.scalar(select(User)):
            return {'skipped':'organization_already_configured'}
        principal=SimpleNamespace(id='system:public-bootstrap',org='primary',role='admin')
        for source in ('bcb','pncp'):
            state=db.scalar(select(Record).where(Record.org=='primary',Record.kind=='source_state',Record.external_id==source))
            if state and state.data.get('last_success'):
                result[source]={'already_collected':True}
                continue
            try:
                state=synchronize(source,principal,db,collect)
                result[source]={'received':state['received'],'connected':True}
            except Exception:
                result[source]={'connected':False,'notice':'Falha na fonte oficial; nenhum registro simulado.'}
    return result


if __name__=='__main__':
    import json
    result=bootstrap_public_data()
    print(json.dumps(result,ensure_ascii=False))
    if os.getenv('BACKUP_ENABLED')=='true' and not result.get('skipped'):
        from datetime import datetime,timezone
        from pathlib import Path
        from .backup import backup_to,verified_frames
        target=Path(os.getenv('BACKUP_DIR','/data/backups'))/('initial-'+datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%S')+'.enc')
        meta=backup_to(target)
        verified=sum(1 for _ in verified_frames(target))
        with DB() as db:
            db.add(Record(org='system',kind='backup_history',external_id=target.name,data={**meta,'verified_rows':verified}))
            db.commit()
        print(json.dumps({'initial_backup_verified':verified==meta['rows']}))
