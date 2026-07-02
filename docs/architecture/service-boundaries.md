# 服务边界矩阵

本文档用于约束 `gateway`、`auth`、`file`、`knowledge`、`parser`、`qa`、`document`、`ai-gateway` 的职责归属，避免早期并行开发时把业务规则堆进 gateway 或把 provider 细节泄露到领域服务外。

所有公开 gateway API 和服务间 HTTP API 必须使用 RESTful 资源路径，由 HTTP method 表达动作。除 `/healthz`、`/readyz` 外，不在稳定 path 中使用 `login`、`logout`、`register`、`download`、`search`、`generate`、`export`、`retry`、`revoke` 等动作词。

## 总览

| 服务 | 负责 | 通过 gateway 暴露 | 不得负责 |
| --- | --- | --- | --- |
| `gateway` | 面向前端、管理端、后端模块和工具调用方的公开 API；路由；基于 Redis 的会话缓存；认证上下文透传；响应/错误包裹结构；请求 ID；轻量聚合。 | `/api/v1/**`、`/healthz`、`/readyz`。 | 持久化用户/角色/权限、文档解析、向量检索、LLM 工作流、报告生成业务逻辑。 |
| `auth` | 用户、凭证、角色、权限、会话或令牌、会话身份签发和撤销。 | 用户创建、会话创建/删除、当前用户、权限检查、供 gateway 缓存的会话身份。 | 文件元数据、知识索引、QA 消息、报告记录。 |
| `file` | 基础文件上传/内容 API、原始对象、对象存储协调、最小 file 元数据生命周期、面向后端服务的 MinIO 中间层。 | 不直接拥有前端公开 API；通过内部 `/internal/v1/files/**` 为 `knowledge`、`document` 等 owner service 提供基础文件能力。 | 知识库归属、知识文档状态、知识分块、向量索引、RAG、报告生成、报告材料/模板/报告文件业务状态、QA 会话附件元数据/解析状态/临时 chunk 归属。QA 会话附件原始 bytes 通过内部 file API 保存。 |
| `knowledge` | 知识库、知识文档上传入口、文档摄取状态、原始文档内容资源、分块、嵌入工作流、检索策略、检索查询、Qdrant 索引归属、文档解析器运行时配置。 | 通过 gateway 暴露知识库 CRUD、文档上传/详情/内容/分块列表、知识查询和管理员解析器配置资源；需要保存或读取原始文件时内部调用 file，需要解析原始 bytes 时内部调用 parser，需要生成嵌入或 rerank 时内部调用 AI Gateway。 | 用户身份、底层对象存储实现、OCR/PaddleOCR 运行时、LLM 答案生成、DOCX 导出、provider API key 存储。 |
| `parser` | 内部文档解析运行时，把原始文档 bytes 转成规范化 parsed content；首个目标后端为 Python/PaddleOCR。 | 不通过 gateway 暴露；只提供内部 `/internal/v1/parsed-documents`、`/healthz`、`/readyz`。 | 知识库/文档业务状态、processing job、chunk 持久化、embedding、Qdrant 写入、检索、parser admin 配置公开契约、对象存储元数据、QA 会话附件业务状态和临时 chunk 持久化。 |
| `qa` | 聊天会话、消息、Agent Host / ReAct 循环、MCP 工具编排、响应运行记录、模型调用摘要、工具调用记录、引用、会话临时附件元数据/解析状态/临时 chunk/Agent 检索入口、QA 配置版本、检索测试运行和 QA 指标。 | 暴露 `/api/v1/qa-sessions/**`（含 `/api/v1/qa-sessions/{sessionId}/attachments/**`）、`/api/v1/response-runs/**`、`/api/v1/messages/{messageId}/citations`、`/api/v1/citations/**`、`/api/v1/qa-config-versions/**`、`/api/v1/llm-config-versions/**`、`/api/v1/llm-connection-tests`、`/api/v1/retrieval-test-runs/**`、`/api/v1/qa-metrics/**` 下的 QA 路由；内部调用 AI Gateway 获取 OpenAI 兼容的 chat completions 和 Function Calling 传输；调用 MCP Client 进行工具发现/执行；保存会话附件原始 bytes 时内部调用 file，解析附件时内部调用 parser。 | 知识库 CRUD、文件上传、报告记录管理、provider API key 存储、具体 MCP server 实现、直接 provider 调用、会话附件原始 bytes 存储实现、OCR/文档解析运行时、把会话临时附件写入 knowledge 长期索引、在公开前端契约中暴露原始 MCP 工具 schema、原始工具结果、`file_ref` 或 object key。 |
| `document` | 报告模板、材料、报告记录、大纲、章节内容、报告任务、生成文件元数据、统计数据和报告操作日志。 | 暴露 `/api/v1/report-*` 和 `/api/v1/reports/**` 下的报告生成路由；涉及文件或模型输出时，使用 file 服务处理文件对象存储/内容，使用 AI Gateway 进行模型调用。 | QA 聊天、知识索引、auth 持久化、provider API key 存储、直接暴露 MinIO object key 或存储 URL。 |
| `ai-gateway` | 模型 profile、provider 配置、API key 写入状态、OpenAI 兼容的 chat completions、Function Calling 传输、embeddings、OpenAI 风格 rerankings、provider 错误归一化。 | 内部 `/internal/v1/model-profiles`、`/internal/v1/chat/completions`、`/internal/v1/embeddings`、`/internal/v1/rerankings`；健康检查和就绪检查。 | 面向前端的 API、QA 会话/消息、Agent Run 状态、MCP 工具发现/执行、知识分块持久化、Qdrant 写入、报告记录、报告导出、领域权限决策。 |

