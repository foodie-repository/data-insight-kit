# External Adapter Registry

이 문서는 `data-insight-kit` core가 이해하는 외부 context adapter category를 정의한다.
외부 adapter는 원본 데이터만으로 부족한 판단 맥락을 보강하는 선택 입력이다. 특정
도메인 사례, 분류 체계, 지역, 업무 규칙은 이 registry에 직접 넣지 않고
`domains/<domain>/` pack에서 확장한다.

`docs/external-denominator-adapters.md`는 수집·조인·lineage 계약을 설명하고, 이
문서는 category별 의미, metric layer, 허용 해석, 금지 해석, QA 기준을 고정한다.

## Category 판단 원칙

- 새 외부 데이터가 이미 등록된 category 의미에 맞으면 registry category를 쓴다.
- guided intake는 category 이름을 그대로 노출하지 않고 사용자 친화적 선택지로 바꿔
  보여준다. 선택은 즉시 수집 실행이 아니라 `intake.external_adapters` 정책 기록이다.
- 반복 사용 여부가 불명확한 1회성 보조 데이터는 `custom`을 쓴다.
- 같은 custom 패턴이 반복되거나 별도 금지 해석이 필요하면 정식 category 승격을
  검토한다.
- category를 추가해도 `fields[].metric_layer` enum을 바로 늘리지 않는다. 우선
  기존 layer(`demand`, `cost`, `performance`, `spatial`, `competition`, `context`,
  `coverage`)로 표현할 수 있는지 본다.
- `coverage` layer는 조인·수집 품질 지표에만 쓴다. 기회, 성과, 비용, 추천 점수에
  섞지 않는다.

## Registry

| category | metric_layer | 의미 | 허용 해석 | 금지 해석 | 권장 KPI 패턴 | 필수 lineage | QA 기준 |
|---|---|---|---|---|---|---|---|
| `population` | `demand`, `context`, `coverage` | 인구, 계정 수, 사용자 수, 조직 수처럼 규모를 보정하는 분모 | 규모 대비 밀도, 배후 규모, segment-normalized 비교 | 실제 수요·구매·성과 확정 | 단위 규모당 발생 수, segment penetration, coverage-adjusted rate | source_ref, 기준일, grain, join key, match_rate/null_rate, 합산 기준 | 단독 사용 시 "규모 대비 보정 신호"까지만 허용 |
| `foot_traffic` | `demand`, `context`, `coverage` | 방문량, 사용량, 접속량, 체류, 시간대 activity proxy | 사용/방문 context, 시간대·채널·접점 비교 | 구매 전환, 매출, 성과 인과 단정 | 활동량당 발생 수, 시간대별 density, active-context index | source_ref, 기간, 시간 grain, 분석 grain, join key, coverage, 추정 방식 | 전환·성과 claim은 별도 outcome 데이터 없으면 WARN/BLOCK |
| `rent` | `cost`, `context`, `coverage` | 비용, 가격, 수수료, 임대료, 공실률, 진입장벽 proxy | 비용 압력, 운영 부담, 선택지 제약 context | 비용이 낮다는 이유만으로 좋은 후보·수익성 단정 | cost pressure, cost percentile, cost-adjusted screening | source_ref, 기준일, grain, join key, coverage, coarse mapping 여부 | performance 데이터 없이 수익성 표현 금지 |
| `sales` | `performance`, `context`, `coverage` | 매출, 소비, 거래액, 전환, outcome/performance proxy | 성과/소비/결과 proxy, 기본 신호와 outcome 정합성 | 순이익·성공 가능성·원인 확정 | performance per unit, outcome rate, spend/usage comparison | source_ref, 기간, segment grain, join key, coverage, 표본 편향 | cost/risk 없는 종합 성공·수익성 claim 금지 |
| `business_dynamics` | `context`, `coverage` | 개시·종료, churn, 생존, 이탈, 상태 변화 proxy | 안정성, 이탈 리스크, 회전율 context | 낮은 이탈률만으로 추천·성공·성과 확정 | churn rate, survival rate, net change, volatility context | source_ref, 기간, grain, join key, coverage, coarse aggregation 여부 | 결과는 risk/context로만 표시. 종합 점수에 단독 사용 금지 |
| `area` | `spatial`, `context`, `coverage` | 면적, 반경, 격자, 공간 범위 | 밀도 보정, 공간 규모 차이 보정 | 행정·임의 범위를 실제 활동 반경으로 단정 | density per area, radius count, spatial coverage | source_ref, 기준일, 공간 정의, join key, coverage | 공간 정의·거리 기준 누락 시 WARN |
| `competition` | `competition`, `context`, `coverage` | 동일/유사 대상 수, 공급자 수, 경쟁군 밀도 | 경쟁 강도, 공급 구조, category mix 비교 | 경쟁 많음=실패 단정 | same-category count, concentration, share, overlap index | source_ref, 기준일, category mapping, grain, join key, coverage | 원본 데이터와 중복 산정 여부 점검 |
| `mobility` | `spatial`, `context`, `coverage` | 접근성, 거리, 이동시간, 네트워크 연결성 | 접근성 context, 이동 제약 비교 | 접근성=성과 인과 단정 | distance/time percentile, accessibility score, network reach | source_ref, 기준일, 계산 방식, join key, coverage | 공간 join 방식과 계산 기준 누락 시 WARN |
| `custom` | 기존 layer 중 선택 | 정식 category 전 단계의 1회성 adapter | manifest에 선언한 allowed_uses 범위 | category 의미를 숨겨서 QA를 우회 | adapter별 선언 KPI | source_ref, 기준일, grain, join key, coverage, limitations | 반복 패턴이면 category 승격 검토 |

## `business_dynamics` Category

`business_dynamics`는 특정 산업 전용 category가 아니다. 개시·종료, churn, 생존,
해지, 재방문 중단, 상태 변화처럼 "얼마나 안정적이거나 이탈이 큰가"를 설명하는
context layer다.

적용 범위는 좁게 둔다.

- 새 metric layer는 만들지 않는다. `business_dynamics`는 `context`와 `coverage`만
  허용한다.
- 기존 `custom + context` manifest는 계속 유효하다. 과거 run 재검증을 깨지 않는다.
- 신규 churn, survival, open/close, status-change adapter는 가능하면
  `category=business_dynamics`를 쓴다.
- 보고서와 대시보드는 안정성, 이탈 리스크, 회전율, 변동성 context까지만 말한다.

## 금지 표현 Guard

다음 표현은 해당 표현이 "금지/한계/단정 불가" 문맥이 아닌 결론 문장에 나오면
QA가 WARN 또는 BLOCK해야 한다.

- 외부 context가 없거나 규모 보정만 있음: `수요 확정`, `성과 확정`, `성공 확정`,
  `수익성`, `시장성 확정`, `원인 확정`
- `business_dynamics`만 있음: `추천`, `성공 가능성 확정`, `수익성 높음`
- `sales`만 있음: `순이익`, `수익성 확정`, `성공 가능성 확정`
- `rent`/cost layer만 있음: `좋은 후보 확정`, `수익성`, `성과 개선 확정`

복수 adapter가 있어도 하나의 종합 점수로 즉시 합치지 않는다. 결합 점수를 만들면
원천 layer별 KPI, 가중치, 금지 해석, 반대 해석을 같이 제시한다.
