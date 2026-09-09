# 容器部署

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

Dockerfile 将 api/src、cli/src、web/src 一起打包。.dockerignore 留在根目录，因为根目录是构建上下文。不要在 docker/ 内直接套用这些命令。升级与备份见 [数据库说明](../docs/DATABASE.md)。
