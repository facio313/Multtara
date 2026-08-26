# Multtara — AGENTS.md

> 물 여행 플랫폼 **퐁당 PongDang**
> 기획: [물따라_기획서.md](물따라_기획서.md) · 플랜: [물따라_플랜.md](물따라_플랜.md)

---

## ⚠️ Agent Authority Boundaries — MUST READ FIRST

### 1. Branch Scope per Agent

Each AI agent may only work within its own tool branch and below.
**`main` and `dev` branches are managed exclusively by the user.**

| Branch | Who controls it |
|--------|----------------|
| `main` | User only |
| `dev` | User only |
| `anthropic` | Claude Code |
| `cursor` | Cursor |
| `codex` | OpenAI Codex |
| `{tool}-{feature}` | Each respective agent |

- Agents **must not** commit, merge, or push to `main` or `dev` without an explicit user request.
- When the user explicitly asks, agents may assist with `main`/`dev` operations.

### 2. Shared Project Information → Always Update `AGENTS.md`

프로젝트 전역 규칙·아키텍처·제약이 바뀌면 **`AGENTS.md`를 갱신**한다.
개별 툴 설정만 고치면 다른 에이전트가 놓친다.

| Type of change | Where to update |
|----------------|----------------|
| Project rules, domain logic, API, constraints | `AGENTS.md` ✅ |
| Claude Code-only settings | `.claude/` |
| Cursor rule formatting | `.cursor/rules/` |
| Codex-only instructions | `AGENTS.md` (Codex reads this directly) |

개별 파일(`CLAUDE.md`, `.cursor/rules/`)은 `AGENTS.md`를 가리키는 thin wrapper다.

---

## Vowline

<!-- vowline:start -->
Always use the skill `vowline` consistently, including for all sub-agents.
<!-- vowline:end -->

| 에이전트 | 전역 스킬 경로 | 활성화 방식 |
|----------|---------------|------------|
| Claude Code | `~/.claude/skills/vowline/` | `~/.claude/CLAUDE.md` 마커 블록 |
| Codex | `~/.agents/skills/vowline/` | `~/.codex/AGENTS.md` 마커 블록 |
| Cursor | `~/.cursor/skills/vowline/` | `.cursor/rules/vowline.mdc` (alwaysApply) |

---

## Stack

| 영역 | 선택 |
|---|---|
| 웹 | React (Vite) · React Router · Zustand · Axios |
| 서버 | Python 3.11+ (운영 3.12) · Django 5.2 LTS · Django REST Framework 3.17 |
| DB | PostgreSQL 16 (production shares the cksDB instance; database/role remain isolated) |
| 인프라 | Docker · Docker Compose · Nginx |
| 배포 | Raspberry Pi 5 (ARM64) |

## Water Index & Recommendation Contract

- Methodology source of truth: [`docs/water-index-methodology.md`](docs/water-index-methodology.md).
- `suitability_score`, `safety_status`, and `confidence` are separate fields. A
  suitability score is never a safety probability.
- Official closure/evacuation, activity-specific hazards, or a required safety
  input that is missing/stale/conflicting must prevent recommendation. `STOP`
  and `UNKNOWN` must never be converted into a low or zero "safe" score.
- Preserve KHOA activity results, provider timestamps, spatial scope, and source.
  Do not interpolate an official score to an unsupported site or label a fallback
  score as official.
- Use the 2026 national-core KHOA APIs (`fcstBeachv2`, `fcstSurfingv2`,
  `fcstMudflatv2`, `ripCurrent`), not the retired legacy oceangrid endpoints.
- Use KMA `VilageFcstInfoService_2.0` for typed weather observations/forecasts
  and TourAPI `*Service2` gateways for tourism POIs. A weather forecast must not
  be interpreted as a warning, lightning clearance, or official access state.
- Where no verified nationwide machine feed exists, trusted operators may use
  `record_operational_observation` only with an approved source class, public
  HTTPS evidence, explicit observation/expiry times, and source-allowed metric
  names. Never store adult-supervision session context as a global observation.
- HCI:Beach may be shown only as coastal climate comfort. Hot-spring scores are
  facility fit, not medical efficacy. Rafting/valley scores require versioned,
  site-specific hydraulic thresholds; never hardcode one nationwide flow limit.
