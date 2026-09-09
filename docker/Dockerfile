FROM python:3.12-slim
WORKDIR /app
COPY pyproject.toml ./
COPY requirements.lock ./
COPY api/src ./api/src
COPY cli/src ./cli/src
COPY web/src ./web/src
RUN pip install --no-cache-dir --require-hashes -r requirements.lock \
    && pip install --no-cache-dir --no-deps . && useradd --uid 10001 --create-home nexus \
    && mkdir /app/data && chown nexus:nexus /app/data
USER nexus
EXPOSE 8000
CMD ["uvicorn", "agent_nexus.app:create_app", "--factory", "--host", "0.0.0.0", "--port", "8000"]
