# Water Index v1 방법론 결정 기록

- 상태: Accepted
- 결정일: 2026-08-15
- 알고리즘 버전: `water-index-v1.0.0`
- 구현: `backend/services/water_index/`
- 테스트: `backend/apps/conditions/test_water_index.py`

## 1. 이 지수가 말하는 것과 말하지 않는 것

퐁당의 공개 결과는 한 숫자가 아니라 다음 세 축이다.

```text
suitability_score: 0..100 | null
safety_status: clear | caution | stop | unknown
confidence: 0..1
```

- `suitability_score`는 해당 활동을 **즐기기 좋은 정도**다. 사고확률이나 안전확률이 아니다.
- `safety_status`는 공식 통제, 특보, 현장 운영 상태, 활동별 핵심 안전자료로 별도 결정한다.
- `confidence`는 데이터 출처·완전성·신선도를 나타낸다. 점수에 곱해 불확실성을 낮은 적합도로 위장하지 않는다.
- 안전 필수값이 없거나 오래됐거나 서로 충돌하면 `unknown`이며 공개 점수는 `null`이다.
- 공식 통제나 중단 조건이 하나라도 있으면 `stop`이며 공개 점수는 `null`이다.
- `stop`과 `unknown`은 추천·랭킹·일정 참여 후보에서 제외한다.
- UI에서는 `활동 적합도`, `공식 지수`, `기후 쾌적도`라고 표현한다. `안전점수`, `안전함`, `사고 없음`이라는 표현은 금지한다.