- Recommendation order is: hard safety/operation/accessibility constraints,
  explainable multi-criteria ranking, diversity reranking, then time-window
  itinerary optimization. LLM output may verbalize structured reasons but must
  not invent safety decisions, scores, sources, or routes.

---

## Branch Strategy

### Worktree Layout

| Directory | Branch | AI Tool |
|-----------|--------|---------|
| `Multtara/` (main repo) | `main` | — (release baseline) |
| `Multtara/worktrees/codex/` | `codex` | OpenAI Codex |
| `Multtara/worktrees/cursor/` | `cursor` | Cursor |
| `Multtara/worktrees/anthropic/` | `anthropic` | Claude Code |

### Flow

```
codex-feature-name ──┐
cursor-feature-name ─┤→ {tool} → dev → main
anthropic-feat-name ─┘
```

1. Branch off the tool branch for any new feature:
   ```bash
   git checkout -b cursor-water-index cursor
   ```
2. Merge completed feature back into the tool branch:
   ```bash
   git checkout cursor && git merge cursor-water-index
   ```
3. Merge tool branch into `dev` after validation (user):
   ```bash
   git checkout dev && git merge cursor
   ```
4. Merge `dev` into `main` after full verification only (user).

### Branch-bound authentication

- `scripts/portfolio-auth-mode.sh` is the canonical resolver. Source priority is
  explicit `PORTFOLIO_BRANCH`, then `GITHUB_REF_NAME`, then the current Git
  branch. `main` and `dev` resolve to `sso`; every other branch resolves to
  `local`.
- An explicit `PORTFOLIO_AUTH_MODE` mismatch fails closed.
  `PONGDANG_SSO_ENABLED` and `VITE_SSO_ENABLED` remain compatibility adapters
  and must agree with the canonical mode.
- Local source checkouts may use Git auto-detection. CI, image builds, and
  containers must inject the branch explicitly. Release images and Pi runtime
  are pinned to `main`/`sso` and require the private edge secret.
- `npm run dev` and `npm run preview` intentionally assert `local` and fail
  immediately on `main` or `dev`; use them only from another development
  branch.
- Vite auth is compiled into the static bundle. Final Nginx image environment
  and OCI branch/auth-mode labels are audit provenance only, not runtime
  switches. Rebuild to change mode, and keep every `main`/`dev` image behind the
  trusted SSO edge. Backend and frontend images also bake the normalized branch
  and mode into the mode-0444, two-line `/etc/portfolio-auth-build`; Django
  settings and the Nginx resolver entrypoint reject runtime mismatches.
- Local branches run without central SSO and retain local registration, password
  login, session, password-change, and account-deletion flows.
- Django admin URLs are registered only in local mode. SSO mode must return 404
  for `/admin/login/` even when the backend is reached without inner Nginx.
- `dev` CI validates backend/frontend and builds both ARM64 images with
  `push: false`. Only a release tag already contained in `origin/main` may push
  release images or request the production deployment; CI never publishes a
  `latest` image from `dev`.

### Naming Rules

- Tool branches: `codex`, `cursor`, `anthropic`
- Feature branches: `{tool}-{kebab-case-feature}` — e.g. `cursor-water-index`.
  A slash cannot be used because the resident tool branches already occupy the
  exact Git refs `codex`, `cursor`, and `anthropic`.
- English kebab-case only.

워크트리 재생성:

```bash
./scripts/setup-worktrees.sh
```

---

## Critical Constraints

- **`.env` 커밋 금지**. API 키·DB 비밀번호·`SECRET_KEY` 하드코딩 금지.
- 운영 설정은 50자 이상의 무작위 `SECRET_KEY`, 명시적 `ALLOWED_HOSTS`, PostgreSQL `NAME`/`USER`/`PASSWORD`/`HOST`가 없으면 기동하지 않는다. `ALLOWED_HOSTS=*`와 비-PostgreSQL 운영 DB는 금지한다.
- 사용자 응답 **한국어**. 코드·식별자·커밋은 **영문**.
- 요청 범위만 구현. 모호하면 구현 전 질문.

## Runtime Integration Contract

