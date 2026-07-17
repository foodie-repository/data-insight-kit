# Expert-Guided Analysis Routing Spec

Status: draft for implementation planning

이 문서는 `data-insight-kit`을 쉬운 분석부터 심화 통계/ML 분석, 도메인 전문가 지식 반영까지
확장하기 위한 개발 기준 문서다. 최종 런타임 단일 원천은 계속
`docs/pipeline-contract.md`이며, 이 문서는 구현 전 결정사항을 모으고 구현 중 흔들리지
않게 하기 위한 spec이다. 구현 중 판단이 바뀌면 이 문서를 먼저 수정한 뒤 코드, schema,
QA, 사용자 문서에 반영한다.

## 1. 제품 목표

`data-insight-kit`은 "쉽고 빠르게 대시보드를 만들어주는 도구"에 머물지 않는다. 목표는
초보자도 분석가의 사고 절차를 따라 데이터 분석, 시각화 차트, 대시보드, 보고서를 만들 수
있게 하는 것이다.

핵심 포지션은 다음과 같다.

- 표면은 쉽게: 사용자는 분석 방법 이름을 몰라도 목적과 데이터만 설명하면 된다.
- 본질은 전문적으로: kit은 분석가처럼 데이터 구조, 품질, 전처리, EDA, 분석 방향, 결과
  검토, 시각화, 보고서 품질을 단계적으로 확인한다.
- 하나의 통합 kit: 통계분석 kit, 도메인 kit, 대시보드 kit을 따로 만들지 않는다.
- 내부 라우팅: 데이터와 목적에 따라 기본 분석, 진단 분석, 통계 분석, ML 탐색, 예측,
  실험/인과 분석 경로를 추천하고 사용자의 승인을 받는다.
- 도메인 전문가 협업: 특정 산업별 kit을 만드는 대신, 도메인 전문가에게 필요한 질문을
  하고 그 답변을 분석 계약에 반영한다.

## 2. Design Decisions From Discussion

이번 구현에서 고정한 결정은 다음과 같다.

- 새 작업은 코드부터 시작하지 않고 이 spec과 checklist를 먼저 작성한다.
- spec은 결정 완료 문서여야 하며, 구현자가 핵심 정책을 다시 판단하지 않게 한다.
- `docs/pipeline-contract.md`는 런타임 단일 원천으로 유지한다.
- 기존 `dashboard_data.json -> dashboard.html` 순수 SVG 렌더링 계약은 유지한다.
- ECharts, Plotly, Seaborn, Matplotlib은 v1에서 core renderer로 바꾸지 않는다.
- 통계 분석은 별도 kit이 아니라 optional route다.
- v1은 전체 통계/ML 자동화가 아니라 routing, registry, dependency approval, guard, 대표 통계
  후보 판정까지 구현한다.
- v2 이후는 지금 상세 구현 계획으로 확정하지 않는다. 이 문서에는 phase별 방향 기준만 두고,
  v1 구현과 실제 run 검증 이후 별도 spec/checklist를 작성한다.
- `analysis_result_review`는 모든 run에 강제하지 않고 조건부 hard gate로 둔다.
- dependency 설치는 사용자가 승인하면 kit이 직접 수행한다.
- dependency 승인은 별도 checkpoint가 아니라 `analysis_strategy` checkpoint 안에서 분석
  방향과 함께 받는다.
- silent install, 전역 Python 설치, registry에 없는 패키지 설치는 금지한다.
- 도메인 대응은 특정 산업 pack을 많이 만드는 방식이 아니라 cross-domain expert-guided
  analysis로 설계한다.
- domain pack보다 run-local domain expert interview가 우선이다.
- 도메인 지식이 부족하면 도메인 결론, 추천, 원인, 성과 판단은 차단하고 일반 구조 분석만
  허용한다.
- 데이터 증거와 도메인 전문가 기준은 분리해서 기록한다.

구현 전 계획 리뷰(2026-07-10)에서 추가로 확정한 결정은 다음과 같다.

- 체크포인트 번호는 절대 재배열하지 않는다. `analysis_result_review`는 고정 prefix
  `05_`를 쓰고 기존 `01`~`04`는 불변이다. 실행 순서는 이 문서와
  `docs/pipeline-contract.md`의 실행 순서 정의가 결정하며, 파일명 번호가 결정하지 않는다.
- `analysis_result_review` 발동 여부는 에이전트가 기록한 플래그가 아니라 구조화 필드로
  계산하는 결정적 술어다. stage guard와 QA는 이 술어를 각자 재계산한다.
- dependency 설치 대상은 data-insight-kit 자체 `pyproject.toml` + kit 전용 `.venv`다.
  optional extra는 v1에서 `stats`, `ml` 2개만 둔다.
- `analysis_strategy` 질문 JSON은 승인 시점의 `method_route.json`,
  `dependency_plan.json` sha256을 내장한다. 승인 후 route 상향 변경은 재승인이 필요하다.
