# 知识库文档解析与分片

当前完成离线解析与分片基础模块，可通过 CLI 预览 JSON；尚未接入上传接口、数据库、企业权限、后台任务或管理页面。预览不会把文件加入知识库，也不会调用大模型。

## 使用

在项目环境安装更新后的依赖及项目：

```sh
python -m pip install --require-hashes -r requirements.lock
python -m pip install -e . --no-deps
python -m agent_nexus_cli.document ./manual.pdf
nexus-document ./manual.md --chunk-size 1000 --overlap 150
```

标准输出是 JSON，包含文件名、原文件 SHA256、warnings 和 chunks；失败向标准错误输出稳定错误码，退出码 2。输出包含原文，按企业文档权限保存预览结果。当前不修改数据库，不需要新增迁移。

| 格式 | 提取内容与来源 |
| --- | --- |
| TXT、Markdown | UTF-8（可带 BOM），保留 Markdown 原文，来源 document:1 |
| PDF | 文本层，来源为从 1 开始的页码；空白或图片页产生警告 |
| DOCX | 正文段落及表格内段落，来源为从 1 开始的段落序号 |

分片采用字符窗口，默认 1000 字符、150 字符重叠，不跨来源段落/页面。size 范围 100–4000，overlap 不超过 size 的一半；不是模型 token 数。start/end 为换行规范化后的来源文本字符偏移，end 不包含在片段内。暂不识别 Markdown 标题层级或语义边界。

## 限制与后续

- 输入最多 10 MiB，PDF 最多 500 页，提取文本最多 200 万字符；DOCX 压缩包最多 2000 项、声明解压体积 50 MiB，正文 XML 最多 10 MiB；禁止 XML 实体，不解压文件到磁盘。
- 加密 PDF 拒绝处理；全部无文本的文档报 no_extractable_text，混合 PDF 通过 warnings 标明无文本页。暂不支持 OCR、图片、旧 DOC、页眉页脚、复杂版式和表格结构还原。
- 文件大小限制不是解析进程的内存/时间隔离。PDF 解码可能消耗较大内存，参见 [pypdf 文本提取说明](https://pypdf.readthedocs.io/en/stable/user/extract-text.html)。当前只用于可信本地文件；开放上传前需在独立 Worker 中加超时、内存限制和任务恢复。
- 下一步：企业/应用/版本归属下的上传、原文件存储、文档与分片持久化、任务状态及租户隔离测试；再接管理页面、向量索引和引用问答。

代码入口：api/src/agent_nexus/knowledge/parsing.py（格式解析），chunking.py（来源分片），cli/src/agent_nexus_cli/document.py（预览），api/tests/knowledge/（回归）。
