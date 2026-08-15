# 🌊 퐁당 PongDang — 물 여행 플랫폼

> **"오늘 가장 가기 좋은 물 여행지를 찾아준다."**

대한민국의 바다, 계곡, 온천, 호수, 폭포, 갯벌 등 물과 관련된 여행지를 모아, **위치뿐 아니라 '지금 그 물의 상태(컨디션)'와 '언제·어떻게 즐길지'까지 안내하는** 여행 플랫폼입니다. 현재 웹앱은 강릉 우선 MVP이며, 외부 데이터 연동 전에도 전체 흐름을 확인할 수 있도록 고정 데모 데이터를 명확히 표기해 제공합니다.

한국관광공사 공공API 활용 공모전 출품작.

## 핵심 3축

| 축 | 기능 | 설명 |
|----|------|------|
| **지금** | Water Index | 0~100점 종합 지표 (활동별 가중치 차등) |
| **언제** | Water Forecast | 7일치 예보 그래프 (최적 방문 시점 추천) |
| **직접 눈으로** | Water Twin + 라이브캠 | 디지털 트윈 지도 + 라이브 영상 연결 상태 |

## 기술 스택

- **Backend:** Python 3.11+ · Django · Django REST Framework
- **Frontend:** React (Vite) · React Router · Zustand · Axios
- **Database:** PostgreSQL 15
- **Infrastructure:** Docker · Docker Compose · Nginx
- **Target:** Raspberry Pi 5 (ARM64)

## 구현된 웹 경험

- 오늘의 활동별 Water Index와 강릉 추천 스팟
- 카카오맵 키가 있으면 실제 지도를 사용하고, 없거나 로딩에 실패하면 접근 가능한 Water Twin 개념도와 목록으로 전환
- 지역·활동별 7일 예보, 날짜 상세와 의미가 동일한 접근성 표
- 실제 라이브와 데모 포스터를 혼동하지 않는 라이브캠 탐색
- 5단계 취향 온보딩, 5개 페르소나, 로컬 저장 기반 프로필과 패스포트
- 악천후 실내 전환까지 포함한 결정형 AI 컨시어지 데모
- 바다·온천·계곡·갯벌에 맞춘 스팟 상세, 안전 카드 다운로드, 시설·물때·예보 정보
- 320px급 모바일부터 대형 데스크톱까지 반응형 내비게이션과 safe-area 대응

관측·예보·라이브캠 값은 화면의 `DEMO`/`데모 데이터` 표기를 기준으로 구분합니다. 실제 제공자 데이터가 없을 때 데모 값을 라이브 정보처럼 표시하지 않습니다.

## 빠른 시작

### 사전 준비
- Docker & Docker Compose 설치
- Git

### 실행

```bash
# 1. 저장소 클론
git clone https://github.com/facio313/Multtara.git
cd Multtara

# 2. 환경변수 설정
cp .env.example .env
# .env 파일을 열어 실제 값 입력

# 3. 운영 모드 실행
docker compose up -d

# 4. 서비스 확인
# Frontend: http://localhost
# Backend API: http://localhost:8000/api/health/
# Django Admin: http://localhost:8000/admin/
# 연동 설정 상태(키 값은 노출하지 않음): http://localhost:8000/api/health/integrations/
```

브라우저에는 `VITE_API_BASE_URL`과 도메인 제한을 적용한 `VITE_KAKAO_MAP_KEY`만 전달합니다. `DATA_GO_KR_SERVICE_KEY`, `TOUR_API_KEY`, `KMA_API_KEY`, `KHOA_API_KEY`, `MOE_API_KEY`, Django/DB 비밀값은 서버에서만 읽습니다. 환경변수 이름과 역할은 [.env.example](.env.example)을 참고하세요.

### 개발 모드 (핫 리로드)

```bash
docker compose -f docker-compose.yml -f docker-compose.dev.yml up

# Frontend (Vite): http://localhost:5173
# Backend (Django): http://localhost:8000
```

## 프로젝트 구조

```
Multtara/
├── backend/          # Django REST API
│   ├── config/       # 프로젝트 설정 (base/dev/prod)
│   ├── apps/         # Django 앱 (users, spots, conditions, ...)
│   └── services/     # 공공API 래퍼 + Water Index 산출 로직
├── frontend/         # React (Vite) SPA
│   ├── src/
│   │   ├── components/   # UI 컴포넌트
│   │   ├── pages/        # 라우트 페이지
│   │   ├── store/        # Zustand 상태관리
│   │   └── services/     # API 클라이언트
│   └── nginx.conf    # 프로덕션 Nginx 설정
├── docker-compose.yml      # 운영 환경
└── docker-compose.dev.yml  # 개발 환경
```

## Git 개발 환경 (Pilgrimage와 동일)

에이전트별로 브랜치 + git worktree를 씁니다. `worktrees/`는 `.gitignore`에 포함됩니다.

| 경로 | 브랜치 | 도구 |
|------|--------|------|
| `Multtara/` | `main` | 배포 기준 (사용자) |
| `Multtara/` (`dev` 체크아웃) | `dev` | 통합 (사용자) |
| `worktrees/cursor/` | `cursor` | Cursor |
| `worktrees/codex/` | `codex` | OpenAI Codex |
| `worktrees/anthropic/` | `anthropic` | Claude Code |

```
{tool}/feature-name → {tool} → dev → main
```

워크트리 재생성:

```bash
./scripts/setup-worktrees.sh
```

Cursor로 개발할 때는 **`worktrees/cursor` 폴더를 워크스페이스로 연다.**
상세 규칙: [AGENTS.md](AGENTS.md)

## 공공데이터 API

모든 API는 [공공데이터포털(data.go.kr)](https://www.data.go.kr)에서 발급받습니다.

| 기관 | 용도 |
|------|------|
| 한국관광공사 TourAPI | 관광지 기본정보 (베이스 레이어) |
| 기상청 | 기온, 강수, 풍속, UV, 예보 |
| 국립해양조사원 | 수온, 파고, 조석, 조류 |
| 환경부 | 수질, 수위, 유량 |

## Raspberry Pi 5 배포

> ⚠️ **중요:** RPi 5 기본 커널(`kernel_2712.img`)은 16K 페이지 크기를 사용하여 Alpine 이미지와 충돌합니다.

```bash
# /boot/firmware/config.txt에 추가
kernel=kernel8.img

# 재부팅
sudo reboot
```

SSD 사용을 강력히 권장합니다 (SD 카드에서 PostgreSQL 운영 비권장).

## 라이선스

MIT License
