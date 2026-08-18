#!/bin/sh
set -eu

python manage.py migrate --noinput
python manage.py bootstrap_gangneung_catalog
python manage.py collectstatic --noinput

exec "$@"
