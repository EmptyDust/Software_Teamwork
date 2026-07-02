# Knowledge 服务接口文档

本文档定义 `knowledge` 服务在项目初期的职责边界和 gateway 公开接口。详细字段、状态码、response envelope 和 schema 以 [`docs/services/gateway/api/public.openapi.yaml`](../gateway/api/public.openapi.yaml) 为准。前端不得直接调用 `services/knowledge`，只能通过 gateway 暴露的 `/api/v1/**` 入口访问知识库能力。

RESTful 路径、统一响应和错误 envelope 以 [前后端集成契约](../../architecture/frontend-backend-contract.md) 为准。知识检索使用 `knowledge-queries` 资源表示，不使用 `/search`、`/retrieval/search` 或其他动作式路径。

## 文档入口

| 文档 | 说明 |
| --- | --- |
| [API 契约](docs/api-contract.md) | 知识管理公开接口、权限、错误码和跨服务边界。 |
| [数据模型](docs/data-models.md) | Knowledge Service 拥有的 PostgreSQL、Qdrant 和运行时逻辑模型。 |
| [权限矩阵](docs/permission-matrix.md) | 知识库、文档、检索和 parser config 的角色/权限矩阵。 |
| [实现说明](docs/implementation.md) | 当前代码实现、契约对齐、缺口、临时后端和最近检查记录。 |
| [Parser Runtime 服务文档](../parser/README.md) | 文档解析运行时和 PaddleOCR 边界；Knowledge 只通过内部 HTTP 调用。 |

## 任务解耦契约

