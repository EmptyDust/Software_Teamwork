# Knowledge Service 实现说明

版本：v0.5
日期：2026-06-30
范围：`services/knowledge/` 当前实现、契约对齐、缺口和后续实现约束

## 1. 文档定位

本文档描述 `knowledge` 当前实现状态和后续实现约束。它只补充服务 README、OpenAPI、架构和技术选型文档，不覆盖这些上游契约。

权威来源：

| 类型 | 权威来源 | 本文档关系 |
| --- | --- | --- |
| 服务公开说明 | `docs/services/knowledge/README.md` | 只能补充，不能覆盖 |
| 服务 OpenAPI | `services/knowledge/api/openapi.yaml` | 只能跟随，不能另起契约 |
| Gateway 公开契约 | `docs/services/gateway/api/openapi.yaml` | 前端稳定契约以 gateway 为准 |
| 服务边界 | `docs/architecture/service-boundaries.md` | 必须遵守 |
| 技术基线 | `docs/architecture/technology-decisions.md` | 必须跟随 |
| 代码实现 | `services/knowledge/` | 本文档记录当前状态和差距 |

凡是本文档与上表文件冲突，以上游文件为准；发现冲突时，在“文档与实现出入”中记录并生成回写或实现任务。

## 2. 当前结论

| 项目 | 状态 | 说明 |
| --- | --- | --- |
| 文档状态 | active | README、公开草案、数据模型、内部 OpenAPI 和实现说明存在。 |
| 代码状态 | partial | Go service 已实现知识库 CRUD、文档列表/上传/详情、File Service handoff、PostgreSQL repository 和 asynq enqueue。Parser service 仅有独立契约文档，Knowledge runtime 尚未接入。 |
| 契约对齐 | drifted | Gateway OpenAPI 已声明 chunks、content、knowledge-queries、parser configs；gateway route matrix 将其中多个 Knowledge active path 标为 `NotImplemented`。 |
| 数据持久化 | postgres / Redis queue | runtime 使用 PostgreSQL；上传后投递 asynq ingestion task。Qdrant 和 chunk/vector 写入未落地。 |
| 测试状态 | partial | 单元和 handler tests 覆盖 CRUD、权限、上传补偿和 queue handoff；缺端到端入库、Qdrant、检索测试。 |
| 依赖解耦 | documented | A-12 检索和 A-14 契约测试可依赖 `docs/api-contract.md` 2.6 与 `docs/data-models.md` 6.7 的 seeded chunk/vector fixture，不再要求 A-11 worker runtime 先完成。 |
| 建议动作 | 并行补实现 | A-11 继续补真实 ingestion worker；A-12 可先实现 retrieval contract 和 fake adapter 测试；A-14 可先收口 active operation/error/request id 契约测试。 |

## 3. 已实现

| 能力 | 代码位置 | 契约来源 | 验证方式 | 备注 |
| --- | --- | --- | --- | --- |
| 健康检查 | `services/knowledge/internal/http/server.go` | `services/knowledge/api/openapi.yaml` | `cd services/knowledge && go test ./...` | `GET /healthz`、`GET /readyz`。 |
| 知识库 CRUD | `services/knowledge/internal/http/server.go`、`internal/service/service.go` | `services/knowledge/api/openapi.yaml` | `TestKnowledgeBaseCRUDAndSoftDelete` | 支持列表、创建、详情、更新、软删除。 |
| 用户上下文和权限校验 | `services/knowledge/internal/service/service.go` | `docs/services/knowledge/README.md` | service tests | 依赖 gateway 注入的 user/permission context。 |
| 文档列表和详情 | `services/knowledge/internal/http/server.go` | `services/knowledge/api/openapi.yaml` | `TestDocumentListAndDetailExcludeDeletedKnowledgeBase` | 只覆盖文档元数据/状态。 |
| 文档上传 handoff | `services/knowledge/internal/platform/fileclient/client.go`、`internal/service/service.go` | `docs/services/knowledge/README.md`、`docs/services/file/README.md` | `TestUploadDocumentCreatesDocumentJobAndQueuesIngestion` | multipart 上传后调用 File `/internal/v1/files`，保存 `file_ref`，创建 processing job。 |
| asynq 入队 | `services/knowledge/internal/platform/queue` | `docs/architecture/technology-decisions.md` | service tests with fake queue | 只投递 ingestion task；worker 未落地。 |
| PostgreSQL migration/repository | `services/knowledge/migrations/0001_create_knowledge_core_tables.sql`、`internal/repository/postgres.go` | `docs/services/knowledge/docs/data-models.md` | `go test ./...`；CI 用 `KNOWLEDGE_TEST_DATABASE_URL` 跑 repository lifecycle integration test | runtime 使用 PostgreSQL。 |

