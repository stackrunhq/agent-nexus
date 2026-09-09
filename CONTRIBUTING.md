# 开发与本地版本记录

按用户约定执行：每个可验收步骤都加入 Git，保留本地提交，不推送 Git 服务。

1. 开始前查看 `git status` 和当前路线图，保留已有改动。
2. 完成一个明确步骤，更新 `CHANGELOG.md`，记录功能、验证结果和未完成的验证。
3. 执行适合本次变更的测试与检查；失败先修复，不把未通过的验证写成通过。
4. 仅暂存该步骤相关文件，检查 `git diff --cached --check` 和暂存差异。
5. 执行本地 `git commit`，使用能说明最终功能的提交信息。
6. 用 `git status` 和 `git log --oneline` 核对结果，向用户报告提交及限制；同时列出当前已完成功能、下一步待开发功能，并维护 docs/STATUS.md。

除非用户另行明确要求，不执行 `git push`，不重写已有提交。不要提交 `.env`、真实凭据、数据库、虚拟环境、缓存或生成的 egg-info。

开始开发前阅读 [代码导航](docs/architecture/CODE_MAP.md)。按业务目录放置代码及对应测试，app.py 只负责组装。移动模块后检查导入、CI、包内资源、迁移路径和文档命令；构建前清理仓库内生成的 build 目录，避免旧模块残留进入 wheel。

Python 检查：`python -m pytest -q`、`python -m ruff check --config pyproject.toml api cli web`。
React 前端：`npm --prefix web ci`、`npm --prefix web test`、`npm --prefix web run build`；先构建前端再构建 Python wheel，提交 package-lock.json，不提交生成的 tenants 静态目录。

原模型前端脚本检查：`node --check web/src/agent_nexus_web/static/admin.js`。

`CHANGELOG.md` 记录代码开发历史；工作台的“配置修改记录”记录运行时模型配置变化，两者用途不同。
