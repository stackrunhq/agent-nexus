# 运维命令

多管线进程树基准：`python -m agent_nexus_cli.pipeline_concurrency --postgres-pid 12345 --output evaluation/results/pipeline-concurrency-local.json`。要求本机专用 PostgreSQL 的准确主进程 PID，详见 [采样范围](../docs/PIPELINE_CONCURRENCY.md)。

PostgreSQL 完整管线：`python -m agent_nexus_cli.postgres_pipeline --output evaluation/results/postgres-pipeline-local.json`，需要测试服务器 `NEXUS_TEST_PGVECTOR_URL` 及创建数据库权限，运行时自建随机隔离数据库，结束后删除。见 [运行边界](../docs/POSTGRES_PIPELINE.md)。

pgvector 并发基准：`python -m agent_nexus_cli.vector_concurrency --output evaluation/results/vector-concurrency-local.json`，需要专用已初始化 PostgreSQL 连接 `NEXUS_TEST_PGVECTOR_URL`。见 [并发基准](../docs/VECTOR_CONCURRENCY.md)。

软件管线基准：`python -m agent_nexus_cli.pipeline_benchmark --output evaluation/results/pipeline-local.json`。使用临时 SQLite 和 HTTP 模型模拟，覆盖解析、构建、恢复、检索问答和配额；结果解释见 [基准说明](../docs/PIPELINE_BENCHMARK.md)。

实现：src/agent_nexus_cli/database.py，复用 API 数据库及迁移定义。安装根项目后可执行：

```sh
nexus-db upgrade
nexus-db check
nexus-db import-sqlite --source /absolute/path/old.db
```

兼容 `python -m agent_nexus.db_cli check`；也可 `python -m agent_nexus_cli.database check`。均读取相同数据库环境变量，前置条件见 [数据库说明](../docs/DATABASE.md)。

知识库 Worker：`python -m agent_nexus_cli.worker`（持续消费）或追加 `--once`（最多一项）；命令入口 nexus-worker。离线预览：`python -m agent_nexus_cli.document manual.pdf`。两者职责见 [知识库说明](../docs/KNOWLEDGE.md)。
