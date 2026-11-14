FROM apache/airflow:3.4.0-python3.12

COPY --from=ghcr.io/astral-sh/uv:0.11.29 /uv /usr/local/bin/uv

# pg_dump must be at least the server's major version (18); Debian's default client is older.
USER root
RUN apt-get update \
 && apt-get install -y --no-install-recommends curl ca-certificates gnupg \
 && install -d /usr/share/postgresql-common/pgdg \
 && curl -fsSL https://www.postgresql.org/media/keys/ACCC4CF8.asc \
      -o /usr/share/postgresql-common/pgdg/apt.postgresql.org.asc \
 && . /etc/os-release \
 && echo "deb [signed-by=/usr/share/postgresql-common/pgdg/apt.postgresql.org.asc] https://apt.postgresql.org/pub/repos/apt ${VERSION_CODENAME}-pgdg main" \
      > /etc/apt/sources.list.d/pgdg.list \
 && apt-get update \
 && apt-get install -y --no-install-recommends postgresql-client-18 \
 && apt-get clean && rm -rf /var/lib/apt/lists/*
USER airflow

# Pipeline deps only, with Airflow pinned so the resolver can't move anything Airflow needs.
# --compile-bytecode: uv skips .pyc generation by default, so every Airflow process would compile
# boto3/botocore from source on first import. Concurrent task starts then blew the 30 s DAG
# import timeout (asset URIs trigger provider discovery, which imports the Amazon provider).
COPY docker/requirements-airflow.txt /tmp/requirements-airflow.txt
RUN uv pip install --no-cache --compile-bytecode --python "$(command -v python)" \
      "apache-airflow==${AIRFLOW_VERSION}" -r /tmp/requirements-airflow.txt \
 && python -m compileall -q "$(python -c 'import site; print(site.getusersitepackages())')" || true

# Code is baked in, so production runs exactly what CI tested. Local dev mounts over these paths.
COPY --chown=airflow:root dags /opt/airflow/dags
COPY --chown=airflow:root src /opt/airflow/project/src
COPY --chown=airflow:root config/feeds.yaml /opt/airflow/project/config/feeds.yaml
COPY --chown=airflow:root migrations /opt/airflow/project/migrations
COPY --chown=airflow:root alembic.ini /opt/airflow/project/alembic.ini
ENV PYTHONPATH=/opt/airflow/project/src
