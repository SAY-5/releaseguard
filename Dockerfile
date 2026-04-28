# syntax=docker/dockerfile:1.7
FROM python:3.12-slim
ENV PYTHONUNBUFFERED=1 PYTHONDONTWRITEBYTECODE=1 PIP_NO_CACHE_DIR=1
WORKDIR /srv

RUN apt-get update && apt-get install -y --no-install-recommends ca-certificates docker.io \
 && rm -rf /var/lib/apt/lists/*

COPY pyproject.toml ./
RUN pip install --upgrade pip && pip install ".[dev]"
COPY releaseguard ./releaseguard
COPY web ./web

RUN useradd -u 10001 -m rg && chown -R rg /srv
USER rg
ENTRYPOINT ["rg"]
CMD ["--help"]
