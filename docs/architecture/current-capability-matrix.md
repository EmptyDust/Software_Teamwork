# 当前能力矩阵

日期：2026-06-30

本文根据截至当前 `develop`、今天的 issue/PR 状态和各服务实现说明，汇总项目当前真实能力。合并到 `develop` 的能力才标为“已实现”；open PR 只作为待合入或下一步，不当作当前能力。

## 状态标记

| 标记 | 含义 |
| --- | --- |
| 已实现 | 代码、契约和基础测试已经在当前 `develop` 可见。 |
| 部分实现 | 核心资源或状态机存在，但关键下游、真实集成或部分 active paths 未闭环。 |
| 占位 | 契约或 route 已存在，但返回 `not_implemented` 或只做安全占位。 |
| 缺失 | 当前没有可执行实现或稳定契约。 |

## 今日输入

| 来源 | 状态 | 对能力判断的影响 |
| --- | --- | --- |
| PR #225 `feat(ai-gateway): add embeddings and rerankings` | merged | AI Gateway chat、embedding、rerank 三类模型调用都已从 501 进入可调用实现。 |
| PR #224 `docs(services): add implementation status docs` | merged | 已补实现状态、缺口、能力矩阵、联调 runbook、测试策略和 provider/generation 细则。 |
| PR #223 `feat(document): add report file docx export` | open | DOCX 导出仍不能写成当前能力。 |
| PR #221 `feat(document): implement C-08 report settings, statistics and operation logs` | open | settings、statistics、operation logs 仍按未合入能力处理。 |
| PR #217 `feat(qa): implement B-03 QA Agent Run MVP with termination handling` | open | 早期 B-03 PR 未合入，不作为当前 `develop` 能力依据；本分支改由 Issue #89 收口。 |
| Issue #89 `B-03 QA ResponseRun 与非流式 Agent Loop MVP` | branch implemented | QA ResponseRun、非流式 Agent Loop MVP、终止原因、模型调用摘要和基础测试已在本分支补齐；合入后计入 `develop` 能力。 |
| PR #222、#220、#219、#212、#210、#208、#204、#202、#200、#199 | merged | 分别补齐前端导航、Document job 状态机、QA 配置对齐、前端 shell/RBAC、QA 会话消息、AI Gateway chat/profile、Document 大纲章节、Knowledge upload job、Gateway active proxy 基础。 |

## 能力矩阵

