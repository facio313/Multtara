# 🌊 퐁당 PongDang — 물 여행 플랫폼

> **“오늘 가장 가기 좋은 물 여행지를 찾아준다.”**

대한민국의 바다, 계곡, 온천, 호수, 폭포, 갯벌 등 물 여행지를 모아 위치뿐 아니라 **지금의 물 상태, 언제 가면 좋은지, 어떻게 즐길지**를 안내합니다. 현재 제품은 강릉 우선 MVP이며 전국 확장이 가능한 데이터 구조를 사용합니다.

공식 데이터가 없거나 오래됐을 때는 안전을 추정하지 않고 `UNKNOWN`으로 보류합니다. 고정 관광 콘텐츠와 시연용 값은 `DEMO`로 구분하며, 현장 표지·구조요원·운영기관 안내가 앱보다 항상 우선합니다.

## 핵심 3축

| 축 | 기능 | 설명 |
|---|---|---|
| **지금** | Water Index | 활동 적합도(0~100 또는 없음), 안전 상태, 데이터 신뢰도를 분리 |
| **언제** | Water Forecast | 7일 예보와 방문 시점 탐색 |
| **직접 눈으로** | Water Twin + 워터뷰 | 지도 기반 장소 탐색과 검증된 영상 연결 상태 |

## 기술 스택

- Backend: Python 3.11+ (운영 이미지 3.12) · Django 5.2 LTS · Django REST Framework
- Frontend: React 19 · Vite 8 · React Router · Zustand · Axios
- Database: PostgreSQL 15
- Infrastructure: Docker · Docker Compose · Nginx · Gunicorn
- Target: Raspberry Pi 5 (`linux/arm64`)

## 구현된 경험

- 강릉 중심 활동별 Water Index와 전국 확장형 물 여행지 카탈로그
- Kakao Maps 키가 있으면 실제 지도를 사용하고, 없거나 실패하면 접근 가능한 Water Twin 개념도와 목록으로 전환
- 지역·활동별 7일 예보와 차트와 의미가 같은 접근성 표
- 실제 라이브와 데모 포스터를 혼동하지 않는 워터뷰
- 5단계 취향 온보딩, Django session 기반 계정·프로필, 검증 여권·에코 기록
- 안전·운영·동행 조건을 먼저 적용하는 설명 가능한 추천 API와 명시적 데모 폴백
- 실제 route matrix를 쓰는 물류 초안, 만료 근거 재검증, 계정별 저장 일정
- 계정 소유자만 조회·수정·삭제할 수 있는 여행 추억 기록
- 바다·온천·계곡·갯벌 상세, 출처·갱신시각·방법론·안전 reason code 표시
- 320px급 모바일부터 대형 데스크톱까지 반응형 내비게이션과 safe-area 대응

화면은 관측 상태를 `LIVE`/`STALE`/`NO DATA`/`DEMO`/`ERROR`로 구분합니다. `STOP`과 `UNKNOWN`은 숫자 점수로 바꾸지 않으며 추천 후보에서도 제외합니다.

## 빠른 시작

### 사전 준비

- Docker와 Docker Compose
- Git

### 개발 환경

```bash
git clone https://github.com/facio313/Multtara.git
cd Multtara
git checkout -b codex-local-auth
cp .env.example .env
# .env에 실제 branch와 local mode를 반영하고 개발용 DB 비밀번호와
# 50자 이상의 무작위 SECRET_KEY를 입력
# PORTFOLIO_BRANCH=codex-local-auth
# PORTFOLIO_AUTH_MODE=local
# PONGDANG_SSO_ENABLED=False
# VITE_SSO_ENABLED=false

scripts/portfolio-auth-mode.sh exec -- \
  docker compose -f docker-compose.yml -f docker-compose.dev.yml up --build
```

- Frontend: `http://localhost:5173`
- Backend: `http://localhost:8000`
- Liveness: `http://localhost:8000/api/health/`

브라우저에는 `VITE_API_BASE_URL`과 도메인 제한을 적용한 `VITE_KAKAO_MAP_KEY`만 전달합니다. 공공데이터 키, Django `SECRET_KEY`, DB 비밀번호는 서버 전용입니다. 변수 이름과 역할은 [.env.example](.env.example)을 참고하세요.

