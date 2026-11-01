'use client';
import { useEffect, useState } from 'react';
import { Plus, Download, Search, ArrowRight, RefreshCw, ShieldCheck } from 'lucide-react';
import { api, post, Row, label } from '../lib/api';

type Field = { name: string; label: string; type?: string; options?: string[]; min?: number; value?: string; required?: boolean; checked?: boolean };
const states = ['Novo', 'Em análise', 'Aguardando informações', 'Confirmado como irregularidade após verificação', 'Falso positivo', 'Resolvido', 'Arquivado'];
const severities = ['Crítico', 'Alto', 'Médio', 'Baixo', 'Informativo'];
const recordKinds = ['companies', 'contracts', 'sanctions', 'alerts', 'investigations', 'indicators', 'audit', 'notifications', 'reports'];

function ProductForm({ title, fields, submit, onDone }: { title: string; fields: Field[]; submit: (data: Record<string, unknown>) => Promise<unknown>; onDone: (data?: unknown) => void }) {
  const [error, setError] = useState('');
  const [busy, setBusy] = useState(false);
  return <form className="card product-form" onSubmit={async event => {
    event.preventDefault(); const form = event.currentTarget; setBusy(true); setError('');
    const data: Record<string, unknown> = Object.fromEntries(new FormData(form));
    fields.filter(f => f.type === 'checkbox').forEach(f => { data[f.name] = new FormData(form).has(f.name); });
    fields.filter(f => f.type === 'number').forEach(f => { data[f.name] = Number(data[f.name]); });
    try { const result = await submit(data); form.reset(); onDone(result); }
    catch (cause) { setError((cause as Error).message); }
    finally { setBusy(false); }
  }}><h2>{title}</h2><div className="form-grid">{fields.map(field => <label key={field.name} className={field.type === 'textarea' ? 'wide' : ''}>{field.label}
    {field.options ? <select name={field.name} defaultValue={field.value || field.options[0]}>{field.options.map(v => <option key={v}>{v}</option>)}</select> : field.type === 'textarea' ? <textarea name={field.name} minLength={field.min} maxLength={10000} required={field.required !== false} defaultValue={field.value}/> : <input name={field.name} type={field.type || 'text'} minLength={field.min} maxLength={field.type === 'password' ? 10000 : 500} defaultValue={field.type === 'checkbox' ? undefined : field.value} required={field.type !== 'checkbox' && field.required !== false} defaultChecked={field.type === 'checkbox' ? field.checked : undefined} autoComplete={field.type === 'password' ? 'off' : undefined}/>}
  </label>)}</div>{error && <p role="alert" className="error">{error}</p>}<button disabled={busy}>{busy ? 'Salvando…' : 'Salvar'}</button></form>;
}

function Bars({ title, data }: { title: string; data: Record<string, number> }) {
  const maximum = Math.max(1, ...Object.values(data));
  return <section className="card"><h2>{title}</h2>{Object.keys(data).length ? Object.entries(data).map(([name, value]) => <div className="bar-row" key={name}><span>{name}</span><div className="bar-track"><i style={{ width: `${value / maximum * 100}%` }}/></div><b>{value.toLocaleString('pt-BR')}</b></div>) : <p>Sem dados suficientes para este gráfico.</p>}</section>;
}

