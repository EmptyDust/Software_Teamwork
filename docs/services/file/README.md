# File 服务接口文档

本文档定义 `file` 服务的职责边界和内部文件能力契约。前端公开契约以 [`docs/services/gateway/api/public.openapi.yaml`](../gateway/api/public.openapi.yaml) 为准；前端不得直接调用 `file` 服务内部地址，只能通过 gateway 暴露的 `/api/v1/**` 入口访问文件能力。

RESTful 路径、统一响应和错误 envelope 以 [前后端集成契约](../../architecture/frontend-backend-contract.md) 为准。知识库原始文件流使用 `documents/{documentId}/content` 子资源表示；报告模板、素材和导出文件使用 `document` 服务拥有的 report 资源路径，由 `document` 在服务边界内复用 `file` 服务的基础文件能力。

## 文档入口

| 文档 | 说明 |
| --- | --- |
| [数据模型](docs/data-models.md) | File Service 拥有的基础文件对象元数据、对象存储引用和清理模型。 |
| [权限矩阵](docs/permission-matrix.md) | File 内部服务认证、owner service 授权责任和公开资源复用边界。 |
| [实现说明](docs/implementation.md) | 当前代码实现、契约对齐、缺口、临时后端和最近检查记录。 |
| [服务 OpenAPI](api/internal.openapi.yaml) | File Service 内部 `/internal/v1/files/**` API 契约；不是前端公开契约。 |

## 技术基线

File Service 必须遵循 [技术选型基线](../../architecture/technology-decisions.md)。本服务只补充文件域特有约束：

- 上传大小限制必须在 HTTP 层和 multipart 解析层同时生效。
- 目标对象存储使用官方 MinIO Go SDK；当前 runtime 已有 memory/local/MinIO `ObjectStore` adapter，根级 Compose 已提供 MinIO server/mc 初始化和本地实现细节 bucket `software-teamwork-local`。`file` 服务封装 bucket、object key、etag、version id 和对象 URL，owner service 与前端都不得直接依赖这些内部字段。
- 当前 `cmd/server` 在 `FILE_DATABASE_URL` 为空时使用 memory metadata repository；配置 `FILE_DATABASE_URL` 时接入 PostgreSQL repository，并要求 `FILE_INTERNAL_SERVICE_TOKEN` 或 `INTERNAL_SERVICE_TOKEN`。具体状态以 [实现说明](docs/implementation.md) 为准。
- 对象物理清理可由 `asynq` worker 执行，任务类型使用 `file:object:purge`。PostgreSQL 中的文件状态、失败摘要、重试次数和最终结果仍是权威来源。
- handler 测试重点覆盖 envelope、错误码、request id、multipart 边界和内容流响应；repository 测试覆盖 migration 后的 SQL 行为。
- File Service 不使用 ORM，不把 MinIO SDK 泄露到 handler 或 owner service client，不把缓存或队列作为基础文件元数据的事实来源。

## 职责边界

| 范围 | 说明 |
| --- | --- |
| 原始文件对象 | 接收后端 owner service 转交的文件流，校验基础文件属性，并写入 MinIO 或等价对象存储。 |
| 基础文件元数据 | 只维护 file ID、原始文件名、内容类型、文件大小、checksum、内部存储引用、创建时间和删除时间等基础元数据。 |
| 对象存储协调 | 生成服务端 object key，管理 bucket/object 写入、读取和删除，不向前端暴露内部存储路径、签名 URL 或存储凭据。 |
| 文件内容读取 | 根据内部 file ID 返回原始文件流，供 `knowledge`、`document` 等 owner service 在自己的资源边界内使用。 |
| 文件删除 | 负责基础文件元数据生命周期和原始对象删除或延迟清理流程。 |

`file` 是后端内与文件对象和对象存储交互的基础中间件服务。它不负责知识库 CRUD、知识库文档处理状态、文档解析、文本切片、embedding、向量索引、RAG、问答生成、报告内容生成、报告模板配置、报告素材业务状态或报告导出状态。

`knowledge` 服务拥有知识库、知识库文档、文档处理状态、chunks 和索引状态。`document` 服务拥有报告、报告模板、报告素材、报告文件和生成流程业务状态。`file` 服务只承诺原始文件对象、对象存储协调和最小基础 file 元数据。

`file` 服务不得存储以下业务数据：

- `knowledgeBaseId`、知识库文档处理状态、chunks、parser 配置、向量索引状态。
- `reportId`、`templateId`、`materialId`、`reportFileId`、导出状态、报告模板结构、报告素材引用关系。
- 业务可见性、业务软删除规则、业务权限 ACL。

## 接入模型

