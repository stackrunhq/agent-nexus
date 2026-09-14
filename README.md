# Agent Nexus

后台索引已支持持久任务、独立 Worker 和批次中断恢复；升级须迁移至 **0011**。见 [检查点与恢复](docs/INDEX_CHECKPOINTS.md)。

面向企业应用的知识库、使用指导与流程规划中台，按阶段实现。

当前版本 **0.3：企业模型接入基础**，提供模型工作台、统一模型 API，以及企业调用凭据和模型授权 API。
这是企业应用中台的开发基础，已具备企业身份和模型/应用/文档读取隔离、知识库入库 API；终端用户帮助中心、检索问答及流程执行仍待开发，不能直接作为多租户 SaaS 上线。

## 从哪里阅读代码

顶层职责：`api/` 后端、`web/` 前端、`cli/` 运维工具、`docker/` 部署、`image/` 项目图片。目标技术栈和当前实现见 [技术架构](docs/architecture/TECH_STACK.md)。目录迁移后已有环境重新执行 `python -m pip install -e '.[dev]'`。

从 [app.py](api/src/agent_nexus/app.py) 查看应用组装，再按业务进入 models、tenants、storage 或 web。完整职责、请求链路和旧路径映射见 [代码导航](docs/architecture/CODE_MAP.md)，所有文档入口见 [文档索引](docs/README.md)。

## 开发顺序

详细范围见 [路线图](docs/ROADMAP.md)，接口约定见 [统一模型接入](docs/MODEL_GATEWAY.md)。

当前已完成及下一步清单见 [STATUS.md](docs/STATUS.md)。企业模式启用和接入流程见 [TENANT_ACCESS.md](docs/TENANT_ACCESS.md)。默认 bootstrap 模式仍为原开发模式，企业授权需要显式设置 `NEXUS_AUTH_MODE=tenant`；企业接入 API 不等于完整文档、会话和用户隔离。

已加入 SQLAlchemy、Alembic 及 PostgreSQL 部署/SQLite 导入工具，详见 [DATABASE.md](docs/DATABASE.md)。保持 NEXUS_DATABASE_URL 为空即可继续使用原 SQLite 文件；PostgreSQL 17.11 实库及备份恢复已通过，详见 [演练记录](docs/BACKUP_RESTORE.md)。

排查数据库连接及结构可执行 `python -m agent_nexus.db_cli check`。就绪接口不扫描模型记录，结构或版本异常返回 503；详细范围见数据库文档。

1. **当前阶段**：工程、模型配置、云端/本地协议适配、鉴权、测试、部署配置。
2. 企业基础：PostgreSQL、迁移、企业/客户组织/用户权限、企业模型授权、React 管理后台。
3. 知识库：文档处理、版本发布、中文混合检索、引用问答。
4. 使用指导：帮助中心、嵌入式助手、会话、流式回答、分步引导。
5. 流程执行：模板、持久化状态机、确认、连接器、幂等、业务回调。
6. 上线：评测、配额、审计、监控、备份恢复、集群部署。

## Docker 启动

需要 Docker Engine 和 Compose。复制 `.env.example` 为 `.env`，填入两个不同的随机令牌（至少 32 字符），并按需要设置允许访问的模型主机和云端密钥。

```sh
docker compose --project-directory . -f docker/compose.yaml up --build -d
```

- API 文档：<http://localhost:8000/docs>，可直接测试管理和调用接口。
- 模型管理工作台：<http://localhost:8000/admin>。
- 企业管理页面：<http://localhost:8000/admin/tenants>，支持创建、启停、轮换凭据、模型授权和事件查看；Docker 自动构建前端。
- 就绪检查：<http://localhost:8000/health/ready>。
- 默认只绑定宿主机回环地址。对外部署通过 HTTPS 网关访问并配置限流。
- 命名卷 `nexus-data` 保存配置，`down -v` 会删除这些数据。
- 容器内 `localhost` 指容器本身；访问宿主机模型使用 `host.docker.internal`。
- 模型服务需要监听容器可访问的地址，结合防火墙限制来源。
- Compose 不安装或下载本地模型。先在独立 Ollama/vLLM 服务准备模型，模型名必须与实际服务一致。

