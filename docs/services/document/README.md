# Document 服务接口文档

本文档定义 `document` 服务在项目初期的职责边界、gateway 公开接口、报告生成工作流和实现约束。详细字段、状态码、response envelope 和 schema 以 [`docs/services/gateway/api/public.openapi.yaml`](../gateway/api/public.openapi.yaml) 为准；服务本地公开 OpenAPI 草案见 [`api/public.openapi.yaml`](api/public.openapi.yaml)，内部运行合同见 [`api/internal.openapi.yaml`](api/internal.openapi.yaml)。

前端、管理端、其他后端模块和 MCP 工具调用方只能通过 gateway `/api/v1/**` 访问报告生成能力，不能直接调用 `document` 服务内部地址。

RESTful 路径、统一响应和错误 envelope 以 [前后端集成契约](../../architecture/frontend-backend-contract.md) 为准。报告生成中的“生成、重新生成、导出、重试”统一建模为任务、任务尝试、章节版本和报告文件等资源创建，不在稳定 path 中使用 `generate`、`regenerate`、`export`、`retry`、`download` 等动作词。

## 配套文档

`README.md` 是服务入口，不替代所有细节文档。当前保留以下有独立维护价值的文档：

| 文档 | 说明 |
| --- | --- |
| [`../../architecture/technology-decisions.md`](../../architecture/technology-decisions.md) | 项目当前技术选型基线；`document` 服务实现和本文档约束必须与其保持一致。 |
| [`api/public.openapi.yaml`](api/public.openapi.yaml) | `document` 服务本地公开 OpenAPI 草案；公开稳定契约仍以 gateway OpenAPI 为准。 |
| [`api/internal.openapi.yaml`](api/internal.openapi.yaml) | `document` 服务内部运行和 report job 合同。 |
| [`docs/data-models.md`](docs/data-models.md) | 报告生成逻辑数据模型、实体关系、关键字段和存储约束。 |
| [`docs/frontend-api-design.md`](docs/frontend-api-design.md) | 前端 API 层、页面到接口映射和类型使用建议。 |
| [`docs/generation-workflow.md`](docs/generation-workflow.md) | 报告 job、attempt、event、worker、AI Gateway、File Service 和 DOCX 创建的目标流程与当前缺口。 |
| [`docs/permission-matrix.md`](docs/permission-matrix.md) | 报告模板、素材、报告、任务、文件、settings、统计和日志的权限矩阵。 |
| [`docs/implementation.md`](docs/implementation.md) | 当前代码实现、契约对齐、缺口和最近检查记录。 |
| [`docs/requirements.md`](docs/requirements.md) | 原始报告生成需求沉淀和验收点。 |

已被 gateway OpenAPI 和本文覆盖的重复 API 契约草稿不再作为当前阅读入口；数据模型、前端 API 设计和需求沉淀这类服务细节文档单独保留。

## 技术基线

`document` 服务实现必须遵循 [技术选型基线](../../architecture/technology-decisions.md)。本服务只补充报告生成特有约束：

- 代码落地时使用独立 Go module，服务代码放在 `services/document/`。
- 使用 `asynq` over Redis 执行大纲、正文、章节和 DOCX 创建任务；PostgreSQL 是任务业务状态权威。
- 当前 `summer_peak_inspection` 固定报告类型已支持通过 AI Gateway chat 完成基础大纲生成和逐章节正文生成，成功结果写入大纲、章节和章节版本。
- 生成请求可通过 `options.knowledgeBaseIds` 等检索参数在配置了 Knowledge 服务时获取受控材料上下文；`document` 不直接访问 Qdrant。
- 当前基础 DOCX 导出由 Document worker 内置 Go `SimpleDOCXGenerator` 完成，并通过 `file` 服务保存底层 bytes；Pandoc/LibreOffice 仅作为后续富 DOCX worker 工具链，落地前不作为当前运行依赖。
- 报告生成链路是后续 OpenTelemetry tracing 重点。

## 职责边界