- 설치 승인은 명시 옵션 선택만 인정한다. free-text 답변은 설치 승인으로 인정하지 않는다.
- method registry 파일은 `methods/method_registry.json`(JSON)이다. 결정적 코어(guard,
  preflight, QA)는 stdlib+jsonschema만 쓰는데, YAML을 쓰면 registry를 읽기 위해 별도
  의존성 설치가 필요해져 승인형 설치 흐름과 모순되기 때문이다.

## 3. 전체 Workflow

### 3.1 일반 분석 흐름

일반 분석은 기존 guided pipeline을 유지한다.

```text
intake
-> connect
-> explore
-> data_profile checkpoint
-> frame
-> analysis_strategy checkpoint
-> analyze
-> dashboard_storyboard checkpoint
-> visualize
-> qa
-> report_outline checkpoint
-> communicate
-> qa-post
```

일반 분석에서는 `analysis_result_review`를 따로 만들지 않는다. 대신 `dashboard_storyboard`
checkpoint 안에 1차 분석 결과 요약과 차트 구성안을 함께 보여준다.

### 3.2 심화 분석 흐름

심화 분석은 `analysis_strategy` checkpoint에서 분석 깊이와 dependency 설치 필요 여부를 함께
승인받는다.

```text
frame
-> method_route 생성
-> dependency_preflight
-> analysis_strategy checkpoint
   - 설치하고 심화 분석 진행
   - 설치 없이 기본/진단 분석 진행
   - 분석 방향 다시 조정
-> 승인된 dependency 설치
-> analyze
-> analysis_result_review checkpoint, 조건부
-> dashboard_storyboard checkpoint
```

심화 route로 진행하더라도 데이터 조건이 부족하면 route를 강등한다. 예를 들어 비교군,
표본 단위, 타깃 변수, 분모, 기준 기간이 부족하면 통계/예측/인과 route를 기본 또는 진단
route로 낮춘다.

### 3.3 Domain Expert-Guided 흐름

도메인 모드는 특정 산업 전용 기능이 아니다. 금융, 제조, 반도체, 자동차, 식품, 영업,
마케팅, 서비스, 운영 데이터처럼 도메인 전문가만 아는 용어, 기술 개념, KPI, 코드값,
제외 규칙이 있는 데이터를 다루기 위한 공통 흐름이다.

```text
domain mode 감지
-> domain expert interview
-> domain_intake.json 생성
-> data_profile checkpoint에서 데이터 해석 확인
-> domain_readiness 판정
-> analysis_strategy checkpoint에서 KPI/route/설치/도메인 기준 승인
-> analyze
-> analysis_result_review checkpoint, domain mode에서는 조건부 필수
-> dashboard/report 반영
-> domain_pack_update_candidates.md 생성, 필요 시
```

domain pack이 있더라도 그것만으로 자동 결론을 만들면 안 된다. domain pack은 반복 가능한
도메인 기준이고, 이번 분석의 실제 의도와 데이터 특성은 run-local `domain_intake.json`에
확정한다.

## 4. 분석가식 사고 절차

kit은 다음 사고 절차를 사용자에게 자연스럽게 안내해야 한다.

1. 목적 확인: 이 분석으로 어떤 판단이나 행동을 할지 확인한다.
2. 데이터 구조 확인: 행의 의미, 컬럼, 기간, grain, source, 표본을 확인한다.
3. 데이터 품질 확인: 결측, 중복, 이상값, 제외 대상, 인코딩, 타입 변환을 확인한다.
4. 전처리 판단: 정규화, long/wide 변환, 코드 매핑, 필터링, 외부 기준 조인이 필요한지 판단한다.
5. EDA: 분포, 구성, 추세, 관계, 세그먼트, 예외, 데이터 품질 신호를 본다.
6. 분석 방향 선택: 데이터가 허용하는 질문과 허용하지 않는 질문을 분리한다.
7. 분석 깊이 routing: 기본, 진단, 통계, ML, 예측, 실험/인과 route를 추천한다.
8. 1차 분석 실행: 선택 route와 method registry에 맞춰 분석한다.
9. 결과 검토: 심화/도메인/의사결정형 run은 결과가 목적과 도메인 기준에 맞는지 확인한다.
10. 시각화 설계: 각 차트가 하나의 질문에 답하도록 설계한다.
11. 대시보드 구성: 독자와 목적에 맞는 dashboard profile과 흐름을 정한다.
12. 보고서 구성: 독자, 깊이, 결론 수위, 한계, 반대 해석을 확정한다.
13. QA: schema, lineage, checkpoint, render, 통계/도메인 과잉해석을 검증한다.

## 5. Analysis Depth Routing

### 5.1 Route 값

`method_route.json`은 다음 route 중 하나를 선택한다.

