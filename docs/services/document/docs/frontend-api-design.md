# 报告生成模块前端 API 接口设计

## 1. 文档说明

本文基于当前 gateway OpenAPI、报告生成接口文档和技术选型基线整理，用于指导前端对接 gateway RESTful API。

结论：当前前端业务流程与最新版后端接口不冲突。此前冲突主要是旧动作路径命名，如 `/outline/generate`、`/content/generate`、`/exports`、`/generation-tasks` 等。前端实现应全部改用最新版 RESTful 资源路径。

## 2. 总体约定

### 2.1 Base URL

```text
/api/v1
```

前端只调用 gateway，不直接调用 `document` 服务内部地址。

### 2.2 请求头

| Header | 必填 | 来源 | 说明 |
|---|---:|---|---|
| `Authorization` | 是 | 大项目登录态 | `Bearer <accessToken>` |
| `X-Request-Id` | 否 | 前端生成或 gateway 生成 | 链路追踪 ID |

### 2.3 响应 envelope

前端不得继续依赖旧 `{ code, message, data }` envelope。gateway 项目自有 JSON 接口统一使用 `{ data, requestId }` 成功响应、分页 envelope 和 `{ error }` 错误响应；具体字段以 [前后端集成契约](../../../architecture/frontend-backend-contract.md) 和 Gateway OpenAPI 生成类型为准。本文不再维护手写 TypeScript envelope。

### 2.4 前端 API 层建议

技术基线固定为 `openapi-typescript` + typed fetch wrapper：

- OpenAPI 类型从 `docs/services/gateway/api/public.openapi.yaml` 生成到 `apps/web/src/api/generated/`，生成文件不得手工修改。
- `apps/web/src/api/client.ts` 只负责 transport：base URL、Bearer token、request id、JSON/form/文件流处理、envelope 和错误归一化。
- feature API 层可以包装生成类型以贴合页面语义，但字段、枚举和响应结构必须以生成类型为准。
- 组件不得直接拼 `fetch`、不得直接依赖 `document` 服务内部地址、不得使用旧 envelope。

建议在 React 项目中按 feature-first 组织：

```text
src/features/report-generation/
  api/
    reportApi.ts
    reportTemplateApi.ts
    reportMaterialApi.ts
    reportJobApi.ts
    reportFileApi.ts
    reportStatisticsApi.ts
    types.ts
  hooks/
    useReportDraft.ts
    useReportJobs.ts
    useReportRecords.ts
  pages/
  components/
```

浏览器代码通过统一 `gatewayClient` 发请求，组件不直接拼 fetch。

## 3. 页面与 Gateway 资源映射

前端 feature API 可以用业务命名包装 generated client，但本文不规定函数签名。页面、hook 和组件应以 Gateway OpenAPI 生成类型为准。

