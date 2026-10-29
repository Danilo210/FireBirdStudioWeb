# Firebird 3 embedded: gera arquivos .FDB reais (ODS 12), sem abrir uma porta Firebird.
FROM python:3.11-slim-bookworm
RUN apt-get update && DEBIAN_FRONTEND=noninteractive apt-get install -y --no-install-recommends \
    firebird3.0-utils firebird3.0-server-core ca-certificates \
    && rm -rf /var/lib/apt/lists/*
WORKDIR /app
COPY index.html server.py ./
COPY static/ ./static/
ENV PYTHONUNBUFFERED=1 PORT=10000
EXPOSE 10000
CMD ["python", "server.py"]