## 工作流归属

| 工作流 | Gateway 角色 | 归属服务 | 说明 |
| --- | --- | --- | --- |
| 用户和会话创建 | 公开入口、响应归一化、写入 Redis 会话缓存。 | `auth` | 密码校验和会话/令牌签发留在 auth；auth 返回供 gateway 缓存的身份/会话 payload。 |
| 当前会话删除 | 公开入口、响应归一化、删除 Redis 会话缓存。 | `auth` | 会话/令牌失效留在 auth；gateway 删除匹配的 Redis 缓存条目。 |
| 当前用户 | 读取 Redis 会话缓存并归一化响应。 | `auth` | Auth 负责用户/会话源数据；gateway 负责运行时缓存查询和下游上下文注入。 |
| 知识库 CRUD | 公开入口和响应归一化。 | `knowledge` | 已生效的 gateway 契约。Gateway 不得存储知识库业务状态。 |
| 向知识库上传文档 | 公开文件上传入口。 | `knowledge` | Knowledge 负责创建知识库文档资源、保存内部 file reference 和摄取状态；底层原始文件对象通过内部 file API 保存。Gateway 不得实现解析、索引或直接操作 file。 |
| 文档处理状态和分块 | 公开读取入口和响应归一化。 | `knowledge` | 文档详情和分块的已生效 gateway 契约。Gateway 不得实现解析、分块、嵌入或 Qdrant 访问。Knowledge 可调用 parser 获取 parsed content，可调用 AI Gateway 生成嵌入，但 job 状态、分块、向量持久化和 hydrate 归 knowledge。 |
| 原始文档内容 | 路由并执行认证上下文约束。 | `knowledge` | Knowledge 拥有 `documents/{documentId}/content` 资源和业务可见性；底层 bytes 可通过内部 file API 读取。 |
| 前端知识查询 | 公开入口和响应归一化。 | `knowledge` | 已生效的 gateway 契约。查询执行建模为 `knowledge-queries`，不使用动作式 search 路径。检索和 rerank 业务规则留在 knowledge；模型 rerank 调用可经过 AI Gateway。 |
| QA Agent 答案生成 | 公开入口、SSE 转发、认证上下文透传和响应归一化。 | `qa` | 已生效的 gateway 契约。QA 负责会话/消息/引用状态，运行 ReAct 循环，调用 AI Gateway 获取 OpenAI 兼容的 Function Calling 传输，并调用 MCP Client 使用已批准工具。公开工具调用字段仅为脱敏后的摘要。 |
| QA 会话附件上传与解析 | 公开文件上传入口、owner 授权和响应归一化。 | `qa` | QA 拥有会话附件元数据、解析状态、临时 chunk 和 Agent 检索入口。QA 内部调用 file 保存原始 bytes（file 拥有原始对象），内部调用 parser 做 OCR/文档解析（parser 仅解析、不持久化业务状态）。会话临时附件不写入 knowledge 的长期知识库或向量索引；访问控制与隐藏策略见 [QA 权限矩阵](../services/qa/docs/permission-matrix.md)。公开响应不暴露 `file_ref`、object key、bucket 或内部 URL。 |
| 引用来源查询 | 公开入口和响应归一化。 | `qa` | 已保存引用快照的已生效 gateway 契约。来源知识分块和原始文档内容仍以 knowledge/file 为权威。 |
| 报告模板管理 | 公开入口和认证上下文透传。 | `document` | Document 服务负责模板元数据、模板结构和模板文件引用。 |
| 报告材料管理 | 公开入口和认证上下文透传。 | `document` | Document 服务负责报告任务使用的材料元数据和材料文件引用；原始文件对象存储应复用 file 服务，而不是把材料当作知识库文档处理。 |
| 报告记录管理 | 公开入口和认证上下文透传。 | `document` | Document 服务负责报告草稿、生命周期状态、大纲、章节和软删除规则。 |
| 报告大纲生成 | 公开任务资源创建和状态查询。 | `document` | 长时间运行的大纲生成和重新生成表示为 `ReportJob` 资源。Document 可调用 AI Gateway 获取模型输出，但任务状态和大纲版本归 document。 |
| 报告章节生成 | 公开任务或章节版本资源创建和状态查询。 | `document` | 长时间运行的内容生成和章节重新生成留在 document 服务内。Document 可调用 AI Gateway 获取 OpenAI 兼容的流式分块，但公开事件形态归 document。 |
| 报告文件创建和内容 | 公开文件资源创建、元数据查询和内容流。 | `document` | Document 服务负责生成文件元数据，并应尽可能使用 file 服务进行对象存储/内容访问；生成文件不是知识文档。 |
| 报告统计和操作日志 | 公开读取入口和认证上下文透传。 | `document` | Document 服务负责报告专属统计数据和便于审计的操作日志。 |
| 运行时模型 profile 管理 | 公开管理员入口、管理员授权、响应包裹结构、密钥安全归一化。 | `ai-gateway` | 已生效的 gateway 契约：`/api/v1/admin/model-profiles` 和 `/api/v1/admin/model-profiles/{profileId}`。AI Gateway 通过 `/internal/v1/model-profiles` 负责模型 profile、provider base URL、模型名称、默认参数、超时设置和 API key 写入状态；gateway 不得持久化 API key 或直接调用 provider。 |
| 运行时解析器配置管理 | 公开管理员入口、管理员授权、响应包裹结构、密钥安全归一化。 | `knowledge` | 已生效的 gateway 契约：`/api/v1/admin/parser-configs` 和 `/api/v1/admin/parser-configs/{parserConfigId}`。Knowledge 负责解析器后端校验、并发限制和文档处理行为。Gateway 不得实现解析。 |
| 文档解析运行时 | 无公开入口；仅传递内部调用上下文。 | `parser` | Parser 负责 OCR/PaddleOCR 等解析运行时和模型加载。Knowledge 负责在调用前做文档权限/状态校验，调用后校验 parsed content，并继续切片、embedding、索引和状态推进。 |
| Provider 模型调用 | 仅内部模型调用 API。 | `ai-gateway` | Chat 和 embedding API 使用 OpenAI 兼容 body。Chat 也支持 OpenAI 兼容的 Function Calling 字段。由于 OpenAI 没有原生 rerank endpoint，rerank 采用 OpenAI 风格。领域服务负责 prompt、业务上下文、MCP 执行和持久化。 |
| 管理概览和聚合指标 | `GET /api/v1/admin/overview` 和 `GET /api/v1/admin/metrics` 均已生效。 | `gateway` 聚合；各服务负责自己的指标。 | 已转为 active contract。Admin overview 提供各模块轻量快照，admin-metrics 提供跨服务时间序列趋势数据。 |

