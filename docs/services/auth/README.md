# Auth 服务 API 文档

本文档定义 `auth` 服务的职责边界、公开 API 契约和内部服务 API。稳定前端公开契约以 [`docs/services/gateway/api/public.openapi.yaml`](../gateway/api/public.openapi.yaml) 为准；auth 服务级 OpenAPI 见 [`api/internal.openapi.yaml`](api/internal.openapi.yaml)，数据模型见 [`docs/data-models.md`](docs/data-models.md)，当前实现状态和缺口见 [`docs/implementation.md`](docs/implementation.md)。本文用于指导 auth 服务实现、gateway 转发和联调。

RESTful 路径、统一响应和错误 envelope 以 [前后端集成契约](../../architecture/frontend-backend-contract.md) 为准。认证相关动作在本服务中建模为资源操作：

| 业务语义 | RESTful 建模 |
| --- | --- |
| 注册用户 | `POST /users` 创建用户资源。 |
| 登录 | `POST /sessions` 创建会话资源。 |
| 登出 | `DELETE /sessions/current` 删除当前会话单例资源。 |
| 当前用户 | `GET /users/me` 读取当前用户单例资源。 |
| 撤销指定会话 | `DELETE /sessions/{sessionId}` 删除会话资源。 |

稳定 path 不使用 `/login`、`/logout`、`/register`、`/revoke` 等动作词。

## 相关文档

| 文档 | 内容 |
| --- | --- |
| [技术选型基线](../../architecture/technology-decisions.md) | 后端服务、数据库访问、迁移、认证 token、密码哈希、日志、测试和观测的统一选型。 |
| [Gateway OpenAPI](../gateway/api/public.openapi.yaml) | 前端稳定公开契约，auth 公开路径以此为准。 |
| [Auth Internal OpenAPI](api/internal.openapi.yaml) | Auth 内部服务 API 草案。 |
| [Auth Public OpenAPI](api/public.openapi.yaml) | 显式声明无前端直连公开 API。 |
| [Auth 数据模型](docs/data-models.md) | 用户、凭证、角色权限、会话、撤销和审计逻辑模型。 |
| [Auth 权限矩阵](docs/permission-matrix.md) | 角色、权限字符串、内部 API 授权和会话权限刷新口径。 |
| [Auth 实现说明](docs/implementation.md) | 当前代码实现、契约对齐、缺口和最近检查记录。 |

## 与 Gateway 契约一致性

本 auth 文档只说明 `users`、`sessions`、`sessions/current` 和 `users/me` 资源的身份域语义，不新增或改名任何前端可调用路径。精确 method、path、认证要求、schema、错误 envelope 和 active 状态只在 [Gateway OpenAPI](../gateway/api/public.openapi.yaml) 与 [active API owner map](../gateway/docs/active-api-owner-map.md) 维护。

响应 envelope、错误 envelope、`CreateUserRequest`、`CreateSessionRequest`、`UserSummary`、`SessionSummary`、`SessionResponse` 和 `UserResponse` 需要与 gateway OpenAPI 的 schema 对齐。本文提到但 gateway OpenAPI 尚未声明的状态码只作为实现建议，不能被前端当作稳定契约依赖。

## 职责边界

| 范围 | Auth 负责 |
| --- | --- |
| 用户身份 | 维护用户账号、用户 ID、用户名和用户基础状态。 |
| 凭证校验 | 校验密码和后续可能的凭证策略；不得泄露账号枚举信息。 |
| 会话 / 令牌 | 签发、校验、查询和撤销 session 或 token。 |
| 角色权限 | 维护用户角色和权限集合，并为 gateway 提供可缓存的会话身份。 |
| 当前用户 | 为 gateway 提供当前用户资料和权限源数据。 |
| 安全事件 | 记录会话创建失败、会话删除、令牌撤销等安全事件。 |

`auth` 不负责文件、知识库、问答、报告生成、模型 provider 或其他业务资源。Gateway 负责公开 API 路由、统一响应 envelope、request id、Redis 会话缓存和错误响应归一化。

## 接入模型

```text
frontend / admin / backend caller
   |
   v
gateway user/session resources
   |
   v
auth service /internal/v1/**
```

前端只能调用 gateway 的 `/api/v1/**`，不得直接调用 auth 内部地址。Gateway 将用户创建和会话创建请求转发给 auth；auth 返回用户身份和会话身份后，gateway 将会话身份写入 Redis。后续业务请求由 gateway 基于 Redis 会话缓存读取身份，并向下游服务注入用户上下文。Auth 的角色、权限字符串、内部 API 授权和会话权限刷新口径统一维护在 [Auth 权限矩阵](docs/permission-matrix.md)。

