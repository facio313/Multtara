#!/bin/sh
set -eu

attempt=1
max_attempts=30
until python - <<'PY'
from django.db import connections

try:
    with connections["default"].cursor() as cursor:
        cursor.execute("SELECT 1")
        cursor.fetchone()
except Exception:
    raise SystemExit(1) from None
PY
do
  if [ "$attempt" -ge "$max_attempts" ]; then
    echo "database did not become ready after $max_attempts attempts" >&2
    exit 1
  fi
  echo "database is not ready; retrying ($attempt/$max_attempts)" >&2
  attempt=$((attempt + 1))
  sleep 2
done

python manage.py migrate --noinput
python manage.py bootstrap_gangneung_catalog
python manage.py collectstatic --noinput

exec "$@"
