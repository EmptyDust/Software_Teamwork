# 仓库维护设置

本文档面向仓库维护者，记录需要在 GitHub 远端仓库配置的保护规则。文档和
workflow 只能拦截 PR 行为；分支保护和 label 仍需要维护者在 GitHub 仓库中
配置。

## 可选 Label

```text
L1nggTeam
PrimeTeam
JerryTeam
frontend
backend
documentation
ci
deployment
trellis
service:gateway
service:auth
service:file
service:qa
service:knowledge
service:document
service:ai-gateway
blocked
```

检查现有 label：

```bash
gh label list --repo Sakayori-Iroha-168/Software_Teamwork
```

## develop 分支保护

`develop` 是日常集成分支，必须通过 PR 合入。

推荐在 GitHub 页面配置：

- Require a pull request before merging
- Require approvals，至少 1 人
- Require status checks to pass before merging
- Require branches to be up to date before merging
- Include administrators，按团队管理要求决定是否启用
- Restrict who can push to matching branches，禁止普通成员直接 push

建议作为 required checks 的 workflow：

- `PR Guard`
- `Commitlint`
- `CI`

如果使用 `gh api` 配置，需要先确保对应 checks 至少运行过一次，再按实际
check 名称补入 `contexts`。

`Auto Label` 负责根据提交账号和修改路径给 PR 自动添加 label。它不是合并
门禁，不建议加入 required checks。

## GitHub Project 自动同步

[.github/workflows/task-issue-sync.yml](../../.github/workflows/task-issue-sync.yml)
会在任务 issue 创建、编辑或重新打开时自动执行：

- 识别标题形如 `[A-001] ...`、`[B-001] ...`、`[C-001] ...`、`[F-001] ...` 或 `[S-001] ...`，且正文写明
  `GitHub Project：Software Teamwork` 的任务 issue。
- 根据 issue 标题前缀强制同步 `Group`，并根据任务正文的 `优先级`、
  `批次`、`模块`、`Risk`、`依赖任务` 同步 GitHub Project 字段。
- 根据任务正文的 `依赖任务` 和 `阻塞任务` 写入 GitHub Issue 原生
  relationship；`并行任务` 只保留在正文中，不创建 blocking relationship。
- 根据主责小组和模块自动补可用 label；当前 `L1nggTeam`、`JerryTeam`、`PrimeTeam`
  会作为小组 label，`Frontend` 和 `Special` 只同步为 Project `Group`，通常通过
  `frontend`、`ci`、`deployment`、`service:<name>` 等模块 label 标记。仓库不存在的
  label 会跳过并在日志中提示。
- 同步成功后把正文中的 `Project sync` 改为 `synced`；同步失败则改为
  `blocked`，并将本次 workflow run 标记为失败，方便维护者发现权限问题。

新任务 issue 默认使用 [.github/ISSUE_TEMPLATE/issue.md](../../.github/ISSUE_TEMPLATE/issue.md)。
模板标题采用 `[F-001] 中文任务标题` 格式，并内置任务前缀和模块枚举，
以便 Task Issue Sync 识别和同步 Project 字段。

GitHub user-level Projects v2 通常需要额外 token。维护者应创建一个有 Project
读写权限的 fine-grained token 或 classic token，并在仓库 Secrets 中配置：

```text
PROJECTS_TOKEN
```

Issue label、Assignee 和正文更新仍使用默认 `GITHUB_TOKEN`，`PROJECTS_TOKEN`
只用于 GitHub Project GraphQL 调用。如果未配置该 secret，workflow 会先尝试使用
`GITHUB_TOKEN`；若 GitHub 拒绝访问 user Project，则 issue 仍会完成 label 同步，
但 Project 字段会保持未同步。

## Issue 认领自动化

[.github/workflows/task-claim.yml](../../.github/workflows/task-claim.yml)
会在 issue 评论创建时识别以下格式：

```text
认领：@your-github-login
```

规则：

- 只能认领自己，评论中的用户名必须等于评论者 GitHub login。
- `Blocked`、`Review`、`Done` 状态的任务不能直接认领，需要协调人先改为
  `Draft` 或 `Ready`。
- issue 已有其他 Assignee 时不会覆盖，会评论提示先完成交接。
- 认领成功后自动把评论者设为 Assignee。
- 若正文包含任务模板字段，会把 `状态` 从 `Draft` 或 `Ready` 改为
  `In Progress`，并把 Project `Status` 同步为 `In Progress`。
