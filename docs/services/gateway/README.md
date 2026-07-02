# Gateway 服务规划

本文档定义 `gateway` 服务在项目初期的职责边界和基础契约。目标是让前端只依赖一个稳定入口，同时让 `auth`、`file`、`knowledge`、`qa`、`document`、`ai-gateway` 等服务可以按清晰边界并行开发。

相关文档：

- [Gateway 数据模型文档](docs/data-models.md)
- [Gateway Public OpenAPI 契约](api/public.openapi.yaml)
- [Gateway Internal OpenAPI 契约](api/internal.openapi.yaml)
- [Gateway Active API Owner Map](docs/active-api-owner-map.md)
- [Gateway 权限矩阵](docs/permission-matrix.md)
- [Gateway 实现说明](docs/implementation.md)
- [技术选型基线](../../architecture/technology-decisions.md)

## 设计原则

- `gateway` 是面向前端、管理端、其他后端模块和工具调用方的后端统一入口，不是业务大单体。
- 所有公开业务请求都必须先进入 `gateway` 暴露的 `/api/v1/**` 接口，不直接调用内部服务。
- `gateway` 通过 HTTP/REST 调用内部服务，不 import 其他服务的 Go `internal/` 包。
- AI Gateway 是内部模型服务；前端不得直接调用其 `/internal/v1/**` 或 OpenAI-compatible endpoint。
- 稳定 API 的 RESTful 命名、统一 envelope、错误和 request id 规则以 [前后端集成契约](../../architecture/frontend-backend-contract.md) 为准。
- 领域业务规则尽量留在拥有该领域数据和流程的服务中。
- 跨服务聚合接口必须有明确前端场景，不能把所有服务编排都放进 `gateway`。
- OpenAPI 契约先行，代码实现必须跟随契约变更。

## 技术选型落地约束

Gateway 后续实现必须遵循 [技术选型基线](../../architecture/technology-decisions.md)。本服务特有约束只包括：

- 代码落地时使用独立 Go module，目录建议为 `services/gateway/`。
- 首期不拥有业务数据库，因此不维护 `sqlc.yaml` 或 `migrations/`；若后续新增自有持久化模型，需回到技术选型基线补齐 `pgx` + `sqlc` 和 `goose`。
- Redis 只保存会话缓存、短期缓存和运行时状态，不作为长期业务真相。
- 路由、中间件、认证缓存、错误映射和 SSE 转发是 Gateway 测试重点。
- 本目录 OpenAPI 是前端 `openapi-typescript` 类型生成的 public gateway 权威契约；内部服务 OpenAPI 不生成到前端。

## Gateway 应负责

| 能力 | 说明 |
| --- | --- |
| Public API surface | 暴露前端、管理端、其他后端模块和工具调用方使用的 `/api/v1/**` HTTP API。 |
| Routing | 将已确定的公开请求转发到 `auth`、`file`、`knowledge`、`qa`、`document`、`ai-gateway` 等内部服务；未定下游服务只保留缺失占位。 |
| Auth context | 基于 Redis 会话缓存读取用户身份，并向下游传递用户、角色、权限和 request id。 |
| Session cache | 用户或会话创建成功后缓存 auth 返回的会话身份信息，后续请求优先从 Redis 获取会话上下文。 |
| Response contract | 对前端保持统一成功响应、分页响应和错误响应结构。 |
| Request correlation | 生成或透传 `X-Request-Id`，并要求下游服务保留该 request id。 |
| Admin runtime configuration entrypoint | 暴露模型 profile 和文档解析器配置的管理入口；模型配置转发给 `ai-gateway`，解析器配置转发给 `knowledge`。 |
| Cross-service aggregation | 仅在前后端契约明确后提供聚合读接口；本轮管理后台概览暂标缺失。 |
| Streaming entrypoint | 问答通过 `POST /api/v1/qa-sessions/{sessionId}/messages` 提供 `text/event-stream` 响应，并通过 `/api/v1/qa-sessions/{sessionId}/events` 提供短期事件回放；报告生成当前提供事件列表资源，后续如需 SSE 需先补 OpenAPI 契约。 |
| Edge policy | 集中处理 CORS、基础请求头、请求大小原则、健康检查和公开 API 命名。 |