| 范围 | 说明 |
| --- | --- |
| 报告类型 | 维护固定报告类型、显示名称、启用状态和默认模板引用。首期覆盖迎峰度夏检查报告、煤库存审计报告。 |
| 报告模板 | 管理 DOCX 模板文件、模板元数据、启用状态、版本和模板结构配置。 |
| 报告素材 | 管理报告生成可引用的支撑材料业务资源；底层文件对象在服务边界内复用 `file`。 |
| 报告记录 | 保存报告草稿、报告基础信息、状态、创建人、来源和生成时间。 |
| 大纲与章节 | 保存报告大纲版本、章节树、章节正文、表格内容和章节版本。 |
| 生成任务 | 维护大纲生成、正文生成、章节重新生成、报告文件创建等异步任务和任务尝试。 |
| 报告文件 | 管理生成文件元数据和内容读取入口；底层 DOCX 对象在服务边界内复用 `file`。 |
| 统计和日志 | 提供报告统计、每日趋势和报告操作日志，用于管理端展示和排查。 |
| 报告配置 | 管理报告生成配置，包括 AI Gateway profile 引用、默认模板和文件生成默认值。 |

`document` 不负责用户登录、会话签发、RBAC 源数据、知识库索引、Qdrant 检索实现、provider API key 存储、MinIO object key 暴露、QA 聊天流程或前端页面。

## 接入模型

```text
frontend / admin / MCP caller
   |
   v
gateway report resources
   |
   v
document service
   |
   +--> PostgreSQL report, template, section, job, file metadata, logs
   +--> asynq over Redis for async report jobs
   +--> File service base file APIs for template, material, generated DOCX bytes
   +--> Knowledge service retrieval when generation needs source material context
   +--> AI Gateway internal model profiles and OpenAI-compatible chat API
```

Document 的认证上下文、报告 owner 约束、settings/统计/日志管理权限和拒绝规则统一维护在 [Document 权限矩阵](docs/permission-matrix.md)。README 不重复维护 header 表或角色权限表。

## 公开资源范围

Document 已进入 Gateway active contract 的公开资源包括：

- `report-types`、`report-templates` 和模板结构配置。
- `report-materials`。
- `reports`、报告大纲、章节和章节版本。
- `report-jobs`、任务尝试和报告事件。
- `report-files` 和生成文件内容流。
- `report-statistics`、`report-operation-logs` 和 `report-settings`。

逐项 method、path、schema、认证和错误响应以 [`docs/services/gateway/api/public.openapi.yaml`](../gateway/api/public.openapi.yaml) 和 [Gateway Active API Owner Map](../gateway/docs/active-api-owner-map.md) 为准。服务级 [`api/public.openapi.yaml`](api/public.openapi.yaml) 是 Document-owned public 设计面；前端稳定契约仍以 Gateway OpenAPI active paths 为准。

## RESTful 建模规则

| 业务动作 | 稳定资源建模 |
| --- | --- |
| 生成或重新生成大纲 | 在报告资源下创建 report job，并用 `jobType` 区分 `outline_generation` 或 `outline_regeneration`。 |
| 生成或重新生成正文 | 在报告资源下创建 report job，并用 `jobType` 区分 `content_generation` 或 `content_regeneration`。 |
| 重新生成指定章节 | 在报告章节下创建新的 section version，默认保留用户编辑。 |
| 重试失败任务 | 在 report job 下创建 attempt 资源。 |
| 导出 DOCX | 创建 report file 资源，首期格式为 DOCX。 |
| 获取导出文件内容 | 读取 report file 的 content 子资源。 |

后续如需报告 SSE，只能先补 gateway OpenAPI active path；当前公开能力通过报告事件资源轮询事件列表。

## 通用响应结构

JSON 成功、分页和错误响应遵循 [前后端集成契约](../../architecture/frontend-backend-contract.md)。文件内容接口成功时返回二进制流，不包裹 JSON envelope；失败时仍返回统一错误响应。调用方应优先匹配 `error.code`，不要解析 `message` 文案。

## 核心工作流

### 创建报告并生成大纲

1. 调用方查询 report type 和 report template 资源。
2. 调用方创建报告草稿资源，传入报告类型、模板、主题、专业、业务对象、年份和补充上下文。
3. 调用方创建 `outline_generation` report job。
4. `document` 根据报告类型、模板结构、主题、上下文和材料引用生成大纲版本。
5. 调用方查询报告大纲列表或指定大纲资源。

### 编辑大纲和章节

1. 调用方更新报告大纲资源，修改章节标题、顺序和层级。
2. 删除大纲章节时，操作报告大纲下的 section 子资源。
3. 服务必须保持章节树合法并重新计算展示编号。
4. 当前大纲版本是后续正文生成的输入；重新生成时应创建新任务或新章节版本，不隐式覆盖用户编辑。

### 生成正文和重新生成

