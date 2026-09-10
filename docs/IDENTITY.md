# 个人账号、会话与角色

当前支持平台管理员和企业成员两个角色，账号创建、启停和密码重置只能由平台管理员执行，没有公开注册接口。

## 首次使用

1. 备份数据库、停止写入，执行 `python -m agent_nexus.db_cli upgrade` 升级到 **0005**，再启动 API。已登记 0001/0002/0003/0004 的 SQLite 和 PostgreSQL 都必须显式升级；无版本的开发 SQLite 仍可自动建表。
2. 原生部署先执行 `npm --prefix web ci`、`npm --prefix web run build`；Docker 构建自动包含前端。
3. 打开 `/admin/tenants`，先用环境变量中配置的管理员令牌连接，在“个人账号与角色”中创建第一个平台管理员。
4. 断开连接，切换“个人账号登录”，输入刚创建的用户名和密码。可创建企业成员、绑定企业，并为该企业授权模型。

用户名为 3–64 位小写字母、数字、下划线、点或连字符，首位为字母或数字；密码 15–256 字符。平台管理员不能绑定企业，企业成员必须绑定一个已启用企业；角色和所属企业暂不支持修改。账号停用、启用和密码重置均撤销原会话。

## 权限边界

| 身份 | 后台管理接口 | 对外模型接口 |
| --- | --- | --- |
| 环境管理员令牌 | 所有平台管理操作 | 不作为模型调用身份 |
| platform_admin 个人会话 | 所有平台管理操作 | 拒绝，需使用企业身份 |
| tenant_user 个人会话 | 拒绝，包括企业、模型及账号管理 | 只允许所属企业已授权且启用的模型 |
| 企业机器凭据 | 拒绝 | tenant 模式下按照企业授权调用 |

个人企业成员会话始终应用企业授权，即使服务处于 bootstrap 模式也不能绕过。所属企业停用期间，个人认证和模型调用被拒绝。当前不是完整组织 RBAC：没有企业内管理员、自定义角色、文档级 ACL 或 RLS。

## API

除登录外，个人身份接口使用 `Authorization: Bearer <个人会话>`。管理接口同时接受环境管理员令牌和平台管理员个人会话。

| 方法与路径 | 用途 |
| --- | --- |
| POST /api/v1/auth/login | username、password 换取个人会话 |
| GET /api/v1/auth/me | 当前个人身份与所属企业 |
| POST /api/v1/auth/logout | 撤销当前会话，成功返回 204 |
| POST /api/v1/admin/users | 创建账号：username、password、role、tenant_id |
| GET /api/v1/admin/users | 账号列表，不返回密码摘要和会话 |
| PATCH /api/v1/admin/users/{id} | enabled 修改状态并撤销会话 |
| POST /api/v1/admin/users/{id}/reset-password | password 重置密码、清除登录锁定并撤销会话 |
| GET /api/v1/admin/user-events | 最近 100 条账号安全事件 |

登录成功返回 access_token、token_type、expires_in 和 user；令牌以 ns_ 开头，TTL 为 1 小时，无自动续期。同一账号新登录会撤销旧会话，刷新页面需重新登录。企业成员暂通过 API 登录并调用模型，当前页面是平台后台，不提供企业成员聊天页面。

## 安全与运维约定

- 密码采用随机盐 scrypt（N=2^17、r=8、p=1），数据库只存哈希；个人会话为随机令牌，数据库只保存 SHA-256 摘要和到期时间。
- 账号连续 5 次失败后暂停登录 5 分钟；错误统一返回 401，不回显密码。失败计数和会话写入持久化；未知账号执行同等密码计算。
- 登录、创建和重置密码使用共享身份事务锁，限制并行密码计算。每次 scrypt 约需 128 MiB 内存；这是低并发管理登录基础，部署应分配足够内存，并由网关增加登录入口请求限流。尚无 MFA、SSO、找回邮件或独立 IP 限流。
- 前端仅在内存中保存会话，退出立即清除本地状态并请求服务端撤销；到期或收到个人会话 401 后返回登录界面。网络失败时显示服务端撤销未确认，此时仍可通过停用账号或等待到期终止会话。关闭浏览器不会保证向服务器发送退出请求。
- 账号创建、状态、重置、登录、失败及退出写入 user_events；模型配置修改写入个人 ID。原企业凭据/授权事件暂未增加个人操作人字段，不应把所有现有日志视为完整个人审计。
- 启动仍要求环境管理员令牌，它是初始创建和恢复入口，没有默认账号或默认密码。限制该令牌的持有人，并在受控 HTTPS 环境部署。
- 导入和备份恢复会保留个人账号、密码摘要和尚未到期的会话；恢复环境隔离使用，正式切换若要求重新登录，应在维护窗口撤销会话。当前没有自助改密、邀请激活与会话列表。

实现位置：`api/src/agent_nexus/identity/`、`api/src/agent_nexus/storage/identity_schema.py`、`web/src/app/features/users/`。迁移文件 `0002_identity.py` 固定历史表结构，不引用运行时模型定义。

依据：[OWASP 密码存储](https://cheatsheetseries.owasp.org/cheatsheets/Password_Storage_Cheat_Sheet.html)、[OWASP 身份认证](https://cheatsheetseries.owasp.org/cheatsheets/Authentication_Cheat_Sheet.html)。