| 能力 | 当前状态 | 已有实现证据 | 对外/内部契约 | 主要缺口 | 关联 |
| --- | --- | --- | --- | --- | --- |
| Auth 用户、会话和权限上下文 | 已实现 | `services/auth/` Go service、PostgreSQL migration、argon2id、session token hash、服务间 token。 | Gateway auth public routes；Auth service OpenAPI。 | 与完整本地 E2E、种子数据和管理端权限配置仍需联调。 | #109、#122、#125 |
| Gateway active route proxy 和 session cache | 部分实现 | `services/gateway/` active proxy matrix、Redis session cache、Auth routes。 | Gateway OpenAPI 是前端权威契约。 | 部分 Knowledge active routes 仍是阶段性 501；跨服务 smoke 未自动化。 | #153、#199、#125 |
| File 基础文件对象 | 部分实现 | `services/file/` 内部 `/internal/v1/files/**`、memory/local/MinIO object store、file metadata migration、PostgreSQL metadata runtime 和 service-token 校验。 | File service 内部 API；业务服务不得暴露 object key。 | MinIO server/mc 本地初始化、真实对象存储 smoke 和跨服务 smoke 未自动化。 | #154、#235 |
| Knowledge 知识库 CRUD 和上传 handoff | 部分实现 | Knowledge PostgreSQL repository、知识库 CRUD、文档上传、File handoff、asynq ingestion 入队。 | Gateway Knowledge active paths；Knowledge service OpenAPI。 | ingestion worker、解析、embedding、Qdrant、retrieval、rerank 闭环未落地。 | #152、#200 |
| Parser Runtime 契约 | 占位 | `docs/services/parser/README.md`、`docs/services/parser/api/public.openapi.yaml`、`docs/services/parser/api/internal.openapi.yaml`、`services/parser/src/parser_service/**` scaffold。 | Parser 内部 `/internal/v1/parsed-documents` API；不通过 gateway 暴露。 | Python/PaddleOCR runtime、Docker image、部署 wiring、service-token auth、Knowledge client 和 smoke tests 未落地。 | #83、#226 |
| QA 会话、消息、配置、引用和统计资源 | 部分实现 | `services/qa/` 会话/消息 API、SSE 事件、config versions、citations、retrieval test/metrics 资源、AI Gateway chat client、B-03 非流式 ResponseRun / Agent Loop MVP（本分支）。 | Gateway QA active paths；QA service OpenAPI。 | 真实 Knowledge retrieval、RAG 引用闭环、权限一致性和跨服务 smoke 待收口。 | #157、#89、#217、#219、#210 |
| QA MCP/local tool 基础 | 部分实现 | `services/qa/internal/platform/mcpclient`、local tools、安全摘要。 | QA README 和数据模型。 | MCP SDK/sidecar 版本、工具白名单运维和完整审计仍待决策。 | #151、#105 |
| AI Gateway model profile 和 credential 安全 | 已实现 | Model profile CRUD、provider credential AES-GCM 加密列、revision、service-token auth。 | AI Gateway `/internal/v1/model-profiles`；Gateway admin model profile routes。 | 真实部署的 secret manager、token 轮换和 profile 运维流程仍需补。 | #119、#204 |
| AI Gateway chat completions | 已实现 | OpenAI-compatible non-stream/stream chat、function-calling 字段透传、provider invocation 记录。 | `POST /internal/v1/chat/completions`。 | 真实 provider smoke、stream cancel 和 provider 特异行为回归仍需扩展。 | #120、#208 |
| AI Gateway embeddings | 已实现 | `POST /internal/v1/embeddings`、profile model exact-match、response count/index 校验、usage aggregate。 | AI Gateway OpenAPI embedding endpoint。 | Knowledge 尚未调用该能力形成 indexing/vector 闭环；真实 provider smoke 缺失。 | #121、#225、#152 |
| AI Gateway rerankings | 已实现 | `POST /internal/v1/rerankings`、OpenAI-style `/rerank` adapter、document_id/index 校验、usage aggregate。 | AI Gateway OpenAPI reranking endpoint。 | Knowledge/QA 尚未接入该能力形成 retrieval/rerank 闭环；真实 provider smoke 缺失。 | #121、#225 |
| Document 模板、素材、报告、大纲、章节 | 已实现 | `services/document/` 模板/材料/报告 CRUD、大纲版本、章节树、章节版本、权限和软删除测试。 | Gateway Document active paths；Document service OpenAPI。 | 模板/材料底层 File Service 的完整运行时 smoke 仍缺。 | #158、#202 |
| Document report jobs、attempts、events 和 worker 状态机 | 部分实现 | report jobs/attempts/events handlers、asynq client/worker、PostgreSQL job tables。 | `/reports/{reportId}/jobs`、`/report-jobs/{jobId}`、events 等 active paths。 | Worker 只推进状态，不执行真实大纲、正文、章节或文件生成。 | #160、#220 |
| Document report files、settings、statistics、operation logs | 占位 / 待合入 | 当前 implementation 标记 report files/statistics/settings 仍为 scaffold；#221/#223 open。 | Gateway active document paths 已声明。 | DOCX 导出、文件内容读取、配置持久化、统计和日志未进入当前 `develop`；#221/#223 合入验证后再升级状态。 | #159、#160、#221、#223 |
| Document MCP tools | 缺失 | README/requirements 保留 Document MCP 工具目标，当前 implementation 已单列缺口。 | QA/Document 工具边界设计。 | 工具注册、权限校验、脱敏输出和调用链路未落地。 | #151、#158 |
| 前端 App shell、登录态和 RBAC 导航 | 已实现 | `apps/web` auth shell、read-only report navigation 修正。 | 只调用 Gateway `/api/v1/**`。 | 管理端配置、Knowledge 页面和测试基线仍在推进。 | #109、#212、#222、#110、#111、#163 |
| 前端 Gateway 类型和 typed client | 已实现 / 需持续校验 | `openapi-typescript` 已进入前端依赖，`api:generate` 脚本存在。 | Gateway OpenAPI -> `apps/web/src/api/generated/`。 | 类型漂移需 CI 和 PR 前检查持续约束。 | #108、#161、#162 |
| 本地联调环境 | 部分实现 | QA 和 Document 有服务级 Compose；无根级全服务 Compose。 | 本地运行手册见 `docs/runbooks/local-integration.md`。 | 全服务 Compose、固定镜像版本、seed data、跨服务 smoke 缺失。 | #122、#125、#150 |
| 测试策略和 CI | 部分实现 | Go services workflow、goose migration workflow、Gateway contract workflow、API type drift workflow。 | 测试策略见 `docs/testing/strategy.md`。 | 前端完整 lint/build workflow、Vitest/RTL/Playwright、服务路径过滤矩阵和 E2E smoke 待补。 | #117、#123、#125、#163 |

## 当前最重要的文档缺口

1. 本地联调要明确“没有根级一键 Compose”，否则团队会把 QA/Document 局部 Compose 误认为全链路环境。
2. AI Gateway provider adapter 要记录 model exact-match、embedding/rerank 响应校验、脱敏和 usage aggregate，避免 Knowledge/QA/Document 接入时绕过 profile 边界。
3. QA B-03 已有 ResponseRun / Agent Loop MVP（本分支），但真实 Knowledge retrieval、RAG 引用闭环和跨服务 smoke 仍要单独追踪，避免把非流式直答误判成完整 RAG 闭环。
4. Document 生成工作流要区分“job 状态机已实现”和“真实生成未实现”，避免前端或部署方误判 DOCX 已可用。
5. 测试策略要把 Go、migration、Gateway contract、frontend check/build 和 env-gated integration tests 放在一张可执行清单里。
