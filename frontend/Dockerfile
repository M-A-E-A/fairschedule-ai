# Frontend production image: build the Vite bundle, then serve it with nginx.
# Matches `build: ./frontend` in docker-compose.yml. The published origin is
# http://localhost:5173 (the origin the backend CORS allowlist expects);
# nginx listens on the same port inside the container so the compose port
# mapping stays 5173:5173.

# --- Stage 1: build ---------------------------------------------------------
FROM node:20-alpine AS build
WORKDIR /app

# Install dependencies first so the layer is cached across source changes.
COPY package.json package-lock.json ./
RUN npm ci

COPY . .

# VITE_* variables are read at build time and baked into the bundle, so the
# API base URL is passed as a build argument by docker-compose (a runtime
# environment variable would be silently ignored by a built bundle).
ARG VITE_API_BASE_URL=http://localhost:8000
ENV VITE_API_BASE_URL=$VITE_API_BASE_URL
RUN npm run build

# --- Stage 2: serve ---------------------------------------------------------
FROM nginx:1.27-alpine

COPY --from=build /app/dist /usr/share/nginx/html
# nginx.conf makes nginx listen on 5173 and falls back unknown paths to
# index.html so BrowserRouter routes work on deep links and refreshes.
COPY nginx.conf /etc/nginx/conf.d/default.conf

EXPOSE 5173

CMD ["nginx", "-g", "daemon off;"]
