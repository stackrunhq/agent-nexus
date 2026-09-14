# 可选 pgvector 后端（第一阶段）

0010 更新：索引元数据单独持久化，正常原生检索不再加载完整向量 JSON。业务表共 19 张；升级及兼容范围见 [向量元数据](VECTOR_METADATA.md)。旧段落中的 JSON 加载限制已由此优化，但完整发布文本指纹与 128 分片限制仍保留。

默认 `NEXUS_VECTOR_BACKEND=portable` 保持原行为，支持 SQLite 和普通 PostgreSQL。设置为 `pgvector` 后，索引重建会同时写入 PostgreSQL 原生 vector 缓存，检索使用数据库余弦距离排序。算法与类型参考 [pgvector 官方文档](https://github.com/pgvector/pgvector)。

业务迁移仍为 **0009**，18 张业务表保持不变。新增的 `nexus_vectors.entries` 是可重建派生缓存，独立显式初始化，不参与 SQLite 导入。可移植 JSON 快照仍是来源。缓存按版本、模型和向量内容 SHA-256 绑定，旧缓存或缺失缓存返回 `409/pgvector_rebuild_required`，需启用后端后重建；不会悄悄降级。

## 部署

1. 备份 PostgreSQL，停止 API 和 Worker；已有 PostgreSQL 数据目录必须保持主版本 17，不能跨主版本直接切换镜像。
2. 在原 Compose 与 PostgreSQL 覆盖文件之后加入 `docker/compose.pgvector.yaml`，数据库镜像提供 pgvector 扩展。先启动 postgres，完成原 0009 迁移。
3. 使用有扩展/建表权限的数据库账号初始化：

```powershell
docker compose --project-directory . -f docker/compose.yaml -f docker/compose.postgres.yaml -f docker/compose.pgvector.yaml run --rm api python -m agent_nexus_cli.pgvector
```

4. API 和 index-worker 均设置 `NEXUS_VECTOR_BACKEND=pgvector`（覆盖文件已设置），再启动服务。以受限账号运行时，授予该账号 schema `nexus_vectors` 的 USAGE 和 entries 表 SELECT/INSERT/UPDATE/DELETE 权限；不要用应用启动流程自动创建扩展。
5. 在页面重新建立各版本/模型索引。原同步及后台构建路径都写原生缓存，与原快照/任务结果同事务提交。查询仍复核模型权限、内容指纹及发布状态。

原生方式同样执行 `python -m agent_nexus_cli.pgvector`，环境变量 NEXUS_DATABASE_URL 指向已完成业务迁移的 PostgreSQL。扩展须安装在 public schema，设置命令不自动移动已有扩展。

## 验证与当前边界

原生集成测试：设置 `NEXUS_TEST_PGVECTOR_URL` 为专用测试库（需安装扩展、建表及创建临时数据库权限），执行 `pytest api/tests/knowledge/test_pgvector_backend.py`。测试验证余弦排序、模型/版本隔离和快照变化要求重建；不配置时明确跳过。

2026-09-11 已在 Windows 临时 PostgreSQL 17.11 中编译官方 pgvector 0.8.6 并完成原生验证；Docker 引擎仍不可用，未进行容器运行验证。详情见下方基准记录。

**本轮没有提升 128 分片上限，也没有 HNSW/IVFFlat 索引。** 当前仍加载可移植快照并核对完整内容，原生检索是有界精确排序，不是大规模扩容已经完成。下一步需在真实 pgvector 库验证正确性、基准测试，然后拆分大快照存储/元数据、放宽容量并引入近似索引；不能仅提高配置数字。

标准 pg_dump 会包含派生缓存；仅恢复业务表或从 SQLite 导入后，执行初始化和重建即可。应用就绪接口仍检查业务数据库，不验证派生缓存；第一次构建/检索会检查后端。默认后端可随时用于回退，但回退期间的重建可能使原生缓存失效，切回需重新建立索引。

## 原生验证与基准（2026-09-11）

完整回归 135 passed、0 skipped；随后新增原生 API 集成测试，定向 4 passed。验证余弦排序、快照内容绑定、版本/模型隔离，以及 SQLite 导入后建立原生索引、原生与 portable 返回相同分片、跨企业拒绝和撤回文档后索引失效。两个临时实例已停止，生成凭据删除。开发头文件和官方 pgvector 0.8.6 源码在独立临时目录编译，未修改业务数据库。

新增可重复基准：先初始化专用 pgvector 测试数据库，然后设置 NEXUS_TEST_PGVECTOR_URL：

```sh
python -m agent_nexus_cli.vector_benchmark --count 128 --dimensions 64 --rounds 10 --output report.json
```

固定 seed=42，Top-10；只使用随机合成数据，无模型请求或实际手册。工具写入随机版本 ID 的临时缓存行，结束时清除这些行。要求专用测试库，输入规模限制为最多 1048576 个标量。

| 向量数 | 维度 | 轮数 | Top-10 平均重合率 | 查询中位数 | P95 | 最大分数误差 |
| --- | --- | --- | --- | --- | --- | --- |
| 128 | 64 | 10 | 100% | 2.45 ms | 3.22 ms | 4.35e-8 |
| 1024 | 64 | 10 | 100% | 15.35 ms | 24.31 ms | 4.20e-8 |

Windows、本机单客户端、PostgreSQL 17.11/pgvector 0.8.6；耗时包含缓存后端 SQL、载荷摘要/解码和连接操作，不含文档解析、模型调用、权限/全文快照校验。10 轮样本不足以代表负载下的延迟保证。原始记录在 evaluation/results/pgvector-2026-09-11-*.json。

1024 行基准仅验证原生缓存层，不放宽业务 128 分片限制；下一步拆分快照存储与元数据、建立完整管线基准后再调整容量。近似索引 HNSW/IVFFlat 仍未实现。
