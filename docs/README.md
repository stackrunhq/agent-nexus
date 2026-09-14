# 文档导航

- [PostgreSQL 完整管线基准](POSTGRES_PIPELINE.md)：隔离数据库、并发准入和进程工作集采样。

- [pgvector 并发与内存基准](VECTOR_CONCURRENCY.md)：运行命令、六组实测及 Python 内存范围。

- [软件管线容量基准](PIPELINE_BENCHMARK.md)：运行命令、实测结果、中断注入及适用边界。

- [索引进度与升级](INDEX_PROGRESS.md)：0012、内容修订计数、独立批次存储及旧进度处理。

- [索引检查点](INDEX_CHECKPOINTS.md)：0011 升级、内容修订摘要、租约隔离与中断恢复。

- [向量元数据](VECTOR_METADATA.md)：0010 回填、状态/原生检索读取优化及旧快照兼容。

- [可选 pgvector 后端](PGVECTOR.md)：部署初始化、重建、回退与未完成的规模验证。

- [企业模型调用账本](MODEL_USAGE.md)：记录范围、查询接口、token 与待确认状态边界。

- [索引构建配额](INDEX_QUOTAS.md)：统一准入、每日用量、错误码与计数边界。

- [后台索引任务](INDEX_JOBS.md)：0006 升级、索引 Worker、任务接口与容量限制。

- [手册与模型评测](../evaluation/README.md)：初始题集、CLI 执行方式和真实模型验证边界。

| 想了解什么 | 从这里开始 |
| --- | --- |
| 如何启动项目 | [项目 README](../README.md) |
| 目标技术栈与当前实现 | [技术架构](architecture/TECH_STACK.md) |
| 容器部署入口 | [Docker 说明](../docker/README.md) |
| 代码在哪、怎么读、怎么扩展 | [代码与目录导航](architecture/CODE_MAP.md) |
| 已完成哪些功能、下一步做什么 | [当前进度](STATUS.md) |
| 总体开发阶段与验收目标 | [路线图](ROADMAP.md) |
| 模型协议、配置和调用接口 | [模型网关](MODEL_GATEWAY.md) |
| 企业应用、版本与发布 | [应用版本](APPLICATIONS.md) |
| 文档格式、分片与本地预览 | [知识库解析](KNOWLEDGE.md) |
| 模型选择、向量索引与失效重建 | [向量检索](VECTOR_SEARCH.md) |
| 个人登录、账号与角色 | [个人身份](IDENTITY.md) |
| 企业凭据与模型授权 | [企业接入](TENANT_ACCESS.md) |
| 数据库部署、迁移、导入与诊断 | [数据库](DATABASE.md) |
| PostgreSQL 备份恢复操作 | [恢复演练](BACKUP_RESTORE.md) |
| 哪些检查真的执行过、有哪些限制 | [验证记录](VALIDATION.md) |
| 如何提交代码 | [贡献约定](../CONTRIBUTING.md) |
| 每一步修改了什么 | [变更日志](../CHANGELOG.md) |

现有接口和操作文档保留原路径，避免已有链接失效。新增架构说明放入 architecture；同一主题优先更新已有文档，避免重复维护多个当前状态。

- [混合检索与引用问答](ANSWERS.md)：模型选择、索引管理、对外接口和引用校验边界。