- `DATA_GO_KR_SERVICE_KEY`, `TOUR_API_KEY`, `KMA_API_KEY`, `KHOA_API_KEY`, `MOE_API_KEY`, DB credentials, and Django `SECRET_KEY` are **server-only**. They must be read by Django and must never appear in frontend source, browser bundles, logs, or API payloads.
- `VITE_KAKAO_MAP_KEY` is the Kakao Maps **public JavaScript key**. Restrict its allowed domains in Kakao Developers. Do not reuse it as a server REST key.
- `VITE_API_BASE_URL` defaults to `/api/v1/`; same-origin production traffic is proxied by Nginx. A separate absolute origin is allowed only for split deployments.
- The `bonifacio.work` portfolio deployment is rooted at `/multtara/`: release
  images use `VITE_APP_BASE_PATH=/multtara/` and
  `VITE_API_BASE_URL=/multtara/api/v1/`, Django uses
  `APPLICATION_BASE_PATH=/multtara`, and the trusted edge strips that prefix
  before forwarding to the loopback origin on `127.0.0.1:5182`.
- On the shared `bonifacio.work` hostname, keep auth cookies isolated as
  `pongdang_sessionid` and `pongdang_csrftoken` with `Path=/multtara/`. The
  frontend XSRF cookie setting must remain identical to Django's CSRF cookie
  name; do not fall back to the generic `sessionid`/`csrftoken` names.
- Production authentication is the portfolio Authelia SSO gate. Release images
  set `PORTFOLIO_BRANCH=main`, `PORTFOLIO_AUTH_MODE=sso`, and
  `VITE_SSO_ENABLED=true`; Compose sets the same canonical pair and
  `PONGDANG_SSO_ENABLED=true`. Any adapter mismatch is fatal. The collector
  retains the canonical SSO mode but uses the explicit `worker` runtime role and
  must never receive the edge secret. The web runtime requires the secret at
  settings startup, and
  the host edge must discard client-supplied identity headers before
  overwriting `Remote-User`, `Remote-Email`, `Remote-Name`, and
  `Remote-Groups`. It also injects the per-app `X-Portfolio-Edge-Secret`; the
  loopback frontend proxy forwards those headers to Django. The exchange binds
  exact `Remote-User` to an immutable unique nullable `sso_subject`, links an
  existing account only once through one unambiguous email match, and never
  treats a username collision as identity. Every SSO-mode authenticated API
  request revalidates the subject, current role, own-app entitlement, complete
  group assertion, and edge secret before accepting the isolated PongDang
  session. Canonical v2 `Remote-Groups` uses the hierarchy-closed role prefix
  `user`, optional `admin`, optional `chief-admin`, then the mandatory
  `portfolio-v2` marker. A non-chief identity carries assigned grants in the
  fixed relative order `access-react`, `access-vue`, `access-dukkeobi`,
  `access-ddit-finalproject`, `access-monitor`, `access-pilgrimage`,
  `access-multtara`, `access-feelmyrythm`, `access-garak` and must include
  `access-multtara`. A chief is universal and carries no grants. Missing,
  duplicate, gapped, reordered, whitespace-bearing, unknown, or own-grant-free
  values fail closed. During central cutover only exact v1 `user`,
  `user,developer`, and `user,developer,admin` remain accepted: the first two
  normalize to an app-entitled `user`, and the last to `chief-admin`.
  `developer` is never a current runtime role or policy label. Bind the native
  session only to subject, current role, and current Multtara entitlement, not
  the full unrelated grant list; nevertheless, validate the current complete
  assertion on every request. SSO roles are hierarchical and never come from
  local staff/superuser/group/permission state.
  Prefer a regular, non-symlink, host-owned mode-0640, 32--4096-byte secret mounted with
  `PONGDANG_SSO_EDGE_SECRET_MOUNT` and read from
  `PONGDANG_SSO_EDGE_SECRET_FILE`; use the direct environment value only when
  no file is configured. A file-backed deployment sets
  `PONGDANG_BACKEND_RUNTIME_USER=pongdang:root` so the application keeps its
  non-root UID while rootless Docker maps the host private group to container
  group 0. Never expose the secret to frontend build/runtime variables, logs,
  API responses, or another
  portfolio application.
  Local registration, password login/change, and account deletion are disabled
  in production SSO mode; central logout is the only browser logout path. The
  portfolio account-management surface is `/sso/admin/`; inner Nginx must
  return 404 for both `/admin` and every `/admin/` subpath so an independent
  Django admin session is never exposed through `/multtara/`.