## 企业应用与版本

`/admin/tenants` 已支持按企业创建应用、版本草稿、发布/退役和操作记录。另已提供 TXT/Markdown、文本型 PDF、DOCX 离线解析与来源分片 CLI，见 [知识库解析与预览](docs/KNOWLEDGE.md)。文档上传、持久化、独立 Worker 和发布读取 API 已接入，可从每个版本的“管理知识库”进入上传、分片预览、重试及发布/撤回页面；产品版本行为见 [应用版本说明](docs/APPLICATIONS.md)。

## 个人登录与账号管理

先备份并执行 `python -m agent_nexus.db_cli upgrade` 升级到 **0005**。在 `/admin/tenants` 用环境管理员令牌创建第一个平台管理员，再切换“个人账号登录”。支持企业成员绑定、账号启停与重置密码；会话 1 小时到期。完整角色边界见 [个人身份](docs/IDENTITY.md)。

## 原生启动

企业页面需要 Node 22.12+。先执行 `npm --prefix web ci` 和 `npm --prefix web run build`，再安装或打包 Python 项目。前端开发说明见 [web/README.md](web/README.md)。

需要 Python 3.11+。在项目目录执行：

```sh
python -m venv .venv
# Linux/macOS
source .venv/bin/activate
# Windows PowerShell 改用：.venv\Scripts\Activate.ps1
python -m pip install --require-hashes -r requirements.lock
python -m pip install -e ".[dev]"
```

通过操作系统设置 `.env.example` 中的环境变量。原生启动**不会自动读取 `.env`**。

```powershell
$env:NEXUS_ADMIN_TOKEN = "替换为独立随机管理员令牌，至少32字符"
$env:NEXUS_CLIENT_TOKEN = "替换为独立随机调用令牌，至少32字符"
$env:NEXUS_ALLOWED_HOSTS = "localhost,127.0.0.1"
uvicorn agent_nexus.app:create_app --factory --host 127.0.0.1 --port 8000
```

Linux 使用 `export NEXUS_ADMIN_TOKEN=...` 设置环境，再用 systemd 托管上述进程。

## 注册与选择模型

推荐先打开 `/admin`，填写 `NEXUS_ADMIN_TOKEN` 对应的管理员令牌，然后：

1. 点击“添加模型”，填写别名、部署位置、协议、实际模型名称及 API 根地址。
2. 云端渠道填写服务器密钥的**环境变量名称**；本地无鉴权服务可以留空。
3. 勾选真实支持的对话/向量能力，设置超时和输出限制，保存配置。
4. 在“连接与能力测试”选择模型及能力，发送一次测试请求，查看响应、用量、耗时和请求 ID。
5. 可在模型卡片编辑、启用或禁用配置。启用状态只代表配置可调用，不代表模型健康。
6. 在“配置修改记录”按模型别名查询历史，查看时间、变更字段和请求 ID，支持加载更早记录。
7. 如果保存提示配置冲突，先保留需要的改动，刷新列表并重新点击编辑，核对最新配置后再保存；系统不会自动覆盖他人修改。

页面令牌仅保存在内存，断开或刷新后需重新输入；测试会请求真实模型，可能产生供应商费用。模型页面暂保留原生实现；企业页面已采用 React/TypeScript/Vite/Ant Design，构建资源随 Python 包交付。基础个人账号与两种角色已实现，更细组织权限仍待开发。

在 `/docs` 的 Authorize 填写管理员令牌，通过 `PUT /api/v1/admin/models/{alias}` 注册模型。完整请求示例见 `examples/`。

管理 API 新建时设置 `If-None-Match: *`；更新前 GET 同一路径，取返回的 etag 放入 `If-Match` 头，提交正文不包含 etag。未携带条件头返回 428，配置冲突返回 412。工作台自动处理这些头，旧管理 API 脚本需要同步调整。

| 场景 | provider | base_url |
| --- | --- | --- |
| 云端兼容 API | `openai_compatible` | 服务商兼容 API 根地址，通常含 `/v1` |
| 本地 vLLM 等 | `openai_compatible` | `http://host.docker.internal:8001/v1` |
| Ollama 原生 | `ollama` | `http://host.docker.internal:11434`，不附加 `/api` |

