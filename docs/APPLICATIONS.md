# 企业应用与产品版本

本轮建立知识库的归属基础：**企业 → 应用 → 产品版本**。产品版本发布只改变版本信息的可见性，不代表手册已解析或知识库已发布。

## 使用与升级

先备份数据库、暂停旧服务写入，执行 `python -m agent_nexus.db_cli upgrade` 升级到 **0003**。已登记 0001/0002 的库必须显式升级；无版本 SQLite 开发库仍可自动建表。原生部署先构建前端，Docker 构建自动包含页面。

进入 `/admin/tenants`，用平台管理员身份连接，在“应用与版本”中选择企业：

1. 创建应用：填写企业内唯一的小写标识、名称、说明。不同企业可以使用相同标识。
2. 点击“管理版本”，填写版本号与说明，创建草稿。
3. 确认发布：应用和企业必须启用，版本从 draft 变为 published。
4. 版本停用时确认退役：published 变为 retired，不允许退役后重新发布。

版本号是应用内唯一标签，不强制 SemVer；列表按标签排序，不推断“最新版本”。同一应用可有多个已发布版本。企业、应用归属和版本标签不可改绑，当前不提供删除、名称/说明编辑或默认版本切换；需要更正时创建新版本。草稿可在应用停用期间准备，但不能发布。

## 接口与权限

平台管理路径前缀：`/api/v1/admin/tenants/{tenant_id}/applications`。

| 方法与相对路径 | 用途 |
| --- | --- |
| GET / POST 前缀本身 | 列表 / 创建应用（slug、name、description） |
| PATCH /{app_id} | 设置 enabled |
| GET / POST /{app_id}/versions | 列表 / 新建草稿（version、notes） |
| PATCH /{app_id}/versions/{version_id} | status=published 或 retired |
| GET /{app_id}/events | 最近 100 条操作记录 |

企业读取接口：`GET /api/v1/applications`、`GET /api/v1/applications/{app_id}/versions`。个人企业成员会话或 tenant 模式下的机器凭据可读取；企业身份由认证上下文决定，不能通过请求参数指定其他企业。全局 bootstrap 客户端令牌没有企业归属，返回 403。

平台管理员才能写入。跨企业的应用路径或不属于该应用的版本返回 404；应用停用后企业读取不到该应用及版本。企业端版本列表只返回 published，隐藏草稿和退役版本。当前为企业内统一可见，尚无企业内按用户授予应用权限。

## 状态、一致性与存储

生命周期为 `draft → published → retired`。重复提交当前状态不重复记录事件；逆向流转或跳过发布返回 409。重复应用标识或版本标签返回 409。应用和版本操作使用事务与应用锁，事件同时提交，记录 actor、request_id、版本 ID 与时间。

0003 新增 applications、application_versions、application_events，业务表总数为 11；唯一约束及外键保证归属基础。导入按外键排序，恢复后校正应用事件序列，数据库受限运行角色需要增加三表权限。数据回退使用经过验证的备份，不执行删除历史表的降级。

代码：`api/src/agent_nexus/applications/`（接口、结构、存储），`storage/application_schema.py`（表定义），`web/src/app/features/applications/`（页面及交互测试）。

## 下一步知识库

当前已提供 PDF/DOCX/Markdown/TXT 离线解析与来源分片，见 [知识库解析](KNOWLEDGE.md)。文件上传、原文件/分片持久化、独立 Worker 与处理状态已按企业/应用/版本绑定。只有 draft 产品版本允许新上传，文档需 ready 且产品版本 published 后才能单独发布。知识库管理页面已接入，OCR 和检索待开发。产品版本发布和知识库内容发布需各自管理状态，不能混为一次操作。
