# AI Gateway 服务接口文档

本文档定义 `ai-gateway` 服务在项目初期的职责边界和内部接口契约。机器可读契约见 [`docs/services/ai-gateway/api/internal.openapi.yaml`](api/internal.openapi.yaml)，逻辑数据模型见 [`docs/data-models.md`](docs/data-models.md)，当前实现状态和缺口见 [`docs/implementation.md`](docs/implementation.md)。

`ai-gateway` 是内部服务，不直接面向前端。前端仍只调用 public `gateway` 的 `/api/v1/**` 接口；`qa`、`knowledge`、`document` 等领域服务在需要大模型、embedding 或 rerank 能力时，通过内部 HTTP API 调用 `ai-gateway`。管理员需要运行时管理模型配置时，也只能调用 public gateway 的 `/api/v1/admin/model-profiles` 资源，再由 gateway 调用本服务的 `/internal/v1/model-profiles`。

RESTful 路径、统一响应和错误 envelope 以 [前后端集成契约](../../architecture/frontend-backend-contract.md) 为准。AI Gateway 使用 `/internal/v1/**` 作为内部业务 API 前缀，健康检查保留 `/healthz` 和 `/readyz`。

## 相关文档

| 文档 | 内容 |
| --- | --- |
| [AI Gateway Internal OpenAPI](api/internal.openapi.yaml) | 内部服务机器可读 API 契约。 |
| [AI Gateway Public OpenAPI](api/public.openapi.yaml) | 显式声明无前端直连公开 API。 |
| [数据模型](docs/data-models.md) | 模型 profile、provider 凭据、配置审计、脱敏调用日志和安全约束。 |
| [权限矩阵](docs/permission-matrix.md) | 管理端 model profile 权限、内部模型调用服务认证和 provider 凭据保护边界。 |
| [Provider Adapter 说明](docs/provider-adapters.md) | Chat、embedding、rerank provider adapter 的请求映射、响应校验、脱敏和 usage aggregate 约束。 |
| [实现说明](docs/implementation.md) | 当前代码实现、契约对齐、缺口和最近检查记录。 |

## 职责边界

| 范围 | 说明 |
| --- | --- |
| Provider 配置 | 维护运行时模型配置，包括用途、provider 类型、base URL、模型名、超时、默认参数和 API key 写入状态。 |
| Chat completion | 接收 OpenAI-compatible chat completion 请求，转换为 OpenAI-compatible 或 SiliconFlow-compatible provider 请求，并返回 OpenAI-compatible 响应。 |
| Streaming chat | 为 QA 和报告生成等上游服务提供 OpenAI-compatible chat completion chunk 流。 |
| Function calling transport | 透传 OpenAI-compatible `tools`、`tool_choice`、`parallel_tool_calls`、`assistant.tool_calls`、`tool_call_id` 和流式 tool-call delta。 |
| Embeddings | 为知识库解析、检索等场景提供 embedding 向量生成入口。 |
| Rerankings | 为检索结果重排序提供统一入口。 |
| 错误归一化 | 将 provider validation、限流、超时、不可用等失败映射为稳定错误码。 |
| Secret handling | 接收和保存 API key 等敏感配置，但响应、日志和错误中只返回脱敏状态。 |
| Request correlation | 接收或生成 `X-Request-Id`，并在响应体、响应头和下游 provider 调用日志中贯穿。 |

`ai-gateway` 不负责知识库 CRUD、文档解析、chunk 持久化、向量库写入、RAG 编排、MCP tool discovery、MCP tool execution、QA 会话/消息、Agent Run、工具调用记录、报告记录、报告导出或 public gateway 路由。上述业务流程仍由 `knowledge`、`qa`、`document`、MCP Client 和 public `gateway` 按既有边界负责。

## 接入模型

```text
frontend
   |
   v
public gateway /api/v1/**              (frontend-facing only)
   |
   +--> qa service ------------------+
   +--> knowledge service -----------+--> ai-gateway /internal/v1/**
   +--> document service ------------+        |
                                               +--> OpenAI-compatible provider
                                               +--> SiliconFlow-compatible provider
                                               +--> local compatible provider
```

调用方必须把用户和请求上下文作为内部 header 传递给 AI Gateway。AI Gateway 使用这些上下文做审计、配额预留和问题排查，但不因此拥有领域权限判断。管理端权限、内部服务认证、caller service 白名单和模型调用拒绝规则统一维护在 [AI Gateway 权限矩阵](docs/permission-matrix.md)。