export function Workflows({ page, user, onChange, updated }: { page: string; user: Row; onChange: () => void; updated: number }) {
  const [data, setData] = useState<Row[]>([]);
  const [extra, setExtra] = useState<Row>({});
  const [selected, setSelected] = useState<Row | null>(null);
  const [query, setQuery] = useState('');
  const [offset, setOffset] = useState(1);
  const [refresh, setRefresh] = useState(0);
  const [error, setError] = useState('');
  const [message, setMessage] = useState('');
  const [busy, setBusy] = useState(false);
  const editable = ['admin', 'analyst'].includes(label(user.role));
  const admin = user.role === 'admin';
  function reload() { setRefresh(v => v + 1); onChange(); }
  useEffect(() => { setSelected(null); setOffset(1); setQuery(''); setMessage(''); }, [page]);
  useEffect(() => {
    let active = true; setBusy(true); setError('');
    const path = recordKinds.includes(page) ? `records/${page}?page=${offset}&size=25&q=${encodeURIComponent(query)}` : page === 'risk' ? 'analytics' : page === 'relationships' ? 'relationships/graph' : page === 'users' ? 'users' : page === 'plans' ? 'plans' : page === 'operations' ? 'jobs' : 'organization';
    api(path).then(result => { if (active) { if (Array.isArray(result)) { setData(result); setExtra({}); } else { setExtra(result); setData([]); } } }).catch(cause => active && setError(cause.message)).finally(() => active && setBusy(false));
    return () => { active = false; };
  }, [page, offset, query, refresh, updated]);
  async function action(path: string, payload?: unknown) { setError(''); try { const result = await post(path, payload); setMessage('Operação concluída.'); reload(); return result; } catch (cause) { setError((cause as Error).message); } }
  async function open(row: Row) { if (page === 'investigations') { try { setSelected(await api(`investigations/${row.id}`)); } catch (cause) { setError((cause as Error).message); } } else setSelected(row); }
  const afterSave = () => { setMessage('Registro salvo.'); reload(); };
  const evidence = selected?.evidence;
  const timeline = (selected?.timeline || []) as Row[];
  return <div className="workflows">
    {busy && <p role="status">Consultando registros…</p>}{error && <div className="error" role="alert">{error}</div>}{message && <div className="notice" role="status">{message}</div>}
    {page === 'risk' && <><div className="card"><h2>BankGuard Risk Engine</h2><p>Regras rastreáveis: possíveis duplicidades, valor acima de cinco vezes a mediana e coincidência documental entre sanções e contratos. Todo resultado exige revisão humana.</p>{editable && <button onClick={() => action('risk/run')}><RefreshCw size={15}/> Executar análise</button>}<p>Taxa de falsos positivos entre casos revisados: {extra.false_positive_rate == null ? 'Amostra insuficiente' : `${(Number(extra.false_positive_rate) * 100).toFixed(1)}%`}</p></div><div className="sources-grid"><Bars title="Alertas por severidade" data={(extra.severity || {}) as Record<string, number>}/><Bars title="Estado da análise" data={(extra.status || {}) as Record<string, number>}/><Bars title="Categorias" data={(extra.categories || {}) as Record<string, number>}/><Bars title="Empresas por UF" data={(extra.uf || {}) as Record<string, number>}/><Bars title="Evolução de alertas" data={Object.fromEntries(((extra.days || []) as Row[]).map(r => [label(r.date), Number(r.count)]))}/></div></>}
    {page === 'relationships' && <Graph graph={extra}/>}
    {page === 'plans' && <section className="card"><h2>Planos da plataforma</h2><p>Nenhuma cobrança ou assinatura paga está habilitada. O catálogo permite planejar a utilização da organização.</p><div className="sources-grid">{((extra.plans || []) as Row[]).map(plan => <div className="card" key={label(plan.id)}><h3>{label(plan.name)}</h3><p>Limite de referência: {Number(plan.limit).toLocaleString('pt-BR')} registros</p><span className="pill">{plan.id === 'free' ? 'Plano inicial' : 'Contratação não habilitada'}</span></div>)}</div></section>}
    {page === 'settings' && <><ProductForm title="Preferências da organização" key={label(extra.name)} fields={[{name:'name',label:'Nome da organização',value:label(extra.name),min:3},{name:'retention_days',label:'Retenção pretendida em dias',type:'number',value:label((extra.settings as Row)?.retention_days || 365)},{name:'auto_sync',label:'Autorizar coleta automática das fontes configuradas',type:'checkbox',checked:Boolean((extra.settings as Row)?.auto_sync)},{name:'auto_cases',label:'Abrir casos automaticamente para novos alertas',type:'checkbox',checked:Boolean((extra.settings as Row)?.auto_cases)}]} submit={body => post('organization',body)} onDone={afterSave}/><section className="card"><h2>Segurança e retenção</h2><p>Autenticador: {user.mfa ? 'configurado' : 'não configurado'}. Segredos e anexos são cifrados no servidor. O prazo de retenção não provoca exclusões automáticas: a remoção depende de revisão e backup validado.</p><p>Open Finance e DICT continuam aguardando credenciamento.</p></section></>}
    {page === 'users' && <><section className="card"><h2>Usuários da organização</h2><table><thead><tr><th>E-mail</th><th>Perfil</th><th>Autenticador</th><th>Ações</th></tr></thead><tbody>{data.map(row => <tr key={label(row.id)}><td>{label(row.email)}</td><td>{label(row.role)}</td><td>{row.mfa ? 'Ativo' : 'Pendente'}</td><td>{admin && row.email !== user.email && <button className="secondary" onClick={() => action(`users/${row.id}/revoke-sessions`)}>Revogar sessões</button>}</td></tr>)}</tbody></table></section>{admin && <ProductForm title="Convidar integrante" fields={[{name:'email',label:'E-mail',type:'email'},{name:'role',label:'Perfil de acesso',options:['viewer','auditor','analyst','admin']}]} submit={body => post('users/invitations',body)} onDone={result => { const token = (result as Row).token; setMessage(`Convite criado. Compartilhe somente com o destinatário: ${window.location.origin}/#invite=${token}`); reload(); }}/>}</>}
    {page === 'operations' && <section className="card"><h2>Processamento automático</h2><p>Estado persistido das últimas 100 tarefas. Falhas usam retentativas com intervalo crescente e são isoladas após cinco tentativas.</p><table><thead><tr><th>Tarefa</th><th>Estado</th><th>Tentativas</th><th>Última atualização</th><th>Ações</th></tr></thead><tbody>{data.map(row => <tr key={label(row.id)}><td>{label(row.source)}</td><td>{label(row.state)}</td><td>{label(row.attempts)}</td><td>{new Date(label(row.updated)).toLocaleString('pt-BR')}</td><td>{['dead_letter','failed'].includes(label(row.state)) && <button onClick={() => action(`jobs/${row.id}/retry`)}>Reprocessar</button>}</td></tr>)}</tbody></table>{data.length === 0 && <p>Nenhuma tarefa registrada. Autorize a coleta nas configurações para iniciar.</p>}</section>}
    {recordKinds.includes(page) && <section className="card"><div className="card-heading"><h2>Registros da organização</h2><div>{page !== 'notifications' && <a className="export-inline" href={`/api/v1/reports/${page}.csv`}><Download size={15}/> Exportar CSV</a>}</div></div><label className="search"><Search size={16}/><input aria-label="Pesquisar registros" placeholder="CNPJ, título, órgão, UF ou número" value={query} onChange={event => { setQuery(event.target.value); setOffset(1); }}/></label>
      {data.length ? <div className="table-wrap"><table><thead><tr><th>Identificação</th><th>Detalhes</th><th>Estado / data</th><th>Ação</th></tr></thead><tbody>{data.map(row => {
        const original = (row.original || {}) as Row;
        return <tr key={label(row.id)}><td><b>{label(row.title || row.name || row.source_record_id || row.id)}</b>{Boolean(row.cnpj) && <small>{label(row.cnpj)}</small>}</td><td>{label(original.objetoContrato || original.nomeRazaoSocialFornecedor || row.category || row.value || row.action || row.origin || 'Registro documentado')}{row.score != null && <small>Score: {label(row.score)} / 100 · revisão humana</small>}</td><td>{label(row.status || row.severity || row.reference_date || row.created)}</td><td><button className="secondary" onClick={() => open(row)}>Abrir <ArrowRight size={13}/></button></td></tr>;
      })}</tbody></table></div> : <div className="empty"><Search size={28}/><h3>Nenhum registro encontrado</h3><p>Cadastre uma empresa, importe um extrato autorizado ou sincronize uma fonte oficial.</p></div>}
      <div className="pagination"><button className="secondary" disabled={offset === 1 || busy} onClick={() => setOffset(v => v - 1)}>Anterior</button><span>Página {offset}</span><button className="secondary" disabled={data.length < 25 || busy} onClick={() => setOffset(v => v + 1)}>Próxima</button></div>
    </section>}
    {selected && <section className="card detail-panel"><div className="card-heading"><h2>{label(selected.title || selected.name || selected.source_record_id)}</h2><button className="secondary" onClick={() => setSelected(null)}>Fechar detalhes</button></div><p>Identificador: {label(selected.id)} · {label(selected.status || 'Registro de referência')}</p>
      {Boolean(selected.source_url) && <a href={label(selected.source_url)} target="_blank" rel="noreferrer">Abrir fonte original ↗</a>}
      {page === 'investigations' && <><a className="export" href={`/api/v1/investigations/${selected.id}/report.pdf`}><Download size={16}/> Baixar dossiê PDF</a><h3>Linha do tempo</h3>{timeline.map((event,index) => <div className="timeline-event" key={index}><small>{label(event.at)}</small><p>{label(event.note)}</p></div>)}<h3>Documentos autorizados</h3>{((selected.attachments || []) as Row[]).map(file => <a className="export" key={label(file.id)} href={`/api/v1/attachments/${file.id}`}>{label(file.name)} <small>SHA-256: {label(file.digest)}</small></a>)}{editable && <label className="upload">Anexar documento autorizado · até 5 MB<input type="file" accept=".pdf,.txt,.csv,.png,.jpg,.jpeg" onChange={async event => { const file = event.target.files?.[0]; if (!file) return; const form = new FormData(); form.set('file',file); try { await api(`investigations/${selected.id}/attachments`, {method:'POST',body:form}); setSelected(await api(`investigations/${selected.id}`)); reload(); } catch (cause) { setError((cause as Error).message); } }}/></label>}</>}
      {Boolean(evidence) && <details open><summary>Evidências vinculadas</summary><pre>{JSON.stringify(evidence,null,2)}</pre></details>}
      <details><summary>Registro completo e proveniência</summary><pre>{JSON.stringify(selected,null,2)}</pre></details>
      {editable && ['alerts','investigations'].includes(page) && <ProductForm title="Registrar andamento ou reabrir" fields={[{name:'status',label:'Novo estado',options:states,value:label(selected.status)},{name:'note',label:'Fundamento, observações e verificações realizadas',type:'textarea',min:10}]} submit={async body => { const result = await post(`${page}/${selected.id}/events`,body); setSelected({...selected,...result}); return result; }} onDone={afterSave}/>}
      {editable && page === 'alerts' && <ProductForm title="Abrir investigação deste alerta" fields={[{name:'title',label:'Título do caso',value:label(selected.title),min:5},{name:'note',label:'Objetivo e fundamento',type:'textarea',min:10}]} submit={body => post('investigations',{...body,alert_id:selected.id})} onDone={afterSave}/>}
      {page === 'notifications' && editable && <button onClick={() => action(`notifications/${selected.id}/read`)}>Marcar como lida</button>}
    </section>}
    {editable && page === 'companies' && <ProductForm title="Monitorar empresa" fields={[{name:'cnpj',label:'CNPJ (numérico ou alfanumérico)'},{name:'name',label:'Razão social',min:3},{name:'uf',label:'UF',options:['AC','AL','AP','AM','BA','CE','DF','ES','GO','MA','MT','MS','MG','PA','PB','PR','PE','PI','RJ','RN','RS','RO','RR','SC','SP','SE','TO']},{name:'municipality',label:'Município',required:false},{name:'purpose',label:'Finalidade e fundamento do monitoramento',type:'textarea',min:10}]} submit={body => post('companies',body)} onDone={afterSave}/>}
    {editable && page === 'alerts' && <ProductForm title="Registrar alerta manual" fields={[{name:'title',label:'Título do alerta',min:5},{name:'category',label:'Categoria',min:3},{name:'severity',label:'Severidade',options:severities},{name:'source_url',label:'Link verificável da fonte',type:'url'},{name:'reference_date',label:'Data de referência',type:'date'},{name:'evidence',label:'Evidências e limitações observadas',type:'textarea',min:20}]} submit={body => post('alerts',body)} onDone={afterSave}/>}
    {editable && page === 'investigations' && <ProductForm title="Abrir investigação" fields={[{name:'title',label:'Título do caso',min:5},{name:'note',label:'Objetivo e fundamento',type:'textarea',min:10}]} submit={body => post('investigations',body)} onDone={afterSave}/>}
    {page === 'reports' && <section className="card"><h2>Exportações da organização</h2>{['alerts','investigations','contracts','transactions','audit'].map(kind => <a className="export" key={kind} href={`/api/v1/reports/${kind}.csv`}><Download size={16}/>{({alerts:'Alertas',investigations:'Investigações',contracts:'Contratos',transactions:'Transações',audit:'Auditoria'} as Record<string,string>)[kind]} · CSV</a>)}<p>Os dossiês PDF ficam disponíveis no detalhe de cada investigação. Resumos diários são gerados pelo agendador quando a coleta automática está autorizada.</p></section>}
    {page === 'audit' && admin && <button onClick={async () => { try { const check = await api('audit/verify'); setMessage(`Verificação: ${check.verified} assinaturas; ${check.invalid.length} inválidas; ${check.legacy_unsigned} registros legados sem assinatura.`); } catch (cause) { setError((cause as Error).message); } }}><ShieldCheck size={16}/> Verificar assinaturas da auditoria</button>}
  </div>;
}

