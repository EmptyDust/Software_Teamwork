# Auth 数据模型文档

## 1. 文档说明

本文定义 `auth` 服务的逻辑数据模型，用于支撑用户身份、凭证、角色权限、会话令牌、撤销状态、安全审计和 gateway 会话缓存协作。

本文只描述逻辑数据模型，不提供具体 SQL 建表语句。后续实现可根据 Go 服务和数据库规范转换为 PostgreSQL migration。服务级 API 契约见 [`../api/internal.openapi.yaml`](../api/internal.openapi.yaml)，稳定前端公开契约仍以 [`../../gateway/api/public.openapi.yaml`](../../gateway/api/public.openapi.yaml) 为准。

## 2. 存储边界

### 2.1 Auth 持久化数据库

Auth 数据库保存 auth 自己拥有的结构化数据：

- 用户账号和用户状态。
- 密码哈希和凭证策略元数据。
- 角色、权限和用户角色关系。
- 会话元数据、令牌哈希、过期时间和撤销状态。
- 登录失败、会话撤销、权限变更等安全事件。
- 可选的账号锁定、限流和审计辅助状态。

实现落地时，Auth 持久化数据库使用 PostgreSQL；数据库访问使用 `pgx` + `sqlc`，迁移使用 `goose`。`auth_sessions` 中的 token hash、撤销状态和过期时间是服务端会话权威来源，Gateway Redis 只是运行时缓存。

Auth 数据库不得保存文件、知识库、问答、报告、模型 provider 配置、MinIO object key、prompt 或其他领域服务业务状态。

### 2.2 Gateway Redis 会话缓存

Gateway Redis 是运行时缓存，不是 auth 的持久化源数据。Auth 创建用户或会话后返回用户身份和会话身份；gateway 将其写入 Redis，缓存键使用：

```text
gateway:session:<accessTokenHash>
```

`accessTokenHash` 必须由 opaque access token 派生，不得来自 JWT claim 或任何可逆编码。建议使用与 auth 一致的版本化派生格式：

```text
hmac-sha256:v1:<hex>
```

Redis 缓存值至少包含：

| 字段 | 来源 | 说明 |
| --- | --- | --- |
| `sessionId` | `auth_sessions.id` | Auth 会话 ID。 |
| `userId` | `auth_users.id` | 已认证用户 ID。 |
| `username` | `auth_users.username` | 用户名，仅用于展示、审计和调试。 |
| `roles` | 角色关系计算结果 | 写入 `X-User-Roles`。 |
| `permissions` | 权限计算结果 | 写入 `X-User-Permissions`。 |
| `accessTokenHash` | access token 派生值 | 不可逆哈希，不保存原始 token。 |
| `expiresAt` | `auth_sessions.expires_at` | Redis TTL 必须不晚于该时间。 |
| `issuedAt` | `auth_sessions.issued_at` | 会话签发时间。 |

Auth 数据库仍是用户、角色、权限和会话撤销状态的权威来源。Redis 未命中、过期或内容无效时，gateway 首期返回 `401 unauthorized`，不把 Redis 作为账号恢复来源。后续如实现缓存修复，只能把 token hash 作为请求体字段传给 auth，不得把原始 token 放入 URL、日志或审计字段。

## 3. 设计原则

- 主键建议使用字符串 ID，公开 ID 可带业务前缀，例如 `usr_`、`sess_`、`role_`、`perm_`。
- 数据库字段使用 snake_case；公开 API 字段使用 camelCase。
- 时间字段使用 `TIMESTAMPTZ`，公开 API 映射为 RFC 3339 / OpenAPI `date-time`。
- 密码只保存安全哈希和哈希参数，不保存明文、可逆密文或临时明文。
- Access token 只保存不可逆哈希；日志、审计事件、错误响应、Redis 可读字段均不得记录原始 token。
- Access token 是 opaque Bearer token，不是 JWT；任何服务都不得从 token 中解析用户 ID、角色、权限或过期时间。
- 角色权限源数据归 auth；gateway 和下游服务只消费 auth 计算出的角色、权限和用户上下文。
- 跨服务只传递公开用户 ID、角色名、权限字符串和 request id，不传递内部数据库自增序号或凭证字段。

## 4. 实体关系概览

