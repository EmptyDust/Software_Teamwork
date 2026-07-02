# QA 数据模型文档

## 1. 文档说明

本文定义 `qa` 服务的逻辑数据模型，用于支撑会话、消息、Agent Run、模型调用、MCP 工具调用、SSE 事件回放、引用快照、配置版本、LLM 连接测试、检索体验测试和 QA 指标查询。

本文只描述逻辑数据模型，不提供具体 SQL 建表语句。后续实现应根据服务代码、PostgreSQL 规范和迁移策略转换为 migration。稳定前端公开契约以 [`../../gateway/api/public.openapi.yaml`](../../gateway/api/public.openapi.yaml) 为准，领域说明见 [`../README.md`](../README.md)。

## 2. 存储边界

### 2.1 QA 持久化数据库

QA 数据库保存 QA 自己拥有的业务状态：

- QA 会话、会话归属用户和软删除状态。
- 用户消息、助手消息和可展示消息内容块。
- 会话临时附件元数据、解析状态、临时解析 chunk 和消息附件关联。
- 一次回答生成的 `response_run` 状态、配置版本、token 用量、延迟和终止原因。
- 每轮 AI Gateway 模型调用的脱敏摘要。
- 每次 MCP 工具调用的脱敏参数摘要和结果摘要。
- 可向前端展示的处理步骤。
- 短期 SSE 事件，用于断线恢复和调试。
- 回答引用快照，保证历史回答可追溯。
- QA 配置版本、默认知识库快照和 LLM 配置版本。
- LLM 连接测试的脱敏结果。
- 检索体验测试运行和结果快照。
- 管理员配置变更审计日志。

QA 数据库不得保存用户主数据、角色权限主数据、知识库主数据、文档原文件、向量索引、报告业务数据、provider API key、provider base URL、完整 prompt、私有 chain-of-thought、完整 MCP 参数、完整 MCP 原始结果、内部 URL、MinIO object key 或原始文档全文。

### 2.2 外部服务标识

跨服务引用只保存外部 owner 的公开 ID 和必要展示快照，不在 QA 数据库中创建跨服务物理外键：

| 字段 | 外部 owner | 说明 |
| --- | --- | --- |
| `external_user_id` | `auth` | Gateway 认证后注入的用户 ID。 |
| `external_kb_id` | `knowledge` | 知识库 ID；QA 只保存配置快照、引用快照或测试结果。 |
| `external_doc_id` | `knowledge` / `file` | 文档 ID；原文件内容仍通过 gateway 的 file-owned API 读取。 |
| `external_chunk_id` | `knowledge` | 文档切片 ID；chunk 主数据和向量索引归 knowledge。 |
| `profile_id` | `ai-gateway` | AI Gateway 模型 profile ID；provider 凭证和 base URL 归 AI Gateway。 |

### 2.3 短期缓存

SSE 传输层可以使用 Redis 或内存队列辅助推送，但 PostgreSQL 中的 `response_stream_events` 是断线恢复和调试回放的权威短期事件记录。事件过期后可清理，不作为长期消息正文来源。最终可展示回答必须落入 `messages` 和 `message_content_blocks`。

## 3. 设计原则

- 数据库字段使用 snake_case；公开 API 字段使用 camelCase。
- 主键建议使用 UUID 或带业务前缀的字符串 ID；公开响应始终按 string 暴露。
- 时间字段使用 `TIMESTAMPTZ`，公开 API 映射为 RFC 3339 / OpenAPI `date-time`。
- QA 自己拥有的表之间应创建物理 FK；跨服务外部 ID 不创建物理 FK。
- 配置采用版本化资源，历史 `response_runs` 必须引用当时使用的 QA/LLM 配置版本。
- `qa_config_versions` 和 `llm_config_versions` 必须通过部分唯一索引保证最多一个 `is_active = true`。
- 所有可展示步骤、工具调用摘要、错误摘要和审计字段都必须先脱敏再入库。
- API 响应字段以 gateway OpenAPI 为准；内部字段与公开字段不是简单大小写转换时，本文单独列出映射。

## 4. 持久化实现基线

本节把逻辑模型约束映射到当前技术选型。实现时以 [`../../../architecture/technology-decisions.md`](../../../architecture/technology-decisions.md) 为工程基线；如需偏离，必须先在 [`../README.md`](../README.md) 说明原因。

### 4.1 PostgreSQL、pgx 和 sqlc

- QA 数据库访问使用 `pgx` + `sqlc`，不默认引入 GORM/ent 等 ORM。
- `sqlc.yaml` 放在 `services/qa/sqlc.yaml`；查询 SQL 放在 `services/qa/internal/repository/queries/`；生成代码放在 `services/qa/internal/repository/sqlc/`。
- `sqlc` 生成代码只能被 repository 适配层调用，HTTP handler、Agent loop 和 MCP client 不直接依赖生成类型。
- SQL 查询必须显式列名，不使用 `SELECT *`。
- 用户输入、工具参数、知识库 ID、会话 ID 和分页参数必须通过 SQL 参数绑定传入，不拼接 SQL 字符串。
- `metadata`、`arguments_summary`、`result_summary`、`payload` 等 JSONB 字段写入前必须先完成 schema 校验、长度限制和脱敏。

### 4.2 goose 迁移

- QA 迁移文件放在 `services/qa/migrations/`，文件名使用有序前缀，例如 `0001_create_qa_core_tables.sql`。
- 首期允许 forward-only migration；如果提供 down migration，必须能在本地和 CI 中验证。
- 配置激活、消息顺序、SSE replay 顺序、工具调用幂等和引用编号等约束应通过数据库唯一索引落地，而不是只依赖应用层检查。
- `qa_config_versions` 和 `llm_config_versions` 的“最多一个 active 版本”必须使用 PostgreSQL 部分唯一索引实现。