### 운영 Compose

```bash
# Git tag release가 만든 bundle을 Raspberry Pi로 전달한 뒤 실행합니다.
sudo ./scripts/pi-setup.sh \
  --target /opt/pongdang \
  --deploy-user pongdang \
  --project-name pongdang

sudo -u pongdang /opt/pongdang/scripts/pi-deploy.sh deploy \
  --target /opt/pongdang \
  --release-file /path/to/release.env
```

운영 장치에서 직접 build하지 않습니다. Release workflow가 생성한 `linux/arm64`
GHCR digest image, provenance, SBOM, checksum manifest만 배포합니다. 최초 설정,
필수 외부 입력, image rollback, PostgreSQL backup/restore와 분리 복구 drill은
[운영 runbook](docs/operations-runbook.md)을 따릅니다.

`bonifacio.work`에서는 전용 target `/opt/pongdang-multtara`, Compose project
`pongdang-multtara`, loopback `127.0.0.1:5182`와 독립 PostgreSQL volume을 사용합니다.
`origin/main` 이력에 이미 포함된 commit에 붙은 tag만 release할 수 있습니다.
workflow revision과 tag commit이 정확히 일치해야 하며, tag release가 digest를 만든
뒤 제한된 서버 명령으로 자동 배포합니다. 공개 prefix는 `/multtara/`입니다. 다른
프로젝트의 `cksDB`나 네트워크를 공유하지 않습니다.

인증 모드는 Git branch에 묶입니다. `scripts/portfolio-auth-mode.sh`가 명시된
`PORTFOLIO_BRANCH`, `GITHUB_REF_NAME`, 현재 Git branch 순으로 판정하며 `main`과
`dev`는 항상 `sso`, 나머지는 `local`입니다. 명시한 `PORTFOLIO_AUTH_MODE`나 기존
backend/Vite SSO flag가 다르면 build/startup이 중단됩니다. 로컬 checkout만 Git
자동 감지를 사용하고 CI·image build·container에는 branch를 명시 주입합니다.
`npm run dev`와 `npm run preview`는 local mode를 명시적으로 assert하므로
`main`/`dev`에서는 즉시 실패하고 다른 개발 branch에서만 실행됩니다.

Vite 인증 설정은 정적 번들에 build-time으로 고정됩니다. 최종 Nginx image의
`PORTFOLIO_BRANCH`/`PORTFOLIO_AUTH_MODE` 환경값과 OCI label은 배포 provenance
확인용일 뿐 runtime 전환 스위치가 아닙니다. 인증 모드를 바꾸려면 image를 다시
build해야 하며 `main`/`dev` image는 항상 신뢰할 수 있는 SSO edge 뒤에 둡니다.
두 image는 정규화한 branch와 mode를 `/etc/portfolio-auth-build`의 mode-0444 두
줄로 고정합니다. Django settings와 frontend Nginx resolver entrypoint가 runtime
canonical pair와 비교하므로 container 환경변수 override로 build 계약을 바꿀 수
없습니다.

운영 계정은 `bonifacio.work/sso/`의 Authelia 통합 로그인을 사용합니다. 호스트
Nginx가 인증한 `Remote-*` 헤더와 퐁당 전용 `X-Portfolio-Edge-Secret`만 loopback
원본에 전달하며, Django는 불변 `sso_subject`에 정확히 결합한 뒤 전용
`pongdang_sessionid` 세션으로 교환합니다. 최초 연결은 중복 없는 이메일 한 건에만
허용되고 이후 모든 인증 API 요청은 현재 SSO subject와 엣지 시크릿을 다시
검증합니다. 운영에서는 별도 회원가입·비밀번호
로그인/변경·계정 삭제가 비활성화되고 로그아웃은 중앙 `/sso/logout`으로
연결됩니다. main/dev가 아닌 개발 branch에서 canonical mode와 두 adapter를
`local`/`false`로 맞추면 중앙 SSO 없이 기존 로컬 계정 흐름을 사용할 수 있습니다.