| route | 목적 | 예시 질문 | 기본 dependency |
|---|---|---|---|
| `descriptive` | 현재 구조 요약 | 무엇이 많고 적은가? 분포는 어떤가? | core |
| `diagnostic` | 차이, 집중, 예외 진단 | 어떤 세그먼트가 두드러지는가? 어디가 예외인가? | core |
| `statistical` | 차이/관계의 통계적 확인 | 차이가 우연일 가능성이 큰가? 관계가 있는가? | stats |
| `ml_exploratory` | 패턴/군집/이상치 탐색 | 자연스럽게 묶이는 그룹이나 이상치가 있는가? | ml |
| `predictive` | 예측/분류 후보 | 무엇을 예측할 수 있고 검증 가능한가? | ml |
| `causal_experiment` | 실험/전후/처리 효과 검토 | 이 조치가 결과를 바꿨다고 말할 수 있는가? | stats |

### 5.2 Route 선택 기준

기본 판단은 다음 순서로 한다.

1. 사용자 목적이 단순 현황 파악이면 `descriptive`.
2. 목적이 세그먼트 차이, 예외, 병목, 후보 선별이면 `diagnostic`.
3. 비교군과 수치형 결과, 표본 조건이 있고 "차이가 의미 있는지"가 핵심이면 `statistical`.
4. 라벨 없이 패턴, 군집, 이상치를 찾고 싶고 도메인 검토가 가능하면 `ml_exploratory`.
5. 예측 타깃, 시간 기준, 검증 구조, 누수 방지 기준이 있으면 `predictive`.
6. 처리군/대조군, 전후 기간, 교란요인 검토가 가능하면 `causal_experiment`.

### 5.3 강등 조건

다음 조건에서는 심화 route를 낮춘다.

- 비교군이 업무적으로 타당하지 않다.
- 표본 수가 작거나 표본 단위가 독립적이지 않다.
- 분모, 단위, 기준 기간이 없다.
- 예측 타깃 또는 검증 기간이 없다.
- 미래 정보 누수 가능성을 배제할 수 없다.
- 처리군/대조군 또는 전후 기간이 불명확하다.
- 도메인 전문가가 핵심 KPI나 코드값 의미를 확정하지 못했다.
- dependency 설치가 승인되지 않았거나 실패했다.

강등 결과는 `method_route.json`에 `downgraded_from`, `downgrade_reason`,
`allowed_scope`로 기록한다. 강등은 사유 기록만으로 허용하지만, 승인 이후의 route
상향(예: `descriptive` → `statistical`)은 `analysis_strategy` 재승인이 필요하다.

## 6. Method Registry

`methods/method_registry.json`은 LLM이 임의로 분석 방법을 invent하지 않게 하는 기준이다.
JSON을 쓰는 이유: 결정적 코어(preflight, guard, QA)는 stdlib+jsonschema만 사용하며,
registry를 읽기 위해 YAML 파서 설치가 필요하면 승인형 설치 흐름과 모순된다.
route별 기본 dependency group의 단일 원천은 이 registry이며, §5.1 표의 dependency
컬럼은 참고용 요약이다.

각 method는 최소한 다음 정보를 가진다.

```json
{
  "id": "group_difference_candidate",
  "route": "statistical",
  "label": "그룹 차이 후보 판정",
  "requires": {
    "data_conditions": ["numeric_measure", "categorical_group", "sample_size_check"],
    "domain_conditions": ["group_definition_valid", "measure_definition_valid"]
  },
  "dependency_groups": ["stats"],
  "allowed_questions": ["그룹 간 차이가 우연인지 확인할 필요가 있는가?"],
  "blocked_claims": ["원인 단정", "효과 확정"],
  "recommended_charts": ["boxplot", "bar", "confidence_interval"]
}
```

v1 registry 범위는 다음으로 제한한다.

- core: ranking, distribution, composition, trend, quality.
- stats: group difference candidate, correlation candidate, simple regression candidate,
  confidence interval candidate.
- ml: clustering candidate, anomaly candidate, dimensionality reduction candidate.

v1은 다중 회귀 자동 모델링, 예측 모델 학습/튜닝, 군집 자동 명명, A/B test 전체
자동화를 목표로 하지 않는다.

## 7. Dependency Approval and Install

### 7.1 Dependency groups

data-insight-kit 자체 `pyproject.toml`의 optional extra는 v1에서 다음 2개 group만 둔다.

| group | 역할 | 대표 패키지 |
|---|---|---|
| `stats` | 통계 검정, 회귀 후보, 신뢰구간, 진단 그래프 | scipy, statsmodels, matplotlib, seaborn |
| `ml` | 클러스터링, 이상치, 차원축소, 예측 후보 | scikit-learn |

`interactive-viz`(plotly)와 `echarts`(renderer adapter)는 v4 시각화 확장에서 다룬다.
v1에서 group을 미리 만들지 않는다. group 추가는 비파괴적 확장이다.