## Gateway 不应负责

| 领域 | 归属服务 | Gateway 不做什么 |
| --- | --- | --- |
| 用户、密码、会话、角色权限源数据 | `auth` | 不保存密码，不维护用户表，不实现 RBAC 持久化；只在 Redis 保存运行时会话缓存。 |
| 文件对象、基础 file 元数据、对象存储协调 | `file` | 不直接操作 MinIO，不生成业务 object key。 |
| 知识库、文档切片、向量索引、检索策略 | `knowledge` | 不执行切片、嵌入、Qdrant 查询或重排序。 |
| 问答 Agent、MCP 工具编排、LLM 调用 | `qa` | 不拼 prompt，不执行 ReAct loop，不执行 MCP 工具，不保存对话业务状态。 |
| 报告大纲、章节生成、DOCX 导出 | `document` | 不生成报告内容，不操作报告模板业务规则。 |
| 模型 provider 配置、API key、chat/embedding/rerank 调用 | `ai-gateway` | 不保存 provider API key，不直连 OpenAI-compatible 或 SiliconFlow-compatible provider，不把内部模型调用接口暴露给前端；只通过 admin model-profile 资源转发配置管理请求。 |
| 服务数据库迁移 | 各领域服务 | 不拥有其他服务的 migrations。 |

## Public API 命名

第一版公开 API 使用统一版本前缀：

```text
/api/v1
```

健康检查接口不带版本前缀：

```text
/healthz
/readyz
```

逐项 active operation、owner service、tag、operationId 和认证要求见
[Gateway Active API Owner Map](docs/active-api-owner-map.md)。该清单从
[`api/public.openapi.yaml`](api/public.openapi.yaml) 审计生成；若两者冲突，以 OpenAPI 为准并同步更新清单。

当前 active API 的完整逐项清单只在 Gateway OpenAPI 和 owner map
维护；本文只保留 owner 级资源分组，避免多处复制 path 明细：

| Owner | Gateway 公开资源范围 |
| --- | --- |
| `gateway` | 健康检查和就绪检查。 |
| `auth` | 用户、会话和当前用户身份。 |
| `knowledge` | 知识库、知识库文档、文档详情、文档切片、原始文件内容、知识查询和管理员解析器配置。 |
| `document` | 报告类型、模板、素材、报告记录、大纲、章节、任务、事件、生成文件、统计、操作日志和报告设置。 |
| `qa` | QA 会话、消息、回答运行、脱敏工具调用摘要、引用、配置版本、连接测试、检索体验测试和 QA 指标。 |
| `ai-gateway` | 管理端模型 profile 配置；Gateway 只做管理员鉴权、响应归一化和密钥脱敏转发，不保存 API key。 |

仍暂缺的下游接口：

| 无。所有计划内公开 API 已转为 active paths。 |

当某个 endpoint 涉及两个服务时，文档必须显式标注 workflow owner。默认规则是：拥有核心业务状态的服务拥有流程，gateway 只做入口和上下文传递。若流程需要模型能力，领域服务应通过 [AI Gateway 服务接口文档](../ai-gateway/README.md) 和 [AI Gateway OpenAPI 契约](../ai-gateway/api/internal.openapi.yaml) 调用内部模型接口，不能让 public gateway 直接拼 prompt 或直连 provider。

## 认证与上下文传递

认证机制初期采用 opaque bearer token + Redis 会话缓存。Auth 服务负责认证、签发不透明随机 access token、维护会话身份和撤销会话；Gateway 负责在用户或会话创建成功后写入 Redis，并在后续请求中从 Redis 读取会话上下文。

