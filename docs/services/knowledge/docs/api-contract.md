# 知识管理 API 契约

## 1. 契约目标

本文定义知识管理模块的 HTTP API 契约，覆盖知识库、文档、文档处理、切片、检索、报告支撑材料和知识管理配置。该模块是智能问答和报告生成的数据底座。

主责服务：

- `knowledge`：知识库、文档上传公开资源、文档业务元数据、解析/切片/向量化任务、Qdrant 索引、检索协调和原始文档内容入口。
- `file`：后端内部基础文件对象存储和内容读取能力，由 `knowledge` 在服务边界内复用。
- `parser`：后端内部文档解析运行时，把 raw bytes 转成规范化 parsed content；首期目标为 Python/PaddleOCR，不拥有业务状态。
- `auth`：用户、角色、权限和认证上下文。
- `gateway`：外部 API 入口。
- `ai-gateway`：统一提供 OpenAI-compatible 模型调用入口，供 embedding、rerank 和后续 LLM 能力使用。

边界原则：

- `knowledge` 是 Qdrant 的唯一业务写入方。
- `qa`、`document` 只能通过本契约的知识查询资源复用知识能力，不能直接写 Qdrant。
- 原始文件存储在 File/MinIO 边界；Parser 返回规范化 parsed content，不保存知识业务状态、object key、bucket、内部 URL 或持久化解析产物。
- Knowledge 负责保存业务元数据、chunks、processing jobs 和 Qdrant 索引事实。
- Redis 用于异步任务队列、短期任务状态辅助和缓存；PostgreSQL 保存可追溯业务状态，不把 Redis 作为长期业务真相。

技术基线：

- 后端通用技术栈、数据库、迁移、日志、配置、队列和测试规则以 [`docs/architecture/technology-decisions.md`](../../../architecture/technology-decisions.md) 为准。
- Qdrant 当前使用面较窄，短期以轻量 HTTP client 接入；Knowledge 负责 collection/point 生命周期，但不把 Qdrant 作为业务状态事实来源。
- 文档解析通过 Parser 内部 HTTP API 接入，契约见 [`docs/services/parser/api/internal.openapi.yaml`](../../parser/api/internal.openapi.yaml)；Knowledge 不引入 PaddleOCR/PaddlePaddle/OpenCV/CUDA 运行时依赖。
- embedding、rerank 和后续 LLM 能力通过 AI Gateway profile 调用；Knowledge 不保存 provider API key 明文。

## 2. 通用约定

### 2.1 基础路径

外部 API 统一使用 `/api/v1` 作为网关前缀：

```text
/api/v1/knowledge-bases/...
/api/v1/documents/...
/api/v1/knowledge-queries
```

服务内部可映射到 `knowledge` 或 `file` 服务，但前端只感知网关路径。

### 2.2 RESTful + OpenAPI + Swagger UI 规范

RESTful 路径、动作词限制、分页、时间和通用 OpenAPI 协作规则以 [`docs/architecture/frontend-backend-contract.md`](../../../architecture/frontend-backend-contract.md) 为准。本文只记录 Knowledge 资源如何落到这些通用规则上：`/knowledge-bases`、`/documents`、`/knowledge-queries`、job、attempt 和 query 等资源语义。

OpenAPI 约定：

- `knowledge` 服务维护服务内契约：`services/knowledge/api/openapi.yaml`。
- 当前文档配套的 OpenAPI 草稿见 [public.openapi.yaml](../api/public.openapi.yaml)。
- 涉及知识库文档上传和内容读取的公开接口由 `knowledge` 通过 gateway 维护；`file` 仅提供内部基础文件对象契约：`services/file/api/openapi.yaml`。公开 API 不要求前端先申请 file 上传 URL，也不暴露 file 内部 ID。
- OpenAPI 必须声明 `securitySchemes`、通用错误响应、分页响应、资源 schema、状态枚举和 SSE/异步任务说明。
- API 文档中的 request/response 示例应与本文 Markdown 契约保持一致。

