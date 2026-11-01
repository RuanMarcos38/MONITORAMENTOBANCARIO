FROM node:24-bookworm-slim AS web
WORKDIR /build
RUN npm install -g pnpm@11.25.0
COPY apps/web/package.json apps/web/pnpm-lock.yaml ./
RUN pnpm install --frozen-lockfile
COPY apps/web/ ./
RUN pnpm build

FROM python:3.11-slim-bookworm
RUN apt-get update && apt-get install -y --no-install-recommends supervisor ca-certificates libstdc++6 && rm -rf /var/lib/apt/lists/*
COPY --from=web /usr/local/bin/node /usr/local/bin/node
WORKDIR /app/api
COPY apps/api/requirements.txt ./
RUN pip install --no-cache-dir -r requirements.txt && useradd --uid 10001 --create-home bankguard
COPY apps/api/ ./
COPY --from=web --chown=bankguard:bankguard /build/.next/standalone /app/web/
COPY --from=web --chown=bankguard:bankguard /build/.next/static /app/web/.next/static/
COPY infra/deployment/supervisord.conf /etc/supervisor/conf.d/bankguard.conf
COPY infra/deployment/start.sh /app/start.sh
RUN mkdir -p /data && chown -R bankguard:bankguard /data /app && chmod +x /app/start.sh
USER bankguard
ENV NODE_ENV=production HOSTNAME=0.0.0.0 PORT=3000 APP_ENV=production PYTHONUNBUFFERED=1
EXPOSE 3000
HEALTHCHECK --interval=30s --timeout=5s --start-period=90s --retries=3 CMD python -c "import urllib.request; urllib.request.urlopen('http://127.0.0.1:8000/api/v1/health',timeout=3)"
CMD ["/app/start.sh"]