1. 调用方通过 `POST /api/v1/reports/{reportId}/jobs` 创建 `content_generation` 或 `content_regeneration` 任务。
2. 当前实现会由 worker 通过 AI Gateway chat 逐章节生成正文，保存章节内容、结构化表格、章节版本和任务进度；首个闭环固定报告类型为 `summer_peak_inspection`。
3. 部分章节失败时，已成功章节不得丢失；任务可进入 `partial_succeeded` 或 `failed`，具体枚举以 OpenAPI 为准。
4. 单章重新生成通过 `POST /api/v1/reports/{reportId}/sections/{sectionId}/versions` 创建新章节版本。`preserveUserEdits` 默认应为 `true`，只有调用方显式传 `false` 才覆盖用户编辑内容。

### 创建报告文件

1. 调用方创建报告文件资源，首期格式为 DOCX。
2. 当前基础实现使用已保存的报告和章节内容，通过内置 `SimpleDOCXGenerator` 生成基础 DOCX，不重新执行 AI 生成；富 DOCX 阶段再接入样式配置和 Pandoc/LibreOffice worker。
3. 底层文件对象由 `document` 在服务边界内调用 `file` 保存。
4. 调用方查询 report file 元数据，读取 report file content 子资源获取内容。

## 核心数据模型

数据库字段建议使用 `snake_case`，公开 API 字段使用 `camelCase`，并以 gateway OpenAPI 为准。

| 实体 | 说明 | 关键字段 |
| --- | --- | --- |
| `ReportType` | 固定报告类型配置。 | `code`、`name`、`enabled`、`defaultTemplateId`。 |
| `ReportTemplate` | DOCX 模板业务资源。 | `id`、`templateName`、`reportType`、`version`、`enabled`、`fileName`、`fileSize`。 |
| `ReportTemplateStructure` | 模板大纲、材料映射和样式配置。 | `outlineSchema`、`materialMappings`、`styleConfig`。 |
| `ReportMaterial` | 报告支撑材料业务资源。 | `id`、`materialName`、`materialType`、`category`、`tags`、`enabled`。 |
| `Report` | 报告草稿和报告记录。 | `id`、`name`、`reportType`、`templateId`、`topic`、`status`、`creatorId`。 |
| `ReportOutline` | 报告大纲版本。 | `id`、`reportId`、`version`、`outlineSchema`、`source`、`isCurrent`。 |
| `ReportSection` | 当前章节内容。 | `id`、`reportId`、`outlineId`、`sectionPath`、`title`、`content`、`tableData`。 |
| `ReportSectionVersion` | 章节历史版本和 AI 生成版本。 | `id`、`sectionId`、`version`、`source`、`content`、`createdBy`。 |
| `ReportJob` | 异步生成任务。 | `id`、`reportId`、`jobType`、`status`、`progress`、`error`。 |
| `ReportJobAttempt` | 任务执行尝试。 | `id`、`jobId`、`attemptNumber`、`status`、`error`。 |
| `ReportEvent` | 任务进度和审计事件。 | `id`、`reportId`、`jobId`、`eventType`、`payload`。 |
| `ReportFile` | 生成文件业务资源。 | `id`、`reportId`、`format`、`status`、`contentPath`、`fileSize`。 |
| `ReportOperationLog` | 报告相关操作日志。 | `id`、`operatorId`、`operationType`、`targetType`、`targetId`、`operationResult`。 |

## 状态约定

`ReportStatus` 公开枚举以 gateway OpenAPI 为准，当前覆盖：

```text
draft | outline_generating | outline_generated | content_generating | generated | exporting | exported | failed | deleted
```

`ReportJobStatus` 公开枚举以 gateway OpenAPI 为准，当前覆盖：

```text
pending | running | succeeded | partial_succeeded | failed | canceled
```

`ReportJobType` 当前覆盖：

```text
outline_generation | outline_regeneration | content_generation | content_regeneration | section_regeneration | report_file_creation
```

长任务失败优先体现在 `ReportJob.status=failed` 和 `ReportJob.error` 中；只有同步创建任务失败时才直接返回 HTTP 错误。

## 报告配置

管理端报告生成配置通过 gateway active 的 report settings 资源暴露，精确 method/path/schema 以 Gateway OpenAPI 为准。

配置范围：

