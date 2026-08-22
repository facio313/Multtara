# Stage 1: Builder
FROM python:3.14-slim-bookworm AS builder

RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential \
    libpq-dev \
    && rm -rf /var/lib/apt/lists/*

COPY requirements.lock /tmp/requirements.lock
RUN pip install \
    --disable-pip-version-check \
    --prefix=/install \
    --no-cache-dir \
    --require-hashes \
    -r /tmp/requirements.lock

# Stage 2: Runtime
FROM python:3.14-slim-bookworm

ARG PORTFOLIO_BRANCH
ARG PORTFOLIO_AUTH_MODE
RUN case "$PORTFOLIO_BRANCH" in ""|*[!A-Za-z0-9._/-]*) exit 1 ;; esac \
    && normalized_branch="${PORTFOLIO_BRANCH#refs/heads/}" \
    && case "$normalized_branch" in ""|*[!A-Za-z0-9._/-]*) exit 1 ;; esac \
    && case "$normalized_branch:$PORTFOLIO_AUTH_MODE" in \
         main:sso|dev:sso) ;; \
         main:*|dev:*) exit 1 ;; \
         *:local) ;; \
         *) exit 1 ;; \
       esac \
    && printf '%s\n%s\n' "$normalized_branch" "$PORTFOLIO_AUTH_MODE" \
         > /etc/portfolio-auth-build \
    && chmod 0444 /etc/portfolio-auth-build
ENV PORTFOLIO_BRANCH=${PORTFOLIO_BRANCH} \
    PORTFOLIO_AUTH_MODE=${PORTFOLIO_AUTH_MODE} \
    PORTFOLIO_BUILD_AUTH_MODE=${PORTFOLIO_AUTH_MODE}

RUN apt-get update && apt-get install -y --no-install-recommends \
    libpq5 \
    && rm -rf /var/lib/apt/lists/*

COPY --from=builder /install /usr/local

WORKDIR /app
COPY . /app/

RUN addgroup --system pongdang \
    && adduser --system --ingroup pongdang --home /app pongdang \
    && chmod +x /app/docker-entrypoint.sh \
    && chown -R pongdang:pongdang /app

USER pongdang

EXPOSE 8000

ENTRYPOINT ["/app/docker-entrypoint.sh"]
CMD ["gunicorn", "config.wsgi:application", "--bind", "0.0.0.0:8000", "--workers", "3", "--timeout", "30", "--graceful-timeout", "30", "--max-requests", "1000", "--max-requests-jitter", "50", "--no-control-socket", "--access-logfile", "-", "--error-logfile", "-"]
