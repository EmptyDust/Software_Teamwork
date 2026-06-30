# 任务 Issue 与 Project 流程

本文档说明如何把一个待办事项写成标准任务书、发布为 GitHub Issue，并通过
Task Issue Sync 自动同步到 GitHub Project `Software Teamwork`。任务正文格式见 [标准任务书模板](task-brief-template.md)，仓库维护配置见
[仓库维护设置](repository-settings.md)。

## 适用范围

本流程适用于协调人、组长或 AI 把文档缺口、实现缺口、联调问题拆成可分发任务。

注意：

- GitHub Issue / Project 是团队任务派发和追踪载体。
- Trellis task / PRD 只用于本地 AI 开发上下文，不用于公开任务派发。
- 发布 GitHub 任务时，不创建 `.trellis/tasks/`，不调用 `.trellis/scripts/task.py create/start/add-context/archive`。
- 本地草稿只用于校对；校对完成后必须创建或更新 GitHub Issue。

## 总流程

1. 查 GitHub 当前状态基线，避免重复建任务。
2. 判断任务归属，选择编号前缀。
3. 按模板写完整任务书正文。
4. 补齐 `依赖任务`、`阻塞任务`、`并行任务` 和 `依赖原因`。
5. 逐张校对任务书。
6. 先发布上游任务，再发布下游任务。
7. 等待 Task Issue Sync 自动加入 Project、同步字段和更新 `Project sync`。
8. 回填依赖 issue 编号，确认 `Project sync` 为 `synced`。

## 1. 查询当前状态基线

创建或更新任务前，先查询 GitHub 远端状态。GitHub Issue / Project 是任务事实来源；
不要用本地草稿覆盖已经进入 `In Progress`、`Review`、`Done`、closed 或已有 assignee
的远端任务。

常用命令：

```bash
gh issue list --repo Sakayori-Iroha-168/Software_Teamwork --state all --limit 200
gh issue list --repo Sakayori-Iroha-168/Software_Teamwork --state all --search "<任务编号或关键词>" --limit 50
gh issue view <number> --repo Sakayori-Iroha-168/Software_Teamwork --json number,title,state,labels,assignees,body,closedAt,url
```

需要记录的基线：

| 任务编号 | Issue | GitHub 状态 | Project 状态 | Assignee | Linked PR | 对本次动作的影响 |
| --- | --- | --- | --- | --- | --- | --- |
| `S-001` | `#156` | open | In Progress | `@user` | `#180` | 不新建；如需补充，只评论或更新原 issue。 |

判断规则：

- 同编号或同范围 Issue 已存在时，更新原 Issue，不新建重复 Issue。
- Issue 已关闭且覆盖当前缺口时，不重新创建，只记录为已完成或无需新增。
- Issue 已关闭但当前缺口是新范围时，创建 follow-up，并在正文中引用旧 Issue。
- Issue 已有 assignee、处于 `In Progress` 或 `Review` 时，不拆出同范围并行任务。
- Issue 处于 `Blocked` 时，优先更新阻塞原因和依赖关系。

## 2. 选择编号和主责小组

任务编号前缀决定 Project `Group` 和对应 View。Task Issue Sync 会根据标题前缀自动同步
`Group`，Project View 由 `Group` 字段筛选，不需要手动放入 View。

| 前缀 | 主 View | Project `Group` | 默认主责 | 典型范围 |
| --- | --- | --- | --- | --- |
| `A-*` | `Platform View` | `L1nggTeam` | 平台底座与知识管理 | `knowledge`、知识库、文档处理、检索。 |
| `B-*` | `QA View` | `JerryTeam` | 智能问答 | `qa`、会话、消息、RAG、引用、SSE。 |
| `C-*` | `Report View` | `PrimeTeam` | 报告生成 | `document`、模板、材料、报告任务、导出。 |
| `F-*` | `Frontend View` | `Frontend` | 前端横向小队 | `apps/web/` 页面、路由、API client、前端联调。 |
| `S-*` | `Special View` | `Special` | 专项 | OpenAPI、`gateway`、`auth`、`file`、`ai-gateway`、CI/CD、部署、联调。 |

编号规则：

- 新任务标题使用 `[A/B/C/F/S-001]` 这类编号格式，数字为字母组内部顺序编号。
- 每个字母组独立从 `001` 起三位补零递增；创建新任务前先查询同前缀已有最大编号。
- Issue 标题和正文都使用中文，标题格式为 `[F-001] 中文任务标题`。

优先级建议：