## 4. 未实现

| 缺口 | 文档来源 | 影响范围 | 建议任务 |
| --- | --- | --- | --- |
| 文档处理 worker 未实现 | `docs/services/knowledge/README.md`、`docs/requirements-analysis/overall-requirements-analysis.md`、`docs/services/parser/README.md` | worker / DB / Redis / Parser | 实现 worker 调用 Parser Service 解析 raw bytes，再执行 chunking/embedding/indexing 状态流转；上传入队不能被写成入库闭环完成。 |
| chunks API 未实现 | `docs/services/gateway/api/openapi.yaml` | API / frontend / QA | 实现 `GET /internal/v1/documents/{documentId}/chunks` 并开放 gateway route。 |
| 原文 content API 未实现 | `docs/services/gateway/api/openapi.yaml` | API / file integration | 通过 file reference 读取原文件内容。 |
| `knowledge-queries` 检索未实现 | `docs/services/gateway/api/openapi.yaml`、`docs/services/knowledge/api/public.openapi.yaml`、`docs/services/knowledge/docs/api-contract.md` 2.6 | API / QA / document | 可先用 seeded chunks、fake vector hits 和 fake AI Gateway adapter 实现契约；真实 Qdrant/embedding/rerank runtime 作为集成层补齐。 |
| Qdrant adapter / embedding / rerank 未实现 | `docs/architecture/service-boundaries.md`、`docs/services/knowledge/docs/data-models.md` | vector store / AI provider | 接入 AI Gateway embeddings/rerank 和 Qdrant；AI Gateway endpoint 已有不等于 Knowledge RAG 可用。 |
| Parser service runtime 未实现 | `docs/services/parser/README.md`、`docs/services/parser/api/internal.openapi.yaml` | parser / OCR / ingestion | Parser 已有内部契约；Python/PaddleOCR runtime、Docker image、部署 wiring 和 Knowledge HTTP client 仍需后续实现。 |
| admin parser-configs 未实现 | `docs/services/gateway/api/openapi.yaml` | API / admin | 实现解析器配置资源或由管理组决策契约阶段状态。 |
| document PATCH/DELETE 未实现 | `docs/services/gateway/api/openapi.yaml` | API / frontend | 实现标签更新、删除和 file/index cleanup。 |

## 5. 文档与实现出入

