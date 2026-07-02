# Document 权限矩阵

本文档说明 `document` 服务在报告模板、素材、报告记录、大纲、章节、任务、文件、配置、统计和日志上的权限边界。稳定公开路径以 Gateway OpenAPI 为准。

## 权限来源

| 项 | 说明 |
| --- | --- |
| 认证入口 | 前端、管理端和 MCP 调用方经 Gateway 调用，Document active paths 均需要 bearer auth。 |
| 用户上下文 | Gateway 注入 `X-User-Id`、`X-User-Roles`、`X-User-Permissions`。 |
| 角色 | `standard`、`admin`、`super_admin`。 |
| 权限字符串 | `document:read`、`document:upload`、`document:update`、`document:delete`、`report:read`、`report:write`。 |
| 管理权限 | Report settings、统计和操作日志面向 `admin` / `super_admin`。 |
| 资源事实 | Document PostgreSQL 保存报告、模板、材料、任务、文件、settings、统计和操作日志。 |

## 业务能力矩阵

| 能力 | `standard` | `admin` | `super_admin` | 额外约束 |
| --- | --- | --- | --- | --- |
| 查看报告类型 | 允许，需认证。 | 允许。 | 允许。 | 只返回启用和可见的类型。 |
| 查看报告模板 | 允许，需 `document:read`。 | 允许。 | 允许。 | 模板文件内容读取仍经 File 边界。 |
| 创建/更新/删除报告模板 | 默认不允许，除非授予 `document:update` / `document:delete`。 | 允许。 | 允许。 | 删除必须软删除或按模板状态约束。 |
| 查看报告素材 | 允许，需 `document:read`。 | 允许。 | 允许。 | 按素材可见性和状态过滤。 |
| 创建/删除报告素材 | 默认不允许，除非授予 `document:upload` / `document:delete`。 | 允许。 | 允许。 | 原始 bytes 通过 File 保存，不暴露 object key。 |
| 创建报告 | 允许，需 `report:write`。 | 允许。 | 允许。 | `created_by` 绑定当前用户。 |
| 查看/更新/删除自己的报告 | 允许，需 `report:read` / `report:write`。 | 允许。 | 允许。 | 标准用户只能管理自己的报告。 |
| 查看和软删除全局报告 | 不允许。 | 允许。 | 允许。 | 管理员和超级管理员可按角色级 RBAC 查看、软删除全站报告；操作必须写入审计。 |
| 大纲、章节、章节版本 | 允许，需可访问对应报告和 `report:write`。 | 允许。 | 允许。 | AI 生成前仍需报告和材料权限。 |
| 报告任务和 attempts | 允许，限自己可访问报告。 | 允许。 | 允许。 | 任务状态归 Document；依赖错误需脱敏。 |
| 报告文件和 content | 允许，限自己可访问报告文件。 | 允许。 | 允许。 | 文件 bytes 经 File 读取，不能暴露 `file_ref`、bucket、object key。 |
| Report settings | 不允许。 | 允许。 | 允许。 | `PATCH /report-settings` 仅 `admin` / `super_admin`。 |
| 统计和操作日志 | 不允许。 | 允许。 | 允许。 | 日志和指标必须脱敏。 |

## 服务间调用矩阵

| 调用目标 | Document 调用前必须校验 | 目标服务继续负责 |
| --- | --- | --- |
| File Service | 用户可访问模板、素材或报告文件资源。 | 底层 bytes 和 file object 元数据。 |
| Knowledge retrieval | 报告生成请求允许使用指定知识库范围。 | 知识库、文档、chunk 和原文权限过滤。 |
| AI Gateway chat | 报告/章节生成权限、settings profile 可用。 | Provider 调用、API key 保护和错误归一化。 |
| QA/MCP caller | 工具调用参数、报告资源权限和输出脱敏。 | QA 负责工具白名单、调用记录和用户会话权限。 |

## 拒绝规则

| 条件 | 响应 |
| --- | --- |
| 未认证 | `401 unauthorized`。 |
| 缺少 report/document 权限 | `403 forbidden`。 |
| 标准用户非 owner 访问报告、章节、任务或文件 | `403 forbidden` 或隐藏为 `404 not_found`，按接口契约执行。 |
| 普通用户访问 settings、统计、操作日志 | `403 forbidden`。 |
| 资源不存在、已软删除或状态不允许 | `404 not_found` 或 `409 conflict`。 |
| 下游 File/Knowledge/AI Gateway 失败 | `dependency_error`，不得返回 object key、内部 URL、prompt、provider raw body 或 API key。 |

## 当前缺口

- 组织、电厂、专业等细粒度报告权限不属于首期范围。
- 管理员跨用户报告访问仅限查看和软删除全局报告；如果要扩展到代写、恢复、硬删除或读取内部生成明细，必须补明确契约和审计。
- Document 不保存用户、角色、权限源数据，只消费 Gateway 注入的上下文。
