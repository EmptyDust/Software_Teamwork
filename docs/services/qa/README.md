# QA 服务接口文档

本文档定义 `qa` 服务的前端接口、内部 Agent Host 设计目标和 gateway 适配约定。稳定公开契约以 [`Gateway OpenAPI 契约`](../gateway/api/public.openapi.yaml) 中的 active paths 为准；本文档解释字段来源、处理流程和内部边界。本文档基于以下来源整理：

- 外部前端接口文档《智能问答系统 — 前端接口文档》。
- [`技术选型基线`](../../architecture/technology-decisions.md)：`pgx` + `sqlc`、`goose`、`net/http` / `ServeMux`、`slog`、opaque Bearer token、`fetch` stream SSE、MCP SDK/sidecar 等实现约束。
- [`Gateway 服务规划`](../gateway/README.md)、[`前后端集成契约`](../../architecture/frontend-backend-contract.md)、[`服务边界矩阵`](../../architecture/service-boundaries.md) 和 [`Gateway OpenAPI 契约`](../gateway/api/public.openapi.yaml)。
- [`QA 数据模型文档`](docs/data-models.md)：`qa_config_versions`、`llm_config_versions`、`conversations`、`messages`、`response_runs`、`agent_model_invocations`、`agent_tool_calls`、`message_content_blocks`、`response_process_steps`、`response_stream_events`、`citations`、`retrieval_test_runs`、`retrieval_test_results`、`llm_connection_tests`、`admin_audit_logs`。
- [`QA 权限矩阵`](docs/permission-matrix.md)：QA 会话、消息、回答运行、引用、配置、检索测试、指标和工具调用的权限边界。
- [`QA 实现说明`](docs/implementation.md)：当前代码实现、契约对齐、缺口和最近检查记录。
- GitHub Discussion #65《请问能否重构AI问答模块接口契约？》。

> 当前状态：QA 会话、消息、非流式/流式回答、SSE 事件回放、回答运行、脱敏工具调用摘要、引用、配置、检索体验测试和统计接口已经进入 `docs/services/gateway/api/public.openapi.yaml` 的 active paths。MCP 原始 tool schema、完整工具参数/结果、内部审计和服务间私有接口仍不属于前端稳定公开契约。

## 设计目标

QA 不再按固定规则写死“意图识别 -> 检索 -> 生成”的单一路径，而是作为 Agent Host 运行一次可控的 ReAct 循环：

```text
frontend
   |
   v
gateway QA session resources
   |
   v
qa service (Agent Host)
   |-- ReAct loop
   |-- MCP client manager
   |-- tool policy and permission checks
   |-- public SSE event projection
   |-- session, response run, model invocation, and tool-call state
   |
   |-- ai-gateway /internal/v1/chat/completions
   |     OpenAI-compatible function calling transport
   |
   +-- MCP client
         tools/list
         tools/call
         |
         +-- knowledge MCP server
         +-- document MCP server
         +-- future approved MCP servers
```

ReAct 在本文档中具体表示：

- Action：LLM 通过 OpenAI-compatible `tool_calls` 选择要调用的工具。
- Observation：QA 通过 MCP Client 执行 `tools/call` 后得到的结构化工具结果。
- Loop：QA 把 `role=tool` 的工具结果追加回模型上下文，继续下一轮模型调用，直到模型返回最终文本、达到终止条件或发生错误。

QA 只能保存和返回可向用户展示的处理摘要，不保存或返回模型原始 Thought、私有 chain-of-thought、完整 prompt、完整工具参数、内部 URL、原始文档全文、向量 payload 或 provider 原始错误。

## 职责边界

| 范围 | 说明 |
| --- | --- |
| 会话管理 | 维护用户的 QA 会话、会话标题、状态和消息顺序。 |
| 消息与回答运行 | 保存用户消息、助手消息、一次回答生成的运行状态、token 使用量、延迟和失败原因。 |
| Agent Host / ReAct Loop | 负责创建 response run、选择可用工具、调用模型、执行工具、循环终止和可展示步骤投影。 |
| MCP Client 编排 | 通过 MCP Client `tools/list` 发现工具，通过 `tools/call` 执行工具；QA 负责工具白名单、权限裁剪、参数校验和结果脱敏。 |
| 模型调用记录 | 记录每次模型调用的 iteration、模型、finish reason、token 用量、延迟和状态。 |
| 工具调用记录 | 记录每次工具调用的 tool call id、工具名、参数摘要、结果摘要、状态、延迟和错误码。 |
| SSE 事件 | 产生并短期保存前端可消费的流式事件，用于断线恢复或调试。 |
| 引用快照 | 保存回答中的引用编号、文档/chunk 外部 ID、引用文本、上下文和分数。 |
| QA 配置 | 管理问答检索参数、默认知识库选择和配置版本。 |
| LLM 配置 | 管理 AI Gateway profile 引用、模型名称、超时、生成参数和 Agent 终止策略。 |
| 检索体验测试 | 记录管理员发起的检索测试及结果快照。 |
| QA 统计 | 基于 `response_runs`、模型调用和工具调用记录聚合问答次数、延迟、工具使用和热门问题。 |