### 4.3 事务和并发控制

- 创建用户消息、助手占位消息、`response_runs` 和首个 `message.created` 事件必须在同一事务内完成。
- 配置版本切换必须在同一事务中完成：插入新版本、失活旧版本、激活新版本、写入 `admin_audit_logs`。
- SSE 事件写入必须保证 `(response_run_id, event_seq)` 单调且唯一；可使用事务内序号分配或显式行级锁。
- Agent Run 取消应以 PostgreSQL 中的 `response_runs.status` 为权威，并通过 Redis 或内存信号辅助打断正在执行的模型/工具请求。
- Redis、内存队列或 SSE 连接状态不得成为消息正文、运行最终状态、引用快照或工具调用审计的唯一来源。

### 4.4 日志、指标和保留

- 日志使用 `log/slog`，生产默认 JSON；日志字段至少包含 `service=qa`、`request_id`、`operation`、`status`。
- `request_id` 必须写入关键事实表：`response_runs`、`llm_connection_tests`、`retrieval_test_runs`、`admin_audit_logs`。
- 指标可以从本模型聚合得到；Prometheus label 不得包含用户问题全文、prompt、工具原始参数、object key、token、API key 指纹或 provider 原始错误。
- `response_stream_events` 是短期事件记录，必须设置 `expires_at` 并由清理任务定期删除；清理任务如异步执行，应使用 `asynq`，但清理结果不改变业务事实。

## 5. 实体关系概览

```text
QASession 1 ── N QAMessage
QASession 1 ── N QAResponseRun

QASession 1 ── N SessionAttachment

QAMessage 1 ── N MessageContentBlock
QAMessage 1 ── N QACitation
QAMessage N ── N SessionAttachment

SessionAttachment 1 ── N SessionAttachmentChunk

QAResponseRun 1 ── N AgentModelInvocation
QAResponseRun 1 ── N AgentToolCall
QAResponseRun 1 ── N ResponseProcessStep
QAResponseRun 1 ── N ResponseStreamEvent
QAResponseRun 1 ── N QACitation

AgentModelInvocation 1 ── N AgentToolCall

QAConfigVersion 1 ── N QAConfigKnowledgeBase
QAConfigVersion 1 ── N QAResponseRun
QAConfigVersion 1 ── N RetrievalTestRun

LLMConfigVersion 1 ── N QAResponseRun
LLMConfigVersion 1 ── N LLMConnectionTest

RetrievalTestRun 1 ── N RetrievalTestResult
```

## 6. 通用字段约定

| 字段 | 说明 |
| --- | --- |
| `id` | 主键。 |
| `created_at` | 创建时间。 |
| `updated_at` | 更新时间。 |
| `deleted_at` | 软删除时间，仅用于可软删除资源。 |
| `created_by_user_id` | 创建人外部用户 ID。 |
| `updated_by_user_id` | 最近修改人外部用户 ID。 |
| `request_id` | Gateway 请求追踪 ID。 |
| `metadata` | JSONB 扩展字段；不得包含秘密、完整 prompt、内部 URL 或原始文档全文。 |

## 7. 配置与管理实体

### 7.1 QAConfigVersion

表名建议：`qa_config_versions`

QA 运行配置版本。用于保存检索默认参数、Agent 终止策略、工具白名单和版本激活状态。

| 字段 | 类型建议 | 说明 |
| --- | --- | --- |
| `id` | uuid/string | 配置版本 ID。 |
| `version_no` | int | 递增版本号，唯一。 |
| `top_k` | int | 默认检索返回数量；对应 `retrieval.topK`。 |
| `score_threshold` | decimal | 默认相似度阈值；对应 `retrieval.scoreThreshold`。旧字段 `similarityThreshold` 仅作为 API 兼容别名。 |
| `enable_rerank` | boolean | 是否启用重排序；旧字段 `useRerank` 仅作为 API 兼容别名。 |
| `rerank_threshold` | decimal | 重排序分数阈值。 |
| `rerank_top_n` | int | 重排序后保留数量。 |
| `tag_filters_default_json` | jsonb | 默认标签过滤，可选。 |
| `max_iterations` | int | 单次 Agent Run 最大 ReAct 迭代次数。 |
| `tool_timeout_seconds` | int | 单次 MCP 工具调用超时。 |
| `model_timeout_seconds` | int | 单次 AI Gateway 模型调用超时。 |
| `overall_timeout_seconds` | int | 单次 Agent Run 总超时。 |
| `enabled_tool_names_json` | jsonb | 工具白名单数组，例如 `["search_knowledge"]`。 |
| `is_active` | boolean | 是否当前生效。 |
| `created_by_user_id` | string | 创建人外部用户 ID。 |
| `created_at` | datetime | 创建时间。 |

约束建议：

- `version_no` 唯一。
- `top_k BETWEEN 1 AND 100`。
- `score_threshold >= 0`，如按归一化分数实现则应限制 `<= 1`。
- `rerank_top_n` 为空或 `rerank_top_n <= top_k`。
- `max_iterations BETWEEN 1 AND 10`。
- 部分唯一索引：`UNIQUE (is_active) WHERE is_active = true`。

公开 API 字段映射：

| 数据库字段 | 公开 API 字段 |
| --- | --- |
| `version_no` | `versionNo` |
| `top_k` | `retrieval.topK` |
| `score_threshold` | `retrieval.scoreThreshold` |
| `enable_rerank` | `retrieval.enableRerank` |
| `enabled_tool_names_json` | `enabledToolNames` 或 `agent.enabledToolNames` |