이 분리는 WHO가 권고하는 수상레저 위험관리·감시·적시 위험소통의 방향과, 불완전한 데이터를 안전으로 오인하지 않는 fail-safe 원칙을 따른다. [WHO Guidelines on Recreational Water Quality, Volume 1 (2021)](https://www.who.int/publications/i/item/9789240031302)

## 2. 핵심 결정

모든 물 활동을 하나의 만능 공식으로 계산하지 않는다.

| 활동 | v1의 1차 적합도 | 안전 판단 |
|---|---|---|
| 가족 해수욕 | KHOA 해수욕 공식 등급 + 기후·현장 쾌적도 | 입수 통제, 이안류, 수질, 낙뢰, 해양특보, 수온, 안전요원 |
| 서핑 | KHOA 숙련도별 공식 지수 원형 보존 | 현장 통제, 이안류, 낙뢰, 풍랑·태풍 등 해양특보 |
| 갯벌 | KHOA 공식 지수와 공식 체험 가능 시간 원형 보존 | 공식 시간창, 안개, 지정 진입로, 현장 통제, 해양특보 |
| 물멍·해안 감상 | 검증된 HCI:Beach 기후 쾌적도 | 해안·산책로 통제, 낙뢰, 풍랑·태풍 등 해양특보 |
| 온천·스파 | 운영·혼잡·요구시설·실내대피·선호온도의 시설 핏 | 폐쇄, 위생 조치, 온수 욕조 40°C 초과 |
| 래프팅·계곡 | 현장 승인된 지점별 유량/수위 곡선이 있을 때만 | 운항 중지, 상류 강우, 수위 위험, 낙뢰·호우, 필수 장비 |

공식 지수가 없는 지점의 값을 인근 지점에서 복사하거나 공간 보간하지 않는다. 지점별 보정 근거가 없는 서핑 파향·래프팅 유량·계곡 수위는 전국 공통 임계값을 만들지 않고 적합도를 `null`로 둔다.

## 3. 근거의 우선순위

같은 시각에 여러 정보가 충돌하면 다음 순서를 적용한다.

1. 현장 관리자·구조기관의 폐쇄, 입수 통제, 대피 명령
2. 기상청·국립해양조사원·보건당국의 현재 공식 특보와 위험 단계
3. 해당 장소·시간을 직접 대표하는 공식 관측 또는 공식 활동지수
4. 해당 장소의 검증된 지점별 보정 모델
5. 논문에 근거한 일반 쾌적도 모델
6. 제품 선호 가중치

낮은 우선순위의 높은 점수는 높은 우선순위의 `stop`을 절대 해제하지 못한다.

## 4. 공식 데이터 계약

2026년 1월에 폐기된 구 바다누리 연계 API는 사용하지 않는다. 국립해양조사원이 국가중점데이터로 신규 개방한 HTTPS API를 사용한다. [35종 폐기 및 대체서비스 공식 공지](https://www.data.go.kr/bbs/ntc/selectNotice.do?originId=NOTICE_0000000004473)

| 데이터 | 공식 API |
|---|---|
| 해수욕지수 | `https://apis.data.go.kr/1192136/fcstBeachv2/GetFcstBeachApiServicev2` |
| 서핑지수 | `https://apis.data.go.kr/1192136/fcstSurfingv2/GetFcstSurfingApiServicev2` |
| 갯벌체험지수 | `https://apis.data.go.kr/1192136/fcstMudflatv2/GetFcstMudflatApiServicev2` |
| 이안류지수 | `https://apis.data.go.kr/1192136/ripCurrent/GetRipCurrentApiService` |

공식 계약: [해수욕](https://www.data.go.kr/data/15142484/openapi.do), [서핑](https://www.data.go.kr/data/15142490/openapi.do), [갯벌](https://www.data.go.kr/data/15142489/openapi.do), [이안류](https://www.data.go.kr/data/15156028/openapi.do).

2026-08-15 실제 응답을 서버 키로 검증한 결과, 세 활동지수의 현재 응답은 `totalIndex`에 한국어 5단계 등급을 제공했고 문서가 언급한 숫자 점수 필드는 응답에 없었다. 따라서:

- 원본 `totalIndex`를 `official_grade`로 그대로 저장한다.
- 추후 `lastScr` 같은 숫자 필드가 실제로 오면 `official_score`로 별도 보존한다.
- 현재 등급을 0–100 UI에 결합할 때 쓰는 `95/80/60/35/15`는 **공식 점수라고 부르지 않는 표시용 앵커**다.
- 제공자 원문, 인증키, 알 수 없는 필드는 API 응답에 포함하지 않는다.

KHOA 클라이언트는 `backend/services/providers/khoa.py`에 있으며 키 생성자 주입, HTTPS, connect/read timeout, 제한된 429/5xx 재시도, 응답 코드 검증, 페이지네이션, 단일·목록·빈 응답 정규화, 비밀값 제거를 수행한다.

기상 적합도에는 [기상청 단기예보 조회서비스](https://www.data.go.kr/data/15084084/openapi.do)의 2026년 `VilageFcstInfoService_2.0` 계약을 사용한다. `backend/services/providers/kma.py`는 실황·초단기·단기예보를 시간대가 있는 typed value로만 반환한다. 단기예보 값으로 특보 발효 여부나 낙뢰 해제를 추론하지 않는다. 관광 POI는 [한국관광공사 국문 관광정보 서비스](https://www.data.go.kr/data/15101578/openapi.do)의 `KorService2`를 사용하며 영·일·중문은 각 공식 `*Service2` 게이트웨이로 분리한다. 서버 키와 제공자 원문은 브라우저에 전달하지 않는다.

## 5. 공통 데이터 불변조건

엔진에 들어오는 각 metric에는 다음이 반드시 있어야 한다.

```json
{
  "name": "rip_current_risk",
  "value": "attention",
  "unit": "canonical",
  "source": "KHOA",
  "spatial_scope": "beach:GYEONGPO",
  "observed_at": "2026-08-15T11:50:00+09:00",
  "fetched_at": "2026-08-15T11:51:00+09:00",
  "valid_from": "2026-08-15T11:00:00+09:00",
  "valid_until": "2026-08-15T12:00:00+09:00",
  "source_url": "https://www.data.go.kr/data/15156028/openapi.do",
  "mode": "observed",
  "confidence": 1.0,
  "state": "valid"
}
```

`state=conflict|invalid`, 유효시간 밖의 값, timezone 없는 시각, 위치 범위가 없는 값은 안전 필수입력으로 사용할 수 없다. `missing != 0`, `stale != fresh`, `estimated != observed`를 항상 보존한다.

- 관측값의 `observed_at`은 수집시각보다 미래일 수 없다.
- 예보값은 `valid_from`과 `valid_until`이 모두 있어야 한다.
- 안전 필수입력의 신뢰도가 `0.80` 미만이면 사용 불가로 보고 `unknown`을 반환한다.
- 적합도 선택 입력이 빠져도 남은 가중치를 100%로 재분배하지 않는다. 관측된 하한과 결측 항이 가질 수 있는 상한을 `score_range`로 함께 보존한다.

융합 metric은 선택된 원본 metric과 충돌에 참여한 원본 metric을 별도
lineage edge로 보존한다. 각 edge에는 `selected|conflict` 관계와 당시의
source priority가 기록된다. 원본 metric은 이를 참조하는 융합 근거가 있는
동안 보호되며, 공개 API는 원본 payload·요청 URL·인증정보 대신 최소한의
제공자·공개 출처·공간·시각 provenance만 반환한다.

## 6. 가족 해수욕 안전 게이트

가족·초급 일반 해수욕은 다음 입력을 필수로 요구한다.

- 공식 입수·접근 상태
- KHOA 이안류 단계 또는 원지수
- 마지막 천둥 이후 경과시간
- 공식 수질 운영 상태
- 해양특보 상태
- 수온
- 안전요원 운영 상태
- 지정 수영구역 운영 상태
- 가족·초급자의 팔 길이 이내 성인 감독 확보 상태

정책은 다음과 같다.

| 조건 | 결과 |
|---|---|
| 공식 입수 금지·폐쇄·대피 | `stop` |
| KHOA 원지수 `R >= 55` 또는 `경계/위험` | `stop` |
| `30 <= R < 55` 또는 `주의` | `caution`, 가족 추천 제외, 공개 점수 최대 39 |
| 마지막 천둥 후 30분 미만 | `stop` |
| 공식 수질 부적합·오수·유해조류 이용제한 | `stop` |
| 풍랑·태풍·폭풍해일 등 해당 활동 중단 특보 | `stop` |
| 가족 정책 수온 `<15°C` 또는 `>31°C` | `stop` |
| 가족 정책 수온 `15°C 이상 18°C 미만` | `caution`, 가족 추천 제외, 공개 점수 최대 39 |
| 안전요원 미운영 | `caution`, 가족 추천 제외, 공개 점수 최대 39 |
| 지정 수영구역 폐쇄·구역 밖 또는 성인 감독 불가 | `stop` |
| 위 필수값 결측·stale·conflict·저신뢰·미인식 | `unknown` |

KHOA 이안류 시스템은 2021–2024년 9개 해변 검증에서 대부분 AUC 0.92–0.99와 양의 Brier skill을 보였고 경포·낙산·망상에서도 높은 성능을 보였다. 이것은 공식 지수를 우선할 근거지만, 경보 시스템이 현장 안전을 보증한다는 뜻은 아니다. [Choi & Kim, 2026, DOI 10.12652/Ksce.2026.46.1.0061](https://www.kci.go.kr/kciportal/ci/sereArticleSearch/ciSereArtiView.kci?sereArticleSearchBean.artiId=ART003301317)

낙뢰는 마지막 천둥 이후 최소 30분을 기다리는 기상청 행동요령을 적용한다. [기상청 낙뢰 안전 가이드](https://www.weather.go.kr/w/hazard/safety-guide/lightning.do)

EPA의 2012 Recreational Water Quality Criteria는 30일 기하평균·통계 임계값과 Beach Action Value를 구분한다. 단일 오래된 시료 하나를 `pass`로 바꾸지 않으며, 운영기관의 현재 이용판정과 검사 유효기간을 사용한다. [US EPA 2012 RWQC](https://www.epa.gov/sites/default/files/2015-10/documents/rwqc2012.pdf)

수온 경계는 가족·초급을 위한 보수적인 제품 정책이다. 개인 건강, 노출시간, 구명장비, 방한복을 반영한 의료 판단이 아니며 한국 현장 결과로 재검증해야 한다.

## 7. 서핑

지원 지점에서는 KHOA의 장소·시간·숙련도별 공식 결과를 원형 보존한다. KHOA 결과는 파고, 파주기, 풍속, 수온과 숙련도 등급을 포함한다. 높은 공식 적합도가 입수 통제, 이안류, 풍랑, 태풍, 낙뢰를 무시할 수 없다.

공식 미지원 지점에서 일반 소비자용 보편 점수를 만들지 않는다. 연구에서 사용한 숙련도별 파고 구간은 특정 지역과 해상 모델의 활동 분류에 가깝고 한국 모든 해변의 안전기준이 아니다. [Boqué Ciurana et al., 2022](https://www.mdpi.com/2071-1050/14/14/8496)

지점별 해안 방향, 실제 쇄파, 파향 전달, 바람, 조위 보정이 승인된 경우에만 별도 `fallback` 알고리즘 버전으로 계산한다. 공식 결과와 fallback 결과는 같은 레이블로 섞지 않는다.

## 8. 물멍·해안 감상: HCI:Beach

물멍은 안전점수나 정신건강 효과가 아니라 HCI:Beach 기반 `해안 기후 쾌적도`로 표시한다. [Rutty et al., 2020 원문](https://fenix.igot.ulisboa.pt/downloadFile/563078802440222/Rutty%20et%20al_2020.pdf)

```text
HCI:Beach = 2 × thermal_comfort
          + 4 × aesthetic_cloud
          + 3 × precipitation
          + 1 × wind
```

최고점은 100이다. 구현은 논문의 구간표를 그대로 사용하며 다음 회귀 벡터를 고정한다.

| Humidex / 구름 / 일강수 / 평균풍속 | 결과 |
|---|---:|
| `29 / 20% / 0mm / 5km/h` | 100 |
| `24 / 70% / 4mm / 25km/h` | 66 |
| `29 / 100% / 30mm / 75km/h` | 15 |

일평균 쾌적도가 시간별 돌풍·소나기·낙뢰·해안 통제를 가리지 않도록 안전 게이트를 먼저 적용한다. HCI 결과를 우울감 감소, 치료, 치유 확률로 표현하지 않는다.

## 9. 갯벌

KHOA 공식 등급과 장소별 체험 시작·종료시각을 원형 보존한다. 다음은 `stop`이다.

- 공식 체험 시간 밖
- 안개 발생
- 현장 폐쇄·통제
- 지정 진입로·가이드 경로 확인 불가
- 관련 풍랑·태풍·호우·낙뢰 위험

공식 시작·종료는 timezone이 포함된 별도 구조화 metric과 원래의
`valid_from`/`valid_until`로 함께 보존한다. 시작과 종료는 포함 경계이며,
평가 시각이 해당 공식 기록의 한국 표준시 날짜 범위 안이면서 창 밖이면
`tide_window_open=false`로 평가한다. 야간 교차 창은 종료시각을 다음 날로
보존한다. 시작=종료, 파싱 실패, timezone 결손, 또는 공식 기록과 무관한
날짜에는 24시간 창이나 폐쇄기간을 만들지 않고 `unknown`으로 남긴다.

간조 시각만 보고 임의의 전국 공통 체험창을 만들지 않는다. 갯골은 들물 때 먼저 차오를 수 있으므로 인근 조위소의 한 시각이 경로 안전을 대신하지 않는다. [해양환경정보포털 갯벌체험 안전요령](https://meis.go.kr/mes/mudFlat/experience/view1.do), [해양수산부 갯골 안전 안내](https://www.mof.go.kr/doc/ko/selectDoc.do?bbsSeq=10&docSeq=34946&menuSeq=971)

## 10. 온천·스파

온천은 `시설 핏`으로만 계산한다.

```text
facility_fit = 0.40 × verified_operation
             + 0.20 × crowd_fit
             + 0.20 × amenity_fit
             + 0.10 × indoor_weather_shelter
             + 0.10 × preferred_temperature_fit
```

이는 의학 공식이 아니라 제품 가중치다. 광물 성분에서 질환 치료·면역 향상 같은 효능을 추론하지 않는다. 시설 폐쇄·보건조치 중이거나 온수 욕조 실측 수온이 40°C를 초과하면 `stop`; 위생검사나 수온이 없으면 `unknown`이다. [WHO Safe Recreational Water Environments, Volume 2](https://iris.who.int/bitstream/10665/43336/1/9241546808_eng.pdf), [CDC Legionella hot-tub module](https://www.cdc.gov/control-legionella/php/toolkit/hot-tub-module.html)

## 11. 래프팅·계곡

최소·최적·최대 유량 또는 수위는 하천, 구간, 활동, 장비, 숙련도마다 다르다. 전국 공통 `m³/s` 또는 수위 임계값을 코드에 넣지 않는다. [Brown, Taylor & Shelby](https://pubs.usgs.gov/publication/70125918), [Carolli et al., 2017](https://doi.org/10.1016/j.scitotenv.2016.11.049)

현지 운영자·수리모델·공식 관측소가 승인한 버전 있는 네 값이 있을 때만 역 U자 적합도를 만든다.

```text
q_min < q_opt_low <= q_opt_high < q_max
flow_fit = trapezoid(Q; q_min, q_opt_low, q_opt_high, q_max)

rafting_fit = 0.60 × flow_fit
             + 0.20 × operator_readiness
             + 0.10 × flow_trend_stability
             + 0.10 × thermal_gear_readiness
```

운항 중지, 호우·태풍·낙뢰, 상류 집중호우, 급격한 수위상승·방류, 지점별 최대 초과, 구명조끼·안전모 미확인은 `stop`이다. [기상청 호우 행동요령](https://www.weather.go.kr/w/hazard/safety-guide/heavy-rain.do)

## 12. 점수 가중치의 지위

공식 게이트와 공식 지수는 운영 근거다. 반면 다음은 v1의 명시적 제품 판단이며 과학적으로 검증된 보편 상수가 아니다.

- 공식 5단계 등급의 표시용 숫자 앵커
- 해수욕 쾌적도 세부 가중치
- 온천 시설 핏 가중치
- 혼잡·자외선 선호 가중치
- 추천/고려 표시 경계 80·60

이 값들은 코드에서 버전 관리하고 한국 사용자 연구·실제 운영 중단·현장 검수 결과로 교정한다. 안전 게이트는 클릭률이나 예약 전환율 최적화 대상이 아니다.

## 13. 검증 불변조건

자동 테스트는 최소한 다음을 보장한다.

```text
official_stop => safety_status == stop and public_score is null
missing_required_safety => safety_status == unknown and public_score is null
stale_or_conflict != fresh
low_confidence_required_safety => unknown
high_suitability never overrides stop
rip_R == 30 => caution for family swim
rip_R == 55 => stop
lightning_clearance < 30min => stop
family_water_temp < 15 or > 31 => stop
15 <= family_water_temp < 18 => caution
missing_optional_score_factor != redistributed_weight
hot_tub_temperature > 40 => stop
mudflat_outside_official_window => stop
rafting_without_site_thresholds => suitability null
fallback never labeled official
every metric has source, spatial_scope, observed_at, fetched_at, validity
```

## 14. 운영 전 남은 검증

코드 단위 테스트 통과만으로 실제 안전 서비스를 선언하지 않는다. 운영 전에는 다음이 필요하다.

1. 강릉시·해양경찰·해수욕장 운영기관과 reason-code별 대응표 현장 검수
2. 각 공식 API의 운영계정 승인과 장애·쿼터·지연 관측
3. 이안류·수질·특보·입수통제의 장소 코드 매핑 검수
4. 과거 폐쇄·구조·특보 사례를 이용한 retrospective test
5. 데이터 누락·지연·서로 다른 기관 충돌을 주입한 chaos test
6. 점수 대신 `unknown`이 노출되는 전체 UI·추천·일정 회귀 테스트
7. 계절별·해변별 calibration 보고서와 모델 카드 공개
8. 현재 snapshot/metric 단위 감사와 command 로그를 넘어, 빈 응답·부분 성공·오류를 한 실행으로 묶는 credential-free `IngestionRun` 운영 감사 모델

현장 표지·구조요원·관계기관 안내가 언제나 앱보다 우선한다.
