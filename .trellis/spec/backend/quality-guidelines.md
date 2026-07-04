# Quality Guidelines

> Code quality standards for Go backend services.

---

## Overview

Every backend service must remain independently testable, buildable, and
deployable. Quality checks run from each service directory because every service
owns a separate `go.mod`.

Minimum Go service-local checks:

```bash
go test ./...
go build ./cmd/server
```

`services/knowledge-runtime/` is a Python vendored runtime boundary rather than
a Go service. When changing the runtime API, route registration, parser/chunking
configuration, or Docker entrypoints, run targeted runtime tests from
`services/knowledge-runtime` and the owning Knowledge adapter checks:

```bash
cd services/knowledge-runtime
PYTHONPATH=. uv run --no-project --with pytest --with pytest-asyncio python -m pytest <targeted tests> -q

cd ../knowledge
go test ./...
go build ./cmd/adapter
```

### Knowledge Runtime PDF E2E

#### 1. Scope / Trigger

- Trigger: changing Knowledge document upload, runtime API/worker wiring,
  parser/chunking/embedding/indexing behavior, retrieval contracts, or
  host-run Knowledge runtime startup.
- Applies to `services/knowledge`, `services/knowledge-runtime`, `deploy/**`,
  and Knowledge runbook entries.

#### 2. Signatures

```bash
# Exact command may vary by local runtime profile, but the smoke must prove:
# upload PDF -> runtime parse/chunk/embed/index -> retrieval returns hits.
DL_T_673-1999.pdf
```

#### 3. Contracts

- The old standalone `services/parser` must not be restored.
- Knowledge owns document business state, permissions, and public responses.
- `services/knowledge-runtime` owns parse, chunk, embedding, index, and
  retrieval support as an implementation detail behind the Knowledge adapter.
- A real PDF E2E must record document readiness, chunk count, query id, hit
  count, and a short retrieval preview when the fixture is available.
- Cloud OCR model adapters used by the runtime chunker must preserve the OCR
  parser interface expected by chunking code, including `crop`, `remove_tag`,
  and `outlines`. Unit coverage for a new OCR adapter must exercise these
  delegation methods, not just the remote parse request.
- Binding the embedding model is part of the parse job. Runtime code may retry
  provider-marked transient model failures, such as a retryable upstream `502`,
  with bounded attempts and delay; it must not retry non-retryable
  authentication, authorization, or configuration errors.
- Parser and model smoke logs may include provider job ids and redacted parser
  configuration, but must not print access tokens or raw credential payloads.

#### 4. Validation & Error Matrix

| Condition | Required handling |
| --- | --- |
| Runtime API unreachable | Fail with the configured `VENDOR_RUNTIME_URL` and sanitized proxy/network diagnostics. |
| Worker not consuming tasks | Fail with document status, elapsed polling time, and worker health/log pointer. |
| Chunk count is zero | Fail with document id, parser configuration, and runtime task status. |
| Retrieval returns zero hits for the fixture | Fail with query id, chunk count, and retrieval config. |

#### 5. Good/Base/Bad Cases

- Good: targeted unit/contract tests pass and a real PDF E2E proves upload,
  parse, chunk, index, and retrieval.
- Base: PR records that only unit/contract checks ran because local runtime
  infrastructure is unavailable, with the blocker stated explicitly.
- Bad: reporting success from adapter unit tests while the real runtime upload
  or retrieval path was not exercised.

#### 6. Tests Required

- Knowledge adapter: `go test ./...` and `go build ./cmd/adapter`.
- Runtime route/config tests for changed Python surfaces.
- Runtime OCR adapter tests for cloud parser wrappers, including chunker-facing
  helper methods used after parsing succeeds.
- Runtime task executor tests for retryable versus non-retryable model binding
  failures when embedding providers are involved.
- Docker policy and Compose config checks when deployment wiring changes.
- Real PDF E2E when `DL_T_673-1999.pdf` is present.

#### 7. Wrong vs Correct

Wrong:

```bash
go test ./...  # then claim PDF parsing and retrieval were proven
```

Correct:

```bash
go test ./...
# plus an explicit PDF upload -> ready/chunks -> retrieval smoke against runtime
```

### Knowledge Runtime Standard Corpus Evaluation

#### 1. Scope / Trigger

- Trigger: changing standard-document parsing, OCR routing, cleanup, clause
  chunking, table extraction, runtime parser selection, or metadata propagation
  for Knowledge runtime.
- Applies to `services/knowledge-runtime/tools/evaluate_standard_corpus.py`,
  standard-parser modules, and Trellis task artifacts that compare before/after
  parsing quality.
- The command evaluates local PDFs only. It must not call OCR providers, read
  `.env.local`, or require runtime services unless an explicit parser sample is
  requested.

#### 2. Signatures

Run from `services/knowledge-runtime`:

```bash
PYTHONPATH=. uv run --no-project --with pypdf python tools/evaluate_standard_corpus.py \
  --input ../../res/知识库管理/标准文档 \
  --output ../../.trellis/tasks/<task>/artifacts/baseline.json \
  --summary ../../.trellis/tasks/<task>/artifacts/baseline.md \
  --mode current
```

Optional current-parser sampling:

```bash
PYTHONPATH=. uv run --no-project --with pypdf python tools/evaluate_standard_corpus.py \
  --input ../../res/知识库管理/标准文档 \
  --output ../../.trellis/tasks/<task>/artifacts/baseline-plain-text-sample.json \
  --summary ../../.trellis/tasks/<task>/artifacts/baseline-plain-text-sample.md \
  --mode current \
  --parse-sample 1 \
  --layout-recognize "Plain Text"
```

#### 3. Contracts

Inputs:

- `--input`: local directory scanned recursively for `*.pdf`.
- `--output`: machine-readable JSON path.
- `--summary`: Markdown summary path.
- `--mode`: `probe` or `current`.
- `--parse-sample`: optional number of PDFs to run through the current parser.
- `--layout-recognize`: parser backend label recorded and used for parser
  sampling.

Output JSON must include:

- `run.input_dir`, `run.mode`, `run.started_at`, `run.tool_version`;
- `corpus.pdf_count`, `corpus.total_pages`, `corpus.file_list_sha256`;
- `text_probe.zero_text`, `lt_100_chars`, `chars_100_to_999`,
  `gte_1000_chars`, `garbled_candidates`, `read_errors`;
