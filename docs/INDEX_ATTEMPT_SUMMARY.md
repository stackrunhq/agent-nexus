# 索引任务按尝试汇总

步骤 54（2026-09-16），数据库保持 0017，无新迁移。

管理员任务详情响应增加 `summary`，包含 `scope=all_exact_task_calls`、`attempts` 和 `unconfirmed_request_calls`。服务端对本企业、本模型 embeddings 调用中 index_job_id 等于该任务的全部记录聚合，不受调用列表 offset/limit 影响。其他任务、模型、企业的记录不参与。

每个尝试分组返回 attempt、calls、succeeded、failed、pending，以及 known_input_tokens、known_output_tokens、known_elapsed_ms 和对应 unknown_*_calls。SUM 忽略空值，全部未知时保留 null；已知零值保持 0。精确任务关联但缺少尝试次数的旧记录单列 attempt=null，不按任务当前次数回填。

没有任务 ID 的请求匹配仅计入 unconfirmed_request_calls，不混入精确尝试用量。页面展示每次尝试的调用结果、已知 token、未知记录数和累计调用耗时；没有精确调用时明确提示不能据此认定未调用或未收费。没有调用记录的尝试不生成虚假的零用量分组。

累计调用耗时不是任务总耗时，尤其不能覆盖排队、检查点复用、解析和保存时间。token 不是费用金额，不据此计算账单或模型定价。失败/pending 的未知用量仍可能产生上游费用。汇总与分页明细是实时读取，不保证并发更新时跨 SQL 快照一致；刷新可更新观测。

下一步增加详情按尝试次数和调用状态筛选，支持从统计定位到对应失败调用，同时保持全任务汇总范围明确。