```text
AuthUser 1 ── 1 AuthCredential
AuthUser 1 ── N AuthSession
AuthUser 1 ── N AuthSecurityEvent
AuthUser 1 ── N UserRole

AuthRole 1 ── N UserRole
AuthRole 1 ── N RolePermission

AuthPermission 1 ── N RolePermission

AuthSession 1 ── 0..1 SessionRevocation
AuthSession 1 ── N AuthSecurityEvent
```

## 5. 通用字段约定

| 字段 | 说明 |
| --- | --- |
| `id` | 主键。建议使用字符串 ID 或 UUID；公开响应始终按 string 暴露。 |
| `created_at` | 创建时间。 |
| `updated_at` | 更新时间。 |
| `deleted_at` | 软删除时间，可选。Auth 关键安全记录默认不物理删除。 |
| `created_by` | 创建来源，可来自 gateway 用户上下文、系统任务或初始化脚本。 |
| `updated_by` | 最近修改来源。 |
| `request_id` | 贯穿 gateway、auth 和下游服务的一次请求 ID。 |

公开 API 字段映射以 `docs/services/gateway/api/public.openapi.yaml` 和 `docs/services/auth/api/internal.openapi.yaml` 为准。当内部字段和公开字段不是简单大小写转换时，本文在实体说明中单独列出。

## 6. 核心实体

### 6.1 AuthUser

用户主记录。该实体是用户 ID、用户名和账号状态的权威来源。

| 字段 | 类型建议 | 说明 |
| --- | --- | --- |
| `id` | string / uuid | 用户公开 ID，对外映射为 `UserSummary.id`。 |
| `username` | string | 登录用户名，唯一。 |
| `display_name` | string | 展示名称，可选；当前 gateway UserSummary 未暴露。 |
| `email` | string | 邮箱，可选；首期公开契约未使用。 |
| `phone` | string | 手机号，可选；首期公开契约未使用。 |
| `status` | string | 用户状态，见状态枚举。 |
| `locked_until` | datetime | 临时锁定截止时间，可选。 |
| `last_login_at` | datetime | 最近成功创建会话时间。 |
| `created_at` | datetime | 创建时间。 |
| `updated_at` | datetime | 更新时间。 |
| `deleted_at` | datetime | 软删除时间，可选。 |

状态枚举：

| status | 说明 |
| --- | --- |
| `active` | 正常可登录。 |
| `disabled` | 已禁用，不允许创建新会话；已有会话应撤销或失效。 |
| `locked` | 因失败次数、风控或管理员操作被锁定。 |

公开 API 字段映射：

| 数据库字段 | 公开 API 字段 |
| --- | --- |
| `id` | `id` |
| `username` | `username` |
| `status` | `UserRecord.status`，仅内部 auth OpenAPI 暴露；gateway `UserSummary` 当前不暴露。 |

### 6.2 AuthCredential

用户凭证记录。首期以密码登录为主，后续可扩展 MFA、外部身份源或密钥凭证。

| 字段 | 类型建议 | 说明 |
| --- | --- | --- |
| `id` | string / uuid | 凭证 ID。 |
| `user_id` | string / uuid | 所属用户。 |
| `credential_type` | string | 凭证类型，首期为 `password`。 |
| `password_hash` | string | 密码安全哈希，建议保存 PHC 字符串。 |
| `password_hash_alg` | string | 固定为 `argon2id`，后续算法升级通过参数版本和迁移策略处理。 |
| `password_hash_params_version` | string | 参数版本，首期固定为 `argon2id-v1`。 |
| `password_hash_params_json` | json | 哈希参数快照，例如 memory、iterations、parallelism、salt 长度和 key 长度。 |
| `password_changed_at` | datetime | 最近修改密码时间。 |
| `password_expires_at` | datetime | 密码过期时间，可选。 |
| `failed_attempt_count` | int | 连续失败次数，用于风控或锁定。 |
| `last_failed_at` | datetime | 最近失败时间。 |
| `created_at` | datetime | 创建时间。 |
| `updated_at` | datetime | 更新时间。 |

安全约束：

- `password_hash` 不得通过任何 API、日志或错误响应返回。
- `CreateUserRequest.password` 和 `CreateSessionRequest.password` 只存在于请求处理过程，写入数据库前必须转换为安全哈希。
- 登录失败响应不得区分“用户不存在”和“密码错误”。

`argon2id-v1` 固定参数：

| 参数 | 值 |
| --- | --- |
| memory | `65536 KiB` |
| iterations | `3` |
| parallelism | `2` |
| salt length | `16 bytes` |
| key length | `32 bytes` |
| encoding | PHC string，例如 `$argon2id$v=19$m=65536,t=3,p=2$...` |