| 前端页面/区域 | 用户动作 | Gateway 资源 |
|---|---|---|
| 报告生成-步骤 1 | 查询报告类型 | `GET /report-types` |
| 报告生成-步骤 1 | 查询可用模板 | `GET /report-templates` |
| 报告生成-步骤 1 | 查询可用素材 | `GET /report-materials` |
| 报告生成-步骤 1 | 保存报告草稿 | `POST /reports` |
| 报告生成-步骤 1 | 生成大纲 | `POST /reports/{reportId}/jobs`，`jobType=outline_generation` |
| 报告生成-步骤 2 | 查询大纲版本 | `GET /reports/{reportId}/outlines` |
| 报告生成-步骤 2 | 保存大纲章节树 | `PATCH /reports/{reportId}/outlines/{outlineId}` |
| 报告生成-步骤 2 | 删除大纲章节 | `DELETE /reports/{reportId}/outlines/{outlineId}/sections/{sectionId}` |
| 报告生成-步骤 2 | 重新生成大纲 | `POST /reports/{reportId}/jobs`，`jobType=outline_regeneration` |
| 报告生成-步骤 3 | 生成完整报告 | `POST /reports/{reportId}/jobs`，`jobType=content_generation` |
| 报告生成-步骤 3 | 查询生成任务 | `GET /report-jobs/{jobId}` |
| 报告生成-步骤 3 | 重试失败任务 | `POST /report-jobs/{jobId}/attempts` |
| 正文编辑 | 查询章节正文 | `GET /reports/{reportId}/sections` |
| 正文编辑 | 保存正文/表格 | `PATCH /reports/{reportId}/sections/{sectionId}` |
| 正文编辑 | 单章节重新生成 | `POST /reports/{reportId}/sections/{sectionId}/versions` 或 `POST /reports/{reportId}/jobs` |
| 导出 | 创建 DOCX 文件 | `POST /report-files` |
| 导出 | 查询文件元数据 | `GET /report-files/{reportFileId}` |
| 导出 | 下载文件内容 | `GET /report-files/{reportFileId}/content` |
| 报告记录 | 分页查询报告 | `GET /reports` |
| 报告记录 | 删除报告 | `DELETE /reports/{reportId}` |
| 模板管理 | 上传模板 | `POST /report-templates` |
| 模板管理 | 更新/删除模板 | `PATCH/DELETE /report-templates/{reportTemplateId}` |
| 模板可视化编辑器 | 查询/保存结构 | `GET/PATCH /report-templates/{reportTemplateId}/structure` |
| 素材管理 | 上传/删除素材 | `POST/DELETE /report-materials` |
| 统计监控 | 统计概览 | `GET /report-statistics/overview` |
| 统计监控 | 30 天趋势 | `GET /report-statistics/daily?days=30` |
| 操作日志 | 查询日志 | `GET /report-operation-logs` |

## 4. 类型与 API 封装边界

- `ReportStatus`、`ReportJobStatus`、`ReportJobType`、报告模板、素材、报告、章节、任务和文件等类型从 `apps/web/src/api/generated/` 导入，或基于生成类型做窄包装。
- feature API 层可以提供 `listReports`、`createReportJob` 等符合页面语义的函数名，但函数参数、响应和错误类型必须引用生成类型，不在本文重复定义。
- `GET /report-files/{reportFileId}/content` 成功时返回文件流，不按普通 JSON envelope 解析；失败时仍按统一错误结构处理。
- 表单草稿、临时 UI 状态、乐观更新状态可以定义为前端本地类型，但不得覆盖 Gateway schema、枚举或字段名称。

## 5. 关键流程设计

### 5.1 创建报告并生成大纲

1. `GET /report-types`
2. `GET /report-templates?reportType=...&enabled=true`
3. `GET /report-materials`
4. `POST /reports` 创建草稿
5. `POST /reports/{reportId}/jobs`，`jobType=outline_generation`
6. 轮询 `GET /report-jobs/{jobId}`
7. 成功后 `GET /reports/{reportId}/outlines` 获取最新大纲版本

### 5.2 编辑大纲章节

1. 用户新增、删除、上移、下移、改标题、改层级。
2. 保存整棵大纲树：`PATCH /reports/{reportId}/outlines/{outlineId}`。
3. 删除指定章节也可调用：`DELETE /reports/{reportId}/outlines/{outlineId}/sections/{sectionId}`。
4. 前端保存成功后重新读取 `GET /reports/{reportId}/outlines/{outlineId}`，避免本地排序与后端编号不一致。

### 5.3 生成完整报告

1. 确认当前大纲已保存。
2. `POST /reports/{reportId}/jobs`，`jobType=content_generation`。
3. 轮询 `GET /report-jobs/{jobId}` 或 `GET /reports/{reportId}/events`。
4. 展示 `completedSections / totalSections / percent`。
5. 成功后 `GET /reports/{reportId}/sections` 获取章节正文和表格。
6. 若 `partial_succeeded`，保留已生成章节，失败章节显示重试入口。

### 5.4 编辑正文和表格

1. 查询章节：`GET /reports/{reportId}/sections/{sectionId}`。
2. 保存章节：`PATCH /reports/{reportId}/sections/{sectionId}`。
3. 单章节 AI 重新生成：优先使用 `POST /reports/{reportId}/sections/{sectionId}/versions`；如果后端统一走任务，也可使用 `POST /reports/{reportId}/jobs`，`jobType=section_regeneration`。

### 5.5 DOCX 导出和下载