```text
frontend
   |
   v
gateway owner-service file-backed resources
   |
   v
owner service
   |-- knowledge owns knowledge documents and document content resources
   |-- document owns report templates, materials, and report files
   |
   v
file service /internal/v1/files/**
   |
   |-- PostgreSQL basic file metadata
   +-- MinIO object storage
```

前端侧只调用 gateway 公开接口。gateway 将认证后的请求转发给 owner service，并统一处理响应 envelope、request id 和错误归一化。

知识库文件上传、文档详情、文档标签、删除和原始文件流公开资源由 `knowledge` 拥有。`knowledge` 在服务边界内保存内部 `file_ref`、知识库归属、处理状态和索引状态，并调用 `file` 读写底层原始文件对象。

报告模板、素材和导出文件公开资源由 `document` 拥有。`document` 保存 `reportTemplateId`、`materialId`、`reportFileId`、业务状态和内部 `file_ref`，并通过内部 client 调用 `file` 完成对象写入、读取和删除。前端仍只看到 report 资源 ID 和 content 子资源，不接触 file 内部 ID、bucket、object key 或 MinIO URL。

## 公开能力复用边界

`file` 服务不直接拥有前端公开 API。Gateway active path、owner service 和认证要求只在 [Gateway OpenAPI](../gateway/api/public.openapi.yaml) 与 [active API owner map](../gateway/docs/active-api-owner-map.md) 维护；本文只说明哪些业务资源会在内部复用 `file` 的基础能力。

- `knowledge` 拥有知识库文档、文档详情、文档标签、文档切片和文档内容资源；上传、读取原始文件流和删除底层对象时，在服务边界内调用 `file`。
- `document` 拥有报告模板、报告素材、报告导出文件和文件内容资源；模板文件、素材文件和生成文件的对象写入、读取和删除在内部复用 `file`。

前端仍只看到 owner service 的业务资源 ID 和 content 子资源，不接触 file 内部 ID、bucket、object key、签名 URL 或 MinIO 地址。

## 通用响应结构

JSON 成功、分页和错误响应遵循 [前后端集成契约](../../architecture/frontend-backend-contract.md)。文件内容接口成功时返回文件流，不包裹 JSON envelope；失败时仍返回统一错误响应。前端和调用方应优先匹配 `error.code`，不要解析 `message` 文案。

## 内部服务接口目标契约

`file` 的目标内部契约只表达基础文件对象，不表达 knowledge document、report material、report template 或 report file 等业务语义。

| Method | File Service Path | 说明 |
| --- | --- | --- |
| `GET` | `/healthz` | file 进程存活检查。 |
| `GET` | `/readyz` | file 就绪检查。返回 metadata/storage backend、service token 配置状态和 PostgreSQL dependency 状态。 |
| `POST` | `/internal/v1/files` | 创建基础文件对象，接收 multipart 文件流并返回内部 `fileId` 和基础元数据。 |
| `GET` | `/internal/v1/files/{fileId}` | 查询基础文件元数据。 |
| `DELETE` | `/internal/v1/files/{fileId}` | 删除或标记删除基础文件对象。 |
| `GET` | `/internal/v1/files/{fileId}/content` | 读取原始文件流。 |

`services/file/` 已移除知识库文档形态的历史兼容路由。旧的
`/internal/v1/knowledge-bases/{knowledgeBaseId}/documents` 和
`/internal/v1/documents/{documentId}` 调用面返回统一 `404 not_found`
错误 envelope。owner service 必须使用 `/internal/v1/files/**` 完成基础对象存储，
并在自身边界内维护知识库文档或报告文件等业务资源。

## 内部数据结构

### CreateFileRequest

上传请求使用 `multipart/form-data`。

| 字段 | 类型 | 必填 | 说明 |
| --- | --- | --- | --- |
| `file` | `binary` | 是 | 原始文件内容。 |
| `checksumSha256` | `string` | 否 | 调用方已计算的 SHA-256；缺失时可由 `file` 服务计算。 |

`file` 基础接口不接收 `knowledgeBaseId`、`reportId`、`templateId`、`materialId`、`reportFileId`、业务标签或处理状态。需要这些字段时，由 owner service 在自己的数据库中保存。

### FileObject

```json
{
  "id": "file_123",
  "filename": "设备巡检规范.pdf",
  "contentType": "application/pdf",
  "sizeBytes": 1048576,
  "checksumSha256": "2cf24dba5fb0a30e26e83b2ac5b9e29e1b161e5c1fa7425e73043362938b9824",
  "createdAt": "2026-06-28T10:00:00Z",
  "deletedAt": null
}
```

