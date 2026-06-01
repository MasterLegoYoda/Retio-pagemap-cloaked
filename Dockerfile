# Stage 1: uv로 패키지 설치
FROM python:3.14-slim-trixie AS builder
ARG PAGEMAP_VERSION=1.0.0
COPY --from=ghcr.io/astral-sh/uv:0.8 /uv /usr/local/bin/uv
RUN uv venv /opt/pagemap && \
    uv pip install --python /opt/pagemap/bin/python \
        "retio-pagemap==${PAGEMAP_VERSION}"

# Stage 2: CloakBrowser binary preinstall + non-root runtime
FROM python:3.14-slim-trixie
COPY --from=builder /opt/pagemap /opt/pagemap
ENV PATH="/opt/pagemap/bin:$PATH"
ENV CLOAKBROWSER_CACHE_DIR=/opt/cloakbrowser
ENV CLOAKBROWSER_AUTO_UPDATE=false

RUN apt-get update && \
    apt-get install -y --no-install-recommends \
        libnss3 libnspr4 libdbus-1-3 libatk1.0-0 libatk-bridge2.0-0 \
        libcups2 libdrm2 libxkbcommon0 libatspi2.0-0 libxcomposite1 \
        libxdamage1 libxfixes3 libxrandr2 libgbm1 libpango-1.0-0 \
        libcairo2 libasound2t64 libwayland-client0 fonts-liberation \
        ca-certificates && \
    apt-get clean && rm -rf /var/lib/apt/lists/* && \
    cloakbrowser install

RUN groupadd -r pagemap && useradd -r -g pagemap -m pagemap && \
    chown -R pagemap:pagemap /opt/cloakbrowser
USER pagemap
WORKDIR /home/pagemap

# MCP Registry 소유권 검증용 OCI 라벨
LABEL io.modelcontextprotocol.server.name="io.github.Retio-ai/pagemap"

EXPOSE 8000
STOPSIGNAL SIGTERM

ENTRYPOINT ["retio-pagemap"]