Swagger UI 约定：

- 网关应暴露聚合入口，建议为 `/api/docs`。
- 服务级 OpenAPI JSON/YAML 建议暴露为 `/api/v1/knowledge/openapi.yaml` 或通过网关聚合。
- Swagger UI 只用于开发、测试和内网验收环境；生产环境是否开放需由部署配置控制。

### 2.3 认证与权限

首期统一采用 opaque Bearer token：

```http
Authorization: Bearer <accessToken>
```

`gateway` 或服务侧鉴权中间件负责校验 token，并向下游传递用户 ID、角色和权限上下文。当前不为知识管理 API 单独设计独立会话鉴权通道。

权限要求：

| 能力 | 标准用户 | 管理员 | 超级管理员 |
| --- | --- | --- | --- |
| 查看有权限知识库 | 支持 | 支持 | 支持 |
| 创建/编辑/删除知识库 | 不支持 | 支持 | 支持 |
| 上传/删除文档 | 按角色级 RBAC 和知识库可见性控制 | 支持 | 支持 |
| 修改模型/解析配置 | 不支持 | 支持 | 支持 |
| 检索测试 | 不支持 | 支持 | 支持 |

首期只做角色级 RBAC，不引入组织、电厂、专业等多维数据权限。

### 2.4 通用响应结构

除 `204 No Content` 和原始文件二进制流外，browser-facing JSON 成功、分页和错误响应使用 gateway envelope；格式和通用错误码见 [`docs/architecture/frontend-backend-contract.md`](../../../architecture/frontend-backend-contract.md)。Knowledge 文档只补充知识库、文档、切片、检索和依赖失败的业务场景。

### 2.5 枚举

知识库文档类型：

```text
REGULATION        规程规范
TECHNICAL_REPORT  技术报告论文
TERM              术语条目
GENERAL           通用文档
SUPPORT_MATERIAL  报告支撑材料
```

分段策略：

```text
SEMANTIC_TEXT  语义文本切片
HEADING        基于标题层级智能分段
FIXED_SIZE     固定字符数分段
```

检索策略：

```text
VECTOR         语义向量检索
VECTOR_RERANK  向量检索 + 重排序
```

文档状态：

```text
uploaded
parsing
chunking
embedding
ready
failed
```

`deleted`、`indexing`、`reprocessing` 等只能作为内部状态、软删除字段或 job stage；进入公开 `DocumentStatus` 前必须先更新 gateway OpenAPI 和本文档。

处理任务状态：

```text
queued
running
succeeded
failed
cancelled
```

### 2.6 Worker、检索与契约测试解耦

以下规则用于解除 A-12、A-14 对 A-11 runtime 完成度的直接依赖。A-11
仍负责真实解析、切片、embedding 和 Qdrant 写入；A-12 和 A-14
只依赖本节定义的稳定数据契约。

稳定交接面不是 asynq worker 进程本身，而是 Knowledge 拥有的
PostgreSQL 行和 Qdrant 最小 payload：

- `knowledge_documents.status=ready` 且 `deleted_at IS NULL` 的文档可作为检索候选。
- `document_chunks` 必须保存 `id`、`knowledge_base_id`、`document_id`、
  `chunk_index`、`content`、`token_count`、`section_path`、`chunk_type`、
  `metadata`、`qdrant_point_id`、`embedding_provider` 和 `embedding_dimension`。
- Qdrant payload 必须至少包含 `knowledge_base_id`、`document_id`、
  `chunk_id` 和 `chunk_index`，可包含 `tags`、`chunk_type`、`section_path`
  和过滤用 `metadata`。
- 展示字段、权限判断、文档状态判断和删除状态判断必须回 PostgreSQL hydrate；
  不得把 Qdrant payload 当作业务事实来源。

