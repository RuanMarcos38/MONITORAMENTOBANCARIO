#!/bin/sh
set -eu
cd /app/api
python -m app.preflight
alembic upgrade head
exec /usr/bin/supervisord -c /etc/supervisor/conf.d/bankguard.conf
