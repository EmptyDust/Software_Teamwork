# 文档维护工作流

本文定义 `docs/` 下文档的归属规则，避免把跨服务标准重复写进单个服务细则。

## 文档归属

| 内容类型 | 权威位置 | 服务文档中应如何处理 |
| --- | --- | --- |
| 服务职责、数据归属、公开能力边界 | `docs/architecture/service-boundaries.md` | 只写本服务负责/不负责的细化说明，并链接边界矩阵。 |
| 技术栈、数据库、迁移、日志、队列、测试和观测基线 | `docs/architecture/technology-decisions.md` | 只记录本服务的特殊约束或明确偏离原因，不重复完整技术栈表。 |
| RESTful 路径、OpenAPI、统一响应、分页、错误、SSE、上传和 request id | `docs/architecture/frontend-backend-contract.md` | 只列本服务资源路径、业务语义、状态枚举和服务特有错误场景。 |
| 分支、PR、提交、CI 和维护者设置 | `CONTRIBUTING.md`、`docs/collaboration/*.md` | 服务文档不得定义仓库级流程。需要补充时更新协作文档。 |
| 机器可读 API 契约 | `docs/services/<service>/api/public.openapi.yaml` 和 `docs/services/<service>/api/internal.openapi.yaml` | Markdown 只解释业务语义，不替代 OpenAPI schema；服务级 `public` 中未进入 Gateway active paths 的内容必须标为 candidate/draft。 |
| 服务权限矩阵 | `docs/services/<service>/docs/permission-matrix.md` | README、API 设计、runbook 和链路文档只链接权限矩阵，不重复维护角色能力表、权限字符串集合、owner 访问规则或 `401` / `403` 分支。 |
| 服务内数据模型、业务流程 | `docs/services/<service>/README.md` 和 `docs/services/<service>/docs/data-models.md` 等细节文档 | 保留服务特有内容，避免复制跨服务规则。 |
| 当前实现状态、代码与契约出入、临时后端、最近检查记录 | `docs/services/<service>/docs/implementation.md` | README 只链接 implementation 文档，不重复列实现缺口、代码状态或检查结论。 |

## 文档与代码出入判定

出现文档和代码不一致时，不再笼统说“以代码为准”或“以文档为准”，按层级判断：

1. 契约层优先。Gateway OpenAPI、服务边界、数据模型、明确验收需求和团队已确认需求是协作契约。
2. `develop` 代码是当前事实基线。open PR、未合入 issue 和草案不能写成当前已实现。
3. `docs/services/<service>/docs/implementation.md` 负责记录当前事实，包括已实现、部分实现、pending、not implemented 和实现/契约出入。
4. README、runbook 和 testing strategy 只负责入口、操作方式和限制说明，不替代契约和实现状态文档。

处理规则：

- 代码偏离已确认契约时，默认修代码；如确需改契约，先交管理组决策。
- 当前实现状态文档落后时，修 `implementation.md` 或相关状态文档。
- 设计目标未落地时，文档保留目标，但必须标为 pending / not implemented，不得写成已实现。
- 联调、CI、运行环境缺支撑时，先在 runbook 或 testing strategy 写清限制，再拆 follow-up issue。

实现 PR 不应擅自修改协作契约。契约变更包括但不限于 Gateway public OpenAPI 路径、字段、状态码、错误码或认证方式，服务边界，资源归属，数据模型核心关系，已确认需求验收语义，以及会影响多组并行开发的内部服务接口。

## 更新顺序

新增或修改公开接口时：

1. 先确认归属服务和边界，必要时更新 `docs/architecture/service-boundaries.md`。
2. 更新 `docs/services/gateway/api/public.openapi.yaml`，公开字段、状态码和错误码以 OpenAPI 为准。
3. 如果改动影响通用调用规则，更新 `docs/architecture/frontend-backend-contract.md`。
4. 更新对应服务文档，只补充服务业务语义、状态枚举、工作流和实现注意事项。不要在 README 中复制完整 active operation 表；逐项清单由 Gateway OpenAPI 和 owner map 维护。
5. 如果涉及协作、CI、分支或提交要求，更新 `docs/collaboration/` 或 `CONTRIBUTING.md`。

新增或修改内部服务接口时：

1. 更新对应服务的 `api/internal.openapi.yaml`。
2. 如果内部能力会影响公开 API、前端生成类型或服务边界，同步更新 gateway OpenAPI、架构契约和服务边界矩阵。
3. 服务 README 只记录内部接口的业务用途和调用边界，不复制项目统一 envelope、日志或技术栈基线。

行为变更 PR 还必须按改动范围检查文档：

| 改动类型 | 必须检查或更新 |
| --- | --- |
| 服务能力变化 | 对应 `docs/services/<service>/docs/implementation.md`。 |
| OpenAPI / Gateway active path / 数据模型变化 | OpenAPI、README、owner map、service boundaries 或相关契约文档；契约语义变化需先交管理组决策。 |
| runtime dependency / Compose / CI / provider adapter / worker / migration 变化 | `technology-decisions.md`、runbook 或 `testing/strategy.md`。 |
| open PR 或未合入能力 | 不得写进“已实现”；只能写为 pending、待合入或 follow-up。 |

## 服务文档检查清单

提交服务文档前，检查：

- 没有在服务 README 中重新定义仓库级分支、PR、提交或 CI 流程。
- 没有在服务 README 中重复完整技术选型表；仅保留服务特有约束。
- 统一响应、分页、错误 envelope、request id、SSE 和上传规则链接到前后端集成契约。
- RESTful 命名规则链接到前后端集成契约或服务边界矩阵；服务文档只给出本服务资源映射。
- Markdown 中的字段和状态没有与 OpenAPI 冲突；如冲突，以 OpenAPI 为准并修正文档。
- 没有把 open PR 或未合入 issue 写成当前 `develop` 已实现能力。
- 没有在实现 PR 中直接修改协作契约语义；确需修改时已有管理组决策记录。
- 当前代码实现、未实现能力、mock/memory 后端和文档与实现出入只写在对应服务的 `docs/implementation.md`，不要在 README、架构文档或数据模型文档重复维护。
