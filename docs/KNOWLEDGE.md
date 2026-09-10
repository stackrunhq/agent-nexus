# 知识库上传、处理与来源分片

当前完成管理员上传、原文件及分片持久化、独立 Worker、处理状态、失败重试、文档发布/撤回和企业读取隔离。原文件先存数据库 BLOB/bytea，保证原文件和任务一起提交；尚未采用 S3 或 Celery；React 管理页面已接入这些接口。离线 CLI 预览仍可用，不入库、不调用大模型。

## 启动与升级

已有数据库先停止 API 和 Worker，备份后执行 `python -m agent_nexus.db_cli upgrade` 升级到 **0004**；新增 knowledge_documents、knowledge_chunks 两张表。API 和 Worker 使用相同的 NEXUS_DATABASE_URL 或 NEXUS_DATABASE_PATH。

```sh
# 独立终端/服务启动 Worker；API 仍使用原 uvicorn 启动命令
python -m agent_nexus_cli.worker
# 运维调试：最多处理一项，然后退出
python -m agent_nexus_cli.worker --once
```

重新安装项目后也可使用 `nexus-worker`。Docker Compose 已包含 worker 服务，SQLite 共用命名卷，PostgreSQL 等待 migrate 成功。未启动 Worker 时任务保持 queued；API 健康检查不代表 Worker 存活。

## 页面操作

入口 `/admin/tenants` → 应用与版本 → 选择企业 → 管理版本 → 对应版本的“管理知识库”。

1. 草稿版本中选择非空 PDF/DOCX/MD/TXT 文件，点击“上传手册”。页面先检查 10 MiB 上限、格式和文件名；服务器仍是最终校验方。
2. 点击“刷新处理状态”查看等待、解析、完成或失败；当前按需刷新，不自动轮询。失败时显示原因，可点击“重试解析”。等待处理时需确认 Worker 已启动。
3. 点击“查看分片”查看原文、页码/段落和字符范围。原文以纯文本呈现，不执行 HTML 或渲染 Markdown。解析提示可展开查看。
4. 先发布产品版本，再进入其知识库，确认“发布文档”；撤回也需确认。停用企业/应用和退役版本禁止上传、重试及新发布，已发布文档仍可撤回。

文档和分片每页 20 条，使用服务端 offset 分页；满页时可能还存在一个空的末页，可返回上一页。切换企业/应用/版本、刷新应用详情或断开连接会卸载知识库面板，取消其请求并清除选中文件与分片。取消浏览器请求不等于取消已入库任务，重新进入可刷新查询，重复上传由后端去重。

源码：`web/src/app/features/knowledge/KnowledgePanel.tsx`（页面与确认）、`types.ts`（文档/分片类型与错误文案），通过 ApplicationsPanel 接入版本归属。二进制上传复用 shared/client.ts 的身份、取消和过期会话处理，不把文件或凭据存到浏览器持久存储。

## API 操作顺序

管理员根路径：`/api/v1/admin/tenants/{tenant_id}/applications/{app_id}/versions/{version_id}/documents`。使用环境管理员令牌或个人平台管理员会话；企业用户不能上传或管理文档。

| 方法与相对路径 | 功能 |
| --- | --- |
| POST 根路径，query filename | 原始二进制上传，Content-Type: application/octet-stream，返回 202 和文档状态 |
| GET 根路径 | 分页列出文档元信息 |
| GET /{document_id} | 查询 queued/processing/ready/failed、warnings、error 和 published |
| GET /{document_id}/chunks | 分页查看文本、来源及字符偏移 |
| POST /{document_id}/retry | failed 任务重新排队，返回 202 |
| PATCH /{document_id} | JSON `{"published":true}` 发布，false 撤回 |

列表和分片接口支持 offset（默认 0）与 limit（默认 50，最大 100）；不会返回原文件二进制、任务领取令牌或模型凭据。分页顺序固定，但并发上传时不是快照。

1. 创建企业、启用应用并创建 draft 产品版本。
2. 向根路径上传文件，例如 shell 中使用：

```sh
curl -X POST "$DOCUMENTS_URL?filename=manual.pdf" \
  -H "Authorization: Bearer $ADMIN_TOKEN" \
  -H "Content-Type: application/octet-stream" --data-binary @manual.pdf
```