| 出入点 | 文档要求 | 当前实现 | 风险 | 建议处理 |
| --- | --- | --- | --- | --- |
| Gateway active Knowledge paths | Gateway OpenAPI 将 18 个 knowledge operation 设为 active | `services/gateway/internal/http/routes.go` 中 `PATCH/DELETE /documents`、chunks、content、knowledge-queries、parser-configs 标为 `NotImplemented` | 前端生成 client 后调用会得到 501 | 要么补实现并取消 `NotImplemented`，要么把阶段性未实现状态回写到契约说明。 |
| 旧实现说明提到 Qdrant/local hashing | 早期文档描述 Qdrant HTTP adapter 和 local hashing embedding | 当前 `services/knowledge/` 无 Qdrant/embedding platform 代码 | 文档高估实现成熟度 | 已在本文改为未实现；同步更新技术选型状态。 |
| AI Gateway embedding/rerank 状态 | AI Gateway 已实现 embeddings/rerankings endpoint | Knowledge 尚未调用 AI Gateway，也没有 Qdrant adapter 或 ingestion worker 闭环 | 容易误读为 Knowledge RAG 已可用 | 维持 Knowledge 未闭环表述，并拆 Knowledge ingestion worker + Qdrant + embedding/rerank 接入任务。 |
| 公开 Knowledge 草案范围 | `docs/services/knowledge/api/public.openapi.yaml` 覆盖 deletion jobs、processing jobs、query tests、support materials、settings、statistics | runtime 只实现 KB CRUD 和文档 upload/list/detail | 公开草案可能被误读为已落地 | 保留为设计草案，在 implementation 中明确缺口。 |
| File handoff 边界 | Knowledge 拥有文档资源，File 只保存基础 file object | 当前已按 `/internal/v1/files` 保存 raw file，但 content/delete cleanup 未闭环 | 删除或内容读取时 file reference 可能残留 | 实现 document lifecycle cleanup。 |
| asynq 任务状态权威 | PostgreSQL 为 job 状态权威，Redis 只排队 | 已创建 job 并投递任务，但无 worker 更新状态 | 文档状态可能长期停留在 uploaded | 补 worker 或阶段性标记为 pending implementation。 |
| A-12/A-14 对 A-11 的误依赖 | `docs/api-contract.md` 2.6 定义稳定 chunk/vector fixture 交接面 | runtime worker 未完成，但契约测试可 seed 所需数据 | Project 依赖字段可能把可并行工作排成串行 | A-12/A-14 的单元、handler、contract 测试按 fixture/fake adapter 执行；端到端 smoke 另等 A-11。 |
| Parser 边界 | 解析运行时应在 Parser Service，Knowledge 只消费 parsed content | 当前 Knowledge runtime 尚未接入 Parser；PR #226 提供了文档和实现草案但未合入当前分支 | 容易把 OCR 依赖放回 Knowledge Go 进程 | 保留 Parser HTTP 契约，后续实现不得在 Knowledge 中引入 PaddleOCR/PaddlePaddle/OpenCV/CUDA。 |

## 6. MVP / mock / memory backend / 占位

| 项目 | 当前用途 | 退出条件 | 关联任务 |
| --- | --- | --- | --- |
| memory repository | 单元测试 | PostgreSQL integration tests 覆盖关键 CRUD 后仍可保留测试用 | 保留测试用 |
| fake file client / fake queue | 上传补偿和入队测试 | 真实 file/Redis 集成测试补齐 | File/Redis integration smoke |
| fake parser client | A-11 worker、A-12/A-14 契约测试的 parsed content 输入 | 真实 Parser service smoke 稳定后仍可保留为快速契约测试 | Parser contract tests |
| seeded chunk/vector fixture | A-12 retrieval 和 A-14 contract tests | 真实 worker + Qdrant + AI Gateway smoke 稳定后仍可保留为快速契约测试 | A-12/A-14 并行开发 |
| fake vector / fake AI adapter | 检索过滤、rerank trace、错误 envelope 和 request id 测试 | 真实依赖集成测试补齐；不替代端到端 smoke | Retrieval contract tests |
| gateway `NotImplemented` Knowledge routes | 暂时占住 active contract | 对应服务实现或契约阶段状态经管理组确认 | Knowledge active paths follow-up |

## 7. 运行与配置

| 项目 | 当前状态 | 缺口 |
| --- | --- | --- |
| 启动命令 | `cd services/knowledge && go run ./cmd/server` | 需要 PostgreSQL、File Service 和 Redis。 |
| 环境变量 | `DATABASE_URL`、`FILE_SERVICE_BASE_URL`、`KNOWLEDGE_REDIS_ADDR` 必填；另有 HTTP/version/env/max upload/service token/shutdown | 缺 Qdrant、embedding/rerank、parser 配置 runtime env。 |
| PostgreSQL / migration | `migrations/0001_create_knowledge_core_tables.sql`，runtime `pgx/v5` | goose apply CI 已覆盖 migration；repository lifecycle 由 `KNOWLEDGE_TEST_DATABASE_URL` 集成测试覆盖。 |
| Redis / queue | 使用 `asynq` client 投递 ingestion | worker 未实现。 |
| Parser / object storage / vector store / AI provider | 通过 File Service 保存 raw file；Parser 契约已补 | Parser runtime、Qdrant adapter 尚未落地；Knowledge 尚未接入 Parser 或 AI Gateway embedding/rerank 调用。 |

