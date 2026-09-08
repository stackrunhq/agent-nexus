# 统一模型接入约定

业务请求 → 认证 → 别名解析 → 启用/能力/目标主机校验 → 凭据解析 → 协议转换 → 上游调用 → 结果归一化。

业务模块不接触密钥、不拼接供应商 URL、不自行跨云降级。目前 Gateway 含两种协议分支；增加第三种原生协议时拆为独立 Adapter，维持相同契约。

## 能力

| 能力 | 状态 |
| --- | --- |
| 同步文本对话 | 已实现 |
| 批量向量 | 已实现，核验数量/维度/有限数值，按 index 恢复顺序 |
| 流式 | 阶段 04，使用真实上游流，不伪装流式 |
| 工具调用 | 阶段 05，归一化参数和调用 ID，由执行层鉴权 |
| 多模态、JSON Schema、重排 | 后续独立适配与评测 |

capabilities 为管理员声明，须真实联调验证。cloud/local 是部署分类，不替代网络隔离。上游未返回用量时为 null，不能伪造为 0。finish_reason 暂保留供应商值。

## 接口

| 方法与路径 | 授权 | 用途 |
| --- | --- | --- |
| GET /health/live | 无 | 进程存活 |
| GET /health/ready | 无 | 数据库可访问，不代表模型可用 |
| GET /api/v1/admin/models | 管理员 | 配置列表，不含密钥 |
| GET /api/v1/admin/settings | 管理员 | 查看部署允许的模型主机 |
| GET /api/v1/admin/audit-events | 管理员 | 配置变更审计，按 alias 筛选，before 游标分页 |
| PUT /api/v1/admin/models/{alias} | 管理员 | 创建、更新、禁用 |
| POST /api/v1/admin/models/{alias}/test | 管理员 | 真实对话或向量测试，返回耗时与归一化结果 |
| GET /api/v1/models | 调用端 | 启用模型别名及能力 |
| POST /api/v1/chat/completions | 调用端 | 文本对话 |
| POST /api/v1/embeddings | 调用端 | 向量 |

Schema 见 `/docs` 和 `/openapi.json`。授权使用 `Authorization: Bearer <token>`。

错误格式：`{"error":{"code":"...","message":"..."},"request_id":"..."}`。参数错误附字段路径，不回显输入。所有响应包含 X-Request-ID。

401 令牌错误；403 端点未允许；404 模型不存在/禁用；422 参数或能力不符；429 上游限流；502 上游连接/响应错误；503 未配置凭据；504 超时。

## 0.2 管理工作台与参数适配

访问 `/admin` 打开配置工作台。静态页面公开可读取，所有配置和测试请求均要求管理员令牌。前端无第三方脚本，不持久化令牌，使用纯文本渲染模型名称与回答；断开连接会清空页面状态并中止尚未完成的浏览器请求（不保证供应商停止生成或计费）。

管理试调用示例：

```http
POST /api/v1/admin/models/local-help/test
Authorization: Bearer <admin-token>
Content-Type: application/json

{"capability":"chat","input":"请回复一句你好"}
```

`capability` 为 chat 或 embeddings，input 最多 4000 字符且不能全空白。测试直接复用网关，不绕过禁用、端点、凭据及能力校验，不自动重试。成功返回 request_id、model、capability、elapsed_ms 及 result；耗时是网关总耗时，不是纯推理耗时。仅验证选定能力，不宣称模型全能力健康。

兼容协议新增配置：

- `token_parameter`：max_tokens（默认）或 max_completion_tokens；业务请求始终用 max_tokens，由网关映射。Ollama 始终使用 options.num_predict，不允许选择非默认兼容参数。
- `supports_temperature`：默认 true；关闭后，带 temperature 的请求返回 422 unsupported_parameter，未传该参数正常调用。
- 旧数据库配置缺少上述字段时自动补默认值。

总时限覆盖接收完整响应；超过 timeout_seconds 返回 504。读取上游时累计限制解码后的响应为 8 MiB，超限返回 502 provider_response_too_large。畸形嵌套字段返回 502，不透传上游正文。

## 安全边界

模型配置保存与审计写入同一事务，审计失败则更新回滚。审计只记录变更字段名，不保存字段值、密钥或提示词。相同配置重复保存不产生事件，既有配置不补造历史。操作者目前为共享管理员类别 platform_admin（内部调用为 system），后续接入用户体系后替换为可信用户 ID。

日志接口可传 `alias`、`limit`（1–100，默认 50）、`before`（上一页 next_before）。返回 `data` 和 `next_before`，按事件 ID 降序；游标为空表示结束。当前不提供日志修改/删除 API，但此日志不是防篡改合规存储。

- 无默认有效凭据，管理员与调用令牌必须不同且长度足够。
- api_key_env 仅允许 NEXUS_PROVIDER_ 前缀，不能引用任意系统变量。
- 云端 HTTPS，禁止 URL 内嵌凭据、query 或 fragment。
- 主机允许列表、禁止重定向、不使用隐式环境代理；生产配合网络出口规则。
- 不返回原始上游错误，不记录提示词及凭据。
- 目前限制业务输入长度、总调用时限和上游响应大小；生产补充请求体上限、并发控制与企业配额。
- 后续在 resolve 阶段加入企业模型授权；当前不是多租户服务。

## 协议依据

- [Ollama Chat](https://docs.ollama.com/api/chat)：/api/chat，显式关闭流式。
- [Ollama Embed](https://docs.ollama.com/api/embed)：/api/embed，禁止静默截断。
- [vLLM 兼容服务](https://docs.vllm.ai/en/latest/serving/openai_compatible_server/)：实际能力取决于部署模型。
