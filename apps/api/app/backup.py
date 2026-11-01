"""Authenticated, encrypted, complete database snapshots and guarded restoration.

Format: encrypted ordered NDJSON frames with a final authenticated digest.
Restoration never overwrites an existing database or deletes existing data.
"""
import hashlib
import json
import os
from pathlib import Path
from datetime import datetime, timezone
from sqlalchemy import create_engine, select, inspect
from .db import Base, engine
from . import models
from .security import cipher


def canonical(value):
    return json.dumps(value,ensure_ascii=False,sort_keys=True,separators=(',', ':')).encode()


def backup_to(path, source_engine=None):
    source=source_engine or engine
    target=Path(path)
    target.parent.mkdir(parents=True,exist_ok=True)
    encryption=cipher()
    count=0
    digest=hashlib.sha256()
    with target.open('xb') as output:
        os.chmod(target,0o600)
        output.write(b'BANKGUARD-BACKUP-1\n')
        connection=source.connect()
        if source.dialect.name=='postgresql':
            connection=connection.execution_options(isolation_level='REPEATABLE READ')
        with connection,connection.begin():
            for table in Base.metadata.sorted_tables:
                for row in connection.execute(select(table)).mappings():
                    frame=canonical({'index':count,'table':table.name,'row':dict(row)})
                    digest.update(frame)
                    output.write(encryption.encrypt(frame)+b'\n')
                    count+=1
        output.write(encryption.encrypt(canonical({'index':count,'end':True,'rows':count,'digest':digest.hexdigest()}))+b'\n')
        output.flush()
        os.fsync(output.fileno())
    return {'rows':count,'digest':digest.hexdigest(),'format':'BANKGUARD-BACKUP-1','created':datetime.now(timezone.utc).isoformat()}


def verified_frames(path):
    encryption=cipher()
    digest=hashlib.sha256()
    count=0
    ended=False
    with Path(path).open('rb') as source:
        if source.readline()!=b'BANKGUARD-BACKUP-1\n':
            raise ValueError('Formato de backup inválido')
        for encrypted in source:
            if ended:
                raise ValueError('Conteúdo após o fechamento do backup')
            plain=encryption.decrypt(encrypted.strip())
            frame=json.loads(plain)
            if frame['index']!=count:
                raise ValueError('Sequência do backup inválida')
            if frame.get('end'):
                if frame['rows']!=count or frame['digest']!=digest.hexdigest():
                    raise ValueError('Integridade do backup inválida')
                ended=True
                continue
            if frame.get('table') not in Base.metadata.tables or not isinstance(frame.get('row'),dict):
                raise ValueError('Tabela ou registro não reconhecido')
            digest.update(plain)
            count+=1
            yield frame
    if not ended:
        raise ValueError('Backup incompleto: fechamento autenticado ausente')


def restore_to_empty(path,target_engine):
    # Verify the complete archive before creating or inserting anything.
    count=sum(1 for _ in verified_frames(path))
    if inspect(target_engine).get_table_names():
        raise ValueError('Restauração exige um banco completamente vazio e isolado')
    with target_engine.begin() as connection:
        Base.metadata.create_all(connection)
        for frame in verified_frames(path):
            connection.execute(Base.metadata.tables[frame['table']].insert().values(**frame['row']))
    return {'restored_rows':count,'notice':'Requer a mesma chave de criptografia da origem para abrir segredos e anexos.'}


if __name__=='__main__':
    import argparse
    parser=argparse.ArgumentParser()
    parser.add_argument('operation',choices=['backup','verify','restore'])
    parser.add_argument('path')
    args=parser.parse_args()
    if args.operation=='backup':
        print(json.dumps(backup_to(args.path)))
    elif args.operation=='verify':
        print(json.dumps({'verified_rows':sum(1 for _ in verified_frames(args.path))}))
    else:
        from sqlalchemy.engine import make_url
        url=os.environ.get('BANKGUARD_RESTORE_URL','')
        target=make_url(url)
        source=make_url(os.environ.get('DATABASE_URL','sqlite:///./bankguard.db'))
        if target.database==source.database or not str(target.database).endswith('_restore'):
            raise SystemExit('Defina BANKGUARD_RESTORE_URL para um banco vazio com nome terminado em _restore, diferente da origem.')
        print(json.dumps(restore_to_empty(args.path,create_engine(url))))