A-12 的 `knowledge-queries` 实现可以在单元测试和契约测试中直接 seed
上述文档、chunk 和 vector hit fixture，或使用 fake Qdrant/AI Gateway adapter。
这类测试不要求 A-11 worker、真实 Parser service、真实 Qdrant 或真实 embedding profile
已经可运行。无命中、低分、无权限、文档未 `ready` 或已删除时，必须按本契约返回
稳定空结果或统一错误 envelope。

A-14 的 active operation 契约测试、错误 envelope 测试和 request id 测试可以使用
seeded repository、fake file client、fake parser client、fake queue、fake vector index 和 fake AI Gateway。
只有跨服务 smoke 或“上传 -> worker -> Parser -> Qdrant -> 检索”的端到端验收需要等待
A-11 runtime。端到端 smoke 可以登记为 integration follow-up，不应阻塞 A-14
对公开契约、路由、错误和状态流转的测试收口。

## 3. 数据对象

### 3.1 KnowledgeBase

```json
{
  "id": "kb_001",
  "name": "技术监督规程库",
  "description": "电厂技术监督相关规程和术语",
  "docType": "REGULATION",
  "visibility": "private",
  "chunkStrategy": {
    "type": "SEMANTIC_TEXT",
    "chunkSize": 1600,
    "overlap": 200,
    "separators": ["\n\n", "\n", "。"]
  },
  "retrievalStrategy": {
    "mode": "VECTOR_RERANK",
    "topK": 8,
    "scoreThreshold": 0.35,
    "rerankTopN": 5
  },
  "documentCount": 128,
  "chunkCount": 9800,
  "createdBy": "user_001",
  "createdAt": "2026-06-28T10:00:00Z",
  "updatedAt": "2026-06-28T10:00:00Z"
}
```

权限说明：

- 首期按角色级 RBAC 和知识库可见性控制访问。
- `private`、`team`、`public` 可作为可见性枚举保留；组织、电厂、专业等多维权限不作为首期要求。
- `team` 首期可按角色级 RBAC 和创建人范围实现，不要求接入组织树。

### 3.2 KnowledgeDocument

```json
{
  "id": "doc_001",
  "knowledgeBaseId": "kb_001",
  "name": "技术监督规程.pdf",
  "contentType": "application/pdf",
  "sizeBytes": 1024000,
  "status": "ready",
  "tags": ["锅炉", "2026"],
  "chunkCount": 86,
  "errorCode": null,
  "errorMessage": null,
  "parserBackend": "text",
  "createdBy": "user_001",
  "jobId": "job_001",
  "createdAt": "2026-06-28T10:00:00Z",
  "updatedAt": "2026-06-28T10:10:00Z"
}
```

### 3.3 DocumentChunk

```json
{
  "id": "chunk_001",
  "documentId": "doc_001",
  "knowledgeBaseId": "kb_001",
  "chunkIndex": 1,
  "sectionPath": "1. 总则 / 1.1 适用范围",
  "chunkType": "text",
  "content": "本规程适用于...",
  "tokenCount": 320,
  "qdrantPointId": "550e8400-e29b-41d4-a716-446655440000",
  "metadata": {
    "page": 3
  },
  "createdAt": "2026-06-28T10:10:00Z"
}
```

### 3.4 KnowledgeQueryResult

```json
{
  "chunkId": "chunk_001",
  "documentId": "doc_001",
  "knowledgeBaseId": "kb_001",
  "documentName": "技术监督规程.pdf",
  "sectionPath": "1. 总则 / 1.1 适用范围",
  "score": 0.82,
  "contentPreview": "本规程适用于...",
  "chunkIndex": 1,
  "tags": ["锅炉", "2026"]
}
```

## 4. 知识库 API

### 4.1 创建知识库

```http
POST /api/v1/knowledge-bases
```

请求：