前端请求：

- 登录类接口不要求认证。
- 业务接口必须携带认证凭据。
- 前端不直接设置用户身份 header，用户身份由 gateway 认证后注入。
- 后续请求使用 `Authorization: Bearer <accessToken>` 携带 gateway 返回的访问令牌；该令牌不可被前端或 Gateway 当作 JWT 解析。

会话缓存流程：

1. 前端调用 `/api/v1/sessions` 或 `/api/v1/users`。
2. Gateway 将请求转发给 auth 服务。
3. Auth 服务校验凭证，返回用户身份、角色、权限、`sessionId`、不透明 `accessToken` 和 `expiresAt`。
4. Gateway 将完整会话身份写入 Redis，缓存键使用 `gateway:session:<accessTokenHash>`，TTL 与 `expiresAt` 对齐。
5. 前端后续请求携带 `Authorization: Bearer <accessToken>`。
6. Gateway 从 Redis 查询会话；命中且未过期时，不需要每次调用 auth 服务。
7. Gateway 基于缓存的会话身份向下游服务注入认证上下文；具体 header 和权限复核责任见 [Gateway 权限矩阵](docs/permission-matrix.md)。
8. 当前会话删除时 Gateway 调用 auth 删除会话，并删除 Redis 中的对应缓存。

Redis 会话缓存值应至少包含：

| 字段 | 说明 |
| --- | --- |
| `sessionId` | Auth 服务签发的会话 ID。 |
| `userId` | 已认证用户 ID。 |
| `username` | 用户名，用于审计和调试，不作为权限判断唯一依据。 |
| `roles` | 角色列表。 |
| `permissions` | 权限字符串列表。 |
| `accessTokenHash` | 访问令牌哈希，避免把原始 token 当作可读缓存字段。 |
| `expiresAt` | 会话过期时间，使用 RFC 3339 / OpenAPI `date-time`。 |
| `issuedAt` | 会话签发时间。 |

缓存规则：

- Redis 是运行时会话缓存，不是用户、角色、权限的持久化源数据。
- 每条会话缓存必须设置明确 TTL。
- Gateway 日志和错误响应不得输出原始 token、session secret 或 Redis 连接信息。
- Redis 未命中、会话过期或缓存内容无效时，Gateway 返回 `401 unauthorized`，前端回到登录流程。
- Redis 不可用时，业务接口返回 `502 dependency_error`；登录、注册和登出等 auth 流程可以按实现策略选择失败或降级，但必须保持错误 envelope 一致。
- 权限变更、用户禁用或安全事件需要让旧会话失效时，auth 服务应提供撤销能力，Gateway 删除对应 Redis 会话缓存。

Gateway 的公开入口、下游认证上下文、角色权限口径、owner service 复核责任和拒绝规则统一维护在 [Gateway 权限矩阵](docs/permission-matrix.md)。README 不重复维护 header 表；会话缓存字段的存储模型见 [Gateway 数据模型文档](docs/data-models.md)。

## Gateway User / Session 行为

Gateway 对前端暴露 auth 拥有的用户与会话资源，精确 method、path、认证要求、schema 和错误码只在 [`api/public.openapi.yaml`](api/public.openapi.yaml) 与 [active API owner map](docs/active-api-owner-map.md) 维护。

Gateway 负责转发用户创建和会话创建请求，成功后把 auth 返回的会话身份写入 Redis 会话缓存；当前用户查询优先从 Redis 会话缓存读取；登出时定位当前会话，调用 auth 删除会话或令牌，并删除 Redis 缓存。

Auth service 负责创建用户、校验凭证、维护角色权限、签发会话身份和记录安全事件。Gateway 必须只把 `data.session.accessToken` 返回给前端，不得把 Redis key、token hash、内部 auth URL 或 session secret 暴露给前端。

## Gateway Knowledge 行为

