# 퐁당 Frontend

React 19와 Vite 8로 만든 강릉 우선 물 여행 SPA입니다. 같은 출처의 Django API가 없을 때도 관광 콘텐츠는 사용할 수 있지만, 관측값은 `DEMO` 또는 `NO DATA`로 표시하며 안전 상태를 추정하지 않습니다.

로컬 빌드와 운영 컨테이너는 지원 중인 Node.js 24 LTS를 기준으로 합니다.

## 환경변수

- `VITE_API_BASE_URL`: 기본값 `/api/v1/`. 분리 개발 환경에서는 예: `http://localhost:8000/api/v1/`.
- `VITE_KAKAO_MAP_KEY`: 브라우저에 노출되는 Kakao Maps JavaScript 키. Kakao Developers에서 허용 도메인을 제한해야 합니다.

공공데이터 키, DB 비밀번호, Django `SECRET_KEY`는 프런트 환경변수나 번들에 넣지 않습니다.

## 명령

```bash
npm ci
npm run dev
npm run lint
npm test
npm run build
npm run build:sites
```

`npm test`는 Node 내장 테스트 러너로 STOP/UNKNOWN nullable score, 만료·미래 근거, 데모 폴백, 공개 오류 메시지 계약을 검증합니다. `build`는 Docker/Nginx용이며 `build:sites`는 별도의 비공개 프런트 미리보기용입니다. Sites 미리보기에는 Django 터널을 연결하지 않으므로 실시간 API가 아니라 명시적인 `DEMO`/`UNKNOWN` 폴백을 보여줍니다. 실제 운영 데이터는 같은 출처의 Nginx + Django 배포에서만 `LIVE`로 승격합니다.

## 화면 확인

최소 320×568, 390×844, 768×1024, 1024×768, 1440×900에서 가로 오버플로, 모바일 하단 내비, 키보드 포커스, 감소 모션을 확인합니다. 실제 API 테스트에서는 loading/error/empty/live/stale/stop/unknown을 각각 검증합니다.