- `runtime_parse.attempted`, `ready`, `failed`, `empty_outputs`,
  `configured_backend`, `skipped_reason`;
- `chunks.total`, `empty`, `avg_chars`, `median_chars`, `table_chunks`;
- when `--parse-sample` is set, standard clause evaluation fields:
  `standard_clause_chunking.attempted`, `ready`, `failed`,
  `total_clause_chunks`, `with_section_path`, `with_clause_no`,
  `clean_public_content`, `section_path_coverage`, and
  `clean_public_content_coverage`;
- when `--parse-sample` is set, standard table evaluation fields:
  `standard_table_extraction.attempted`, `ready`, `failed`,
  `table_chunks`, `row_chunks`, `with_caption`, `with_context`,
  `caption_coverage`, and `context_coverage`;
- per-document probe rows with relative file paths, page counts, sampled pages,
  sampled chars, text bucket, and garbled-candidate marker.

Security:

- Do not read or print OCR tokens, provider API keys, database URLs, MinIO
  credentials, or `.env.local`.
- Do not commit source PDFs from `res/`.
- Preview text must be short and UTF-8 safe. PDF text extraction can yield
  invalid surrogate characters; sanitize previews before JSON/Markdown writes.
- Clause/table samples in the evaluator must not import the full indexing
  tokenizer stack. Use lightweight token/position fillers for evaluation-only
  chunk payloads; production chunking remains responsible for calling the
  runtime tokenizer and position writer.

#### 4. Validation & Error Matrix

| Condition | Required handling |
| --- | --- |
| Input path is missing or not a directory | Fail with a clear local path error. |
| A PDF cannot be read | Record a per-document `error`, increment `read_errors`, continue the corpus run. |
| Extracted text contains invalid Unicode surrogates | Replace invalid characters in previews/errors before writing JSON/Markdown. |
| Current parser import fails during `--parse-sample` | Keep probe metrics and set `runtime_parse.skipped_reason` to the import failure. |
| A sampled parse fails for one PDF | Record that document as failed and continue remaining sampled files. |
| `--parse-sample` is not set | Record `parse_sample_not_requested`; do not pretend runtime chunking was exercised. |
| Clause sample builder import fails | Keep probe metrics and set `standard_clause_chunking.skipped_reason` to the import failure. |
| Clause sample cannot chunk one PDF | Record that document as failed and continue remaining sampled files. |
| Table sample builder import fails | Keep probe metrics and set `standard_table_extraction.skipped_reason` to the import failure. |
| Table sample finds no tables in pypdf text | Record attempted documents as `empty`; do not treat this as parser-table extraction failure. |

#### 5. Good/Base/Bad Cases

- Good: full local corpus probe records PDF/page counts, text buckets, garbled
  candidates, and a small parser sample with chunk statistics.
- Base: probe-only run records `parse_sample_not_requested` and is still a valid
  baseline for OCR routing and text-layer quality.
- Bad: claiming parser chunk quality from probe-only output, or treating
  scanned/zero-text documents as successfully parsed without OCR.

#### 6. Tests Required

- Unit tests for page sampling, text bucket boundaries, garbled/CID detection,
  invalid-surrogate sanitization, output schema, and secret non-leak behavior.
- Unit tests for standard cleanup, full-width heading detection, clause metadata,
  public cleaned content, and evaluator clause coverage metrics.
- Unit tests for standard table caption detection, DeepDOC-like table tuples,
  markdown/html table sections, row-level quality gates, and evaluator table
  coverage metrics.
- A local corpus run against `res/知识库管理/标准文档` when the directory is
  available.
- `git diff --check` for changed runtime tool/test files.

#### 7. Wrong vs Correct

Wrong:

```bash
python tools/evaluate_standard_corpus.py --input ../../res/知识库管理/标准文档
# no explicit output paths, no JSON artifact, no skipped_reason for parser stats
```

Correct:

```bash
PYTHONPATH=. uv run --no-project --with pypdf python tools/evaluate_standard_corpus.py \
  --input ../../res/知识库管理/标准文档 \
  --output ../../.trellis/tasks/<task>/artifacts/baseline.json \
  --summary ../../.trellis/tasks/<task>/artifacts/baseline.md \
  --mode current
```

When lint tooling is introduced, CI should run the selected linter for each
changed service.

---

## Go Service CI Baseline

### 1. Scope / Trigger

- Trigger: adding or changing repository CI for landed Go services under `services/*`.

### 2. Signatures

- Workflow: `.github/workflows/go-services.yml`.
- Events: `pull_request` and `push` to `develop` with path filters for `services/**` and the workflow file.
- Matrix key: `service`, with one entry for each landed Go service that owns a `go.mod`.

### 3. Contracts

- Toolchain: `actions/setup-go@v5` with `go-version: '1.25.x'`.
- Working directory: `services/${{ matrix.service }}`.
- Required commands for every matrix service: `go test ./...` and `go build ./cmd/server`.
- QA contract: run `go build ./cmd/agent` when `services/qa/cmd/agent` exists.
- Cache dependency input must exist for every matrix service; use `services/${{ matrix.service }}/go.mod` unless all services have `go.sum`.

### 4. Validation & Error Matrix

| Condition | Required response |
|-----------|-------------------|
| Service directory has `go.mod` but no matrix entry | Add it before merging CI changes. |
| Matrix entry has no `services/<name>/go.mod` | Remove or fix the entry; setup/run will fail. |
| Go service module diverges from `go-version: '1.25.x'` CI baseline | Update the module baseline or CI baseline together. |
| `services/qa/cmd/agent` exists but CI does not build it | Add or restore the QA agent build step. |

### 5. Good/Base/Bad Cases

- Good: `services/qa` runs tests, server build, and agent build under Go `1.25.x`.
- Base: a service with no `go.sum` still caches against its existing `go.mod`.
- Bad: a root-level Go workflow runs from the repository root and assumes a root `go.mod`.

### 6. Tests Required

- For each changed Go service, run `go test ./...` from the service directory.
- For each changed Go service, run `go build ./cmd/server` from the service directory.
- For QA, also run `go build ./cmd/agent` from `services/qa`.
- Run `git diff --check` before commit.

### 7. Wrong vs Correct

Wrong:

```yaml
with:
  go-version: '1.25.x'
  cache-dependency-path: services/${{ matrix.service }}/go.sum
```

Correct when not every service has `go.sum`:

```yaml
with:
  go-version: '1.25.x'
  cache-dependency-path: services/${{ matrix.service }}/go.mod
```

