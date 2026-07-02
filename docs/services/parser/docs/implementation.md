# Parser Runtime 服务实现说明

版本：v0.1
日期：2026-06-30
范围：`services/parser/` 当前实现、契约对齐、缺口和后续实现约束

## 1. 文档定位

本文档描述 `parser` 当前实现状态和后续实现约束。Parser 是内部文档解析运行时，供 Knowledge ingestion、QA 会话附件解析等后端服务调用，不通过 Gateway 公开给前端、管理端或 MCP 调用方。

权威来源：

| 类型 | 权威来源 | 本文档关系 |
| --- | --- | --- |
| 服务公开说明 | `docs/services/parser/README.md` | 只能补充，不能覆盖 |
| 服务 OpenAPI | `docs/services/parser/api/public.openapi.yaml`、`docs/services/parser/api/internal.openapi.yaml`；`services/parser/api/openapi.yaml` 是实现本地路由副本 | 只能跟随，不能另起契约 |
| 服务边界 | `docs/architecture/service-boundaries.md` | 必须遵守 |
| 技术基线 | `docs/architecture/technology-decisions.md` | 必须跟随 |
| 代码实现 | `services/parser/` | 本文档记录当前状态和差距 |

凡是本文档与上表文件冲突，以上游文件为准；发现冲突时，在“文档与实现出入”中记录并生成回写或实现任务。

## 2. 当前结论

| 项目 | 状态 | 说明 |
| --- | --- | --- |
| 文档状态 | active | Parser README、public/internal OpenAPI 和 runtime README 存在；public OpenAPI 明确无 Gateway 公开路径。 |
| 代码状态 | partial | Python/FastAPI runtime、`/healthz`、`/readyz`、`POST /internal/v1/parsed-documents`、base64/size/timeout/concurrency guard、TXT/Markdown/OpenXML 直接解析、PP-StructureV3 PDF/image parser、legacy PaddleOCR backend、Dockerfile 和 service-local tests 已落地。 |
| 契约对齐 | aligned / partial | 内部解析响应只暴露 `content`、`title`、`backend` 和页级 `pages[]` 质量字段；readiness contract 已按 #329 对齐。真实跨 Knowledge/File/Parser 依赖 smoke 仍待补齐。 |
| 数据持久化 | none | Parser 不拥有数据库、对象存储、知识库、chunk、embedding、Qdrant point 或业务权限事实。 |
| 测试状态 | partial | 默认 pytest 使用 fake OCR/backend，真实 PaddleOCR/PP-StructureV3 smoke 需显式环境变量；普通 CI 不下载模型。 |
| 建议动作 | 联调 / 运行时加固 | 补 #289 Knowledge ingestion real deps smoke、生产 compose/env/resource baseline、真实模型 smoke 运行记录和部署资源说明。 |

## 3. 已实现

| 能力 | 代码位置 | 契约来源 | 验证方式 | 备注 |
| --- | --- | --- | --- | --- |
| 健康检查 | `services/parser/src/parser_service/http` | Parser internal OpenAPI | `cd services/parser && uv run pytest` | `GET /healthz` 返回进程存活。 |
| readiness contract | `services/parser/src/parser_service/http`、`docs/services/parser/api/internal.openapi.yaml`、`services/parser/api/openapi.yaml` 实现本地副本 | #329 / internal OpenAPI | readiness OpenAPI/schema tests | `/readyz` 报告 runtime dependency 状态，不把模型缺失误写成业务解析成功。 |
| 内部解析 API | `services/parser/src/parser_service/http`、`service` | `POST /internal/v1/parsed-documents` | service/http tests | 接收 base64 文档 bytes、文件名、content type 和 size，返回项目 `{ data, requestId }` envelope。 |
| 请求 guard | `services/parser/src/parser_service/service`、`config` | Parser README | service tests | 覆盖 base64 校验、最大文档大小、解析超时、队列等待和并发限制。 |
| TXT/Markdown/OpenXML 解析 | `services/parser/src/parser_service/backends/document.py` | Parser README | pytest | TXT/Markdown、DOCX、PPTX、XLSX 直接在服务内解析。 |
| PP-StructureV3 PDF/image parser | `services/parser/src/parser_service/backends/ppstructurev3.py` | #323 / Parser README | pytest + env-gated smoke | 默认处理 PDF/image；按页渲染 PDF，使用 PP-StructureV3 输出 Markdown，合并页级 Markdown。 |
| 内存和子进程隔离 | `ppstructurev3.py`、runtime config | #323 / Parser README | pytest / review | `PARSER_PAGE_BATCH_SIZE=1`、`PARSER_SUBPROCESS_ISOLATION=true`、`PARSER_MEMORY_LIMIT_MB` 等默认值用于降低 16 GB 环境常驻模型风险。 |
| legacy PaddleOCR backend | `services/parser/src/parser_service/backends/paddleocr` | Parser README | fake/backend tests | 兼容旧行级 OCR 路径，默认仍推荐 PP-StructureV3。 |
| Docker runtime image | `services/parser/Dockerfile` | deploy baseline | build/runbook | 构建带 PaddleOCR extra 的 parser runtime image。 |
| 无公开 Gateway API | `docs/services/parser/api/public.openapi.yaml` | 服务边界 | docs/openapi review | Parser 不直接暴露给前端；管理端 parser runtime config 由 Knowledge owning API 承接。 |