### 7.2 QAConfigKnowledgeBase

表名建议：`qa_config_knowledge_bases`

QA 配置版本绑定的默认知识库快照。知识库主数据仍归 knowledge。

| 字段 | 类型建议 | 说明 |
| --- | --- | --- |
| `config_id` | uuid/string | 所属 `qa_config_versions.id`。 |
| `external_kb_id` | string | Knowledge 服务知识库 ID。 |
| `kb_type` | string | 知识库类型快照。 |
| `display_name_snapshot` | string | 创建配置时的知识库名称快照。 |
| `sort_order` | int | 展示或检索排序。 |
| `created_at` | datetime | 创建时间。 |

约束建议：

- FK：`config_id -> qa_config_versions.id`。
- 主键或唯一约束：`(config_id, external_kb_id)`。
- `sort_order >= 0`。

### 7.3 LLMConfigVersion

表名建议：`llm_config_versions`

QA-owned LLM 配置版本，只保存 AI Gateway profile 引用、模型名和生成参数。Provider 凭证、base URL 和供应商适配逻辑不归 QA 保存。

| 字段 | 类型建议 | 说明 |
| --- | --- | --- |
| `id` | uuid/string | LLM 配置版本 ID。 |
| `version_no` | int | 递增版本号，唯一。 |
| `provider` | string | 固定为 `ai-gateway`。 |
| `profile_id` | string | AI Gateway chat model profile ID。 |
| `model_name` | string | 模型名称或 AI Gateway alias。 |
| `timeout_seconds` | int | 模型请求超时。 |
| `temperature` | decimal | 生成温度。 |
| `max_tokens` | int | 最大输出 token。 |
| `is_active` | boolean | 是否当前生效。 |
| `created_by_user_id` | string | 创建人外部用户 ID。 |
| `created_at` | datetime | 创建时间。 |

不得出现的字段：

- `api_url`
- `api_key`
- `api_key_secret_ref`
- `api_key_last4`
- provider 原始错误详情

约束建议：

- `version_no` 唯一。
- `provider = 'ai-gateway'`。
- `timeout_seconds >= 1`。
- `max_tokens >= 1`。
- 部分唯一索引：`UNIQUE (is_active) WHERE is_active = true`。

### 7.4 LLMConnectionTest

表名建议：`llm_connection_tests`

一次 LLM 配置连接测试记录。该表只保存脱敏测试结果，不保存测试 prompt、provider 原始错误、provider 密钥或内部 URL。

| 字段 | 类型建议 | 说明 |
| --- | --- | --- |
| `id` | uuid/string | 连接测试 ID。 |
| `llm_config_version_id` | uuid/string | 被测试的 LLM 配置版本，可为空。 |
| `external_user_id` | string | 发起测试的用户 ID。 |
| `provider` | string | 固定为 `ai-gateway`。 |
| `profile_id` | string | 被测试的 profile ID。 |
| `model_name` | string | 被测试的模型名。 |
| `success` | boolean | 是否成功。 |
| `latency_ms` | int | 测试耗时。 |
| `error_code` | string | 脱敏后的错误码。 |
| `error_message` | string | 面向管理端的脱敏错误摘要。 |
| `request_id` | string | Gateway 请求追踪 ID。 |
| `tested_at` | datetime | 测试时间。 |

约束建议：

- FK：`llm_config_version_id -> llm_config_versions.id`，可空。
- `provider = 'ai-gateway'`。

### 7.5 AdminAuditLog

表名建议：`admin_audit_logs`

管理员配置变更审计日志。

| 字段 | 类型建议 | 说明 |
| --- | --- | --- |
| `id` | uuid/string | 审计日志 ID。 |
| `external_user_id` | string | 操作人用户 ID。 |
| `action` | string | 操作类型，例如 `create`、`activate`、`test_connection`。 |
| `target_type` | string | 操作对象类型，例如 `qa_config`、`llm_config`。 |
| `target_id` | string | 操作对象 ID。 |
| `before_data` | jsonb | 脱敏变更前快照。 |
| `after_data` | jsonb | 脱敏变更后快照。 |
| `request_id` | string | Gateway 请求追踪 ID。 |
| `ip_address` | string | 来源 IP。 |
| `created_at` | datetime | 创建时间。 |

安全约束：

- `before_data` 和 `after_data` 不得包含 provider 密钥、完整 prompt、内部 URL、object key 或完整工具参数。

## 8. 会话与消息实体

### 8.1 QASession

表名建议：`conversations`

用户的 QA 会话。

| 字段 | 类型建议 | 说明 |
| --- | --- | --- |
| `id` | uuid/string | 会话 ID；公开为 `QASession.id`。 |
| `external_user_id` | string | 会话归属用户。 |
| `title` | string | 会话标题，可为空。 |
| `status` | string | `active` 或 `archived`。 |
| `last_message_at` | datetime | 最近消息时间，用于会话列表排序。 |
| `created_at` | datetime | 创建时间。 |
| `updated_at` | datetime | 更新时间。 |
| `deleted_at` | datetime | 软删除时间。 |

约束建议：

- `status IN ('active', 'archived')`。
- 会话列表查询默认过滤 `deleted_at IS NULL`。

### 8.2 QAMessage

表名建议：`messages`

会话内消息元数据。消息正文从 `message_content_blocks` 合并得到。

