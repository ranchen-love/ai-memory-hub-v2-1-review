# README 多语言维护与验收约定
## 默认语言与文档结构
根目录 `README.md` 使用简体中文；英文与其他七种语言统一位于 `docs/i18n/`。九个入口应保留独立的语言导航段落，所有站内链接必须有效。
中文与英文主 README 采用以下统一结构：
1. 项目概述：定位、适用范围、基本原则；
2. 系统架构与数据组织：产品仓库、个人 Workspace、本地 Vault、可审阅 Private Git 投影；
3. 核心能力与设计机制：L0–L3、长期记忆治理、12/52/134 人生档案、文件字节与版本、逐 Agent 重读确认；
4. Agent 首次初始化与资料交付：授权、规划、执行、投影、结果报告；
5. 安装与使用示例：集中展示 CLI 命令、合成数据、离线交接；
6. 数据安全与同步机制：权限、五类策略、实际调度/提交/回执；
7. 实现状态与适用边界：已测试、待实际环境验证、未提供能力；
8. 技术文档与项目维护：集中索引，避免在多个章节重复放置同一套说明。
一级标题使用**正式、简洁的书面表达**，不采用疑问式、口语化或营销式标题。每项机制在核心能力章节集中解释，详细命令放到安装示例，安全限制集中说明。
## Agent 引导与当前能力
[Agent 首次部署指南](agent-onboarding.md)及[中文版本](agent-onboarding.zh-CN.md)给出 `onboarding plan/apply/report`、实际获准来源导入、受审 Git 投影、Private 远端操作及交付报告的完整参数。`AGENTS.md` 是 Agent 的执行入口。
V2.4.0 已实现 19 模块初始化、Private Vault 逐项获审投影及模拟 GitHub 远端发布；未实测真实 GitHub 账号发布。软件保留 Vault `2.1`、Workspace `1.0` 和离线交接 `2.2` 协议。
不得宣称任何 Agent 可以仅凭仓库链接访问其他 AI 平台的全部历史会话或文件。未经单独授权，不安装定时任务、不读取 L3 原文、不将 Vault/附件/敏感内容提交 Git。工作区的 `.gitignore` 默认拒绝追踪全部内容；Git 仅发布经审核的独立投影。
## 验收与发行
执行 `python scripts/check_readme_i18n.py` 检查默认中文、九语言链接、八章结构、L0–L3 与操作示例。自动化回归在 Windows/Ubuntu 运行，并审查 ZIP、Bundle、历史秘密与精确文件白名单。
[初始化](workspace.md) · [来源适配器](adapters.md) · [会话协议](protocol.md) · [字段注册表](../life-archive/field-registry.json) · [功能覆盖](workspace-parity.md) · [版本确认](../integrations/memory-bootstrap.md)
其它七种语言的扩展说明以现有译文为基础独立维护，V2.4 的新增工作流程应引用 Agent 入门指南；不得删除已验证的语言入口。
