FROM python:3.12-slim

# System deps
RUN apt-get update && apt-get install -y --no-install-recommends \
    supervisor postgresql-client libpq5 ca-certificates curl xz-utils && \
    rm -rf /var/lib/apt/lists/*

WORKDIR /app
RUN mkdir -p /var/log/supervisor

# --- Python deps first for layer caching
COPY requirements.txt /app/requirements.txt
RUN pip install --no-cache-dir -r /app/requirements.txt

# --- Entrypoint + supervisor
COPY docker-entry.sh /usr/local/bin/docker-entry.sh
COPY supervisord.conf /etc/supervisor/conf.d/supervisord.conf
RUN sed -i 's/\r$//' /usr/local/bin/docker-entry.sh && chmod +x /usr/local/bin/docker-entry.sh

# --- PostgREST: try both v13 and v12 filenames
ARG PGRST_VERSION=v13.0.6
RUN set -eux; \
  base="https://github.com/PostgREST/postgrest/releases/download/${PGRST_VERSION}"; \
  for name in \
    "postgrest-${PGRST_VERSION}-linux-static-x86-64.tar.xz" \
    "postgrest-${PGRST_VERSION}-linux-static-x64.tar.xz" \
    "postgrest-${PGRST_VERSION}-linux-x64.tar.xz" \
  ; do \
    url="${base}/${name}"; \
    echo "Trying $url"; \
    if curl -fsSL -o /tmp/postgrest.tar.xz "$url"; then \
      echo "Downloaded $name"; \
      break; \
    fi; \
  done; \
  tar -xJf /tmp/postgrest.tar.xz -C /usr/local/bin; \
  rm /tmp/postgrest.tar.xz; \
  chmod +x /usr/local/bin/postgrest

# --- App code last
COPY . /app

# --- Defaults (override at runtime)
ENV PORT=8000 \
    PYTHONUNBUFFERED=1 \
    GUNICORN_APP="jobLink.app:create_app()" \
    PGRST_SERVER_PORT=3000 \
    PGRST_DB_SCHEMA=public \
    PGRST_DB_ANON_ROLE=anon \
    PGRST_BASE=http://127.0.0.1:3000 \
    FLASK_ENV=production

EXPOSE ${PORT}
ENTRYPOINT ["/usr/local/bin/docker-entry.sh"]
