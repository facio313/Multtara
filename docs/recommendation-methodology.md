# 추천·일정 생성 v1 결정 기록

- 상태: Implemented v1 baseline; production routing/experimentation pending
- 결정일: 2026-08-15
- 구현 검증일: 2026-08-16
- 범위: 콜드스타트, 후보 필터, 랭킹, 다양화, 일정 최적화, 설명, 평가

## 결정

퐁당 추천은 다음 순서를 고정한다.

```text
공식 안전·운영·접근성 하드 게이트
→ 설명 가능한 다기준 후보 점수
→ MMR 기반 다양화
→ 실제 이동시간을 사용한 시간창 오리엔티어링
→ 결정적 reason code와 출처 표시
```

LLM은 자유문장을 구조화된 조건으로 바꾸거나 이미 결정된 JSON 근거를 다국어 문장으로 표현할 수 있다. 안전 판정, 숫자 점수, 후보 순위, 일정 경로를 새로 만들 수 없다.

## 현재 구현 범위

`POST /api/v1/trips/recommendations/`는 요청 시점의 Water Index를 다시 평가한 뒤, 안전·운영·연령·반려동물·접근성 하드 게이트, 연속 선호 점수, 불확실성 패널티와 결정적 MMR을 적용한다. 성인 초급 수영은 가족 보수 프로필을 사용하고, 서핑은 명시된 실력과 확인된 공식 활동 등급이 일치할 때만 적격 후보로 남는다. 결과에는 데이터 상태·출처·만료·배제 요약을 포함하며 `UNKNOWN`과 `STOP`은 추천하지 않는다.

일정 모듈에는 주입형 이동시간 행렬과 시간창·체류시간·예산·도착지 제약을 보존하는 결정적 greedy baseline이 구현되어 있다. 이 baseline은 테스트 가능한 안전한 초기 해법이지 전역 최적해를 증명하지 않는다. 실제 도로 이동시간 공급자, OR-Tools 최적화, 예약·교통 불확실성, 이벤트 로그와 온라인 실험은 운영 데이터 계약이 준비된 다음 단계이며 현재 UI에서 완료된 기능으로 주장하지 않는다.

## 1. 콜드스타트와 페르소나

기존 다섯 페르소나는 고정된 사용자 집단이나 알고리즘 분기 키가 아니라 현재 선호를 이해하기 쉽게 요약하는 레이블이다. 사용자는 언제든 수정할 수 있고, 페르소나에서 아이·장애·반려동물·건강·안전 요구를 추론하지 않는다.

초기 온보딩은 다음 3개 필수 + 2개 선택 질문으로 축소한다.

1. 동행, 아이 나이, 반려동물: 하드 제약
2. 두 경험 이미지 중 더 끌리는 것: 활동 선호
3. 느긋함↔활동적, 유명 명소↔로컬 발견: 효용·다양성 성향
4. 걷기·이동 허용량과 교통수단: 경로 제약
5. 비·바람 시 실내 전환 허용: 상황 정책

