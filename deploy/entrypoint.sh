#!/bin/sh
# Точка входа контейнера.
#
# Первый аргумент выбирает, чем работает контейнер:
#   web     — приложение за gunicorn;
#   manage  — разовая команда управления, остальные аргументы передаются ей.
#
# Миграции и сборка статики выполняются только в web: разовая команда
# управления не должна менять схему базы мимоходом.

set -eu

wait_for_database() {
    echo "Жду базу данных..."
    attempt=0
    until python -c "
import os, sys, psycopg
try:
    psycopg.connect(
        host=os.environ.get('POSTGRES_HOST', 'db'),
        port=os.environ.get('POSTGRES_PORT', '5432'),
        dbname=os.environ['POSTGRES_DB'],
        user=os.environ['POSTGRES_USER'],
        password=os.environ['POSTGRES_PASSWORD'],
        connect_timeout=3).close()
except Exception as error:
    print(error, file=sys.stderr)
    sys.exit(1)
" 2>/dev/null; do
        attempt=$((attempt + 1))
        if [ "$attempt" -ge 30 ]; then
            echo "База данных не отвечает, сдаюсь." >&2
            exit 1
        fi
        sleep 2
    done
    echo "База данных готова."
}

case "${1:-web}" in
    web)
        wait_for_database
        python manage.py migrate --noinput
        python manage.py collectstatic --noinput
        python manage.py setup_roles
        exec gunicorn config.wsgi:application \
            --bind 0.0.0.0:8000 \
            --workers "${GUNICORN_WORKERS:-3}" \
            --timeout "${GUNICORN_TIMEOUT:-120}" \
            --access-logfile - \
            --error-logfile -
        ;;
    manage)
        wait_for_database
        shift
        exec python manage.py "$@"
        ;;
    *)
        exec "$@"
        ;;
esac
