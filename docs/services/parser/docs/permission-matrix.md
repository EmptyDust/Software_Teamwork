# Parser 权限矩阵

本文档说明 Parser Runtime 的内部服务认证和权限边界。Parser 不通过 Gateway 暴露给前端，也不保存业务权限事实。

## 权限来源

| 项 | 说明 |
| --- | --- |
| 服务认证 | `/internal/v1/parsed-documents` 需要内部 service token。 |
| 调用方服务 | 当前允许的业务调用方是 `knowledge` 和 `qa`，通过 `X-Caller-Service` 标识。 |
| 用户上下文 | `X-User-Id` 可用于审计，但不作为 Parser 授权事实。 |
| 业务权限 | 调用方 owner service 在调用 Parser 前完成资源归属、处理状态和用户权限校验。 |
| 解析事实 | Parser 只返回 normalized parsed content，不保存知识库、文档、chunk 或 ACL。 |

## 内部 API 矩阵

| 能力 | 路径 | 认证 | 允许调用方 | Parser 校验 |
| --- | --- | --- | --- | --- |
| 健康检查 | `GET /healthz` | 不需要 | 本地运行、编排和监控。 | 返回进程状态。 |
| 就绪检查 | `GET /readyz` | 不需要 | 编排和监控。 | 返回后端加载、配置和依赖状态。 |
| 解析文档 | `POST /internal/v1/parsed-documents` | service token | `knowledge`、`qa`。 | request id、caller service、文件大小、content type、解析后内容结构和安全输出。 |

## 边界矩阵

| 场景 | Parser 不做 | 由谁负责 |
| --- | --- | --- |
| 用户是否能处理文档或附件 | 不判断 `standard`、`admin` 或 `super_admin`。 | `knowledge` 负责知识文档；`qa` 负责会话附件。 |
| 文件是否属于某知识库或 QA 会话 | 不读取知识库、document metadata、QA conversation 或 attachment metadata。 | `knowledge` 或 `qa`。 |
| 原始 bytes 获取 | 不读取 MinIO、object key 或 `file_ref`。 | `knowledge` / `qa` 调用 `file` 后转交 bytes。 |
| chunk、embedding、Qdrant 或临时附件 chunk 写入 | 不保存或索引解析结果。 | `knowledge` 负责长期知识分块和索引；`qa` 负责会话附件临时 chunk。 |
| parser runtime config 公开管理 | 不暴露前端管理 API。 | Gateway + `knowledge`。 |

## 拒绝规则

| 条件 | 响应语义 |
| --- | --- |
| 缺少或无效 service token | `401 unauthorized`。 |
| caller service 不允许 | `403 forbidden`。 |
| 输入文件类型、大小或 body 不合法 | `400 validation_error`。 |
| 后端 OCR/Office 解析失败 | `422 processing_error` 或契约定义的解析错误，不得返回完整调试日志。 |
| 运行时依赖不可用 | `503` readiness failure 或 `502 dependency_error` 上游映射。 |

## 当前缺口

- Parser 当前只作为内部运行时边界；`qa` 调用仅限会话附件解析，不能绕过 QA owner 授权或把附件写入 Knowledge 长期索引。
- Parser 不应返回 object key、bucket、内部 URL、签名 URL、provider body、API key、prompt 或完整调试日志。