- `cleanup_sso_legacy_auth --canonical-subject <subject>` is aggregate dry-run
  by default. Explicit `--apply` must lock and project every known domain FK to
  that subject before deleting any unlinked legacy user, abort on an
  unclassified reverse relation, and remove local passwords, role grants,
  sessions, and local admin history. Admin `LogEntry` rows must be deleted with
  an exact aggregate count, never relabeled as actions by the canonical
  subject. `EcoAction.verified_by` is a protected domain invariant and must be
  projected to the canonical subject without changing verification state/time.
  `--apply` must require reviewed expected user/domain-row counts and abort if
  either changes. Never apply it to production without a reviewed
  aggregate and database snapshot; finish with `--check`. Ownership must remain
  an immutable `sso_subject` projection, never an email/username lookup.
- Production CORS is same-origin by default (`CORS_ALLOWED_ORIGINS` is empty). A
  split deployment may opt in only exact HTTPS origins without userinfo, paths,
  queries, fragments, or wildcards; invalid entries must fail startup.
- `frontend/npm run build` remains the Docker/Nginx build. `frontend/npm run build:sites` is the separate Cloudflare Worker-compatible private preview build; keep `.openai/hosting.json` limited to the Sites `project_id` and optional logical bindings, never secrets.
- Production Compose binds frontend Nginx to host loopback by default. Only a trusted HTTPS termination proxy may reach it and supply `X-Forwarded-Proto`; never expose that origin port while trusting client-supplied forwarding headers.
- Backend and collector keep a read-only root filesystem. Gunicorn's optional
  control socket stays disabled because its default `/app/.gunicorn` path is not
  writable; writable runtime state is limited to the declared tmpfs mounts.
- Production Compose runs `run_condition_pipeline` as a separate non-root collector. Missing/failed providers must not extend stale evidence; preserve provider issue cadence and quota-aware defaults when changing its intervals.
- Recommendation requests accept at most 20 preference targets. `party.participant_skill_level` is one of `beginner|intermediate|advanced|unspecified`; adult beginner swimming uses the conservative family profile, and surfing suitability remains unknown unless an explicit skill matches an authoritative KHOA `GrdCn` shape. Unfiltered nationwide candidate sets above the bounded pool require a region.
- Anonymous API throttling uses the connection peer, never caller-supplied forwarding headers. Nginx applies an additional origin-wide limit and a stricter recommendation limit; per-client limits belong at the trusted HTTPS edge.
- The first curated experience is Gangneung-focused, while route and data shapes remain nationwide-ready.
- When a provider or credential is unavailable, keep static tourism content usable and label fallback values as demo/missing data. Never present fixtures as live observations or infer `safe` from absent safety data.
- The legacy `WaterForecast` table may remain available to development, tests,
  and admin workflows, but its read API is fail-closed in production: list
  requests expose no rows and detail requests expose no records. It must never
  be presented as evidence-backed or `LIVE` forecast data.
- Evidence-backed daily forecasts use
  `GET /api/v1/forecasts/daily/?spot=<id>&activity=<activity>&participant_profile=general|family&participant_skill_level=unspecified|beginner|intermediate|advanced&start_date=YYYY-MM-DD&days=1..7`.
  Each result evaluates the exact KST 12:00 target. Unsupported dates, provider
  horizon gaps, missing expiry, and stale evidence stay `UNKNOWN` with null
  score; never interpolate a seven-day value or infer warnings/access from
  ordinary weather forecasts. The `family` profile is valid only for swimming;
  non-swimming queries use `general`. A concrete skill is valid only for
  surfing, and an unspecified skill, missing authoritative KHOA `GrdCn`, or an
  inexact grade-to-skill match keeps surfing suitability `UNKNOWN` with a null
  score.
- `PONGDANG_DERIVED` is the only producer identity for HCI:Beach, verified
  hot-spring facility fit, and site-calibrated rafting flow fit. Every stored
  derivation retains metric-level lineage to original evidence. Request-scoped
  amenity/crowd/temperature preference overlays use `SESSION_CONTEXT`, expire
  immediately, and must never be persisted globally.