```json
{
  "name": "技术监督规程库",
  "description": "电厂技术监督相关规程和术语",
  "docType": "REGULATION",
  "visibility": "private",
  "chunkStrategy": {
    "type": "HEADING",
    "chunkSize": 1200,
    "overlap": 200,
    "separators": ["\n\n", "\n", "。"]
  },
  "retrievalStrategy": {
    "mode": "VECTOR_RERANK",
    "topK": 8,
    "scoreThreshold": 0.35,
    "rerankTopN": 5
  }
}
```

响应：`201 Created`

```json
{
  "data": {
    "id": "kb_001",
    "name": "技术监督规程库",
    "docType": "REGULATION",
    "visibility": "private",
    "documentCount": 0,
    "chunkCount": 0,
    "createdAt": "2026-06-28T10:00:00Z"
  },
  "requestId": "req_123"
}
```

校验规则：

- `name` 必填，建议同一可见范围内唯一。
- `docType` 必须是允许枚举。
- `chunkStrategy.type=FIXED_SIZE` 时必须提供 `chunkSize` 和 `overlap`。
- `retrievalStrategy.mode=VECTOR_RERANK` 时需要存在可用重排序模型配置。

### 4.2 查询知识库列表

```http
GET /api/v1/knowledge-bases?page=1&pageSize=20
```

响应：

```json
{
  "data": [
    {
      "id": "kb_001",
      "name": "技术监督规程库",
      "docType": "REGULATION",
      "visibility": "private",
      "documentCount": 128,
      "chunkCount": 9800,
      "createdBy": "user_001",
      "createdAt": "2026-06-28T10:00:00Z"
    }
  ],
  "page": {
    "page": 1,
    "pageSize": 20,
    "total": 1
  },
  "requestId": "req_123"
}
```

### 4.3 获取知识库详情

```http
GET /api/v1/knowledge-bases/{knowledgeBaseId}
```

响应：`data` 为 `KnowledgeBase`

### 4.4 更新知识库

```http
PATCH /api/v1/knowledge-bases/{knowledgeBaseId}
```

请求：

```json
{
  "name": "技术监督规程库",
  "description": "更新后的描述",
  "chunkStrategy": {
    "type": "FIXED_SIZE",
    "chunkSize": 1200,
    "overlap": 200,
    "separators": ["\n\n", "\n", "。"]
  },
  "retrievalStrategy": {
    "mode": "VECTOR_RERANK",
    "topK": 10,
    "scoreThreshold": 0.35,
    "rerankTopN": 5
  }
}
```

响应：`data` 为 `KnowledgeBase`

状态影响：

- 分段策略变更后，所有 `ready` 文档需要进入后台重处理。
- 检索策略变更不一定需要重建向量，但如果影响 embedding 模型或向量维度，则必须重建索引。

### 4.5 删除知识库

```http
DELETE /api/v1/knowledge-bases/{knowledgeBaseId}
```

响应：`204 No Content`

规则：

- 删除前必须校验权限。
- 首期采用软删除；Qdrant 向量、MinIO 文件引用和后台清理由生命周期任务处理。
- 删除知识库时应处理 PostgreSQL 元数据、Qdrant 向量、MinIO 文件引用的生命周期。

### 4.6 创建知识库删除任务

候选扩展接口，尚未进入 gateway active public OpenAPI；进入公开契约前必须先更新 `docs/services/gateway/api/openapi.yaml`。

```http
POST /api/v1/knowledge-base-deletion-jobs
```

请求：

```json
{
  "ids": ["kb_001", "kb_002"]
}
```

响应：

```json
{
  "data": {
    "id": "kbdel_001",
    "status": "queued",
    "targetIds": ["kb_001", "kb_002"],
    "failed": [
      {
        "id": "kb_002",
        "code": "forbidden",
        "message": "no permission"
      }
    ]
  },
  "requestId": "req_123"
}
```

规则：

- 批量删除建模为 deletion job 资源，不使用 `batch-delete` 动作路径。

## 5. 文档 API

### 5.1 上传文档

