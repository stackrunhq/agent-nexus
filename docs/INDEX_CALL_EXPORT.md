# 调用诊断 JSON 导出

步骤 57（2026-09-16），数据库保持 0017，无新迁移。

任务详情增加“导出调用诊断 JSON”。导出使用当前已生效的 attempt、call_status、call_error，未提交的输入框草稿不参与。始终从第一条开始，不受当前明细页码影响，最多 1000 条。文件名为 `index-call-diagnostics.json`，由浏览器本地下载；关闭详情或更换筛选会取消尚未完成的导出请求。

管理员接口：`GET /api/v1/admin/tenants/{tenant_id}/applications/{app_id}/versions/{version_id}/index-jobs/{job_id}/export`。支持与详情相同的三个筛选参数及校验，不接受自定义导出上限；鉴权与完整资源范围校验沿用详情接口。

文件包含 format_version=1、generated_at（Unix 秒）、resource、filters、export、scope_notes，以及 task/calls/summary/correlation。export 明确 limit、returned、truncated、starts_at=0。超过上限时 JSON 与页面均显示截断，须缩小筛选范围；空结果可导出，returned=0。summary 始终为全任务精确调用汇总，与筛选明细范围不同。

保留原始 null、精确关联/请求匹配标记和尝试/批次位置。只复用详情接口允许的诊断字段，不包含手册正文、提示词、模型配置、指纹、凭据或租约令牌。JSON 不做 CSV/表格公式处理，不生成表格文件。该操作不重试任务、不调用模型。

导出是实时观测，不保证明细与多个统计查询的跨 SQL 快照一致；truncated 也仅反映本次读取。调用成功不代表业务成功，未知用量不按零估算费用。下载完成提示表示浏览器已触发下载，磁盘保存由浏览器管理。

步骤 58（2026-09-16）已增加导出审计，复用 application_events，无数据库迁移。服务端生成导出后、返回响应前提交事件；审计写入失败则请求失败，不静默返回未审计的数据。

查询入口：`GET /api/v1/admin/tenants/{tenant_id}/applications/{app_id}/events`，需要管理员权限，并校验应用所属企业；沿用最近 100 条事件限制。筛选 action 以 `index_calls_exported:` 开头的记录，冒号后为 JSON：format_version=1、resource（企业/应用/版本/任务）、filters（保留 null 和空字符串）、export（上限/返回数/截断/起始位置）和 outcome=generated。外层记录 actor、request_id、created_at、version_id。这里的 request_id 是本次导出请求 ID，而非索引任务原始请求 ID。

actor 来自已验证身份：共享管理员密钥对应 platform_admin，用户认证对应用户 ID，不能把共享密钥使用者区分为具体个人。审计不保存调用明细、手册或凭据。非法参数、未授权、资源不存在的请求不会产生成功导出事件；每次成功生成（含空结果和重复请求）分别记录。事件仅证明服务端生成，不证明网络交付或磁盘保存，取消请求也不保证服务器尚未生成事件。该表不提供防篡改保证。

步骤 59（2026-09-16）提供结构化查询：`GET /api/v1/admin/tenants/{tenant_id}/applications/{app_id}/versions/{version_id}/index-export-events`。管理员鉴权，完整验证企业/应用/版本归属。参数 limit 默认 20、范围 1–100；before 为正整数事件 ID，查询更早记录。结果 data 按事件 ID 倒序，next_cursor=null 表示没有下一页。该查询不受通用应用事件接口最近 100 条限制。

每项包含 id、actor、request_id、created_at、readable。可解析记录另含 format_version、outcome、resource、filters、export，均按白名单返回；损坏、不支持的格式或资源不匹配仅返回事件基础字段及 readable=false，不暴露原始 action。坏记录也计入分页，保证游标可以继续前进。查询是实时读取，不保证跨页快照一致；数据库仍为 0017。

索引任务详情新增“查看版本导出审计”，按需加载当前版本全部导出记录，展示生成者、时间、请求、任务、条件及截断结果。使用“更早的导出记录”翻页，“刷新导出审计”回到最新页；关闭或离开时取消查询。调用筛选不影响审计范围，导出后需手动刷新。

下一步增加审计按任务和操作者筛选，并评估结构化存储及索引，避免在大量历史事件中扫描。