参数升级必须通过新的 `password_hash_params_version` 表达。用户成功登录且旧 hash 低于当前版本时，auth 可以在验证成功后重新计算并更新 hash。

### 6.3 AuthRole

角色记录。角色是权限集合的业务分组。

| 字段 | 类型建议 | 说明 |
| --- | --- | --- |
| `id` | string / uuid | 角色 ID。 |
| `code` | string | 角色编码，唯一；对外可作为 `UserSummary.roles[]`。 |
| `name` | string | 角色名称。 |
| `description` | string | 角色描述。 |
| `enabled` | boolean | 是否启用。 |
| `system_role` | boolean | 是否系统内置角色。 |
| `created_at` | datetime | 创建时间。 |
| `updated_at` | datetime | 更新时间。 |

公开 API 字段映射：

| 数据库字段 | 公开 API 字段 |
| --- | --- |
| `code` | `roles[]` |

### 6.4 AuthPermission

权限记录。权限字符串用于 gateway 和下游服务做服务边界校验。

| 字段 | 类型建议 | 说明 |
| --- | --- | --- |
| `id` | string / uuid | 权限 ID。 |
| `code` | string | 权限字符串，唯一；对外作为 `UserSummary.permissions[]`。 |
| `domain` | string | 领域，例如 `knowledge`、`document`、`report`、`admin`。 |
| `action` | string | 动作能力，例如 `read`、`write`、`upload`。 |
| `description` | string | 权限描述。 |
| `enabled` | boolean | 是否启用。 |
| `created_at` | datetime | 创建时间。 |
| `updated_at` | datetime | 更新时间。 |

权限字符串格式：

```text
<domain>:<action>
```

当前 seed 的角色、权限字符串集合和角色授权关系统一维护在 [Auth 权限矩阵](permission-matrix.md)，本文只定义权限字段的数据模型。

公开 API 字段映射：

| 数据库字段 | 公开 API 字段 |
| --- | --- |
| `code` | `permissions[]` |

### 6.5 UserRole

用户与角色关系。

| 字段 | 类型建议 | 说明 |
| --- | --- | --- |
| `id` | string / uuid | 关系 ID。 |
| `user_id` | string / uuid | 用户 ID。 |
| `role_id` | string / uuid | 角色 ID。 |
| `assigned_by` | string | 分配来源或操作者 ID。 |
| `assigned_at` | datetime | 分配时间。 |
| `expires_at` | datetime | 角色过期时间，可选。 |
| `created_at` | datetime | 创建时间。 |

约束建议：

- `(user_id, role_id)` 在未过期且未删除的有效关系中唯一。
- 用户角色变化后，auth 应触发相关会话失效或通知 gateway 刷新 Redis 缓存。

### 6.6 RolePermission

角色与权限关系。

| 字段 | 类型建议 | 说明 |
| --- | --- | --- |
| `id` | string / uuid | 关系 ID。 |
| `role_id` | string / uuid | 角色 ID。 |
| `permission_id` | string / uuid | 权限 ID。 |
| `created_at` | datetime | 创建时间。 |

约束建议：

- `(role_id, permission_id)` 唯一。
- 权限变化后，需要让受影响用户的旧会话失效或刷新 gateway Redis 缓存。

### 6.7 AuthSession

会话记录。该实体是 session ID、token 哈希、过期时间和撤销状态的权威来源。

| 字段 | 类型建议 | 说明 |
| --- | --- | --- |
| `id` | string / uuid | 会话 ID，对外映射为 `sessionId`。 |
| `user_id` | string / uuid | 所属用户。 |
| `access_token_hash` | string | opaque access token 的不可逆派生值，例如 `hmac-sha256:v1:<hex>`。 |
| `access_token_hash_alg` | string | token hash 算法，首期为 `hmac-sha256`。 |
| `access_token_hash_key_version` | string | token hash secret 版本，用于密钥轮换。 |
| `token_type` | string | 当前固定为 `Bearer`。 |
| `status` | string | 会话状态，见状态枚举。 |
| `issued_at` | datetime | 签发时间。 |
| `expires_at` | datetime | 过期时间。 |
| `last_seen_at` | datetime | 最近使用时间，可选。 |
| `revoked_at` | datetime | 撤销时间，可选。 |
| `revoke_reason` | string | 撤销原因，可选。 |
| `client_ip` | string | 创建会话时的客户端 IP，可选。 |
| `user_agent` | string | 创建会话时的 User-Agent，可选。 |
| `created_request_id` | string | 创建会话的 request id。 |
| `revoked_request_id` | string | 撤销会话的 request id，可选。 |
| `created_at` | datetime | 创建时间。 |
| `updated_at` | datetime | 更新时间。 |

