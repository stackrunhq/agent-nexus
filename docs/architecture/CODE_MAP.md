# 代码阅读与目录导航

第一次阅读：先看根目录 README 了解启动方法，再看 `src/agent_nexus/app.py` 的组装过程，然后按业务进入对应目录。当前采用按业务划分的 Python 单体服务，管理页面随服务一起打包。

## 目录职责

```text
agent-nexus/
├── src/agent_nexus/
│   ├── app.py                 # 应用工厂：生命周期、依赖组装、注册路由
│   ├── db_cli.py              # 稳定的数据库命令入口
│   ├── core/                  # 配置、公共错误、严格请求模型基类
│   ├── api/                   # HTTP 公共处理：认证、错误响应、健康检查
│   ├── models/                # 模型业务
│   │   ├── admin_router.py    # 模型配置、审计、试调用管理接口
│   │   ├── client_router.py   # 对外模型列表、对话、向量接口
│   │   ├── schemas.py         # 模型配置与调用请求/响应结构
│   │   ├── gateway.py         # 云端兼容协议和 Ollama 协议适配
│   │   └── store.py           # 模型配置、ETag、审计存储
│   ├── tenants/               # 企业机器凭据与模型授权
│   │   ├── router.py          # 企业管理接口
│   │   ├── schemas.py         # 企业请求结构
│   │   └── store.py           # 凭据摘要、授权、事件存储
│   ├── storage/               # 数据库连接、表结构、事务和运维工具
│   │   ├── database.py
│   │   ├── cli.py             # upgrade / import-sqlite / check 实现
│   │   └── migrations/        # Alembic 环境与不可随意改写的历史版本
│   └── web/                   # 内置管理页面
│       ├── routes.py          # 页面与资源挂载
│       └── static/            # HTML、CSS、JavaScript
├── tests/                     # 与业务目录对应
│   ├── models/                # 模型协议、配置、审计、鉴权接口回归
│   ├── tenants/               # 企业凭据、授权与越权回归
│   └── storage/               # SQLite、PostgreSQL、备份恢复
├── docs/                      # 文档索引见 docs/README.md
├── examples/                  # 不含真实密钥的模型配置示例
├── .github/workflows/         # CI 检查与构建
├── compose.yaml               # 默认 SQLite 部署入口
├── compose.postgres.yaml      # PostgreSQL 部署入口
├── Dockerfile                 # 镜像构建入口
├── pyproject.toml             # Python 包、依赖范围、检查配置
└── requirements.lock          # 锁定的依赖及校验值
```

根目录保留部署和构建入口，方便直接运行现有命令。`.venv-standard/`、`.tools/`、`build/`、`dist/`、`*.egg-info/` 和缓存为本地环境或生成物；`data/` 是运行数据。这些目录不属于业务源码，不提交 Git，也不应手工修改生成的 dependency_links.txt。

## 修改某项功能去哪里找

| 任务 | 入口 | 对应验证 |
| --- | --- | --- |
| 新增模型供应商协议 | models/gateway.py、schemas.py | tests/models/test_gateway.py |
| 修改模型管理或试调用 | models/admin_router.py、store.py | tests/models/test_gateway.py |
| 修改调用权限 | api/auth.py、tenants/store.py | tests/tenants/test_tenants.py |
| 企业创建、轮换、停用和授权 | tenants/router.py、schemas.py、store.py | tests/tenants/test_tenants.py |
| 环境变量与启动校验 | core/settings.py、app.py、根目录 .env.example | 模型及企业接口测试 |
| 错误格式与请求 ID | core/errors.py、api/errors.py | tests/models/test_gateway.py |
| 数据库表与升级 | storage/database.py、migrations/versions/ | tests/storage/ |
| 管理页面交互和样式 | web/static/ | JS 语法检查、页面资源及 API 回归 |

## 请求如何流转

对话请求：`app.py` 注册 `models/client_router.py` → `api/auth.py` 识别身份与检查授权 → `models/gateway.py` 读取模型配置并适配上游协议 → 返回统一响应。数据库读取通过业务 `store.py` 使用 `storage/database.py`；异常在 `api/errors.py` 统一转换。

新增业务按职责放入独立包，其请求结构、接口、业务逻辑和存储就近组织，测试使用同名业务目录。`core` 不导入业务模块；业务存储不导入 HTTP 路由；应用工厂负责把公共依赖注入路由。不要把新功能继续堆进 app.py，也不要提前创建尚无实现的空业务目录。

## 兼容性与边界

HTTP 路径、环境变量、数据库表和版本号保持原约定。现有 `uvicorn agent_nexus.app:create_app --factory` 与 `python -m agent_nexus.db_cli ...` 命令继续使用。

内部 Python 导入已迁移：原 gateway/schemas/store 位于 models，tenant_store 位于 tenants/store，database 位于 storage/database，数据库函数位于 storage/cli。仓库内调用已经更新；若外部脚本直接导入旧内部模块，需要按此映射修改。

本次只重构组织方式。tenants 目前代表企业机器接入，尚无个人用户登录与角色权限；企业管理页面、个人身份及应用版本仍按 STATUS 中的顺序开发。
