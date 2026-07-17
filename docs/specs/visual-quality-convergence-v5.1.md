# Visual Quality Convergence v5.1 — 계획·표현·검수 품질 수렴

상태: **설계 승인됨 — 구현 기준선**
작성일: 2026-07-17
승인: 사용자 원문 `설계 승인` (2026-07-17, user chat)
기반 계약: `docs/specs/dashboard-freeform-v5.md`
구현 체크리스트: `docs/specs/visual-quality-convergence-v5.1-checklist.md`

## 1. 결정

v5.1은 별도 kit나 새 렌더러가 아니다. `data-insight-kit`을 제품 본체로 유지하면서
현재 v5의 승인 레이아웃·결정적 compiler 위에 다음 두 계약을 추가한다.

1. **계획 품질 계약**: 분석 목적, 판단 대상, 지표 역할, 차트별 질문과 데이터
   충분성을 구현 전에 구조화한다.
2. **시각 품질 계약**: 척도, 색, 라벨, 범례, 반응형, 겹침과 가독성을 계획과
   최종 산출물에서 함께 검증한다.

`dashboard_profile_contract`와 renderer 선택 값은 계속 `v5`를 쓴다. v5.1 적용
여부는 `chart_spec.quality_contract.version = "v5.1"`과
`dashboard_layout.quality_contract_version = "v5.1"`로 선언한다. 즉 v5.1은
렌더러 포크가 아니라 v5 입력 계약과 QA의 엄격한 opt-in이다.

## 2. 배경과 문제

v5 smoke에서 자유 레이아웃, 실제 날짜·단위 문구, 분리 시계열, role 기반 색,
compact 출처, 범례/plot 겹침 검사는 안정화되었다. 그러나 좋은 결과를 얻기까지
사용자 검토에서 다음 문제가 반복되었다.

- 카드와 제목이 계산 위치나 내부 용어를 사용해 독자가 기준을 다시 찾아야 했다.
- 차트 유형은 유효해도 계열 수, 관측 수, 단위와 변화폭에 맞는 표현인지가 늦게
  검증되었다.
- 단일색과 다색 중 무엇이 옳은지가 명시적 의미 계약 없이 구현 단계에서
  결정되었다.
- 직접 라벨, 범례, 모바일 강등 전략이 계획에 없어서 렌더 후 반복 수정이 필요했다.
- 1440px와 390px 사이, 390px보다 좁은 화면의 품질이 명시적으로 보장되지 않았다.
- 빈 카드·장식용 구성요소·중복 질문을 줄이는 원칙은 문서에 있으나 일부는
  기계적으로 검증되지 않았다.

v5.1의 목적은 자연스러운 문장을 자동 작성하는 범용 문장 생성기를 만드는 것이
아니다. **무엇을 왜 보여주는지, 어떤 비교를 어떤 척도로 읽는지, 어떤 문맥이
문구에 반드시 포함되어야 하는지를 먼저 고정**하여 에이전트가 작성한 문구와
차트가 검증 가능한 상태가 되게 하는 것이다.

## 3. 참고 원칙과 clean-room 경계

설계 시 공식 Codex `Data Analytics`와 `Visualize` 플러그인의 현재 설치본을
행동 수준에서 검토했다. 반영 대상은 다음처럼 제품에 독립적인 원칙뿐이다.

| 참고 축 | 독립적으로 반영할 원칙 |
|---|---|
| Data Analytics | 의사결정·독자·주기·원천을 먼저 고정하고, 지표 역할과 차트별 질문·근거·대안을 구현 전에 기록하며, 데이터 충분성과 최종 문맥을 함께 검증한다. |
| Visualize | 필요한 최소 구성만 사용하고, 직접 라벨·의미 기반 색·비색상 채널·작은 화면 reflow·최종 눈검토를 통해 실제 읽기 품질을 보장한다. |

다음 경계는 구현·패키징·문서에서 모두 지킨다.

- OpenAI 플러그인의 코드, 프롬프트, 문장, 자산, 스키마를 복사하거나
  재배포하지 않는다.
- plugin cache 경로, `window.openai`, `::codex-inline-vis`,
  `dataAnalyticsWidgets` 등에 런타임 의존하지 않는다.