---

## Go Migration CI Baseline

### 1. Scope / Trigger

- Trigger: adding or changing repository CI for service-owned PostgreSQL migrations under `services/*/migrations`.

### 2. Signatures

- Workflow: `.github/workflows/go-migrations.yml`.
- Events: `pull_request` and `push` to `develop` with path filters for service migrations, service README files, the workflow file, and technology decisions.
- Matrix key: `service`, with one entry for each landed Go service that owns SQL migration files.

### 3. Contracts

- PostgreSQL CI image: `postgres:16-alpine`.
- Goose command: `go run github.com/pressly/goose/v3/cmd/goose@v3.27.1 -dir migrations postgres "$DATABASE_URL" up`.
- Working directory: `services/${{ matrix.service }}`.
- Migration filenames must match ordered snake_case names such as `0001_create_users.sql`.
- SQL migrations must include `-- +goose Up`; `-- +goose Down` is optional only for forward-only slices.

### 4. Validation & Error Matrix

| Condition | Required response |
|-----------|-------------------|
| Service has `migrations/*.sql` but no matrix entry | Add the service to migration CI before merging. |
| SQL migration has no `-- +goose Up` annotation | Add the annotation so goose can parse it. |
| Migration filename lacks an ordered prefix | Rename to `0001_<snake_case_summary>.sql` or the next ordered prefix. |
| README goose command version differs from CI | Update both to `v3.27.1`. |

### 5. Good/Base/Bad Cases

- Good: `services/auth` migration applies against an empty PostgreSQL database with `goose@v3.27.1`.
- Base: a forward-only migration has `-- +goose Up` and no down section.
- Bad: a service relies only on PostgreSQL Docker init scripts, or README says `goose` without a pinned version.

### 6. Tests Required

- Run migration apply validation for every matrix service or rely on the PR workflow when local PostgreSQL is unavailable.
- Run `git diff --check` before commit.
- Run service-local Go tests when migration files or repository code changed.

### 7. Wrong vs Correct

Wrong:

```bash
goose -dir migrations postgres "$DATABASE_URL" up
```

Correct:

```bash
go run github.com/pressly/goose/v3/cmd/goose@v3.27.1 -dir migrations postgres "$DATABASE_URL" up
```

---

## Scenario: Local Integration Compose Baseline

### 1. Scope / Trigger

- Trigger: adding or changing `deploy/docker-compose.yml`, local demo seed data,
  infrastructure image tags, Docker image source overlays, service ports,
  readiness wiring, service tokens, or `.env.example` files for the backend
  integration environment.
- Applies to `deploy/**`, host-run migration wiring, local seed docs, Docker
  policy/environment scripts, and documentation that tells frontend or new
  contributors how to start services.

### 2. Signatures

- Compose entrypoint:
  - `CONFIG_SECRET_FILE=.env.example ./scripts/config/load-profile.sh --print-compose-env`
  - `docker compose -f deploy/docker-compose.yml --env-file .local/config/dev.env config --quiet`
  - `docker compose -f deploy/docker-compose.yml --env-file .local/config/dev.env config --services`
- Runtime entrypoint:
  - `cp .env.example .env.local`
  - `./scripts/local/check.sh`
  - `./scripts/local/check.sh`
  - `./scripts/local/start.sh`
  - `cd apps/web && bun install && bun run dev`
- Default Compose services:
  - `postgres`
  - `redis`
  - `minio`
  - `minio-init`
  - `elasticsearch`
- Public browser/API entrypoint after host-run services start:
  - `http://localhost:8080` through gateway.
- Operational routes:
  - `GET /healthz`
  - `GET /readyz`

### 3. Contracts

- The root local Compose path stays infrastructure-only. Business services and
  the Knowledge runtime API/worker run on the host. Local Elasticsearch is part
  of the default Compose infrastructure for Knowledge runtime doc-engine
  support.
- Docs must provide host-run commands for Auth, File, Knowledge, AI Gateway,
  QA, Document, Gateway, and frontend.
- Frontend and browser-facing documentation must route traffic through gateway;
  internal service ports may be exposed only for local debugging.
- `config/` is the single default local configuration source for committed
  non-sensitive defaults and profile overrides. Root `.env.example` is the
  local secret template; `.env.local` is untracked local input.
- `.env.example` values must be local placeholders and must not contain real
  provider keys, tokens, passwords, or production credentials.
- Startup scripts must use `config/ctl` through `scripts/config/load-profile.sh`
  to render `.local/config/<profile>.env` and `.env.sh` from the selected
  profile and untracked local secret file.
- Knowledge runtime worker timeout decorators must stay active in the default
  host-run profile with `ENABLE_TIMEOUT_ASSERTION=1` in `config/base.yaml`.
  Do not remove this default unless the worker timeout mechanism is replaced
  and the runbook documents the accepted risk or replacement behavior.
- `start.sh` must not prepare or start the retired standalone Parser.
  Knowledge parsing runs through the Knowledge runtime API/worker path.
- Host-run uv package downloads should use `UV_DEFAULT_INDEX` from
  `config/base.yaml`, with official PyPI as the committed default. Mainland
  China mirror usage must be explicit through `check.sh --china` suggestions
  or local untracked env overrides. Runtime dependency/artifact setup must be
  manual; `start.sh` must not run `uv sync` or artifact downloads.
  `ragflow_deps/download_deps.py --china` remains the manual
  fallback. This is separate from Docker registry rewrite and should not be
  handled in Docker policy.
- Runtime Python dependency changes belong under `services/knowledge-runtime`;
  the default local backend startup path must not depend on `services/parser`.
- `start.sh --runtime full` must not run direct `docker build` or `docker run`
  for Elasticsearch. Local Elasticsearch lifecycle belongs to the default root
  Compose infrastructure started by `start.sh`.
- Shared local shell helpers under `scripts/local/lib/` are part of the startup
  contract. Entry scripts may move common behavior there, but
  `scripts/verify_local_seed_contract.py` must read the helper files together
  with the entrypoints so process-group, runtime config, mirror, and proxy
  contracts stay covered.
- Local startup helpers may auto-append `NO_PROXY` only for loopback runtime
  URLs such as `localhost`, `127.0.0.1`, and `::1`. External runtime URLs and
  official download hosts such as PyPI, Docker Hub, `proxy.golang.org`, and
  `sum.golang.org` must keep using the user's shell or daemon proxy
  environment.
