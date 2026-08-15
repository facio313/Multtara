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
- 5단계 취향 온보딩, 5개 페르소나, 로컬 저장 기반 프로필과 패스포트
- 안전·운영·동행 조건을 먼저 적용하는 설명 가능한 추천 API와 명시적 데모 폴백
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
cp .env.example .env
# .env에 개발용 DB 비밀번호와 50자 이상의 무작위 SECRET_KEY 입력

docker compose -f docker-compose.yml -f docker-compose.dev.yml up --build
```

- Frontend: `http://localhost:5173`
- Backend: `http://localhost:8000`
- Liveness: `http://localhost:8000/api/health/`

브라우저에는 `VITE_API_BASE_URL`과 도메인 제한을 적용한 `VITE_KAKAO_MAP_KEY`만 전달합니다. 공공데이터 키, Django `SECRET_KEY`, DB 비밀번호는 서버 전용입니다. 변수 이름과 역할은 [.env.example](.env.example)을 참고하세요.

### 운영 Compose

```bash
# 무작위 SECRET_KEY, 명시적 ALLOWED_HOSTS, PostgreSQL 비밀번호,
# HTTPS 종단 프록시를 먼저 구성합니다.
docker compose up -d --build
```

백엔드 컨테이너는 외부 포트를 열지 않으며, 프런트 Nginx도 기본적으로 호스트의 `127.0.0.1:8080`에만 바인딩됩니다. Caddy·Cloudflare Tunnel 등 신뢰 가능한 HTTPS 종단 프록시가 이 주소로 전달하도록 구성한 뒤, 공개 HTTPS 도메인에서 다음 경로를 확인합니다.

- `/api/health/`: 프로세스 liveness
- `/api/health/ready/`: PostgreSQL readiness
- `/api/health/integrations/`: 키 값이 아닌 제공자 설정 여부

백엔드는 기동 전에 마이그레이션과 정적 파일 수집을 수행하고, DB readiness가 통과한 뒤에만 프런트가 준비됩니다. `FRONTEND_BIND_ADDRESS=0.0.0.0`으로 바꾸어 Nginx를 직접 공개한 상태에서 외부 요청의 `X-Forwarded-Proto`를 신뢰하면 안 됩니다. 운영에서는 신뢰 가능한 TLS 종단 프록시만 Nginx 앞에 두고 프런트 원본 포트·PostgreSQL·Gunicorn에 대한 외부 접근을 방화벽으로 차단하세요.

같은 출처 배포에서는 운영 CORS 허용 목록이 기본적으로 비어 있습니다. 프런트와 API를 분리할 때만 `CORS_ALLOWED_ORIGINS`에 쉼표로 구분한 정확한 HTTPS origin을 지정하세요. 사용자 정보, 경로, 쿼리, 프래그먼트, 와일드카드 또는 HTTP 주소가 들어간 항목은 서버 기동 시 거부됩니다.

`collector` 서비스는 KMA 키가 있으면 30분마다 일반 날씨를, KHOA 키가 있으면 1시간마다 해양 자료를 수집하고 5분마다 일반·가족 프로필 Water Index를 재평가합니다. 실패한 호출은 이전 관측의 만료시간을 연장하지 않으며 다음 주기에 다시 시도합니다. 간격은 `.env`의 `*_INTERVAL_SECONDS`로 조정하되 제공자 발행주기와 일일 쿼터를 먼저 확인하세요.

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

## 검증

```bash
cd frontend
npm ci
npm run lint
npm test
npm run build

cd ../backend
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

흐름은 `{tool}/feature-name → {tool} → dev → main`이며 상세 규칙은 [AGENTS.md](AGENTS.md)에 있습니다.

## 라이선스

MIT License