| 优先级 | 使用场景 |
| --- | --- |
| `P0` | 不做会阻塞开发、联调、契约对齐或导致文档与代码明显冲突。 |
| `P1` | 本轮业务闭环需要，但不阻塞其他人起步。 |
| `P2` | 演示质量、管理能力、体验增强或后续优化。 |

## 3. 编写任务书

每个任务必须是一份独立 Issue 正文。不要把多个任务合并到一个 Issue，也不要只发任务清单。

最低要求：

- 使用 [标准任务书模板](task-brief-template.md)。
- 只设置 1 名主责人；认领前不预分配 Assignee。
- `任务信息` 字段完整，尤其是 `状态`、`主责小组`、`优先级`、`批次`、`模块`、`Risk`、`GitHub Project`、`Project sync`。
- `权威依据` 指向具体公开文档、implementation 文档、GitHub issue 或 PR。
- `任务范围`、`交付物`、`验收标准` 一一对应。
- `边界与不做内容` 写清楚，避免和相邻任务重复。

初始状态通常这样填：

```markdown
- 状态：`Ready`
- Risk：`Normal`
- GitHub Project：`Software Teamwork`
- Project sync：`pending`
```

需要协调人确认时：

```markdown
- 状态：`Draft`
- Risk：`Needs Decision`
```

依赖未满足时：

```markdown
- 状态：`Blocked`
- Risk：`Blocked`
```

## 4. 完善依赖关系

任务正文必须同时写清：

- `依赖任务`：当前任务开始前必须完成或至少稳定输出的任务。
- `阻塞任务`：当前任务完成后会解锁的下游任务。
- `并行任务`：可以并行推进但需要同步契约的任务。
- `依赖原因`：写具体接口、schema、数据结构、环境变量、服务能力或验收条件。

所有依赖字段优先使用 GitHub issue 引用，例如 `#118 #125`；没有则写“无”。上游 Issue
尚未创建时，可以先写任务编号，等拿到 issue number 后再回填。

基础依赖方向：

```text
S 契约/专项
  -> A 平台底座
    -> B 智能问答
    -> C 报告生成
  -> F 前端横向
```

常见依赖规则：

| 上游缺口 | 下游缺口 | 处理方式 |
| --- | --- | --- |
| OpenAPI、schema、错误 envelope、鉴权、分页、SSE 不清 | 后端实现、前端接入、测试 | 先建 `S-*` 契约确认任务，下游 `依赖任务` 指向它。 |
| Auth identity、role、permission、session/token 缺失 | Gateway、QA、Report、前端鉴权 | 下游依赖对应 `S-*` 或 `A-*` Auth/Gateway 任务。 |
| Gateway route、envelope、转发缺失 | 前端真实 API 接入 | 前端可先并行做 mock；真实联调必须依赖 Gateway 任务。 |
| File reference、上传、读取、对象存储适配缺失 | Knowledge、Document/Report | 下游依赖 File contract 或实现任务。 |
| Knowledge retrieval、chunk、citation source 缺失 | QA、Report、前端检索页 | 下游依赖 retrieval response 任务。 |
| AI Gateway chat、embedding、rerank 缺失 | Knowledge embedding、QA RAG、Report 生成 | 下游依赖 `S-*` AI Gateway 任务。 |
| 数据库 migration 缺失 | repository、service、handler | 业务实现依赖 migration，或把 migration 写进同一任务的第一项。 |
| 联调环境、`.env.example`、部署脚本缺失 | 演示、端到端验收 | 演示或验收任务依赖 `S-*` 联调部署任务。 |

回填顺序：

1. 先创建上游任务。
2. 拿到上游 issue number。
3. 在下游任务的 `依赖任务` 写 `#上游编号`。
4. 在上游任务的 `阻塞任务` 写 `#下游编号`。
5. 如果两个任务可以并行推进，在双方或相关任务中写 `并行任务`。
6. 如果出现循环依赖，拆出更小的 `S-*` 契约确认任务。

## 5. 发布 Issue

建议先把任务正文写入临时文件，例如 `/tmp/task-body.md`，校对后再发布：

```bash
gh issue create \
  --repo Sakayori-Iroha-168/Software_Teamwork \
  --title "[S-001] 对齐引用字段契约" \
  --body-file /tmp/task-body.md
```

更新既有任务：

```bash
gh issue edit <number> \
  --repo Sakayori-Iroha-168/Software_Teamwork \
  --body-file /tmp/task-body.md
```

发布顺序：

