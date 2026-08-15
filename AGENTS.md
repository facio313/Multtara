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
| `{tool}/feature-*` | Each respective agent |

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
| 웹 | React (Vite) · React Router · Zustand · Axios · Kakao Maps (`VITE_KAKAO_MAP_KEY`, 없으면 Leaflet) |
| 서버 | Python 3.11+ · Django · Django REST Framework |
| DB | PostgreSQL 15 |
| 인프라 | Docker · Docker Compose · Nginx |
| 배포 | Raspberry Pi 5 (ARM64) |

공공데이터: `DATA_GO_KR_SERVICE_KEY` (TourAPI / 기상청 / 해양조사원 / 환경부 수질측정망).  
갱신: `python manage.py refresh_conditions --skip-tour` 또는 Compose `refresher` 서비스(`--loop`, 기본 3시간). `fetch_quality`는 수질만.  
수질: NIER `WaterQualityService/getWaterMeasuringList` → `WaterCondition.water_quality_grade`. 자외선: 기상청 `LivingWthrIdxServiceV5/getUVIdxV5` → `WaterCondition.uv_index`. 기존 Water Index 가중치 슬롯에만 반영.  
지도: Kakao Maps JS SDK (`VITE_KAKAO_MAP_KEY`). 키가 없거나 SDK 로드 실패 시 Leaflet.  
추천: `GET /api/v1/spots/recommend/` — 로그인 시 `persona_type` / `mood_state` / `home_region` + Water Index 규칙 랭킹. 비로그인 시 일반 지수 순. LLM 없음.  
컨시어지: `GET /api/v1/spots/concierge/?q=` — 키워드 규칙 랭킹, LLM 없음.  
프로필: `PATCH /api/v1/auth/me/` — `persona_type`(swim, surf, relax, onsen, mudflat, rafting, family, healing) · `mood_state`(healing, release, energetic, calm) · `home_region`.  
일정: `GET`/`POST /api/v1/itinerary/` — POST `start_point`, `transport`(car|public|walk), `is_day_trip`, `party_size`, `budget`, `activity`. 로그인 시 저장.  

인증: Django **세션 쿠키**(httpOnly, SameSite=Lax) + **세션 CSRF**. JWT/로컬스토리지 토큰 없음. 비밀번호 Argon2, 최소 12자, 실패 5회 잠금. 소셜 로그인은 아직 없음.  
Passport: `POST /api/v1/passport/checkin/` (로그인 필요, 장소당 1회). **위도·경도 필수**, 5km 안만 허용. 선택 `eco_action` 또는 `POST /api/v1/passport/eco/`.  
Safety card: `POST /api/v1/safety-card/` (로그인 필요). 컨디션 스냅샷을 저장하고 기기에도 남겨 오프라인으로 본다.

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
codex/feature-name ──┐
cursor/feature-name ─┤→ {tool} → dev → main
anthropic/feat-name ─┘
```

1. Branch off the tool branch for any new feature:
   ```bash
   git checkout -b cursor/water-index cursor
   ```
2. Merge completed feature back into the tool branch:
   ```bash
   git checkout cursor && git merge cursor/water-index
   ```
3. Merge tool branch into `dev` after validation (user):
   ```bash
   git checkout dev && git merge cursor
   ```
4. Merge `dev` into `main` after full verification only (user).

### Naming Rules

- Tool branches: `codex`, `cursor`, `anthropic`
- Feature branches: `{tool}/{kebab-case-feature}` — e.g. `cursor/water-index`
- English kebab-case only.

워크트리 재생성:

```bash
./scripts/setup-worktrees.sh
```

---

## Critical Constraints

- **`.env` 커밋 금지**. API 키·DB 비밀번호·`SECRET_KEY` 하드코딩 금지.
- 사용자 응답 **한국어**. 코드·식별자·커밋은 **영문**.
- 요청 범위만 구현. 모호하면 구현 전 질문.