## 缺失契约登记

当前无缺失契约。所有计划内公开 API 均已转为 active paths。
MCP 原始工具 schema、完整工具参数/结果、内部审计细节、prompt、provider 原始错误和存储对象 key
被有意排除在公开 QA 契约之外，而不是被视为缺失的前端端点。

## 数据归属规则

- 拥有数据库表的服务，也拥有修改该数据的 API。
- Gateway 可以为前端、管理端、后端模块和工具调用方暴露调用方友好的公开路径，但必须把业务校验委托给归属服务。
- AI Gateway 可以存储模型 provider 配置，以及加密或由密钥系统托管的 API key 材料，但不得负责领域 prompt、会话、Agent Run、MCP 工具调用、分块、引用、报告、生成文件或面向前端的路由。Gateway 暴露管理员模型 profile 路由，并转发密钥写入，不记录或持久化密钥。
- 跨服务 ID 在公开 API 契约中应使用字符串。各服务可自行决定内部 ID 表示。
- 公开契约中的时间戳使用 RFC 3339 / OpenAPI `date-time`。
- 删除操作必须由负责该资源生命周期的服务拥有。

## 新端点边界检查

添加 gateway 端点前，先在端点文档或 OpenAPI 描述中回答以下问题：

1. 哪个服务负责资源状态？
2. 该端点只是路由转发，还是会聚合多个服务？
3. 如果会聚合，哪个前端页面需要这种数据形态？
4. 哪个服务校验领域规则？
5. 前端可以依赖哪些错误码？
6. 该端点是否暴露原始 object key、凭证、prompt、向量 payload 或内部 URL？不应暴露。
7. 该路径是否建模为资源或集合，并由 HTTP method 承载动作？

