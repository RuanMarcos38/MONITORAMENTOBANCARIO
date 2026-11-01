# Implantação candidata: EasyPanel / Docker Compose

Crie um projeto isolado `bankguard-ai`. Não altere serviços de outras aplicações. Configure um domínio próprio, POSTGRES_PASSWORD exclusivo e variáveis sem reutilizar credenciais. Preserve `.env` fora do Git.

1. Valide os bloqueios de produção listados no README e no relatório de execução.
2. Copie `.env.example` para `.env`; configure domínio e senha forte. Codifique caracteres especiais na URL do banco.
3. Execute `docker compose config` e `docker compose build`.
4. Execute `docker compose up -d` apenas no ambiente de homologação autorizado.
5. Provisione o administrador interativamente: `docker compose exec bankguard-api python -m app.bootstrap`.
6. Confirme HTTPS, cookie Secure, bloqueio entre organizações e `/api/v1/health`.
7. Restrinja o acesso de rede ao banco e Redis. Não publique suas portas.

Não existem worker e scheduler nesta entrega; Redis está preparado e não é utilizado. Não afirmar operação contínua ou recuperação de filas.

## Backup e rollback (procedimentos ainda não ensaiados)

Antes de atualização: gerar dump PostgreSQL com `pg_dump`, cifrar o arquivo e armazenar em destino autorizado fora do host. Testar a restauração em banco isolado, verificar contagens e permissões e só então considerar o backup validado. Não salvar dumps neste repositório.

Fixar imagens pelo commit validado. Para rollback, parar a entrada de gravações, restaurar a imagem anterior e avaliar compatibilidade de esquema. Se a migração exigir reversão destrutiva, restaurar backup previamente testado. Não executar `alembic downgrade` automaticamente.
