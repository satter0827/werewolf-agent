# syntax=docker/dockerfile:1.7

FROM mcr.microsoft.com/playwright:v1.61.1-noble

WORKDIR /workspace/frontend

COPY frontend/package.json frontend/package-lock.json ./
RUN npm ci

COPY frontend/playwright.config.ts ./
COPY frontend/e2e ./e2e

CMD ["npm", "run", "test:e2e"]