## 错误模式

- 直接在 gateway handler 中加入 SQL、MinIO、Qdrant 或 LLM 调用。
- 添加 `/login`、`/logout`、`/download`、`/search`、`/generate`、`/export`、`/retry`、`/revoke` 等动作式路径，而不是把用户、会话、内容、查询、任务、文件、消息或事件建模为资源。
- 在前端、gateway 和领域服务中重复实现权限逻辑，且没有单一归属方。
- 当某个领域服务应该负责完整工作流时，让 gateway 把一个前端动作翻译成一条很长的业务工作流。
- 将下游服务内部细节直接返回给前端。
- 从 `gateway`、`qa`、`knowledge` 或 `document` 直接调用 OpenAI 兼容、SiliconFlow 兼容或本地模型 provider，而不是通过 `ai-gateway` 路由模型调用。
- 让 AI Gateway 执行 MCP 工具或决定工具权限；QA/MCP Client 必须负责这些决策和记录。
- 在前端契约中暴露 AI Gateway `/internal/v1/**`、API key 值、prompt、embedding、rerank payload 或 provider 原始错误。经过授权的管理员模型 profile 响应只能通过 gateway 暴露 provider/model/base URL 元数据和 `apiKeyConfigured` 状态。
- 在 Knowledge Go 进程中引入 PaddleOCR、PaddlePaddle、OpenCV、CUDA 或 parser 模型加载依赖；这些应放在 parser runtime 后面，通过内部 HTTP 契约调用。
- 当 file-service 内部资源可以建模原始对象时，让 `document` 为报告模板、材料或生成文件重复实现 file 服务的对象存储语义。
- 在至少三个服务需要同一个稳定抽象之前创建共享 Go package。