## 技术选型落地约束

Auth 实现必须遵循 [技术选型基线](../../architecture/technology-decisions.md)。本服务只补充身份域特有约束：

- 服务代码使用独立 Go module，目录为 `services/auth/`。
- 用户、凭证、角色权限、会话和安全事件均以 PostgreSQL 为权威来源；首期 migration 需覆盖这些表。
- Gateway 使用 Redis 维护会话缓存；auth 不把 Redis 作为用户或会话权威来源。auth 如使用 Redis，只能用于短期限流或临时风控状态。
- Access token 固定为 opaque Bearer token，不使用 JWT，不承载可解析 claims。auth 只保存 token hash，gateway Redis key 也只使用 token hash。
- 密码哈希使用 `argon2id`；首期参数固定为 `m=65536 KiB`、`t=3`、`p=2`、`salt=16 bytes`、`key=32 bytes`，以 PHC 字符串保存并记录参数版本 `argon2id-v1`。
- 测试重点覆盖注册、登录、登出、token hash、会话撤销、密码参数升级和错误归一化。

Token hash 采用版本化不可逆派生值，建议格式为 `hmac-sha256:v1:<hex>`，密钥由 auth 和 gateway 通过部署 secret 注入。原始 access token 只允许在创建用户或创建会话的成功响应中返回一次，不能写入数据库、Redis 可读字段、日志、指标 label、错误响应或链路追踪。

## 公开资源范围

Auth 拥有前端可见的用户与会话资源语义，公开入口仍统一由 gateway 暴露。本文只记录这些资源的行为边界：

- `users`：创建用户并返回新会话。
- `sessions`：使用用户名和密码创建会话。
- `sessions/current`：删除当前登录会话。
- `users/me`：获取当前用户资料。

公开路径均相对于 gateway，不是 auth 服务内部地址；精确 method、path、认证要求和 schema 以 [Gateway OpenAPI](../gateway/api/public.openapi.yaml) 为准。

认证机制使用 `bearerAuth`：

```http
Authorization: Bearer <accessToken>
```

用户创建或会话创建成功后，前端从 `data.session.accessToken` 读取访问令牌，并在后续请求中作为 Bearer token 发送。

## 通用响应

Auth 公开接口通过 gateway 使用统一 envelope；格式、分页、错误响应和前端处理规则见 [前后端集成契约](../../architecture/frontend-backend-contract.md)。本文只记录 auth 资源的字段语义和错误场景。

## 公开字段语义

公开 request/response schema 只在 Gateway OpenAPI 维护。本文只记录 auth 字段的业务含义和安全边界：

| 字段或结构 | Auth 语义 |
| --- | --- |
| `username` | 登录用户名；不得通过错误响应泄露账号是否存在。 |
| `password` | 只在创建用户或创建会话请求中出现；请求、响应、日志和链路追踪中不得记录明文密码。 |
| `UserSummary` | 当前认证用户的公开 ID、用户名、角色和权限摘要；gateway 使用角色和权限构造下游认证上下文。 |
| `SessionSummary` | Auth 签发的会话摘要，包括会话 ID、opaque Bearer token、token 类型和过期时间。 |
| `accessToken` | 只允许在创建用户或创建会话成功响应中返回一次；gateway 只能使用不可逆 hash 写入 Redis key 或缓存字段，不能记录原文。 |
| `SessionResponse` | 创建用户或创建会话成功后返回给 gateway 的用户与会话组合；gateway 必须用它写入 Redis 会话缓存。 |
| `UserResponse` | 当前用户资料；默认由 gateway 从 Redis 会话缓存读取，必要时可回源 auth。 |

## 公开资源行为

公开 method、path、schema、认证和错误响应以 [`docs/services/gateway/api/public.openapi.yaml`](../gateway/api/public.openapi.yaml) 和 [Gateway Active API Owner Map](../gateway/docs/active-api-owner-map.md) 为准。本文只记录 Auth-owned 资源的行为语义。

用户创建或会话创建成功后，gateway 必须把 `data.user` 与 `data.session` 一起写入 Redis，并只将 `data.session.accessToken` 返回给前端作为后续 Bearer 凭据。会话创建失败响应不得区分“用户名不存在”和“密码错误”，避免泄露账号枚举信息。

