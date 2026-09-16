# 调用诊断 JSON 导出

步骤 57（2026-09-16），数据库保持 0017，无新迁移。

任务详情增加“导出调用诊断 JSON”。导出使用当前已生效的 attempt、call_status、call_error，未提交的输入框草稿不参与。始终从第一条开始，不受当前明细页码影响，最多 1000 条。文件名为 `index-call-diagnostics.json`，由浏览器本地下载；关闭详情或更换筛选会取消尚未完成的导出请求。

管理员接口：`GET /api/v1/admin/tenants/{tenant_id}/applications/{app_id}/versions/{version_id}/index-jobs/{job_id}/export`。支持与详情相同的三个筛选参数及校验，不接受自定义导出上限；鉴权与完整资源范围校验沿用详情接口。

文件包含 format_version=1、generated_at（Unix 秒）、resource、filters、export、scope_notes，以及 task/calls/summary/correlation。export 明确 limit、returned、truncated、starts_at=0。超过上限时 JSON 与页面均显示截断，须缩小筛选范围；空结果可导出，returned=0。summary 始终为全任务精确调用汇总，与筛选明细范围不同。

保留原始 null、精确关联/请求匹配标记和尝试/批次位置。只复用详情接口允许的诊断字段，不包含手册正文、提示词、模型配置、指纹、凭据或租约令牌。JSON 不做 CSV/表格公式处理，不生成表格文件。该操作不重试任务、不调用模型。

导出是实时观测，不保证明细与多个统计查询的跨 SQL 快照一致；truncated 也仅反映本次读取。调用成功不代表业务成功，未知用量不按零估算费用。下载完成提示表示浏览器已触发下载，磁盘保存由浏览器管理。

下一步增加导出操作审计，记录操作者、任务范围、筛选条件和截断情况，便于企业追踪诊断数据导出。
