# 决策同步清单：智能知识管理与报告生成系统

## 1. 文档目的

本文记录整体需求分析和三份 API 契约中原先未定稿的问题，并同步 GitHub Discussion #48 的确认结果。它用于把需求文档从“可讨论初稿”推进到“可实现契约”。

确认结果来源：

- Discussion #48 主贴：<https://github.com/Sakayori-Iroha-168/Software_Teamwork/discussions/48>
- QA 侧决策汇总：<https://github.com/Sakayori-Iroha-168/Software_Teamwork/discussions/48#discussioncomment-17459396>
- D7 AI gateway：<https://github.com/Sakayori-Iroha-168/Software_Teamwork/discussions/48#discussioncomment-17459473>
- D6 OCR 分期：<https://github.com/Sakayori-Iroha-168/Software_Teamwork/discussions/48#discussioncomment-17459492>
- D5 支撑材料与 file service：<https://github.com/Sakayori-Iroha-168/Software_Teamwork/discussions/48#discussioncomment-17459535>
- D9 RBAC：<https://github.com/Sakayori-Iroha-168/Software_Teamwork/discussions/48#discussioncomment-17459574>

需要同步保持一致的文档：

- [整体需求分析](./overall-requirements-analysis.md)
- [知识管理 API 契约](../services/knowledge/docs/api-contract.md)
- [QA 服务接口文档](../services/qa/README.md)
- [Document 服务接口文档](../services/document/README.md)

## 2. 已确认的核心决策

| 编号 | 决策项 | 确认结果 | 文档影响 |
| --- | --- | --- | --- |
| D1 | 认证方式 | 首期统一使用 opaque Bearer token。普通 JSON 接口、SSE 流式接口和下载授权接口都使用同一套 `Authorization: Bearer <accessToken>` 鉴权，不另设其他会话通道；access token 不采用 JWT，不允许前端解析 token 内容。 | 三份 API 契约的“认证与权限”部分；OpenAPI `securitySchemes`；前端请求封装 |
| D2 | API 网关前缀 | 外部 API 统一使用 `/api/v1/...`。 | 所有 endpoint、OpenAPI servers、Swagger UI 聚合路径 |
| D3 | 异步任务机制 | 首期采用 `asynq` over Redis + PostgreSQL 持久化状态。Redis/asynq 用于队列、调度和执行；PostgreSQL 保存可追溯业务状态、最终状态和失败摘要。 | 文档处理、向量化、报告生成任务；任务状态查询 API；基础设施职责 |
| D4 | 会话历史持久化 | 智能问答会话、消息、Agent Run、工具调用摘要、引用和处理过程摘要以服务端 PostgreSQL 为权威数据源。前端只缓存 `sessionId` 等恢复信息。 | QA 会话/消息 API；刷新恢复说明；前端缓存边界 |
| D5 | 报告支撑材料归属 | 报告支撑材料是独立业务资源，复用 `file` service 处理上传、下载和 MinIO 相关能力；需要检索时复用 `knowledge` 能力。 | 知识管理支撑材料 API；报告生成材料引用；file service 边界 |
| D6 | OCR 与文档解析后端 | 分期建设。首期使用内部 Parser HTTP 服务确保文档处理 pipeline 跑通；Parser runtime 独立部署并预留 PaddleOCR 后端，通过 `parser.baseUrl`、`apiKey`、`timeoutSeconds`、`maxConcurrency` 配置，失败最多自动重试 3 次。 | 文档解析配置；失败重试；PaddleOCR 本地化演进 |
| D7 | 模型供应商与配置 | 抽象到专门的 AI gateway。业务服务通过 OpenAI-compatible API 调用，首期各组无需各自实现供应商适配层；业务配置只引用 AI Gateway `profileId`、模型名和超时等参数，provider `baseUrl` 与 `apiKey` 由 AI Gateway 管理。AI Gateway 只透传 Function Calling 字段，不执行 MCP 工具。 | 知识、QA、报告配置 API；模型调用边界；后续 `ai-gateway` 服务设计 |
| D8 | 数据分析工具 | 统计指标本期做；智能问答中的 Excel/表格“数据分析”工具本期不开放，不进入工具白名单。 | QA Agent 工具白名单；统计 API；P2 范围说明 |
| D9 | 数据权限粒度 | 首期只做角色级 RBAC。暂不做组织、电厂、专业多维数据权限。 | 权限表述；知识库过滤策略；QA 检索过滤 |
| D10 | 审计日志范围 | 当前暂时忽略审计日志查询与独立服务，先保证各模块调试可用。首期只保留配置变更、任务失败、删除结果等基础排查字段。 | 下载、删除、配置变更不接入独立审计服务 |

## 3. 模块内细节同步

### 3.1 知识管理

