# 管理员索引任务详情

步骤 51（2026-09-15），数据库保持 0015。

管理端任务历史每行提供“查看任务详情”，支持独立刷新、关闭以及关联调用分页。详情展示任务状态、尝试次数、错误建议、请求 ID，以及调用状态、错误码、耗时和已知 token。关闭详情取消尚未完成的请求。

管理员接口：`GET /api/v1/admin/tenants/{tenant_id}/applications/{app_id}/versions/{version_id}/index-jobs/{job_id}?offset=0&limit=20`。offset 范围 0–100000，limit 范围 1–100；返回 `task`、`calls` 和 `correlation`。calls 包含 data、offset、limit、has_more，按调用创建时间及 ID 升序返回。身份缺失返回 401，任务不存在或资源范围不匹配返回 404，非法分页参数返回 422。

关联依据是同企业、请求 ID、模型别名及 embeddings 能力。当前账本没有独立 job_id 字段，重复请求 ID 时可能匹配其他调用；`correlation=tenant_request_model_capability` 明确表示匹配规则，不保证精确任务归属。不同重试的调用可能汇集；不能据此确认某条调用属于某次尝试。

接口不返回 claim_token、检查点/向量正文、模型配置或 fingerprint。没有调用记录不证明未发生上游费用；pending 可能尚未确认，成功调用不表示最终索引已提交，未知 token 不按零计。详情和调用读取是实时观测，不保证跨 SQL 快照一致。

下一步增加模型调用的显式任务关联，保留历史请求匹配作为兼容回退，明确区分精确关联和旧记录匹配。