운영 계정 관리는 중앙 `/sso/admin/`에서만 수행합니다. Multtara의 독립 Django
admin은 공개하지 않으며 `/multtara/admin`과 모든 하위 경로는 inner Nginx에서
항상 `404`를 반환합니다. Django 자체도 SSO mode에서는 admin URL을 등록하지 않아
backend에 직접 접근한 `/admin/login/` 요청이 404입니다.

엣지 시크릿은 환경변수보다 host `cks:cks`, mode `0640` 일반 파일을 권장합니다.
`PONGDANG_SSO_EDGE_SECRET_MOUNT`에 절대 호스트 경로를,
`PONGDANG_SSO_EDGE_SECRET_FILE=/run/secrets/pongdang_sso_edge_secret`를 설정하면
파일이 우선됩니다. rootless Docker에서는 host 소유자가 container root로
매핑되므로 `PONGDANG_BACKEND_RUNTIME_USER=pongdang:root`로 앱 UID는 비-root로
유지하고 전용 group-read 권한만 사용합니다.
파일 경로를 설정하지 않은 배포에서만
`PONGDANG_SSO_EDGE_SECRET` 값으로 폴백합니다. 시크릿은 printable ASCII
32~4096바이트이고
심볼릭 링크가 아니어야 하며 브라우저 번들·로그·API 응답에 포함하면 안 됩니다.

백엔드 컨테이너는 외부 포트를 열지 않으며, 프런트 Nginx도 기본적으로 호스트의 `127.0.0.1:8080`에만 바인딩됩니다. Caddy·Cloudflare Tunnel 등 신뢰 가능한 HTTPS 종단 프록시가 이 주소로 전달하도록 구성한 뒤, 공개 HTTPS 도메인에서 다음 경로를 확인합니다.

- `/multtara/api/health/`: 프로세스 liveness
- `/multtara/api/health/ready/`: PostgreSQL readiness
- `/multtara/api/health/integrations/`: provider 작업 이력과 실제 freshness
- `/multtara/api/health/safety/`: verified/non-DEMO 지점의 현재 Water Index 준비 상태

Integrations 성공은 안전 근거 준비를 뜻하지 않습니다. Safety 응답의 aggregate
`counts`·`reason_counts`를 별도로 감시하고, 현재 `CLEAR`가 하나도 없어 반환되는
`503 degraded`를 정상 응답으로 치환하지 않습니다.

백엔드는 기동 전에 마이그레이션과 정적 파일 수집을 수행하고, DB readiness가 통과한 뒤에만 프런트가 준비됩니다. `FRONTEND_BIND_ADDRESS=0.0.0.0`으로 바꾸어 Nginx를 직접 공개한 상태에서 외부 요청의 `X-Forwarded-Proto`를 신뢰하면 안 됩니다. 운영에서는 신뢰 가능한 TLS 종단 프록시만 Nginx 앞에 두고 프런트 원본 포트·PostgreSQL·Gunicorn에 대한 외부 접근을 방화벽으로 차단하세요.

같은 출처 배포에서는 운영 CORS 허용 목록이 기본적으로 비어 있습니다. 프런트와 API를 분리할 때만 `CORS_ALLOWED_ORIGINS`에 쉼표로 구분한 정확한 HTTPS origin을 지정하세요. 사용자 정보, 경로, 쿼리, 프래그먼트, 와일드카드 또는 HTTP 주소가 들어간 항목은 서버 기동 시 거부됩니다.

`collector` 서비스는 최대 4개 worker로 현재·예보 수집, 파생 적합도, 일반·가족
Water Index, daily forecast, retention을 합친 9개 핵심 작업을 실행합니다. `ROUTING_MATRIX_URL`이
있으면 drive/walk/bicycle route snapshot refresh도 24시간 기본 주기로 추가합니다.
설정되지 않은 provider 수집은 안전하게 건너뛰고, 실패한 호출은 이전 관측의
만료시간을 연장하지 않으며 다음 주기에 다시 시도합니다. 간격은 `.env`와 command
기본값을 조정하기 전에 provider 발행주기와 일일 쿼터를 먼저 확인하세요.

| 운영 입력 | 현재 수집 경로 |
|---|---|
| KMA 일반 기상, KHOA 해양 | `collector` 자동 수집 |
| KMA 특보, 낙뢰 clearance, MOE 수질, 지자체 출입·순찰·지정구역·시설 운영 | 자동 수집 미구현. 검증된 공개 근거를 수동 만료형 입력으로 기록 |