`qa` 不拥有用户、角色、权限、知识库主数据、文档原文件、文档解析、向量索引、报告记录、文件下载、provider API key 或 MCP server 的具体业务实现。相关能力由 `auth`、`knowledge`、`file`、`document`、`ai-gateway` 和 MCP server 拥有，gateway 只做公开入口、认证上下文和响应归一化。

## 接入模型

```text
frontend
   |
   v
gateway QA resources
   |
   v
qa service
   |
   +--> PostgreSQL conversations / messages / response_runs / agent_tool_calls / citations
   +--> ai-gateway for OpenAI-compatible model calls and function-calling transport
   +--> MCP Client for tools/list and tools/call
```

QA 的认证上下文、owner 约束、settings 管理权限、工具权限裁剪和拒绝规则统一维护在 [QA 权限矩阵](docs/permission-matrix.md)。README 不重复维护 header 表或 owner 权限语义。

## 技术落地基线

QA 服务实现必须对齐 [技术选型基线](../../architecture/technology-decisions.md)。本服务只补充 Agent Host 特有约束：

- QA 作为独立 Go module 微服务实现，公开前端入口仍经 gateway 暴露。
- 业务表结构以 `docs/services/qa/docs/data-models.md` 为逻辑来源；创建消息并启动 Agent Run、配置版本切换、引用快照落库等跨表写入必须由 service/use-case 层开启事务。
- Redis 只可用于短期 SSE 推送、运行中取消信号、短期锁或缓存；`response_runs`、`messages`、`response_stream_events` 和工具调用摘要仍以 PostgreSQL 为权威。
- 交互式 QA 回答主路径不默认投递后台队列，避免破坏 SSE 实时性。后续若增加离线评测、批量重放或清理任务，应使用 `asynq`，任务最终状态仍落 PostgreSQL。
- QA、AI Gateway、MCP tool call、knowledge/file/document 依赖调用属于重点 tracing 链路；第一阶段至少确保 request id 在日志、数据库记录和下游请求中贯穿。
- 消息创建使用 `POST` + `Accept: text/event-stream`；前端通过 `fetch` stream reader 和 `AbortController` 消费/取消，不以原生 `EventSource` 作为主实现。
- QA 负责工具白名单、权限裁剪、参数 schema 校验、超时、幂等和脱敏记录，不手写完整 MCP 协议栈作为首选。
- QA 不保存 provider API key、provider base URL、MinIO object key、数据库连接串或 secret ref 明文。模型 profile、provider 凭证和供应商适配由 AI Gateway 拥有。

建议的服务目录：

```text
services/qa/
  cmd/qa/
  internal/config/
  internal/http/
  internal/middleware/
  internal/service/
  internal/repository/
    queries/
    sqlc/
  internal/agent/
  internal/mcp/
  internal/aigateway/
  migrations/
  sqlc.yaml
```

## 与前端原始设计的映射

历史前端设计中的 conversation、chat stream、citation、RAG test、LLM config 和 stats 能力已经被重新归并为 QA-owned 或 Knowledge-owned 资源。精确迁移路径、method 和 schema 只在 Gateway OpenAPI 与 owner map 维护；本文保留归属语义：

- conversation 类能力归并为 `qa-sessions`、session messages 和 session events。
- chat stream 由 session message 创建触发，流式事件由 QA SSE 投影提供。
- 正式知识检索归 `knowledge`，QA 通过 MCP 工具、内部 client 或检索体验测试间接调用。
- citation lookup 归 `qa` 的回答引用快照；原文详情由 Knowledge/File-owned 资源补齐。
- QA config、LLM config、LLM connection test、retrieval test 和 QA metrics 均由 `qa` 拥有，但 provider profile 和 API key 仍由 `ai-gateway` 拥有。

## 通用响应结构

JSON 成功、分页和错误响应遵循 [前后端集成契约](../../architecture/frontend-backend-contract.md)。本文只保留外部旧数字码到项目错误码的迁移映射，便于前端和后端重构时对照。

错误码映射：