## 8. 测试与验证

| 验证项 | 命令或步骤 | 当前结果 | 缺口 |
| --- | --- | --- | --- |
| 单元测试 | `cd services/knowledge && go test ./...` | pass（本次执行） | 主要使用 memory/fake 依赖。 |
| Repository 集成测试 | `KNOWLEDGE_TEST_DATABASE_URL=... go test ./internal/repository -count=1` | CI 覆盖 repository lifecycle；无 env 时本地跳过 | 只覆盖 PostgreSQL repository，不覆盖 File/Redis/Qdrant。 |
| 端到端上传联调 | PostgreSQL + File + Redis end-to-end upload | missing | 需要真实依赖联调。 |
| A-12 检索契约测试 | seeded documents/chunks + fake vector/AI adapter | documented, not implemented | 不要求真实 A-11 worker；覆盖 topK/threshold/tags/rerank、空结果、不可见文档过滤。 |
| A-14 active operation 契约测试 | gateway route matrix + Knowledge handler tests + fake dependencies | partial | 可先验证 OpenAPI schema、错误 envelope、request id 和 501 退出；Parser/File/Qdrant/AI Gateway 跨服务 smoke 另列。 |
| Parser contract test | `docs/services/parser/api/internal.openapi.yaml` schema review + future HTTP tests | documented, not implemented | 需要 Parser runtime 实现后补 health/ready/parse/error/de-sensitization tests。 |
| 手工 smoke | 启动 PostgreSQL、File、Redis 后上传文档 | not run | 需要可复现脚本或 Compose。 |

## 9. 建议任务

| 任务 | 类型 | 优先级 | 依据 | 说明 |
| --- | --- | --- | --- | --- |
| 实现 Knowledge 文档内容、删除和 chunks API | 新任务 | P0 | Gateway active contract | 解除 `/documents/**` 相关 501。 |
| 实现 ingestion worker 与状态流转 | 新任务 | P0 | 上传后必须进入处理闭环 | 调用 Parser 解析 raw bytes，再处理 chunking/embedding/ready/failed。 |
| 实现 Parser runtime | 新任务 | P0 | A-11 解析运行时边界 | 按 `docs/services/parser/api/internal.openapi.yaml` 落地 Python/PaddleOCR 服务、Docker image、service token、payload limit 和脱敏错误。 |
| 实现 Qdrant + AI Gateway embedding/rerank 接入 | 新任务 | P0 | 文档/代码出入评审结论 | 上传入队 -> chunk/content -> embedding -> Qdrant -> retrieval/rerank 最小闭环。 |
| 实现 knowledge-queries 检索 | 新任务 | P0 | QA/Document 依赖检索 | 先按 seeded chunk/vector fixture 返回 chunk/document/source/score，并可选 rerank 摘要；真实 worker/Qdrant/AI Gateway smoke 作为集成层。 |
| 实现 parser configs 或回写契约状态 | 新任务 | P1 | Gateway active admin paths | 避免 active path 长期 501。 |

## 10. 最近检查记录

| 日期 | 检查人/工具 | 代码基准 | 结论 |
| --- | --- | --- | --- |
| 2026-06-30 | Codex | working tree | 补充 A-11/A-12/A-14 解耦契约：A-12/A-14 可用 seeded chunks、fake vector/AI adapter 做契约和 handler 测试；完整 ingestion runtime 仍由 A-11 交付。 |
| 2026-06-30 | Codex | PR #226 docs extraction | 从 PR #226 单独抽出 Parser Runtime 文档和 OpenAPI 契约；当前分支只记录契约，未引入 Knowledge worker 实现代码。 |
| 2026-06-29 | Codex goal | `eddf917` + working tree | Knowledge 已完成 KB CRUD 和文档上传 handoff，但入库 worker、chunks、content、retrieval、parser config 仍是关键缺口。 |
