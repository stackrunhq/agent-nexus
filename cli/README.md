# 运维命令

软件管线基准：`python -m agent_nexus_cli.pipeline_benchmark --output evaluation/results/pipeline-local.json`。使用临时 SQLite 和 HTTP 模型模拟，覆盖解析、构建、恢复、检索问答和配额；结果解释见 [基准说明](../docs/PIPELINE_BENCHMARK.md)。

实现：src/agent_nexus_cli/database.py，复用 API 数据库及迁移定义。安装根项目后可执行：

```sh
nexus-db upgrade
nexus-db check
nexus-db import-sqlite --source /absolute/path/old.db
```

兼容 `python -m agent_nexus.db_cli check`；也可 `python -m agent_nexus_cli.database check`。均读取相同数据库环境变量，前置条件见 [数据库说明](../docs/DATABASE.md)。

知识库 Worker：`python -m agent_nexus_cli.worker`（持续消费）或追加 `--once`（最多一项）；命令入口 nexus-worker。离线预览：`python -m agent_nexus_cli.document manual.pdf`。两者职责见 [知识库说明](../docs/KNOWLEDGE.md)。