- Route matrices come only from an operator-configured credential-free HTTPS
  Valhalla endpoint or an explicit operator import. They expire, are refreshed
  separately for drive/walk/bicycle, and Haversine distance is never an
  executable itinerary travel time. Saved itineraries retain immutable route
  and Water Index evidence plus participant profile/skill and both revalidation
  deadlines. Every referenced route snapshot, condition score, observation
  snapshot, identity, and current methodology must still exist and agree;
  expired, missing, dangling, or mismatched evidence blocks transitions to
  `accepted` or `started` until replanning. Family-swimming adult supervision is
  session-only and is never stored as global evidence; the same transition
  request must explicitly send `adult_supervision_confirmed=true` whenever the
  returned reason codes require reconfirmation.
- Account APIs use Django sessions and CSRF under `/api/v1/users/`. Passports are
  operator/QR/partner-verified and read-only to clients; eco submissions begin
  `pending` and only a staff verifier may establish verified state and time.
  `/api/v1/content/memories/` and saved itineraries are owner-private CRUD.
- `seed_dummy_data` creates only clearly labeled `PONGDANG_DEMO` catalog rows and
  never seeds live observations, scores, or forecasts. Its destructive reset is
  explicitly scoped to those demo rows.
- Pipeline liveness/freshness (`/api/health/integrations/`) and actual current
  safety readiness (`/api/health/safety/`) are separate signals. Retention must
  preserve latest groups, longer STOP/CAUTION audit windows, metric lineage,
  and every evidence row referenced by a saved itinerary.
- Production releases are tag-bound `linux/arm64` GHCR images with immutable
  backend/frontend digests, provenance, and SBOM attestations. Raspberry Pi
  deployment must use `docker-compose.deploy.yml` through `pi-deploy.sh`; never
  build application images on the Pi or deploy a mutable tag. A release tag
  must resolve to the exact workflow revision, and that revision must already
  be an ancestor of `origin/main`; the release workflow fails closed otherwise.
- A tag push builds and verifies release artifacts but must not change the
  server. A successful explicit workflow dispatch with `deploy_to_server=true`
  requests the restricted server command
  `deploy multtara <version> <commit> <backend-digest> <frontend-digest>`.
  The server fixes the GHCR namespace, deploys at `/opt/pongdang-multtara` with
  Compose project `pongdang-multtara`. Production backend and collector attach
  only to the external `cksDB-multtara` database network and use the dedicated
  `pongdang` database/login role; frontend and other app backends never join
  that network. Application deploys
  must never create, restart, or remove the shared `cksDB` service. Local
  development instead gets a self-contained PostgreSQL 16 service and volume
  from `docker-compose.dev.yml`.
- Pi deployment configuration is rooted at a validated marker directory and
  requires Docker Compose 2.24.4 or newer. Preserve the loopback-only origin,
  call the allowlisted cksDB Multtara operator tool for a verified backup before
  upgrades/rollback, and require the explicit restore confirmation contract
  before replacing only the `pongdang` database.
- Before the one-time PG15-to-cksDB cutover, stage
  `state/pre-cksdb-rollback` with `db-migration-rollback.sh` while the original
  `db` service and retained project volume are still present. That bundle is a
  secret, owner-only, checksum-verified emergency artifact and is valid only
  while no Multtara write has reached cksDB. Activating it publishes
  `state/pre-cksdb-rollback.active`; normal shared-DB deploy/backup/restore
  commands must then fail closed until a reviewed forward reconciliation.
- The first shared-DB deployment is gated by the fixed, deployment-user-owned
  mode-0400 `state/cksdb-cutover-ready.env`. Only the migration tool may publish
  it after stopping legacy writers, creating and checksumming the final PG15
  dump, restoring through the pinned cksDB tool, and obtaining byte-identical
  deterministic source/target fingerprints for schemas, constraints, indexes,
  sequence state, and exact per-table row counts. The marker binds the final
  dump SHA-256, both fingerprint SHA-256 values, full cksDB Git revision,
  installed tool SHA-256, and rollback-bundle manifest SHA-256.
- Production deploy and rollback must revalidate that marker, final dump and
  checksum sidecar, the complete rollback manifest plus its separate manifest
  checksum, and the retained PG15 volume identity. The effective production
  service set is exactly `backend`, `collector`, and `frontend`; frontend is
  attached only to the project default network.
