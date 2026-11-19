# 用 Agent 建立个人 AI Memory Hub

V2.4 命令行可以预览首次部署计划、建立仅属主可访问的工作区及独立 Vault、导入获准材料并报告实际结果。创建远端仓库和发布各有单独的授权步骤。先阅读[数据与权限边界](../core/boundaries.md)。

## 1. 生成首次部署计划

1. 在已获准的源代码检出中，用 Python 3.11 或更新版本安装。为工作区与 Vault 选两个互不嵌套的新目录，避开所有 Git 工作树，且父目录已经存在。恢复先前部署时沿用已经绑定的路径。
2. 把[空白请求模板](../examples/onboarding-request.json)复制到仅自己可访问的本地目录，按[请求与结果 Schema](../schemas/onboarding.schema.json)填写副本。相对路径从请求文件所在目录解析。省略 `vault` 时使用名称带 `-vault` 的同级目录，默认敏感度为 `private`。
3. 清单只列用户实际选定的本地路径。每项填写唯一且稳定的 `id`、`adapter`、`path` 和 `authorized`。用户明确批准读取并归档该来源后才填 `authorized: true`。`allow_raw` 可省略，默认关闭。在 `private` 或 `restricted` Vault 中保存获准的可见 L3 消息时，再单独确认 `allow_raw: true`。首次只建空库时，保留空的 `sources`。
4. 如需规划可选的 GitHub 私有仓库，加入 `"github": {"target": "OWNER/NAME", "visibility": "private"}`。这一步仅登记目标。创建和发布各自确认。

```sh
python -m pip install .
ai-memory-hub onboarding plan --request hub-request.json
```

读取 JSON 中的 Markdown 摘要和 `plan_digest`。计划只读检查当前运行环境、已选路径及工具能力，标明不可用来源。请用户集中核对属主、资料保留规则、拟读取范围和落盘位置。

## 2. 应用已批准的计划

```sh
ai-memory-hub onboarding apply --request hub-request.json \
  --approve-plan APPROVED_PLAN_DIGEST --consent
ai-memory-hub onboarding report --request hub-request.json \
  --markdown /path/to/approved/workspace/first-run.md > first-run.json
```

命令中的摘要替换成实际批准值。报告默认向标准输出写 JSON。使用 `--markdown` 时选已绑定工作区内尚不存在的文件。初始化受阻时省略 `--markdown`，直接读取 JSON 失败报告。两种报告均在本地妥善保存。路径含空格时加引号。示例使用 POSIX 续行符 `\`，在 PowerShell 中可用单行命令或反引号续行。
某个来源失败时可以保留其他已完成的数据。`apply` 和 `report` 退出码 0 表示完成，1 表示部分完成、受阻或失败，具体原因在 JSON 中。输入或批准有误时退出 2。先看各来源结果和受影响条目，再补齐缺失路径、修正清单或解决修订冲突，重新检查计划并运行。计划变化后重新批准新摘要。同一来源重跑时保留旧版，使用既有成功回执识别未变化项。遇到未绑定的已有目录，核对状态后选择新目录或按恢复流程处理。

## 3. 准备获准的来源

| 适配器 | 选定输入 |
| --- | --- |
| `normalized`、`codex_workspace`、`local_checkpoint` | 含 `memory-hub.json` 的目录。清单仅用相对路径列出获准的文件、链接及规范记录 |
| `chatgpt_export` | 含支持的会话分片的官方本地 ZIP，或提取后仅含已获授权会话的 JSON |
| `life_profile`、`life_timeline` | 符合工作区人生档案 Schema 和字段注册表的单个获准 JSON 文档 |

Agent 可以把自己实际可读的资料整理成规范化清单。平台没有可用导出或授权连接时，将其标记不可用，并由用户提供明确授权的本地检查点。[来源适配器及覆盖范围](adapters.md)

获准的本地检查点目录可在 `sources` 中登记为下列形式。路径相对请求文件，原文导入保持关闭。

```json
{
  "id": "checkpoints",
  "adapter": "local_checkpoint",
  "path": "./owner-selected-intake",
  "authorized": true,
  "allow_raw": false
}
```

- **会话和项目**。L0 保存实际索引、L1 保存已有摘要、L2 保存带证据的目标、决策、结果与下一步。L3 需单独许可。ChatGPT 导出适配器会保留摘要与检查点的缺口，附件仍按文件单独授权。
- **长期记忆**。先录入候选，核查重复或冲突，审批证据后单独激活。推断和证据不足的内容留在候选。[候选查重、审批和激活命令](../workflows/memory-lifecycle.md)
- **文件与链接**。清单键和资产 ID 保持稳定。用户上传件标为 `user_upload`，AI 生成件标为 `ai_generated`。可按精确版本回读字节并检查 SHA-256。只有 URL 时保留为外部引用。
- **人生档案**。使用现有 12 类、52 个领域和 134 个字段。仅填有真实证据的结构化值，缺失信息保持 `unknown`。[字段说明](../life-archive/README.md)

## 4. 预览独立 Git 投影

在工作区、Vault 和 Git 工作树之外选择独立输出目录。默认预览包含中立的 19 模块骨架和汇总计数。要从默认 `private` Vault 分享内容，先创建本地 UTF-8 JSON 审阅文件，填写真实来源 ID 和当前修订，另写脱敏内容和可分享别名。以下值为合成示例。

```json
{
  "format": "1.0",
  "target": "owner/example-private-repo",
  "items": [
    {
      "kind": "memory",
      "id": "verification-rule",
      "source": {"id": "accepted-local-rule", "revision": 2},
      "purpose": "reference",
      "data": {"key": "验证规则", "claim": "验收结论须有实际检查记录。"}
    },
    {
      "kind": "project",
      "id": "instrument-review",
      "source": {"id": "local-project", "revision": 1},
      "purpose": "continuity",
      "data": {"title": "仪器复核", "summary": "待记录第二次读数。"}
    },
    {
      "kind": "session",
      "id": "second-reading",
      "source": {"id": "local-session", "revision": 1},
      "purpose": "navigation",
      "data": {"title": "第二次读数", "project": "instrument-review"}
    }
  ]
}
```

```sh
ai-memory-hub projection preview --workspace WORKSPACE \
  --output NEW_PROJECTION
