# 混合检索与引用问答

管理入口：`/admin/tenants` → 应用与版本 → 管理知识库 → 向量索引与检索。先发布版本与手册，再选择本企业已授权的 embedding 模型，确认建立索引。面板显示本地/云端、索引缺失/可用/失效、分片数和维度；发布资料变化后需重建。聊天模型单独选择，支持网关已有的 Ollama 和 OpenAI 兼容服务。

## 对外接口

企业身份接口前缀为 `/api/v1/applications/{app_id}/versions/{version_id}`；管理员预览前缀为 `/api/v1/admin/tenants/{tenant_id}/applications/{app_id}/versions/{version_id}`。都使用 Bearer 认证，并执行相同的发布范围过滤。

| POST 路径 | JSON 请求 | 返回 |
| --- | --- | --- |
| `/hybrid-search` | `{"model":"embed-local","query":"如何重置密码","limit":5}` | `data` 原文来源列表、`method: hybrid_rrf` |
| `/answers` | `{"model":"embed-local","chat_model":"chat-local","query":"如何重置密码","limit":5}` | `answer`、`citations`、`status` |

`model` 必须拥有 embedding 能力，`chat_model` 必须拥有 chat 能力，且均已向当前企业授权。模型别名通过既有模型管理接口配置；索引操作见 [向量检索](VECTOR_SEARCH.md)。数据库版本保持 0005，无新迁移。

关键词和向量各取前 20 项，使用等权倒数排名融合（RRF，常数 60），按文档和分片去重，返回 1–20 项。无索引或索引失效返回 409，不自动降级为关键词结果。问题最多 200 字符，仍受 128 分片索引容量约束。分数仅用于排序，不是相关概率。

问答将检索原文和问题发送到选定聊天模型，固定本次模型配置；无需工具调用，也不执行应用操作。模型需返回 JSON 和 `[1]` 格式引用。服务端校验编号属于本次检索来源且与正文标记一致，再返回对应文件、原文、页码/段落及字符范围。无引用统一返回 `insufficient_evidence`；格式或引用无效返回 `502/invalid_answer_citations`，不展示未经校验的模型输出。上下文过大返回 `409/answer_context_too_large`，应减少 limit。

模型调用前后复查发布内容及授权；生成期间撤回资料或撤销模型授权会阻止回答返回。问题会发送到 embedding 模型，问题和检索原文会发送到聊天模型；云端服务可能收费。关闭页面只取消浏览器请求，不保证停止服务端调用。

## 当前边界与下一步

这是单轮、有界检索问答。编号校验只能确认来源存在，不能证明回答受到原文支持，也不能保证抵御所有提示注入。前端按纯文本显示回答与原文。没有会话记忆、流式输出、自动重试修复 JSON、语义事实验证或相关性拒答阈值。

下一步先用真实模型和企业手册建立检索/引用评测集，验证无答案问题、错误引用与文档内恶意指令；随后接入索引后台任务、配额和 pgvector，再推进帮助中心与嵌入式助手。

代码入口：`api/src/agent_nexus/knowledge/answers.py` 实现融合和问答，`vector_router.py` 提供路由；`web/src/app/features/knowledge/VectorPanel.tsx` 管理模型与索引，`AnswerPanel.tsx` 展示引用问答。
