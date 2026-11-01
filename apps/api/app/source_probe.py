"""Live public-source smoke test in an isolated in-memory database."""
import json
from sqlalchemy import create_engine, select, func
from sqlalchemy.orm import sessionmaker
from .db import Base, User, Record
from . import models
from .connectors import collect
from .synchronization import synchronize


def main():
    engine=create_engine('sqlite://')
    Base.metadata.create_all(engine)
    session=sessionmaker(engine,expire_on_commit=False)
    result={}
    with session() as db:
        user=User(id='isolated-source-probe',org='isolated-probe',email='source-probe@example.test',password='not-an-authentication-account',role='admin')
        db.add(user)
        db.commit()
        for source in ('bcb','pncp'):
            try:
                state=synchronize(source,user,db,collect)
                result[source]={'connected':True,'received':state['received'],'scope':state.get('scope'),'at':state['last_success']}
            except Exception:
                result[source]={'connected':False,'error':'Consulta oficial indisponível neste ambiente'}
        result['stored_records']=db.scalar(select(func.count()).select_from(Record).where(Record.org==user.org,Record.kind.in_(['indicators','contracts'])))
    print(json.dumps(result,ensure_ascii=False))
    if not result['stored_records']:
        raise SystemExit(1)


if __name__=='__main__':
    main()