- 공식 플러그인의 proprietary 패키지를 Claude Code용으로 변환하거나 포함하지
  않는다.
- `/Users/foodie/.codex/skills/visualize`는 별도 목적의 사용자 설치물이며 본 설계의
  참고·의존·패키징 대상에서 제외한다.
- 필드명, 임곗값, renderer와 QA 구현은 기존 data-insight-kit 계약과 두 smoke의
  문제를 기준으로 새로 설계하고 테스트한다.

## 4. 범위

### 4.1 포함

- `chart_spec.json`의 v5.1 계획 품질 계약
- `dashboard_layout.json`의 구성요소 목적·결정 연결 계약
- 차트 선택 충분성, fallback, 척도, 색, 비색상 채널, 라벨·범례·모바일 전략
- 독자 문구에 필요한 실제 범위·기간·지표·단위 문맥
- 빈 카드, 중복 질문, 무의미한 조작 요소를 막는 구성 최소화 게이트
- 1440/736/390/320px browser QA와 모든 생성 screenshot의 직접 눈검토
- Claude Code와 Codex marketplace용 얇은 어댑터
- 기존 snapshot·time-series smoke의 이전/이후 비교

### 4.2 제외

- 새 kit 또는 독립 PoC
- 자연어 문장 생성 전용 모델·템플릿 엔진
- raw HTML/CSS/JavaScript/ECharts option 입력
- CDN, 외부 font, 플러그인 위젯 runtime
- 브라우저에서 KPI·분모를 다시 계산하는 전역 cross-filter
- 원인·인과·추천을 데이터 근거보다 강하게 만드는 자동 서술
- 기존 run의 승인 답변을 새 run에 복사하거나 에이전트가 승인하는 행위

## 5. 전체 흐름

기존 파이프라인과 체크포인트 순서는 바꾸지 않는다.

```text
intake -> connect -> explore -> data_profile 확인
       -> frame -> analysis_strategy 확인
       -> analyze
          ├─ decision brief
          ├─ metric model
          └─ chart visual contracts
       -> dashboard_storyboard 확인
          ├─ v5 layout
          └─ component purpose/decision links
       -> visualize
       -> qa
          ├─ static quality gate
          ├─ browser quality gate (1440/736/390/320)
          └─ screenshot eyes-on record
       -> report_outline 확인 -> communicate -> qa-post
```

계획 품질은 `analysis_strategy`와 `dashboard_storyboard` 사이에서 구조화된다.
사용자가 승인하는 대상은 여전히 실제 `chart_spec.json`과
`dashboard_layout.json`의 revision/hash다. v5.1 메타데이터가 승인 절차를
대체하지 않는다.

## 6. `chart_spec` v5.1 계약

### 6.1 최상위 `quality_contract`

`schemas/chart_spec.schema.json`에 optional `quality_contract`를 추가한다. 값이
있으면 아래 필드를 모두 요구하고, 없으면 기존 legacy/v4/v5 문서는 그대로
유효하다.

```json
{
  "quality_contract": {
    "version": "v5.1",
    "decision_brief": {
      "decision_id": "district-priority-review",
      "primary_audience": "mixed",
      "decision": "가격과 거래량이 엇갈린 지역을 다음 검토 대상으로 좁힌다",
      "review_cadence": "one_off",
      "primary_question": "어느 지역의 가격과 거래량 방향이 가장 크게 엇갈렸는가",
      "source_scope": "서울 25개 구 월별 아파트 매매 집계",
      "freshness_anchor": "2026-06",
      "known_gaps": ["거래 원인 자료는 포함하지 않음"]
    },
    "metrics": [
      {
        "metric_id": "median_price",
        "role": "hero",
        "decision_link": "district-priority-review",
        "definition": "구·월별 실거래 가격의 중앙값",
        "unit": "만원",
        "denominator": null,
        "window": "2022-01~2026-06",
        "source_ref": "outputs/04_analysis.md#median-price"
      }
    ]
  }
}
```

`review_cadence`는 `one_off | periodic | continuous`, metric `role`은
`hero | diagnostic | guardrail | detail`만 허용한다.

