# 容器部署

**已有 0001/0002/0003/0004/0005 数据库须先备份并升级到 0006。** SQLite：暂停 API 和 Worker 后执行 `docker compose --project-directory . -f docker/compose.yaml run --rm --build api python -m agent_nexus.db_cli upgrade`，再启动 API 和 Worker；PostgreSQL 使用覆盖配置执行 migrate 服务，见 DATABASE.md。

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

Compose 新增独立 worker 服务，使用同一数据库处理知识库队列，原文件随数据库一起备份。没有 Worker 时上传仍会返回 queued；API 就绪检查不检查队列消费。运行机制、原生启动和接口步骤见 [知识库说明](../docs/KNOWLEDGE.md)。本阶段未采用 S3/Redis/Celery。

知识库页面入口：/admin/tenants → 管理版本 → 管理知识库。更新页面需重新构建镜像；本轮向量快照新增 0005 迁移，须先备份升级。Worker 必须独立运行才能消费上传任务。

本轮混合检索和引用问答复用 API 进程与网关配置，数据库已升级为 0006，新增索引 Worker 服务。部署后在知识库管理中先建立索引，再选择已授权聊天模型。页面通过索引 Worker 后台构建，解析 Worker 仍只负责文件解析。见 [问答说明](../docs/ANSWERS.md)。

新增 index-worker 服务，消费持久化索引任务；部署前升级至 0006。页面构建操作已改为提交后台任务，详见 [索引任务](../docs/INDEX_JOBS.md)。

索引构建额度由 NEXUS_INDEX_DAILY_LIMIT 配置，默认每企业每天 100 个新任务（UTC 日）。所有 API 副本须使用同值。同步和后台构建共用额度，详见 [索引配额](../docs/INDEX_QUOTAS.md)。
