# PostgreSQL 实库与备份恢复演练

## 0005 向量快照（2026-09-10）

PostgreSQL 17.11 全量 **103 passed、0 skipped**，恢复摘要覆盖 14 张业务表；新增向量快照及模型授权后，恢复环境中个人企业成员使用受限数据库账号完成向量检索。embedding 服务采用 HTTP 模拟，未验证真实模型质量。临时服务器已停止，生成凭据已删除。下列早期版本为历史结果。

## 0004 知识库升级（2026-09-09）

本轮 PostgreSQL 17.11 全量 **95 passed、0 skipped**，包含 13 张业务表的摘要恢复校验。新增原文件 bytea 与来源分片恢复、已发布文档的个人企业身份读取；受限运行角色授权包含 knowledge_documents、knowledge_chunks。临时服务器已停止、生成凭据文件已删除。以下 0001–0003 结果为历史记录。

升级/导入/恢复前停止 API 和 Worker，先备份再升级 0004。文件与数据库一起备份，不依赖单独文件卷；恢复后的 processing 任务由 Worker 在 5 分钟租约到期后重新领取。当前未验证大文件规模的备份性能或生产 RPO/RTO。

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

## 0002 身份数据升级

2026-09-09 本轮已在独立 PostgreSQL 17.11 再次执行全量测试：69 passed、0 skipped。包含个人账号、密码摘要、会话恢复，以及八表和受限运行角色校验。测试后服务器已停止，临时凭据文件已移除。

当前业务表增至八张，测试现包含个人账号、密码摘要和会话恢复校验；上面的 0001 五表结果为历史记录。受限角色需增加下方三张身份表权限。备份和导入保留会话，正式恢复切换若需全员重新登录，须在维护窗口清理 user_sessions。

## 0003 应用版本升级

2026-09-09 已完成 PostgreSQL 17.11 实库演练，全量 73 passed、0 skipped；恢复后用个人企业成员身份读取已发布版本，并验证受限运行角色及新增应用事件序列。临时服务已停止、生成凭据已删除。

0003 时业务表为 11 张，新增应用、版本和应用事件。下面的运行角色授权已更新；恢复测试加入已发布版本读取和应用事件序列校验。上面的 0001/0002 结果属于历史记录。

## 重复执行自动化演练

准备**专用测试服务器**和同版本 pg_dump/pg_restore。测试连接角色需具有创建数据库、schema 和角色的权限；不要指向生产服务器。

设置 `NEXUS_TEST_POSTGRES_URL` 为该测试服务器的 SQLAlchemy 连接串，设置 `NEXUS_TEST_PG_BIN` 为 PostgreSQL bin 目录，然后执行：

```sh
python -m pytest -q api/tests/storage/test_postgres.py api/tests/storage/test_postgres_restore.py
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
ON models, model_audit, tenants, tenant_models, tenant_events, users, user_sessions, user_events, applications, application_versions, application_events, knowledge_documents, knowledge_chunks, knowledge_vector_indexes TO nexus_app;
GRANT SELECT ON alembic_version TO nexus_app;
GRANT USAGE, SELECT ON ALL SEQUENCES IN SCHEMA public TO nexus_app;
```

目标 schema 不应向 PUBLIC 开放 CREATE（PostgreSQL 17 新库的默认权限符合本次演练）。已有数据库需另行检查权限。本模板不是企业数据行级隔离；基础个人身份已在 0002 实现；RLS、不可篡改审计和后续新增表授权仍需设计。Compose 当前仍使用简化的统一数据库账户，生产落地需拆分迁移与 API 连接凭据。

依据：[PostgreSQL 17 pg_restore](https://www.postgresql.org/docs/17/app-pgrestore.html)、[PostgreSQL Windows 二进制说明](https://www.postgresql.org/download/windows/)。
