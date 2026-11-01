"""Cryptography and validation shared by API, workers and provisioning."""
import hashlib
import hmac
import json
import os
import re
from cryptography.fernet import Fernet, InvalidToken
from fastapi import HTTPException


def cipher():
    key = os.getenv('BANKGUARD_ENCRYPTION_KEY', '')
    if not key:
        raise HTTPException(503, 'Chave de criptografia não configurada no servidor')
    return Fernet(key.encode())


def encrypt(value):
    return 'enc:' + cipher().encrypt(value.encode()).decode()


def decrypt(value):
    if not value:
        return ''
    if not value.startswith('enc:'):
        if os.getenv('APP_ENV') == 'production':
            raise HTTPException(503, 'Segredo legado precisa de migração segura')
        return value
    try:
        return cipher().decrypt(value[4:].encode()).decode()
    except InvalidToken:
        raise HTTPException(503, 'Não foi possível abrir o segredo configurado')


def fingerprint(data):
    return hashlib.sha256(json.dumps(data, sort_keys=True, ensure_ascii=False, separators=(',', ':')).encode()).hexdigest()


def cnpj(value):
    value = re.sub(r'[./\s-]', '', value).upper()
    if not re.fullmatch(r'[A-Z0-9]{12}[0-9]{2}',value) or len(set(value)) == 1:
        raise ValueError('CNPJ inválido')
    for length, weights in [(12, [5,4,3,2,9,8,7,6,5,4,3,2]), (13, [6,5,4,3,2,9,8,7,6,5,4,3,2])]:
        digit = 11 - sum((ord(n)-48)*w for n,w in zip(value[:length], weights)) % 11
        if int(value[length]) != (0 if digit >= 10 else digit):
            raise ValueError('Dígitos verificadores do CNPJ inválidos')
    return value


def sign(data):
    key = os.getenv('BANKGUARD_AUDIT_KEY')
    if not key:
        if os.getenv('APP_ENV') == 'production':
            raise HTTPException(503, 'Chave de auditoria não configurada')
        return fingerprint(data)
    return hmac.new(key.encode(), json.dumps(data, sort_keys=True, ensure_ascii=False, separators=(',', ':')).encode(), hashlib.sha256).hexdigest()
