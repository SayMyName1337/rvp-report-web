#!/bin/sh
# Резервная копия базы и хранилища файлов.
#
# Запускается по расписанию на узле, где работает приложение:
#   0 3 * * * /opt/rvp-report/deploy/backup.sh >> /var/log/rvp-backup.log 2>&1
#
# Копия базы делается через pg_dump внутри контейнера, файлы — архивом
# тома. Старые копии удаляются, чтобы диск не заполнился незаметно.
#
# Восстановление описано в docs/deploy.md. Проверять восстановление
# нужно не тогда, когда оно понадобилось: раз в квартал разверните
# копию в стороне и убедитесь, что данные на месте.

set -eu

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
COMPOSE="docker compose -f $ROOT/deploy/compose.yaml --env-file $ROOT/.env"
TARGET="${BACKUP_DIR:-$ROOT/deploy/backup}"
KEEP_DAYS="${BACKUP_KEEP_DAYS:-30}"
STAMP="$(date +%Y-%m-%d_%H%M)"

mkdir -p "$TARGET"

echo "[$(date '+%F %T')] Копия базы..."
$COMPOSE exec -T db pg_dump \
    -U "$POSTGRES_USER" -d "$POSTGRES_DB" --format=custom \
    > "$TARGET/db_$STAMP.dump"

echo "[$(date '+%F %T')] Копия файлов..."
$COMPOSE run --rm --no-deps -v "$TARGET:/backup" web \
    tar czf "/backup/media_$STAMP.tar.gz" -C /app/media .

echo "[$(date '+%F %T')] Удаляю копии старше $KEEP_DAYS суток..."
find "$TARGET" -name 'db_*.dump' -mtime "+$KEEP_DAYS" -delete
find "$TARGET" -name 'media_*.tar.gz' -mtime "+$KEEP_DAYS" -delete

echo "[$(date '+%F %T')] Готово:"
ls -lh "$TARGET" | tail -5