```http
POST /api/v1/knowledge-bases/{knowledgeBaseId}/documents
```

请求使用 `multipart/form-data`。Knowledge 创建知识库文档资源并在内部调用 file 服务保存底层原始文件对象。

| 字段 | 类型 | 必填 | 说明 |
| --- | --- | --- | --- |
| `file` | binary | 是 | 原始文件。 |
| `tags` | string[]/json string | 否 | 文档标签；multipart 中可用 JSON 字符串编码。 |

响应：`201 Created`

```json
{
  "data": {
    "id": "doc_001",
    "knowledgeBaseId": "kb_001",
    "name": "技术监督规程.pdf",
    "status": "uploaded",
    "jobId": "job_001",
    "createdAt": "2026-06-28T10:00:00Z"
  },
  "requestId": "req_123"
}
```

### 5.2 查询文档列表

```http
GET /api/v1/knowledge-bases/{knowledgeBaseId}/documents?page=1&pageSize=20&status=ready&q=规程
```

响应：

```json
{
  "data": [
    {
      "id": "doc_001",
      "name": "技术监督规程.pdf",
      "status": "ready",
      "tags": ["锅炉", "2026"],
      "chunkCount": 86,
      "createdAt": "2026-06-28T10:00:00Z"
    }
  ],
  "page": {
    "page": 1,
    "pageSize": 20,
    "total": 1
  },
  "requestId": "req_123"
}
```

### 5.3 获取文档详情

```http
GET /api/v1/documents/{documentId}
```

响应：`data` 为 `KnowledgeDocument`

### 5.4 更新文档标签

```http
PATCH /api/v1/documents/{documentId}
```

请求：

```json
{
  "tags": ["锅炉", "2026"]
}
```

响应：`data` 为 `KnowledgeDocument`

### 5.5 删除文档

```http
DELETE /api/v1/documents/{documentId}
```

响应：`204 No Content`

规则：

- 删除文档必须同步标记 Qdrant 向量生命周期。
- 如果历史问答引用了该文档，引用详情应返回“原文已删除或无权限访问”的 fallback。
- 首期不立即硬删原始 MinIO 对象；通过 `file` service 生命周期和后台清理策略处理。
- 首期删除只做软删除，原始文件对象保留到后台生命周期任务确认无引用后清理。

### 5.6 创建文档删除任务

候选扩展接口，尚未进入 gateway active public OpenAPI；进入公开契约前必须先更新 `docs/services/gateway/api/openapi.yaml`。

```http
POST /api/v1/document-deletion-jobs
```

请求：

```json
{
  "ids": ["doc_001", "doc_002"]
}
```

响应结构同知识库删除任务。

### 5.7 创建文档处理任务

候选扩展接口，尚未进入 gateway active public OpenAPI；进入公开契约前必须先更新 `docs/services/gateway/api/openapi.yaml`。

```http
POST /api/v1/documents/{documentId}/processing-jobs
```

响应：

```json
{
  "data": {
    "id": "job_002",
    "documentId": "doc_001",
    "status": "queued"
  },
  "requestId": "req_123"
}
```

规则：

- 仅 `failed` 或管理员允许重处理的状态可创建新的处理任务。
- 重新处理需要保留上一次失败原因供排查。
- 自动尝试已满 3 次后仍允许管理员通过任务或任务尝试资源手动排队。

### 5.8 获取文档切片

```http
GET /api/v1/documents/{documentId}/chunks?page=1&pageSize=50
```

响应：

```json
{
  "data": [
    {
      "id": "chunk_001",
      "chunkIndex": 1,
      "sectionPath": "1. 总则",
      "chunkType": "text",
      "content": "本规程适用于...",
      "tokenCount": 320
    }
  ],
  "page": {
    "page": 1,
    "pageSize": 50,
    "total": 86
  },
  "requestId": "req_123"
}
```

### 5.9 读取原文内容