前端不得直接设置或调用这些内部接口。模型配置的前端可用管理 API 由 public `gateway` 提供：`/api/v1/admin/model-profiles` 和 `/api/v1/admin/model-profiles/{profileId}`。AI Gateway 只作为内部配置源，保存 provider 配置和 API key 写入状态，并确保响应只返回 `apiKeyConfigured` 等脱敏字段。

## 技术选型落地约束

AI Gateway 实现必须遵循 [技术选型基线](../../architecture/technology-decisions.md)。本服务只补充模型网关特有约束：

- 服务代码使用独立 Go module，目录为 `services/ai-gateway/`。
- 模型配置、凭据元数据、审计和调用摘要都以 PostgreSQL 为权威来源。
- 不保存明文 provider API key。生产优先 secret manager；第一阶段可使用数据库加密列，但必须记录加密密钥版本和脱敏写入状态。
- 本服务首期不拥有异步任务；如后续引入配额缓存、短期熔断状态或队列，缓存使用 `go-redis`，队列使用 `asynq`，PostgreSQL 仍是业务状态权威。
- Provider client 应通过 fake HTTP server 覆盖错误归一化、超时、流式取消和脱敏。
- AI Gateway、QA、document 生成链路是后续 OpenTelemetry tracing 重点。

建议服务目录：

```text
services/ai-gateway/
  cmd/server/
  internal/config/
  internal/http/
  internal/middleware/
  internal/repository/queries/
  internal/repository/sqlc/
  internal/provider/
  internal/service/
  migrations/
  sqlc.yaml
```

Provider 适配层只能处理 OpenAI-compatible、SiliconFlow-compatible 或本地兼容 provider 的协议差异，不能持有 QA、knowledge 或 document 的领域状态。

## 内部接口总览

| Method | Path | 说明 |
| --- | --- | --- |
| `GET` | `/healthz` | 进程存活检查。 |
| `GET` | `/readyz` | 配置和关键依赖就绪检查。 |
| `GET` | `/internal/v1/model-profiles` | 查询模型配置列表。 |
| `POST` | `/internal/v1/model-profiles` | 创建模型配置。 |
| `GET` | `/internal/v1/model-profiles/{profileId}` | 查询单个模型配置。 |
| `PATCH` | `/internal/v1/model-profiles/{profileId}` | 更新模型配置，包括 API key 轮换。 |
| `DELETE` | `/internal/v1/model-profiles/{profileId}` | 删除或停用模型配置。 |
| `POST` | `/internal/v1/chat/completions` | 创建 OpenAI-compatible 非流式或流式 chat completion。 |
| `POST` | `/internal/v1/embeddings` | 创建 embedding 向量。 |
| `POST` | `/internal/v1/rerankings` | 创建 OpenAI-style rerank 结果。 |

## 通用响应结构

配置、健康检查等项目自有接口的 JSON 成功和错误响应使用项目统一 envelope，具体格式见 [前后端集成契约](../../architecture/frontend-backend-contract.md)。

模型调用接口使用 OpenAI-compatible 成功响应和错误响应，不包裹 `data/requestId` envelope。调用方需要从响应头 `X-Request-Id` 读取请求追踪 ID。

OpenAI-compatible 错误响应：

```json
{
  "error": {
    "message": "request validation failed",
    "type": "invalid_request_error",
    "param": "model",
    "code": "validation_error"
  }
}
```

所有错误响应都不得包含 API key、provider bearer token、完整 prompt、原始 provider URL 中的敏感参数、内部堆栈、原始 provider 响应体或向量 payload。

## 错误码

| Code | HTTP status | 场景 |
| --- | --- | --- |
| `validation_error` | `400` | 请求字段缺失、类型错误、参数越界或 provider profile 不适用于该能力。 |
| `unauthorized` | `401` | 缺少或无法校验内部服务凭据。 |
| `forbidden` | `403` | 调用方服务无权访问配置写接口或指定模型能力。 |
| `not_found` | `404` | 指定 profile 不存在或已被隐藏。 |
| `conflict` | `409` | 配置版本冲突、默认 profile 约束冲突或 profile 正在被使用不能删除。 |
| `rate_limited` | `429` | 调用方、用户、provider 或模型配额超限。 |
| `dependency_error` | `502` | Provider 超时、不可用、返回非契约响应或网络失败。 |
| `internal_error` | `500` | AI Gateway 内部未预期错误。 |

