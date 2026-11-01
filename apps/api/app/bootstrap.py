"""Local administrative provisioning; no public signup or default passwords."""
import getpass
import uuid
import pyotp
from sqlalchemy import select
from .db import DB, User
from .main import hasher
from .security import encrypt
from .models import Organization

def main():
    email=input('E-mail do administrador: ').strip().lower()
    password=getpass.getpass('Senha (mínimo 12 caracteres): ')
    if '@' not in email or len(password)<12:
        raise SystemExit('E-mail ou senha inválidos')
    secret=pyotp.random_base32()
    print('Cadastre no autenticador (não salve em logs):', pyotp.TOTP(secret).provisioning_uri(email, issuer_name='BankGuard AI'))
    if not pyotp.TOTP(secret).verify(input('Código do autenticador: ').strip(),valid_window=1):
        raise SystemExit('Código inválido')
    with DB() as db:
        if db.scalar(select(User).where(User.email==email)):
            raise SystemExit('Usuário já existe')
        org=Organization(id=str(uuid.uuid4()),name='Minha organização',settings={'auto_sync':False,'auto_cases':False})
        db.add(org)
        db.add(User(org=org.id,email=email,password=hasher.hash(password),totp=encrypt(secret),role='admin'))
        db.commit()
    print('Organização e administrador criados. Segredo do autenticador armazenado com criptografia.')

if __name__=='__main__':
    main()
