# PostgreSQL 实库与备份恢复演练

## 本次结果（2026-09-09）

已在 Windows 上运行独立 PostgreSQL 17.11，使用 Python 3.12.14 完成全部测试：**61 passed，0 skipped**。没有依赖 Docker，数据库仅监听 127.0.0.1:55439，演练后已停止。

验证范围：

- Alembic 迁移、重复升级、未迁移拒绝启动、SQLite 导入和序列校正。
- 企业密钥认证、模型授权、停用以及模型 ETag 并发写入。
- `pg_dump --format=custom` 备份，在另一个全新数据库用 `pg_restore --single-transaction --exit-on-error` 恢复。
- 对比五张业务表的逐表内容摘要，确认迁移版本 0001、模型配置、凭据摘要、授权及审计完整。
- 恢复后执行健康检查、企业模型列表和对话 API；模型上游使用 HTTP 模拟服务，数据库为真实 PostgreSQL。
- 恢复后继续写入，审计自增序列无冲突。
- 受限运行角色可执行所需业务读写，无法建表或修改 alembic_version。

测试自动创建随机名称的源库、恢复库及运行角色；演练结束确认残留测试数据库为 0、测试角色为 0。生成的明文凭据文件已删除，下载包及临时运行文件不纳入 Git。

这不是生产规模灾备认证：没有测量大数据量恢复时间、RPO/RTO、跨机恢复、PITR 或高可用切换。Docker 部署和真实模型联调仍待验证。

## 重复执行自动化演练

准备**专用测试服务器**和同版本 pg_dump/pg_restore。测试连接角色需具有创建数据库、schema 和角色的权限；不要指向生产服务器。

设置 `NEXUS_TEST_POSTGRES_URL` 为该测试服务器的 SQLAlchemy 连接串，设置 `NEXUS_TEST_PG_BIN` 为 PostgreSQL bin 目录，然后执行：

```sh
python -m pytest -q tests/storage/test_postgres.py tests/storage/test_postgres_restore.py
```

执行完整回归使用 `python -m pytest -q`。缺少服务器/工具时相关测试会跳过，跳过不等于通过。CI 配置会准备 PostgreSQL 17 与对应客户端，但本次没有推送，未运行远端 CI。

Windows 原生工具应放在不含特殊字符的路径；本次项目目录的特殊连字符导致 initdb 自重启失败，使用 ASCII 临时目录后成功。原生服务启动日志应写文件，避免后台子进程继承管道导致启动控制进程等待输出无法结束。

## 手工备份与恢复流程

以下操作在专用数据库或正式维护窗口执行。通过 PGHOST、PGPORT、PGUSER、PGDATABASE 及安全凭据机制设置连接，不把密码放入命令参数或 Git。

```sh
pg_dump --format=custom --no-owner --no-acl --file=nexus.backup
pg_restore --list nexus.backup
```

新建空的恢复数据库，然后切换 PGDATABASE 到该库：

```sh
pg_restore --exit-on-error --single-transaction --no-owner --no-acl --dbname=新建的恢复数据库 nexus.backup
```

恢复流程不使用 `--clean` 或覆盖生产库。`--list` 只检查归档目录，必须继续执行实际恢复、数据核验和应用验证。备份中有配置和凭据摘要，应按敏感文件保护并制定保留周期。

备份未包含全局角色，且示例不恢复原所有者和 ACL；恢复后需要重建或重新授权运行角色。应用切换到恢复库前，检查版本、五张表、授权、健康接口、企业凭据以及新写入序列，再决定是否切换。

## 运行角色参考

迁移角色负责建表和升级。运行角色只需要连接、schema 使用、业务表 DML 和序列权限。用管理员预先创建并安全设置 nexus_app 密码，在目标数据库执行：

```sql
GRANT CONNECT ON DATABASE nexus TO nexus_app;
GRANT USAGE ON SCHEMA public TO nexus_app;
GRANT SELECT, INSERT, UPDATE, DELETE
ON models, model_audit, tenants, tenant_models, tenant_events TO nexus_app;
GRANT SELECT ON alembic_version TO nexus_app;
GRANT USAGE, SELECT ON ALL SEQUENCES IN SCHEMA public TO nexus_app;
```

目标 schema 不应向 PUBLIC 开放 CREATE（PostgreSQL 17 新库的默认权限符合本次演练）。已有数据库需另行检查权限。本模板不是企业数据行级隔离；RLS、个人身份、不可篡改审计和后续新增表的授权仍需设计。Compose 当前仍使用简化的统一数据库账户，生产落地需拆分迁移与 API 连接凭据。

依据：[PostgreSQL 17 pg_restore](https://www.postgresql.org/docs/17/app-pgrestore.html)、[PostgreSQL Windows 二进制说明](https://www.postgresql.org/download/windows/)。