미자동 입력은 항목별 운영 담당자와 갱신주기를 정하고 만료 전에 재확인해야 합니다. 담당·주기·유효한 근거 중 하나라도 없으면 해당 안전 조건은 `UNKNOWN`으로 유지되고 추천은 fail-closed됩니다.

## 데이터 수집과 평가

```bash
cd backend

# KMA 격자 관측 또는 예보 수집
python manage.py sync_weather_conditions --mode nowcast

# KHOA 활동지수와, 명시적으로 매핑된 해변의 이안류 자료 수집
python manage.py sync_marine_conditions

# 최신 비데모 관측 융합과 Water Index 평가
python manage.py evaluate_water_conditions

# 기존에 검수한 WaterSpot만 TourAPI 상세정보로 보강
python manage.py sync_tour_spots --dry-run
```

각 명령의 옵션은 `python manage.py help <command>`로 확인합니다. 키나 검수된 장소 매핑이 없으면 값을 추정하지 않으며, 공식 장소 ID를 인근 장소로 공간 보간하지 않습니다.

추가 운영 명령은 다음 역할을 가집니다.

```bash
# HCI/온천 시설/지점별 래프팅 적합도 파생과 lineage 저장
python manage.py derive_suitability_metrics --dry-run

# KMA/KHOA 예보 근거 수집 후 exact KST 12:00 daily projection 평가
python manage.py sync_weather_conditions --mode short
python manage.py sync_forecast_evidence
python manage.py evaluate_daily_forecasts

# 선택형 Valhalla route matrix와 bounded history retention
python manage.py refresh_route_matrix --transport drive --dry-run
python manage.py prune_condition_history --dry-run

# idempotent 강릉 초기 catalog. 관측·점수·예보는 생성하지 않음
python manage.py bootstrap_gangneung_catalog --dry-run
```

전국 공통 자동 API가 없는 입수 허가·순찰·지정구역·시설 운영판정은 공식 근거를 확인한 운영자만 만료시각과 함께 기록합니다. 예시는 형식을 보여줄 뿐이며, 실제 값과 URL은 관할 기관 자료에서 가져와야 합니다.

```bash
python manage.py record_operational_observation \
  --spot 1 \
  --source LOCAL_AUTHORITY \
  --record-id PUBLIC-AUTHORITY-RECORD-ID \
  --source-url https://authority.example/status \
  --observed-at 2026-08-16T12:00:00+09:00 \
  --valid-until 2026-08-16T12:10:00+09:00 \
  --metric official_entry_status=open \
  --metric patrol_status=active \
  --dry-run
```

명령은 공개 HTTPS 근거, timezone이 있는 관측·만료시각, 출처별 허용 지표를 강제합니다. 한 업데이트는 최대 24시간까지만 유효하며 엔진의 더 짧은 지표별 만료시간이 우선합니다. 성인 감독 여부는 사용자 요청의 세션 문맥이므로 이 경로로 저장할 수 없습니다. 검증 후 `--dry-run`을 제거하고 `evaluate_water_conditions`를 다시 실행해야 공개 평가에 반영됩니다.

## 프로젝트 구조

```text
Multtara/
├── backend/
│   ├── config/       # base/dev/prod 설정과 health endpoint
│   ├── apps/         # users, spots, conditions, forecasts, content, trips
│   └── services/     # typed 제공자 경계, 수집/융합, Water Index, 추천
├── frontend/
│   ├── src/          # 페이지, 컴포넌트, 스토어, API 서비스
│   └── nginx.conf    # SPA와 동일 출처 API 프록시
├── docs/             # 방법론 결정 기록
├── docker-compose.yml
├── docker-compose.deploy.yml
└── docker-compose.dev.yml
```

## 공식 데이터 경계