- `HF_ENDPOINT=https://hf-mirror.com` must not be active in committed defaults
  or forced by runtime scripts in official-default mode. Mainland China runtime
  model download mirrors are explicit through
  `start.sh --runtime full --china` or local untracked env overrides.
- Host-run Go module downloads should use `GOPROXY` and `GOSUMDB` from
  `config/base.yaml`, with official upstream values as the committed
  default. Mainland China mirror usage must be explicit through
  `check.sh --china` suggestions or local untracked env overrides. This covers
  manual Go tool/service binary builds; it is separate from Docker
  registry rewrite and Knowledge runtime `UV_DEFAULT_INDEX`.
- `check.sh` may print manual `go build` / `go install` suggestions but must not
  execute them. `start.sh` must use `.local/tools` and
  `.local/bin` only; it must not run `go mod download`, `go run module@version`,
  or `go run ./cmd/server`.
- `check.sh` is only the pre-start readiness check. It must not inspect local
  Docker image state with commands such as `docker image inspect`, start
  containers, pull images, or fail because an image is not present yet. Keep
  Docker image handling as manual pull suggestions plus `start.sh --pull never`
  startup failure/status output.
- Host-run backend processes should be started in managed process groups and
  stopped by process group so `go run` or `uv run` wrapper processes do not
  leave child service binaries listening on local ports.
- Local entrypoint scripts under `scripts/local/` must print clear command-line
  status: starting, per-stage success where useful, warnings, final success,
  final failure with the current stage, and next diagnostic hints. Use
  human-scannable colored status labels when stdout/stderr supports color, with
  `NO_COLOR=1` disabling color. Do not rely on `set -e` alone or force users to
  infer failure from missing output.
- After forking host-run backend services, `start.sh` should watch a short
  configurable startup window and report any process group that exits early with
  the corresponding service log tail. This prevents `backend started` from
  hiding immediate `go run`, dependency download, port binding, or config
  failures.
- After startup, `start.sh` should print Docker infrastructure status, host-run
  process group status, and `.local/logs/*.log` location so post-start health is
  visible in the terminal.
- `start.sh` must wait for long-running Compose infrastructure health before
  running host migrations or seed SQL. One-shot infrastructure jobs such as
  `minio-init` must run separately and use their own exit code so a normal
  `Exited (0)` does not skip migrations or seed.
- `start.sh` must not initialize retired vector-store collections. Current
  Knowledge ingestion uses Knowledge runtime and its configured doc engine.
- Compose must include practical health checks for infrastructure containers.
- PostgreSQL health checks must probe TCP readiness, e.g.
  `pg_isready -h localhost -U postgres -d postgres`.
- Compose infrastructure images must keep explicit pinned defaults. If a local
  or enterprise registry is required, expose it through image variables such as
  `POSTGRES_IMAGE`, `REDIS_IMAGE`, `MINIO_IMAGE`,
  `MINIO_MC_IMAGE`, and `KNOWLEDGE_RUNTIME_ELASTICSEARCH_IMAGE`; do not replace
  pinned defaults with `latest`.
- For mainland China Docker usage, prefer `check.sh --china` registry rewrite
  suggestions or local untracked `*_IMAGE` overrides over daemon mirrors and
  proxies. Do not make third-party registries active defaults in
  committed config. Existing daemon mirrors or proxies are acceptable only
  after `python3 scripts/check_docker_environment.py --profile all --clean-env`
  proves their manifest path is healthy.
- `start.sh --china` must apply Docker image rewrites after config rendering and
  update the generated compose env file used for that run, while leaving
  committed config and `.env.local` unchanged.
- The current mainland China Docker registry rewrite uses `docker.1ms.run`.
  The Elasticsearch rewrite is `docker.1ms.run/elasticsearch:8.15.3`.
  `docker.1panel.live/elasticsearch:8.15.3` was not available in local manifest
  probes, and DaoCloud Elasticsearch layer pulls were too slow for the normal
  path; do not switch mirrors without manifest probes and docs/tests updates in
  the same change.
- Local Docker image tags must stay pinned and version-aligned across Compose,
  README/runbooks, and `docs/architecture/technology-decisions.md`.
- PostgreSQL seed scripts may create local/demo data only after service-owned
  migrations have applied from the host with `goose@v3.27.1`.
- Local/demo seed changes should have a deterministic contract checker that
  validates required resource IDs, idempotency markers, documentation coverage,
  host-run migration/seed commands, and forbidden secret/private-content
  patterns.
- File Service runs with PostgreSQL metadata in the local baseline, so it must
  receive `FILE_INTERNAL_SERVICE_TOKEN` or `INTERNAL_SERVICE_TOKEN`. Callers that
  may reach File Service without passing through gateway must send a matching
  `X-Service-Token`.
- AI Gateway runs on the host. It may still report provider readiness as degraded
  while seeded placeholder credentials are present; use `/healthz` for process
  startup and `/readyz` only for real provider readiness.
- Seeded local AI Gateway model profiles must use a host-resolvable base URL,
  currently `http://localhost:11434/v1`; do not use container-only names such as
  `host.docker.internal` in the host-run default path.
- Optional real-provider local AI Gateway bootstrap is controlled only by
  `AI_GATEWAY_LOCAL_SEED_ENABLED=true` plus `AI_GATEWAY_LOCAL_PROVIDER`,
  `AI_GATEWAY_LOCAL_PROVIDER_BASE_URL`, `AI_GATEWAY_LOCAL_PROVIDER_API_KEY`,
  `AI_GATEWAY_LOCAL_CHAT_MODEL`, `AI_GATEWAY_LOCAL_EMBEDDING_MODEL`,
  `AI_GATEWAY_LOCAL_EMBEDDING_DIMENSIONS`, `AI_GATEWAY_LOCAL_RERANK_MODEL`, and
  `AI_GATEWAY_LOCAL_RERANK_TOP_N` in untracked `.env.local`. The bootstrap must
  encrypt provider credentials with the same AES-GCM/HMAC contract as
  `services/ai-gateway/internal/service/crypto.go`, update the three default AI
  Gateway profiles, and append/activate a matching QA `llm_config_versions` row
  so QA requests do not keep sending the placeholder chat model.

### 4. Validation & Error Matrix