Provider 的 `401`、`403`、`429` 和 `5xx` 不应原样透传给上游服务；AI Gateway 应归一化为自己的错误码。项目自有接口使用 `validation_error` 等错误码，OpenAI-compatible 模型调用接口使用 `invalid_request_error`、`authentication_error`、`permission_error`、`rate_limit_error`、`upstream_error` 等 OpenAI-style `error.type`。日志中只记录脱敏字段，例如 provider、profileId、status、duration 和 requestId。

## Model Profile

模型配置用 `model-profiles` 资源表示。一个 profile 绑定一个 provider、一个用途和一个模型名。用途包括：

```text
chat | embedding | rerank
```

### ModelProfile

```json
{
  "id": "mp_chat_default",
  "name": "default-chat",
  "purpose": "chat",
  "provider": "siliconflow",
  "baseUrl": "https://api.siliconflow.cn/v1",
  "model": "Qwen/Qwen2.5-72B-Instruct",
  "enabled": true,
  "isDefault": true,
  "timeoutMs": 60000,
  "apiKeyConfigured": true,
  "supportsStreaming": true,
  "dimensions": null,
  "topN": null,
  "defaultParameters": {
    "temperature": 0.2,
    "top_p": 0.9
  },
  "createdAt": "2026-06-28T10:00:00Z",
  "updatedAt": "2026-06-28T10:00:00Z"
}
```

| 字段 | 类型 | 必填 | 说明 |
| --- | --- | --- | --- |
| `id` | `string` | 是 | Profile 公开 ID。 |
| `name` | `string` | 是 | 管理展示名，同一用途内建议唯一。 |
| `purpose` | `string` | 是 | `chat`、`embedding` 或 `rerank`。 |
| `provider` | `string` | 是 | `openai_compatible`、`siliconflow` 或 `local_compatible`。 |
| `baseUrl` | `string(uri)` | 是 | Provider API base URL。错误响应和普通日志不得输出含敏感参数的 URL。 |
| `model` | `string` | 是 | Provider 模型名。 |
| `enabled` | `boolean` | 是 | 是否允许用于新请求。 |
| `isDefault` | `boolean` | 是 | 是否为该用途默认 profile。每个用途最多一个默认 profile。 |
| `timeoutMs` | `integer` | 是 | Provider 请求超时时间。 |
| `apiKeyConfigured` | `boolean` | 是 | 是否已配置 API key；响应中不返回明文 key。 |
| `supportsStreaming` | `boolean` | 是 | Chat profile 是否支持流式输出。非 chat 用途固定为 `false` 或忽略。 |
| `dimensions` | `integer` | 否 | Embedding profile 的向量维度。非 embedding 用途可为空。 |
| `topN` | `integer` | 否 | Rerank profile 的默认返回数量。非 rerank 用途可为空。 |
| `defaultParameters` | `object` | 否 | 该 profile 的 provider 特定默认参数，例如 `temperature`、`top_p`、`max_tokens` 等。请求参数可按 endpoint 规则覆盖。 |
| `createdAt` / `updatedAt` | `string(date-time)` | 是 | 创建和更新时间。 |

### CreateModelProfileRequest

创建时允许写入 `apiKey`，但响应只返回 `apiKeyConfigured`。

```json
{
  "name": "default-chat",
  "purpose": "chat",
  "provider": "siliconflow",
  "baseUrl": "https://api.siliconflow.cn/v1",
  "model": "Qwen/Qwen2.5-72B-Instruct",
  "apiKey": "sk_***",
  "enabled": true,
  "isDefault": true,
  "timeoutMs": 60000,
  "supportsStreaming": true,
  "dimensions": null,
  "topN": null,
  "defaultParameters": {
    "temperature": 0.2,
    "top_p": 0.9
  }
}
```

### UpdateModelProfileRequest

`PATCH` 使用部分更新。更新 `apiKey` 表示轮换密钥；传 `null` 或空字符串不得作为清除密钥的隐式语义。是否支持清除密钥需要后续实现单独定义，避免误删生产配置。

```json
{
  "model": "Qwen/Qwen3-32B",
  "apiKey": "sk_new_***",
  "timeoutMs": 45000,
  "enabled": true,
  "isDefault": true
}
```