| 字段 | 类型 | 必填 | 说明 |
| --- | --- | --- | --- |
| `id` | `string` | 是 | file 服务内部文件 ID。前端公开响应不得直接暴露报告文件、模板或素材使用的内部 file ID。 |
| `filename` | `string` | 是 | 展示用原始文件名或规范化文件名。 |
| `contentType` | `string` | 是 | 文件内容类型；缺失或不可信时使用 `application/octet-stream`。 |
| `sizeBytes` | `integer` | 是 | 文件大小。 |
| `checksumSha256` | `string` | 否 | 文件内容 checksum。 |
| `createdAt` | `string(date-time)` | 是 | 创建时间。 |
| `deletedAt` | `string(date-time)` | 否 | 删除时间；未删除时为 `null`。 |

内部响应可包含 `contentType`、`sizeBytes`、`checksumSha256` 等基础 file 对接字段，但不得包含 bucket、object key、内部对象 URL 或存储凭据。

## 文件内容读取

`GET /internal/v1/files/{fileId}/content` 成功时返回原始文件二进制流。

推荐响应头：

| Header | 说明 |
| --- | --- |
| `Content-Type` | 原始文件内容类型；缺失或不可信时使用 `application/octet-stream`。 |
| `Content-Disposition` | 使用安全转义后的原始文件名，通常为 `attachment`。 |
| `Content-Length` | 文件大小，能可靠获得时返回。 |
| `X-Request-Id` | 与响应体或日志一致的 request id。 |

当前目标契约不要求断点续传或 Range 内容读取；如后续支持，需要同步更新 gateway OpenAPI、前后端集成契约和本文档。`file` 服务不得把 MinIO 内部 URL、bucket、object key 或 access key 返回给前端或 owner service 的公开响应。

## 权限与上下文要求

`file` 服务的内部服务认证、owner service 授权责任、公开资源映射和 `401` / `403` 拒绝规则统一维护在 [File 权限矩阵](docs/permission-matrix.md)。README 只保留文件能力和存储边界，不重复维护权限规则。

## 对象存储与元数据要求

- PostgreSQL 只存储基础文件元数据：file ID、原始文件名、内容类型、大小、checksum、内部存储引用、创建时间、删除时间。
- PostgreSQL 不存储 `knowledgeBaseId`、`documentId`、`reportId`、`templateId`、`materialId`、`reportFileId`、业务标签、处理状态或业务权限 ACL。
- MinIO 存储原始文件对象；bucket 名和 object key 是 `file` 服务内部实现细节。
- Object key、bucket、内部对象 URL、MinIO 错误和 access key 不得进入前端响应。
- 上传文件名必须做展示层安全处理，不能直接用于 object key。
- 文件删除应优先保证 owner service 无法再通过内部 `file_ref` 读取；物理删除失败时应有可重试的清理机制。

## 错误码约定

File 相关接口使用项目统一错误码：

| Code | HTTP status | File 场景 |
| --- | --- | --- |
| `validation_error` | `400` | multipart 解析失败、缺少文件、文件为空、checksum 格式非法、文件类型或大小不满足规则。 |
| `unauthorized` | `401` | 缺少可信服务调用上下文或认证无效。 |
| `forbidden` | `403` | 调用方服务无权执行该基础文件操作。 |
| `not_found` | `404` | 文件元数据或原始对象不存在，或已删除。 |
| `conflict` | `409` | 文件状态不允许当前操作。 |
| `rate_limited` | `429` | 上传频率、容量、数量或租户配额超限；配额归属由 owner service 定义。 |
| `dependency_error` | `502` | PostgreSQL、MinIO 或其他已确定依赖失败。 |
| `internal_error` | `500` | 未预期服务端错误。 |

## 安全与日志要求

- 不得在日志、错误响应或追踪字段中记录 object key、内部 URL、access key、token、数据库连接串或完整敏感文件内容。
- 日志建议包含 `service`、`request_id`、`operation`、`file_id`、`caller_service`、`status`、`content_type`、`size_bytes` 等可排查字段。
- 文件名来自用户输入，写入响应头前必须安全转义，避免 header injection。
- 所有跨服务 HTTP client 必须设置超时，并传递 `context.Context`。
- 上传大小、内容类型白名单、危险文件扫描和租户配额属于实现前必须明确的安全策略；业务配额归属仍由 owner service 持有。
- `file` 服务可以记录文件域内结构化日志和 request id，但不拥有全局审计日志查询能力；后续如审计日志独立成服务，file/domain 服务应只对接审计事件生产或查询授权契约。

## 实现状态

当前代码实现、临时后端、文档与实现出入和建议任务统一维护在
[`docs/implementation.md`](docs/implementation.md)。本文档只保留 File Service
的职责边界、内部契约和稳定业务规则；实现缺口不在 README 重复维护。
