# 顶层目录与代码导航

采用模块化单体：顶层按交付职责分区，后端内部按业务功能组织。目前一个 Python 安装包包含 API、CLI 和页面资源，原生与 Docker 使用相同构建产物。

```text
agent-nexus/
├── api/                         # 后端 API
│   ├── src/agent_nexus/
│   │   ├── app.py               # 生命周期、模块组装和路由注册
│   │   ├── core/                # 配置、公共错误、请求基类
│   │   ├── api/                 # HTTP 认证、异常响应、健康检查
│   │   ├── models/              # 模型配置、调用、协议适配
│   │   ├── applications/        # 企业应用、版本生命周期与读取权限
│   │   ├── knowledge/           # 文档 HTTP、持久化队列、解析进程与来源分片
│   │   ├── identity/            # 个人账号、会话、角色与身份接口
│   │   ├── tenants/             # 企业凭据、授权、事件
│   │   ├── storage/             # 连接、表结构、事务、migrations/
│   │   ├── web/routes.py        # 挂载前端资源，仅负责 HTTP
│   │   └── db_cli.py            # 兼容原数据库命令
│   └── tests/                   # models / tenants / storage 回归
├── web/                         # React 企业前端与原模型页面
│   ├── src/app/features/tenants/ # React 企业管理功能与类型
│   ├── src/app/shared/          # 请求客户端与测试
│   └── src/agent_nexus_web/static/ # 原模型页面及生成的企业页资源
├── cli/                         # 运维命令
│   └── src/agent_nexus_cli/database.py # 升级、导入、检查
├── docker/                      # Dockerfile、compose.yaml 及 PostgreSQL 覆盖
├── image/                       # 项目图片与来源说明
├── docs/                        # 文档索引 README.md、架构 architecture/
├── examples/                    # 无真实凭据的模型配置样例
├── .github/workflows/           # CI
├── pyproject.toml               # 三个源码目录的打包、命令、检查配置
├── requirements.lock            # Python 依赖锁
├── .env.example                 # 环境变量模板
└── .dockerignore                # 根构建上下文排除规则
```

## 阅读顺序和修改入口

先看根 README 的运行方式，再看 api/src/agent_nexus/app.py 的模块装配，然后进入业务 router → schemas → gateway/store，最后看 api/tests 下同名业务测试。

| 修改内容 | 文件位置 |
| --- | --- |
| 模型供应商、超时、统一返回 | api/src/agent_nexus/models/gateway.py |
| 模型配置、审计、试调用 | api/src/agent_nexus/models/admin_router.py、store.py |
| 对外聊天与向量接口 | api/src/agent_nexus/models/client_router.py |
| 企业创建、停用、轮换和授权 | api/src/agent_nexus/tenants/router.py、store.py |
| 请求与响应字段 | 对应业务目录 schemas.py |
| 身份和模型权限 | api/src/agent_nexus/api/auth.py |
| 数据库表、连接、事务 | api/src/agent_nexus/storage/database.py |
| 数据库版本升级 | api/src/agent_nexus/storage/migrations/versions/ |
| 运维命令 | cli/src/agent_nexus_cli/database.py |
| 个人身份与账号页面 | api/src/agent_nexus/identity/、web/src/app/features/users/ |
| 应用及版本 | api/src/agent_nexus/applications/、web/src/app/features/applications/ |
| 文档解析与来源分片 | api/src/agent_nexus/knowledge/parsing.py、chunking.py |
| 文档 JSON 预览命令 | cli/src/agent_nexus_cli/document.py |
| 企业页面 | web/src/app/features/tenants/、src/app/style.css |
| 原模型页面 | web/src/agent_nexus_web/static/ |
| 容器编排与镜像构建 | docker/ |

调用链：模型路由 → 身份与授权 → 模型网关 → 存储/上游协议 → 统一响应。CLI 复用 API 的存储和迁移，不维护第二份表结构。API 业务不依赖 CLI，db_cli.py 仅兼容命令转发。web 资源通过包资源接口挂载，不依赖工作目录向上查找。

## 迁移说明

- src/agent_nexus 移至 api/src/agent_nexus，tests 移至 api/tests。
- 页面资源移至 web/src/agent_nexus_web/static。
- 原 agent_nexus.storage.cli 函数移至 agent_nexus_cli.database；外部脚本导入应调整。
- uvicorn agent_nexus.app:create_app --factory 与 python -m agent_nexus.db_cli 保留；增加 nexus-db 命令。
- 现有环境重新执行 `python -m pip install -e '.[dev]'` 更新源码映射。
- Compose 已移至 docker/，从仓库根使用 `docker compose --project-directory . -f docker/compose.yaml ...`。保持根 .env、构建上下文和项目名称推导一致；原先指定过 -p 的继续用同一名称以复用数据卷。