export function IntegrationSettings({ user }: { user: Row }) {
  const [refresh, setRefresh] = useState(0);
  const [status, setStatus] = useState<Row>({});
  const [message, setMessage] = useState('');
  useEffect(() => { if (user.role === 'admin') api('operations').then(setStatus).catch(() => {}); }, [user.role,refresh]);
  if (user.role !== 'admin') return null;
  return <><section className="card"><h2>Operação do monitoramento</h2><div className="summary-row"><span>Banco de dados</span><b>{label(status.database)}</b></div><div className="summary-row"><span>Fila Redis</span><b>{label(status.redis)}</b></div><div className="summary-row"><span>Agendador</span><b>{label(status.scheduler)}</b></div><p>Último sinal: {label(status.last_tick)}</p></section><ProductForm title="Configurar token oficial da CGU" fields={[{name:'value',label:'Token oficial · armazenado com criptografia',type:'password',min:8}]} submit={body => post('connectors/cgu/credential',body)} onDone={() => {setMessage('Token configurado. Cadastre os CNPJs monitorados antes de consultar.');setRefresh(v => v + 1);}}/>{message && <div role="status" className="notice">{message}</div>}<section className="card"><h2>Integrações institucionais</h2><p>Open Finance e DICT: aguardando credenciamento. Nenhuma transação privada é recebida ou consultada por esses canais. Registrar consentimento não substitui a homologação institucional.</p></section></>;
}

