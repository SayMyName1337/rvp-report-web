# Образ приложения «Суточный рапорт».
#
# Собирается в два этапа: на первом ставятся зависимости Python,
# на втором — только то, что нужно для работы. Так в конечный образ
# не попадают компиляторы и заголовочные файлы.
#
# LibreOffice нужен только для перевода презентаций в PDF и добавляет
# к образу около полугигабайта. Если PDF не нужен, соберите образ
# с `--build-arg WITH_PDF=0`: приложение это переживёт и скажет
# пользователю, что перевод недоступен.

FROM python:3.12-slim AS builder

ENV PIP_NO_CACHE_DIR=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1

RUN apt-get update \
    && apt-get install --no-install-recommends -y build-essential libpq-dev \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /build
COPY requirements/base.txt requirements/base.txt
RUN python -m venv /opt/venv \
    && /opt/venv/bin/pip install --upgrade pip \
    && /opt/venv/bin/pip install -r requirements/base.txt


FROM python:3.12-slim AS runtime

ARG WITH_PDF=1

ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PATH="/opt/venv/bin:$PATH" \
    DJANGO_SETTINGS_MODULE=config.settings.prod \
    # Диаграммы рисуются без экрана.
    MPLBACKEND=Agg

# fonts-liberation метрически совместимы с Arial и Times: без них
# LibreOffice подставляет случайные шрифты, и PDF расходится
# с презентацией по вёрстке.
RUN apt-get update \
    && apt-get install --no-install-recommends -y \
        libpq5 fonts-dejavu-core fonts-liberation tini \
    && if [ "$WITH_PDF" = "1" ]; then \
        apt-get install --no-install-recommends -y \
            libreoffice-impress libreoffice-core; \
    fi \
    && rm -rf /var/lib/apt/lists/*

# Приложение работает не от суперпользователя: если его всё же удастся
# обмануть, права будут ограничены своим каталогом.
RUN useradd --create-home --uid 10001 rvp

COPY --from=builder /opt/venv /opt/venv

WORKDIR /app
COPY --chown=rvp:rvp . /app
RUN chmod +x /app/deploy/entrypoint.sh \
    && mkdir -p /app/media /app/staticfiles \
    && chown -R rvp:rvp /app/media /app/staticfiles

USER rvp

EXPOSE 8000
ENTRYPOINT ["/usr/bin/tini", "--", "/app/deploy/entrypoint.sh"]
CMD ["web"]
