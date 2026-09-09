# 目标技术栈与当前实现

沿用 TypeScript + Python、模块化单体 + 独立后台任务进程的目标方案。目录整理不代表技术栈迁移已经完成。

| 部分 | 目标 | 位置 | 当前状态 |
| --- | --- | --- | --- |
| 管理后台、帮助中心 | React + TypeScript + Vite、Ant Design | web/ | React 企业管理页已实现；模型页保留原生，帮助中心待开发 |
| 嵌入式助手 | TypeScript SDK + iframe | 未来 sdk/ | 待开发 |
| 后端 API | FastAPI + Pydantic | api/ | 模型、企业接入基础已实现 |
| 数据访问 | SQLAlchemy + Alembic | API storage/ | 已实现 |
| 数据库 | PostgreSQL + pgvector | api/、docker/ | PostgreSQL 已验证，向量检索待开发 |
| 缓存与后台任务 | Redis + Celery | 未来 worker/、docker/ | 待开发 |
| 文件存储 | S3 兼容存储 | 未来知识库模块 | 待开发，私有文件不放 image/ |
| 模型接入 | 自有网关，可选 LiteLLM | API models/ | 兼容协议与 Ollama 已实现，未引入 LiteLLM |
| 流程执行 | 持久化状态机 + Worker | 未来流程模块 | 待开发 |
| 部署 | Docker Compose，后续 Kubernetes | docker/ | Compose 配置已有，Docker 实际启动待验证 |
| 监控 | 结构化日志 + OpenTelemetry | API 公共设施 | 当前请求 ID 和错误日志，完整追踪待开发 |
| 运维 | Python CLI | cli/ | 升级、导入、检查 |

React 企业管理及现有企业接口对接已完成；个人登录、会话和两角色已实现；应用版本基础及知识库离线解析与来源分片已完成；下一项推进文档上传、持久化和隔离后台处理，更细权限继续按需扩展，并逐步迁移模型页面。知识库、任务及流程按依赖顺序推进。
