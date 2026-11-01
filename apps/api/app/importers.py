"""Strict parsers. Uploaded files are validated completely before persistence."""
import csv
import io
from datetime import datetime
from decimal import Decimal
import hashlib


def parse_file(filename, raw):
    if len(raw) > 2_000_000:
        raise ValueError('Arquivo excede 2 MB')
    suffix = filename.lower().rsplit('.', 1)[-1]
    if suffix == 'csv':
        reader = csv.DictReader(io.StringIO(raw.decode('utf-8-sig')))
        if reader.fieldnames != ['id', 'date', 'amount', 'beneficiary']:
            raise ValueError('CSV: colunas id,date,amount,beneficiary, nessa ordem')
        rows = list(reader)
    elif suffix in ('ofx', 'qfx'):
        if b'<!ENTITY' in raw.upper() or b'<!DOCTYPE' in raw.upper():
            raise ValueError('Declarações XML externas não são permitidas')
        from ofxparse import OfxParser
        statement = OfxParser.parse(io.BytesIO(raw), fail_fast=True)
        rows = []
        for account in statement.accounts:
            account_hash = hashlib.sha256((str(account.routing_number)+':'+str(account.account_id)).encode()).hexdigest()[:20]
            for tx in account.statement.transactions:
                if not tx.id:
                    raise ValueError('Transação OFX sem FITID')
                rows.append({'id': account_hash+':'+tx.id, 'date': tx.date.strftime('%Y-%m-%d'), 'amount': str(tx.amount), 'beneficiary': tx.payee or tx.memo or 'Não informado no extrato'})
    else:
        raise ValueError('Formato não suportado. Utilize CSV UTF-8 ou OFX/QFX; CNAB exige layout bancário homologado.')
    if not rows or len(rows) > 10000 or len({r['id'] for r in rows}) != len(rows):
        raise ValueError('Lote vazio, excedido ou com identificadores repetidos')
    for row in rows:
        if set(row) != {'id', 'date', 'amount', 'beneficiary'}:
            raise ValueError('Estrutura de transação inválida')
        datetime.strptime(row['date'], '%Y-%m-%d')
        amount = Decimal(row['amount'])
        if not amount.is_finite() or abs(amount) > Decimal('1e15') or amount.as_tuple().exponent < -2:
            raise ValueError('Valor inválido; use até duas casas decimais')
        if not row['id'] or not row['beneficiary'] or any(not isinstance(v, str) or len(v)>500 for v in row.values()):
            raise ValueError('Campo vazio ou muito longo')
        row['amount'] = format(amount, '.2f')
    return rows