- 若 Project 同步成功，正文中的 `Project sync` 会写为 `synced`；同步失败会写为
  `blocked`，并将本次 workflow run 标记为失败，此时维护者需要检查
  `PROJECTS_TOKEN`。

## main 分支保护

`main` 不是日常开发 PR 目标。普通开发和文档修改只能 PR 到 `develop`。

推荐规则：

- Restrict who can push to matching branches，仅允许发布维护者或发布机器人更新
- Require status checks to pass before updating
- Require linear history
- 禁止普通成员直接 push

发布方式由维护者执行，可以是受限账号将 `develop` 合并到 `main`，也可以是
后续增加专门的 release workflow。不要让普通成员向 `main` 发起日常开发 PR。

## PR Guard 规则

[.github/workflows/pr-guard.yml](../../.github/workflows/pr-guard.yml) 会检查：

- PR base 必须是 `develop`
- PR head 必须来自个人 fork
- PR 分支必须包含当前最新 `develop`
- PR 标题不能包含中文字符
- PR 描述必须包含中文内容
- PR 描述的 `修改内容`、`关联 Issue`、`验证`、`已知风险` 不能保留模板占位文本
- `关联 Issue` 必须填写 GitHub 自动关闭关键字，例如 `Closes #118`；如果没有
  关联 issue，必须填写 `无。原因：...`，不能只写 `无`

## Auto Label 规则

[.github/workflows/auto-label.yml](../../.github/workflows/auto-label.yml) 会读取
[.github/labeler.json](../../.github/labeler.json)，并按两类规则给 PR 添加 label：

- `accountLabels`: GitHub 账号 login 或数字 ID 到 label 的映射，匹配 PR
  发起人以及 PR commit 的 GitHub author/committer
- `pathLabels`: 文件路径 glob 到 label 的映射

此外，workflow 会把 PR 的 `blocked` label 同步为关联 issue 的阻塞状态：

- 关联 issue 以 GitHub 的 PR closing issue references 为准，也就是 PR 描述中的
  `Closes #118`、`Fixes #119`、`Resolves #120` 等自动关闭关键字。GraphQL 查询失败时，
  workflow 才退回解析 `关联 Issue` 区块。
- PR 至少有一个关联 issue，且所有关联 issue 都处于阻塞状态时，才会添加
  `blocked` label。
- 只要任意关联 issue 不阻塞、已关闭、不可读取，或 PR 没有关联 issue，就会移除
  PR 上的 `blocked` label。
- 任务 issue 的阻塞状态以正文 `状态：Blocked` 或 `Risk：Blocked` 为准；如果正文已经改成
  非阻塞，即使遗留了 `blocked` label，也不会继续阻塞 PR。非任务 issue 没有这些正文
  字段时，才用 issue 自身的 `blocked` label 兜底。修改 issue 正文、label、关闭或重新
  打开 issue 时，会自动反查打开的关联 PR 并重新同步。

示例：

```json
{
  "accountLabels": [
    {
      "accounts": ["username", "12345678"],
      "labels": ["L1nggTeam"]
    }
  ],
  "pathLabels": [
    {
      "paths": ["apps/web/**"],
      "labels": ["frontend"]
    },
    {
      "paths": ["services/knowledge/**", "docs/services/knowledge/**"],
      "labels": ["service:knowledge"]
    }
  ]
}
```

服务实现目录和对应服务文档目录应使用同一个 `service:<name>` label。例如，
`services/knowledge/**` 和 `docs/services/knowledge/**` 都会添加
`service:knowledge`。

workflow 只添加仓库中已经存在的 label。新增小组或领域 label 后，需要先在
GitHub 仓库创建 label，再更新 `.github/labeler.json`。

## Commitlint 规则

[.github/workflows/commitlint.yml](../../.github/workflows/commitlint.yml) 会检查每个
PR commit 的第一行是否符合 Conventional Commits：

```text
<type>(<scope>): <subject>
```

允许的 type：

```text
feat, fix, docs, style, refactor, test, chore, perf, revert
```

## 维护者日常检查

```bash
gh pr list --repo Sakayori-Iroha-168/Software_Teamwork --base develop
gh pr checks <PR_NUMBER> --repo Sakayori-Iroha-168/Software_Teamwork
gh pr view <PR_NUMBER> --repo Sakayori-Iroha-168/Software_Teamwork --json baseRefName,headRepositoryOwner,headRefName,labels
```

发现 PR 目标分支、来源仓库或 commit 不符合规范时，不要合并。要求
contributor 修正后再 review。