| Condition | Required handling |
| --- | --- |
| Compose YAML or env interpolation is invalid | `docker compose ... config --quiet` must fail before merge. |
| Default Compose service list includes anything other than `postgres`, `redis`, `minio`, `minio-init`, or `elasticsearch` | Remove the service or update policy only if the team explicitly changes the Docker boundary. |
| Host migrations or seed run before PostgreSQL/init scripts are ready | Add or restore an infra health wait in `scripts/local/start.sh`; do not rely on plain `docker compose up -d`. Run one-shot init jobs separately from `up --wait` and fail visibly if they exit non-zero. |
| Knowledge runtime/doc-engine env is configured but required runtime provisioning is missing | Fix the runtime dependency guard, startup docs, or smoke setup; do not restore the old Go adapter Qdrant bootstrap as the default Knowledge path. |
| Compose contains `build:` | Remove it; repository root Compose must stay pull-only infrastructure. |
| Docker policy checker fails | Fix the Compose/docs/script regression or update `scripts/check_docker_policy.py` and the runbook in the same PR when the policy intentionally changes. |
| Retired parser paths or env keys reappear in startup scripts | Remove the parser dependency and route document parsing through `services/knowledge-runtime`. |
| Local startup script exits without a success or failure summary | Add or restore explicit command-line status output in the script and local seed contract checker. |
| Go module preflight, migration, or service startup shows `Get "https://proxy.golang.org/...": i/o timeout` | Confirm `config/base.yaml` contains the repository `GOPROXY` / `GOSUMDB` defaults and `.env.local` has not overridden them unexpectedly. If the mirror is unavailable, override only local `.env.local` or enterprise shell config. The startup script should surface failures in the terminal and exit non-zero. |
| Local helper adds PyPI, Docker Hub, `proxy.golang.org`, or an external runtime host to `NO_PROXY` | Restrict automatic `NO_PROXY` additions to loopback hosts and add/restore a helper unit test. Official/external paths must be able to use the user's proxy. |
| `ENABLE_TIMEOUT_ASSERTION` is missing or disabled in the default local profile | Restore `ENABLE_TIMEOUT_ASSERTION=1` in `config/base.yaml` or document the replacement timeout mechanism and accepted risk in the Knowledge runtime runbook. |
| `stop.sh` only kills the wrapper PID | Start host services in a managed process group and stop the whole group; verify the script does not leave child service processes bound to ports. |
| Seeded local AI Gateway profile uses `host.docker.internal` | Replace it with `http://localhost:11434/v1` for the host-run default path. |
| `AI_GATEWAY_LOCAL_SEED_ENABLED=true` updates AI Gateway profiles but QA still sends `local-placeholder-chat` | Update the same overlay to append/activate a QA `llm_config_versions` row for `provider='ai-gateway'`, `profile_id='default-chat'`, and `model_name=AI_GATEWAY_LOCAL_CHAT_MODEL`. |
| Generated provider credential decrypts in SQL but AI Gateway invocation fails with credential decrypt errors | Regenerate credentials with the service crypto contract: `SHA-256(AI_GATEWAY_CREDENTIAL_ENCRYPTION_KEY)` as AES-GCM key and keyed HMAC fingerprint derived from `ai-gateway credential fingerprint v1`; do not invent a bash/OpenSSL-only format. |
| Required Docker image is unavailable locally | Document `docker compose pull <service>` commands and report Docker runtime validation as skipped. |
| Same component appears with multiple Docker tags | Use the documented baseline or record the reason in the implementation document. |
| Compose infrastructure image pull is slow or blocked | Run `./scripts/local/check.sh --china` for pinned `docker.1ms.run` pull suggestions, or use local untracked `.env.local` overrides; if using daemon mirror, prove it with `scripts/check_docker_environment.py`; use Docker daemon proxy only when registry rewrite and mirror paths are unavailable. |
| `check.sh --china` suggests a registry whose Elasticsearch manifest or layer pull is unhealthy | Replace it with a registry whose full image set passes manifest probes and an Elasticsearch pull smoke, then update docs/tests in the same change. |
| File calls return `401 unauthorized` while `file /readyz` is healthy | Verify `FILE_INTERNAL_SERVICE_TOKEN` on file and matching `KNOWLEDGE_SERVICE_TOKEN`, `DOCUMENT_FILE_SERVICE_TOKEN`, or propagated `X-Service-Token` on callers. |
| Gateway readiness fails | Check Redis and Auth first, then search logs by `X-Request-Id`. |
| Auth/document/ai-gateway readiness fails | Inspect PostgreSQL, host-run migration status, and service logs. |
| Seed data insert fails | Keep scripts idempotent with `ON CONFLICT` and verify migrations ran first. |
| AI Gateway `/readyz` returns placeholder/degraded while `/healthz` is ok | Treat service startup as successful; document that real provider credentials are still required for model calls. |

### 5. Good/Base/Bad Cases

- Good: `deploy/README.md` documents infra pulls, default Compose
  Elasticsearch startup, host-run migrations, host-run services, seed data,
  request-id troubleshooting, and common dependency failures; default Compose
  config parses and lists only the five infra services.
- Base: Docker runtime smoke tests are skipped when images are missing, but the
  exact image pull commands and skipped validation are reported.
- Bad: documentation tells new contributors to run business services through
  Compose, `.env.example` contains a real provider API key, or a seed script
  writes data before the owning service migration has run.

### 6. Tests Required

- Run Compose config parsing for the infra baseline.
- Run `docker compose ... config --services` and confirm only the five default
  infra services are present, including `elasticsearch`.
- Run `bash -n scripts/local/check.sh scripts/local/start.sh scripts/local/stop.sh scripts/local/clean.sh scripts/local/lib/*.sh scripts/config/load-profile.sh`
  when local startup scripts change.
- Run `python3 scripts/check_docker_policy.py` and the policy/environment unit
  tests when Compose, Docker docs, image tags, or Docker scripts change.
- Run the local seed contract checker and its unit tests when seed SQL, seed
  docs, startup scripts, Knowledge runtime startup defaults, or host-run Go
  module proxy defaults change.
- Run `python3 -m unittest scripts.tests.test_local_common_helpers` when
  `scripts/local/lib/*.sh` changes proxy, URL, or process helper behavior.
- For AI Gateway local provider overlay changes, test disabled overlay output,
  enabled overlay SQL redaction/no raw key leakage, missing env validation, and
  `start.sh` piping the generated SQL into `psql`.
- Search Docker and docs for duplicate image tags such as `redis:7` vs
  `redis:7-alpine`, and MinIO server/client tags before declaring version
  cleanup complete.