## 4. 未实现

| 缺口 | 文档来源 | 影响范围 | 建议任务 |
| --- | --- | --- | --- |
| 真实 Knowledge/File/Parser ingestion smoke 未闭环 | #289 / Knowledge ingestion 流程 | Knowledge / Parser / deploy | 使用真实 PostgreSQL、File、Redis、Parser 和可选 Qdrant/AI Gateway 验证 upload -> parse -> chunks/query。 |
| 真实 PP-StructureV3 模型 smoke 缺少当前 develop 运行记录 | #285 / Parser README | parser runtime | 在有模型缓存或允许下载的环境运行 env-gated smoke 并记录结果。 |
| 生产 compose/env/resource baseline 未定稿 | #306 / deploy expectation | deploy / ops | 固定 image tag、模型缓存、内存限制、健康检查和重启策略。 |
| 页图、表格图、bbox、block/table/formula 资产化未实现 | Parser README 当前边界 | future parsing / UI | 只有后续产品需要可视化引用或版面资产时再扩展契约；不得先暴露 MinIO key 或内部路径。 |
| parser-side persistence 未实现 | 服务边界 | data ownership | 当前为正确边界；如需缓存，应先定义 owner、TTL、脱敏和清理策略。 |

## 5. 文档与实现出入

| 出入点 | 文档要求 | 当前实现 | 风险 | 建议处理 |
| --- | --- | --- | --- | --- |
| Gateway 公开路径 | Parser public OpenAPI 应为空 | 当前无 Gateway public route，符合边界 | 调用方若直连 Parser 会绕过 Knowledge 权限和业务状态 | README/implementation 明确 Parser 只服务间调用。 |
| parser runtime config owner | 管理端配置属于 Knowledge API | Parser 只消费环境变量和请求参数，不拥有 runtime config CRUD | 把 config CRUD 放进 Parser 会破坏 owner 边界 | 继续由 Knowledge `/internal/v1/parser-configs` 与 Gateway admin proxy 承接。 |
| OCR 模型状态 | README 允许普通测试不下载模型 | 默认 tests 使用 fake OCR/backend；真实模型 smoke 显式开启 | 容易把 fake 测试误读为 PaddleOCR 模型已在本机验收 | 测试表区分默认 pytest 与 env-gated real smoke。 |
| 解析响应 schema | internal OpenAPI 只承诺 lightweight parsed content | 当前响应不返回 object key、bucket、内部 URL、provider body、debug log、prompt 或 secret | 后续调试字段若直接暴露会泄漏敏感信息 | 保持脱敏约束，新增字段先更新 internal OpenAPI。 |

## 6. MVP / mock / memory backend / 占位

| 项目 | 当前用途 | 退出条件 | 关联任务 |
| --- | --- | --- | --- |
| fake OCR/backend tests | 普通 CI 和开发机无需下载 PaddleOCR 模型即可验证服务契约 | 保留为快速单元/契约测试，不替代真实模型 smoke | #285 / #289 |
| lazy backend loading | 避免普通启动和测试初始化大模型 | 生产可按资源情况设置 `PARSER_LOAD_BACKEND_ON_STARTUP=true` 做 fail-fast | deploy baseline |
| env-gated PaddleOCR smoke | 证明本机或部署环境可加载真实模型并跑最小 fixture | 需要模型缓存或允许下载；结果写入 runbook/implementation | #285 |
| optional PaddleX config path | 离线或部署近似环境指定本地模型 | 生产镜像/挂载策略固定后写入部署文档 | #306 |