- `hero`: 첫 판단에 직접 쓰는 핵심 지표
- `diagnostic`: hero의 차이·예외를 설명하는 지표
- `guardrail`: 결론을 과대해석하지 않게 함께 보는 지표
- `detail`: 표·부록에서 확인하는 상세 지표

각 metric은 단위, 분모, 기간과 source를 명시한다. 해당 개념이 없으면 빈 문자열이
아니라 `null`을 쓴다. dashboard KPI와 chart의 계산은 선언된 metric으로 역추적할
수 있어야 한다.

### 6.2 차트별 `visual_contract`

v5.1 chart는 기존 `question`, `calculation`, `chart`, `insight`에 더해 다음을
가진다.

```json
{
  "visual_contract": {
    "comparison_intent": "movement",
    "family": "trend",
    "variant": "line",
    "data_sufficiency": {
      "status": "sufficient",
      "observed_points": 54,
      "observed_series": 2,
      "minimum_points": 3,
      "minimum_series": 1,
      "fallback_chart": "slope",
      "reason": "54개월의 순서 있는 관측값이 있음"
    },
    "scale_policy": "independent_panels",
    "label_strategy": "direct",
    "legend_strategy": "none",
    "palette_policy": {
      "mode": "categorical_identity",
      "max_color_roots": 2,
      "rationale": "가격과 거래량을 같은 기간의 서로 다른 지표로 구분"
    },
    "non_color_channels": ["label", "line_style", "panel"],
    "mobile_strategy": "stack_panels",
    "copy_context": {
      "title_mode": "conclusion",
      "scope_label": "서울 25개 구",
      "metric_label": "월별 중앙가격과 거래량",
      "comparison_period": "2022-01 대비 2026-06",
      "unit_label": "가격 만원, 거래량 건"
    }
  }
}
```

허용 값은 다음과 같다.

| 필드 | 허용 값 |
|---|---|
| `comparison_intent` | `status`, `movement`, `ranking`, `composition`, `distribution`, `relationship`, `exception`, `progression` |
| `family` | `trend`, `comparison`, `composition`, `distribution`, `relationship`, `matrix`, `decomposition` |
| `data_sufficiency.status` | `sufficient`, `fallback_required`, `not_applicable` |
| `scale_policy` | `zero_baseline`, `shared_scale`, `independent_panels`, `indexed_baseline`, `focused_range_with_cue`, `not_applicable` |
| `label_strategy` | `direct`, `axis`, `legend`, `tooltip`, `mixed` |
| `legend_strategy` | `none`, `direct_labels`, `top`, `right`, `bottom`, `paginated` |
| `palette_policy.mode` | `single_measure`, `semantic_highlight`, `categorical_identity`, `sequential`, `diverging`, `neutral` |
| `non_color_channels` | `label`, `shape`, `line_style`, `open_fill`, `panel`, `order` 중 1개 이상 |
| `mobile_strategy` | `reflow`, `stack_panels`, `direct_labels`, `paginated_legend`, `top_n_with_detail`, `table_fallback` |
| `copy_context.title_mode` | `conclusion`, `descriptive` |

`variant`는 기존 `chart.type`과 일치해야 한다. `family`는 목적상 상위 분류이며
`variant`가 실제 renderer를 선택한다. v5.1은 에이전트가 raw option을 정하는
통로가 아니다.

### 6.3 차트 충분성·fallback 규칙

임곗값은 통계적 유의성을 보장하는 규칙이 아니라, 차트 형태가 질문을 읽을 수
있는 최소 조건이다. 도메인 팩이 더 엄격한 조건을 선언할 수 있으나 완화할 수는
없다.