- Run `git diff --check`.
- Run `go test ./...` and `go build ./cmd/server` for changed Go services or
  every service referenced by the integration baseline when feasible.
- For QA, also run `go build ./cmd/agent` when `services/qa/cmd/agent` exists.
- Runtime smoke tests should include `docker compose ps`, Gateway `/readyz`, AI
  Gateway `/healthz`, and at least one host `/readyz` call for each host-run core
  service. AI Gateway `/readyz` is a real-provider readiness check and may return
  `503 degraded` for seeded placeholder credentials.

### 7. Wrong vs Correct

#### Wrong

```text
frontend -> http://localhost:8083/internal/v1/knowledge-bases
.env.example -> real provider API key
document worker -> file /internal/v1/files without X-Service-Token
seed SQL -> inserts model_profiles before ai-gateway migrations
AI_GATEWAY_LOCAL_* seed -> updates default-chat only; QA active LLM remains local-placeholder-chat
root Compose -> business service or unapproved build entry
```

#### Correct

```text
frontend -> gateway http://localhost:8080/api/v1/knowledge-bases
config/base.yaml + .env.example -> non-sensitive defaults plus local placeholder secrets only
document worker -> file /internal/v1/files with DOCUMENT_FILE_SERVICE_TOKEN
seed SQL -> idempotent local/demo data after host-run service migrations
AI_GATEWAY_LOCAL_* overlay -> updates chat/embedding/rerank profiles and activates matching QA LLM config
root Compose -> postgres, redis, minio, minio-init, elasticsearch only
```

---

## Scenario: Environment-Gated Cross-Service Smoke

### 1. Scope / Trigger

- Trigger: adding a smoke test that calls another service or an optional external
  dependency such as AI Gateway, a model provider, object storage, or a parser
  runtime.
- Applies when ordinary unit CI must remain deterministic but operators still
  need an executable proof of the real service client and runtime configuration.

### 2. Signatures

- Name the opt-in gate `<CALLER>_<DEPENDENCY>_SMOKE`; the enabled value is `1`.
- Keep the test beside the real service client and expose one explicit command,
  for example:

```bash
QA_AI_GATEWAY_SMOKE=1 go test ./internal/platform/modelclient \
  -run '^TestAIGatewaySmoke$' -count=1 -v
```

- Reuse the caller's normal endpoint, credential-header, token, profile/model,
  and timeout environment keys instead of inventing parallel smoke-only keys.

### 3. Contracts

- With the gate unset, the test must call `t.Skip` before reading credentials or
  making network requests.
- With the gate enabled, missing required endpoint/profile/token configuration
  must fail with an actionable message that names keys, never values.
- The positive path must use the production service client and assert a minimal
  normalized response.
- Negative probes should stop at the dependency boundary when possible, such as
  invalid service-token or missing-profile checks, to avoid provider cost and
  nondeterministic side effects.
- Missing-resource probes must use a request-scoped unique identifier such as
  `requestID + "-missing-profile"`; do not append a predictable suffix to a
  configured valid resource ID because that name can already exist and reach a
  real provider.
- Generate a request ID for cross-service log correlation. Do not log tokens,
  provider keys, raw downstream bodies, prompts, document text, or vectors.
- Controlled fake providers are preferred. Real providers run only when an
  operator explicitly supplies the gate and credentials.

### 4. Validation & Error Matrix

| Condition | Required behavior |
| --- | --- |
| Smoke gate unset | `SKIP`; ordinary `go test ./...` remains green and offline. |
| Gate set but token/profile/endpoint missing | Fail before network I/O with actionable key names. |
| Dependency authentication rejected | Assert the caller's normalized unauthorized/dependency classification; discard raw body. |
| Selected profile/resource missing | Use a request-scoped missing ID, assert the caller's normalized not-found/dependency classification, and verify a controlled fixture receives no provider call. |
| Provider or dependency unavailable | Fail with request ID and safe configuration hints, not endpoint secrets or provider body. |
| Positive response malformed | Fail on stable normalized fields such as role, finish reason, ID, or result count. |

### 5. Good/Base/Bad Cases

- Good: an opt-in test uses the QA model client, a controlled AI Gateway profile,
  request-ID correlation, positive response assertions, and token/profile
  negative probes whose missing profile ID is scoped to that request.
- Base: a real-provider smoke is documented but skipped until an operator sets
  all required variables.
- Bad: normal CI always calls an external model, a missing-profile probe derives
  `validProfileID + "-missing"`, a test imports another service's `internal`
  packages, or a failure prints raw provider output or a credential.

### 6. Tests Required

- Run the targeted test with the gate unset and assert it reports `SKIP`.
- Exercise the enabled positive and negative paths with a controlled fixture
  before relying on a real provider; assert the missing-resource probe does not
  reach the controlled provider.
- Run the caller service's full unit tests and required builds with the gate
  unset.
- Run `git diff --check` and verify the documented command and link targets.

### 7. Wrong vs Correct

#### Wrong

```go
func TestProviderSmoke(t *testing.T) {
    token := os.Getenv("PROVIDER_API_KEY")
    t.Logf("calling provider with token %s", token)
    missingProfileID := validProfileID + "-missing"
    callProviderDirectly(token)
}
```

#### Correct

```go
func TestAIGatewaySmoke(t *testing.T) {
    if os.Getenv("QA_AI_GATEWAY_SMOKE") != "1" {
        t.Skip("set QA_AI_GATEWAY_SMOKE=1 to run the smoke")
    }
    requestID := newRequestID()
    missingProfileID := requestID + "-missing-profile"
    client := newRuntimeServiceClientFromEnvironment(t)
    result := callWithRequestID(t, client)
    assertNormalizedResult(t, result)
    assertMissingProfileDependencyError(t, client, missingProfileID)
}
```

## Scenario: Gateway Owner Route Smoke

### 1. Scope / Trigger

- Trigger: adding or changing an env-gated smoke that proves Gateway can
  authenticate through Auth/session cache and proxy a real owner-service route.
- Applies to smoke tests for Gateway public `/api/v1/**` routes whose business
  state is owned by Knowledge, QA, Document, AI Gateway admin routes, or another
  backend owner service.

### 2. Signatures

- Gate name: `GATEWAY_<OWNER>_OWNER_SMOKE=1`, for example
  `GATEWAY_KNOWLEDGE_OWNER_SMOKE=1`.
- Command shape:

