# 目标技术栈与当前实现

沿用 TypeScript + Python、模块化单体 + 独立后台任务进程的目标方案。目录整理不代表技术栈迁移已经完成。

| 部分 | 目标 | 位置 | 当前状态 |
| --- | --- | --- | --- |
| 管理后台、帮助中心 | React + TypeScript + Vite、Ant Design | web/ | 原生 HTML/JS 管理页；React、帮助中心待开发 |
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

下一项业务增量：在 web/ 引入 React 管理后台，先对接现有企业创建、停用、凭据轮换及模型授权接口，再完善个人登录、角色权限和应用版本。知识库、任务及流程按依赖顺序推进。
