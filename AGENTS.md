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
| DB | PostgreSQL 15 |
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
  build application images on the Pi or deploy a mutable tag.
- A successful tag release requests the restricted server command
  `deploy multtara <version> <commit> <backend-digest> <frontend-digest>`.
  The server fixes the GHCR namespace, deploys at `/opt/pongdang-multtara` with
  Compose project `pongdang-multtara`, and uses its own PostgreSQL volume and
  network. It must never attach to or recreate the shared `cksDB` service.
- Pi deployment configuration is rooted at a validated marker directory and
  requires Docker Compose 2.24.4 or newer. Preserve the loopback-only origin,
  take a verified PostgreSQL backup before upgrades/rollback, and require the
  explicit restore confirmation contract before replacing a database.