| variant | 최소 조건 | 조건 미달 기본 fallback |
|---|---|---|
| `line`/`area` | 순서 있는 기간 3개 이상 | 2개 기간은 `slope` 또는 비교 `bar`, 1개는 KPI/표 |
| `slope` | 비교 가능한 정확히 2개 기간, entity 2개 이상 | 3개 이상 기간은 `line`, entity 1개는 KPI/비교 문장 |
| `scatter` | complete pair 20개 이상, 각 축 distinct 3개 이상 | 순위 `bar` 또는 표, 관계 표현 금지 |
| `histogram` | non-null 20개 이상, distinct 5개 이상 | 정렬 bar 또는 요약 표 |
| `boxplot` | group별 non-null 5개 이상 | 중앙값·범위 비교 bar/표 |
| `heatmap` | 최소 2×2 cell, 채움 비율 50% 이상 | group bar 또는 cell gradient table |
| `bar` | 비교 category 2~20개 | 1개는 KPI, 20개 초과는 명시적 top-N+나머지 또는 표 |
| `stacked_bar` | part 2개 이상, 동일한 분모·합계 의미 | group bar 또는 표 |
| `waterfall` | signed component가 기준값과 결과값을 가산적으로 연결 | 비교 bar; 기여도 결론 금지 |

다중 identity series가 8개를 넘으면 기본 legend 나열을 허용하지 않는다. 직접
끝점 라벨, small multiple, 선택형 paginated legend, top-N+detail 중 하나를
계획하고 모바일 강등을 명시한다. 이 규칙은 25개 구가 작은 모바일 범례에
몰리는 v5 smoke 문제를 직접 다룬다.

`data_sufficiency.status = fallback_required`인데 실제 chart가 원래 variant를
유지하면 BLOCK한다. fallback을 적용한 뒤에는 적용된 variant와 이유를
`chart_recommendation`에도 독자 언어로 기록한다.

## 7. 문구 계약

### 7.1 문장 생성기가 아닌 문맥 검증

renderer는 제목·카드 결론을 새로 만들지 않는다. analyze가 독자 문구를 작성하고,
validator는 다음 문맥의 존재와 수치 근거만 확인한다.

- 대상 범위: 지역, 상품, 고객군 등
- 지표와 집계 의미: 중앙값, 비율, 합계, 지수 등
- 실제 비교 기간 또는 기준일
- 단위와 필요한 분모
- 관측인지 원인·추천인지 구분할 수 있는 근거 수준

`copy_context`는 문장을 조립하는 템플릿이 아니라 이 문맥을 검증하는 구조화된
근거다.

### 7.2 제목·부제·카드

- **결론형 제목**은 결과가 안정적이고 수치 근거가 있을 때 기본값이다.
  예: `2022-01보다 2026-06 가격은 8.7% 올랐고 거래량은 43.2% 줄었다`.
- 결론형이 과대해석을 만들거나 탐색 범위를 열어두어야 하면 **설명형 제목**을
  쓴다. 예: `2022-01~2026-06 구별 가격과 거래량 변화`.
- 부제는 제목을 반복하지 않고 범위·기간·집계·단위 중 제목에서 빠진 정보를
  보완한다.
- `시작월`, `끝월`, `최근 끝점`, `기간 가격`, `스냅샷`, `proxy`, `grain` 같은
  계산·구현 용어를 독자 화면에 쓰지 않는다.
- 단위는 `(단위: 만원)`처럼 본문과 분리한다. 단위·분모가 확정되지 않은 지표는
  화면에서 제외하거나 BLOCK한다.
- 한계를 카드마다 반복하지 않는다. 핵심 관측은 수치로 말하고, 공통 한계는
  주의·방법론·출처 영역 한 곳에 둔다.
- 내용이 없거나 decision/metric 연결이 없는 KPI 카드는 만들지 않는다.

### 7.3 숫자 표기

- 금액·수량·인원·면적처럼 **측정값으로 읽는 1,000 이상 숫자**는
  `10,970건`, `238,228만원`처럼 천 단위 구분기호를 쓴다.
- 이 규칙은 KPI 본값·비교값, 차트의 값축·직접 라벨·tooltip용 구조화 값,
  histogram 구간, 상세표와 mobile fallback 표, story/action과 차트 설명에
  동일하게 적용한다.
- 소수 자릿수는 지표의 `format.precision` 또는 이미 확정된 계산 정밀도를
  유지한다. 구분기호를 넣기 위해 값을 반올림하거나 단위를 바꾸지 않는다.
- `2026년`, `2026-06`, `2022년 상반기` 같은 날짜·기간, 우편번호·코드·ID처럼
  크기를 뜻하지 않는 식별 숫자는 천 단위 구분기호 대상이 아니다.