3. Worker 完成解析，轮询单文档状态并审阅 chunks/warnings。无文本文件失败，混合 PDF 的无文本页保留警告，不能把 ready 解释为所有页面完整提取。
4. 使用应用版本接口发布产品版本，再明确发布 ready 文档；解析完成不会自动发布。published/retired 产品版本拒绝新上传，修订手册请新建产品版本。
5. 企业身份读取 `/api/v1/applications/{app_id}/versions/{version_id}/documents` 或其 `/{document_id}/chunks`。要求本企业、启用应用、已发布产品版本、ready 且已发布文档；越权/隐藏返回 404，无企业归属 bootstrap 身份返回 403。撤回文档、停用应用/企业或退役产品版本后即不可读。当前授权粒度为整个企业，不含部门或成员级文档授权。

同版本、同文件名、同 SHA256 重复上传返回已有文档，不重复创建任务和上传事件；不同文件名被视为不同文档。失败重试仅适用于启用企业/应用且版本未退役的 failed 文档。上传、重试、发布和撤回写入现有应用事件，带文档 ID、操作人和请求 ID；不提供原文件下载、删除和文件替换接口。

## Worker 与恢复

Worker 使用数据库事务锁领取一项任务，领取凭证和 5 分钟租约持久化。解析子进程 60 秒超时，完成后在单个事务内写入全部分片和 ready 状态；失败仅写稳定错误码。重启后可重新领取过期任务，旧领取凭证不能覆盖新结果。连续 3 次领取后仍被中断的任务转 failed/worker_interrupted，由管理员重试。

原文件包含在数据库备份中；备份/迁移/恢复必须停止 API 和 Worker 等写入者。恢复后 processing 任务需等待租约到期；重复上传检测只在同版本与文件名范围内生效。本阶段为单机低并发基础，数据库存文件会增加备份体积，后续按负载接入对象存储与专用任务系统。

## 使用

在项目环境安装更新后的依赖及项目：

```sh
python -m pip install --require-hashes -r requirements.lock
python -m pip install -e . --no-deps
python -m agent_nexus_cli.document ./manual.pdf
nexus-document ./manual.md --chunk-size 1000 --overlap 150
```

标准输出是 JSON，包含文件名、原文件 SHA256、warnings 和 chunks；失败向标准错误输出稳定错误码，退出码 2。输出包含原文，按企业文档权限保存预览结果。仅此离线预览命令不修改数据库。

| 格式 | 提取内容与来源 |
| --- | --- |
| TXT、Markdown | UTF-8（可带 BOM），保留 Markdown 原文，来源 document:1 |
| PDF | 文本层，来源为从 1 开始的页码；空白或图片页产生警告 |
| DOCX | 正文段落及表格内段落，来源为从 1 开始的段落序号 |

分片采用字符窗口，默认 1000 字符、150 字符重叠，不跨来源段落/页面。size 范围 100–4000，overlap 不超过 size 的一半；不是模型 token 数。start/end 为换行规范化后的来源文本字符偏移，end 不包含在片段内。暂不识别 Markdown 标题层级或语义边界。

## 限制与后续

- 输入最多 10 MiB，PDF 最多 500 页，提取文本最多 200 万字符、分片最多 10000 个；DOCX 压缩包最多 2000 项、声明解压体积 50 MiB，正文 XML 最多 10 MiB；禁止 XML 实体，不解压包内文件到磁盘。入库固定使用默认分片参数，离线 CLI 可调整。
- 加密 PDF 拒绝处理；全部无文本的文档报 no_extractable_text，混合 PDF 通过 warnings 标明无文本页。暂不支持 OCR、图片、旧 DOC、页眉页脚、复杂版式和表格结构还原。
- 入库解析在独立子进程执行，不继承 Nexus 数据库/模型凭据，输入输出放在自动清理的临时目录。POSIX 子进程配置 512 MiB 地址空间、45 秒 CPU 和 32 MiB 输出文件上限；Docker Worker 另限 768 MiB 内存、1 CPU、64 进程。Windows 原生只有子进程超时和输入/输出量限制，没有地址空间硬限制；离线预览 CLI 不具备进程隔离。PDF 解码资源风险见 [pypdf 文本提取说明](https://pypdf.readthedocs.io/en/stable/user/extract-text.html)。进程隔离不是完整安全沙箱，上线前仍需验证平台限制、入口并发/速率/请求超时与文档访问策略。
- 下一步：向量索引、混合检索和带引用问答。OCR、S3、Celery、队列监控与企业存储配额尚未实现。

代码入口：api/src/agent_nexus/knowledge/ 下 router.py（HTTP）、store.py（数据与任务状态）、jobs.py（子进程调度）、process.py（解析子进程）、parsing.py（格式解析）、chunking.py（来源分片）；cli/src/agent_nexus_cli/worker.py（Worker 命令）、document.py（预览），api/tests/knowledge/（回归）。
