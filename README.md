# AI Memory Hub
**语言 / Languages：** [简体中文](README.md) · [English](docs/i18n/README.en.md) · [日本語](docs/i18n/README.ja.md) · [한국어](docs/i18n/README.ko.md) · [Español](docs/i18n/README.es.md) · [Français](docs/i18n/README.fr.md) · [Deutsch](docs/i18n/README.de.md) · [Português (Brasil)](docs/i18n/README.pt-BR.md) · [Русский](docs/i18n/README.ru.md)
**一个由用户掌控、可自行初始化、面向长期积累的通用 AI 共享记忆中枢。**
把分散在对话、项目、文件和不同 AI 工具中的长期信息，整理为**可查找、可理解、可更新、可追溯、可授权迁移**的个人资料体系。它关注的不只是“让 AI 记住”，更是：**应该保存哪些信息，怎样在未来重新使用，如何确保来源可靠，以及用户如何始终掌握控制权。**
> **定位**：个人长期记忆库 · 人生档案体系 · 项目与决策知识库 · 跨 AI 协作上下文 · 会话与文件归档 · 可初始化的工作区
>
> **设计原则**：用户拥有资料、模型中立、按需读取、来源可追溯、变更可审核、敏感数据最小授权。
>
> **版本与状态**：V2.3.0 · Python 3.11+ · MIT License · 本地优先 · 当前仓库仍为 Private，尚未正式公开发布。
本项目提供的是**去个人化的完整模板与本地引擎**，而不是作者私人记忆的公开副本。安装时不包含任何用户的真实经历、个人事实、健康记录或聊天导出，也不会自动获取 AI 平台账户权限。
---
## 一、这个仓库可以做什么？
### 1. 为不同 AI 提供统一的长期背景
不同 AI 工具在**具备实际访问权限并取得用户授权后**，可以使用同一套有来源、有版本的记忆资料，不再只依赖各平台彼此隔离的聊天摘要。一个新 Agent 可以按统一入口了解用户选择分享的稳定偏好、项目背景、协作规则和待完成任务。
通用工作区提供 [Agent 统一入口](AGENTS.md)、[任务导航索引](core/INDEX.md)、[接入协议](integrations/memory-bootstrap.md) 与 [能力边界说明](integrations/capabilities.md)。
**边界**：这些文件存在，不代表每个 AI 平台都能自动访问本机文件或 GitHub；自动读取、自动召回和账号连接均需要独立配置、授权及实际验证。
### 2. 形成持续维护的人生档案
以 **12 个一级类别、52 个二级领域、134 项注册字段**组织身份背景、成长、教育、职业、价值观、关系、健康生活、财务、目标、AI 协作、重大事件及资料维护。
每条记录可标注来源、证据等级、发生时间、有效区间、敏感等级与历史替代关系。初始 12 类全部为 `unknown`，**有分类不代表系统已经知道用户的信息**；后续可按需逐步完善。
[人生档案说明](life-archive/README.md) · [分类目录](life-archive/taxonomy.md) · [字段注册表](life-archive/field-registry.json) · [空白档案](life-archive/profile.json)
### 3. 保存长期偏好与可复用的行为规则
将长期适用的沟通习惯、任务方法、协作标准、执行边界和已确认的个人偏好，分类存入结构化资料。系统区分**事实、偏好、规则、决策、推断和待核实信息**，不把一句临时要求自动升级成永久规则。
[通用规则入口](core/hard-rules.md) · [偏好模板](core/preferences.md) · [结构化记忆](memory/facts.yaml)
### 4. 维持项目上下文与连续性
为长期项目保存目标、范围、关键约束、已经验证的结论、方案取舍、交付资产、风险和下一步。中断数周后可以从项目检查点继续，也可以通过授权的交接包将上下文交给另一位 Agent。
[项目模板](projects/TEMPLATE.md) · [项目入口](projects/README.md) · [交接协议](collaboration/handoff-protocol.md)
**边界**：项目记忆是带来源和时间的背景资料，不能代替当前源码、最新工单或真实环境的重新验证。
### 5. 沉淀经验、决策过程和复盘结论
不仅保存最后的结论，还保留理由、参考证据、适用条件、已否决方案及重审条件。发生变更时记录新旧版本和替代关系，让未来的 AI 分清“当时为什么这样决定”和“现在是否仍然有效”。
[决策索引](memory/decisions.md) · [变更记录](memory/changelog.md) · [待复核资料](memory/pending-review.md)
### 6. 保存工具生态和可迁移的能力信息
用平台中立的方式记录 AI 工具、Skills、插件、MCP（Model Context Protocol，模型上下文协议）及其他外部能力的用途、接入条件、实际验证结果和限制。
严格区分**工具名称、可发现、已安装、已授权、能调用、实际调用成功**等不同状态；不会因为在一台设备或一个 AI 平台上可用，就断言其他 Agent 也具有同样的能力。
[接入目录](integrations/README.md) · [平台能力矩阵](integrations/capabilities.md)
### 7. 归档会话与真实文件，支持可选健康摘要
会话按照 **L0 索引、L1 摘要、L2 详细检查点、可选 L3 有来源的可见原文**组织，原文必须额外获准。对于用户上传件和 AI 生成件，可以保存**实际文件字节**、SHA-256 校验值、资产版本与来源，而不只是一个可能过期的外部链接。
提供可选健康扩展，但目前**仅对明确授权的去标识化汇总做结构校验**；不包含私人版特有的健康设备原始记录同步、历史自动回填或生产定时采集能力。
[会话说明](sessions/README.md) · [资产索引](assets/README.md) · [健康扩展边界](life-archive/health/README.md) · [来源适配器](docs/adapters.md)
### 8. 管理记忆的新增、去重、更正和审核
记忆不是直接覆盖旧文件。V2.3 的候选治理包含可执行的**验证、同键去重与冲突建议、审批、单独激活、撤销、替代和版本追溯**，其逻辑为：
```text
发现具有长期价值的信息
          ↓
核对类型、来源、时间及敏感等级
          ↓
形成候选，验证格式并检查重复与冲突
          ↓
人工核实证据并明确批准或拒绝
          ↓
另行授权激活，或进入可选 PR 审核流程
          ↓
进入可读取的正式记忆并保留修订记录
          ↓
相关 Agent 按权限重读变更
```
**候选被批准不等于已经激活成正式事实**；可选 PR 流程也不会自动把私人信息推送到任何仓库。
[记忆生命周期与命令](workflows/memory-lifecycle.md) · [候选入口](candidates/README.md)
### 9. 检测共享版本变化，避免误报同步
接收方可以检测经用户挑选、批准并交付的共享记忆快照，对变化的范围逐一重读。系统区分：
- `detected_sha`：当前检测到的快照版本；
- `synced_sha`：接收 Agent 已明确确认重读的版本；
- `pending_reload` / `reload_scope`：仍待读取或确认的内容。
原始来源不可访问时会报告 `unknown`；**检测到新的 SHA 不等于已经重读，更不等于 Agent 真正理解了内容**。
[跨 Agent 版本确认](integrations/memory-bootstrap.md) · [共享快照格式](schemas/shared-memory.schema.json)
### 10. 统一验证、权限边界与长期维护
仓库包含 JSON Schema、自动化测试、明确的发行文件白名单、Windows/Ubuntu 回归以及 ZIP/Bundle 独立构建审计。真实工作区与本地 Vault 分开创建，默认**零来源授权**，由操作系统权限控制读取范围。
[安全约定](SECURITY.md) · [权限边界](core/boundaries.md) · [部署与恢复](docs/deployment.md) · [CI 入口](.github/workflows/test.yml)
---
## 二、仓库保存哪些方向的内容？
以下描述的是**可以保存的信息领域**，而不是任何人的实际个人档案。空白工作区不会自动填充个人事实。
### A. 人生档案：12 大类信息领域
| 一级领域 | 可保存的信息方向 |
| --- | --- |
| **01 · 基础身份** | 基本背景、地区与语言、身份资料的用途及隐私边界 |
| **02 · 童年与成长** | 早年环境、家庭与成长轨迹、阶段变化、重要经历 |
| **03 · 教育与学习** | 教育经历、学习方法、技能积累、成长目标 |
| **04 · 职业与事业** | 职业履历、专业能力、项目实践、职业发展 |
| **05 · 性格与价值观** | 自我认识、价值倾向、行为与沟通方式、决策原则 |
| **06 · 人际与社会关系** | 家庭、朋友、社交与职业关系及相关边界 |
| **07 · 健康与生活** | 健康背景、生活习惯、运动作息、资料来源 |
| **08 · 财务与现实条件** | 收支、资产负债、生活成本、计划及现实约束 |
| **09 · 目标与未来规划** | 长期愿景、近期目标、个人兴趣与计划演变 |
| **10 · AI 协作与决策** | 工具、协作约定、任务分工、重要决策与复盘 |
| **11 · 人生重大事件** | 人生里程碑、关键时间线、转折与阶段变化 |
| **12 · 资料收集与维护** | 来源、可信度、敏感等级、冲突复核、归档及访问策略 |
**覆盖度不等于事实完整度**。初始化后所有类别均标记为 `unknown`；52 个领域和 134 项字段是**待填写的结构**。实际数据需要逐条确认来源和权限。
[分类与领域](life-archive/taxonomy.md) · [字段与约束](life-archive/field-registry.json) · [资料结构校验](schemas/life-fields.schema.json)
### B. 长期记忆与协作规范
| 信息领域 | 保存方向 |
| --- | --- |
| **稳定背景和偏好** | 持续适用的表达方式、沟通习惯、生活与任务偏好 |
| **长期规则和授权边界** | 用户批准的行为规则、不可越权事项、风险处理原则 |
| **来源与可信度** | 自述、正式证据、外部材料、推断和候选的区分 |
| **决策及历史版本** | 决策依据、适用时间、变化原因、替代与归档 |
| **多 Agent 协作** | 阅读范围、交接信息、验证标准及版本确认 |
| **可复用工作流程** | 研究、研发、写作、项目交接和质量审核方法 |
入口：[核心资料](core/INDEX.md) · [长期记忆](memory/README.md) · [协作协议](collaboration/) · [工作流](workflows/)
### C. 工作、技术与项目知识
| 信息领域 | 保存方向 |
| --- | --- |
| **项目背景** | 业务目标、需求约束、参与角色、历史进度 |
| **方案与取舍** | 设计方案、选型理由、可替代方案及其风险 |
| **开发与验证** | 技术环境、接口、测试证据、完成与待验收事项 |
| **问题和经验** | 故障现象、有效处理方法、避免重复踩坑的结论 |
| **交付与连续性** | 原始文件、检查点、资产版本、后续任务与交接 |
| **通用知识** | 可以跨项目使用的概念、工具经验和方法 |
入口：[项目模板](projects/TEMPLATE.md) · [知识模板](knowledge/TOPIC.md) · [开发流程](workflows/development.md)
### D. 工具、Skills 与 AI 接入知识
| 信息领域 | 保存方向 |
| --- | --- |
| **AI 接入** | 平台授权、来源格式、是否可访问本地工作区或共享快照 |
| **Skills 与插件** | 适用任务、调用条件、来源、验证状态 |
| **MCP 与其他外部工具** | 可发现能力、连接条件、权限及实际使用结果 |
| **Agent 分工** | 执行职责、协作限制、验收与交付流程 |
| **环境兼容性** | 依赖版本、升级限制、终端及运行环境 |
入口：[平台说明](integrations/capabilities.md) · [Agent 角色](collaboration/agent-roles.md)
### E. 健康、生活与文件资产
| 信息领域 | 保存方向 |
| --- | --- |
| **健康和生活背景** | 有来源且获得授权的历史记录、习惯及时间线 |
| **去标识化健康汇总** | 选定统计周期、指标、单位与样本数的格式校验 |
| **用户上传文件** | 原始字节、文件标识、版本、来源与 SHA-256 |
| **AI 生成文件** | 生成件的真实归档版本、关联项目和会话 |
| **会话上下文** | L0–L2 分层摘要和检查点，另行授权的 L3 原文 |
| **派生分析** | 基于已归档资料产生的可追溯摘要与结论 |
**能力边界**：健康汇总验证不是 Apple Health 或其他设备的原始数据自动同步；外链只有在真实字节保存后才属于本地文件资产。
入口：[健康摘要说明](life-archive/health/README.md) · [资产说明](assets/README.md) · [文件归档指南](docs/guide.md)
---
## 三、常见使用场景
| 你想完成的事情 | 记忆中枢如何支持 |
| --- | --- |
| **刚开始使用新的 AI 工具** | 从 `AGENTS.md` 和分类索引读取获准的核心背景；不能访问时采用经批准的交接包 |
| **重启中断已久的项目** | 根据项目检查点、历史决策、资产版本和遗留事项恢复上下文 |
| **更换 Agent 接手工作** | 提供已审核项目背景，选择性传输确切版本文件并由接收 Vault 核对 |
| **让 AI 按长期偏好工作** | 按需读取相关规则、沟通标准，不把一次性要求扩展为全局规则 |
| **持续补全人生档案** | 在 12/52/134 分类下逐条标记来源、时间、可信度及覆盖缺口 |
| **保存 AI 生成的报告或代码** | 将真实字节与项目/会话关联，保留历史版本而非只存链接 |
| **补充、更正或撤销记忆** | 先建候选并审查冲突，批准后单独激活；原版本可追溯 |
| **确认共享内容有无更新** | 比较快照 SHA，读取变化范围并显式确认，不把检测当同步 |
| **检查某项健康汇总** | 对已授权、去标识化汇总做格式核验，不擅自访问设备原始数据 |
| **确认定时同步有没有执行** | 分别查看开关、来源授权、运行回执和调度状态，不以开关代替执行证据 |
这些场景需要**真实访问权限、实际数据覆盖和任务适配能力**。本项目提供可执行的底座，但不会替任意 AI 平台自动建立账户连接。
---
## 四、数据如何组织？
采用与私人记忆中枢一致的**统一入口 → 分类索引 → 具体资料 → 来源/历史版本**逻辑。公开的是模板与程序，真正的私人资料则放在用户自己初始化的工作区和 Vault。
```text
AI Memory Hub
├── README.md                    中文默认首页与使用导航
├── AGENTS.md                    模型中立的 Agent 接入入口
├── core/                        任务索引、规则、偏好、权限边界
├── memory/                      结构化记忆、决策、变更与待审核
├── projects/                    项目模板与长期检查点
├── sessions/                    L0–L3 会话索引与说明
├── life-archive/                12 类人生档案、52 领域、134 字段
├── knowledge/                   可复用知识及主题模板
├── assets/                      文件资产清单和版本引用
├── candidates/                  新记忆候选与审核入口
├── collaboration/               多 Agent 分工、交接和验收
├── integrations/                平台接入、共享记忆与版本确认
├── workflows/                   记忆治理、研究、研发、写作流程
├── config/                      同步默认策略及工作区设置模板
├── ai_memory_hub/               本地归档、Vault、CLI 与治理引擎
├── schemas/                     数据格式与字段校验规则
├── docs/                        安装、操作、协议与多语言文档
│   └── i18n/                    英文及其他语言的 README
├── examples/                     可公开的合成样例
├── scripts/                      校验、测试和发行审计
├── tests/                        Windows/Linux 自动化回归
├── vendor/                       通用版依赖和来源关系说明
└── .github/workflows/            CI 测试与安全发行检查
```
**注意区分三个层次：**
- **产品仓库**：公开可复用的源码、空白模板、合成示例、测试和说明，不保存使用者的个人事实。
- **个人工作区 Workspace**：使用者初始化出的目录，包含 Agent 导航、个性化规则、档案模板、工作流及工作区设置。
- **本地 Vault**：独立的 SQLite 索引与按内容寻址的文件归档，存放经过授权的记忆修订和文件字节；与工作区分开，默认不进入 Git。
[19 模块能力对照](docs/workspace-parity.md) · [工作区初始化](docs/workspace.md) · [Vault 数据协议](docs/protocol.md)
---
## 五、如何接入和使用？
这是通用版比私人实例 README 更详细的部分。以下命令针对**已获得源码访问权限的 V2.3.0 版本**，Windows 可在 PowerShell 中执行，Linux/macOS 可在终端执行。示例里的路径只是合成演示，不应直接用真实资料替代。
### 1. 准备环境与安装
准备 Python **3.11 或更高版本**和可信的本地文件系统。获得本项目源码并进入仓库根目录后执行：
```sh
python --version
python -m pip install .
ai-memory-hub --help
```
提示：当前仓库尚为 Private，需要实际仓库权限才能获取源码。CLI 名称是 `ai-memory-hub`；若可执行命令未加入 PATH，可使用 `python -m ai_memory_hub`。生产环境建议使用独立虚拟环境并固定代码版本。
### 2. 初始化个人工作区和独立 Vault
```sh
ai-memory-hub workspace init --path ../my-hub
ai-memory-hub workspace check --path ../my-hub
```
这会在 Git 仓库外创建 `../my-hub/` 个人工作区及默认的同级 `../my-hub-vault/`。默认敏感级别为 `private`，**不授权任何数据源、不安装计划任务、不导入个人历史**。可选参数 `--vault PATH` 和 `--sensitivity LEVEL` 用于自定义目标目录和敏感等级。
初始化器拒绝覆盖已存在目录。请在信任的本地目录下创建工作区，勿把真实 Vault 放进公开 Git 仓库。首次使用从新工作区的 `AGENTS.md` 和 `core/INDEX.md` 开始。
### 3. 五分钟体验：完整合成数据闭环
建议首次体验选择**全新目录**。以下演示将建立工作区、加载一个经显式授权的合成来源，然后查看项目、候选、会话和文件状态：
```sh
ai-memory-hub workspace init --path ../hub-demo --demo
ai-memory-hub workspace check --path ../hub-demo
ai-memory-hub --root ../hub-demo-vault source grant sample normalized --path ../hub-demo/demo-inbox --consent
ai-memory-hub --root ../hub-demo-vault local run --source sample
ai-memory-hub --root ../hub-demo-vault local status
ai-memory-hub --root ../hub-demo-vault memory review
ai-memory-hub --root ../hub-demo-vault project list
ai-memory-hub --root ../hub-demo-vault session list
ai-memory-hub --root ../hub-demo-vault asset check calibration-notes
```
`--demo` 只复制合成输入材料；真正读取它们仍需 `source grant ... --consent`。重复执行 `local run` 时，相同内容应返回未变化状态，不会复制一份新的记忆修订。**候选默认仍是候选**，不是已经审核激活的正式事实。
[合成入门及预期结果](docs/workspace.md#synthetic-onboarding)
### 4. 建立自己的资料结构
初始化完成后，可按实际需要填写 `core/` 规则、`projects/` 模板和 `life-archive/profile.json`。人生档案的 12 个大类起初全是 `unknown`；使用 `workspace check` 检查字段覆盖、来源与敏感度等，不需要在初次安装时提供所有资料。
保存敏感内容前先确定是否有必要、是否拥有读取来源的权限，以及它应该留在私有工作区还是限制访问的 Vault。
```sh
ai-memory-hub workspace check --path ../my-hub
ai-memory-hub workspace facts --path ../my-hub --consent
```
`workspace facts` 只投影当前已经**正式接受**的记忆，不会替用户自动创建 Git 提交或远端 Pull Request。
### 5. 接入获准的数据源
来源目录需要使用受支持的清单/导出格式，并且由使用者主动选择。对于一个包含 `memory-hub.json` 的本地目录，先授权再运行：
```sh
ai-memory-hub --root ../my-hub-vault source grant work normalized --path APPROVED_INBOX --consent
ai-memory-hub --root ../my-hub-vault local run --source work
ai-memory-hub --root ../my-hub-vault local status
```
`APPROVED_INBOX` 是需要替换的本地路径。ChatGPT 历史需先按官方流程**自行下载**兼容的 JSON/ZIP，再选择 `chatgpt_export` 适配器并授予本地路径；L3 可见原文必须另行使用显式原文授权，附件需单独登记。没有任何“自动监听所有 AI 对话”的默认功能。
[数据源适配器](docs/adapters.md) · [本地部署](docs/deployment.md)
### 6. 审核和激活一条长期记忆
使用真实的候选 ID、当前修订和审批人替换下列示意值，先对照命令返回的审核建议及证据：
```sh
ai-memory-hub --root ../hub-demo-vault candidate suggest CANDIDATE_ID --consent
ai-memory-hub --root ../hub-demo-vault candidate advance CANDIDATE_ID validated --base 0 --record-revision 1 --actor reviewer --reason "Source checked" --consent
ai-memory-hub --root ../hub-demo-vault candidate advance CANDIDATE_ID review --base 1 --actor reviewer --reason "Peers checked" --consent
ai-memory-hub --root ../hub-demo-vault candidate advance CANDIDATE_ID approved --base 2 --actor reviewer --reason "Owner approved" --evidence-verified --consent
ai-memory-hub --root ../hub-demo-vault candidate advance CANDIDATE_ID active --base 3 --actor reviewer --reason "Activate approved memory" --consent
ai-memory-hub --root ../hub-demo-vault candidate history CANDIDATE_ID --consent
```
这是**无重复或冲突的首次候选**的流程示例；实际审批如有同键记录，必须按建议补充准确的 `--ack-peer ID@REV`、`--supersede ID@REV`，否则会拒绝变更。审批与激活分开进行，不能因为模型自述“我认为已验证”就略过真实证据核查。
[审核流程与所有分支状态](workflows/memory-lifecycle.md)
### 7. 让另一个 Agent 检测并确认共享记忆版本
先由拥有者从 Vault **仅选取已经正式接受并获准共享的记忆**生成本地快照，再经单独批准的渠道交给接收方。接收端使用自己持有的 Vault 和实际得到的快照路径：
```sh
ai-memory-hub --root OWNER_VAULT version snapshot --name checkpoint-01 --include rules=MEMORY_ID --consent
ai-memory-hub --root RECEIVER_VAULT version check --channel shared --agent agent-b --snapshot APPROVED_JSON --consent
ai-memory-hub --root RECEIVER_VAULT version reload --channel shared --agent agent-b --scope rules --consent
ai-memory-hub --root RECEIVER_VAULT version confirm --channel shared --agent agent-b --sha DETECTED_SHA --receipt READ_RECEIPT --consent
```
`OWNER_VAULT`、`RECEIVER_VAULT`、`MEMORY_ID`、`APPROVED_JSON`、`DETECTED_SHA` 和 `READ_RECEIPT` 均为需要替换的操作值。只在 Agent 实际阅读返回的范围后确认；所有变化范围被确认之前，`synced_sha` 不会推进。回执不等于跨平台原生记忆已自动同步。
[完整版本检测协议](integrations/memory-bootstrap.md)
### 8. 授权交接项目与指定文件版本
交接是显式操作，`handoff` 开关默认关闭。发送方可生成包含项目上下文和**单独勾选的文件版本**的离线包；接收方应先审查范围、权限和传输渠道：
```sh
ai-memory-hub --root ../hub-demo-vault config set handoff on
ai-memory-hub --root ../hub-demo-vault transfer pack --project greenhouse-demo --asset calibration-notes@1 --consent
ai-memory-hub --root RECEIVER_VAULT config set handoff on
ai-memory-hub --root RECEIVER_VAULT transfer receive --input APPROVED_COPY.zip --consent
ai-memory-hub --root RECEIVER_VAULT transfer inspect PACKAGE_ID --consent
ai-memory-hub --root RECEIVER_VAULT transfer file PACKAGE_ID calibration-notes@1 --consent
```
接收方 Vault 需先独立初始化，`APPROVED_COPY.zip` 指发送方实际生成、经审核后安全传递的文件，`PACKAGE_ID` 从 `receive` 结果获取。**交接 ZIP 不加密**，SHA-256 能检验字节完整性，不能证明发件人身份；L3 原文与未授权的文件默认不外发。
[完整交接和恢复说明](docs/deployment.md)
### 9. 五种同步开关、维护和恢复
| 开关 | 普通模式默认 | 含义 |
| --- | --- | --- |
| `weekly` | 开 | 每周归档入口，不自动安装系统定时任务 |
| `full` | 开 | 用户主动触发的全量或指定来源导入 |
| `event` | 关 | 明确触发且获准的事件 |
| `daily` | 关 | 可选的每日补漏调用 |
| `handoff` | 关 | 主动交接项目与文件版本 |
可用 `config set FEATURE on|off` 管理；**开关打开不是“已经在后台运行”**。通过 `local status` 分别检查授权源、实际执行和 `scheduler` 状态。升级时先停止写入，再备份成对的工作区与 Vault、校验恢复副本后进行测试，不直接用新旧运行时同时打开同一数据库。
[使用与故障排查](docs/guide.md) · [备份、恢复、升级](docs/deployment.md)
### 10. 对开发者和维护者
本项目保留 V2.2 的 Vault 记录协议 `2.1`，V2.3 工作区格式为 `1.0`，离线交接包采用 `2.2` 格式。代码和数据是分开的：贡献源码或提 PR 时，**不要提交真实个人档案、聊天导出、Vault 数据库、附件和访问令牌**。
```sh
python -m pip install jsonschema
python -m unittest discover -s tests -v
python scripts/smoke_release.py
python scripts/smoke_v22.py
python scripts/smoke_workspace.py --installed
python scripts/check_readme_i18n.py
```
运行已安装 CLI 的冒烟脚本前，应先执行 `python -m pip install .`。CI 在 Windows、Ubuntu 复核程序及公开合成示例；它不能代替用户真实设备和外部平台的独立接入验收。
---
## 六、隐私、安全和控制权
- **用户决定存什么、让谁读、什么时候修改**。来源导入、L3 原文、外发文件和共享记忆均有独立边界。
- **产品仓库不等于个人资料仓库**。本仓库模板仅包含结构与合成数据。个人工作区和 Vault 默认分离，不能因为将来开源就自动公开使用者资料。
- **本地 Vault 依赖操作系统访问权限和磁盘加密**。程序自身不加密 Vault；跨设备交接 ZIP 也不加密。
- **内容敏感度标签不等于文件系统 ACL**。对不同接收主体应使用独立 OS 权限、账号或存储边界。
- **撤销来源授权只停止未来读取**。已经保存的历史修订不会因此自动删除；删除一个 Git 文件也不意味着清除整个 Git 历史。
- **不能把推断当事实**。记录来源、日期和证据状态；正式记忆须经过验证、审批与单独激活。
- **不假设跨平台能力**。任何 AI 能否读取本地文件、远端仓库和新快照，均要以真实权限和执行结果为准。
- **不误报自动化**。没有部署的调度器、未执行的备份恢复、未覆盖的原始健康导入，不应写成已自动完成。
[安全声明](SECURITY.md) · [授权与边界](core/boundaries.md) · [记忆治理](workflows/memory-lifecycle.md)
---
## 七、当前建设状态与边界
截至 **2026-11-19**，V2.3.0 已完成以下工程能力，并通过合成数据验收：
| 模块或事项 | 当前状态 |
| --- | --- |
| **19 个通用工作区模块** | 已模板化，可按用户分别初始化 |
| **12 类 / 52 领域 / 134 字段人生档案** | 分类、注册表和校验已实现，默认无真实资料 |
| **L0–L3 会话、版本文件归档与 Vault** | 已实现；敏感原文与来源读取需额外授权 |
| **候选记忆治理和历史版本** | 验证、建议、审批、单独激活、撤销及追溯已实现 |
| **跨 Agent 快照与重读确认** | 已实现，但只适用于经授权交付的快照与接收端 |
| **离线项目交接和文件版本取回** | 合成测试已通过，不是云端实时同步 |
| **Windows / Ubuntu、ZIP / Bundle 发行审计** | 工程验收已通过 |
| **真实用户数据接入、自动归档定时任务** | 不默认启用，需用户另外配置和验证 |
| **健康原始数据同步** | 未作为通用功能实现；仅支持去标识化汇总校验 |
| **GitHub 公开仓库与正式 2.3.0 Release** | 尚未发布；当前仓库为 Private |
项目完整性与安全边界详见 [19 模块覆盖矩阵](docs/workspace-parity.md)、[安全说明](SECURITY.md)及 [GitHub Actions](.github/workflows/test.yml)。**合成环境测试通过不能替代真实来源授权或某个 AI 平台的实际接入确认。**
---
## 八、长期目标
**让个人记忆从不同 AI 平台内部零散、不可直接迁移的摘要，转变成用户真正拥有、跨工具可用、持续修订且可验证的长期数字资产。**
AI Memory Hub 不追求记录所有聊天，不以“存得越多”作为成功指标。它更重视：
**保存方向清晰、来源证据可靠、历史能够回溯、更新经过审核、使用遵守权限，并且在 AI 工具变化后仍能够继续使用。**