### 7.2 승인 위치

dependency 승인은 `analysis_strategy` checkpoint 안에서 받는다. 별도
`dependency_approval` checkpoint는 만들지 않는다.

사용자에게는 다음을 함께 보여준다.

- 추천 분석 깊이.
- 설치가 필요한 이유.
- 설치되는 extra group.
- 설치하면 가능한 분석.
- 설치하지 않으면 가능한 대체 분석.
- 설치 실패 시 fallback.

선택지는 기본적으로 다음 형태다.

1. 설치하고 심화 분석 진행.
2. 설치 없이 기본/진단 분석 진행.
3. 분석 방향 다시 조정.

답변 매핑 계약:

- 각 선택지는 기존 `maps_to.checkpoint_decision`에 더해
  `maps_to.dependency_decision: "install" | "skip_install" | "adjust"`를 가진다.
- 설치 승인(`install`)은 명시 옵션 선택으로만 인정한다. free-text 답변은
  `continue_pipeline`이 참이어도 설치 승인으로 해석하지 않는다. free-text로 진행한
  run은 `skip_install`로 처리하고 route를 core-only 범위로 강등한다.
- 설치가 필요 없는 run(설치 대상 extra 없음)에서는 dependency 선택지를 만들지 않고
  기존 선택지를 유지한다.

승인 시점 잠금:

- `analysis_strategy` 질문 JSON은 생성 시점의 `method_route.json`과
  `dependency_plan.json`의 sha256을 `approval_targets`에 내장한다.
- 승인 후 두 파일이 승인 시점 hash와 달라지면, route 상향·extra 추가 방향의 변경은
  질문 재생성과 재승인이 필요하다. 강등(route 하향, 설치 축소)은
  `downgrade_reason` 기록만으로 허용한다. 이 검증은 stage guard와 QA가 수행한다.

### 7.3 실행 원칙

- 사용자가 승인하기 전에는 설치하지 않는다.
- 전역 Python에 설치하지 않는다.
- 설치 대상 환경은 data-insight-kit 자체 `pyproject.toml`이 정의하는 kit 전용
  `.venv`다(`uv sync --project data-insight-kit --extra <group>`). 상위 워크스페이스
  `.venv`나 전역 site-packages에 설치하지 않는다.
- `scripts/dependency_preflight.py`의 설치 여부 판정도 kit 전용 `.venv`를 기준으로
  한다. 다른 환경(워크스페이스 venv 등)에 같은 패키지가 있어도 "설치됨"으로 보지
  않는다.
- 이미 kit 환경에 설치된 group은 설치 승인 절차를 생략하되,
  `dependency_plan.json`에 `already_installed`로 기록하고 route 승인은 동일하게 받는다.
- registry와 allowlist에 없는 패키지는 설치하지 않는다.
- 설치 실패 시 원인을 보고하고 route를 강등한다. 강등된 계획은 §7.2의 승인 시점
  잠금 규칙을 따른다(강등은 사유 기록으로 허용, 상향은 재승인).
- 설치 승인 provenance는 `checkpoint_answers.json`의 해당 답변 `answer_id`를
  `dependency_plan.json.approval.answer_id`로 연결해 기록한다.

## 8. Domain Expert Intelligence

### 8.1 목표

도메인 영역은 특정 산업별 kit을 만드는 방식으로 해결하지 않는다. 목표는 어떤 도메인이든
도메인 전문가가 가진 지식을 구조화해 분석에 반영하는 것이다.

도메인 전문가 인터뷰는 다음 문제를 해결한다.

- AI가 모르는 내부 용어와 기술 개념.
- 컬럼명만으로 알 수 없는 데이터 의미.
- 업무적으로 타당한 KPI, 분모, 단위, 비교 기준.
- 분석에서 제외해야 하는 테스트, 취소, 비정상, 내부용, 중복 데이터.
- 데이터로 말하면 안 되는 원인, 성과, 추천, 위험 판단.
- 분석 결과가 업무적으로 말이 되는지 검토.

### 8.2 Domain mode 발동 조건

다음 중 하나라도 해당하면 domain mode 후보로 본다.

- `DIK_DOMAIN_PACK` 또는 `runs/<run-id>/input/domain_pack_ref.txt`가 있다.
- 사용자가 회사, 업무, 내부 데이터, 전문 도메인, 제조, 금융, 영업, 마케팅, 서비스 등
  도메인 데이터임을 말한다.
- domain pack activation hint가 사용자 요청 또는 source hint와 맞는다.
- 데이터 컬럼에 내부 코드, 공정, 장비, 고객 등급, 제품 체계, 상태 코드처럼 해석이 필요한
  값이 많다.

확신이 낮으면 바로 domain mode를 확정하지 말고 사용자에게 묻는다. 확정된 domain mode는
`domain_intake.json` 또는 `manifest`에 기록한다.

