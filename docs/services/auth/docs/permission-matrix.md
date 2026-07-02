# Auth 权限矩阵

本文档说明 `auth` 服务拥有的用户、角色、权限、会话和内部权限查询边界。稳定前端入口仍通过 Gateway；服务级机器可读契约见 [`../api/internal.openapi.yaml`](../api/internal.openapi.yaml)。

## 权限来源

| 项 | 说明 |
| --- | --- |
| 用户源数据 | `auth_users`。 |
| 凭证源数据 | `auth_credentials`，密码使用 `argon2id-v1` hash。 |
| 角色源数据 | `auth_roles`，当前 seed 包含 `standard`、`admin`、`super_admin`。 |
| 权限源数据 | `auth_permissions` 和 `role_permissions`。 |
| 用户授权 | `user_roles` 将用户绑定到角色。 |
| 会话身份 | `auth` 签发 opaque bearer token 和 session identity；Gateway 缓存运行时快照。 |

## 角色权限矩阵

| 角色 | 基础权限 | 管理权限 | 系统级权限 |
| --- | --- | --- | --- |
| `standard` | `knowledge:read`、`document:read`、`report:read`、`qa:use` | 无。 | 无。 |
| `admin` | `knowledge:*`、`document:*`、`report:*`、`qa:use` | `admin:model-profile:write`、`admin:parser-config:write`、`qa:settings:read`、`qa:settings:write` | 无 `system:admin`。 |
| `super_admin` | 与 `admin` 相同。 | 与 `admin` 相同。 | `system:admin`。 |

`*` 在上表中表示当前 seed 中该领域的 read/write/update/delete/upload 等已列权限集合，不表示通配符权限实现。

## API 权限矩阵

| 能力 | 路径范围 | 认证 | 允许调用方 | Auth 负责 |
| --- | --- | --- | --- | --- |
| 创建用户 | `POST /internal/v1/users` | `X-Service-Token` | Gateway 或受信内部调用方。 | 创建用户、分配默认角色、返回用户摘要。 |
| 创建 session | `POST /internal/v1/sessions` | `X-Service-Token` | Gateway。 | 校验用户名/密码、账号状态，签发 session identity 和 opaque access token。 |
| 查询用户 | `GET /internal/v1/users/{userId}` | `X-Service-Token` | Gateway 或受信内部调用方。 | 返回用户基础信息、角色和权限快照。 |
| 查询用户权限 | `GET /internal/v1/users/{userId}/permissions` | `X-Service-Token` | Gateway、权限缓存刷新任务、受信内部调用方。 | 返回 roles、permissions 和更新时间。 |
| 查询 session | `GET /internal/v1/sessions/{sessionId}` | `X-Service-Token` | Gateway。 | 返回 session identity 或失效状态。 |
| 删除 session | `DELETE /internal/v1/sessions/{sessionId}` | `X-Service-Token` | Gateway、安全任务、管理任务。 | 撤销 session 并记录安全事件。 |

## 边界规则

| 场景 | 规则 |
| --- | --- |
| 前端直连 auth | 不允许；前端只能调用 Gateway。 |
| 前端自填角色/权限 header | 不可信；只有 Gateway 认证后注入的上下文可供下游消费。 |
| 用户禁用、权限变更、密码重置 | 应撤销或刷新受影响 session，避免 Gateway 继续使用旧权限快照。 |
| 下游业务权限判断 | Auth 只提供角色和权限字符串，不判断知识库、报告、QA 会话等业务资源归属。 |
| 账号枚举风险 | 登录失败不得暴露用户名是否存在、密码 hash、token hash 或内部原因。 |

## 当前缺口

- Auth 已 seed `super_admin` 角色和权限，但本地 demo seed 未创建超级管理员用户。
- 角色/权限管理的前端公开管理 API 尚未形成稳定公开契约。
- 细粒度组织、电厂、专业等权限模型不属于首期范围。
