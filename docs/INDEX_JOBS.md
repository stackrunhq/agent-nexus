# 后台索引任务

数据库迁移 **0006** 新增 `knowledge_index_jobs`，业务表共 15 张。升级前停止 API 和两个 Worker、备份数据库，运行 `python -m agent_nexus.db_cli upgrade`。生产库不会自动迁移。

## 启动与操作

解析 Worker 保持原命令；索引 Worker 独立启动：

```sh
python -m agent_nexus_cli.worker --queue indexes
```

加 `--once` 最多消费一项任务。两个 Worker 与 API 必须连接同一数据库。索引 Worker 需要与 API 相同的 `NEXUS_ALLOWED_HOSTS` 和所选模型的 `NEXUS_PROVIDER_*` 凭据，但不需要管理员令牌。Compose 新增 `index-worker`，默认传递 CLOUD_KEY；使用其他凭据环境变量时需在该服务中补充配置。PostgreSQL 覆盖配置等待 migrate 成功后启动。

知识库 → 向量索引与检索 → 确认建立，返回排队任务。点击“刷新索引状态”查看最近 20 项任务和当前模型索引；页面不自动轮询。关闭页面不会取消任务。

管理员接口前缀：`/api/v1/admin/tenants/{tenant_id}/applications/{app_id}/versions/{version_id}`。

| 接口 | 行为 |
| --- | --- |
| `POST /index-jobs`，`{"model":"alias"}` | 校验发布资料、授权和容量；202 返回任务 |
| `GET /index-jobs` | 返回该范围最近 20 项任务，含状态、尝试次数及错误码 |

状态为 queued、processing、succeeded、failed。相同版本/模型有活跃任务时复用，每企业最多 5 个活跃任务，超出返回 `429/index_queue_full`。提交时不调用模型，执行时重新核验资料和模型授权，按**执行时**当前配置/发布内容构建。失败后可以重新提交；不会自动重试模型报错。

## 恢复与边界

领取租约 300 秒，异常中断到期可再次领取，最多 3 次后标记 `worker_interrupted`。租约令牌与有效期在索引保存事务内校验，成功状态和索引一起提交；旧 Worker 不可覆盖新 Worker 的结果。模型请求可能已计费，中断恢复不是上游恰好一次调用。索引维持 128 分片、4096 维、16 MiB、嵌入总计 120 秒限制。

原同步 `POST /vector-index` 保留响应兼容，现已共用任务登记、活跃数限制和每日准入额度，见 [索引构建配额](INDEX_QUOTAS.md)。这不是企业 token/费用配额。当前没有进度百分比、取消任务、历史清理、优先级或租户公平调度；失效索引仍须明确重建。

代码：`knowledge/index_jobs.py` 负责入队/领取/执行/租约；`storage/index_job_schema.py` 与冻结 0006 迁移定义表；`cli/…/worker.py --queue indexes` 运行独立消费循环。

当前数据库为 0007，新增 tenant_index_quotas，共 16 张业务表；升级前停止 API 与 Worker 并备份。企业差异化限额通过 index-quota 管理接口配置。

当前数据库 0008 新增 model_calls，17 张业务表，覆盖企业网关调用结果及上游 token 账本。升级前备份并停止 API/Worker；调用次数与 token 配额尚未实现。
# 当前更新：批次恢复

0011 起后台 Worker 支持持久检查点和同任务中断恢复，成功/终止失败时清理。内容或模型修订不匹配时重新构建；普通失败不会自动续跑。升级、配额及重复调用边界见 [索引检查点](INDEX_CHECKPOINTS.md)。以下为历史基础设计。