| 字段 | 类型建议 | 说明 |
| --- | --- | --- |
| `id` | uuid/string | 消息 ID。 |
| `conversation_id` | uuid/string | 所属会话。 |
| `role` | string | `user`、`assistant` 或 `system`。 |
| `sequence_no` | int | 会话内消息顺序。 |
| `status` | string | `queued`、`streaming`、`completed`、`stopped`、`failed` 或 `cancelled`。 |
| `intent_type` | string | `knowledge_qa`、`general_chat`、`report_generation`、`data_analysis` 或 `unknown`，可空。 |
| `model_name` | string | 生成助手消息时使用的模型名，可空。 |
| `content_preview` | string | 列表展示摘要，可由内容块生成并缓存。 |
| `error_code` | string | 脱敏错误码。 |
| `error_message` | string | 脱敏错误摘要。 |
| `created_at` | datetime | 创建时间。 |
| `completed_at` | datetime | 完成时间。 |

约束建议：

- FK：`conversation_id -> conversations.id`。
- `role IN ('user', 'assistant', 'system')`。
- `status IN ('queued', 'streaming', 'completed', 'stopped', 'failed', 'cancelled')`。
- 唯一约束：`(conversation_id, sequence_no)`。

状态说明：

| status | 说明 |
| --- | --- |
| `queued` | 已创建但尚未开始处理。 |
| `streaming` | 助手回答正在流式生成。 |
| `completed` | 消息已完整保存。 |
| `stopped` | 兼容前端旧状态，表示已停止展示；新实现优先用 `cancelled` 表示用户取消。 |
| `failed` | 生成失败。 |
| `cancelled` | 用户、客户端断开或上游取消导致停止。 |

### 8.3 MessageContentBlock

表名建议：`message_content_blocks`

消息内容块。用于支持流式追加、多块文本和未来多模态扩展。

| 字段 | 类型建议 | 说明 |
| --- | --- | --- |
| `id` | uuid/string | 内容块 ID。 |
| `message_id` | uuid/string | 所属消息。 |
| `block_order` | int | 消息内块顺序。 |
| `block_type` | string | `text`、`markdown`、`displayable_reasoning`、`tool_result_summary` 等。 |
| `content` | text | 可展示内容。 |
| `status` | string | `queued`、`streaming`、`completed`、`stopped`、`failed` 或 `cancelled`。 |
| `metadata` | jsonb | 脱敏扩展信息。 |
| `created_at` | datetime | 创建时间。 |
| `completed_at` | datetime | 完成时间。 |

约束建议：

- FK：`message_id -> messages.id`。
- 唯一约束：`(message_id, block_order)`。
- `content` 不得保存私有 chain-of-thought、完整 prompt、完整工具参数、完整工具结果或原始文档全文。

### 8.4 SessionAttachment

表名建议：`session_attachments`

用户在一次 QA 会话中上传的临时附件元数据。QA 拥有附件元数据和解析状态；原始文件 bytes 归 file 服务，OCR/文档解析归 parser 内部调用。QA 不保存 `file_ref`、MinIO object key、bucket 或内部 URL 作为公开字段。

| 字段 | 类型建议 | 说明 |
| --- | --- | --- |
| `id` | uuid/string | 附件 ID；公开为 `SessionAttachment.id`。 |
| `session_id` | uuid/string | 所属会话；公开为 `sessionId`。 |
| `external_user_id` | string | 附件归属用户，用于 owner 授权。 |
| `filename` | string | 客户端原始文件名。 |
| `content_type` | string | 声明的 MIME 类型。 |
| `size_bytes` | int | 文件大小，可空。 |
| `status` | string | `uploaded`、`parsing`、`ready`、`failed` 或 `purged`。 |
| `file_ref` | string | 指向 file 服务对象的内部引用；仅内部使用，不作为公开字段返回。 |
| `error_code` | string | 脱敏解析错误码，可空。 |
| `error_message` | string | 面向前端的脱敏解析错误摘要，可空。 |
| `created_at` | datetime | 创建时间。 |
| `updated_at` | datetime | 更新时间。 |
| `expires_at` | datetime | TTL 过期时间，到期后附件和临时 chunk 被清理。 |

约束建议：

- FK：`session_id -> conversations.id`。
- `status IN ('uploaded', 'parsing', 'ready', 'failed', 'purged')`。
- 附件归属字段为 `external_user_id`；访问控制和隐藏策略见 [QA 权限矩阵](permission-matrix.md)。
- `file_ref` 不得进入公开响应、日志或指标 label。

状态转换：

| 转换 | 说明 |
| --- | --- |
| `uploaded → parsing` | 原始 bytes 存入 file 后触发 parser 内部解析。 |
| `parsing → ready` | 解析完成，parsed content 和临时 chunk 可用于检索与消息关联。 |
| `parsing → failed` | 解析失败；`error_code`/`error_message` 保存脱敏摘要。 |
| `* → purged` | TTL 清理终态；附件公开元数据保留与否由产品口径决定，临时 chunk 必须删除。 |

公开 API 字段映射：

| 数据库字段 | 公开 API 字段 |
| --- | --- |
| `session_id` | `sessionId` |
| `content_type` | `contentType` |
| `size_bytes` | `sizeBytes` |
| `expires_at` | `expiresAt` |
| `file_ref` | 不暴露 |

### 8.5 SessionAttachmentChunk

表名建议：`session_attachment_chunks`

会话附件解析后产生的临时 chunk，仅用于当前会话的 Agent 检索入口，不进入 knowledge 的长期向量索引。临时 chunk 的生命周期与所属附件的 TTL 联动清理。

