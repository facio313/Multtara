# Stage 1: Build
FROM node:24-alpine AS builder
WORKDIR /app
ARG VITE_API_BASE_URL=/api/v1/
ARG VITE_KAKAO_MAP_KEY=
ARG VITE_APP_BASE_PATH=/
ARG VITE_CSRF_COOKIE_NAME=pongdang_csrftoken
ENV VITE_API_BASE_URL=${VITE_API_BASE_URL}
ENV VITE_KAKAO_MAP_KEY=${VITE_KAKAO_MAP_KEY}
ENV VITE_APP_BASE_PATH=${VITE_APP_BASE_PATH}
ENV VITE_CSRF_COOKIE_NAME=${VITE_CSRF_COOKIE_NAME}
COPY package*.json ./
RUN npm ci
COPY . .
RUN npm run build

# Stage 2: Serve
FROM nginx:alpine
COPY --from=builder /app/dist /usr/share/nginx/html
COPY nginx.conf /etc/nginx/conf.d/default.conf

# The official image normally starts a root master on port 80. PongDang uses a
# static configuration, so skip the mutating image entrypoint and run the
# master itself as nginx on an unprivileged port. Runtime PID/cache paths are
# writable tmpfs mounts in Compose while the image filesystem stays read-only.
USER nginx
EXPOSE 8080
ENTRYPOINT []
CMD ["nginx", "-g", "daemon off;"]
