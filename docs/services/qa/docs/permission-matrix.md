# QA 权限矩阵

本文档说明 `qa` 服务在会话、消息、回答运行、引用、配置、检索测试和指标上的权限边界。稳定公开路径以 Gateway OpenAPI 为准。

## 权限来源

| 项 | 说明 |
| --- | --- |
| 认证入口 | 前端经 Gateway 调用，QA active paths 均需要 bearer auth。 |
| 用户上下文 | Gateway 注入 `X-User-Id`、`X-User-Roles`、`X-User-Permissions`。 |
| 角色 | `standard`、`admin`、`super_admin`。 |
| 权限字符串 | `qa:use`、`qa:settings:read`、`qa:settings:write`，以及被 MCP 工具消费的跨服务权限。 |
| 资源事实 | QA PostgreSQL 保存 conversation、message、response run、tool call、citation、settings、test run 和 metrics facts。 |
| 下游权限 | Knowledge、Document、File、AI Gateway 和 MCP server 仍在各自边界校验资源权限。 |

## 业务能力矩阵

| 能力 | `standard` | `admin` | `super_admin` | 额外约束 |
| --- | --- | --- | --- | --- |
| 创建和查看自己的 QA 会话 | 允许，需 `qa:use`。 | 允许。 | 允许。 | 标准用户只能访问自己的会话。 |
| 更新和删除自己的 QA 会话 | 允许，需 `qa:use`。 | 允许。 | 允许。 | 标准用户只能管理自己的会话。 |
| 查看和软删除全站 QA 会话 | 不允许。 | 允许。 | 允许。 | 管理员和超级管理员可按角色级 RBAC 查看、软删除普通用户会话；操作必须写入审计。 |
| 创建消息和回答运行 | 允许，需 `qa:use`。 | 允许。 | 允许。 | 工具可见性必须按配置、白名单和用户权限裁剪。 |
| 查看 response run 和 tool calls | 允许，仅限自己会话关联资源。 | 允许，默认仍按 owner 约束。 | 允许，默认仍按 owner 约束。 | 不返回完整 prompt、chain-of-thought、MCP 原始参数或完整工具结果。 |
| 查看引用和 citation lookup | 允许，仅限自己消息或可访问引用。 | 允许。 | 允许。 | 原文 hydrate 必须回 Knowledge/File 复核权限。 |
| 上传和删除 QA 会话附件 | 允许，仅限自己会话。 | 允许。 | 允许。 | QA 拥有附件元数据；File 保存原始 bytes，Parser 做解析。 |
| 读取当前 QA/LLM settings | 默认不允许，除非授予 `qa:settings:read`。 | 允许。 | 允许。 | 响应必须脱敏模型和 provider 配置。 |
| 创建 QA/LLM settings version | 默认不允许，除非授予 `qa:settings:write`。 | 允许。 | 允许。 | 写入 admin audit logs。 |
| LLM connection test | 默认不允许，除非授予 `qa:settings:write`。 | 允许。 | 允许。 | 不返回 provider raw body 或 secret。 |
| Retrieval test runs | 默认不允许，除非授予管理权限。 | 允许。 | 允许。 | Knowledge retrieval 仍过滤无权限知识库和文档。 |
| QA metrics | 默认不允许，除非授予管理权限。 | 允许。 | 允许。 | 指标不得包含 prompt、原始文档全文或敏感工具参数。 |

## 工具和服务间权限矩阵

| 调用目标 | QA 调用前必须校验 | 目标服务继续负责 |
| --- | --- | --- |
| AI Gateway chat | 用户可创建回答运行、profile/config 可用、调用摘要可审计。 | Provider 调用、API key 保护和错误归一化。 |
| MCP tools | 工具白名单、用户权限、参数 schema、超时、幂等键。 | 具体工具的业务权限和数据脱敏。 |
| Knowledge retrieval/citation source | 用户是否可在当前 QA 上下文使用检索工具。 | 知识库、文档、chunk 和原文读取权限。 |
| Document report tools | 用户是否可调用报告工具。 | 报告、模板、文件、settings 和操作日志权限。 |
| File/Parser for attachments | 会话 owner 和附件状态。 | File 保存 bytes；Parser 解析 bytes。 |

## 拒绝规则

| 条件 | 响应 |
| --- | --- |
| 未认证 | `401 unauthorized`。 |
| 缺少 `qa:use` 或 settings 管理权限 | `403 forbidden`。 |
| 访问他人会话、消息、run 或附件 | `403 forbidden` 或隐藏为 `404 not_found`，按接口契约执行。 |
| 工具未授权、参数越界或策略拒绝 | `policy_denied` / `403 forbidden`，并写入脱敏工具摘要。 |
| 下游依赖失败 | `dependency_error`，不得返回 provider raw body、prompt、MCP 原始参数、object key 或内部 URL。 |

## Owner 隐藏规则

| 资源 | 非 owner 响应语义 | 说明 |
| --- | --- | --- |
| QA 会话详情、会话更新、会话删除、会话消息列表、消息创建 | 标准用户访问他人会话时返回 `403 forbidden`；会话不存在或已软删除时返回 `404 not_found`。 | 管理员和超级管理员可查看、软删除全站会话，但创建消息、启动回答和普通更新仍不得冒充会话 owner。 |
| Message、response run、tool call、citation 单资源或子资源 | 标准用户非 owner 返回 `404 not_found`。 | 始终带当前用户 owner 过滤，不通过单资源响应泄露他人消息、run、tool call 或引用是否存在；管理员跨用户查看必须走明确的管理会话路径并写审计。 |
| Citation lookup 批量查询 | 只返回当前用户可见记录；被过滤 ID 不出现在结果和错误详情中。 | 不披露被省略 ID 是否存在或属于其他用户。 |
| QA 会话附件和临时附件 chunk | 返回 `404 not_found`。 | 附件非 owner 必须隐藏存在性；`file_ref`、object key、bucket 和内部 URL 不进入公开响应。 |

## 当前缺口

- 管理员跨用户 QA 会话访问仅限查看和软删除全站会话；如果要扩展到代发消息、查看完整工具明细或恢复会话，必须补明确契约和审计。
- MCP 原始 tool schema、完整工具参数/结果和内部审计细节不属于前端稳定公开契约。
- QA 不保存用户、角色、权限源数据，只消费 Gateway 注入的上下文。