### 8.3 Domain expert interview lifecycle

도메인 질문은 한 번에 모두 묻지 않는다. 단계별로 필요한 불확실성만 묻는다.

1. 시작 전: 목적, 의사결정, 독자, 도메인 범위.
2. 데이터 확인 후: 행의 의미, grain, 컬럼/코드값, 제외 규칙, 품질 이슈.
3. 분석 전략 전: KPI, 분모, 단위, 비교 기준, 금지 해석, 필요한 reference data.
4. 결과 검토 시: 1차 결과가 도메인적으로 말이 되는지, 강한 결론을 낮춰야 하는지.
5. 보고서 전: 독자별 용어, 문체, 공개 가능 범위, 피해야 할 표현.

### 8.4 Domain artifacts

Domain mode는 다음 run-local artifact를 사용한다.

```text
runs/<run-id>/input/domain_intake.json
runs/<run-id>/input/domain_knowledge_brief.md
runs/<run-id>/outputs/domain_pack_update_candidates.md
```

`domain_intake.json`은 다음 범주를 가진다.

- `domain_scope`: 산업/업무/조직/분석 대상 범위.
- `objective`: 도메인 맥락에서 내릴 판단.
- `row_meaning`: 행 1개가 의미하는 업무 단위.
- `entity_grain`: 고객, 상품, 장비, wafer, lot, 지점, 거래 등 핵심 엔티티.
- `time_grain`: 일, 주, 월, 공정 시점, 이벤트 시점 등 시간 단위.
- `terminology`: 내부 용어와 사용자용 표현.
- `column_semantics`: 컬럼과 코드값의 업무 의미.
- `exclusion_rules`: 제외해야 할 행, 상태, 테스트, 취소, 중복, 특수 케이스.
- `kpi_definitions`: KPI 이름, 계산식, 단위, 분모, 비교 기준, 필요한 데이터.
- `segments`: 업무적으로 의미 있는 세그먼트와 비교축.
- `reference_data`: 필요한 기준표, 마스터, 코드북, 외부 benchmark.
- `forbidden_claims`: 금지 표현과 허용 조건.
- `evidence_boundaries`: 데이터로 직접 말할 수 있는 것과 없는 것.
- `open_questions`: 아직 답하지 못한 도메인 질문.

`domain_knowledge_brief.md`는 사용자가 읽는 요약본이다. 내부 JSON을 길게 보여주지 않고,
현재 이해, 부족한 점, 이번 분석에 반영되는 기준, 막히는 결론을 쉬운 말로 정리한다.

`domain_pack_update_candidates.md`는 이번 run에서 나온 반복 가능한 도메인 지식 후보를 남긴다.
자동으로 `domains/<domain>/`를 수정하지 않는다.

### 8.5 Domain readiness

`domain_readiness`는 도메인 결론을 내릴 수 있는지 판단하는 상태다.

`domain_readiness.status`는 에이전트가 임의로 기록하는 값이 아니다. 아래 공통 필수
항목과 route별 필수 항목의 충족 여부에서 **결정적으로 계산**되며, QA는 같은 규칙으로
status를 재계산해 기록값과 다르면 BLOCK한다. 에이전트가 `ready`라고 써도 필수 항목이
비어 있으면 `insufficient`로 취급한다.

| status | 의미 | 허용 범위 |
|---|---|---|
| `ready` | 핵심 용어, grain, KPI, 분모, 제외 규칙, 금지 해석이 충분함 | 도메인 진단과 제한적 의사결정 지원 |
| `partial` | 일부 기준은 있으나 결론 수위에 필요한 항목이 부족함 | 제한적 도메인 해석, 강한 결론 차단 |
| `insufficient` | 행/컬럼/KPI/금지 해석 등 필수 정보가 부족함 | 일반 구조 분석만 허용 |

공통 필수 항목은 다음이다.

- 행 1개의 의미.
- 핵심 엔티티와 분석 grain.
- 주요 컬럼과 코드값의 업무 의미.
- 제외해야 할 데이터.
- 분석 목적과 실제 의사결정.
- 금지 표현 또는 위험한 해석.

route별 추가 필수 항목은 method registry가 요구한다. 예를 들어 통계 route는 업무적으로
타당한 비교군과 결과 변수 정의가 필요하고, 예측 route는 타깃과 예측 시점, 누수 금지 기준이
필요하다.

### 8.6 Evidence separation

도메인 분석에서는 증거 출처를 분리한다.

| evidence class | 의미 |
|---|---|
| `observed_from_data` | 이번 run input에서 직접 계산한 사실 |
| `domain_rule` | 도메인 전문가 또는 domain pack이 제공한 업무 기준 |
| `inferred` | 데이터 사실과 도메인 기준을 결합한 해석 |
| `unsupported` | 현재 데이터와 도메인 기준으로는 말할 수 없는 주장 |