```bash
GATEWAY_KNOWLEDGE_OWNER_SMOKE=1 \
GATEWAY_BASE_URL=http://127.0.0.1:8080 \
<OWNER>_SERVICE_BASE_URL=http://127.0.0.1:<port> \
GATEWAY_SMOKE_USERNAME=admin \
GATEWAY_SMOKE_PASSWORD='local-password' \
go test ./internal/integration -run '^TestGatewayKnowledgeOwnerRouteSmoke$' -count=1 -v
```

- The owner route must be called through Gateway, not by directly calling the
  owner service.

### 3. Contracts

- With the gate unset, the smoke must skip before reading credentials, endpoints,
  or dependency env.
- With the gate enabled, missing env must fail with key names only.
- The smoke must precheck the owner route's required runtime dependencies before
  the Gateway assertion, such as owner service `/readyz`, PostgreSQL, Redis,
  File, Knowledge runtime/doc engine, or AI Gateway depending on route scope.
- The smoke must first call the Gateway route with spoofed `X-User-*` headers
  and no Bearer token, then assert `401 unauthorized`.
- The positive path must create a real Gateway session through
  `POST /api/v1/sessions`, use the returned Bearer token, and call the owner
  route through Gateway with a request id.
- The positive path must use an observable owner-context assertion, such as
  creating a resource through Gateway and verifying `createdBy` equals the real
  session user.
- The positive path should also send a spoofed inbound `X-User-*` header;
  Gateway must ignore it and inject authenticated context from Auth/session
  cache.
- The smoke must not import Gateway/Auth internals or another service's
  `internal` package. Use HTTP/TCP/database boundaries only.
- Do not print passwords, bearer tokens, session hashes, service tokens, DSNs,
  downstream raw bodies, document text, object keys, or vector payloads.

### 4. Validation & Error Matrix

| Condition | Required behavior |
| --- | --- |
| Smoke gate unset | `SKIP`; ordinary service `go test ./...` remains offline-safe. |
| Required env missing | Fail before network I/O with actionable key names only. |
| Parser/File/Redis/PostgreSQL or owner `/readyz` unavailable | Fail during precheck with the dependency name. |
| Spoofed `X-User-*` headers without Bearer token | Gateway returns `401 unauthorized` with the request id. |
| Gateway session creation fails | Fail without printing credentials or token material. |
| Authenticated owner route returns non-2xx | Fail with status and request id, then inspect Gateway/owner logs by request id. |
| Authenticated route records spoofed owner context | Fail when `createdBy` or an equivalent owner field differs from the real session user. |
| Response envelope malformed | Fail on stable fields such as `data`, `page`, `requestId`, owner fields, or owner-specific IDs. |

### 5. Good/Base/Bad Cases

- Good: a smoke starts the documented local stack, checks owner dependencies,
  rejects a spoofed unauthenticated request, creates a real session, calls the
  public Gateway route with spoofed inbound user headers, and asserts request-id
  propagation plus an observable owner field such as `createdBy`.
- Base: the smoke is documented but skipped locally because a required image or
  seeded credential is unavailable; PR verification records the exact blocker.
- Bad: a smoke directly calls the owner service with `X-User-Id`, trusts a
  caller-supplied auth header, imports Gateway/Auth internals, or requires
  ordinary CI to run the full local Compose stack.

### 6. Tests Required

- Run the targeted smoke with the gate unset and assert it reports `SKIP`.
- When dependencies are available, run the enabled smoke and record the exact
  command.
- Confirm owner dependency prechecks run before the authenticated Gateway route.
- Confirm the spoofed unauthenticated route returns `401`.
- Confirm the authenticated route ignores spoofed `X-User-*` headers by checking
  an owner field such as `createdBy` against the real session user.
- Run the changed service's `go test ./...` and `go build ./cmd/server` with the
  gate unset.
- Run Compose config parsing when the smoke docs reference local Compose
  startup commands.
- If the route depends on local images, document image build/cache prerequisites
  and record missing-image blockers in PR verification.

### 7. Wrong vs Correct

#### Wrong

```go
func TestOwnerRouteSmoke(t *testing.T) {
    req := newRequest("http://localhost:8083/internal/v1/knowledge-bases")
    req.Header.Set("X-User-Id", "admin")
    callOwnerDirectly(req)
}
```

#### Correct

```go
func TestGatewayKnowledgeOwnerRouteSmoke(t *testing.T) {
    if os.Getenv("GATEWAY_KNOWLEDGE_OWNER_SMOKE") != "1" {
        t.Skip("set GATEWAY_KNOWLEDGE_OWNER_SMOKE=1 to run the smoke")
    }
    assertOwnerDependenciesReady(t)
    assertGatewayRejectsSpoofedHeadersWithoutBearer(t)
    token := createGatewaySession(t)
    assertGatewayKnowledgeBases(t, token)
}
```

---

## Scenario: Code Scanning Security Boundary Fixes

### 1. Scope / Trigger

- Trigger: fixing CodeQL or code-scanning findings for command execution, SSRF,
  allocation size, integer conversion, or credential fingerprinting in Go
  services.
- Applies to service-local config loaders, platform clients, repositories,
  credential encryption/fingerprint helpers, and tests that prove the alert is
  closed by a real boundary rather than by suppressing the alert.

### 2. Signatures

- Commands must use `exec.CommandContext(ctx, executable, args...)` with a fixed
  executable string and argument vector.
- Internal AI Gateway callers use service-owned env keys such as
  `AI_GATEWAY_URL` and `DOCUMENT_AI_GATEWAY_URL`.
- Repository pagination/cursor helpers convert to SQL `int32` params only after
  explicit range checks.
- Credential lookup fingerprints use a keyed HMAC helper; compatibility field
  names such as `FingerprintSHA256` may remain when the stored value changes.

### 3. Contracts

- Do not execute user-controlled strings through `/bin/sh -c`, PowerShell
  `-Command`, `cmd /c`, or equivalent shell interpretation.
- Allowlisted stdio or diagnostic commands must reject whitespace,
  control characters, NULs, shell metacharacters, redirects, pipes, expansions,
  and non-allowlisted executable names before process start. LLM-exposed
  diagnostic command tools must be path-free; file reads, writes, and edits must
  go through workspace-bounded file tools instead of path-capable executables.
- MCP stdio is package-test-only. Runtime MCP configuration must reject stdio
  and use Streamable HTTP; package tests that exercise stdio must map validated
  test configuration to an exact code-owned command spec with literal
  executable and argument values. Do not pass configured executable or argv
  values directly into `exec.Command`.