| 字段 | 类型建议 | 说明 |
| --- | --- | --- |
| `id` | uuid/string | 临时 chunk ID。 |
| `attachment_id` | uuid/string | 所属会话附件。 |
| `session_id` | uuid/string | 所属会话，便于会话级检索与清理。 |
| `chunk_index` | int | 附件内 chunk 顺序。 |
| `content` | text | 脱敏可检索内容。 |
| `token_count` | int | token 数，可空。 |
| `metadata` | jsonb | 脱敏扩展信息，例如页码。 |
| `expires_at` | datetime | 与所属附件 TTL 联动的过期时间。 |
| `created_at` | datetime | 创建时间。 |

约束建议：

- FK：`attachment_id -> session_attachments.id`，级联删除。
- 唯一约束：`(attachment_id, chunk_index)`。
- `content` 不得保存原始文档全文以外无关信息，也不得保存内部 URL 或 object key。
- 临时 chunk 属于会话临时上下文，不写入 knowledge 的 Qdrant 集合或长期分块表。

### 8.6 消息附件关联

助手回答可引用当前会话的会话附件。消息与附件的多对多关联建议存于 `message_attachments`（`message_id`、`attachment_id`），或复用 `QAMessage.attachmentIds` 公开字段的持久化形式。

- `QAMessage` 通过 `attachmentIds` 引用会话附件；每个被引用附件必须与消息属于同一会话。
- 仅允许引用 `status = ready` 的附件；`uploaded`、`parsing`、`failed`、`purged` 状态的附件被拒绝，返回 `validation_error` 或 `conflict`。
- 附件被 TTL 清理为 `purged` 后，历史消息可保留引用记录，但不再保证临时 chunk 可检索。

## 9. Agent Run 实体

### 9.1 QAResponseRun

表名建议：`response_runs`

一次助手回答生成运行。一个用户消息通常对应一个 response run。

| 字段 | 类型建议 | 说明 |
| --- | --- | --- |
| `id` | uuid/string | Run ID。 |
| `conversation_id` | uuid/string | 所属会话。 |
| `user_message_id` | uuid/string | 触发本次运行的用户消息。 |
| `assistant_message_id` | uuid/string | 本次运行生成的助手消息。 |
| `qa_config_version_id` | uuid/string | 使用的 QA 配置版本。 |
| `llm_config_version_id` | uuid/string | 使用的 LLM 配置版本。 |
| `request_id` | string | Gateway 请求追踪 ID。 |
| `status` | string | `queued`、`running`、`streaming`、`completed`、`failed` 或 `cancelled`。 |
| `current_iteration` | int | 当前 ReAct 迭代序号。 |
| `max_iterations` | int | 本次运行实际使用的最大迭代次数。 |
| `termination_reason` | string | 终止原因，见枚举。 |
| `intent_type` | string | 归一化意图。 |
| `total_tokens` | int | token 总量。 |
| `prompt_tokens` | int | 输入 token 数。 |
| `completion_tokens` | int | 输出 token 数。 |
| `reasoning_tokens` | int | provider 暴露的 reasoning token 数，可空。 |
| `latency_ms` | int | 总耗时。 |
| `error_code` | string | 脱敏错误码。 |
| `error_message` | string | 脱敏错误摘要。 |
| `started_at` | datetime | 开始时间。 |
| `completed_at` | datetime | 完成时间。 |
| `created_at` | datetime | 创建时间。 |

约束建议：

- FK：`conversation_id -> conversations.id`。
- FK：`user_message_id -> messages.id`。
- FK：`assistant_message_id -> messages.id`，可空直到助手消息创建完成。
- FK：`qa_config_version_id -> qa_config_versions.id`。
- FK：`llm_config_version_id -> llm_config_versions.id`。
- `status IN ('queued', 'running', 'streaming', 'completed', 'failed', 'cancelled')`。
- `termination_reason IN ('completed', 'max_iterations', 'timeout', 'cancelled', 'tool_error', 'model_error', 'policy_denied')` 或为空。

公开 API 字段映射：

| 数据库字段 | 公开 API 字段 |
| --- | --- |
| `conversation_id` | `sessionId` |
| `termination_reason` | `terminationReason` |
| `total_tokens` | `totalTokens` |
| `latency_ms` | `latencyMs` |

### 9.2 AgentModelInvocation

表名建议：`agent_model_invocations`

每次 QA 调用 AI Gateway chat completions 形成一条模型调用记录，用于调试、统计和成本分析。该实体默认不作为前端公开字段直接暴露。

| 字段 | 类型建议 | 说明 |
| --- | --- | --- |
| `id` | uuid/string | 模型调用 ID。 |
| `response_run_id` | uuid/string | 所属 Agent Run。 |
| `iteration_no` | int | ReAct 第几轮，从 1 开始。 |
| `provider` | string | 固定为 `ai-gateway`。 |
| `profile_id` | string | AI Gateway profile ID。 |
| `model_name` | string | 模型名或 alias。 |
| `finish_reason` | string | `stop`、`length`、`content_filter`、`tool_calls` 或 `error`。 |
| `status` | string | `running`、`completed`、`failed` 或 `cancelled`。 |
| `prompt_tokens` | int | 输入 token 数。 |
| `completion_tokens` | int | 输出 token 数。 |
| `reasoning_tokens` | int | reasoning token 数，可空。 |
| `total_tokens` | int | token 总量。 |
| `latency_ms` | int | 本次模型调用耗时。 |
| `error_code` | string | 脱敏错误码。 |
| `error_message` | string | 脱敏错误摘要。 |
| `started_at` | datetime | 开始时间。 |
| `finished_at` | datetime | 结束时间。 |

约束建议：

- FK：`response_run_id -> response_runs.id`。
- 唯一约束：`(response_run_id, iteration_no)`，除非同一 iteration 支持重试；支持重试时应增加 `attempt_no` 并改为 `(response_run_id, iteration_no, attempt_no)`。
- 不保存完整 prompt、provider 原始响应或 provider 原始错误。