- renderer는 구조화된 숫자를 locale(`ko-KR` 기본값)에 맞게 표시한다. 제목·설명
  같은 자유 문구는 renderer가 임의로 고치지 않고, 단위가 붙은 네 자리 이상
  수량·금액이 구분기호 없이 남으면 v5.1 static QA가 BLOCK한다.

## 8. 색·척도·라벨 원칙

### 8.1 색은 의미 계약이다

단일 색 사용 자체를 실패로 보지 않는다. 같은 측정값을 여러 항목에서 비교하는
단일 계열은 한 root color가 가장 정직할 수 있다. 문제는 모든 차트가 같은 색을
반복하거나, 색이 무엇을 뜻하는지 계획에 없는 상태다.

- `single_measure`: 한 측정값 비교. 한 root color와 필요 시 한 강조 role만 사용.
- `semantic_highlight`: 기준 초과, 선택, 예외처럼 정의된 의미만 role color로 강조.
- `categorical_identity`: 서로 다른 계열의 정체성을 구분. 최대 5개 root color와
  label/shape/line style을 함께 사용.
- `sequential`: 낮음→높음의 순서가 있는 연속값. heatmap은 끝점 대비와
  `낮음/높음` 범례를 보장.
- `diverging`: 의미 있는 중앙값·목표·0이 있을 때만 사용.
- category/metric의 색 mapping은 같은 dashboard 안에서 안정적으로 유지한다.
- 5개를 넘는 identity series는 색을 더 늘리지 않고 직접 라벨, panel, order,
  선택과 상세표로 강등한다.
- 다중 series에서 색만이 유일한 구분 수단이면 BLOCK한다.

### 8.2 척도

- bar의 길이 비교는 원칙적으로 0 기준선을 쓴다.
- `zero_baseline`은 값축의 관측 범위에 0을 **포함한다**는 뜻이지
  `min=0`으로 음수 관측값을 잘라도 된다는 뜻이 아니다. 양수와 음수가 함께
  있으면 0을 가운데 기준으로 두 방향 막대를 모두 표시하고, 음수 최솟값까지
  값축 범위에 포함하지 않으면 BLOCK한다.
- 단위가 다른 시계열은 같은 값축에 겹치지 않는다.
- 같은 단위라도 관측 범위가 4배 이상 차이 나 한 계열이 눌리면
  `independent_panels`를 사용한다.
- `indexed_baseline`은 기준 시점과 `기준=100`을 제목 아래에서 명시한다.
- `focused_range_with_cue`는 line/scatter처럼 0이 필수가 아닌 경우만 허용하고,
  축 절단을 눈에 보이게 알린다.
- 이중축은 계속 금지한다.

### 8.3 라벨과 범례

- 1~5개 계열이고 공간이 있으면 직접 라벨을 우선한다.
- 단일 계열 legend는 숨긴다.
- legend가 필요하면 longest label을 기준으로 plot grid 여백을 먼저 예약한다.
- tooltip은 보조 수단이며 제목·축·직접 라벨에 필요한 핵심 정보를 대신하지
  않는다.
- 좁은 화면에서 label을 무작정 축소하지 않는다. reflow, 줄바꿈, top-N,
  paginated legend, table fallback 순으로 해결한다.

## 9. 최소 구성과 layout 계약

`schemas/dashboard_layout.schema.json`에 다음을 추가한다.

- 최상위 `quality_contract_version: "v5.1"`
- 각 component의 `purpose`
- 각 component의 `decision_link`
- 각 component의 `evidence_refs[]`
- 각 component의 `empty_behavior: "hide" | "block"`

`purpose`는 `context | summary | primary_evidence | comparison | diagnostic |
guardrail | detail | provenance | interaction`만 허용한다.

- header와 source note는 `decision_link = null`을 허용한다.
- 그 외 component는 `decision_brief.decision_id`와 연결되어야 한다.
- chart는 자기 `chart_spec.id`, KPI는 metric id, table/insight는 사용한 chart 또는
  metric id를 `evidence_refs`에 포함한다.