| 原始数字码 | 项目错误码 | HTTP status | 说明 |
| --- | --- | --- | --- |
| `40000` | `validation_error` | `400` | 请求参数错误。 |
| `40100` | `unauthorized` | `401` | 未登录或会话失效。 |
| `40300` | `forbidden` | `403` | 已登录但权限不足。 |
| `40400` | `not_found` | `404` | 会话、消息、引用或配置不存在。 |
| `50000` | `internal_error` | `500` | QA 服务未预期错误。 |
| `50100` | `dependency_error` | `502` | LLM 服务失败。 |
| `50200` | `dependency_error` | `502` | 知识检索或重排序依赖失败。 |
| `50300` | `dependency_error` | `502` | 文档处理或知识服务依赖失败。 |

Owner 权限语义、管理员跨用户访问限制和 `401` / `403` 拒绝规则见 [QA 权限矩阵](docs/permission-matrix.md)。

## 公开资源范围

QA 已进入 Gateway active contract 的公开资源包括：

- `qa-sessions`：QA 会话、会话标题、归档状态和当前用户会话列表。
- `qa-sessions/{sessionId}/messages`：会话消息列表、用户消息创建和 Agent Run 触发；请求可通过 `Accept: text/event-stream` 消费流式回答。
- `qa-sessions/{sessionId}/events`：短期 SSE 事件回放，用于断线恢复和调试。
- `response-runs` 和 `response-runs/{responseRunId}/tool-calls`：回答运行状态、取消和脱敏工具调用摘要。
- `messages/{messageId}/citations`、`citations` 和 `citation-lookups`：回答引用快照、引用详情和批量引用详情查询。
- `qa-config-versions`、`llm-config-versions` 和 `llm-connection-tests`：QA/LLM 配置版本和 AI Gateway profile 连接测试。
- `retrieval-test-runs`：管理员检索体验测试运行和结果快照。
- `qa-metrics`：问答统计、趋势、热门问题和意图分布。

逐项 method、path、schema、认证和错误响应以 [`docs/services/gateway/api/public.openapi.yaml`](../gateway/api/public.openapi.yaml) 和 [Gateway Active API Owner Map](../gateway/docs/active-api-owner-map.md) 为准。服务级 [`api/public.openapi.yaml`](api/public.openapi.yaml) 是 QA public 设计上下文；未进入 Gateway active paths 的内容不是前端稳定公开契约。

相关但非 QA-owned 的公开资源仍由 owner service 负责：知识检索和知识库文档归 `knowledge`，用户与会话归 `auth`，模型 profile 与 provider 凭证归 `ai-gateway`。QA 可通过 MCP 工具、内部 client 或 Gateway 公开入口组合这些能力，但不复制 owner service 的主数据或权限事实。

## 公开字段与数据来源

Gateway OpenAPI 定义 browser-facing schema；本文只记录字段来源和边界语义，不维护第二份请求/响应示例。

| 公开概念 | QA 数据来源 | 约束 |
| --- | --- | --- |
| QA 会话 | `conversations` | 只返回当前用户可见会话；跨用户访问不得泄露存在性。 |
| QA 消息 | `messages`、`message_content_blocks` | 可展示正文来自 content blocks；不返回完整 prompt 或私有 chain-of-thought。 |
| 可展示思考步骤 | `response_process_steps` | 只返回安全摘要，例如 `reasoning.step` / `thinking`；不得包含完整工具参数或模型 Thought。 |
| 回答运行 | `response_runs` | 保存状态、终止原因、token 摘要、延迟和安全错误摘要。 |
| 模型调用摘要 | `agent_model_invocations` | 记录脱敏后的模型、finish reason、token usage 和延迟；不返回 provider 原始错误或密钥。 |
| 工具调用摘要 | `agent_tool_calls` | 只保存工具名、参数摘要、结果摘要、状态和错误码；完整 MCP 参数/结果不进入前端契约。 |
| SSE 事件 | `response_stream_events` | 短期保存用于回放和调试；最终可展示回答仍落入消息表。 |
| 引用快照 | `citations` | 保存回答生成时的引用快照；原文内容读取仍走 Knowledge/File-owned 资源。 |
| QA 配置 | `qa_config_versions` | 版本化保存检索默认值、工具白名单和 Agent 终止策略。 |
| LLM 配置 | `llm_config_versions` | 只保存 AI Gateway profile 引用、模型名和生成参数，不保存 provider API key。 |
| 检索测试 | `retrieval_test_runs`、`retrieval_test_results` | 记录管理员测试快照；正式知识检索仍由 `knowledge` 拥有。 |
| QA 指标 | `response_runs`、`messages`、`agent_tool_calls`、`citations` 聚合 | 不新增重复统计事实表；跨服务数量来自 owner service 或聚合缓存。 |

