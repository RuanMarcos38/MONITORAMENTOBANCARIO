"""Official source adapters. Pagination is bounded and checkpoints are explicit."""
from datetime import datetime, timedelta
from decimal import Decimal
from zoneinfo import ZoneInfo
import httpx

SOURCES = [
    {'id':'bcb','name':'Banco Central · SGS 432','url':'https://api.bcb.gov.br/','status':'SEM DADOS','unit':'% a.a.','periodicity':'diária'},
    {'id':'pncp','name':'PNCP · Contratos','url':'https://pncp.gov.br/api/consulta/swagger-ui/index.html','status':'SEM DADOS'},
    {'id':'cgu','name':'CGU · CEIS e CNEP','url':'https://api.portaldatransparencia.gov.br/','status':'CREDENCIAL PENDENTE'},
    {'id':'receita','name':'Receita Federal · CNPJ','url':'https://www.gov.br/receitafederal/dados','status':'Configuração pendente'},
    {'id':'openfinance','name':'Open Finance','url':None,'status':'Aguardando credenciamento'},
    {'id':'dict','name':'DICT','url':None,'status':'Aguardando credenciamento'},
]


class Batch(list):
    def __init__(self, rows, checkpoint=None, complete=True, scope=''):
        super().__init__(rows)
        self.checkpoint=checkpoint or {}
        self.complete=complete
        self.scope=scope


def collect(source, config=None):
    config=config or {}
    today=datetime.now(ZoneInfo('America/Sao_Paulo')).date()
    with httpx.Client(timeout=httpx.Timeout(30,connect=10),follow_redirects=False,headers={'Accept':'application/json','User-Agent':'BankGuardAI/0.2 official-data-monitor'}) as client:
        if source=='bcb':
            response=client.get('https://api.bcb.gov.br/dados/serie/bcdata.sgs.432/dados',params={'formato':'json','dataInicial':(today-timedelta(days=30)).strftime('%d/%m/%Y'),'dataFinal':today.strftime('%d/%m/%Y')})
            response.raise_for_status()
            payload=response.json()
            if not isinstance(payload,list):
                raise ValueError('Resposta BCB incompatível')
            rows=[]
            for r in payload:
                reference=datetime.strptime(r['data'],'%d/%m/%Y').date()
                amount=Decimal(r['valor'])
                if reference>today or not amount.is_finite():
                    raise ValueError('Série BCB inválida')
                rows.append({'external_id':'432:'+reference.isoformat(),'source':'bcb','source_url':str(response.url),'reference_date':reference.isoformat(),'value':str(amount),'unit':'% a.a.','series':432,'periodicity':'diária','aggregated':True})
            return Batch(rows,scope='SGS 432: janela móvel dos últimos 30 dias. Indicador macroeconômico agregado, sem transações individuais.')
        if source=='pncp':
            cursor=config.get('checkpoint',{})
            day=cursor.get('day') or (today-timedelta(days=7)).isoformat()
            page=int(cursor.get('page',1))
            rows=[]
            complete=False
            for _ in range(5):
                reference=datetime.strptime(day,'%Y-%m-%d').date()
                response=client.get('https://pncp.gov.br/api/consulta/v1/contratos',params={'dataInicial':reference.strftime('%Y%m%d'),'dataFinal':reference.strftime('%Y%m%d'),'pagina':page,'tamanhoPagina':50})
                if response.status_code==204:
                    payload={'data':[],'totalPaginas':0}
                else:
                    response.raise_for_status()
                    payload=response.json()
                if not isinstance(payload.get('data'),list):
                    raise ValueError('Resposta PNCP incompatível')
                for r in payload['data']:
                    rows.append({'external_id':r['numeroControlePNCP'],'source':'pncp','source_url':str(response.url),'reference_date':r.get('dataAssinatura'),'published_at':r.get('dataPublicacaoPncp'),'original':r})
                if page>=int(payload.get('totalPaginas',1)):
                    if reference>=today:
                        # Revisit today's publications on the next synchronization.
                        page=1
                        complete=True
                        break
                    day=(reference+timedelta(days=1)).isoformat()
                    page=1
                else:
                    page+=1
            return Batch(rows,{'day':day,'page':page},complete,'Contratos por data de publicação; paginação com checkpoint. Janela inicial de 7 dias, até 250 registros por execução; sem garantia de cobertura histórica nacional.')
        if source=='cgu':
            token=config.get('token')
            companies=config.get('companies',[])
            if not token or not companies:
                raise ValueError('CGU requer token oficial e empresas monitoradas')
            cursor=config.get('checkpoint',{})
            index=int(cursor.get('company',0))
            dataset=cursor.get('dataset','ceis')
            page=int(cursor.get('page',1))
            rows=[]
            complete=False
            for _ in range(3):
                if index>=len(companies):
                    index=0
                    complete=True
                    break
                identifier=companies[index]
                response=client.get('https://api.portaldatransparencia.gov.br/api-de-dados/'+dataset,params={'codigoSancionado':identifier,'pagina':page},headers={'chave-api-dados':token})
                response.raise_for_status()
                payload=response.json()
                if not isinstance(payload,list):
                    raise ValueError('Resposta CGU incompatível')
                for r in payload:
                    rows.append({'external_id':dataset+':'+str(r['id']),'source':'cgu','dataset':dataset,'source_url':str(response.url),'company_cnpj':identifier,'reference_date':r.get('dataInicioSancao'),'original':r})
                if not payload:
                    if dataset=='ceis':
                        dataset='cnep'
                    else:
                        dataset='ceis'
                        index+=1
                    page=1
                else:
                    page+=1
            return Batch(rows,{'company':index,'dataset':dataset,'page':page},complete,'CEIS/CNEP para CNPJs monitorados, conforme token e limites oficiais. CEPIM não incluído.')
    raise ValueError('Conector não habilitado')