| 编号 | 原问题 | 同步结果 |
| --- | --- | --- |
| K1 | 知识库删除是软删除还是硬删除？ | 首期软删除；删除动作标记资源为 `deleted`，Qdrant 向量和底层文件对象清理由后台生命周期任务通过内部 `file_ref` 协调处理。 |
| K2 | embedding 维度变化后如何处理 Qdrant collection？ | 采用版本化 collection；embedding 维度或模型族变化时创建新 collection，后台重建索引，旧 collection 保留到切换完成后清理。 |
| K3 | 文档处理失败后保留几次错误历史？ | PostgreSQL job 保存最近 10 次尝试摘要，包含阶段、错误码、错误信息、开始/结束时间和耗时。 |
| K4 | 文档标签是自由键值对还是预定义字典？ | 首期自由键值对；键和值都按字符串保存，管理端可后续增加字典约束。 |
| K5 | 队列失败重试如何处理？ | `asynq` over Redis 负责队列投递、调度和执行；PostgreSQL job 是权威状态。任务最多自动重试 3 次，超过后进入 `failed`，由手动 retry API 重新排队。 |
| K6 | 原始文件和生成文件放在哪些 bucket？ | Owner service 不依赖 bucket 分类；只保存不透明 `file_ref`。Bucket、object key、storage backend 和凭据由 File Service 独占。 |

### 3.2 智能问答

| 编号 | 原问题 | 同步结果 |
| --- | --- | --- |
| QA1 | 流式中断是否保存部分回答？ | 保存已生成部分内容，并标记为 `cancelled`；依赖错误标记为 `failed`。 |
| QA2 | 无权限知识库如何处理？ | 按 [Knowledge 权限矩阵](../services/knowledge/docs/permission-matrix.md) 和 [QA 权限矩阵](../services/qa/docs/permission-matrix.md) 过滤不可访问知识库；调试信息可返回 filtered 数量。 |
| QA3 | 引用是否保存快照？ | 保存引用片段快照，避免源文档变更或删除后历史回答不可追溯。 |
| QA4 | 思考过程展示是否展示原始推理链？ | 不展示原始 chain-of-thought，只展示处理过程摘要。 |
| QA5 | 管理员能否查看或删除普通用户会话？ | 以 [QA 权限矩阵](../services/qa/docs/permission-matrix.md) 为准；本清单不重复维护跨用户会话规则。 |
| QA6 | `data_analysis` 相关请求怎么返回？ | 首期不注册数据分析工具；如模型或用户请求数据分析，返回 `unsupported_intent` 或普通说明，不执行数据分析任务。 |
| QA7 | Agent 是否展示原始工具参数和结果？ | 不展示。只保存和返回脱敏后的 `argumentsSummary`、`resultSummary` 和用户可见处理摘要。 |

### 3.3 报告生成

| 编号 | 原问题 | 同步结果 |
| --- | --- | --- |
| R1 | 模板文件格式是否限定 DOCX？ | 首期限定 DOCX；模板结构、默认章节、材料映射以数据库配置为权威，不从 DOCX 自动解析。 |
| R2 | 固定大纲来自哪里？ | 首期来自数据库模板结构配置；若缺配置则使用两类报告的内置种子模板初始化。 |
| R3 | 重新生成单章是否覆盖用户编辑？ | `preserveUserEdits` 默认 `true`；只有用户显式传 `false` 时才覆盖用户编辑内容。 |
| R4 | 图/表编号模式是否首期实现？ | 首期只实现全局编号 `global`；`by_chapter` 字段保留但不作为首期验收。 |
| R5 | DOCX 统一样式是否首期必须？ | 首期必须有默认 `styleProfile`，用于字体、标题层级、表格样式和页眉页脚；可视化样式编辑器不进入首期。 |
| R6 | AI 大纲生成是否进入首期？ | 首期大纲生成使用 `mode=template`；`mode=ai` 保留接口枚举但返回暂不支持。 |
| R7 | 管理员能否查看或删除全局报告？ | 以 [Document 权限矩阵](../services/document/docs/permission-matrix.md) 为准；本清单不重复维护全局报告访问规则。 |

## 4. 已定默认方案与后续演进

以下事项不再阻塞首期实现；首期按上表默认方案执行，后续只做能力增强：

- AI gateway 首期只要求 OpenAI-compatible provider `baseUrl`、`apiKey`、模型名、超时配置；业务服务侧只保存 `profileId`、模型名和业务默认参数。健康检查可通过后续运维接口增强。
- OCR/文档解析首期接内部 Parser HTTP 服务；PaddleOCR 本地化解析、额度监控和复杂版面识别作为后续演进。
- `asynq` over Redis 首期配合 PostgreSQL job、3 次自动重试和手动 retry；死信队列和可视化运维台作为后续演进。
- Qdrant 首期使用版本化 collection；跨版本迁移和旧索引清理由后台任务处理。
- 审计日志首期不做独立服务；需要合规查询时再补独立审计服务和管理端页面。
