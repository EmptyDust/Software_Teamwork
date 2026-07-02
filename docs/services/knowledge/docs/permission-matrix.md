# Knowledge 权限矩阵

本文档说明 `knowledge` 服务在知识库、文档、检索和 parser runtime config 上的权限边界。稳定前端路径以 Gateway OpenAPI 为准；知识域契约见 [`api-contract.md`](api-contract.md)。

## 权限来源

| 项 | 说明 |
| --- | --- |
| 认证入口 | 前端经 Gateway 调用，业务路径需要 bearer auth。 |
| 用户上下文 | Gateway 注入 `X-User-Id`、`X-User-Roles`、`X-User-Permissions`。 |
| 角色 | `standard`、`admin`、`super_admin`。 |
| 权限字符串 | `knowledge:read`、`knowledge:write`、`admin:parser-config:write`。 |
| 资源事实 | Knowledge PostgreSQL 保存知识库、文档、处理状态、chunks 和 parser configs。 |
| 文件事实 | 原始 bytes 由 File Service 保存；Knowledge 保存内部 `file_ref`。 |

## 业务能力矩阵

| 能力 | `standard` | `admin` | `super_admin` | 额外约束 |
| --- | --- | --- | --- | --- |
| 查看有权限知识库 | 允许，需 `knowledge:read`。 | 允许。 | 允许。 | 按知识库可见性、创建人或后续 ACL 过滤。 |
| 创建知识库 | 默认不允许，除非授予 `knowledge:write`。 | 允许。 | 允许。 | 创建人写入 `created_by`。 |
| 更新知识库 | 默认不允许，除非授予 `knowledge:write` 且有资源权限。 | 允许。 | 允许。 | 软删除资源不可更新。 |
| 删除知识库 | 默认不允许，除非授予 `knowledge:write` 且有资源权限。 | 允许。 | 允许。 | 需要幂等软删除和后续清理。 |
| 上传/更新/删除文档 | 默认不允许，除非授予 `knowledge:write` 且可访问知识库。 | 允许。 | 允许。 | 需校验知识库状态和 File/Parser 边界。 |
| 读取文档详情、chunks、content | 允许，需 `knowledge:read` 且可访问文档。 | 允许。 | 允许。 | 原文内容必须先做文档访问权限校验。 |
| 创建知识查询 | 允许，需 `knowledge:read`。 | 允许。 | 允许。 | 必须过滤无权限知识库、未 ready 文档和已删除文档。 |
| 管理 parser configs | 不允许。 | 允许，需 `admin:parser-config:write` 或 `admin` 角色。 | 允许。 | 公开入口为 `/api/v1/admin/parser-configs/**`。 |

## 服务间调用矩阵

| 下游依赖 | Knowledge 调用前必须校验 | 下游只负责 |
| --- | --- | --- |
| File Service | 用户是否可上传、读取或删除对应文档资源。 | 原始 file object 读写和基础元数据。 |
| Parser Runtime | 文档存在、状态允许处理、调用方有处理权限。 | 将 bytes 解析为 normalized parsed content。 |
| AI Gateway embeddings/rerankings | 文档或查询权限、profile 配置可用。 | 模型调用和 provider 错误归一化。 |
| Qdrant | PostgreSQL 中 chunk/document 权限和状态。 | 向量相似度查询和最小 payload 存储。 |

## 拒绝规则

| 条件 | 响应 |
| --- | --- |
| 未认证 | `401 unauthorized`。 |
| 缺少 `knowledge:read` / `knowledge:write` 或管理权限 | `403 forbidden`。 |
| 资源不存在、已删除或应隐藏 | `404 not_found`。 |
| 查询范围包含无权限知识库 | 过滤无权限范围；必要时返回 `403 forbidden` 或空结果，按 API 契约执行。 |
| 文档未 ready、解析失败或低于阈值 | 不返回命中；错误 envelope 不暴露内部对象 key、prompt 或 provider body。 |

## 当前缺口

- 首期只做角色级 RBAC 和知识库可见性，不引入组织、电厂、专业多维权限。
- Parser config 管理权限以 `admin` / `super_admin` 和 `admin:parser-config:write` 为准；更细粒度策略待后续确认。
- Knowledge 不保存用户、角色、权限源数据；必须信任 Gateway 注入的认证上下文并在服务边界复核。
