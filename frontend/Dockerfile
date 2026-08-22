# Stage 1: Build
FROM node:26-alpine AS builder
WORKDIR /app
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
    PORTFOLIO_AUTH_MODE=${PORTFOLIO_AUTH_MODE}
ARG VITE_API_BASE_URL=/api/v1/
ARG VITE_KAKAO_MAP_KEY=
ARG VITE_APP_BASE_PATH=/
ARG VITE_CSRF_COOKIE_NAME=pongdang_csrftoken
ARG VITE_SSO_ENABLED
ENV VITE_API_BASE_URL=${VITE_API_BASE_URL}
ENV VITE_KAKAO_MAP_KEY=${VITE_KAKAO_MAP_KEY}
ENV VITE_APP_BASE_PATH=${VITE_APP_BASE_PATH}
ENV VITE_CSRF_COOKIE_NAME=${VITE_CSRF_COOKIE_NAME}
ENV VITE_SSO_ENABLED=${VITE_SSO_ENABLED}
COPY frontend/package*.json ./
RUN npm ci
COPY frontend/ .
COPY scripts/portfolio-auth-mode.sh /scripts/portfolio-auth-mode.sh
RUN npm run build

# Stage 2: Serve
FROM nginx:alpine
ARG PORTFOLIO_BRANCH
ARG PORTFOLIO_AUTH_MODE
ENV PORTFOLIO_BRANCH=${PORTFOLIO_BRANCH} \
    PORTFOLIO_AUTH_MODE=${PORTFOLIO_AUTH_MODE}
LABEL org.opencontainers.image.ref.name="${PORTFOLIO_BRANCH}" \
      io.bonifacio.portfolio.auth-mode="${PORTFOLIO_AUTH_MODE}"
RUN normalized_branch="${PORTFOLIO_BRANCH#refs/heads/}" \
    && printf '%s\n%s\n' "$normalized_branch" "$PORTFOLIO_AUTH_MODE" \
         > /etc/portfolio-auth-build \
    && chmod 0444 /etc/portfolio-auth-build
COPY scripts/portfolio-auth-mode.sh /usr/local/bin/portfolio-auth-mode.sh
COPY scripts/portfolio-auth-entrypoint.sh /usr/local/bin/portfolio-auth-entrypoint.sh
RUN chmod 0555 /usr/local/bin/portfolio-auth-mode.sh \
    /usr/local/bin/portfolio-auth-entrypoint.sh
COPY --from=builder /app/dist /usr/share/nginx/html
COPY frontend/nginx.conf /etc/nginx/conf.d/default.conf

# The official image normally starts a root master on port 80. PongDang uses a
# static configuration, so skip the mutating image entrypoint and run the
# master itself as nginx on an unprivileged port. Runtime PID/cache paths are
# writable tmpfs mounts in Compose while the image filesystem stays read-only.
USER nginx
EXPOSE 8080
ENTRYPOINT ["/usr/local/bin/portfolio-auth-entrypoint.sh"]
CMD ["nginx", "-g", "daemon off;"]
