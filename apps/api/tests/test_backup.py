import pytest
from cryptography.fernet import Fernet
from sqlalchemy import create_engine,select
from sqlalchemy.orm import Session
from app.db import Base,User
from app.backup import backup_to,verified_frames,restore_to_empty


def test_backup_authentication_and_restore(tmp_path,monkeypatch):
    monkeypatch.setenv('BANKGUARD_ENCRYPTION_KEY',Fernet.generate_key().decode())
    source=create_engine('sqlite://')
    Base.metadata.create_all(source)
    with Session(source) as db:
        db.add(User(org='test',email='backup@example.test',password='test-hash',role='viewer'))
        db.commit()
    path=tmp_path/'snapshot.enc'
    meta=backup_to(path,source)
    assert meta['rows']==1
    assert b'backup@example.test' not in path.read_bytes()
    assert len(list(verified_frames(path)))==1
    target=create_engine('sqlite://')
    assert restore_to_empty(path,target)['restored_rows']==1
    with Session(target) as db:
        assert db.scalar(select(User)).email=='backup@example.test'
    with pytest.raises(ValueError):
        restore_to_empty(path,target)
    truncated=tmp_path/'truncated.enc'
    truncated.write_bytes(b'\n'.join(path.read_bytes().splitlines()[:-1])+b'\n')
    with pytest.raises(ValueError):
        list(verified_frames(truncated))
