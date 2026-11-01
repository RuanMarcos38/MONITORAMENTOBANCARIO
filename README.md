# BankGuard AI

Plataforma de triagem financeira e consulta a dados públicos, em homologação. Interface pt-BR, horário America/Sao_Paulo e valores em reais. Alertas exigem revisão humana; score não representa probabilidade de crime.

## Acesso implantado

https://r2rmarketingdigital-monitoramentobancario.ke4n49.easypanel.host

Implantado no EasyPanel existente, projeto `r2rmarketingdigital`, serviço `monitoramentobancario`, com PostgreSQL e Redis próprios, sem exposição pública dos bancos. Não há usuário ou senha padrão. O titular conclui o primeiro cadastro com o código de instalação mantido no ambiente do servidor, escolhe sua senha e configura TOTP. Administradores e analistas precisam de MFA para acessar os dados.

## Funcionalidades

- Sessões revogáveis, funções de acesso, isolamento entre organizações, convites, gestão de membros e preferências.
- Dashboard, fontes, empresas, transações, alertas, casos, anexos cifrados, relatório PDF, exportação CSV, análises e grafo com vínculos documentados.
- Importação autorizada CSV e OFX/QFX; validação integral, limites e idempotência. Triagem de possíveis duplicidades e valores atípicos com fatores explicáveis.
- BCB SGS 432 e PNCP consultados de verdade; paginação limitada com checkpoint, proveniência e histórico. CGU CEIS/CNEP depende de credencial própria e CNPJs monitorados.
- Celery/Redis, tarefas persistidas, retentativas, recuperação de tarefas interrompidas, notificações internas, estado operacional e backups cifrados.
- Auditoria com HMAC por evento, criptografia de TOTP/credenciais/anexos e sessões por cookie seguro em produção.

## Verificação

O commit de código `39a088ec17dd119d8714dbd444a5db3c1811d2ce` passou nos seis trabalhos de CI: backend, frontend, PostgreSQL, imagem, fontes oficiais e E2E. Inclui 21 testes Python, três fluxos de navegador, restauração isolada de backup em PostgreSQL, migrações, build/typecheck e auditoria Python. Evidência: https://github.com/RuanMarcos38/MONITORAMENTOBANCARIO/actions/runs/41318578017

A URL HTTPS exibiu a tela de primeiro acesso e `/api/v1/health` retornou `status: ok`. Isso não equivale a auditoria independente de segurança ou homologação regulatória.

## Desenvolvimento

Python 3.11+, Node 24 e pnpm 11.25.0. Instale `apps/api/requirements.txt`, execute `alembic upgrade head` em `apps/api` e inicie `uvicorn app.main:app --port 8000`. Em `apps/web`, execute `pnpm install --frozen-lockfile` e `pnpm dev`. Configure as variáveis conforme `.env.example`; nenhum segredo pertence ao Git. SQLite é destinado a testes locais. O Dockerfile da raiz é o caminho de implantação verificado; o Compose legado não representa a implantação atual.

## Limites explícitos

O escopo integral do prompt master ainda não está concluído. Há envelope JSON por tipo de registro, e não o esquema normalizado completo. Faltam ingestão Receita, CNAB, recuperação de senha por e-mail, SMTP/WhatsApp/webhooks externos, cobrança e imposição integral de quotas, ML local e todas as regras avançadas do pedido. A coleta PNCP é parcial, sem garantia de cobertura nacional histórica. Open Finance e DICT aguardam credenciamento. A auditoria por HMAC detecta alteração de conteúdo, não garante detecção de exclusão de eventos. Retenção é configurável, sem exclusão automática. Backups locais não substituem cópia externa autorizada.

Veja `docs/EXECUTION.md` e `docs/DEPLOYMENT.md`. A branch permanece separada de main e o PR aguarda revisão, sem merge automático.
