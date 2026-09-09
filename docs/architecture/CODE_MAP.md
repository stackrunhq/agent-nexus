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