function Graph({ graph }: { graph: Row }) {
  const nodes = ((graph.nodes || []) as Row[]).slice(0,60);
  const edges = (graph.edges || []) as Row[];
  const positions = new Map(nodes.map((node,index) => [label(node.id),{x:80 + index % 3 * 250,y:50 + Math.floor(index / 3) * 85}]));
  return <section className="card"><h2>Vínculos documentados</h2><p>{label(graph.notice || 'Carregando vínculos oficiais…')}</p>{nodes.length ? <div className="graph-scroll"><svg role="img" aria-label="Relações entre órgãos, contratos e fornecedores documentadas nas fontes oficiais" viewBox={`0 0 700 ${Math.max(250,Math.ceil(nodes.length / 3) * 85 + 40)}`}>{edges.map((edge,index) => { const from = positions.get(label(edge.source)), to = positions.get(label(edge.target)); return from && to ? <line key={index} x1={from.x} y1={from.y} x2={to.x} y2={to.y} stroke="#b4c5dd"/> : null; })}{nodes.map(node => { const p = positions.get(label(node.id))!; return <g key={label(node.id)}><circle cx={p.x} cy={p.y} r={13} fill={node.kind === 'Contrato' ? '#2468dd' : '#23927b'}/><text x={p.x + 20} y={p.y + 4} fontSize="10" fill="currentColor">{label(node.label).slice(0,25)}<title>{label(node.label)}</title></text></g>; })}</svg></div> : <div className="empty"><h3>Sem vínculos documentados</h3><p>Os vínculos serão mostrados quando os contratos coletados identificarem órgão e fornecedor.</p></div>}<small>Visualização limitada a 60 entidades. A consulta considera até 1.000 contratos da organização.</small></section>;
}