보고서와 dashboard 문구는 `unsupported` 주장을 결론처럼 쓰면 안 된다.

## 9. Conditional Analysis Result Review

`analysis_result_review`는 조건부 checkpoint다.

발동 여부는 에이전트 판단이 아니라 다음 **결정적 술어**로 계산한다. 모든 입력은
구조화 필드다.

```text
required =
     method_route.route ∈ {statistical, ml_exploratory, predictive, causal_experiment}
  OR domain_mode == true          (domain_intake.json 존재 또는 manifest.domain_mode
                                   또는 input/run_context.json의 domain_mode —
                                   wrapper `--domain-mode` 플래그가 스탬프, 재실행에도 유지)
  OR intake.report.depth == "deep"
  OR intake.analysis_mode ∈ {candidate_prioritization, risk_screening}
```

- stage guard와 QA는 이 술어를 **각자 재계산**한다. 에이전트나 wrapper가 기록한
  `review_required` 류 불리언은 편의 정보일 뿐 판정 근거로 신뢰하지 않는다.
  플래그를 쓰지 않는 방식으로 게이트를 우회할 수 없어야 한다.
- `method_route.json`에는 계산 결과와 충족된 조건 목록을 provenance로 기록한다.
- 술어가 거짓이면 발동하지 않는다: 단순 분포·순위·구성·품질 점검 중심의 일반 분석,
  빠른 현황 요약 요청이 여기에 해당한다.

checkpoint 질문은 다음을 확인한다.

- 1차 발견이 사용자의 목적과 맞는가.
- 통계/ML 결과를 더 깊게 볼지, 기본 분석으로 낮출지.
- 도메인 전문가 관점에서 해석이 말이 되는가.
- 결론 수위를 낮춰야 하는가.
- dashboard storyboard로 넘어가도 되는가.

## 10. QA and Guardrails

### 10.1 기존 guard 유지

다음 guard는 유지한다.

- fresh-by-default.
- prior run reference opt-in.
- checkpoint v3 provenance.
- Plan Mode approval을 checkpoint approval로 재사용 금지.
- downstream artifact가 승인보다 먼저 만들어지면 BLOCK.
- `dashboard_data.json` schema 및 render QA.
- report depth QA.

### 10.2 새 QA 항목

이번 spec은 다음 QA를 추가한다.

- `method_route.json`이 schema를 통과해야 한다.
- route와 method가 registry에 존재해야 한다.
- route 조건이 부족하면 강등 또는 BLOCK한다.
- dependency 설치가 필요한 route는 승인 provenance(`approval.answer_id` 연결)가
  있어야 한다.
- allowlist 외 dependency 설치 시도는 BLOCK한다.
- §9 술어가 참인 run에서 `analysis_result_review` 승인 provenance가 없으면 BLOCK한다.
  QA는 술어를 스스로 재계산한다.
- `analysis_strategy` 승인 시점의 `approval_targets` sha256과 현재
  `method_route.json`/`dependency_plan.json`이 다르고 변경 방향이 상향이면 BLOCK한다.
- domain mode인데 `domain_intake.json`이 없으면 도메인 결론은 BLOCK한다.
- `domain_readiness=insufficient`(QA 재계산 기준)에서 추천, 원인, 성과, 위험도 확정
  표현은 BLOCK한다.
- domain `forbidden_claims`의 명시 문구가 dashboard/report visible text에 나오면
  BLOCK한다.
- 그 외 원인·효과·추천 단정에 대한 일반 휴리스틱 언어 검사(예: p-value·상관계수만으로
  단정)는 **WARN으로 시작**한다. 대표 run으로 오탐률을 보정한 뒤에만 BLOCK으로
  승격한다. 부정문("~로 단정할 수 없다")을 BLOCK하지 않도록 한다.
- 예측 route에서 타깃, 검증 기간, 누수 금지 기준이 없으면 BLOCK한다.

QA는 사후 검증이므로, "승인 없는 설치"의 실행 시점 차단은 QA가 아니라
`dik_checkpoint_hook.py`가 담당한다. hook은 kit run 컨텍스트에서
`pip install`, `python -m pip install`, `uv add`, `uv sync --extra` 형태의 Bash 명령을
감지해, 유효한 dependency 승인 provenance가 없거나 대상 패키지가 allowlist 밖이면
deny한다. run 진행 중 `domains/<domain>/` 자동 수정 write도 deny 대상이다.

## 11. Public/User-Facing Language

사용자에게는 내부 용어를 그대로 노출하지 않는다.

| 내부 용어 | 사용자 표현 |
|---|---|
| `data_profile` | 데이터 확인 단계 |
| `analysis_strategy` | 분석 방향 확인 단계 |
| `analysis_result_review` | 1차 결과 확인 단계 |
| `dashboard_storyboard` | 대시보드 구성안 확인 단계 |
| `method_route` | 분석 깊이와 방법 선택 |
| `dependency_plan` | 추가 분석 기능 준비 |
| `domain_readiness` | 도메인 기준 확인 상태 |

