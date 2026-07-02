# File 权限矩阵

本文档说明 `file` 服务的内部文件能力授权边界。`file` 不直接拥有前端公开 API；公开资源由 `knowledge`、`document`、`qa` 等 owner service 通过 Gateway 暴露。

## 权限来源

| 项 | 说明 |
| --- | --- |
| 服务认证 | 内部 `/internal/v1/files/**` API 需要 `X-Service-Token`。 |
| 调用方身份 | `X-Caller-Service` 用于区分 `knowledge`、`document`、`qa` 等 owner service。 |
| 用户上下文 | `X-User-Id`、`X-User-Roles`、`X-User-Permissions` 只用于审计和排障，不作为 File 的业务 ACL。 |
| 业务权限 | 由 owner service 判断，例如知识库文档归 `knowledge`，报告文件归 `document`，QA 附件归 `qa`。 |
| 文件事实 | File 只保存基础 file object 元数据和内部存储引用。 |

## 内部能力矩阵

| 能力 | 调用方 | File 校验 | Owner service 必须先校验 |
| --- | --- | --- | --- |
| 写入原始文件对象 | `knowledge`、`document`、`qa` 等受信服务 | service token、caller service、大小、content type、checksum、request id。 | 用户是否可上传到目标知识库、报告资源或 QA 会话。 |
| 读取文件内容 | 拥有 `file_ref` 的 owner service | service token、caller service、file object 状态。 | 用户是否可读取对应业务资源和内容。 |
| 删除或清理对象 | 拥有 `file_ref` 的 owner service 或清理 worker | service token、caller service、幂等状态。 | 业务资源是否已删除、软删除或进入可清理状态。 |
| 查询基础元数据 | 拥有 `file_ref` 的 owner service | service token、caller service、对象存在性。 | 是否允许当前用户查看业务资源。 |

## 公开资源映射

| 公开资源 | Owner service | File 参与方式 |
| --- | --- | --- |
| 知识库文档上传、文档内容 | `knowledge` | 保存和读取原始文档 bytes；不暴露 `file_ref`、bucket、object key。 |
| 报告模板、报告素材、报告导出文件 | `document` | 保存、读取和删除底层文件对象；不判断模板/报告权限。 |
| QA 会话附件 | `qa` | 保存附件原始 bytes；不拥有会话、解析状态或临时 chunk。 |

## 拒绝规则

| 条件 | 响应语义 |
| --- | --- |
| 缺少或无效 `X-Service-Token` | `401 unauthorized`。 |
| caller service 缺失或不允许 | `403 forbidden`。 |
| 文件不存在、已删除或不属于可读状态 | `404 not_found` 或 owner service 映射后的隐藏响应。 |
| 文件大小、content type、checksum 不合法 | `400 validation_error`。 |
| 对象存储不可用 | `502 dependency_error`，不得返回 bucket、object key、签名 URL 或内部路径。 |

## 当前缺口

- File 不维护业务 ACL；未来如果引入预签名下载，也必须由 owner service 先做业务权限判断。
- `file_ref` 是内部引用，不得作为前端权限依据或公开 ID。
- `FILE_DATABASE_URL` 为空时的 memory metadata 模式只适合本地/测试，不代表持久化权限模型。