状态枚举：

| status | 说明 |
| --- | --- |
| `active` | 会话有效。 |
| `expired` | 已过期。 |
| `revoked` | 已撤销。 |

公开 API 字段映射：

| 数据库字段 | 公开 API 字段 |
| --- | --- |
| `id` | `SessionSummary.sessionId` / `SessionIdentity.sessionId` |
| 原始 token | `SessionSummary.accessToken`，仅创建会话响应返回一次；数据库不保存原文。 |
| `token_type` | `tokenType` |
| `expires_at` | `expiresAt` |
| `issued_at` | `SessionIdentity.issuedAt` |
| `revoked_at` | `SessionIdentity.revokedAt` |
| `revoke_reason` | `SessionIdentity.revokeReason` |
| `access_token_hash` | `SessionIdentity.accessTokenHash`，仅内部诊断可选返回；不得返回原始 token。 |

会话创建时，auth 生成随机 opaque token，保存 token hash，并同时返回 `UserSummary` 和 `SessionSummary`，供 gateway 写入 Redis。会话删除时，gateway 通过 Redis 当前会话值解析 `sessionId`，调用 `DELETE /internal/v1/sessions/{sessionId}`，auth 更新撤销状态后 gateway 删除 Redis 缓存。

### 6.8 SessionRevocation

会话撤销记录。可以作为独立表，也可以由 `auth_sessions` 的撤销字段承载；如果需要审计和批量撤销追踪，建议单独建模。

| 字段 | 类型建议 | 说明 |
| --- | --- | --- |
| `id` | string / uuid | 撤销记录 ID。 |
| `session_id` | string / uuid | 会话 ID。 |
| `user_id` | string / uuid | 用户 ID。 |
| `reason` | string | 撤销原因，例如 `user_logout`、`user_disabled`、`permission_changed`、`security_event`。 |
| `revoked_by` | string | 撤销来源，例如用户 ID、管理员 ID 或系统任务。 |
| `request_id` | string | 撤销请求 ID。 |
| `revoked_at` | datetime | 撤销时间。 |

约束建议：

- `session_id` 唯一，避免同一会话出现多个有效撤销记录。
- 账号禁用或权限变更需要批量撤销时，应记录每个被撤销会话。

### 6.9 AuthSecurityEvent

安全事件记录。用于登录失败、登录成功、会话撤销、账号锁定、权限变更等审计。

| 字段 | 类型建议 | 说明 |
| --- | --- | --- |
| `id` | string / uuid | 事件 ID。 |
| `event_type` | string | 事件类型。 |
| `user_id` | string / uuid | 关联用户，可空。 |
| `session_id` | string / uuid | 关联会话，可空。 |
| `username_snapshot` | string | 事件发生时的用户名快照，可用于登录失败审计。 |
| `request_id` | string | 请求追踪 ID。 |
| `client_ip` | string | 来源 IP。 |
| `user_agent` | string | User-Agent。 |
| `caller_service` | string | 内部调用方，例如 `gateway`。 |
| `status` | string | 事件结果，例如 `success`、`failed`。 |
| `reason_code` | string | 失败或风险原因码。 |
| `metadata_json` | json | 脱敏扩展信息。 |
| `created_at` | datetime | 事件时间。 |

事件类型建议：

| event_type | 说明 |
| --- | --- |
| `user.created` | 用户创建。 |
| `session.created` | 会话创建成功。 |
| `session.create_failed` | 会话创建失败。 |
| `session.revoked` | 会话撤销。 |
| `user.disabled` | 用户禁用。 |
| `user.locked` | 用户锁定。 |
| `role.assigned` | 角色分配。 |
| `role.removed` | 角色移除。 |
| `permission.changed` | 权限配置变化。 |

安全事件不得记录明文密码、原始 token、数据库连接串、内部服务密钥或完整请求体。

### 6.10 AuthRateLimitState

限流和失败计数状态。该实体也可以由 Redis 或专门风控组件承载；如果由 auth 使用 Redis 实现，客户端使用 `go-redis`，且 Redis 仍只能保存短期状态。如果落库，应仅保存必要的状态和脱敏标识。