| 字段 | 说明 |
| --- | --- |
| `llm.provider` | 当前固定为 `ai-gateway`。 |
| `llm.profileId` | AI Gateway chat model profile id。 |
| `llm.model` | 上游模型名或业务显示名。 |
| `llm.timeoutSeconds` | 生成调用超时时间。 |
| `defaultTemplates` | `reportType -> reportTemplateId` 默认模板映射。 |
| `file.defaultFormat` | 首期固定为 `docx`。 |
| `file.defaultNumberingMode` | 首期支持 `global`；`by_chapter` 字段保留但不作为首期验收。 |
| `file.defaultStyleProfileId` | 默认 DOCX 样式配置引用。 |

`document` 不保存 provider `baseUrl` 或 `apiKey`。这些敏感配置只由 AI Gateway model profile 拥有，公开响应和日志不得包含。

## 与其他服务的边界

### File Service

报告模板、报告素材和报告文件由 `document` 拥有业务状态。`document` 在内部调用 `file` 的基础文件能力保存和读取底层对象。公开响应不得暴露 file 内部 ID、bucket、object key、MinIO URL、签名 URL 或存储凭据。

### Knowledge Service

报告生成需要材料上下文时，应通过报告素材业务资源和 knowledge 检索能力获取。`document` 不直接访问 Qdrant，不保存知识库切片索引状态，也不绕过 `knowledge` 读取受控知识库数据。

### AI Gateway

`document` 通过 AI Gateway 内部 OpenAI-compatible API 调用模型。业务配置只引用 AI Gateway `profileId`、模型名和业务超时参数；provider 配置、API key 写入状态和密钥轮换仍由 AI Gateway 管理。

### QA 与 MCP 工具

Document 当前已在 `services/document/internal/service/mcp_tools.go` 提供服务内 MCP 工具适配层，并在 document 主进程通过 `DOCUMENT_MCP_PATH`（默认 `/mcp`）暴露 Streamable HTTP MCP server。该适配层接收可信 `RequestContext`，复用现有 Document service 能力，记录 `requestSource=mcp` 和 `toolName=<tool>` 的安全操作日志；QA 端到端 smoke 仍待 B-017/S-008 联调任务补齐。

当前工具包括：

| MCP 工具 | Gateway 资源 |
| --- | --- |
| `generate_report_outline` | `POST /reports/{reportId}/jobs`，`jobType=outline_generation` |
| `regenerate_report_outline` | `POST /reports/{reportId}/jobs`，`jobType=outline_regeneration` |
| `generate_report_text` | `POST /reports/{reportId}/jobs`，`jobType=content_generation` |
| `regenerate_report_text` | `POST /reports/{reportId}/jobs`，`jobType=content_regeneration` |
| `regenerate_report_section` | `POST /reports/{reportId}/jobs`，`jobType=section_regeneration` |
| `get_generation_status` | `GET /report-jobs/{jobId}` |
| `get_template_schema` | `GET /report-templates/{reportTemplateId}/structure` |
| `export_report_docx` | `POST /report-files` |
| `get_report_result` | `GET /reports/{reportId}`、`GET /report-files/{reportFileId}` |

工具层不得绕过 Document service 边界直连数据库、MinIO、Qdrant 或 provider。工具响应只返回安全摘要、业务资源 ID、进度和错误码，不返回 prompt、provider 原始错误、内部 URL、对象存储路径、File Service 内部引用或完整工具私有参数。`export_report_docx` 只走当前基础 DOCX 导出路径，不代表 Pandoc/LibreOffice 富 DOCX 已可用。

QA runtime 可按以下方式接入 Document MCP endpoint：

```env
MCP_TRANSPORT=streamable_http
MCP_SERVER_ALIAS=document
MCP_SERVER_URL=http://document:8085/mcp
# 必须与 DOCUMENT_MCP_SERVICE_TOKEN 一致；默认 Compose 会把该 token 对齐到 INTERNAL_SERVICE_TOKEN。
MCP_SERVER_TOKEN=${INTERNAL_SERVICE_TOKEN}
MCP_SERVER_TOKEN_HEADER=Authorization
```

## 错误码约定

Document 相关接口使用项目统一错误码：

| Code | HTTP status | Document 场景 |
| --- | --- | --- |
| `validation_error` | `400` | 请求体或查询参数格式错误，例如缺少 `reportType`、`templateId` 或 `jobType`。 |
| `unauthorized` | `401` | 缺少认证凭据或 gateway 未注入有效用户上下文。 |
| `forbidden` | `403` | 已认证但无权访问目标报告、模板、素材或配置。 |
| `not_found` | `404` | 报告、模板、素材、任务、章节或文件不存在，或对当前用户隐藏。 |
| `conflict` | `409` | 当前资源状态不允许修改、删除、导出或重试。 |
| `rate_limited` | `429` | 生成、导出、上传或查询超过配额。 |
| `dependency_error` | `502` | PostgreSQL、Redis、file、knowledge、AI Gateway 或对象存储失败。 |
| `internal_error` | `500` | 未预期服务端错误。 |