### 9.3 AgentToolCall

表名建议：`agent_tool_calls`

每次模型返回 `tool_calls` 并由 QA 通过 MCP Client 执行工具时保存一条脱敏工具调用记录。

| 字段 | 类型建议 | 说明 |
| --- | --- | --- |
| `id` | uuid/string | 工具调用记录 ID。 |
| `response_run_id` | uuid/string | 所属 Agent Run。 |
| `model_invocation_id` | uuid/string | 来源模型调用，可空。 |
| `iteration_no` | int | ReAct 迭代序号。 |
| `tool_call_id` | string | 模型输出的 tool call id。 |
| `tool_name` | string | 工具名，例如 `search_knowledge`。 |
| `mcp_server_name` | string | MCP server 名称或逻辑 owner，可空。 |
| `arguments_summary` | jsonb | 脱敏参数摘要。 |
| `result_summary` | jsonb | 脱敏结果摘要。 |
| `status` | string | `running`、`completed`、`failed` 或 `cancelled`。 |
| `latency_ms` | int | 工具调用耗时。 |
| `error_code` | string | 脱敏错误码。 |
| `error_message` | string | 脱敏错误摘要。 |
| `started_at` | datetime | 开始时间。 |
| `finished_at` | datetime | 结束时间。 |

约束建议：

- FK：`response_run_id -> response_runs.id`。
- FK：`model_invocation_id -> agent_model_invocations.id`，可空。
- 唯一约束：`(response_run_id, tool_call_id)`。
- `arguments_summary` 和 `result_summary` 不得包含完整工具参数、完整 MCP 原始结果、内部 URL、object key、原始文档全文、prompt、provider token 或密钥。

公开 API 字段映射：

| 数据库字段 | 公开 API 字段 |
| --- | --- |
| `response_run_id` | `responseRunId` |
| `model_invocation_id` | `modelInvocationId` |
| `tool_call_id` | `toolCallId` |
| `tool_name` | `toolName` |
| `arguments_summary` | `argumentsSummary` |
| `result_summary` | `resultSummary` |
| `latency_ms` | `latencyMs` |

### 9.4 ResponseProcessStep

表名建议：`response_process_steps`

面向前端展示的处理步骤摘要。它不是模型私有思维链。

| 字段 | 类型建议 | 说明 |
| --- | --- | --- |
| `id` | uuid/string | 步骤 ID。 |
| `response_run_id` | uuid/string | 所属 Agent Run。 |
| `step_order` | int | 步骤顺序。 |
| `step_type` | string | `agent_iteration`、`tool_call`、`tool_result`、`generation`、`citation` 或 `verify`。 |
| `label` | string | 展示标签。 |
| `detail` | text | 脱敏展示详情。 |
| `status` | string | `pending`、`running`、`done` 或 `failed`。 |
| `related_tool_call_id` | uuid/string | 关联工具调用记录，可空。 |
| `created_at` | datetime | 创建时间。 |
| `updated_at` | datetime | 更新时间。 |

约束建议：

- FK：`response_run_id -> response_runs.id`。
- FK：`related_tool_call_id -> agent_tool_calls.id`，可空。
- 唯一约束：`(response_run_id, step_order)`。

### 9.5 ResponseStreamEvent

表名建议：`response_stream_events`

短期保存公开 SSE 事件，用于断线恢复和调试。事件类型必须对齐 gateway OpenAPI active contract。

| 字段 | 类型建议 | 说明 |
| --- | --- | --- |
| `id` | bigint / uuid | 事件记录 ID。 |
| `response_run_id` | uuid/string | 所属 Agent Run。 |
| `event_seq` | int | 本次 run 内单调递增序号。 |
| `event_type` | string | 公开 SSE 事件类型。 |
| `payload` | jsonb | 公开 SSE payload，必须脱敏。 |
| `created_at` | datetime | 创建时间。 |
| `expires_at` | datetime | 过期清理时间。 |

允许的 `event_type`：

| event_type |
| --- |
| `message.created` |
| `agent.iteration.started` |
| `reasoning.step` |
| `tool.started` |
| `tool.completed` |
| `tool.failed` |
| `answer.delta` |
| `citation.delta` |
| `answer.completed` |
| `error` |

说明：

- `heartbeat` 是传输层保活事件，默认不持久化。
- 旧事件名 `intent`、`step`、`token`、`citation`、`done` 只能作为迁移兼容输入，入库前应转换成当前事件名。

约束建议：

- FK：`response_run_id -> response_runs.id`。
- 唯一约束：`(response_run_id, event_seq)`。
- `payload` 不得包含完整工具参数、完整 MCP 结果、内部 URL、原始文档全文、prompt 或 provider 原始错误。

## 10. 引用实体

### 10.1 QACitation

表名建议：`citations`

回答引用快照。QA 保存回答生成时实际展示的片段，避免源文档变更或删除后历史回答不可追溯。