```http
GET /api/v1/documents/{documentId}/content
```

响应：原始文件二进制流。

规则：

- 必须先校验文档访问权限。
- 不得返回内部 MinIO object key 或内部存储 URL。
- 审计日志首期暂缓，后续可接入独立审计服务。

## 6. 文档处理任务 API

本节为候选扩展接口，尚未进入 gateway active public OpenAPI；当前服务内实现优先走 `services/knowledge/api/openapi.yaml` 的 `/internal/v1/**` contract。进入 browser-facing 契约前必须先更新 gateway OpenAPI。

### 6.1 获取处理任务

```http
GET /api/v1/knowledge-processing-jobs/{jobId}
```

响应：

```json
{
  "data": {
    "id": "job_001",
    "documentId": "doc_001",
    "status": "running",
    "stage": "embedding",
    "attemptCount": 1,
    "maxAttempts": 3,
    "progress": {
      "current": 42,
      "total": 86
    },
    "errorMessage": null,
    "attempts": [
      {
        "attempt": 1,
        "stage": "embedding",
        "status": "running",
        "startedAt": "2026-06-28T10:04:00Z"
      }
    ],
    "createdAt": "2026-06-28T10:00:00Z",
    "updatedAt": "2026-06-28T10:05:00Z"
  },
  "requestId": "req_123"
}
```

规则：

- PostgreSQL 中的 processing job 是权威状态；Redis 只用于队列投递、短期进度和并发协调。
- 自动尝试最多 3 次，超过后进入 `failed`；手动排队通过 `POST /api/v1/knowledge-processing-jobs/{jobId}/attempts` 创建新的任务尝试并递增 `attemptCount`。
- `attempts` 最多返回最近 10 次尝试摘要，包含阶段、状态、错误信息和时间字段。

### 6.2 创建知识库处理任务

```http
POST /api/v1/knowledge-bases/{knowledgeBaseId}/processing-jobs
```

请求：

```json
{
  "documentIds": ["doc_001"],
  "reason": "segmentation_changed"
}
```

响应：

```json
{
  "data": [
    {
      "id": "job_010",
      "documentId": "doc_001",
      "status": "queued"
    }
  ],
  "requestId": "req_123"
}
```

### 6.3 创建处理任务尝试

```http
POST /api/v1/knowledge-processing-jobs/{jobId}/attempts
```

响应：

```json
{
  "data": {
    "id": "attempt_002",
    "processingJobId": "job_001",
    "attempt": 2,
    "status": "queued"
  },
  "requestId": "req_123"
}
```

## 7. 知识查询 API

### 7.1 创建知识查询

```http
POST /api/v1/knowledge-queries
```

请求：

```json
{
  "query": "锅炉技术监督有哪些检查要求？",
  "knowledgeBaseIds": ["kb_001", "kb_002"],
  "topK": 8,
  "scoreThreshold": 0.35,
  "tags": ["锅炉", "2026"],
  "metadataFilter": {
    "专业": "锅炉",
    "年份": "2026"
  },
  "rerank": true,
  "rerankTopN": 5
}
```

响应：

```json
{
  "data": {
    "id": "kq_001",
    "query": "锅炉技术监督有哪些检查要求？",
    "results": [
      {
        "chunkId": "chunk_001",
        "documentId": "doc_001",
        "knowledgeBaseId": "kb_001",
        "documentName": "技术监督规程.pdf",
        "sectionPath": "1. 总则 / 1.1 适用范围",
        "score": 0.82,
        "contentPreview": "本规程适用于...",
        "chunkIndex": 1,
        "tags": ["锅炉", "2026"]
      }
    ],
    "trace": {
      "embeddingProvider": "ai-gateway",
      "embeddingModel": "embedding-model-name",
      "embeddingDimension": 1024,
      "qdrantCollection": "knowledge_chunks",
      "searchTopK": 8,
      "scoreThreshold": 0.35,
      "hitCount": 1,
      "rerank": true,
      "rerankTopN": 5
    }
  },
  "requestId": "req_123"
}
```

