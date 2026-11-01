# BankGuard AI

Plataforma de inteligência financeira em desenvolvimento. **Não homologada para produção.** A branch entrega uma primeira fatia funcional, não o escopo completo do prompt master.

## Executar localmente

Pré-requisitos: Python 3.11+, Node 24, pnpm. Não há usuário ou senha padrão.

```powershell
python -m venv .venv
.\.venv\Scripts\python -m pip install -r apps/api/requirements.txt
cd apps/api
..\..\.venv\Scripts\python -m alembic upgrade head
..\..\.venv\Scripts\python -m app.bootstrap
..\..\.venv\Scripts\python -m uvicorn app.main:app --port 8000
```

Em outro terminal, `cd apps/web`, `pnpm install --frozen-lockfile` e `pnpm dev`. Abra http://localhost:3000. O provisionamento administrativo cria uma organização e exige validação do autenticador TOTP. Nunca use dados bancários reais neste ambiente de homologação.

## Implementação atual

- Next.js/React/TypeScript: login, painel sem números artificiais, consulta de registros, busca, estados vazios/erro, tema escuro e navegação responsiva.
- FastAPI/SQLAlchemy: sessões opacas com hash no banco, Argon2, TOTP no provisionamento administrativo, expiração, logout, limitação persistida de tentativas e separação de registros por organização.
- CSV UTF-8 autorizado: validação integral antes da gravação, limite de tamanho, datas/valores, idempotência por organização e rejeição de conflitos de conteúdo.
- Motor determinístico v1: possíveis duplicidades e valores acima de cinco vezes a mediana do lote, com mínimo de dez transações para análise de outliers. Não constitui análise de lavagem de dinheiro ou confirmação de crime.
- Casos: abertura, vínculo opcional a alerta, notas, estado, histórico e registro de auditoria. Exportação CSV por organização.
- BCB SGS 432: consulta dos últimos 30 dias, com fonte, referência, coleta e hash. PNCP: primeira página de contratos publicados na data da consulta, máximo de dez. **Cobertura PNCP parcial, sem ingestão nacional completa.**
- Alembic inicial; configuração PostgreSQL, Redis, Caddy e contêineres de API e web.

## Verificações

```powershell
cd apps/api
..\..\.venv\Scripts\python -m pytest -q
cd ../web
pnpm typecheck
pnpm build
```

Consulte [relatório de execução](docs/EXECUTION.md) para os resultados efetivamente obtidos e os bloqueios. Testes com fixtures são isolados do banco operacional. Não há dados de demonstração nas telas.

## Limites e bloqueios de produção

O armazenamento usa um envelope JSON por tipo de registro nesta fundação. O modelo normalizado completo solicitado ainda não foi criado. Não há ingestão completa PNCP, CGU ou Receita, jobs persistentes, workers/scheduler, filas com recuperação, notificações, OFX/CNAB, grafo, PDF, assinatura de webhooks bancários, gestão de consentimentos, gestão de usuários/planos ou recuperação de senha.

Faltam criptografia do segredo TOTP, MFA obrigatório por política e ciclo de revogação, revisão de segurança, testes PostgreSQL/Redis/E2E/a11y, monitoramento, backups e ensaio de restauração. O contador de fontes operacionais representa a última consulta bem-sucedida; a política de expiração por fonte ainda precisa ser implementada.

CGU fica com credencial pendente. Receita fica com configuração pendente. Open Finance e DICT ficam aguardando credenciamento. Nenhum acesso a transações privadas está habilitado. Não há cobrança real, envio a contatos ou denúncias automáticas.

**Não publique com dados reais até fechar os bloqueios.** O Compose é uma configuração candidata, ainda sujeita a validação de execução, TLS, permissões e recuperação.