| 字段 | 类型建议 | 说明 |
| --- | --- | --- |
| `id` | string / uuid | 状态 ID。 |
| `scope` | string | 限流维度，例如 `username`、`ip`、`user_id`。 |
| `scope_hash` | string | 维度值的哈希，避免直接保存敏感原文。 |
| `operation` | string | 操作，例如 `create_session`、`create_user`。 |
| `window_started_at` | datetime | 当前窗口开始时间。 |
| `window_expires_at` | datetime | 当前窗口结束时间。 |
| `attempt_count` | int | 窗口内尝试次数。 |
| `blocked_until` | datetime | 阻断截止时间，可选。 |
| `updated_at` | datetime | 更新时间。 |

如果首期不落库，可由 gateway 或 auth 的 Redis 限流实现代替，但错误响应仍应使用统一 `rate_limited`。

## 7. API Schema 映射

### 7.1 UserSummary

`UserSummary` 同时被 gateway OpenAPI 和 auth OpenAPI 使用：

| API 字段 | 来源 |
| --- | --- |
| `id` | `auth_users.id` |
| `username` | `auth_users.username` |
| `roles` | `auth_roles.code` 聚合 |
| `permissions` | `auth_permissions.code` 聚合 |

### 7.2 UserRecord

内部 `GET /internal/v1/users/{userId}` 可返回 `UserRecord`：

| API 字段 | 来源 |
| --- | --- |
| `id` | `auth_users.id` |
| `username` | `auth_users.username` |
| `roles` | 角色聚合 |
| `permissions` | 权限聚合 |
| `status` | `auth_users.status` |
| `createdAt` | `auth_users.created_at` |
| `updatedAt` | `auth_users.updated_at` |

### 7.3 SessionSummary

`SessionSummary` 只在用户创建或会话创建成功时返回给 gateway 和前端：

| API 字段 | 来源 |
| --- | --- |
| `sessionId` | `auth_sessions.id` |
| `accessToken` | 新签发 opaque token 原文，仅响应一次；数据库保存 `access_token_hash`。 |
| `tokenType` | `auth_sessions.token_type` |
| `expiresAt` | `auth_sessions.expires_at` |

### 7.4 SessionIdentity

内部 `GET /internal/v1/sessions/{sessionId}` 可返回 `SessionIdentity`：

| API 字段 | 来源 |
| --- | --- |
| `sessionId` | `auth_sessions.id` |
| `user` | `AuthUser` + 角色权限聚合 |
| `tokenType` | `auth_sessions.token_type` |
| `expiresAt` | `auth_sessions.expires_at` |
| `issuedAt` | `auth_sessions.issued_at` |
| `revokedAt` | `auth_sessions.revoked_at` 或 `session_revocations.revoked_at` |
| `revokeReason` | `auth_sessions.revoke_reason` 或 `session_revocations.reason` |
| `accessTokenHash` | `auth_sessions.access_token_hash`，仅内部诊断可选。 |

### 7.5 UserPermissions

内部 `GET /internal/v1/users/{userId}/permissions` 返回用户权限快照：

| API 字段 | 来源 |
| --- | --- |
| `userId` | `auth_users.id` |
| `roles` | `auth_roles.code` 聚合 |
| `permissions` | `auth_permissions.code` 聚合 |
| `updatedAt` | 角色关系或权限关系的最近更新时间；实现可取聚合最大值。 |

## 8. 索引与约束建议

| 表 | 约束 / 索引 | 说明 |
| --- | --- | --- |
| `auth_users` | `UNIQUE(username)` | 用户名唯一。 |
| `auth_users` | `INDEX(status)` | 支持按状态筛选和禁用流程。 |
| `auth_credentials` | `UNIQUE(user_id, credential_type)` | 每用户每类型一个主凭证。 |
| `auth_roles` | `UNIQUE(code)` | 角色编码唯一。 |
| `auth_permissions` | `UNIQUE(code)` | 权限字符串唯一。 |
| `user_roles` | `UNIQUE(user_id, role_id)` | 避免重复分配。 |
| `role_permissions` | `UNIQUE(role_id, permission_id)` | 避免重复授权。 |
| `auth_sessions` | `UNIQUE(access_token_hash)` | 用 token 哈希定位会话。 |
| `auth_sessions` | `INDEX(user_id, status)` | 支持按用户撤销活跃会话。 |
| `auth_sessions` | `INDEX(expires_at)` | 支持过期清理。 |
| `session_revocations` | `UNIQUE(session_id)` | 避免重复撤销记录。 |
| `auth_security_events` | `INDEX(user_id, created_at)` | 支持用户安全审计。 |
| `auth_security_events` | `INDEX(request_id)` | 支持跨服务链路排查。 |

