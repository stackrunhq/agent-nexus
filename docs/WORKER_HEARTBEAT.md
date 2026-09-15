# 索引 Worker 心跳与配置观测

步骤 44（2026-09-15）。索引 Worker 启动时登记随机进程实例标识，此后每 10 秒上报调度策略和时间。超过 30 秒未更新或时间在未来的记录计为过期；正常退出删除自身记录，超过一天的记录由后续上报清理。文档解析 Worker 和直接调用 run_once 的基准不参与。

管理员 `GET /api/v1/admin/tenants/{tenant_id}/index-usage` 的 `scheduling.workers` 返回 `recent`、`stale`、`mismatched`、`ttl_seconds` 和 `status`。这是共享数据库全部索引 Worker 的聚合观测，不是本企业专属进程；不返回实例标识或主机信息。原有排队指标仍按企业隔离。

- `unknown`：没有近期上报，不能判断配置是否一致。
- `mismatch`：至少一个近期 Worker 的策略与当前 API 不同，应统一 `NEXUS_INDEX_SCHEDULER` 后重启。
- `matching`：所有近期上报者与当前 API 一致，不保证所有预期进程均已启动。

管理页面通过“刷新索引状态”更新结果。心跳独立于模型请求等待；上报失败将在下一次领取前或退出时暴露，Worker 停止。该机制不续期任务租约，也不证明任务取得进展。机器需同步时钟；强制终止和恢复备份可能暂时保留近期记录，过期记录也不能直接认定进程死亡。

## 升级部署

先备份并停止 API 与全部 Worker，执行 `python -m agent_nexus_cli.database upgrade` 至 **0014**，再启动。新增 `knowledge_index_workers`，共 **24 张业务表**，运行角色需要新表读写权限。备份恢复包含该表；不清理现有任务、索引或检查点，无需重建索引。回退使用验证过的备份。

下一步完善索引失败诊断：按失败原因筛选任务，并在管理端给出可执行的处理建议。
