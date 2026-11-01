#!/bin/sh
set -eu
cd /app/api
python -m app.preflight
alembic upgrade head
exec /usr/bin/supervisord -c /app/bankguard.conf
