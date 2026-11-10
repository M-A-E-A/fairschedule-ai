# Frontend dev server (Vite) — matches `build: ./frontend` in docker-compose.yml.
# Serves on 5173 with host 0.0.0.0 (configured in vite.config.ts) so the port
# mapping works from the host machine.
FROM node:20-alpine

WORKDIR /app

# Install dependencies first so the layer is cached across source changes.
COPY package.json package-lock.json ./
RUN npm ci

COPY . .

EXPOSE 5173

# VITE_API_BASE_URL is injected by docker-compose; Vite reads VITE_* variables
# from the process environment at dev-server start.
CMD ["npm", "run", "dev", "--", "--host", "0.0.0.0", "--port", "5173"]
