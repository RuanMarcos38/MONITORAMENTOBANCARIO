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
    print(json.dumps(bootstrap_public_data(),ensure_ascii=False))