## 9. 生命周期规则

### 9.1 用户创建

1. Gateway 调用 `POST /internal/v1/users`。
2. Auth 创建 `AuthUser` 和 `AuthCredential`。
3. Auth 为新用户计算默认角色和权限。
4. Auth 生成 opaque token，创建保存 token hash 的 `AuthSession`，返回 `SessionResponse`。
5. Gateway 将 `UserSummary` 和 `SessionSummary` 写入 Redis。
6. Auth 记录 `user.created` 和 `session.created` 安全事件。

### 9.2 会话创建

1. Gateway 调用 `POST /internal/v1/sessions`。
2. Auth 根据 `username` 查询用户和凭证。
3. Auth 校验用户状态、锁定状态和密码哈希。
4. 成功时生成 opaque token，创建保存 token hash 的 `AuthSession`，更新 `last_login_at`，返回 `SessionResponse`。
5. 失败时更新失败计数，记录 `session.create_failed`，返回统一 `401 unauthorized` 或 `429 rate_limited`。

### 9.3 会话删除

1. Gateway 从 Redis 当前会话缓存读取 `sessionId`。
2. Gateway 调用 `DELETE /internal/v1/sessions/{sessionId}`。
3. Auth 将 `AuthSession.status` 更新为 `revoked`，写入撤销时间和原因。
4. Auth 记录 `session.revoked`。
5. Gateway 删除 Redis 缓存键。

### 9.4 权限变更

1. Auth 修改 `UserRole` 或 `RolePermission`。
2. Auth 记录 `role.assigned`、`role.removed` 或 `permission.changed`。
3. Auth 应撤销受影响用户的活跃会话，或提供机制让 gateway 刷新 Redis 会话缓存。
4. 下游服务后续只能信任 gateway 注入的新 `X-User-Roles` 和 `X-User-Permissions`。

## 10. 安全保留策略

- 原始 access token 不落库、不进日志、不进错误响应。
- `access_token_hash` 使用版本化 HMAC-SHA-256 派生值，hash secret 由 auth 和 gateway 通过部署 secret 注入并记录 key version。
- 原始 access token 的随机部分不少于 `32 bytes`，token 前缀不得编码用户 ID、角色、权限、过期时间或其他 claims。
- `argon2id` 参数必须按 `argon2id-v1` 保存并可版本化，便于后续升级 memory、iterations、parallelism 或 salt 策略。
- 安全事件应保留 request id、用户 ID、会话 ID、来源 IP 和风险原因，但不得保存敏感原文。
- 账号禁用、权限变更、密码重置等高风险操作应撤销该用户现有活跃会话。
- Auth 删除用户时优先软删除或禁用；安全审计记录不应随用户记录物理删除。

## 11. 与其他服务的边界

| 数据 | Owner | Auth 处理方式 |
| --- | --- | --- |
| 用户、凭证、角色、权限、会话 | `auth` | 权威保存和变更。 |
| Gateway Redis 会话缓存 | `gateway` | Auth 返回会话身份；gateway 写入、读取和删除缓存。 |
| 知识库 ACL 细粒度规则 | `knowledge` / 后续权限设计 | Auth 首期只提供角色和权限字符串。 |
| 文件、文档、报告资源归属 | `file` / `knowledge` / `document` | Auth 不保存业务资源状态。 |
| 问答会话与消息 | `qa` | Auth 只提供 `X-User-Id` 等身份上下文。 |
| 模型 provider 与 API key | `ai-gateway` | Auth 不保存 provider 密钥或模型配置。 |

## 12. 后续待确认

- 用户名格式、大小写敏感性和唯一性规则。
- 密码复杂度、密码过期和密码重置机制。
- 角色和权限的初始种子数据。
- 是否需要管理员创建用户、邀请注册、验证码或 MFA。
- Access token 有效期和批量撤销机制；首期不引入 refresh token，如后续引入必须新增独立凭证模型并继续使用 opaque token。
- 登录失败限流维度和账号锁定阈值。
- 安全事件保留周期和归档策略。