## 7. 运行与配置

| 项目 | 当前状态 | 缺口 |
| --- | --- | --- |
| 启动命令 | `cd services/parser && uv run parser-service` | 生产部署需固定模型缓存、资源限制和健康检查策略。 |
| 环境变量 | `PARSER_HOST`、`PARSER_PORT`、`PARSER_SERVICE_TOKEN`、`PARSER_BACKEND`、`PARSER_MAX_DOCUMENT_BYTES`、`PARSER_MAX_CONCURRENCY`、`PARSER_QUEUE_TIMEOUT_SECONDS`、`PARSER_PARSE_TIMEOUT_SECONDS`、`PARSER_LOAD_BACKEND_ON_STARTUP`、`PARSER_PROFILE`、DPI/重试/子进程/内存限制、`PADDLEOCR_*`、`PPSTRUCTUREV3_*` | 详细默认值见 `services/parser/README.md`；部署文档仍需固定资源和模型缓存策略。 |
| PostgreSQL / migration | 不拥有数据库 | 无。 |
| Redis / queue | 不使用队列；任务由 Knowledge/asynq 管理 | 无。 |
| Object storage / vector store / AI provider | 不直接访问；raw file、chunk、embedding、Qdrant、AI provider 都由 owner services 处理 | 无。 |

## 8. 测试与验证

| 验证项 | 命令或步骤 | 当前结果 | 缺口 |
| --- | --- | --- | --- |
| 代码检查 | `cd services/parser && uv run ruff check .` | available / not run in this documentation pass | 需要本机 uv 依赖环境。 |
| 默认测试 | `cd services/parser && uv run pytest` | available / not run in this documentation pass | 默认使用 fake OCR/backend，不证明真实模型加载。 |
| Python compile | `cd services/parser && uv run python -m compileall src tests` | available / not run in this documentation pass | 需要本机 uv 依赖环境。 |
| 真实 PaddleOCR smoke | `PARSER_PADDLEOCR_SMOKE=1 PARSER_PADDLEOCR_ALLOW_DOWNLOAD=1 uv run pytest -m paddleocr_smoke -s` | env-gated / not run by default | 需要真实模型、网络或本地缓存；普通 CI skip。 |
| 离线模型 smoke | `PARSER_PADDLEOCR_SMOKE=1 PARSER_PADDLEOCR_CONFIG_PATH=/absolute/path/to/paddlex.yaml uv run pytest -m paddleocr_smoke -s` | env-gated / not run by default | 需要准备好的 PaddleX config 和模型文件。 |
| 跨服务 smoke | Knowledge upload -> Parser parse -> chunks/query | missing | 由 #289 承接，需要 File、Redis、PostgreSQL、Parser 和可选 Qdrant/AI Gateway。 |

## 9. 建议任务

| 任务 | 类型 | 优先级 | 依据 | 说明 |
| --- | --- | --- | --- | --- |
| 运行并记录真实 PaddleOCR/PP-StructureV3 smoke | 测试 / runbook | P0 | #285 / #323 | 在可控模型环境验证 real backend，记录 fixture、资源、耗时和失败模式。 |
| 完成 Knowledge ingestion real deps smoke | 测试 / runbook | P0 | #289 | 证明 Parser 与 File/Knowledge/Redis/Qdrant/AI Gateway 可组合，而不只是在单服务测试中通过。 |
| 固定 Parser deploy baseline | 部署任务 | P1 | #306 | 明确 image tag、模型缓存挂载、内存限制、CPU/GPU 选择、健康检查和降级策略。 |
| 评估解析资产化契约 | 后续增强 | P2 | UI/引用可视化需求 | 若需要页图/table/formula/bbox，先定义 owner 和脱敏输出，再扩展 OpenAPI。 |

## 10. 最近检查记录

| 日期 | 检查人/工具 | 代码基准 | 结论 |
| --- | --- | --- | --- |
| 2026-06-30 | Codex full-day audit | `develop@92d3afc` | 复核今日 PR/issue：Parser Runtime 已包含 Python/FastAPI 服务、internal parse API、PP-StructureV3 默认 PDF/image parser、子进程/分页内存保护、readiness contract 对齐、pytest 安全更新和 env-gated real PaddleOCR smoke 入口；无 Gateway public API。剩余为 #289 跨服务真实依赖 smoke、真实模型运行记录和生产 deploy/env/resource baseline。 |
