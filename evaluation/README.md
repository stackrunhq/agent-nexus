# 手册与模型评测

本目录放可版本化的问题与预期来源；企业原文件、凭据及包含敏感内容的结果不提交 Git。

第一组基准使用本项目真实操作文档 `docs/ANSWERS.md` 和 `docs/VECTOR_SEARCH.md`，不是虚构企业手册。将这两个 Markdown 文件上传至测试企业的同一产品版本，解析后发布版本与文档，并为测试企业授权 embedding 模型、建立索引。企业手册可按相同结构另建 cases 文件。

设置环境变量 `NEXUS_EVAL_TOKEN` 为测试企业凭据，然后运行（替换应用、版本与模型别名）：

```powershell
python -m agent_nexus_cli.evaluate --base-url http://127.0.0.1:8000 --application APP_ID --version VERSION_ID --model EMBED_ALIAS --chat-model CHAT_ALIAS --cases evaluation/cases.json --output .tools/evaluation-report.json
```

省略 `--chat-model` 仅测试混合检索。每个问题调用一次接口；问答模式还会调用聊天模型并可能计费。工具不上传手册、不修改发布状态、不自动重建索引。每次最多 100 题，报告不保存原文和生成回答，只保存题号、来源文件、状态、延迟及命中/拒答情况。

预期来源命中率只能检查检索是否找到指定文件，不是回答准确率。无答案题只有问答模式可计分。人工应逐项核对事实是否被引用支持、步骤是否完整、无答案是否拒答，并记录模型实际版本、手册版本、配置及评测日期。模板初始规模很小，应补充真实企业的同义问法、跨段问题、版本冲突及文档提示注入案例。

真实模型运行依赖可用测试环境、已发布手册和企业授权；自动化测试使用模拟响应，只验证评测器计算逻辑，不代表真实质量。下一阶段为持久化索引任务、并发/用量配额和 pgvector 扩展，需独立迁移、Worker 租约与回归验证。