规则：

- 必须过滤用户无权限访问的知识库和文档。
- browser-facing API 返回 `contentPreview`，不得返回原始向量、完整 Qdrant payload、prompt、object key 或 provider 原始响应体。
- `qa` 和 `document` 应通过该接口复用检索能力。
- 检索建模为创建 `knowledge-query` 资源，不使用 `search` 动作路径。

### 7.2 创建知识查询测试

管理员接口：

候选扩展接口，尚未进入 gateway active public OpenAPI；进入公开契约前必须先更新 `docs/services/gateway/api/openapi.yaml`。

```http
POST /api/v1/knowledge-query-tests
```

请求同 `knowledge-queries`，可额外包含：

```json
{
  "name": "锅炉召回测试"
}
```

响应：

```json
{
  "data": {
    "id": "rt_001",
    "results": [],
    "createdAt": "2026-06-28T10:00:00Z"
  },
  "requestId": "req_123"
}
```

## 8. 报告支撑材料 API

报告支撑材料指报告生成复用的专业业务文档，例如厂级专业报告、技术文档、检查报告。它不是 UI 素材，也不是普通附件。

报告支撑材料首期作为候选扩展资源建模，尚未进入 gateway active public OpenAPI；如该资源仍由 `knowledge` 暴露，则由 `knowledge` 接收 multipart 上传并在内部复用 `file` 的基础文件能力。需要检索时复用 `knowledge` 的处理和查询能力，避免和普通知识库文档混淆。

### 8.1 创建报告支撑材料

```http
POST /api/v1/knowledge-support-materials
```

请求使用 `multipart/form-data`。

| 字段 | 类型 | 必填 | 说明 |
| --- | --- | --- | --- |
| `file` | binary | 是 | 支撑材料原始文件。 |
| `name` | string | 是 | 材料名称。 |
| `materialType` | string | 是 | 材料类型。 |
| `tags` | string[]/json string | 否 | 标签；multipart 中可用 JSON 字符串编码。 |

响应：

```json
{
  "data": {
    "id": "mat_001",
    "name": "某电厂迎峰度夏检查材料",
    "materialType": "plant_report",
    "status": "uploaded",
    "jobId": "job_020"
  },
  "requestId": "req_123"
}
```

### 8.2 查询报告支撑材料

```http
GET /api/v1/knowledge-support-materials?page=1&pageSize=20&type=plant_report&tag.专业=锅炉
```

响应：分页列表。

### 8.3 更新标签

```http
PATCH /api/v1/knowledge-support-materials/{materialId}
```

请求：

```json
{
  "tags": ["A电厂", "锅炉", "2026"]
}
```

### 8.4 删除材料

```http
DELETE /api/v1/knowledge-support-materials/{materialId}
```

响应：`204 No Content`

## 9. 配置 API

本节为候选扩展接口。当前公开 runtime/admin 配置能力以 gateway 的 admin-runtime-config 契约为准；Knowledge 仅维护 parser/processing 相关服务内配置。

### 9.1 获取知识管理配置

```http
GET /api/v1/knowledge-settings
```

响应：

```json
{
  "data": {
    "embeddingModel": {
      "provider": "ai-gateway",
      "profileId": "mp_embedding_default",
      "model": "embedding-model-name",
      "dimension": 1024
    },
    "rerankModel": {
      "provider": "ai-gateway",
      "profileId": "mp_rerank_default",
      "model": "rerank-model-name",
      "topN": 20
    },
    "parser": {
      "backend": "external_api",
      "baseUrl": "https://parser.example.com",
      "maxConcurrency": 4
    }
  },
  "requestId": "req_123"
}
```

### 9.2 更新知识管理配置

```http
PATCH /api/v1/knowledge-settings
```

请求：