Gateway 对前端暴露 knowledge 拥有的知识库、知识库文档、文档内容、文档切片和检索查询资源，精确接口清单以 [`api/public.openapi.yaml`](api/public.openapi.yaml) 与 [active API owner map](docs/active-api-owner-map.md) 为准。Gateway 只负责鉴权上下文传递、路由和响应归一化，不执行解析、切片、embedding、Qdrant 检索或重排序。

检索被建模为 `knowledge-queries` 资源创建，不使用 `/search` 或 `/retrieval/search`。知识库文档公开资源统一由 `knowledge` 拥有：创建文档资源时保存底层 file reference，列表和详情返回处理状态，chunk 和 content 子资源返回切片或原文件流。Gateway 不直接解析文件、操作 MinIO 或操作 Qdrant。

报告素材、模板和导出文件不得复用知识库文档上传路径建模。它们的公开资源由 `document` 拥有，`document` 在内部通过 file 服务保存、读取或删除底层文件对象；Gateway 只做入口、认证上下文传递和响应归一化。

## Gateway QA 行为

Gateway 对前端暴露 `qa` 拥有的会话、消息、回答运行、工具调用摘要、引用、配置版本、检索体验测试和统计资源，精确接口清单以 [`api/public.openapi.yaml`](api/public.openapi.yaml) 与 [active API owner map](docs/active-api-owner-map.md) 为准。

Gateway 只负责认证上下文、统一 envelope、SSE 转发和错误归一化；`qa` 服务拥有会话、消息、回答运行、Agent/ReAct 循环、MCP 工具编排、引用快照、配置版本、检索体验测试和问答统计。SSE 事件语义见 [QA 服务文档](../qa/README.md) 与 [前后端集成契约](../../architecture/frontend-backend-contract.md)。SSE 事件、工具摘要和错误响应不得包含完整工具参数、MCP 原始响应、内部 URL、原始文档全文、prompt、provider 原始错误或存储 object key。

## 响应约定

Gateway 负责对前端保持统一成功响应、分页响应和错误响应结构。通用 envelope、错误码和前端处理规则见 [前后端集成契约](../../architecture/frontend-backend-contract.md)。本节不再重复定义格式，避免与 OpenAPI 和架构契约漂移。

Gateway 可透传或映射 owner service 的服务特有错误码，但任何稳定公开错误都必须先进入 [`api/public.openapi.yaml`](api/public.openapi.yaml)。

## 缺失下游接口

`GET /api/v1/admin/overview` 和 `GET /api/v1/admin/metrics` 已转为 active contracts，具体 schema 以 Gateway OpenAPI 为准。Gateway 负责轻量聚合，各领域服务提供指标来源。路由注册由单独后端 issue 追踪。

AI Gateway 的内部模型调用接口已经有独立契约：[`docs/services/ai-gateway/api/internal.openapi.yaml`](../ai-gateway/api/internal.openapi.yaml)。该契约不属于前端可调用的 gateway OpenAPI，也不应生成到前端 API client。前端需要管理运行时模型配置时，只能使用 gateway OpenAPI 中的 `/api/v1/admin/model-profiles` 资源；gateway 再调用 AI Gateway 内部 `/internal/v1/model-profiles`。

后续补齐任一缺失接口时，需要同步更新：

- `docs/services/gateway/api/public.openapi.yaml`
- `docs/architecture/frontend-backend-contract.md`
- `docs/architecture/service-boundaries.md`
- 对应服务接口文档

## 健康检查

| Endpoint | 说明 |
| --- | --- |
| `GET /healthz` | 进程存活检查，只表示 gateway 进程可响应。 |
| `GET /readyz` | 就绪检查，后续可包含关键下游依赖状态。 |

## 后续扩展

本轮只定义基础契约包。以下内容后续单独细化：

- 下游服务完整内部 API 索引。
- 超时、重试、熔断和断线重连策略。
- API 版本兼容策略。
- 限流、审计和安全事件记录。
- 多端 BFF 拆分条件。
