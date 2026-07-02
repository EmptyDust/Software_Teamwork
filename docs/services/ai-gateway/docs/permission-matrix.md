# AI Gateway 权限矩阵

本文档说明 `ai-gateway` 的模型 profile 管理、内部模型调用和 provider 凭据保护边界。前端不得直接调用 AI Gateway；管理端入口由 Gateway `/api/v1/admin/model-profiles/**` 提供。

## 权限来源

| 项 | 说明 |
| --- | --- |
| 管理入口认证 | 前端经 Gateway bearer auth 访问 `/api/v1/admin/model-profiles/**`。 |
| 管理入口权限 | Gateway 应要求 `admin` / `super_admin` 或 `admin:model-profile:write`。 |
| 内部服务认证 | AI Gateway `/internal/v1/**` 需要 `X-Service-Token`。 |
| 调用方服务 | `X-Caller-Service` 标识 `gateway`、`qa`、`knowledge`、`document` 等允许调用方。 |
| 用户上下文 | `X-User-Id`、`X-User-Roles`、`X-User-Permissions` 用于审计、配额和排障，不作为领域权限事实。 |
| 凭据事实 | AI Gateway 保存 provider 凭据写入状态和加密材料，不返回 API key 明文。 |

## 管理能力矩阵

| 能力 | `standard` | `admin` | `super_admin` | AI Gateway 负责 |
| --- | --- | --- | --- | --- |
| 列出 model profiles | 不允许。 | 允许。 | 允许。 | 返回脱敏配置和 `apiKeyConfigured` 等状态。 |
| 创建 model profile | 不允许。 | 允许，需 `admin:model-profile:write` 或 admin 角色。 | 允许。 | 校验 provider、base URL、模型、用途和默认参数。 |
| 查看 model profile | 不允许。 | 允许。 | 允许。 | 不返回 API key、fingerprint、last4 或 provider secret。 |
| 更新 model profile | 不允许。 | 允许。 | 允许。 | 接收 write-only API key，保存加密状态和 revision。 |
| 删除/停用 model profile | 不允许。 | 允许。 | 允许。 | 执行服务定义的删除或停用语义并保留审计事实。 |

## 内部模型调用矩阵

| 能力 | 路径 | 允许调用方 | AI Gateway 校验 | 调用方仍需负责 |
| --- | --- | --- | --- | --- |
| Chat completions | `/internal/v1/chat/completions` | `qa`、`document` 等受信服务。 | service token、caller service、profile、model、body size、timeout。 | prompt、用户权限、工具权限、业务上下文和持久化。 |
| Embeddings | `/internal/v1/embeddings` | `knowledge` 等受信服务。 | service token、caller service、profile、模型和输入形状。 | 文档/知识库权限、chunk 状态和索引持久化。 |
| Rerankings | `/internal/v1/rerankings` | `knowledge` 等受信服务。 | service token、caller service、profile、候选数量和模型。 | 检索范围、文档权限、结果过滤和 hydrate。 |
| Internal model profile CRUD | `/internal/v1/model-profiles/**` | `gateway`。 | service token、caller service、请求合法性、secret 脱敏。 | 管理员认证和权限判定。 |

## 拒绝规则

| 条件 | 响应语义 |
| --- | --- |
| 前端直连 AI Gateway | 不允许；部署和 Gateway 均不得暴露内部路径。 |
| 缺少或无效 `X-Service-Token` | `401 unauthorized`。 |
| caller service 不允许 | `403 forbidden` 或 OpenAI-style `permission_error`。 |
| 普通用户尝试管理 profile | Gateway 返回 `403 forbidden`。 |
| profile 缺失、停用或 credential 未配置 | `404 not_found`、`validation_error`、`dependency_error` 或 readiness `degraded`，按契约执行。 |
| provider 认证、限流、超时或失败 | 归一化为稳定错误，不透传 provider raw body。 |

## 当前缺口

- AI Gateway 不做领域权限判断；它只校验内部服务认证、caller service、profile 和请求形状。
- 真实 provider 可用性必须通过显式 smoke 验证；本地 placeholder credential 不代表 provider 可用。
- API key、secret fingerprint、last4、prompt、provider 原始错误和内部 URL 不得出现在公开响应、普通日志或指标标签中。