- Internal service URLs must be absolute `http` or `https`, contain no userinfo,
  query, or fragment, and restrict paths to the expected internal endpoint or
  base path.
- Trusted internal hosts are explicit service DNS names documented by the
  caller plus loopback/local development hosts; raw private, link-local,
  multicast, unspecified, or public escape targets are not a safe default.
- Allocation sizes derived from request/provider data must be capped by a
  service-level validated maximum before allocating slices or maps.
- `int` to `int32` conversion must reject negative values and overflow,
  including computed offset overflow; do not silently clamp caller input.
- Fingerprints over provider API keys or similar secrets must use keyed HMAC
  with domain separation, not bare SHA-256 over the secret.

### 4. Validation & Error Matrix

| Condition | Required behavior |
| --- | --- |
| Command contains shell syntax or a path-capable executable | Reject before `exec.CommandContext`; no process starts. |
| Runtime MCP configuration uses stdio, or a test stdio command spec is not allowlisted | Return validation/configuration error. |
| Internal URL includes credentials, query, fragment, or wrong path | Reject at config loading and client construction. |
| Internal URL uses raw private/link-local/public host outside the allowlist | Reject as untrusted target. |
| Allocation limit exceeds service maximum | Cap to the validated maximum before allocation or reject the request. |
| Pagination, offset, or cursor is negative/over `math.MaxInt32` | Return a validation error before building SQL params. |
| Credential fingerprint equals bare SHA-256 of the secret | Fail tests; replace with keyed HMAC. |

### 5. Good/Base/Bad Cases

- Good: a QA diagnostic tool parses a simple `echo hello` command into an
  allowlisted executable plus args, starts it without a shell, and rejects
  `echo hello; uname -a`.
- Base: `httptest.Server` and loopback AI Gateway URLs remain accepted for
  local tests while credentialed URLs and wrong internal paths fail.
- Bad: a repository casts `(page - 1) * pageSize` to `int32`, a client trusts any
  `http://10.0.0.5/...` URL from env, or a secret fingerprint is
  `hex(sha256(apiKey))`.

### 6. Tests Required

- Add table-driven unit tests for allowed and rejected command values, including
  shell metacharacters, non-allowlisted executables, and non-allowlisted MCP
  command specs.
- Add URL validator tests for malformed, credentialed, wrong-path, public,
  private/link-local, loopback, and explicit service-DNS cases.
- Add integer boundary tests for negative, valid maximum, and overflow values,
  including computed offset overflow.
- Add allocation boundary tests where the effective allocation cap can differ
  from caller/provider supplied counts.
- Add fingerprint tests for determinism with the same key, key separation, and
  non-equality with bare SHA-256.
- Run the changed service's `go test ./...`, required `go build ./cmd/server`,
  and any service-specific additional build such as QA `go build ./cmd/agent`.

### 7. Wrong vs Correct

#### Wrong

```go
cmd := exec.CommandContext(ctx, "/bin/sh", "-c", request.Command)
offset := int32((page - 1) * pageSize)
fingerprint := sha256.Sum256([]byte(apiKey))
```

#### Correct

```go
spec, err := validateCommand(request.Command)
if err != nil {
    return err
}
cmd := exec.CommandContext(ctx, spec.Executable, spec.Args...)

limit, offset, err := paginationInt32(page, pageSize)
if err != nil {
    return err
}

fingerprint := hmacSHA256(fingerprintKey, []byte(apiKey))
```

---

## Forbidden Patterns

- Root-level Go module used to build all microservices together.
- Cross-service imports from `services/<other-service>/internal/...`.
- HTTP handlers that contain business rules, SQL, runtime doc-engine queries, or MinIO object logic.
- Unbounded goroutines without cancellation.
- HTTP clients without timeouts.
- SQL built by concatenating user input.
- Panics for expected business errors.
- Global mutable state for request-scoped data.
- Logging secrets, tokens, raw credentials, or full sensitive payloads.

---

## Required Patterns

- Pass `context.Context` through request, service, repository, and infrastructure calls.
- Use graceful shutdown for HTTP servers.
- Validate environment configuration at startup.
- Keep service dependencies explicit in constructors.
- Keep business workflows in `internal/service/`.
- Keep persistence in `internal/repository/`.
- Use stable API response shapes: project-owned JSON APIs use
  `{ data, requestId }` / `{ error }`; AI Gateway model invocation success
  responses use OpenAI-compatible shapes as documented in
  `docs/services/ai-gateway/api/internal.openapi.yaml`.
- Add or update tests for changed business logic.

---

## Testing Requirements

Use a risk-based test strategy:

| Change Type | Required Coverage |
|-------------|-------------------|
| Pure functions or validators | Unit tests |
| Service business workflows | Unit tests with mocked repositories/clients |
| Repository SQL changes | Integration tests when database test tooling exists |
| HTTP handlers | Handler tests for status code and response shape |
| Cross-service client changes | Contract-style tests or mocked HTTP server tests |
| Migration changes | Migration validation once tooling exists |

Test naming:

- Use `Test<FunctionOrBehavior>`.
- Prefer table-driven tests for validators, mappers, and policy decisions.
- Test expected errors explicitly with `errors.Is` or `errors.As`.

---

## Configuration Quality

- Read configuration from environment variables in `internal/config` using an
  `envconfig`-style structured loader.
- Validate all required variables at startup.
- Keep defaults safe for local development only.
- Do not read environment variables throughout business logic.
- Document required variables in service README or deployment docs.

---

## Code Review Checklist

Reviewers should check:

- [ ] Does the change stay within the correct service boundary?
- [ ] Are HTTP request and response contracts stable?
- [ ] Are errors classified and returned through the standard error shape?
- [ ] Is sensitive data excluded from logs and responses?
- [ ] Are database changes represented by service-owned migrations?
- [ ] Are Redis/runtime doc-engine/MinIO responsibilities owned by the correct service?
- [ ] Are timeouts and context cancellation handled for external calls?
- [ ] Do tests cover the changed behavior?
- [ ] Can the service still run `go test ./...` and `go build ./cmd/server` independently?

---

## Common Mistakes

- Adding shared code before three services actually need the same behavior.
- Testing only handlers while business rules remain untested.
- Treating Docker Compose startup as a substitute for service-level tests.
- Allowing the gateway to accumulate all business logic.