Gateway 应从 Redis 定位当前会话，调用 auth 内部会话删除接口，然后删除 Redis 中的对应会话缓存。Auth 不使用 JWT denylist；会话撤销以 `auth_sessions` 的 token hash、状态、撤销时间和撤销原因为准。首期 access token 不引入 refresh token，过期后由前端重新创建会话。

默认当前用户读取路径是 gateway 从 Redis 会话缓存读取当前用户并返回 `UserResponse`。Auth 仍是用户、角色和权限源数据；当缓存修复、权限变更或安全事件需要回源时，gateway 可以调用 auth 内部会话或用户资源。

如需把 `409 conflict`、`429 rate_limited` 或其他 auth 特有公开错误作为前端稳定契约，必须先同步更新 Gateway OpenAPI。本文中的错误场景说明不能替代 Gateway OpenAPI 的稳定响应声明。

## 会话缓存协作模型

Auth 服务是用户、角色、权限和会话签发的源服务；Gateway 是运行时会话缓存的使用方。二者协作方式如下：

1. Gateway 接收前端用户创建或会话创建请求。
2. Gateway 调用 auth 服务内部资源接口。
3. Auth 校验凭证或创建用户后，返回 `UserSummary` 和 `SessionSummary`。
4. Gateway 将完整会话身份写入 Redis，缓存键使用 `gateway:session:<accessTokenHash>`。
5. 前端后续请求携带 `Authorization: Bearer <accessToken>`。
6. Gateway 用 token 派生 hash 查询 Redis，会话命中后向下游服务注入用户、角色、权限。
7. 当前会话删除、账号禁用、权限变更或安全事件发生时，auth 更新 PostgreSQL 会话状态，gateway 负责删除 Redis 中对应缓存。

Auth 返回给 gateway 的会话身份必须足以构造 Redis 缓存值：

| 字段 | 来源 | Gateway 用途 |
| --- | --- | --- |
| `session.sessionId` | auth 会话记录 | 关联撤销、审计和问题排查。 |
| `session.accessToken` | auth token 签发逻辑 | opaque token，仅返回给前端；gateway 对其做 hash 后作为 Redis key。 |
| `session.expiresAt` | auth 会话策略 | 设置 Redis TTL 和过期判断。 |
| `user.id` | auth 用户记录 | 写入 `X-User-Id`。 |
| `user.username` | auth 用户记录 | 用于审计和展示。 |
| `user.roles` | auth 角色关系 | 写入 `X-User-Roles`。 |
| `user.permissions` | auth 权限计算 | 写入 `X-User-Permissions`。 |

Redis 不是 auth 的持久化数据库。Auth 仍需在自己的 PostgreSQL 中维护用户、角色、权限、会话元数据和撤销状态，并通过 `pgx` + `sqlc` 访问、通过 `goose` 迁移。Gateway Redis 缓存只用于减少后续请求对 auth 的重复查询。

## 内部 Auth Service REST API 草案

公开契约由 gateway OpenAPI 决定。后续落地 `services/auth/` 时，gateway 可通过内部 HTTP API 与 auth 服务协作。内部 API 同样必须使用资源路径、统一 JSON error shape，并保留 `X-Request-Id`。

机器可读契约见 [`api/internal.openapi.yaml`](api/internal.openapi.yaml)。

| Method | Auth service path | 说明 |
| --- | --- | --- |
| `GET` | `/healthz` | Auth 进程存活检查。 |
| `GET` | `/readyz` | Auth 就绪检查，应覆盖 PostgreSQL 等关键依赖。 |
| `POST` | `/internal/v1/users` | 创建用户资源，返回用户身份和会话身份。 |
| `GET` | `/internal/v1/users/{userId}` | 查询用户资源，用于管理、缓存修复或内部审计。 |
| `POST` | `/internal/v1/sessions` | 创建会话资源，返回用户身份和会话身份。 |
| `GET` | `/internal/v1/sessions/{sessionId}` | 查询会话资源，用于缓存修复或调试，不作为 gateway 每次请求的默认路径。 |
| `DELETE` | `/internal/v1/sessions/{sessionId}` | 删除指定会话资源，用于当前会话删除、账号禁用、权限变更或安全事件。 |
| `GET` | `/internal/v1/users/{userId}/permissions` | 查询用户权限集合，用于权限变更后的缓存刷新或内部校验。 |

内部接口不应暴露给前端，不应出现在 gateway public OpenAPI 中。内部接口可以比公开接口更细，但不得引入与公开契约冲突的字段语义。

