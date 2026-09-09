# 容器部署

**已有 0001/0002 数据库须先备份并升级到 0003。** SQLite：暂停 API 后执行 `docker compose --project-directory . -f docker/compose.yaml run --rm --build api python -m agent_nexus.db_cli upgrade`，再启动 API；PostgreSQL 使用覆盖配置执行 migrate 服务，见 DATABASE.md。

以下命令均从仓库根执行，先配置根 .env。显式项目目录保持根环境文件、构建上下文和默认项目名称一致；已有部署使用过 -p 的继续指定原名称，以复用数据卷。

```sh
# SQLite
docker compose --project-directory . -f docker/compose.yaml up --build -d
# PostgreSQL：另需设置密码与连接串
docker compose --project-directory . -f docker/compose.yaml -f docker/compose.postgres.yaml up --build -d
# 配置校验
docker compose --project-directory . -f docker/compose.yaml config --quiet
# 单独构建
docker build -f docker/Dockerfile -t agent-nexus:local .
```

Dockerfile 先用 Node 22 执行 npm ci 和前端构建，再将 API、CLI、原页面及 React 构建资源放入 Python 镜像。.dockerignore 留在根目录，因为根目录是构建上下文。不要在 docker/ 内直接套用这些命令。升级与备份见 [数据库说明](../docs/DATABASE.md)。