A-11 ingestion worker、A-12 `knowledge-queries` 检索和 A-14 契约测试通过
[`API 契约 2.6`](docs/api-contract.md#26-worker检索与契约测试解耦) 解耦。
A-12/A-14 可以依赖 `knowledge_documents`、`document_chunks` 和 Qdrant 最小
payload 的稳定契约，通过 seeded repository 或 fake vector/AI adapter 验证
检索、错误 envelope 和 request id。A-021 已新增 env-gated ingestion 真实依赖
smoke，覆盖一个 fixture 文档从 File Service、Parser Service、Knowledge worker 到
Qdrant point 写入和状态更新；同时新增 Gateway -> Knowledge owner route smoke，覆盖
伪造 `X-User-*` 拒绝、Gateway session 创建、`GET /api/v1/knowledge-bases` 和 KB
`createdBy` 真实 session user 断言。完整上传到检索、rerank、MCP/Gateway 总入口仍由
后续跨服务 smoke 覆盖。文档删除清理 worker 已消费
`knowledge:document:delete_cleanup`，负责在软删除后幂等清理 File 引用和
Qdrant points；同进程 reconciler 会从 PostgreSQL 重投 retryable cleanup job
以补偿短暂 Redis/asynq handoff 失败。Redis/asynq 只承载投递，PostgreSQL 的
document/job 状态仍是事实来源。

## 技术基线

Knowledge Service 的工程选型以 [技术选型基线](../../architecture/technology-decisions.md) 为准。本服务只补充知识域特有约束：

- 文档入库、重处理和删除清理使用 `asynq` over Redis；PostgreSQL 仍是 job 状态、失败摘要和重试次数的事实来源。
- 原始文档解析运行时由内部 Parser service 提供；Knowledge 不承载 PaddleOCR、PaddlePaddle、OpenCV、CUDA 或模型加载依赖。
- Qdrant 只保存向量和最小检索 payload；知识库、文档处理状态、chunks 和权限相关状态仍归 PostgreSQL 与 owner service。
- embedding、rerank 和后续 LLM 能力通过 AI Gateway 的 OpenAI-compatible profile 接入；Knowledge 不保存 provider API key 明文。

## 职责边界

| 范围 | 说明 |
| --- | --- |
| 知识库元数据 | 创建、查询、更新和删除知识库，维护文档类型、切片策略和检索策略。 |
| 文档处理状态 | 维护文档从 `uploaded` 到 `ready` 或 `failed` 的处理状态、错误摘要和统计字段。 |
| 文档解析协调与切片 | 调用 Parser service 获取 parsed content，并在 Knowledge 内做语义切片和切片详情保存。 |
| 向量索引 | 生成 embedding，维护 Qdrant collection、point 和检索 payload。 |
| 删除清理 | 文档删除后消费 `delete_cleanup` job，调用 File Service 删除不透明 `file_ref`，并按 `document_id` 清理 Qdrant points。 |
| 检索查询 | 根据 query、知识库范围、Top K、阈值和标签过滤返回召回结果。 |

`knowledge` 不负责用户登录、RBAC 源数据、底层对象存储实现、OCR/PaddleOCR
运行时、LLM 回答生成或 DOCX 报告导出。知识库文档公开资源、处理状态和原始文件流入口由
`knowledge` 拥有；底层原始文件对象可在服务边界内复用 `file` 的基础能力，解析运行时通过
`parser` 内部服务调用。

## 接入模型

```text
frontend
   |
   v
gateway knowledge resources
   |
   v
knowledge service
   |
   +--> PostgreSQL metadata, document status, chunks
   +--> Qdrant vectors and retrieval payload
   +--> asynq over Redis for async ingestion/indexing workers
   +--> File service base file APIs for raw source bytes
   +--> Parser service /internal/v1/parsed-documents for normalized parsed content
   +--> AI Gateway /internal/v1/embeddings and /internal/v1/rerankings
```

Knowledge 的认证上下文、角色/权限矩阵、parser config 管理权限和拒绝规则统一维护在 [权限矩阵](docs/permission-matrix.md)。README 不重复维护 header 表或角色权限表。

## 公开资源范围

Knowledge 已进入 Gateway active contract 的公开资源包括：

- `knowledge-bases`：知识库创建、查询、更新和删除。
- `knowledge-bases/{knowledgeBaseId}/documents`：知识库文档上传和列表。
- `documents/{documentId}`：Knowledge-owned 文档详情、标签更新和删除。
- `documents/{documentId}/chunks`：文档切片详情。
- `documents/{documentId}/content`：知识库原始文件流，底层 bytes 可由 Knowledge 从 File Service 读取。
- `knowledge-queries`：创建一次知识检索查询并返回召回结果。

逐项 method、path、schema、认证和错误响应以 [`docs/services/gateway/api/public.openapi.yaml`](../gateway/api/public.openapi.yaml) 和 [Gateway Active API Owner Map](../gateway/docs/active-api-owner-map.md) 为准。服务级 [`api/public.openapi.yaml`](api/public.openapi.yaml) 还包含候选扩展资源；未进入 Gateway active paths 的内容不是前端稳定公开契约。

## 数据结构

公开响应统一使用 gateway envelope；格式、分页和错误响应见 [前后端集成契约](../../architecture/frontend-backend-contract.md)。

核心公开 schema：

| Schema | 说明 |
| --- | --- |
| `KnowledgeBaseSummary` | 知识库 ID、名称、描述、文档类型、切片策略、检索策略、文档数、切片数和时间字段。 |
| `DocumentSummary` | 文档 ID、知识库 ID、文件名、处理状态、错误摘要、切片数、标签和解析信息。 |
| `DocumentChunk` | 切片 ID、章节路径、切片文本、token 数、embedding 元数据和 Qdrant point ID。 |
| `KnowledgeQueryRequest` | query、knowledgeBaseIds、topK、scoreThreshold、tags、metadataFilter、rerank 配置。 |
| `KnowledgeQuerySummary` | 检索请求 ID、原始 query、召回结果列表和 trace。 |

字段详情以 [`docs/services/gateway/api/public.openapi.yaml`](../gateway/api/public.openapi.yaml) 为准，不在本文档重复定义完整 schema。

## 状态约定

`DocumentStatus` 公开枚举：

```text
uploaded | parsing | chunking | embedding | ready | failed
```

`indexing`、`reprocessing`、`deleted` 等内部阶段或扩展状态进入公开 API 前，必须先更新 gateway OpenAPI、前后端契约和本文档。

## 检索约定

知识检索使用 `knowledge-queries` 资源创建语义，精确 method、path 和 schema 以 Gateway OpenAPI 为准。

请求语义：

| 字段 | 说明 |
| --- | --- |
| `query` | 用户检索问题或关键词。 |
| `knowledgeBaseIds` | 可选知识库范围；空数组表示由权限和默认策略决定范围。 |
| `topK` | 向量召回数量上限，默认 10，范围 1-100。 |
| `scoreThreshold` | 相似度阈值，默认 0.35，低于阈值的结果应过滤。 |
| `tags` | 标签过滤条件。 |
| `metadataFilter` | 扩展元数据过滤条件。 |
| `rerank` | 是否请求重排序；配置 AI Gateway rerank adapter 时调用 `/internal/v1/rerankings`。 |
| `rerankTopN` | 重排序后保留数量，必须小于等于 `topK`；未配置 reranker 时仍会按向量顺序截断。 |

响应必须返回可溯源字段，例如 `knowledgeBaseId`、`documentId`、`chunkId`、`documentName`、`sectionPath`、`score` 和 `contentPreview`。不要向前端返回原始向量、完整 Qdrant payload、内部 object key、prompt 或下游服务 URL。

检索实现必须从 Qdrant hit 中读取最小 payload 后回 PostgreSQL hydrate。测试中允许用
seeded `document_chunks` 和 fake vector hit 替代真实 worker/Qdrant，只要请求、
响应、过滤、权限和错误 envelope 与 gateway OpenAPI 一致。

## 与 File Service 的边界

知识库文档上传入口由 `knowledge` 拥有，精确 method、path 和 multipart schema 以 Gateway OpenAPI 为准。Knowledge Service 负责接收 gateway 转发的 multipart、创建知识库文档资源、保存内部不透明 `file_ref`、维护处理状态、chunks、embedding、Qdrant 索引和检索。Knowledge 可在服务边界内调用 File Service 的 `/internal/v1/files/**` 基础接口保存、读取和删除底层原始文件对象，并调用 Parser Service 的 `/internal/v1/parsed-documents` 将 raw bytes 转成规范化 parsed content；File Service 独占 bucket、object key、MinIO URL、签名 URL、storage backend 和凭据，Knowledge 不读取、不推断、不暴露这些存储细节。File Service 不保存 `knowledgeBaseId`、文档处理状态、chunks 或索引状态，Parser Service 不保存业务状态、chunks、embedding 或 Qdrant point。gateway 不能直接解析文件或操作 Qdrant。

## 错误码约定

Knowledge 相关接口使用项目统一错误码：

| Code | HTTP status | Knowledge 场景 |
| --- | --- | --- |
| `validation_error` | `400` | 请求体或查询参数格式错误，例如 `query` 为空、`topK` 超出范围、策略配置非法。 |
| `unauthorized` | `401` | 缺少认证凭据或 gateway 未注入有效用户上下文。 |
| `forbidden` | `403` | 已认证但无权访问目标知识库、文档或检索范围。 |
| `not_found` | `404` | 知识库、文档或切片不存在，或对当前用户隐藏。 |
| `conflict` | `409` | 当前资源状态不允许修改、删除或重新处理。 |
| `rate_limited` | `429` | 检索、上传或处理任务超过配额。 |
| `dependency_error` | `502` | PostgreSQL、Qdrant、Redis、File、Parser、AI Gateway 或其他依赖失败。 |
| `internal_error` | `500` | 未预期服务端错误。 |

错误响应不得包含 SQL、object key、MinIO 内部路径、Parser 内部文件路径、OCR debug output、原始向量、prompt、API key、token 或堆栈。

## 实现状态

当前代码实现、临时后端、文档与实现出入和建议任务统一维护在
[`docs/implementation.md`](docs/implementation.md)。本文档只保留 Knowledge
Service 的职责边界、公开资源语义和稳定业务规则；实现缺口不在 README
重复维护。