## Chat Completions

`POST /internal/v1/chat/completions` 创建一次 OpenAI-compatible chat completion。该接口不保存会话历史；`qa` 和 `document` 必须自己管理业务上下文、消息持久化和重试恢复。

请求必须包含 `model`，取值可以是 provider 原始模型名，也可以是 AI Gateway 配置的模型别名。请求可额外指定 `profile_id`；若缺省，AI Gateway 使用 `purpose=chat` 的默认启用 profile。

AI Gateway 支持 OpenAI-compatible function calling 字段，但只负责请求/响应归一化和 provider 适配，不执行工具。`qa` 作为 Agent Host 负责把 MCP `tools/list` 转换为 `tools`，校验 `tool_calls`，通过 MCP Client 执行 `tools/call`，并把 `role=tool` 的结果追加回下一轮模型调用。

### ChatCompletionRequest

```json
{
  "model": "Qwen/Qwen2.5-72B-Instruct",
  "profile_id": "mp_chat_default",
  "messages": [
    {
      "role": "system",
      "content": "You are a power-industry assistant."
    },
    {
      "role": "user",
      "content": "总结迎峰度夏检查重点。"
    }
  ],
  "temperature": 0.2,
  "top_p": 0.9,
  "max_tokens": 2048,
  "stream": false,
  "tools": [
    {
      "type": "function",
      "function": {
        "name": "search_knowledge",
        "description": "Search approved knowledge bases and return citation-ready chunks.",
        "parameters": {
          "type": "object",
          "properties": {
            "query": {
              "type": "string"
            }
          },
          "required": ["query"]
        }
      }
    }
  ],
  "tool_choice": "auto",
  "parallel_tool_calls": false,
  "metadata": {
    "workflow": "qa"
  }
}
```

| 字段 | 类型 | 必填 | 说明 |
| --- | --- | --- | --- |
| `model` | `string` | 是 | OpenAI-compatible 模型名或 AI Gateway 模型别名。 |
| `profile_id` | `string` | 否 | 指定 chat profile；缺省使用默认 chat profile。 |
| `messages` | `ChatMessage[]` | 是 | 本次请求的完整消息上下文。AI Gateway 不读取历史会话。 |
| `temperature` | `number` | 否 | 采样温度，范围由 profile/provider 实现约束。 |
| `top_p` | `number` | 否 | nucleus sampling 参数。 |
| `max_tokens` | `integer` | 否 | 最大输出 token 数。 |
| `stream` | `boolean` | 否 | `true` 时使用 SSE 响应；客户端也应发送 `Accept: text/event-stream`。 |
| `tools` | `Tool[]` | 否 | OpenAI-compatible function calling 工具定义。AI Gateway 只转发给 provider，不校验领域权限。 |
| `tool_choice` | `string \| object` | 否 | `auto`、`none`、`required` 或指定 function。 |
| `parallel_tool_calls` | `boolean` | 否 | 是否允许模型在一轮返回多个并行工具调用。是否实际并行执行由调用方决定。 |
| `metadata` | `object` | 否 | 调用方自定义审计元数据。不得放入密钥、原文档全文或敏感业务数据。 |

### ChatCompletionResponse

```json
{
  "id": "chatcmpl_123",
  "object": "chat.completion",
  "created": 1782631200,
  "model": "Qwen/Qwen2.5-72B-Instruct",
  "choices": [
    {
      "index": 0,
      "message": {
        "role": "assistant",
        "content": "迎峰度夏检查应重点关注设备负荷、隐患治理和应急预案。",
        "tool_calls": []
      },
      "finish_reason": "stop"
    }
  ],
  "usage": {
    "prompt_tokens": 128,
    "completion_tokens": 32,
    "total_tokens": 160
  }
}
```

工具调用响应示例：

```json
{
  "id": "chatcmpl_124",
  "object": "chat.completion",
  "created": 1782631201,
  "model": "Qwen/Qwen2.5-72B-Instruct",
  "choices": [
    {
      "index": 0,
      "message": {
        "role": "assistant",
        "content": null,
        "tool_calls": [
          {
            "id": "call_001",
            "type": "function",
            "function": {
              "name": "search_knowledge",
              "arguments": "{\"query\":\"迎峰度夏检查重点\"}"
            }
          }
        ]
      },
      "finish_reason": "tool_calls"
    }
  ]
}
```

