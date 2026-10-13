FROM postgres:16@sha256:ca0bd484cb98bf4b24eb1010e73fb3fcbd6714d240fbc1a10eea5b7dbecb641d AS migration

COPY database/schema /schema
COPY deploy/docker/migrate.sh /migration/migrate.sh

ENTRYPOINT ["/bin/sh", "/migration/migrate.sh"]
CMD ["migrate"]

FROM python:3.13-slim@sha256:70729b46c69b4f1e97c4822c1af3df53a1476cf5ddc6c087c0c10bc3a5678c2f AS runtime

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1

WORKDIR /app

RUN groupadd --gid 10001 app \
    && useradd --uid 10001 --gid app --shell /usr/sbin/nologin app

COPY requirements.txt /app/requirements.txt
RUN python -m pip install --require-hashes -r /app/requirements.txt

COPY --chown=app:app . /app
RUN mkdir -p /app/output/report \
    && chown -R app:app /app/output

ARG GIT_SHA=""
ARG APP_VERSION="local"

LABEL org.opencontainers.image.revision=$GIT_SHA \
    org.opencontainers.image.version=$APP_VERSION

ENV APP_VERSION=$APP_VERSION

USER app

EXPOSE 8080

CMD ["gunicorn", "--bind", "0.0.0.0:8080", "--workers", "2", "--threads", "4", "--access-logfile", "-", "--error-logfile", "-", "webapp.wsgi:app"]
