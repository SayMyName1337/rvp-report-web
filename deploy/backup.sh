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

# Параметры читаются из .env в окружение сценария. Ключ --env-file
# передаёт их только docker compose, а имя базы и пользователя нужны
# здесь же, в командной строке pg_dump. Cron запускает сценарий
# с пустым окружением, поэтому без этой строки он обрывался на первом
# же обращении к $POSTGRES_USER — то есть копии не делались вовсе.
# Значения с пробелами в .env должны быть взяты в кавычки.
if [ -f "$ROOT/.env" ]; then
    set -a
    . "$ROOT/.env"
    set +a
fi

COMPOSE="docker compose -f $ROOT/deploy/compose.yaml --env-file $ROOT/.env"
TARGET="${BACKUP_DIR:-$ROOT/deploy/backup}"
KEEP_DAYS="${BACKUP_KEEP_DAYS:-30}"
STAMP="$(date +%Y-%m-%d_%H%M)"

mkdir -p "$TARGET"

# Копии пишутся во временное имя и переименовываются только после
# успешного завершения: оборванный файл не должен выглядеть как готовая
# копия. Ключ -T обязателен: без него docker выделяет терминал
# и портит двоичный поток.
PARTIAL_DB="$TARGET/db_$STAMP.dump.part"
PARTIAL_MEDIA="$TARGET/media_$STAMP.tar.gz.part"
trap 'rm -f "$PARTIAL_DB" "$PARTIAL_MEDIA"' EXIT

echo "[$(date '+%F %T')] Копия базы..."
$COMPOSE exec -T db pg_dump \
    -U "$POSTGRES_USER" -d "$POSTGRES_DB" --format=custom \
    > "$PARTIAL_DB"
mv "$PARTIAL_DB" "$TARGET/db_$STAMP.dump"

# Архив принимается потоком, а не пишется в подключённый каталог:
# приложение внутри контейнера работает не от суперпользователя и в
# каталог копий, принадлежащий root, писать не вправе. Здесь файл
# создаёт сам сценарий, и вопрос прав не возникает вовсе.
echo "[$(date '+%F %T')] Копия файлов..."
$COMPOSE run --rm --no-deps -T web \
    tar czf - -C /app/media . > "$PARTIAL_MEDIA"
mv "$PARTIAL_MEDIA" "$TARGET/media_$STAMP.tar.gz"

echo "[$(date '+%F %T')] Удаляю копии старше $KEEP_DAYS суток..."
find "$TARGET" -name 'db_*.dump' -mtime "+$KEEP_DAYS" -delete
find "$TARGET" -name 'media_*.tar.gz' -mtime "+$KEEP_DAYS" -delete

echo "[$(date '+%F %T')] Готово:"
ls -lh "$TARGET" | tail -5
