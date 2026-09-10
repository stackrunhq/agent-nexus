# 管理前端

企业管理采用 React + TypeScript + Vite + Ant Design，入口 /admin/tenants；原模型工作台 /admin 暂保留原生页面，两者可互相跳转。个人账号登录位于企业页面；原模型页仍需输入管理员令牌或有效的平台管理员个人会话，暂不共享页面会话。

## 代码位置

- src/app/main.tsx：React 入口与主题。
- src/app/features/tenants/TenantPage.tsx：企业列表、创建、启停、轮换、授权及事件。
- src/app/features/tenants/types.ts：企业页面数据类型。
- src/app/features/applications/ApplicationsPanel.tsx：按企业管理应用与版本、发布确认和操作记录。
- src/app/features/knowledge/KnowledgePanel.tsx：按产品版本上传、处理状态、服务端分页、分片预览、重试及发布确认；types.ts 定义协议类型和错误文案。
- src/app/features/users/UsersPanel.tsx：账号创建、状态、密码重置与安全事件。
- src/app/shared/client.ts：管理员请求、个人登录/退出、会话到期、204 空响应、错误和断开取消。
- src/agent_nexus_web/static：原模型页面及打包资源；tenants 子目录是生成物，不手工修改、不提交。

## 开发与构建

使用 Node 22.12+，从仓库根执行：

```sh
npm --prefix web ci
npm --prefix web test
npm --prefix web run build
python -m pip install -e '.[dev]'
```

设置后端环境变量并启动 API，再访问 http://127.0.0.1:8000/admin/tenants。打包 wheel 前也必须先构建前端。未构建企业页时该入口返回明确 503，原模型页面不受影响。Docker 已使用 Node 构建阶段自动完成这些步骤。

开发模式：启动后端后执行 `npm --prefix web run dev`，使用 Vite 输出的地址加 /admin/assets/tenants/；/api 代理到本地 8000。请勿将开发服务器暴露公网。

凭据仅在内存中；关闭凭据弹窗立即卸载内容，断开连接取消请求并清除页面数据。状态变更与轮换有确认；轮换后旧凭据立即失效。已支持个人平台管理员登录和账号管理；企业成员只可调用所属企业授权模型，不能进入平台后台。详见 [个人身份](../docs/IDENTITY.md)。

企业页因 Ant Design 动态样式允许内联 CSS，脚本仍限定同源；原模型页 CSP 保持严格。当前生产 JS 约 965 KB（gzip 约 306 KB），后续页面扩展时做拆分加载。

构建路径依据 [Vite build](https://vite.dev/guide/build)；组件用法参照 [Ant Design Modal](https://5x.ant.design/components/modal/)。
