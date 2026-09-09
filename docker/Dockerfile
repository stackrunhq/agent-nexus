FROM node:22-slim AS frontend
WORKDIR /frontend
COPY web/package.json web/package-lock.json ./
RUN npm ci --no-audit --no-fund
COPY web/index.html web/tsconfig.json web/vite.config.ts ./
COPY web/src/app ./src/app
RUN npm run build

FROM python:3.12-slim
WORKDIR /app
COPY pyproject.toml ./
COPY requirements.lock ./
COPY api/src ./api/src
COPY cli/src ./cli/src
COPY web/src ./web/src
COPY --from=frontend /frontend/src/agent_nexus_web/static/tenants ./web/src/agent_nexus_web/static/tenants
RUN pip install --no-cache-dir --require-hashes -r requirements.lock \
    && pip install --no-cache-dir --no-deps . && useradd --uid 10001 --create-home nexus \
    && mkdir /app/data && chown nexus:nexus /app/data
USER nexus
EXPOSE 8000
CMD ["uvicorn", "agent_nexus.app:create_app", "--factory", "--host", "0.0.0.0", "--port", "8000"]