1. 确认章节正文已保存。
2. `POST /report-files` 创建文件。
3. 若返回 `status=pending` 或 `jobId`，轮询文件元数据或任务状态。
4. 成功后 `GET /report-files/{reportFileId}/content` 下载文件。
5. 重新导出只调用 `POST /report-files`，不重新调用 AI 生成任务。

## 6. 权限与角色边界

Document 的角色能力、owner 约束、settings/统计/日志管理权限和 `403 forbidden` 语义统一维护在 [Document 权限矩阵](permission-matrix.md)。本文只保留前端 API 使用建议，不重复维护权限表。

## 7. 状态处理

### 7.1 任务状态到 UI 的映射

| 后端状态 | 前端展示 | 操作 |
|---|---|---|
| `pending` | 等待中 | 禁用重复提交 |
| `running` | 生成中 | 展示进度 |
| `succeeded` | 已完成 | 允许进入下一步 |
| `partial_succeeded` | 部分成功 | 展示失败章节和重试入口 |
| `failed` | 失败 | 展示错误原因和重试入口 |
| `canceled` | 已取消 | 允许重新创建任务 |

### 7.2 错误处理

- 401：跳转或提示重新登录，由大项目统一处理。
- 403：显示“当前角色无权限访问该功能”。
- 409：提示当前状态不允许操作，例如未保存大纲时生成正文。
- 502：展示 AI Gateway、file、PostgreSQL、Redis/asynq 或下游依赖失败，并允许重试任务。
- 同步创建任务失败：读取 `error.message` 和 `error.fields`。
- 长任务失败：读取 `ReportJob.error`。

## 8. 旧路径替换表

| 旧前端/旧文档写法 | 最新接口写法 |
|---|---|
| `POST /reports/{id}/outline/generate` | `POST /reports/{reportId}/jobs` + `jobType=outline_generation` |
| `POST /reports/{id}/outline/regenerate` | `POST /reports/{reportId}/jobs` + `jobType=outline_regeneration` |
| `POST /reports/{id}/content/generate` | `POST /reports/{reportId}/jobs` + `jobType=content_generation` |
| `POST /reports/{id}/content/regenerate` | `POST /reports/{reportId}/jobs` + `jobType=content_regeneration` |
| `POST /reports/{id}/sections/{sectionId}/regenerate` | `POST /reports/{reportId}/sections/{sectionId}/versions` 或 `POST /reports/{reportId}/jobs` + `jobType=section_regeneration` |
| `GET /generation-tasks/{taskId}` | `GET /report-jobs/{jobId}` |
| `POST /generation-tasks/{taskId}/retry` | `POST /report-jobs/{jobId}/attempts` |
| `POST /reports/{id}/exports` | `POST /report-files` |
| `GET /exports/{exportId}` | `GET /report-files/{reportFileId}` |
| `GET /exports/{exportId}/file` | `GET /report-files/{reportFileId}/content` |
| `GET /templates` | `GET /report-templates` |
| `GET /materials` | `GET /report-materials` |
| `GET /statistics/overview` | `GET /report-statistics/overview` |
| `GET /statistics/report-generation-trend` | `GET /report-statistics/daily?days=30` |

## 9. 验收清单

- [ ] 前端 API 路径不出现 `generate`、`regenerate`、`export`、`retry`、`download` 等动作词。
- [ ] 类型由 `openapi-typescript` 从 gateway OpenAPI 生成，`apps/web/src/api/generated/` 不手工修改。
- [ ] 组件通过 typed fetch wrapper 或 feature API 调用 gateway，不直接拼 `fetch`。
- [ ] 所有 JSON 响应按 `data/requestId` 或分页 envelope 解析。
- [ ] 所有公开字段使用 camelCase，例如 `requestId`、`reportType`、`templateId`、`businessObject`。
- [ ] 生成大纲、生成全文、导出 DOCX、重试失败任务均创建资源或任务。
- [ ] 前端按 [Document 权限矩阵](permission-matrix.md) 控制模板、素材、统计、日志和接口诊断入口展示。
- [ ] 文件下载不暴露 MinIO object key 或内部 URL。
- [ ] 任务失败和部分成功能保留已生成内容，并允许重试。