모든 질문은 skip 가능하며 3개 응답 뒤 즉시 결과를 낸다. 쌍대비교와 value-of-information 기반 질문은 다속성 선호를 긴 평점표보다 낮은 부담으로 elicitation할 수 있다는 연구에 근거한다. [Guo & Sanner, AISTATS 2010](https://proceedings.mlr.press/v9/guo10b.html)

성격과 관광 선호의 관련성 연구가 존재하지만 특정 국가 표본의 계수를 한국 사용자에게 그대로 적용하지 않는다. [Alves et al., UMUAI 2023](https://link.springer.com/article/10.1007/s11257-023-09361-2)

## 2. 후보 자격

점수를 계산하기 전에 다음을 `eligible / ineligible / unknown`으로 결정한다.

- Water Index `safety_status`
- 공식 운영·영업 시간창
- 동행 연령과 활동 제한
- 반려동물 허용 조건
- 사용자가 요구한 휠체어·유모차·화장실·주차 등 접근성
- 출발·종료·이동수단 안에서 실제 도달 가능성
- 예산과 예약 필요 여부
- 동적 필드의 source, observed_at, valid_until, freshness/conflict 상태

악천후 활동은 점수 감점으로 남기지 않고 후보에서 제외하고 검증된 실내 대안으로 전환한다. 날씨 문맥을 반영한 관광 추천의 현장 연구에서도 위험한 날씨의 활동을 제안하지 않는 설계를 사용했고 지각된 추천 품질·선택 만족이 향상됐다. [Braunhofer et al., ENTER 2014](https://doi.org/10.1007/978-3-319-03973-2_7)

## 3. 설명 가능한 후보 점수

후보 `i`, 사용자·동행 구성원 `m`, 문맥 `c`의 초기 효용은 다음처럼 구성한다.

```text
U_im = w_m · feature_i
     + alpha × activity_fit(i, c)
     + beta  × data_quality_i
     - gamma × travel_minutes_i
     - delta × cost_i
     - rho   × uncertainty_i

U_i_group = theta × mean_m(U_im)
          + (1 - theta) × min_m(U_im)
```

그룹 평균만 최적화해 한 구성원이 크게 불편해지는 것을 막기 위해 최저 구성원 효용을 함께 반영한다. 안전, 접근성, 연령, 반려동물은 이 식의 벌점이 아니라 사전 하드 제약이다.

가중치는 버전 있는 설정으로 두고 사용자 연구와 행동 로그로 보정한다. 초기에는 콘텐츠 기반 가중점수를 사용하며 충분한 편향 보정 로그가 생기기 전 딥러닝·LTR·bandit을 도입하지 않는다.

## 4. 다양성

최소 관련성·안전 기준을 통과한 후보 안에서만 MMR을 적용한다.

```text
MMR(i) = lambda × relevance(i)
       - (1 - lambda) × max similarity(i, selected)
       + kappa × merit_aware_exposure_gap(i)
```

같은 해변·지역·활동의 반복을 줄이고 한 슬롯을 로컬 발견 또는 악천후 대안에 배정한다. 무작위 장소 삽입은 하지 않는다. MMR은 관련성과 중복 감소의 고전적 재랭킹 원리다. [Carbonell & Goldstein, SIGIR 1998](https://doi.org/10.1145/290941.291025) 추천 목록의 주제 다양성이 정확도 일부와 교환되더라도 사용자 경험에 기여할 수 있다는 실험 근거도 있다. [Ziegler et al., WWW 2005](https://doi.org/10.1145/1060745.1060754)

지역·소규모 사업자·장소 유형 노출은 안전과 관련성이 같은 eligible 후보의 merit에 비례해 감사한다. 숫자를 맞추기 위해 위험·접근성 부적합 후보를 올리지 않는다. [Singh & Joachims, KDD 2018](https://doi.org/10.1145/3219819.3220088)

## 5. 일정 최적화

일정은 개인화 관심도, 방문시간, 시간 예산을 결합하는 관광 오리엔티어링 연구를 따른다. [PersTour](https://doi.org/10.1007/s10115-017-1056-y)

의사결정 변수는 방문 `x_i`, 이동 `y_ij`, 도착 `T_i`로 두고 다음 목적을 사용한다.

```text
maximize Σ x_i × group_utility_i
       - c_t × Σ y_ij × travel_p90_ij
       - c_w × Σ wait_i
       - c_u × Σ x_i × uncertainty_i
```

필수 제약:

- 지정 출발·종료 지점
- 총 가용시간
- 교통수단별 실제 이동시간 행렬
- 각 장소의 영업 시간창과 체류시간
- 예산
- 식사·휴식
- 필수 방문, 선후행, 장소 유형별 상한
- `x_i <= eligibility_i`

OR-Tools는 travel-time dimension, 대기 slack, 시간창, optional node와 drop penalty를 지원하므로 Raspberry Pi 5 ARM64 운영환경에서 우선 사용한다. [OR-Tools VRPTW](https://developers.google.com/optimization/routing/vrptw), [Drop penalties](https://developers.google.com/optimization/routing/penalties)

이동시간은 공급자 추상화 뒤 Kakao Mobility 또는 자체 Valhalla 행렬을 사용한다. Haversine 직선거리는 UI 근사치일 뿐 일정 실행 가능성의 근거로 쓰지 않는다. [Valhalla Matrix API](https://valhalla.github.io/valhalla/api/matrix/)

## 6. 설명 계약

각 결과는 자연어보다 먼저 다음의 구조화된 근거를 만든다.

```json
{
  "policy_version": "recommendation-v1",
  "eligibility": "eligible",
  "positive_reasons": ["HIGH_ACTIVITY_FIT", "LOW_TRAVEL_TIME"],
  "constraints_applied": ["PET_ALLOWED", "STEP_FREE_REQUIRED"],
  "tradeoffs": ["HIGHER_CROWD_THAN_ALTERNATIVE"],
  "source_refs": [],
  "freshness": {},
  "alternative_ids": [],
  "adjustable_inputs": ["departure_time", "walking_limit"]
}
```

화면에는 실제 양의 기여 상위 2–3개, 적용 제약, 중요한 trade-off, 출처·갱신시각·데이터 상태, 조건을 바꾸면 가능한 대안을 보여준다. 존재하지 않는 수치나 출처를 생성하지 않는다.

설명은 신뢰·투명성·효율·만족을 높일 수도 있지만 과도한 개인화 설명이 실제 결정 효과성을 해칠 수 있다. 설득력보다 충실도와 사용자의 수정 가능성을 우선한다. [Tintarev & Masthoff, UMUAI 2012](https://doi.org/10.1007/s11257-011-9117-5)

## 7. 이벤트 로그와 온라인 학습

다음 이벤트 계약이 먼저다.

```text
request_id
context_snapshot_hash
candidate_set
eligibility_reasons
rank and score_components
policy_version
propensity
impression / click / save / dismiss
plan_accept / edit / start / complete / replan / report
```

장애·아이·반려동물 요구는 기본적으로 session scope에 두고 불필요한 민감 프로필을 영구 저장하지 않는다.

충분한 노출 로그와 propensity가 쌓인 뒤에만 안전 후보 내부에서 contextual bandit 또는 LTR을 시험한다. 신경망 확률은 별도 calibration이 필요하다. [Guo et al., ICML 2017](https://proceedings.mlr.press/v70/guo17a.html) 과거 로그 비교는 replay/IPS 또는 doubly robust 평가를 선행한다. [Li et al., WSDM 2011](https://arxiv.org/abs/1003.5956), [Dudík et al., ICML 2011](https://www.microsoft.com/en-us/research/publication/doubly-robust-policy-evaluation-and-learning-2/)

## 8. 승격 게이트

### Gate 0: 안전·데이터·제약

- 공식 중단·위험 후보의 참여 추천률 0
- missing/stale 안전값을 `clear`로 표시한 비율 0
- 가족·반려동물·접근성 명시 요구 위반률 0
- 영업창·예산·출발/종료·총시간 일정 위반률 0
- 모든 점수와 이유의 provenance 추적률 100%
- fallback을 official로 표시한 비율 0

### Gate 1: 오프라인 랭킹

- 시간 기반 split, 같은 여행·세션 누출 금지
- baseline: 지역 인기순, 콘텐츠 cosine, 무문맥 가중점수, 문맥 게이트+점수, +MMR
- NDCG@5, Recall@5, MRR
- Brier score, ECE
- intra-list similarity, category/region coverage, 로컬 노출
- first-time/returning, party type, accessibility mode, 악천후별 worst-segment 지표

### Gate 2: 사용자 연구

- 무설명 대 근거+출처+상태+조절 설명
- 실제로 더 적합한 선택, decision time, perceived effort, 만족, calibrated trust, 오류 조건 수정 능력
- 고정 5문항 대 3문항+선택 2문항의 이탈·시간·첫 저장·만족
- 표본수는 사전 정의 MDE와 power analysis로 결정

### Gate 3: 온라인

- 1차: 노출에서 실행 가능한 일정 저장·수락, 실제 일정 완료·재계획 후 유지
- 2차: first-save 시간, 편집량, 대안 확인, 재방문, 만족
- guardrail: unsafe suggestion 0, stale 오표시 0, 제약 위반 0, 신고, 즉시취소, p95 latency, worst-segment utility
- 계절·악천후를 별도 보고하고 한 시기의 평균으로 전천후 성능을 주장하지 않음

정확도 하나만으로 추천 경험을 평가하지 않는다. [Herlocker et al., ACM TOIS 2004](https://doi.org/10.1145/963770.963772), [Knijnenburg et al., UMUAI 2012](https://doi.org/10.1007/s11257-011-9118-4)

## 9. 구현 순서

1. POI/context/provenance 스키마와 하드 게이트·reason code
2. 온보딩 답변을 연속 선호벡터·제약으로 바꾸는 deterministic ranker
3. MMR 다양화
4. 이동시간 공급자 추상화와 OR-Tools 반나절·하루 일정
5. 악천후 실내 fallback replan
6. gold set, property-based 제약 테스트, 오프라인 evaluator
7. 사용자 연구·A/B 계측
8. 충분한 편향 보정 로그 뒤 LTR/contextual bandit

이 순서는 NIST AI RMF의 fail-safe, 배포 유사 조건 평가, 지식 한계·설명·안전 문서화 원칙과 일치한다. [NIST AI RMF Core](https://airc.nist.gov/airmf-resources/airmf/5-sec-core/)
