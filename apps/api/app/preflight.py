"""Fail closed before opening a production listener. Never print secrets."""
import os
from urllib.parse import urlsplit
from cryptography.fernet import Fernet


def validate():
    if os.getenv('APP_ENV')!='production':
        return
    Fernet(os.environ['BANKGUARD_ENCRYPTION_KEY'].encode())
    if len(os.environ['BANKGUARD_AUDIT_KEY'])<32:
        raise RuntimeError('Chave de auditoria insuficiente')
    url=os.environ['DATABASE_URL']
    if not url.startswith('postgresql+psycopg://'):
        raise RuntimeError('Produção requer PostgreSQL dedicado')
    origin=urlsplit(os.environ['PUBLIC_ORIGIN'])
    if origin.scheme!='https' or not origin.hostname or origin.path not in ('','/'):
        raise RuntimeError('PUBLIC_ORIGIN deve usar HTTPS e não conter caminho')
    if not os.environ.get('REDIS_URL','').startswith('redis://'):
        raise RuntimeError('Fila Redis não configurada')
    if os.getenv('BANKGUARD_BOOTSTRAP_TOKEN') and len(os.environ['BANKGUARD_BOOTSTRAP_TOKEN'])<32:
        raise RuntimeError('Código de instalação insuficiente')


if __name__=='__main__':
    try:
        validate()
        print('Configuração de produção validada; segredos preservados.')
    except Exception:
        raise SystemExit('Configuração de produção incompleta. Confira criptografia, auditoria, PostgreSQL, Redis e PUBLIC_ORIGIN no ambiente seguro.')