原生部署将示例地址替换为 `localhost`。云端示例的地址和模型 ID 必须替换，并将真实主机加入 `NEXUS_ALLOWED_HOSTS`。

凭据通过 `NEXUS_PROVIDER_*` 环境变量提供；新增变量时要在 Compose 中显式传入容器。配置只保存变量名，不保存密钥。

注册 `local-help` 后，将 `/docs` 的授权切换为调用令牌，向 `POST /api/v1/chat/completions` 发送：

```json
{"model":"local-help","messages":[{"role":"user","content":"请介绍你能提供哪些帮助"}]}
```

响应格式示例（非真实运行记录）：

```json
{
  "request_id": "服务生成的UUID",
  "model": "local-help",
  "content": "模型回答",
  "finish_reason": "stop",
  "usage": {"input_tokens": 20, "output_tokens": 40}
}
```

切换模型只修改 `model` 别名。管理端更新配置后，新请求立即使用新配置，已开始请求保持原配置；设置 `enabled: false` 可禁用模型。

向量接口 `POST /api/v1/embeddings`：

```json
{"model":"local-embedding","input":["采购单使用说明","库存查询说明"]}
```

## 测试

```sh
python -m pytest -q
python -m ruff check --config pyproject.toml api cli web
npm --prefix web test
```

测试使用模拟 HTTP 验证协议转换、认证、凭据引用、配置持久化、错误脱敏和向量顺序；真实供应商联调需要可用端点与凭据。

本次验证记录见 [VALIDATION.md](docs/VALIDATION.md)。运行依赖锁定在 `requirements.lock`，CI 配置覆盖测试、静态检查和 Docker 镜像构建。

## 当前限制

开发修改见 [CHANGELOG.md](CHANGELOG.md)，本地 Git 工作约定见 [CONTRIBUTING.md](CONTRIBUTING.md)。每个完成步骤创建本地提交，不推送远端。

- 仅文本同步对话和向量。流式、图片、工具调用和 JSON Schema 暂不支持，未知参数返回 422。
- 兼容接口可以配置 `token_parameter` 为 `max_tokens` 或 `max_completion_tokens`；对不支持 temperature 的模型关闭 `supports_temperature`。调用端统一使用 `max_tokens`，网关负责映射。
- 总调用时限使用 `timeout_seconds`，上游解码后响应最多 8 MiB；超限返回明确错误，不截取成成功答案。
- 暂无自动重试及跨模型降级，避免重复计费和私有内容意外发送到云端。
- 已完成 PostgreSQL 实库与基础恢复演练，SQLite 保留为开发方式；RLS、生产规模灾备目标和自动备份尚待完成。
- 主机允许列表只配置可信端点，生产还需网络出口控制以约束 DNS 变化及内网访问。
- 响应采用 Nexus 格式，不是完整的第三方 SDK 兼容代理。

知识库页面支持中文/英文关键词排序，返回文件及页码/段落来源；企业 search API 遵守相同发布权限。向量索引另由下述 API 提供，大模型问答尚未实现。见 [知识库说明](docs/KNOWLEDGE.md)。

0005 新增小规模持久化向量索引与向量检索 API，支持企业已授权的云端/本地 embedding 模型，详见 [向量检索](docs/VECTOR_SEARCH.md)。关键词页面仍独立，混合检索与大模型引用问答未实现。

本轮已接通模型选择与索引管理、混合检索和单轮引用问答，见 [操作与接口](docs/ANSWERS.md)。

当前数据库为 0007，新增 tenant_index_quotas，共 16 张业务表；升级前停止 API 与 Worker 并备份。企业差异化限额通过 index-quota 管理接口配置。

当前数据库 0008 新增 model_calls，17 张业务表，覆盖企业网关调用结果及上游 token 账本。升级前备份并停止 API/Worker；调用次数与 token 配额尚未实现。

当前数据库 0009，新增 tenant_model_quotas，共 18 张业务表。企业模型调用限额覆盖全局默认值；升级前停止 API/Worker 并备份。

当前数据库 0010，新增 knowledge_vector_metadata，共 19 张业务表；升级回填现有向量的分片数和摘要，不调用模型。升级前停止 API/Worker 并备份。
