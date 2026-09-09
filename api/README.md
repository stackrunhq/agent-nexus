# 后端 API

入口：src/agent_nexus/app.py。模型业务在 models/，企业接入在 tenants/；router 处理 HTTP、schemas 校验数据、store 管理业务读写。公共认证在 api/，配置在 core/，连接、表结构和迁移在 storage/。

从仓库根安装 `python -m pip install -e '.[dev]'`，设置环境变量后运行 `uvicorn agent_nexus.app:create_app --factory --host 127.0.0.1 --port 8000`。测试执行 `python -m pytest -q`，用例在 api/tests 下按业务分类。

前端源码在顶层 web/，运维命令在 cli/。完整导航见 [代码地图](../docs/architecture/CODE_MAP.md)。

知识库业务在 knowledge/：router.py 是上传/状态/发布/读取接口，store.py 是租户归属、数据事务和持久化队列，jobs.py 启动 process.py 解析子进程；parsing.py 与 chunking.py 保持纯解析和分片职责。独立 Worker 入口在 cli/src/agent_nexus_cli/worker.py，详见 [知识库说明](../docs/KNOWLEDGE.md)。