| 字段 | 类型建议 | 说明 |
| --- | --- | --- |
| `id` | uuid/string | 引用 ID。 |
| `message_id` | uuid/string | 引用所属助手消息。 |
| `response_run_id` | uuid/string | 引用所属 Agent Run，可空但建议保存。 |
| `citation_no` | int | 回答中的引用序号。 |
| `char_start` | int | 引用标注在回答文本中的开始位置，可空。 |
| `char_end` | int | 引用标注在回答文本中的结束位置，可空。 |
| `external_kb_id` | string | 知识库 ID。 |
| `external_doc_id` | string | 文档 ID；公开为 `documentId`。 |
| `external_chunk_id` | string | chunk ID；公开为 `chunkId`。 |
| `document_name_snapshot` | string | 文档名称快照；公开为 `documentName`。 |
| `section_path` | string | 章节路径或标题。 |
| `quote_text` | text | 引用文本快照；公开为 `text` 或详情 `content` 的来源。 |
| `content_preview` | text | 列表展示摘要。 |
| `context` | text | 可展示上下文，不是原文全文。 |
| `page_number` | int | 页码，可空。 |
| `score` | decimal | 检索相关性分数。 |
| `rerank_score` | decimal | 重排序分数，可空。 |
| `chunk_type` | string | chunk 类型。 |
| `is_source_available` | boolean | 当前用户是否仍可访问源文件。 |
| `source_unavailable_reason` | string | 不可访问原因，例如 `source_deleted_or_forbidden`。 |
| `metadata` | jsonb | 脱敏扩展信息。 |
| `created_at` | datetime | 创建时间。 |

约束建议：

- FK：`message_id -> messages.id`。
- FK：`response_run_id -> response_runs.id`，可空。
- 唯一约束：`(message_id, citation_no)`。
- `page_number` 为空或 `>= 1`。

公开 API 字段映射：

| 数据库字段 | 公开 API 字段 |
| --- | --- |
| `external_doc_id` | `documentId`，旧别名 `docId` |
| `document_name_snapshot` | `documentName`，旧别名 `docName` |
| `external_kb_id` | `knowledgeBaseId` |
| `external_chunk_id` | `chunkId` |
| `quote_text` | `text` / `content` |

## 11. 检索体验测试实体

### 11.1 RetrievalTestRun

表名建议：`retrieval_test_runs`

管理员发起的一次 QA 检索体验测试。正式知识检索仍由 knowledge 服务执行，QA 只保存测试运行和脱敏结果快照。

| 字段 | 类型建议 | 说明 |
| --- | --- | --- |
| `id` | uuid/string | 测试运行 ID。 |
| `qa_config_version_id` | uuid/string | 使用的 QA 配置版本。 |
| `external_user_id` | string | 发起测试的用户 ID。 |
| `query` | text | 测试查询文本。 |
| `knowledge_base_ids_json` | jsonb | 显式指定的知识库 ID 数组。 |
| `overrides` | jsonb | 临时覆盖参数，例如 topK、scoreThreshold、rerankTopN。 |
| `status` | string | `queued`、`running`、`completed`、`failed` 或 `cancelled`。 |
| `result_count` | int | 命中数量。 |
| `latency_ms` | int | 耗时。 |
| `error_code` | string | 脱敏错误码。 |
| `error_message` | string | 脱敏错误摘要。 |
| `request_id` | string | Gateway 请求追踪 ID。 |
| `created_at` | datetime | 创建时间。 |
| `finished_at` | datetime | 完成时间。 |

约束建议：

- FK：`qa_config_version_id -> qa_config_versions.id`。
- `status IN ('queued', 'running', 'completed', 'failed', 'cancelled')`。

### 11.2 RetrievalTestResult

表名建议：`retrieval_test_results`

检索体验测试结果快照。

| 字段 | 类型建议 | 说明 |
| --- | --- | --- |
| `id` | uuid/string | 测试结果 ID。 |
| `test_run_id` | uuid/string | 所属测试运行。 |
| `rank_no` | int | 排名，从 1 开始。 |
| `external_kb_id` | string | 知识库 ID。 |
| `external_doc_id` | string | 文档 ID。 |
| `external_chunk_id` | string | chunk ID。 |
| `document_name_snapshot` | string | 文档名称快照。 |
| `section_path` | string | 章节路径。 |
| `text_snapshot` | text | 命中文本快照。 |
| `content_preview` | text | 展示摘要。 |
| `vector_score` | decimal | 向量相似度分数。 |
| `rerank_score` | decimal | 重排序分数，可空。 |
| `metadata` | jsonb | 页码、chunk index 等脱敏扩展信息。 |
| `created_at` | datetime | 创建时间。 |

约束建议：

- FK：`test_run_id -> retrieval_test_runs.id`。
- 唯一约束：`(test_run_id, rank_no)`。
- `rank_no >= 1`。

## 12. 指标查询模型

QA 指标接口默认从权威事实表聚合，不新增重复事实表：

| 指标接口 | 数据来源 |
| --- | --- |
| `/api/v1/qa-metrics/overview` | `response_runs`、`messages`、`citations`，必要时调用 knowledge 获取知识库/文档数量。 |
| `/api/v1/qa-metrics/trend` | `response_runs.completed_at` 或 `messages.created_at` 按日聚合。 |
| `/api/v1/qa-metrics/top-queries` | 用户消息内容块或 `messages.content_preview` 聚合，需排除已删除会话。 |
| `/api/v1/qa-metrics/intent-distribution` | `response_runs.intent_type` 聚合。 |

如果后续性能需要，可增加只读物化视图或定时聚合表，但不得让聚合表成为问答事实的唯一来源。

## 13. 索引建议