公开 API 字段映射和枚举以 Gateway OpenAPI 为准；内部字段与公开字段不是简单大小写转换时，在 [`QA 数据模型文档`](docs/data-models.md) 中维护映射。

## SSE 事件语义

问答流式接口已经进入 Gateway OpenAPI。前端通过创建消息触发回答；请求头包含 `Accept: text/event-stream` 时，gateway 返回 QA SSE 流。SSE 通用格式、payload schema 和错误响应以 Gateway OpenAPI 为准，本文只解释事件语义和安全边界。

| 事件类型 | 触发时机 | 用途 | 数据库来源 |
| --- | --- | --- | --- |
| `message.created` | 用户消息已保存，Agent Run 已创建 | 前端创建消息占位和运行状态。 | `messages`、`response_runs`。 |
| `agent.iteration.started` | 新一轮 ReAct 迭代开始 | 展示 Agent 正在规划或调用模型。 | `response_runs.current_iteration`、`agent_model_invocations`。 |
| `reasoning.step` | 可展示步骤变化 | 更新前端处理步骤列表。 | `response_process_steps`。 |
| `tool.started` | 工具调用开始 | 展示正在执行的工具摘要。 | `agent_tool_calls`。 |
| `tool.completed` | 工具调用成功 | 展示工具结果摘要。 | `agent_tool_calls`。 |
| `tool.failed` | 工具调用失败 | 展示工具失败摘要，可继续或终止。 | `agent_tool_calls`。 |
| `answer.delta` | 最终回答生成文本增量 | 流式渲染回答。 | `response_stream_events`，最终合并入 `message_content_blocks`。 |
| `citation.delta` | 引用产生或确认 | 展示引用标注。 | `citations`。 |
| `answer.completed` | 回答完成 | 关闭流式状态。 | `response_runs`、`messages`。 |
| `error` | 任何环节失败 | 展示错误并决定是否终止流。 | `response_runs.error`、`messages.error_code`。 |
| `heartbeat` | 空闲保活 | 防止代理超时。 | 可不持久化。 |

历史事件名 `intent`、`step`、`token`、`citation`、`done` 可以作为迁移前兼容别名，但新 Agent 契约应优先使用上表事件。`heartbeat` 是传输层事件，不要求持久化。

SSE 不得返回完整工具参数、完整 MCP tool result、内部 URL、原始文档全文或私有 chain-of-thought。需要展示推理过程时，只返回 `reasoning.step` 的安全摘要。

## 配置、引用、测试和统计边界

- 引用接口只返回 QA 保存的回答引用快照和可展示来源状态；如果前端需要原文件内容，应使用 Knowledge-owned `documents/{documentId}/content` 资源。
- QA 配置采用版本化资源，历史 `response_runs` 必须引用当时使用的配置版本；更新配置时创建新版本，不原地覆盖历史配置。
- 创建 active QA/LLM 配置版本后，QA runtime 必须立即 reload；用户无需重启 QA 服务才能使用新知识库或新模型 profile。
- `retrieval.scoreThreshold: 0` 是显式有效配置，表示不按分数过滤，不能被默认值覆盖；模型工具调用可以放宽检索阈值，但不能把管理员配置的阈值调高。
- LLM 配置只引用 AI Gateway profile 和生成参数；provider `baseUrl`、密钥和供应商适配逻辑由 AI Gateway 管理。
- 检索体验测试是管理员使用当前 QA 配置发起的一次测试运行及结果快照，不改变 Knowledge 的索引事实。
- QA 指标默认从权威事实表聚合。`knowledgeBaseCount`、`documentCount` 等跨服务数量应来自 owner service 或聚合缓存，不能在 QA 中复制主数据。

## Agent Loop 处理约定

前端只需要创建消息并消费 SSE 事件。QA 服务内部按以下顺序执行：

```text
user message
  -> create response_run
  -> load active QA / LLM config
  -> MCP Client tools/list
  -> filter tools by config, whitelist, user permission, and request overrides
  -> convert MCP tool schemas to OpenAI-compatible tools
  -> for iteration < maxIterations:
       call AI Gateway chat/completions(messages, tools)
       persist agent_model_invocation
       if assistant returns tool_calls:
         validate tool name, JSON schema, permissions, timeout, and idempotency
         execute MCP tools/call through MCP Client
         persist agent_tool_calls
         append role=tool results to model messages
         emit sanitized tool events
         continue
       if assistant returns final text:
         persist assistant message, content blocks, process steps, citations, and response run
         emit answer.completed
         stop
  -> if limit/timeout/cancel/error:
       persist termination_reason and safe error summary
```