통계 기능도 쉬운 말로 설명한다.

- "t-test"보다 "두 그룹 차이가 우연인지 확인".
- "regression"보다 "어떤 요인이 결과와 함께 움직이는지 후보 확인".
- "clustering"보다 "비슷한 대상을 자연스럽게 묶어보기".

## 12. Phased Roadmap

이 roadmap은 상세 구현 계획이 아니다. v1 구현자가 이후 확장을 막는 결정을 하지 않도록
phase별 방향과 경계를 정하는 skeleton이다. v2 이후의 상세 spec과 checklist는 v1 구현,
대표 run 검증, 사용자 피드백을 확인한 뒤 별도로 작성한다.

### 12.1 v1: Contract Foundation

목표는 통합 kit의 확장 가능한 기반을 만드는 것이다.

- 새로 가능해지는 경험: 사용자가 데이터와 목적을 제시하면 kit이 분석 깊이를 추천하고,
  필요한 경우 dependency 설치와 결과 검토를 승인받는다.
- 포함: analysis depth routing, method registry, dependency approval/install, 조건부
  `analysis_result_review`, `domain_intake`, `domain_readiness`, 대표 통계 route 후보 판정.
- 열어둘 확장 지점: route/method schema, checkpoint numbering, dependency group, domain
  artifact 위치, renderer hint.
- 하지 않을 일: 전체 통계/ML 자동화, 산업별 domain pack 완성, core renderer 전환.
- 완료 기준: 단순 분석, 심화 route 후보, domain mode 후보가 모두 기존 checkpoint/QA guard와
  충돌하지 않고 동작한다.

### 12.2 v2: Domain Expert Workflow

목표는 회사·전문 도메인 데이터에서 도메인 전문가와 협업하는 흐름을 강화하는 것이다.

- 새로 가능해지는 경험: 사용자가 도메인 용어, KPI, 코드 의미, 제외 규칙, 업무 맥락을
  설명하면 kit이 이를 분석 계약과 질문 흐름에 반영한다.
- 포함 후보: domain expert interview 강화, 용어집/KPI/금지 결론 구조화, domain pack 재사용
  및 승격 후보 관리, domain readiness 기반 질문 재시도.
- v1에서 열어둘 지점: `domain_intake.json`과 `domain_pack_update_candidates.md`를 run-local
  artifact로 유지하고, domain pack 자동 수정은 금지한다.
- 하지 않을 일: 특정 산업 전용 kit 제작, 도메인 전문가 승인 없는 원인/추천/성과 단정.
- 완료 기준: domain knowledge가 부족한 run에서는 도메인 결론이 차단되고, 충분한 run에서는
  제한적 도메인 진단이 checkpoint와 QA를 거쳐 반영된다.

### 12.3 v3: Advanced Statistical and ML Analysis

목표는 통계/ML route의 실행과 해석 보조를 넓히는 것이다.

- 새로 가능해지는 경험: 사용자가 차이, 관계, 군집, 이상치, 예측 후보를 더 깊게 검토하되,
  가정과 한계, 반대 해석을 함께 확인한다.
- 포함 후보: 통계 검정 확대, 회귀 진단, 군집/이상치/차원축소 결과 검토, 예측 후보의 누수
  방지와 검증 구조 확인.
- v1에서 열어둘 지점: method registry가 method별 전제 조건, dependency, blocked claim,
  recommended chart를 확장 가능하게 가진다.
- 하지 않을 일: 검증 구조 없는 예측 자동화, 통계 결과를 원인/효과/추천으로 단정.
- 완료 기준: 심화 분석 결과가 `analysis_result_review`에서 사용자 목적, 데이터 조건, 도메인
  조건에 맞는지 검토된 뒤에만 dashboard/report로 이어진다.

### 12.4 v4: Visualization and Renderer Expansion

목표는 최종 대시보드와 탐색/진단 시각화의 역할을 나누고 renderer 선택지를 넓히는 것이다.

- 새로 가능해지는 경험: 사용자는 정적 대시보드뿐 아니라 필요할 때 EDA·진단용 인터랙티브
  차트를 함께 검토할 수 있다.
- 포함 후보: ECharts renderer backend, Plotly 진단 부록, renderer hint, chart_spec 기반
  renderer adapter. optional extra `interactive-viz`, `echarts`도 이 phase에서 추가한다
  (v1은 `stats`, `ml`만 둔다).
- v1에서 열어둘 지점: `dashboard_data.json -> dashboard.html` 계약을 유지하되
  `chart_spec`에 renderer hint를 둘 수 있게 한다.