- control은 실제 state-changing interaction을 가진 chart를 참조해야 한다.
- 빈 KPI·빈 insight·데이터 없는 chart는 `empty_behavior`에 따라 숨기거나
  출고를 막는다. 빈 카드 외곽만 남기지 않는다.
- 같은 질문·근거를 반복하는 chart/component는 BLOCK, 단 summary와 detail처럼
  명시적 역할 차이가 있으면 허용한다.
- source note는 compact provenance로 유지하며 큰 전폭 카드로 승격하지 않는다.

## 10. QA 계약

### 10.1 plan/static — BLOCK

- v5.1 chart_spec과 layout 중 한쪽만 v5.1 선언
- decision brief, metric role, 단위·분모·기간·source 누락
- chart question 또는 component purpose/decision/evidence 연결 누락
- 충분성 조건 미달인데 fallback 미적용
- `family`/`variant`/기존 `chart.type` 불일치
- 다른 단위의 overlay, bar의 비0 기준, 의미 없는 diverging scale
- 다중 series를 색만으로 구분하거나 categorical root가 5개 초과
- 8개 초과 identity series에 기본 legend만 사용
- 실제 날짜·단위가 있는데 계산 자리표현이나 미확정 단위 노출
- 단위가 붙은 1,000 이상 수량·금액을 천 단위 구분기호 없이 노출
- 내용 없는 KPI/insight, 데이터 없는 chart, 동작 없는 control
- 같은 질문과 근거의 중복 component
- 기존 v5의 schema, 승인 hash/revision, lineage, raw option/CDN BLOCK

### 10.2 browser — BLOCK

QA viewport를 다음 네 개로 고정한다.

| 이름 | viewport | screenshot |
|---|---:|---|
| desktop | 1440×1000 | `qa_render_desktop.png` |
| compact | 736×1000 | `qa_render_compact.png` |
| mobile | 390×844 | `qa_render_mobile.png` |
| narrow | 320×800 | `qa_render_narrow.png` |

모든 viewport에서 다음을 검사한다.

- page overflow, component/plot/legend/label 겹침·잘림·0 크기
- ECharts instance, 비어 있지 않은 plot, console/network error
- 제목·부제·단위·축·범례·active state의 DOM/Canvas 가시성
- essential secondary text 11px 미만
- longest label을 포함한 legend와 plot 여백
- tooltip이 viewport 밖으로 벗어나거나 핵심 값을 가리는 문제
- 키보드 focus, native control name, reset과 현재 상태
- 색만으로 상태·series를 구분하는 문제
- mobile/narrow에서 정보 component가 임의로 사라지는 문제

### 10.3 눈검토와 기록

QA는 run-local `outputs/visual_review.json` 초안을 만든다. 이 파일은 사용자 승인
증거가 아니며 다음 관찰 기록만 보존한다.

- screenshot 경로와 sha256
- desktop/compact/mobile/narrow 검사 여부
- 문구 직관성, 정보 위계, 색 의미, 척도, 라벨·범례, 여백·밀도 관찰
- `pass | revise` 상태와 구체적 관찰
- 검사자 역할(`orchestrator`)과 검사 시각

대시보드 정지점을 전달하기 전에 오케스트레이터는 생성된 모든
`outputs/qa_render_*.png`를 직접 열어야 한다. 자동 QA가 green이어도 눈검토를
생략하지 않는다. 눈검토가 `revise`이면 사용자에게 승인 선택을 제시하지 않고
수정·재렌더한다. 실제 사용자 답변만 기존 checkpoint에 기록한다.

## 11. Claude/Codex marketplace 어댑터

제품 core와 문서는 하나만 유지하고, 플랫폼별 어댑터는 진입점과 manifest만
가진다.

### 11.1 공통 원칙

- core SSOT: `docs/pipeline-contract.md`, `AGENTS.md`, schemas, scripts, QA
- 공유 실행 skill: `skills/run-pipeline/SKILL.md`
- 어댑터가 checkpoint 정책이나 분석 규칙을 복제하지 않음
- 두 플랫폼 모두 같은 wrapper와 `checkpoint_answers.json`을 사용
- plugin cache, proprietary asset, host-only widget에 의존하지 않음
- 패키징 테스트는 설치 발견, manifest, skill 진입, hook 경로, dry-run을 확인