ai-memory-hub projection review --workspace WORKSPACE --input REVIEW.json
ai-memory-hub projection approve --workspace WORKSPACE --input REVIEW.json \
  --digest REVIEW_SHA256 --confirm-redacted --consent
ai-memory-hub projection preview --workspace WORKSPACE --output NEXT_PROJECTION \
  --review-digest REVIEW_SHA256 --previous NEW_PROJECTION
```

在本地逐项核对来源修订、用途、脱敏文字和 Private 接收仓库，用户确认后才记录审阅摘要。记忆必须已接受且有事实、规则或偏好分类，存在冲突时先处理候选。项目或会话可用 `checkpoint` 提供脱敏的 `goal`、可选 `decisions` 和 `next_actions`。会话的 L1 摘要和 L2 检查点要求原记录有对应层，关联项目别名必须指向同一审阅中实际对应的项目。

获审资料分别进入 `memory/reviewed.json`、`projects/index.json` 和 `sessions/index.json`。原始来源 ID 和定位符留在本地。最终逐文件预览会给出另一个投影 SHA-256 和差异，发布要单独批准该摘要。来源修订或脱敏文本变化后须重新审阅。审阅输入和输出只能留在本地。内置过滤可识别常见敏感格式，普通文字中的个人细节仍由用户核对。凭据、私有路径、L3、附件和 Vault 保持本地隔离。已有 `public` Vault 可在另一份预览中继续使用 `--select ID` 与 `--asset ID@REV`。

## 5. 可选创建和发布到 GitHub 私有仓库

使用工作区已应用计划中记录的 GitHub 目标。确认用户批准了账号、仓库名和对应操作，再使用已获授权的 GitHub CLI。凭据由现有认证机制管理。

```sh
ai-memory-hub repo probe --target OWNER/NAME
ai-memory-hub repo create --workspace WORKSPACE \
  --target OWNER/NAME --consent
ai-memory-hub repo publish --workspace WORKSPACE --target OWNER/NAME \
  --repository-id VERIFIED_REPO_ID --projection REVIEWED_PROJECTION \
  --digest APPROVED_SHA256 --consent
```

内置创建入口适用于 github.com 上当前登录的个人账号。组织账号或缺少 `gh` 的场景，可走获准的 GitHub 集成或网页创建全新空的 Private 仓库并核对可见性。手动发布时，只在独立 Git 历史中暂存获审的投影文件。发布前通过哈希核对暂存文件，发布后验证远端引用和可见性，并留存手动回执。内置发布器会审核自身协议建立的历史，可能拒绝接管手动初始化或经过改写的提交历史。

发布前核对用户批准的目标和投影摘要。私有审阅资料还要求提供 `repo create` 或 `repo probe` 返回的数字 `repository_id`。创建命令先保留一个空 Private 仓库。首次获准发布时，用清单初始化分支，再提交 19 模块骨架和获审资料。中断后用同一摘要重试。若只发布了清单且原来源已变化，重新审阅后用 `--base-sha` 钉住该清单提交并批准新摘要。其他更新用 `repo probe` 核实到的 `base_commit`。只有用户明确同意创建 PR、远端也已有完整发布基线时，才加 `--pr`。保留原 Vault 用于核对私有发布历史，记录实际返回的私有状态、提交和 PR 回执。工具或权限不可用时保留本地结果，报告远端受阻。

## 6. 交付与持续维护

报告应包含实际范围、版本、执行记录、资料缺口及待授权事项。用户未要求的步骤记为 `not_requested`，无权限的记为受阻，无法证实的记为 `not_verified`。把 JSON、可读报告和最少量的待补事项一起交给用户。

```sh
ai-memory-hub --root VAULT local status
ai-memory-hub --root VAULT local run --source APPROVED_ID
ai-memory-hub --root VAULT asset check ASSET_ID --version REV
```

来源路径改变或授权收窄时，先暂停已有调度。用 `source revoke ID` 撤销旧授权，再审查新计划并批准替代来源。撤销保留已归档的历史版本。冲突按当前修订核对后，仅重试受影响的获准来源。

普通模式启用每周和按需全量，事件、每日和交接默认关闭。使用 `local status` 查看来源和最近结果。实际归档回执、远端提交、接收 Agent 的 `detected_sha` 与 `synced_sha` 分别核对。[逐 Agent 读取与确认](../integrations/memory-bootstrap.md) 与[备份、恢复和定时任务指南](deployment.md)提供原有命令。调度需另行批准，在真实执行后核对系统记录及归档回执。