1. 先发布 `S-*` 契约、AI Gateway、联调部署、CI/CD 等上游专项任务。
2. 再发布 `A-*` 平台底座和 Knowledge 任务。
3. 再发布 `B-*` QA 和 `C-*` Report 任务。
4. 最后发布 `F-*` 前端任务，并标清 mock 并行与真实联调依赖。
5. 发布下游任务后，回到上游任务补 `阻塞任务`。

## 6. 等待 Task Issue Sync

本仓库配置了 Task Issue Sync 自动化。Issue 满足以下条件时，workflow 会自动把它加入
GitHub Project `Software Teamwork`，同步 Project 字段和 GitHub Issue 原生依赖关系，
补 label，并把正文中的 `Project sync` 改为 `synced` 或 `blocked`：

- 标题匹配 `[S-001] ...`、`[A-001] ...` 等任务标题格式。
- 正文包含 `GitHub Project：Software Teamwork`。
- 正文包含可解析的 `状态`、`优先级`、`批次`、`模块`、`Risk`、`依赖任务` 等字段。
- 正文包含 `Project sync：pending`、`synced` 或 `blocked`。

自动完成内容：

| 自动动作 | 来源 |
| --- | --- |
| 加入 GitHub Project `Software Teamwork` | Issue 标题和 `GitHub Project` 字段。 |
| 同步 `Status`、`Priority`、`Batch`、`Module`、`Risk`、`Dependency` | Issue 正文任务字段。 |
| 同步 `Group` | Issue 标题编号前缀。 |
| 写入 Issue relationship | `依赖任务` 让当前 issue blocked by 上游；`阻塞任务` 让下游 issue blocked by 当前 issue。 |
| 写入 `OwnerNote` | workflow 自动生成。 |
| 添加可用 label | 主责小组和模块。 |
| 回写 `Project sync` | 同步结果。 |

`并行任务` 只表示需要同步契约的并行工作，不创建 GitHub Issue 原生 blocking relationship。

检查同步结果：

```bash
gh issue view <number> --repo Sakayori-Iroha-168/Software_Teamwork --json body,labels,url
```

正文中的 `Project sync` 应变为 `synced`。如果变为 `blocked`，workflow run 会标记为失败，
维护者需要检查 Task Issue Sync 日志和 `PROJECTS_TOKEN`。

如果 `Project sync` 变为 `blocked`，或任务没有出现在预期 View：

- 检查标题前缀是否错误，标准格式为 `[S-001] 中文任务标题`。
- 检查正文是否包含 `GitHub Project：Software Teamwork`。
- 检查必填任务字段是否能被 workflow 解析。
- 检查 `PROJECTS_TOKEN` 是否可访问 user-level Project。
- 检查默认 `GITHUB_TOKEN` 是否有 issue 写权限，能否调用 issue dependency relationship API。
- 必要时由维护者检查 Project View 过滤条件是否包含对应 `Group`。

## 7. 认领和执行

任务发布后默认不预分配 Assignee。成员认领时在 Issue 评论：

```text
认领：@your-github-login
```

自动化会：

- 校验评论者只能认领自己。
- 把评论者设为 Assignee。
- 将正文 `状态` 从 `Draft` 或 `Ready` 改为 `In Progress`。
- 将 Project `Status` 同步为 `In Progress`。

`Blocked`、`Review`、`Done` 状态的任务不能直接认领，需要协调人先改回 `Draft` 或 `Ready`。

## 8. 发布前校对清单

- [ ] 已查询 GitHub 当前状态基线，没有重复创建同范围任务。
- [ ] 标题是中文，格式符合 `[A/B/C/F/S-001] 中文任务标题` 这类三位顺序编号格式。
- [ ] 编号前缀和 `主责小组` 匹配。
- [ ] 正文字段完整，能被 Task Issue Sync 解析。
- [ ] `GitHub Project：Software Teamwork` 和 `Project sync：pending` 已填写。
- [ ] `依赖任务`、`阻塞任务`、`并行任务` 使用 GitHub issue 引用；暂未创建的上游任务已列入回填项。
- [ ] `依赖原因` 具体说明依赖的接口、schema、数据结构、环境变量、服务能力或验收条件。
- [ ] 权威依据指向公开文档、implementation 文档、GitHub issue 或 PR。
- [ ] 验收标准可验证，且和交付物一一对应。
- [ ] 边界与不做内容明确。
- [ ] 上游任务先发布，下游任务后发布，并已回填上下游引用。
- [ ] Issue 发布后 `Project sync` 已变为 `synced`。
