# 运维命令

实现：src/agent_nexus_cli/database.py，复用 API 数据库及迁移定义。安装根项目后可执行：

```sh
nexus-db upgrade
nexus-db check
nexus-db import-sqlite --source /absolute/path/old.db
```

兼容 `python -m agent_nexus.db_cli check`；也可 `python -m agent_nexus_cli.database check`。均读取相同数据库环境变量，前置条件见 [数据库说明](../docs/DATABASE.md)。