| 기관·서비스 | 사용 범위 |
|---|---|
| 한국관광공사 TourAPI `*Service2` | 이미 검수한 관광지의 상세정보 보강 |
| 기상청 단기예보 | 기온·강수·풍속 등 격자 관측/예보. 특보나 입수 허용으로 해석하지 않음 |
| 국립해양조사원 국가중점 API | 해수욕·서핑·갯벌 공식 활동지수와 명시 매핑된 이안류 |
| 해양수산부·환경 당국 | 수질·수위 등 추가 운영자료. 검증된 연동만 안전 게이트에 사용 |

Water Index 방법론은 [docs/water-index-methodology.md](docs/water-index-methodology.md), 추천 계약은 [docs/recommendation-methodology.md](docs/recommendation-methodology.md)에 기록합니다.

기존 `WaterForecast` 테이블은 초기 개발용 seed/legacy 데이터 모델로만 유지합니다. 증거 기반 조건 파이프라인의 공식 예보로 간주할 수 없으므로 운영 `/api/v1/forecasts/`는 저장 행이 있어도 빈 목록을 반환하고 상세 행을 공개하지 않습니다.

## 주요 API 계약

- `GET /api/v1/forecasts/daily/`: `spot`, `activity`, `participant_profile`,
  `participant_skill_level`, 선택 `start_date`, `days=1..7`에 대해 KST 12:00
  기준 결과를 정확히 요청 일수만큼 반환합니다. 숙련도는
  `unspecified|beginner|intermediate|advanced`이며 구체 숙련도는 서핑에서만
  허용됩니다. 서핑 숙련도를 지정하지 않았거나 KHOA `GrdCn`의 정확한 대응 근거가
  없으면 적합도는 `UNKNOWN/null`입니다. `family` 프로필은 수영에서만 허용되고,
  provider horizon 밖이거나 근거가 만료되어도 `UNKNOWN/null`입니다.
- `POST /api/v1/trips/recommendations/`: 안전·운영·party constraint를 먼저 적용한
  뒤 설명 가능한 적합도와 다양성 순위를 반환합니다.
- `POST /api/v1/trips/itineraries/plan/`: 현재 route evidence만 사용하는 물류
  초안입니다. 저장 행은 route/water provenance, participant profile/skill과
  재검증 시각을 보존합니다. 조회 시 실제 DB의 route snapshot, condition score,
  observation snapshot과 평가 identity를 다시 확인하며 만료·누락·불일치 후에는
  `accepted`/`started`로 전환할 수 없습니다. 가족 수영 일정의 성인 감독은
  저장하지 않는 세션 확인값이므로 응답의 재확인 reason code가 있을 때 상태 전환
  `PATCH`와 함께 `adult_supervision_confirmed=true`를 다시 보내야 합니다.
- `/api/v1/users/`: session/CSRF 계정, 활동·리뷰, 읽기 전용 검증 여권,
  검증 lifecycle이 있는 eco action입니다.
- `/api/v1/content/memories/`: 로그인 사용자 본인만 접근하는 여행 추억 CRUD입니다.

운영 split-origin에서는 `CORS_ALLOWED_ORIGINS`의 정확한 HTTPS origin이
`CSRF_TRUSTED_ORIGINS`와 credential cookie 정책에도 함께 적용됩니다. 같은 출처가
기본이며, browser에 server credential을 전달하지 않습니다.

## 검증

```bash
cd frontend
npm ci
npm run lint
npm test
npm run build

cd ..
scripts/test-ops-config.sh

cd backend
python manage.py check
python manage.py makemigrations --check --dry-run
python manage.py test
```

운영 승격 전에는 실제 장치에서 Compose 설정, `linux/arm64` 이미지 빌드, 마이그레이션, `/api/health/ready/`, 재시작 복구, DB 백업·복구를 확인해야 합니다. PostgreSQL 데이터 볼륨에는 SD 카드보다 SSD를 권장합니다.

## Git 작업 경계

| 경로 | 브랜치 | 소유자 |
|---|---|---|
| `Multtara/` | `main`/`dev` | 사용자 |
| `worktrees/cursor/` | `cursor` | Cursor |
| `worktrees/codex/` | `codex` | OpenAI Codex |
| `worktrees/anthropic/` | `anthropic` | Claude Code |

흐름은 `{tool}-feature-name → {tool} → dev → main`이며 상세 규칙은 [AGENTS.md](AGENTS.md)에 있습니다.

## 라이선스

MIT License
