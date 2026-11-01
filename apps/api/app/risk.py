from decimal import Decimal
from statistics import median

VERSION = '1.0.0'

def evaluate(rows):
    """Deterministic, explainable screening; never a crime probability."""
    values = [abs(Decimal(str(r['amount']))) for r in rows]
    baseline = median(values) if values else Decimal(0)
    seen = set()
    results = []
    for row in rows:
        key = (row['date'], str(row['amount']), row['beneficiary'])
        factors = []
        if key in seen:
            factors.append({'rule': 'possible_duplicate', 'points': 50, 'reason': 'Mesma data, valor e beneficiário; verificar documentos.'})
        if len(rows) >= 10 and baseline and abs(Decimal(str(row['amount']))) > baseline * 5:
            factors.append({'rule': 'median_outlier', 'points': 30, 'reason': 'Valor superior a cinco vezes a mediana do lote (mínimo 10 registros).'})
        seen.add(key)
        if factors:
            results.append({'transaction_id': row['id'], 'score': min(100, sum(f['points'] for f in factors)), 'version': VERSION,
                            'factors': factors, 'human_review': True, 'confidence': 'limitada', 'data_quality': 'dados importados pelo cliente',
                            'false_positive_risk': 'Pagamentos recorrentes legítimos e amostra limitada.', 'status': 'Novo', 'severity': 'Médio',
                            'title': 'Inconsistência transacional para revisão', 'evidence': row})
    return results