### 11.2 Claude Code

기존 `.claude-plugin/plugin.json`, `.claude-plugin/marketplace.json`,
`hooks/hooks.json`을 얇은 어댑터로 정리한다. Claude 전용 문구는 core 규칙을
요약하지 않고 `skills/run-pipeline/SKILL.md`와 wrapper로 연결한다.

### 11.3 Codex

동일한 제품 root에 `.codex-plugin/plugin.json`과 Codex marketplace metadata를
추가하고, 공유 skill과 `.codex/hooks.json`을 선언한다. Codex 인라인 위젯을
요구하지 않으며 standalone `dashboard.html`과 checkpoint 채팅 흐름을 유지한다.

어댑터는 별도 kit가 아니다. 배포 단위는 하나의 data-insight-kit이고 각
marketplace가 자기 manifest를 읽는다.

## 12. 이전/이후 비교

기준 smoke는 다음 두 개다.

| 성격 | v5 baseline run |
|---|---|
| snapshot·구성/분포 | `sbiz-gangnam-v5-freeform-smoke-20260714` |
| time-series·다중 계열 | `apt-sale-v5-freeform-smoke-20260714` |

baseline의 HTML, JSON, screenshot은 읽기 전용으로 보존하고 커밋하지 않는다.
v5.1 비교는 원천 데이터만 재사용한 새 run-id로 실행한다. 이전 checkpoint 답변은
복사하지 않으며, 새 hash/revision은 실제 사용자 승인 없이는 다음 단계로 넘기지
않는다.

비교표는 최소 다음 항목을 같은 기준으로 평가한다.

1. decision brief와 metric role의 완결성
2. 차트 질문 중복과 데이터 충분성/fallback
3. 실제 날짜·단위·범위가 포함된 문구의 직관성
4. 척도·분리 패널·baseline의 정직성
5. 색의 의미와 비색상 채널
6. 직접 라벨·범례와 plot 공간
7. 1440/736/390/320 반응형 완성도
8. 카드·control·출처의 최소 구성
9. 자동 QA BLOCK/WARN과 눈검토 수정 횟수
10. lineage, source, build/visual review 재현성

pixel hash나 “더 예뻐 보인다”만으로 승리 판정하지 않는다. hard BLOCK은 0이어야
하며, 사용자 피드백으로 반복되던 문구·척도·범례 문제가 줄었는지 raw evidence와
나란히 판단한다.

## 13. 구현·커밋 순서

구현은 설계 승인 뒤 다음 순서를 고정한다.

1. schema/fixture에 additive v5.1 계약 추가
2. planner와 cross-contract validator에 decision/metric/visual 계약 추가
3. renderer에 scale/color/label/mobile 전략 반영
4. static/browser/eyes-on QA와 visual review record 추가
5. 사용자 문서와 design system 갱신
6. Claude Code 어댑터 검증·정리
7. Codex 어댑터 추가·검증
8. snapshot smoke 재실행과 checkpoint
9. time-series smoke 재실행과 checkpoint
10. 이전/이후 비교와 release checklist 마감

각 커밋 직전에는 정확히 아래를 실행해 green을 확인한다.

```bash
cd data-insight-kit && python3 -m pytest tests/ -q
```

`runs/*`는 커밋하지 않고 push하지 않는다. spec과 구현 판단이 충돌하면 spec을
먼저 수정해 사용자에게 다시 확인받는다.

## 14. 완료 조건

- v5.1 두 JSON 계약과 교차검증이 기존 legacy/v4/v5 문서를 깨지 않음
- 충분성, 척도, 색+비색상, 최소 구성, 문구 문맥이 테스트로 고정됨
- 네 viewport browser QA가 BLOCK 0이고 모든 screenshot을 직접 검토함
- Claude/Codex 어댑터가 같은 core와 checkpoint gate를 호출함
- 두 v5.1 smoke가 실제 사용자 checkpoint 답변으로 완료됨
- 이전/이후 비교에서 반복 피드백 항목과 수정 횟수가 감소함
- 모든 커밋 직전 전체 pytest green, `runs/*` 제외, push 없음
