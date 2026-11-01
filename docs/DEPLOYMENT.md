# Implantação EasyPanel verificada — 01/11/2026

Projeto existente: r2rmarketingdigital. Serviço: monitoramentobancario. URL HTTPS: https://r2rmarketingdigital-monitoramentobancario.ke4n49.easypanel.host

Fonte: repositório RuanMarcos38/MONITORAMENTOBANCARIO, branch feature/bankguard-ai-platform, Dockerfile na raiz. Código validado: 39a088ec17dd119d8714dbd444a5db3c1811d2ce. A imagem executa API, web, worker, scheduler e carga inicial de fontes públicas com usuário sem privilégios. Porta pública 3000; API interna 8000. Volume bankguard-data em /data.

Banco: serviço bankguard-postgres, PostgreSQL 17, banco/usuário bankguard. Redis: bankguard-redis, Redis 7. Ambos somente na rede interna. Não alterar outros serviços do projeto.

## Ambiente seguro

Definir APP_ENV=production; DATABASE_URL com driver postgresql+psycopg; REDIS_URL autenticada; BANKGUARD_ENCRYPTION_KEY Fernet; BANKGUARD_AUDIT_KEY longa; PUBLIC_ORIGIN com a URL HTTPS; API_INTERNAL_URL=http://127.0.0.1:8000; BACKUP_ENABLED=true; BACKUP_DIR=/data/backups. BANKGUARD_BOOTSTRAP_TOKEN habilita o cadastro único. BANKGUARD_BOOTSTRAP_PUBLIC_DATA=true permite carga de BCB/PNCP antes da criação do primeiro usuário, sem contas fictícias.

Nunca versionar valores de segredos. No editor do EasyPanel, colar todas as linhas, salvar e conferir após recarregar antes de implantar. O editor visual não expõe o conteúdo integral na propriedade value: não usar value vazio como base para uma atualização parcial. Scripts Linux devem manter LF; a inicialização e leitura da configuração pelo usuário da aplicação são verificadas no CI.

## Primeiro acesso

O titular escolhe organização, e-mail e senha de pelo menos 14 caracteres na própria página. Depois faz login, cadastra seu aplicativo autenticador TOTP e retorna ao login com o código. Não compartilhar senha, segredo TOTP ou código de instalação no chat. A criação de uma conta bloqueia a repetição da instalação. Pode-se remover a variável de instalação após concluir o cadastro, preservando as demais linhas.

## Operação e recuperação

A tela Operações mostra banco, fila, heartbeat, tarefas e resultado do último backup. O worker agenda backups locais cifrados diários. A chave de criptografia deve ser preservada por meio seguro separado: sem ela, anexos, credenciais e backups não podem ser recuperados.

CLI da API: `python -m app.backup backup /data/backups/nome.bgbackup` e `python -m app.backup verify /data/backups/nome.bgbackup`. Para restauração, definir BANKGUARD_RESTORE_URL apontando para outro banco completamente vazio, com nome terminado em _restore, e executar `python -m app.backup restore arquivo`. Nunca restaurar sobre a origem. O CI ensaiou backup cifrado, validação de integridade, restauração e versão Alembic em PostgreSQL. A recuperação completa da VPS e a cópia externa ainda precisam de um destino autorizado.

Antes de atualizar, verificar backup e fixar o commit. Para rollback, selecionar a imagem anterior compatível e avaliar migrações; não executar downgrade destrutivo nem sobrescrever dados automaticamente. O Docker Compose legado não foi usado nesta implantação.
