# README 的章节、语言与能力维护规则
## 默认语言及信息架构
根目录 `README.md` 使用**简体中文**，其它八种语言放在 `docs/i18n/`。语言导航必须独立成段，并且所有相对链接可解析。
主 README 的八章围绕用户完成任务的顺序组织：
1. 产品定位和适合谁；
2. Agent 首次使用与授权；
3. 能力机制和设计理由（尤其是 L0–L3、文件字节、候选治理、逐 Agent 版本确认）；
4. 工作区、Vault 和 Git 仓库的存放边界；
5. 可执行的初始化与合成演示；
6. 同步开关、权限与运维；
7. 已实现、需要授权和待开发的能力；
8. 长期目标。
英文首页遵循相同的八章顺序；其他语言保留实际能力和边界，并引导新用户阅读 `docs/agent-onboarding.md`。
## Agent 首次部署入口
[Agent 首次部署指南](agent-onboarding.md)和[中文版本](agent-onboarding.zh-CN.md)记录 `onboarding plan/apply/report`、授权导入、Git 投影及可选的私有仓库命令。平台数据取决于实际获准来源，计划任务需单独部署和验收。
`AGENTS.md` 必须包含第一次搭建时的入口；所有 Agent 要报告真实工具、来源权限、合成测试结果、Workspace/Vault、可选用户私有 Git 仓库、数据覆盖、待审批与待补信息，以及同步策略与真实运行证据。
GitHub 远端写入与创建私人仓库必须经过用户批准。生成的 Workspace 默认 `.gitignore` 忽略全部个人内容，不能用 `git add -f .` 回避安全界限；Git 只使用经审核的最小化投影。
## 产品版本与测试
- V2.4.0 软件沿用 Vault `2.1` 协议、Workspace `1.0` 格式和离线传输 `2.2`。
- [初始化](workspace.md)、[能力差异](workspace-parity.md)、[来源适配器](adapters.md)、[会话协议](protocol.md)、[候选治理](../workflows/memory-lifecycle.md)、[Agent 版本确认](../integrations/memory-bootstrap.md)。
- [人生档案字段注册表](../life-archive/field-registry.json)包括 12 类、52 个二级领域和 134 字段，但无真实个人内容。
- 健康功能当前仅校验去标识化汇总；原始健康平台自动同步、所有 AI 账户会话自动获取、远端 Git 私有资料全自动推送以及持续生产调度均不是已完成的通用能力。
执行 `python scripts/check_readme_i18n.py` 核验语言导航、章节、关键能力、L0–L3 和本地链接；Windows/Ubuntu CI 与发布审计还需核实。
发行清单严格枚举当前文件，历史遗留白名单与当前发布清单分开管理；所有真实个人资料和 Vault 字节都不得加入通用仓库。
