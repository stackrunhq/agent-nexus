# 索引租户轮转调度

当前步骤 44 已增加 [Worker 心跳与策略一致性观测](WORKER_HEARTBEAT.md)，数据库升级至 0014，共 24 张业务表。下述步骤 42/43 为历史记录；当前接口额外返回 `scheduling.workers`。

## 当前增量：管理端状态（步骤 43，2026-09-15）

管理员 `GET /api/v1/admin/tenants/{tenant_id}/index-usage` 新增 `scheduling` 对象：

- `api_strategy`、`observed_at`：当前 API 进程的配置和统计时间；不代表已经探测 Worker 配置。
- `queued`、`processing`、`recovery_pending`：本企业所有应用/模型的当前排队数、处理中数、租约到期数。最后一项是 processing 的子集，不能重复加总。
- `oldest_queued_age_seconds`：最早 queued 任务自创建以来的秒数；无排队任务时为 null。
- `oldest_recovery_overdue_seconds`：最早过期 processing 租约距到期的秒数；无过期租约时为 null。

完成或失败任务不参与等待指标，不读取手册或向量正文，不暴露其他租户及调度游标。秒数下限为 0；没有任务用 null 区分。指标不提供历史平均/P95、预计完成时间或 Worker 健康判断；恢复等待也不代表必然续建成功，重试耗尽可被标记失败。

管理端“模型选择与索引管理”选定模型后展示本企业全部任务统计，点击“刷新索引状态”重新读取。数据库保持 0013，无新迁移。下一步增加 Worker 心跳与配置一致性观测。

步骤 42（2026-09-15），数据库 **0013**，共 **23 张业务表**。

## 配置

`NEXUS_INDEX_SCHEDULER` 支持：

- `fifo`：默认，保持按 `created_at, id` 排序。时间戳精度为秒，同秒任务按 ID 排序，不保证严格提交顺序。
- `tenant_round_robin`：在可领取任务所属租户之间轮转；每次选择上次租户之后的下一个租户 ID，末尾回到开头。租户内部仍按 `created_at, id` 排序。

Compose 的 API 和 index-worker 已接入该变量；原生部署给所有索引 Worker 设置相同值并重启。不要混用不同策略的 Worker；混用不会绕过租约，但不能保证轮转顺序。无效值在 API 配置校验或 Worker 领取时拒绝。

## 一致性与边界

`knowledge_index_scheduler` 的固定 ID=1 行保存上次领取的租户。游标与任务领取在同一个 `index-queue` 数据库事务锁内提交，领取失败则一起回滚。多个 Worker 和进程重启共享该状态；空队列不更新游标。没有待领取任务的租户被跳过，已删除租户的旧游标也不会阻断查找。

轮转适用于 queued 及可重领的过期 processing 任务，保持三次中断上限和现有租约校验。同步构建不经过领取调度。FIFO 模式不更新游标；切回轮转会从上次轮转游标继续。

该策略平衡的是领取机会，不是完成时间、模型调用成本或每租户并发数。长任务不会被抢占；租户仍受现有活跃数/日配额限制。它不提供通用等待 SLA，也不能据此提高容量上限。

## 升级

先备份并停止 API 和全部 Worker，使用迁移账号执行：

```sh
python -m agent_nexus_cli.database upgrade
```

运行账号需新表 SELECT、INSERT、UPDATE、DELETE 权限，备份恢复需包含全部 23 张业务表。0013 只增加调度状态表，不清理现有索引、检查点或任务；无需重建索引。升级后可先以默认 FIFO 启动，再统一切换索引 Worker 的配置。回退用验证过的备份，不执行破坏性 downgrade。

## 验证与下一步

测试覆盖默认顺序、租户轮转、跨 Store 实例持久化、并发去重、事务回滚和显式迁移；PostgreSQL 不均衡负载使用现有 `shared_queue_benchmark --continuous`，通过环境变量分别选择两种策略。

本机 PostgreSQL 17.11 + pgvector 0.8.6、30 周期模拟模型观测：

| 策略 | Worker | 成功任务 | 高频最长等待 ms | 低频最长等待 ms |
| --- | ---: | ---: | ---: | ---: |
| FIFO | 1 | 34 | 1074.2 | 883.4 |
| 轮转 | 1 | 31 | 1274.9 | 199.4 |
| FIFO | 4 | 89 | 176.1 | 165.5 |
| 轮转 | 4 | 89 | 183.9 | 158.8 |

原始记录：[FIFO](../evaluation/results/scheduler-fifo-2026-09-15.json)、[轮转](../evaluation/results/scheduler-tenant_round_robin-2026-09-15.json)。四组均无重复领取、任务遗漏或遗留检查点。单 Worker 下低频等待降低，同时高频等待增加；任务合并导致实际任务数不同，不能视为严格等工作量性能对照。样本短且 ID/竞争时机变化，不提供普遍延迟保证，因此默认仍为 FIFO。

下一步增加调度策略和租户等待指标的管理端展示，支持运维判断。继续保留 128 分片限制。