旧意图值可保留为统计标签或首轮提示上下文，但不再作为固定后端编排分支：

| 历史意图 | Agent Host 处理方式 |
| --- | --- |
| `knowledge_qa` | 模型可选择 `search_knowledge`，QA 从工具结构化结果生成引用快照。 |
| `general_chat` | 模型不调用工具，直接返回最终文本。 |
| `report_generation` | 后续注册 Document MCP 工具后由模型选择对应工具；首期未注册时返回安全的不支持提示。 |
| `data_analysis` | 首期不注册数据分析工具，返回 `unsupported_intent` 或普通回答，不执行未授权工具。 |

终止原因初始值：

| termination_reason | 说明 |
| --- | --- |
| `completed` | 模型返回最终文本并完成持久化。 |
| `max_iterations` | 达到配置的最大迭代次数。 |
| `timeout` | 单次模型、单次工具或整体运行超时。 |
| `cancelled` | 用户或上游请求取消。 |
| `tool_error` | 工具调用失败且无法恢复。 |
| `model_error` | AI Gateway 或 provider 调用失败。 |
| `policy_denied` | 工具、参数或用户权限校验失败。 |

安全规则：

- MCP server 和工具必须在白名单内。
- runtime MCP 只能通过 `streamable_http` 接入；stdio 仅用于包内 SDK lifecycle 测试，并且必须映射到代码内精确 allowlist 的 command spec，避免把配置中的 executable/argv 作为进程启动输入。
- 内置命令工具只允许 path-free diagnostic command；读取、写入或编辑文件必须通过已做 workspace/symlink 边界校验的 file tools。
- 每次工具调用必须校验 JSON Schema。
- 根据用户权限裁剪可用工具，不把未授权工具暴露给模型。
- 工具结果必须限制长度和条数，并在进入模型上下文、日志、SSE 或数据库前脱敏。
- 只读工具失败可以重试一次；写操作必须使用幂等键，不能自动盲目重试。
- 工具结果中的 prompt injection 文本不能提升工具权限、改变系统策略或启用未授权工具。
- 远程 MCP 必须使用 HTTPS、受限出站访问和独立凭证，避免 SSRF 与 token passthrough。
- QA 服务只能保存可向用户展示的处理步骤。不得保存或返回模型私有思维链、完整 prompt、内部工具参数、向量 payload、下游内部 URL、原始 token 或完整 API key。

## 内部服务接口草案

以下接口为 gateway 到 QA 的内部草案，不直接暴露给前端；公开路径仍以 `/api/v1/**` 为准。

| Method | Internal Path | 说明 |
| --- | --- | --- |
| `POST` | `/internal/qa-sessions` | 创建会话。 |
| `GET` | `/internal/qa-sessions` | 按 `X-User-Id` 查询会话列表。 |
| `POST` | `/internal/qa-sessions/{sessionId}/messages` | 创建消息并触发回答。 |
| `GET` | `/internal/qa-sessions/{sessionId}/events` | 查询短期流式事件。 |
| `GET` | `/internal/messages/{messageId}/citations` | 查询消息引用。 |
| `GET` | `/internal/qa-config-versions/current` | 查询当前 QA 配置。 |
| `POST` | `/internal/qa-config-versions` | 创建配置版本。 |
| `GET` | `/internal/response-runs/{responseRunId}` | 查询 Agent Run 内部状态。 |
| `GET` | `/internal/response-runs/{responseRunId}/tool-calls` | 查询脱敏后的工具调用摘要。 |
| `POST` | `/internal/retrieval-test-runs` | 创建检索体验测试。 |

内部服务错误也必须被 gateway 归一化为公开错误 envelope，不能把 SQL 错误、AI Gateway 或 provider 原始错误、MCP 原始错误、密钥引用、prompt、完整工具参数、工具原始结果或内部 URL 直接返回给前端。

## OpenAPI 维护清单

调整 QA 公开接口时，需要同步：

- 更新 `docs/services/gateway/api/public.openapi.yaml` 中对应 active `paths`、schemas、tags、`operationId`、错误响应和 `x-owner-service`。
- 仅在确有未定公开接口时，才把该范围登记到 `x-missing-contracts`；MCP 原始 tool schema、完整工具参数/结果和内部审计不应作为前端缺失契约登记。
- 更新 [`前后端集成契约`](../../architecture/frontend-backend-contract.md) 中 SSE、Agent Run 和 QA 路径说明。
- 更新 [`服务边界矩阵`](../../architecture/service-boundaries.md) 中 QA 契约状态。
- 前端只从 gateway OpenAPI active paths 生成或实现可调用 client。