调用方执行工具后，应在下一轮请求中追加 `role=tool` 消息：

```json
{
  "role": "tool",
  "tool_call_id": "call_001",
  "content": "{\"summary\":\"命中 8 个片段\"}"
}
```

`role=tool` 的 `content` 必须由调用方脱敏和裁剪。AI Gateway 不保存、审计或改写完整工具结果。

## Streaming Chat

流式输出复用 `POST /internal/v1/chat/completions`。当 `stream=true` 且客户端接受 `text/event-stream` 时，成功响应的 `Content-Type` 为 `text/event-stream`，不使用 JSON envelope 包裹每个事件。事件 payload 使用 OpenAI-compatible chat completion chunk。

事件格式：

chunk 示例：

```text
data: {"id":"chatcmpl_123","object":"chat.completion.chunk","created":1782631200,"model":"Qwen/Qwen2.5-72B-Instruct","choices":[{"index":0,"delta":{"content":"迎峰度夏"},"finish_reason":null}]}
```

完成示例：

```text
data: [DONE]
```

流式实现要求：

- 上游请求取消时，AI Gateway 必须取消 provider 请求。
- 不得等待 provider 完整响应后再一次性发送给调用方。
- Provider 原始事件字段不得直接泄露给调用方；对外只暴露 OpenAI-compatible chunk 字段。
- 如果 provider 返回 tool-call delta，AI Gateway 应归一化为 OpenAI-compatible `delta.tool_calls`，并保持 `index`、`id`、`type`、`function.name` 和 `function.arguments` 增量语义。
- 流式错误不得包含原始 provider body、API key、prompt 全文或堆栈。

## Embeddings

`POST /internal/v1/embeddings` 创建一个或多个输入文本的 OpenAI-compatible embedding。该接口不负责将向量写入 Qdrant；`knowledge` 服务负责持久化、索引和 chunk 关联。

请求 `model` 必须与解析出的 embedding profile `model` 完全一致；AI Gateway 实际转发给 provider 的模型名以 profile 配置为准，调用方不能借用该 profile 的凭据调用其他 provider 模型。

### EmbeddingRequest

```json
{
  "model": "BAAI/bge-m3",
  "profile_id": "mp_embedding_default",
  "input": [
    "变压器油温异常处理要求",
    "迎峰度夏设备检查重点"
  ],
  "dimensions": 1024,
  "encoding_format": "float"
}
```

### EmbeddingResponse

```json
{
  "object": "list",
  "data": [
    {
      "object": "embedding",
      "index": 0,
      "embedding": [0.0123, -0.0456]
    }
  ],
  "model": "BAAI/bge-m3",
  "usage": {
    "prompt_tokens": 64,
    "total_tokens": 64
  }
}
```

`embedding` 字段在 `encoding_format=float` 时是 float array，在 `encoding_format=base64` 时是 base64 string。调用方日志和错误响应不得输出完整 embedding payload；向量 payload 可能包含原文语义信息，按敏感数据处理。

## Rerankings

`POST /internal/v1/rerankings` 对候选文本进行重排序。OpenAI 官方 API 没有原生 rerank endpoint，因此该接口是 OpenAI-style 扩展：使用 snake_case 字段、`object` 标记、`data` 列表和 OpenAI-compatible error body。该接口不负责检索候选集，也不决定 RAG 引用格式；`knowledge` 或 `qa` 负责业务过滤、召回和引用。

请求 `model` 必须与解析出的 rerank profile `model` 完全一致；AI Gateway 实际转发给 provider 的模型名以 profile 配置为准，调用方不能借用该 profile 的凭据调用其他 provider 模型。

### RerankingRequest

```json
{
  "model": "BAAI/bge-reranker-v2-m3",
  "profile_id": "mp_rerank_default",
  "query": "迎峰度夏检查重点是什么？",
  "documents": [
    {
      "id": "chunk_1",
      "text": "迎峰度夏期间应重点检查主变负荷、冷却系统和应急预案。"
    },
    {
      "id": "chunk_2",
      "text": "煤库存审计关注库存盘点、热值和入厂煤记录。"
    }
  ],
  "top_n": 5
}
```

### RerankingResponse

```json
{
  "object": "list",
  "data": [
    {
      "index": 0,
      "document_id": "chunk_1",
      "score": 0.92
    }
  ],
  "model": "BAAI/bge-reranker-v2-m3",
  "usage": {
    "prompt_tokens": 96,
    "total_tokens": 96
  }
}
```

