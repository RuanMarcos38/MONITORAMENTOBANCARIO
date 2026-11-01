from datetime import date, timedelta
import httpx

SOURCES = [
    {'id': 'bcb', 'name': 'Banco Central · SGS 432', 'url': 'https://dadosabertos.bcb.gov.br/dataset/432-taxa-de-juros---meta-selic-definida-pelo-copom', 'status': 'SEM DADOS', 'unit': '% a.a.', 'periodicity': 'diária'},
    {'id': 'pncp', 'name': 'PNCP · Contratos', 'url': 'https://pncp.gov.br/api/consulta/swagger-ui/index.html', 'status': 'SEM DADOS'},
    {'id': 'cgu', 'name': 'CGU · Sanções', 'url': 'https://api.portaldatransparencia.gov.br/', 'status': 'CREDENCIAL PENDENTE'},
    {'id': 'receita', 'name': 'Receita Federal · CNPJ', 'url': 'https://www.gov.br/receitafederal/dados', 'status': 'Configuração pendente'},
    {'id': 'openfinance', 'name': 'Open Finance', 'url': None, 'status': 'Aguardando credenciamento'},
    {'id': 'dict', 'name': 'DICT', 'url': None, 'status': 'Aguardando credenciamento'},
]

def collect(source):
    today = date.today()
    with httpx.Client(timeout=30, follow_redirects=False) as client:
        if source == 'bcb':
            url = 'https://api.bcb.gov.br/dados/serie/bcdata.sgs.432/dados'
            response = client.get(url, params={'formato': 'json', 'dataInicial': (today-timedelta(days=30)).strftime('%d/%m/%Y'), 'dataFinal': today.strftime('%d/%m/%Y')})
            response.raise_for_status()
            rows = response.json()
            if not isinstance(rows, list):
                raise ValueError('Resposta BCB incompatível')
            return [{'external_id': '432:'+r['data'], 'source': 'bcb', 'source_url': str(response.url), 'reference_date': r['data'], 'value': str(r['valor']), 'unit': '% a.a.', 'series': 432} for r in rows]
        if source == 'pncp':
            response = client.get('https://pncp.gov.br/api/consulta/v1/contratos', params={'dataInicial': today.strftime('%Y%m%d'), 'dataFinal': today.strftime('%Y%m%d'), 'pagina': 1, 'tamanhoPagina': 10})
            if response.status_code == 204:
                return []
            response.raise_for_status()
            return [{'external_id': r['numeroControlePNCP'], 'source': 'pncp', 'source_url': str(response.url), 'original': r} for r in response.json()['data']]
    raise ValueError('Conector ainda não homologado')