| 索引 | 用途 |
| --- | --- |
| `idx_conversations_user_updated` on `(external_user_id, updated_at DESC)` where `deleted_at IS NULL` | 当前用户会话列表。 |
| `idx_messages_conversation_sequence` on `(conversation_id, sequence_no)` | 会话消息列表。 |
| `idx_messages_created_at` on `(created_at)` | 消息时间过滤和统计。 |
| `idx_response_runs_conversation` on `(conversation_id, created_at DESC)` | 会话下运行记录。 |
| `idx_response_runs_user_message` on `(user_message_id)` | 通过用户消息定位 run。 |
| `idx_response_runs_status_started` on `(status, started_at)` | 查找运行中或超时 run。 |
| `idx_response_runs_completed_at` on `(completed_at)` | 指标趋势聚合。 |
| `idx_response_runs_request_id` on `(request_id)` | 请求排障。 |
| `idx_agent_model_invocations_run` on `(response_run_id, iteration_no)` | 查询模型调用链路。 |
| `idx_agent_tool_calls_run` on `(response_run_id, iteration_no)` | 查询工具调用摘要。 |
| `idx_message_content_blocks_message` on `(message_id, block_order)` | 合并消息正文。 |
| `idx_response_process_steps_run` on `(response_run_id, step_order)` | 展示处理步骤。 |
| `idx_response_stream_events_run_seq` on `(response_run_id, event_seq)` | SSE 事件回放。 |
| `idx_response_stream_events_expires_at` on `(expires_at)` | 清理过期事件。 |
| `idx_citations_message` on `(message_id, citation_no)` | 查询消息引用。 |
| `idx_citations_external_doc` on `(external_doc_id)` | 引用来源排查。 |
| `idx_retrieval_test_runs_created_at` on `(created_at DESC)` | 检索测试历史。 |
| `idx_retrieval_test_results_run` on `(test_run_id, rank_no)` | 查询测试结果。 |
| `idx_llm_connection_tests_tested_at` on `(tested_at DESC)` | 查询连接测试历史。 |
| `idx_admin_audit_logs_created_at` on `(created_at DESC)` | 审计日志查询。 |
| `idx_admin_audit_logs_user` on `(external_user_id, created_at DESC)` | 按用户追踪审计。 |

唯一索引建议：

| 唯一约束 | 说明 |
| --- | --- |
| `uniq_active_qa_config` on `qa_config_versions(is_active)` where `is_active = true` | 保证只有一个当前 QA 配置。 |
| `uniq_active_llm_config` on `llm_config_versions(is_active)` where `is_active = true` | 保证只有一个当前 LLM 配置。 |
| `uniq_message_sequence` on `messages(conversation_id, sequence_no)` | 保证会话消息顺序不冲突。 |
| `uniq_stream_event_seq` on `response_stream_events(response_run_id, event_seq)` | 保证 SSE replay 顺序稳定。 |
| `uniq_citation_no` on `citations(message_id, citation_no)` | 保证引用编号稳定。 |
| `uniq_tool_call` on `agent_tool_calls(response_run_id, tool_call_id)` | 保证工具调用幂等记录。 |

## 14. 写入流程

### 14.1 创建会话

```text
gateway authenticates user
gateway forwards X-User-Id / X-Request-Id
qa inserts conversations(status='active')
qa returns QASession envelope through gateway
```

### 14.2 创建消息并生成回答

```text
qa inserts user message(status='completed')
qa inserts user message content block
qa inserts assistant message(status='queued')
qa inserts response_run(status='queued')
qa loads active QAConfigVersion and LLMConfigVersion
qa updates response_run(status='running' or 'streaming')
qa persists response_stream_events(message.created, agent.iteration.started, ...)
qa persists agent_model_invocations for each AI Gateway call
qa persists agent_tool_calls for each MCP tool execution
qa persists response_process_steps as user-visible summaries
qa streams answer.delta and appends message_content_blocks
qa persists citations when references are confirmed
qa marks assistant message and response_run completed / failed / cancelled
```

### 14.3 取消生成

```text
gateway forwards PATCH /api/v1/response-runs/{responseRunId}
qa verifies current user owns the conversation or has admin permission
qa marks response_run(status='cancelled', termination_reason='cancelled')
qa marks assistant message(status='cancelled' or legacy stopped)
qa attempts to cancel active AI Gateway request and MCP tool call
qa writes final response_stream_events(error or answer.completed with cancelled status as appropriate)
```

### 14.4 创建配置版本

```text
qa validates admin permission
qa inserts qa_config_versions or llm_config_versions
qa inserts related qa_config_knowledge_bases when needed
qa uses transaction to deactivate old active version and activate new version
qa writes admin_audit_logs
future response_runs reference the selected version
```

### 14.5 创建检索体验测试

```text
qa inserts retrieval_test_runs(status='running')
qa calls knowledge retrieval using current config plus sanitized overrides
qa inserts retrieval_test_results snapshots
qa updates retrieval_test_runs(status, result_count, latency_ms, finished_at)
```

## 15. 安全与保留策略

- `response_stream_events` 是短期回放数据，应设置 `expires_at` 并定期清理。
- `agent_model_invocations` 和 `agent_tool_calls` 可长期保留脱敏摘要，用于成本、质量和排障分析。
- `admin_audit_logs` 应长期保留，且不得包含秘密。
- 引用快照可以保留与回答同生命周期；源文档不可访问时仍可展示已保存的引用片段快照，但不能绕过 file/knowledge 权限读取原文件。
- 删除会话采用软删除；统计应按产品口径决定是否包含软删除会话，但用户列表默认不展示。

## 16. 与公开契约的关系

- QA 公开路径、响应 envelope、状态枚举和 SSE 事件类型以 gateway OpenAPI 为准。
- 本文定义的是 QA 服务内部持久化模型，不新增前端可直接调用的 API。
- 前端可见的 `thinking` / `reasoning.step` 只来自 `response_process_steps` 的安全摘要。
- `response-runs/{responseRunId}/tool-calls` 只返回 `agent_tool_calls` 中的脱敏摘要。
- LLM 配置接口只返回 `llm_config_versions` 的 AI Gateway profile 引用和生成参数。
- 引用接口只返回 `citations` 的保存快照和可展示来源状态。