AI Gateway 只返回排序分数和原输入文档 ID/index，不返回额外业务引用字段。引用标题、章节路径、原文下载等由 `qa` 或 `knowledge` 在自己的契约中定义。

## 配置与就绪语义

`GET /readyz` 应体现 AI Gateway 是否具备处理请求的最低配置条件：

- 至少存在一个 enabled chat profile，且已配置 active credential。
- 至少存在一个 enabled embedding profile，且已配置 active credential。
- 至少存在一个 enabled rerank profile，且已配置 active credential。
- 配置存储可读。

`check.status` 使用 `ok`、`missing`、`placeholder` 或 `failed`。`missing` 表示缺少对应 profile 或 active credential；`placeholder` 表示根级本地 seed 仍使用占位 provider key；`ok` 只表示已配置非占位 credential，不代表真实 provider 已接受该 key。检查结果不得包含 API key 明文、fingerprint、key last4 或 provider 原始错误体；真实 provider 可用性必须通过显式 env-gated smoke 验证。

示例：

```json
{
  "data": {
    "status": "degraded",
    "checks": [
      {
        "name": "chat_profile",
        "status": "ok"
      },
      {
        "name": "embedding_profile",
        "status": "placeholder"
      }
    ]
  },
  "requestId": "req_123"
}
```

## 配置项约定

AI Gateway 的环境变量应按结构化配置分组，服务启动时一次性解析、校验并输出脱敏配置摘要。以下名称是建议基线，实际实现如需调整必须同步更新本文：

| 环境变量 | 必填 | 说明 |
| --- | --- | --- |
| `AI_GATEWAY_HTTP_ADDR` | 是 | HTTP 监听地址，例如 `:8080`。 |
| `AI_GATEWAY_DATABASE_URL` | 是 | PostgreSQL 连接串；不得写入日志。 |
| `AI_GATEWAY_SERVICE_TOKEN_HASHES` | 是 | 允许的内部服务 token hash 列表，不能配置明文 token。 |
| `AI_GATEWAY_SECRET_MODE` | 是 | `secret_ref` 或 `encrypted_column`。 |
| `AI_GATEWAY_CREDENTIAL_ENCRYPTION_KEY_REF` | 条件 | `encrypted_column` 模式下的加密密钥引用或版本。 |
| `AI_GATEWAY_DEFAULT_TIMEOUT_MS` | 否 | Provider 请求默认超时，profile 未配置时使用。 |
| `AI_GATEWAY_MAX_REQUEST_BYTES` | 否 | JSON 请求体大小限制。 |
| `AI_GATEWAY_METRICS_ADDR` | 否 | 预留 metrics 监听地址；当前代码只解析配置，尚未启动独立 metrics listener。 |

配置校验失败时服务应启动失败，不应以缺省空 token、空数据库连接串或明文密钥配置继续运行。启动日志只能输出配置项是否存在、超时和非敏感开关，不能输出 token、数据库连接串、secret ref、加密密钥引用或 provider API key。

## 安全与日志规则

- 配置写接口必须要求内部服务认证，后续还需叠加管理员权限或配置服务授权。
- `apiKey` 是 write-only 字段；任何响应中都只能返回 `apiKeyConfigured`。
- 内部服务 token 按 opaque token 处理；服务侧只保存和比对 token hash，不记录原始 token。
- 日志不得记录 API key、bearer token、数据库连接串、secret ref、加密密钥引用、完整 prompt、完整 generated answer、完整 embedding payload、原始 provider 响应体或用户上传文档全文。
- Provider 调用日志建议记录：`service=ai-gateway`、`request_id`、`caller_service`、`operation`、`profile_id`、`provider`、`model`、`status`、`duration_ms`。
- Metrics label 只能使用低基数字段，例如 `operation`、`provider`、`model_purpose`、`status` 和归一化错误码；不得使用用户输入、prompt hash、object key、API key 指纹、完整 model name 或完整 base URL。
- 对外错误消息保持稳定简短，详细 provider 失败信息只进入脱敏日志。

## 实现状态

当前代码实现、临时后端、文档与实现出入和建议任务统一维护在
[`docs/implementation.md`](docs/implementation.md)。本文档只保留 AI Gateway
的职责边界、内部接口语义和稳定安全规则；实现缺口不在 README 重复维护。
