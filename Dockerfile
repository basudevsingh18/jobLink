# --- Stage 1: grab the official postgrest binary ---
FROM postgrest/postgrest:v12.0.2 AS postgrest_src

# --- Stage 2: final image with Python + supervisord + psql + postgrest ---
FROM python:3.12-slim

# System deps: supervisor (process manager), psql client, libpq, certs
RUN apt-get update && apt-get install -y --no-install-recommends \
    supervisor postgresql-client libpq5 ca-certificates && \
    rm -rf /var/lib/apt/lists/*

# Workdir & logs
WORKDIR /app
RUN mkdir -p /var/log/supervisor

# Copy your app code
COPY . /app

# Python deps
RUN pip install --no-cache-dir -r requirements.txt

# Copy postgrest binary from stage 1
COPY --from=postgrest_src /usr/local/bin/postgrest /usr/local/bin/postgrest

# Supervisord config + entrypoint
COPY supervisord.conf /etc/supervisor/conf.d/supervisord.conf
COPY docker-entry.sh /usr/local/bin/docker-entry.sh
RUN chmod +x /usr/local/bin/docker-entry.sh

# Defaults (Render injects PORT at runtime; these are safe fallbacks)
ENV PORT=8000 \
    PYTHONUNBUFFERED=1 \
    # Gunicorn import path for your Flask factory (override in Render if needed)
    GUNICORN_APP="jobLink.app:create_app()" \
    # PostgREST internal port & defaults
    PGRST_SERVER_PORT=3000 \
    PGRST_DB_SCHEMA=public \
    PGRST_DB_ANON_ROLE=anon \
    # Flask talks to PostgREST over localhost in-container
    PGRST_BASE=http://127.0.0.1:3000 \
    FLASK_ENV=production

EXPOSE ${PORT}

# Run migrations/seeds, then start gunicorn + postgrest under supervisord
ENTRYPOINT ["/usr/local/bin/docker-entry.sh"]
