# 管理前端

源码在 src/agent_nexus_web/static/：index.html 为布局表单，admin.js 为模型配置、试调用和审计交互，admin.css 为样式。

当前是原生页面，尚未迁移 React。资源通过 Python 包 agent_nexus_web 打包，使原生安装和 Docker 均可由 API 的 /admin、/admin/assets 访问，源码仅维护一份。

从仓库根执行 `node --check web/src/agent_nexus_web/static/admin.js`。

后续在此目录引入 React + TypeScript + Vite 和 Ant Design，按 models、tenants、users 等功能组织页面，并更新构建与部署。