### 内部创建用户

```http
POST /internal/v1/users
Content-Type: application/json
X-Request-Id: req_123
```

请求体与 `CreateUserRequest` 对齐。成功响应使用与 `SessionResponse.data` 一致的业务数据：

```json
{
  "data": {
    "user": {
      "id": "usr_123",
      "username": "alice",
      "roles": ["<role-code>"],
      "permissions": ["<domain>:<action>"]
    },
    "session": {
      "sessionId": "sess_123",
      "accessToken": "atk_v1_7Qb4mK9xZ2nH8pL5rT1cV6yS3wE0aD",
      "tokenType": "Bearer",
      "expiresAt": "2026-06-28T12:00:00Z"
    }
  },
  "requestId": "req_123"
}
```

### 内部创建会话

```http
POST /internal/v1/sessions
Content-Type: application/json
X-Request-Id: req_123
```

请求体与 `CreateSessionRequest` 对齐。成功响应与内部创建用户接口一致。Auth 返回 opaque `accessToken` 后，gateway 负责派生不可逆 hash 并写入 Redis；auth 和 gateway 都不得把原始 token 写入日志。

### 内部删除会话

```http
DELETE /internal/v1/sessions/{sessionId}
X-Request-Id: req_123
```

成功时建议返回 `204 No Content`。Gateway 通过 Redis 当前会话缓存获取 `sessionId` 后调用该接口；auth 完成撤销后，gateway 删除 Redis 会话缓存。

## 权限与上下文输出

Auth 服务需要为 gateway 提供足够的信息，用于构造下游服务认证上下文；具体输出字段、角色权限矩阵、权限字符串和会话权限刷新规则统一维护在 [Auth 权限矩阵](docs/permission-matrix.md)。逻辑数据模型字段仍见 [Auth 数据模型](docs/data-models.md)。

## 错误码约定

Auth 相关接口使用项目统一错误码：

| Code | HTTP status | Auth 场景 |
| --- | --- | --- |
| `validation_error` | `400` | 请求体格式错误、必填字段缺失、字段不满足规则。 |
| `unauthorized` | `401` | 未登录、凭证无效、登录失败、认证过期。 |
| `forbidden` | `403` | 已认证但缺少访问某能力的权限；当前四个 auth 公开接口暂未定义 `403`。 |
| `not_found` | `404` | 内部用户或会话资源不存在；公开登录失败不应用该错误泄露账号存在性。 |
| `conflict` | `409` | 用户名已存在等状态冲突；作为公开契约前需先补充 gateway OpenAPI。 |
| `rate_limited` | `429` | 用户创建、会话创建等频率限制；作为公开契约前需先补充 gateway OpenAPI。 |
| `dependency_error` | `502` | auth 依赖数据库、Redis 等基础设施失败并由 gateway 归一化。 |
| `internal_error` | `500` | 未预期服务端错误。 |

## 安全与日志要求

- 不得在日志、错误响应或追踪字段中记录明文密码、token、API key、数据库连接串或 session secret。
- 登录失败可以记录安全事件，但日志只应包含 `service`、`request_id`、`operation`、`status`、必要的用户标识或风险标签。
- 密码存储必须使用 `argon2id-v1` 参数：`m=65536 KiB`、`t=3`、`p=2`、`salt=16 bytes`、`key=32 bytes`。数据库保存 PHC 字符串和参数版本，不得保存明文密码或可逆密码材料。
- 密码参数升级必须版本化；用户成功登录且旧 hash 参数低于当前版本时，auth 可在同一事务内重算并替换密码 hash。
- Access token 必须由密码学安全随机数生成，随机部分不少于 32 bytes；token 前缀只用于排查类型，不承载用户 ID、角色、权限或过期时间。
- Token hash 使用版本化不可逆派生值；gateway 和 auth 必须使用同一 hash 规则，Redis key 和 `auth_sessions.access_token_hash` 不得使用原始 token。
- 认证失败信息应保持稳定且模糊，不暴露账号是否存在。
- Token 或 session 撤销必须可审计，至少能关联 `sessionId`、`userId`、撤销原因、操作来源和 request id。
- 所有跨服务 HTTP client 后续实现必须设置超时，并传递 `context.Context`。

## 实现状态

当前代码实现、临时后端、文档与实现出入和建议任务统一维护在
[`docs/implementation.md`](docs/implementation.md)。本文档只保留 Auth Service
的职责边界、公开资源语义和稳定安全规则；实现缺口不在 README 重复维护。