新增业务在 API 中建立同名功能包和测试；服务复杂后再拆 service，不把逻辑堆入 app.py。未来 Worker、SDK 有实际实现时分别创建顶层 worker/、sdk/。当前未实现的技术见 [技术栈与状态](TECH_STACK.md)。

虚拟环境、.tools、build、dist、缓存与 *.egg-info 是本地生成物，data 是运行数据，均不提交。旧 src 可能只剩忽略的 egg-info，不是业务代码，不手工修改。构建前清理已核对的仓库 build 生成目录，避免旧模块进入安装包。

知识库调用链：knowledge/router.py → store.py（归属校验、文档/分片和队列）→ storage/knowledge_schema.py。独立 cli/src/agent_nexus_cli/worker.py → knowledge/jobs.py（领取与超时）→ process.py（子进程资源限制）→ parsing.py/chunking.py。0004_knowledge.py 冻结迁移；api/tests/knowledge/ 对应测试。

知识库前端：web/src/app/features/knowledge/KnowledgePanel.tsx 负责上传、状态、来源预览和发布确认，types.ts 管理协议类型；ApplicationsPanel.tsx 传入企业/应用/版本路径并按版本重新挂载，shared/client.ts 统一二进制上传及请求取消。

关键词检索：api/src/agent_nexus/knowledge/search.py（可读分片查询、词项和 BM25 排序）、search_router.py（企业与管理员预览）；web/src/app/features/knowledge/SearchPanel.tsx（检索与来源原文）。当前无向量索引表，不在模型网关中混入检索逻辑。

向量检索：api/src/agent_nexus/knowledge/vectors.py 保存配置指纹、文档摘要与归一化向量，vector_router.py 提供构建/状态/检索 API；storage/vector_schema.py 与 0005_vectors.py 为快照表。模型协议仍由 models/gateway.py 统一。

### 混合检索与引用问答

- `storage/vector_metadata_schema.py` / `0010_vector_metadata.py`：轻量索引元数据与回填迁移；`knowledge/vectors.py:load_metadata` 避免状态查询加载向量 JSON。

- `cli/src/agent_nexus_cli/vector_benchmark.py`：可重复原生缓存基准；`evaluation/results/` 保存本轮合成数据实测结果。

- `knowledge/pgvector_backend.py`：原生派生缓存写入与余弦排序；`cli/src/agent_nexus_cli/pgvector.py`：显式扩展/缓存初始化。

- `models/usage.py` 中 ModelQuotaPolicy/get_policy/put_policy：企业模型准入覆盖值；`storage/model_quota_schema.py` 和 0009 迁移定义持久表。
- `web/src/app/features/knowledge/ModelQuotaPanel.tsx`：模型限额读取与确认保存。

- `api/src/agent_nexus/models/usage.py`：调用前登记、结果入账及租户分页查询；`models/gateway.py` 统一计量入口。
- `storage/model_usage_schema.py` / `0008_model_usage.py`：调用账本表与冻结迁移。
- `web/src/app/features/knowledge/ModelCallsPanel.tsx`：调用状态、token、耗时和分页展示。

- `api/src/agent_nexus/tenants/quotas.py`：企业覆盖限额、默认继承、修改审计；`storage/quota_schema.py` 与 0007 迁移定义表。
- `web/src/app/features/knowledge/QuotaPanel.tsx`：企业限额读取、确认修改和恢复继承。

- `api/src/agent_nexus/knowledge/index_jobs.py`：索引入队、容量、租约领取和写入隔离。
- `api/src/agent_nexus/storage/index_job_schema.py` / `0006_index_jobs.py`：持久任务表与迁移。
- `cli/src/agent_nexus_cli/worker.py --queue indexes`：独立索引 Worker。

- `api/src/agent_nexus/knowledge/answers.py`：RRF 融合、模型授权、单轮生成、引用校验和发布状态复查。
- `api/src/agent_nexus/knowledge/vector_router.py`：向量、混合检索、引用问答的企业与管理员接口。
- `web/src/app/features/knowledge/VectorPanel.tsx`：企业模型选择、索引状态和建立确认。
- `web/src/app/features/knowledge/AnswerPanel.tsx`：聊天模型选择、问题提交和原文引用展示。

索引配额：knowledge/index_jobs.py 在任务登记事务内检查企业日用量与活跃数；vector_router.py 提供 index-usage 并将同步构建接入同一登记逻辑。
# 步骤 32 导航

- `api/src/agent_nexus/knowledge/vectors.py`：流式内容指纹、批次间内容和授权校验、最终索引原子保存。
- `api/tests/knowledge/test_vector_batches.py`：多批次成功、批次间失效及旧索引保留回归。