错误响应、任务错误、操作日志和工具输出不得包含 SQL、MinIO object key、内部文件路径、prompt、API key、token、provider 原始响应或堆栈。

## 实现与验证要求

- 服务代码放在 `services/document/`，使用独立 Go module；通用数据库、迁移、HTTP、配置、日志、测试和观测规则见 [技术选型基线](../../architecture/technology-decisions.md)。
- 启动时必须校验 PostgreSQL、Redis、file client、AI Gateway 配置、监听地址和 MCP endpoint/token header；Knowledge 服务配置是可选项，仅在生成请求要求检索上下文时使用；`DOCUMENT_PANDOC_PATH` 和 `DOCUMENT_LIBREOFFICE_PATH` 是富 DOCX 工具链预留配置，工具链选型已由 C-011 固定（见 [rich-docx-worker.md](docs/rich-docx-worker.md)），当前 Dockerfile 不安装对应 CLI。
- Gateway 只做公开入口、认证上下文、统一 envelope、错误归一化和路由转发，不承载报告生成业务逻辑。
- Document MCP endpoint 必须配置非空 `DOCUMENT_MCP_SERVICE_TOKEN` 或 `INTERNAL_SERVICE_TOKEN`；默认 Compose 会把 `DOCUMENT_MCP_SERVICE_TOKEN` 对齐到 `INTERNAL_SERVICE_TOKEN`，若单独覆盖则 QA `MCP_SERVER_TOKEN` 必须使用同一个值；未配置时服务启动失败，避免 `/mcp` 在宿主机映射端口上无鉴权开放。
- Redis 只通过 `asynq` 承载任务队列和短期协调；PostgreSQL 中的 `ReportJob`、`ReportJobAttempt`、`ReportEvent` 是权威业务状态。
- 任务最多自动重试 3 次，失败后保留最近尝试摘要；手动重试通过 `report-jobs/{jobId}/attempts` 创建新资源。
- 当前大纲/正文生成由 worker 通过 AI Gateway chat 完成，不保存 provider base URL/API key，不直连 provider；当前 DOCX 创建由 worker 调用内置 `SimpleDOCXGenerator` 完成，生成后通过 file 服务保存底层对象；富 DOCX 工具链（`pandoc/core:3.10`）已由 C-011 固定选型，Dockerfile 接入时必须同步更新部署和技术基线。
- 服务日志和指标不得记录 prompt 全文、文档全文、`file_ref`、object key、token、API key 或 provider 原始响应体。
- 模板文件首期限定 DOCX；模板结构、默认章节和材料映射以数据库配置为权威，不从 DOCX 自动解析。
- 首期 AI 生成闭环覆盖 `summer_peak_inspection`；新增报告类型或更复杂的检索/流式事件前必须确保 OpenAPI、状态枚举和错误处理已同步。
- 契约测试应覆盖 active document operations 的 response envelope、字段命名、错误码、request id、权限边界和文件内容接口。

## C-010 跨服务契约验证

C-010 的本地可重复验证以 Document 服务内 fake-backed contract tests 为主，不要求启动真实 File、Knowledge 或 AI Gateway：

```bash
cd services/document
go test ./...
go build ./cmd/server
```

这些测试覆盖 Document 调用 File Service `/internal/v1/files/**`、`X-Service-Token` 透传、模板/素材/报告文件公开响应脱敏、报告文件 content 成功二进制返回、失败 JSON error envelope，以及 fake 依赖失败到 `dependency_error` 的映射。

需要完整联调时，先通过 gateway 访问公开 `/api/v1/**` 路径，并确保 Document、File、Redis、AI Gateway 可用；如果生成请求使用知识库上下文，还需要 Knowledge。联调时重点检查 `X-Request-Id` 贯穿日志，File Service token 匹配，报告文件 content 未就绪时返回统一错误 envelope。当前富 DOCX 的 Pandoc/LibreOffice 工具链、QA MCP 端到端 smoke 和 `coal_inventory_audit` 生成策略仍是后续任务，不能作为 C-010 验收前提。