```json
{
  "embeddingModel": {
    "provider": "ai-gateway",
    "profileId": "mp_embedding_default",
    "model": "embedding-model-name",
    "dimension": 1024
  },
  "rerankModel": {
    "provider": "ai-gateway",
    "profileId": "mp_rerank_default",
    "model": "rerank-model-name",
    "topN": 20
  },
  "parser": {
    "backend": "external_api",
    "baseUrl": "https://parser.example.com",
    "apiKey": "<write-only secret>",
    "timeoutSeconds": 120,
    "maxConcurrency": 4
  }
}
```

响应：

```json
{
  "data": {
    "updatedAt": "2026-06-28T10:00:00Z"
  },
  "requestId": "req_123"
}
```

规则：

- 模型配置中的 `profileId` 指向 AI Gateway 中的 embedding 或 rerank profile；`knowledge` 不保存 provider `baseUrl` 或 `apiKey`，也不直接适配多个模型供应商。
- 配置变更应记录变更人和时间。
- `parser.backend` 首期固定为 `external_api`；`parser.apiKey` 只允许写入，不允许明文读取。
- embedding 维度或模型族变化时创建新的 Qdrant collection 版本，并通过后台任务重建索引；旧 collection 保留到切换完成后清理。

## 10. 统计 API

候选扩展接口，尚未进入 gateway active public OpenAPI；进入公开契约前必须先更新 `docs/services/gateway/api/openapi.yaml`。

```http
GET /api/v1/knowledge-statistics/overview
```

响应：

```json
{
  "data": {
    "knowledgeBaseCount": 12,
    "documentCount": 128,
    "chunkCount": 9800,
    "uploadTrend30d": [
      {
        "date": "2026-06-28",
        "count": 6
      }
    ]
  },
  "requestId": "req_123"
}
```

## 11. 存储与数据归属

| 数据 | 存储 | 所有者 |
| --- | --- | --- |
| 知识库元数据 | PostgreSQL | `knowledge` |
| 文档元数据和状态 | PostgreSQL | `knowledge` |
| 文件对象和内容读取授权 | MinIO + PostgreSQL 元数据；bucket 首期分为 `source-files`、`templates`、`generated-reports` | `file` |
| 切片元数据 | PostgreSQL | `knowledge` |
| 向量和检索 payload | Qdrant | `knowledge` |
| 处理任务状态 | PostgreSQL 持久化，`asynq` over Redis 队列和短期状态辅助；自动重试最多 3 次 | `knowledge` |
| 模型配置 | PostgreSQL 保存业务默认参数和 AI Gateway profile 引用；provider 密钥由 AI Gateway 管理 | `knowledge` / `ai-gateway` |

## 12. 已确认决策与后续跟踪

| 编号 | 结论 |
| --- | --- |
| K1 | 首期采用角色级 RBAC 和知识库可见性，不做组织/电厂/专业多维权限。 |
| K2 | 报告支撑材料是独立资源，复用 `file` service 和必要的 `knowledge` 检索能力。 |
| K3 | 文档删除首期按软删除设计；Qdrant 和 MinIO 清理在后台生命周期任务中处理。 |
| K4 | 文档解析/OCR 首期使用外部 HTTP 解析服务，通过 `parser.baseUrl`、`apiKey`、`timeoutSeconds`、`maxConcurrency` 配置。 |
| K5 | 异步任务采用 `asynq` over Redis + PostgreSQL 持久化状态。 |
| K6 | embedding 维度或模型族变化后创建版本化 Qdrant collection，并通过后台任务重建索引。 |
| K7 | 任务自动重试最多 3 次，PostgreSQL job 保留最近 10 次尝试摘要。 |
| K8 | MinIO bucket 首期拆为 `source-files`、`templates`、`generated-reports` 三类，实际名称由部署配置决定。 |
| K9 | 审计日志首期暂缓，不作为知识管理 API 的强制验收项；首期保留配置变更、任务失败和删除结果等排查字段。 |
