# 数据库部署与迁移

存储层使用 SQLAlchemy，同时支持 SQLite 和 PostgreSQL（psycopg 驱动）。数据库存模型配置、配置审计、企业、模型授权和企业事件，共 5 张业务表；凭据摘要保持不变。

## 选择数据库

- 不设置 `NEXUS_DATABASE_URL`：使用 `NEXUS_DATABASE_PATH` 的 SQLite 文件，保留开发环境自动创建缺失表的行为。
- 设置 `NEXUS_DATABASE_URL=postgresql+psycopg://用户名:密码@主机:5432/数据库名`：使用 PostgreSQL，URL 优先于文件路径。用户名、密码中的特殊字符需要 URL 编码，不把真实连接串加入 Git。
- PostgreSQL 启动前必须迁移至 0001，缺少版本或版本不匹配时 API 拒绝启动。API 不自动执行生产迁移。

## 原生迁移

先设置上述环境变量，安装更新后的锁定依赖，执行：

```sh
python -m agent_nexus.db_cli upgrade
uvicorn agent_nexus.app:create_app --factory --host 127.0.0.1 --port 8000
```

迁移脚本打包在 Python 包内，无需在项目根目录查找 alembic.ini。重复 upgrade 不重复建表。初始迁移允许登记已有已知列布局的 SQLite 数据库，不会覆盖数据；不自动接管未登记版本的 PostgreSQL 表。

本阶段 SQLite 自动建表仅服务开发便利，不替代后续版本迁移。正式升级仍应执行 upgrade。降级删除数据的操作被禁用，回退应使用经过验证的备份。

## Docker PostgreSQL

复制 `.env.example` 为 `.env`，配置管理员令牌及所需模式，再设置：

```dotenv
NEXUS_POSTGRES_PASSWORD=替换为随机密码
NEXUS_DATABASE_URL=postgresql+psycopg://nexus:编码后的同一密码@postgres:5432/nexus
```

```sh
docker compose -f compose.yaml -f compose.postgres.yaml up --build -d
```

启动顺序为 postgres 健康检查 → migrate 执行 Alembic → api。数据库端口不映射到宿主机，数据保存在 postgres-data 命名卷。生产环境应按组织规则管理数据库角色和密钥；示例为简化的单机部署，不是高可用或最小权限配置。

每次升级应先备份、暂停写入，重新执行迁移服务再启动 API；不要假定已退出的 migrate 容器会因所有类型的版本变更自动重跑。可显式执行 `docker compose -f compose.yaml -f compose.postgres.yaml run --rm migrate`。不要执行带 `-v` 的 down 来升级，否则会删除数据卷。

## 从 SQLite 导入

1. 停止旧 API 及所有写入者，备份完整数据库。若使用 WAL，采用 SQLite backup API 或包含已正确检查点的数据，不能只复制正在写入的主文件。
2. 建立目标 PostgreSQL，并执行 upgrade。目标 5 张业务表必须为空。
3. 将目标连接串放入 NEXUS_DATABASE_URL，执行：

```sh
python -m agent_nexus.db_cli import-sqlite --source /absolute/path/old-nexus.db
```

4. 导入成功输出各表条数；检查模型配置、企业密钥认证、授权及审计记录后再切换流量。

导入使用只读源连接和单次源快照，按外键顺序分批写入，逐表计算内容摘要核对后提交；失败回滚目标业务数据。拒绝同源同目标及非空目标，保留源文件；不自动合并或覆盖。PostgreSQL 导入期间锁定目标业务表，成功后校正审计自增序列。请在维护窗口执行，目标锁会阻止并发写入。

当前工具迁移业务数据，不复制原 SQLite 的触发器、自定义索引或 alembic_version；目标使用本版本标准结构。导入本身不验证企业应用业务语义。

## 并发与连接

同一模型别名的写入使用事务锁后校验 ETag；同一企业的授权/停用/轮换使用企业事务锁。SQLite 使用 BEGIN IMMEDIATE，PostgreSQL 使用事务级 advisory lock；审计与更新仍原子提交。不同进程需要使用同一数据库和本应用写入约定，直接 SQL 写入不受 ETag 保护。

应用共享连接池，在退出时释放。异步模型请求中的同步数据库查询在线程池执行。连接串和 SQL 参数不写入业务错误响应。

## 验证与限制

SQLite 回归、导入校验和回滚已自动测试。PostgreSQL 集成测试位于 tests/test_postgres.py，只有显式设置 NEXUS_TEST_POSTGRES_URL 才执行；测试会创建并删除独立随机 schema。CI 已配置专用 PostgreSQL 17 服务。

当前机器无 PostgreSQL 服务且 Docker Engine 未运行，因此真实 PostgreSQL 测试尚未执行。此版本仍无 PostgreSQL RLS、企业用户体系、备份自动化或恢复演练，不能直接视为完整多租户生产方案。

实现依据：[SQLAlchemy 事务文档](https://docs.sqlalchemy.org/en/20/core/connections.html)、[Alembic 迁移文档](https://alembic.sqlalchemy.org/en/latest/tutorial.html)。
