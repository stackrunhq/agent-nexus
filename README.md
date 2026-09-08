# Agent Nexus

面向企业应用的知识库、使用指导与流程规划中台，按阶段实现。

当前版本 **0.2：模型管理工作台**，提供浏览器配置页面、模型启停、真实对话/向量试调用，以及统一模型 API。
这是单平台开发基础，尚未实现企业多租户隔离、知识库、终端用户帮助中心及流程执行，不能直接作为多租户 SaaS 上线。

## 开发顺序

详细范围见 [路线图](docs/ROADMAP.md)，接口约定见 [统一模型接入](docs/MODEL_GATEWAY.md)。

1. **当前阶段**：工程、模型配置、云端/本地协议适配、鉴权、测试、部署配置。
2. 企业基础：PostgreSQL、迁移、企业/客户组织/用户权限、企业模型授权、React 管理后台。
3. 知识库：文档处理、版本发布、中文混合检索、引用问答。
4. 使用指导：帮助中心、嵌入式助手、会话、流式回答、分步引导。
5. 流程执行：模板、持久化状态机、确认、连接器、幂等、业务回调。
6. 上线：评测、配额、审计、监控、备份恢复、集群部署。

## Docker 启动

需要 Docker Engine 和 Compose。复制 `.env.example` 为 `.env`，填入两个不同的随机令牌（至少 32 字符），并按需要设置允许访问的模型主机和云端密钥。

```sh
docker compose up --build -d
```

- API 文档：<http://localhost:8000/docs>，可直接测试管理和调用接口。
- 模型管理工作台：<http://localhost:8000/admin>，无需单独构建前端。
- 就绪检查：<http://localhost:8000/health/ready>。
- 默认只绑定宿主机回环地址。对外部署通过 HTTPS 网关访问并配置限流。
- 命名卷 `nexus-data` 保存配置，`down -v` 会删除这些数据。
- 容器内 `localhost` 指容器本身；访问宿主机模型使用 `host.docker.internal`。
- 模型服务需要监听容器可访问的地址，结合防火墙限制来源。
- Compose 不安装或下载本地模型。先在独立 Ollama/vLLM 服务准备模型，模型名必须与实际服务一致。

## 原生启动

需要 Python 3.11+。在项目目录执行：

```sh
python -m venv .venv
# Linux/macOS
source .venv/bin/activate
# Windows PowerShell 改用：.venv\Scripts\Activate.ps1
python -m pip install --require-hashes -r requirements.lock
python -m pip install -e ".[dev]" -c requirements.lock
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

页面令牌仅保存在内存，断开或刷新后需重新输入；测试会请求真实模型，可能产生供应商费用。页面使用原生 HTML/CSS/JavaScript 随 Python 包交付，完整企业后台仍按下一阶段引入 React。

在 `/docs` 的 Authorize 填写管理员令牌，通过 `PUT /api/v1/admin/models/{alias}` 注册模型。完整请求示例见 `examples/`。

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
python -m ruff check src tests
```

测试使用模拟 HTTP 验证协议转换、认证、凭据引用、配置持久化、错误脱敏和向量顺序；真实供应商联调需要可用端点与凭据。

本次验证记录见 [VALIDATION.md](docs/VALIDATION.md)。运行依赖锁定在 `requirements.lock`，CI 配置覆盖测试、静态检查和 Docker 镜像构建。

## 当前限制

- 仅文本同步对话和向量。流式、图片、工具调用和 JSON Schema 暂不支持，未知参数返回 422。
- 兼容接口可以配置 `token_parameter` 为 `max_tokens` 或 `max_completion_tokens`；对不支持 temperature 的模型关闭 `supports_temperature`。调用端统一使用 `max_tokens`，网关负责映射。
- 总调用时限使用 `timeout_seconds`，上游解码后响应最多 8 MiB；超限返回明确错误，不截取成成功答案。
- 暂无自动重试及跨模型降级，避免重复计费和私有内容意外发送到云端。
- SQLite 仅保存首阶段配置，下一阶段迁移 PostgreSQL 并加入企业授权。
- 主机允许列表只配置可信端点，生产还需网络出口控制以约束 DNS 变化及内网访问。
- 响应采用 Nexus 格式，不是完整的第三方 SDK 兼容代理。