- 하지 않을 일: 검증된 core dashboard 계약을 깨는 renderer 교체.
- 완료 기준: 같은 분석 계약에서 core SVG 대시보드와 선택 renderer가 서로 다른 결론을 만들지
  않고, render QA가 backend별로 분리된다.

### 12.5 v5: Team and Enterprise Readiness

목표는 개인 분석 kit을 회사 내부 반복 분석 환경으로 확장할 수 있게 하는 것이다.

- 새로 가능해지는 경험: 팀은 domain pack, 승인 이력, QA 규칙, 보고서 템플릿을 재사용하고
  감사 가능한 분석 흐름을 유지한다.
- 포함 후보: domain pack versioning, approval/audit trail, PII/security guard, 팀 template 및
  method library 운영.
- v1에서 열어둘 지점: run-local provenance와 checkpoint lineage를 잃지 않고, 사용자 승인과
  자동 산출물을 분리한다.
- 하지 않을 일: 보안/권한/배포 정책을 일반 분석 계약 안에 섞어 임의 구현.
- 완료 기준: 회사 도메인 데이터에서도 누가 어떤 기준으로 승인했고 어떤 근거로 결론을 냈는지
  추적할 수 있다.

## 13. Non-goals

이번 구현에서 하지 않는 일은 다음이다.

- 산업별 전용 kit 제작.
- 반도체, 금융, 자동차 등 특정 domain pack 완성.
- 모든 통계/ML 자동화.
- 다중 회귀 모델링 자동 완성.
- 예측 모델 학습/튜닝 자동화.
- A/B test 전체 자동화.
- ECharts/Plotly를 core renderer로 즉시 전환.
- domain pack 자동 수정.
- 사용자 승인 없는 dependency 설치.
- 전역 Python 환경 변경.

## 14. Implementation Handoff

구현은 다음 순서로 진행한다.

1. 이 spec과 checklist를 검토하고 필요한 결정 변경을 반영한다.
2. `docs/pipeline-contract.md`에 최종 런타임 계약을 반영한다.
3. schema를 추가한다.
4. method registry와 dependency preflight를 추가한다.
5. wrapper와 checkpoint gate를 연결한다.
6. stage guard, Codex/Claude hook, QA를 갱신한다.
7. docs와 skill 문서를 갱신한다.
8. 단순 분석, 심화 분석, domain mode 회귀 테스트를 실행한다.

구현 중 이 문서와 실제 코드가 달라지면 코드에 맞춰 조용히 넘어가지 않는다. 먼저 이 spec을
수정하고 그 다음 구현을 맞춘다.

## 15. Implementation Defaults

구현자가 다시 판단하지 않도록 다음 기본값을 둔다. 구현 중 더 나은 선택이 필요하면 이
섹션을 먼저 수정한다.

- `domain_readiness`는 별도 파일로 만들지 않고 `domain_intake.json` 내부 객체로 둔다.
- `method_route.json`의 canonical 위치는 `runs/<run-id>/outputs/method_route.json`이다.
  wrapper가 prompt 전달을 위해 mirror가 필요하면 생성할 수 있지만, 공식 provenance는
  outputs 파일을 기준으로 한다.
- `dependency_plan.json`의 canonical 위치는 `runs/<run-id>/input/dependency_plan.json`이다.
  설치 전 plan과 설치 후 `install_result`를 같은 파일에 기록한다.
- checkpoint 파일 prefix는 **재배열하지 않는다**. 기존 `01_data_profile`,
  `02_analysis_strategy`, `03_dashboard_storyboard`, `04_report_outline`은 불변이고,
  조건부 결과 검토 질문 파일은 고정 prefix `05_analysis_result_review_question.json|md`를
  쓴다. 파일명 번호는 식별자일 뿐 실행 순서가 아니며, 실행 순서는 pipeline contract가
  정의한다(`05_`는 analyze 직후, `03_` 앞에 온다). 덕분에 legacy dual-read 경로가
  필요 없고, `stage_guard.CHECKPOINT_PREFIXES`·wrapper·hook·QA의 prefix 상수는 정적으로
  유지된다.
- route 상향/강등 판정용 rank는 `descriptive`=0, `diagnostic`=0, `statistical`=1,
  `ml_exploratory`=1, `predictive`=2, `causal_experiment`=2로 둔다. 승인 후 rank가 커지면
  상향(재승인 필요), `downgraded_from` rank가 현재 rank 이상이면 강등(사유 기록으로 허용)이다.
- QA(`qa/validate.py`)의 `analysis_result_review` 승인 provenance 요구는
  `outputs/method_route.json`이 존재하는 run(=v1 routing 파이프라인 run)에만 적용한다.
  routing 도입 이전 legacy run은 이 요구에서 제외한다. 런타임 가드(stage_guard·hook)는
  §9 술어를 무조건 적용하므로 신규 run이 이 경계를 우회할 수 없다 — method_route.json은
  frame 필수 산출물이고, 그 생성 자체가 hook으로 게이트된다.
