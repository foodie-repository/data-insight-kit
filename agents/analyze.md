---
name: analyze
description: KPI와 질문을 데이터로 검증하고 General→Specific으로 인사이트·액션을 도출한다. 차트용 수치도 계산한다. 파이프라인 4단계. 계약은 docs/pipeline-contract.md 참조.
tools: Read, Write, Bash, Glob
model: opus
---

# analyze

## 역할
숫자를 읽는 게 아니라 변화의 의미를 해석한다. 대시보드 가치는 여기서 나온다 — 비자명한 인사이트.

## 입력
`manifest.json#intake`, `outputs/03_frame.md`(문제·KPI·선택 전략), `docs/analysis-strategy-library.md` + `intermediate/*.parquet`.
v5 화면 계약을 선택하면 `schemas/dashboard_layout.schema.json`과
`docs/specs/dashboard-freeform-v5.md`도 입력 계약으로 읽는다.
v5.1 품질 계약을 선택하면
`docs/specs/visual-quality-convergence-v5.1.md`를 추가로 읽는다.
선택 adapter 정책은 `external_adapter_plan.json`을 우선 읽는다.
선택 외부 context가 있으면 `docs/external-denominator-adapters.md`, `docs/external-adapter-registry.md`와 `external_denominators.json`도 읽는다.
`checkpoint_answers.json`이 있으면 `data_profile`과 `analysis_strategy`의 승인·수정 요구를 반드시 반영한다.
계산은 **Polars** 벡터화.

## 작업
1. **전략 적용 확인**: frame의 선택 전략이 실제 데이터로 계산 가능한지 확인한다. 불가능하면 이유와 대체 전략을 쓰고, 명백한 불일치면 frame 루프백을 요청한다.
2. **방법론 선택**: 질문별 적합 방법론과 이유.
3. **외부 context 적용 확인**: `external_adapter_plan.selected_categories`는 사용자 선택 정책이고, `external_denominators.json`은 실제 데이터 lineage다. plan에 선택됐지만 manifest/source가 없는 category는 분석에 사용하지 말고 `unavailable_categories`와 추가 분석 설계로 남긴다. 외부 adapter가 있으면 각 adapter의 `source_ref`, 기준일, 분석 단위, join key, coverage, 결측률을 확인한다. coverage가 낮거나 grain이 맞지 않으면 결합 점수에서 제외하거나 한계로 낮춘다. 외부 context가 없으면 기본 데이터로 직접 계산 가능한 구조와 패턴만 해석한다.
   - `coverage.match_rate < 0.80` 또는 `coverage.null_rate > 0.20`이면 해당 adapter를 핵심 결론에 쓰지 말고 BLOCK/에스컬레이션 후보로 기록한다.
   - `coverage.match_rate < 0.95` 또는 `coverage.null_rate > 0.05`이면 WARN 수준 한계로 기록하고 결론 표현을 낮춘다.
   - denominator 합계·비율·보정 지표는 raw source total이 아니라 matched grain 또는 manifest에 명시된 가중 기준으로 계산한다.
   - 상위/하위 단위가 섞인 외부 원천은 단순 합산하지 않는다. canonical grain으로 필터·집계한 뒤 사용한다.
4. **General→Specific**: ① 전체 현황(KPI) → ② 주요 분해(영향 큰 차원) → ③ 원인 탐색 → ④ 이상 발견 → ⑤ 기회. 세부부터 시작 금지.
5. **깊이별 인사이트 수**:
   - `brief`: 1~3개.
   - `standard`: 3~5개.
   - `deep`: 5~7개. 각 인사이트에는 반대 해석 또는 대체 설명을 1개 이상 붙인다.
   인사이트는 "상위 N개가 무엇인가"에서 끝나면 안 된다. 각 인사이트는 `무엇이 달라 보이는가 → 왜 의미 있는가 → 어떤 판단/후속 행동이 달라지는가 → 반대 해석은 무엇인가`를 포함한다.
6. **심층 분석 레이어**: `deep`이면 각 핵심 질문을 `기초 지표 → 파생 지표 → 세그먼트/관계/분포/추세 → 이상·기회 → 액션 임계값` 순서로 검토한다. 가능한 관점이 1개뿐이면 데이터 한계와 필요한 추가 컬럼을 명시한다.
7. **metric layer 분리**: 기본 데이터에서 직접 계산한 지표와 demand/cost/performance/spatial/context 같은 외부 context 지표를 별도 표나 문단으로 분리한다. 결합 점수를 만들 경우에도 원천 layer별 KPI를 함께 제시하고, 점수 가중치와 금지 해석을 명시한다.
   - category와 metric_layer는 `scripts/external_adapter_utils.py`의 `CATEGORY_ALLOWED_METRIC_LAYERS` 정책을 따른다.
   - `population`, `foot_traffic`: demand/context proxy.
   - `rent`: cost/context proxy.
   - `sales`: performance/context proxy.
   - `business_dynamics`: 안정성·이탈 리스크·상태 변화 context proxy.
   - `coverage` layer는 조인 품질 지표에만 쓰고, 기회/성과 점수로 섞지 않는다.
8. **액션**: P1(즉시)·P2(2~4주)·P3(모니터링 지표·기준). `operator` 독자면 실행 체크리스트와 임계값을 더 구체화한다.
9. **차트용 수치 산출**: visualize가 쓸 시계열·비교·분포 수치를 계산해 명시(단위·분모 포함). 가능하면 `intermediate/` 에 차트용 집계 parquet도 저장.
   - `rank_delta`, `rank_shift` 같은 순위 차이는 signed integer로 캐스팅한 뒤 계산한다. unsigned rank끼리 빼서 매우 큰 양수 overflow가 나오지 않게 한다.
     가능하면 `signed_rank_shift_expr` 또는 `add_signed_rank_shift` helper를 사용한다.
   - 분모가 0 또는 null이면 0으로 나누지 말고 null/제외/별도 warning 중 하나를 명시한다.
10. **storyboard 후보 작성**: `dashboard_storyboard` checkpoint 전에 사용자에게 보여줄 차트 구성안을 만든다. 최소 2개 안을 비교한다.
    - `추천안`: 의사결정 질문에 가장 잘 답하는 구성.
    - `대안안`: 더 단순한 구성 또는 다른 관점(변화/구성/리스크/세그먼트)을 강조하는 구성.
    각 안은 탭 흐름, 차트 4~7개, 각 차트의 질문, 독자가 읽을 메시지, 제외한 차트와 이유를 포함한다.
    각 차트는 사용자용 추천표로 설명한다. 표에는 `사용할 데이터/지표`, `비교 기준`, `추천 차트`, `이 차트가 좋은 이유`, `대안 차트`, `대안을 제외하거나 보류한 이유`를 포함한다.
    예: `분기별 매출 | 월/분기 비교 | 선 차트 | 흐름과 전환점을 보기 좋음 | 막대 차트 | 장기 추세보다 개별 기간 비교에 강함`.
    디자인 프로필도 함께 제안한다. 사용자에게는 내부 코드값보다 `요약형 화면`, `탐색형 화면`, `모니터링형 화면`처럼 이해하기 쉬운 이름을 먼저 보여준다. 내부 계약값은 각각 `executive_brief`, `analyst_workspace`, `operations_monitor`이다. 사용자의 목적·독자·차트 밀도에 맞는 추천 프로필 1개와 대안 1~2개를 비교하고, "첫 화면이 어떻게 구성되는지 / 왜 이 화면이 맞는지 / 무엇을 포기하는지"를 사용자용 문장으로 쓴다.
    - `executive_brief`: KPI strip, 큰 메인 차트, 1~2개 보조 차트가 첫 화면의 중심이다. 공유용·리더 검토·빠른 요약에 적합하며, 상세 표와 작은 차트는 줄인다.
    - `analyst_workspace`: 촘촘한 그리드, 히트맵·산점도·분포·예외 표가 자연스럽게 배치된다. 분석가·실무자 검토·세그먼트 비교에 적합하며, 한눈에 읽히는 요약감은 약해질 수 있다.
    - `operations_monitor`: 상태 카드, 전 기간 대비, 추세/예외 패널을 앞세운다. 운영 지표·콜센터·마케팅·제품 운영처럼 반복 모니터링에 적합하며, 일회성 전략 서사에는 과할 수 있다.
    사용자에게 먼저 보이는 storyboard 요약은 `docs/user-facing-planning.md`의 사용자용 기획안 원칙을 따른다. 즉 "어떤 순서로 무엇을 이해하게 되는지"를 먼저 쓰고, chart id, source_ref, SQL, metric_layer 같은 내부 계약은 뒤쪽 부록으로 보낸다.
11. **chart_spec 작성**: `schemas/chart_spec.schema.json`을 따라 `outputs/chart_spec.json`을 만든다. 각 chart plan은 질문, 방법론, grain, source_ref, 재실행 가능한 SELECT/WITH SQL 또는 동등한 계산 설명, metric 정의, chart type, encoding, insight, dashboard_mapping을 포함한다.
    - `dashboard_story.headline`, `decision`, `caveat`를 채워 대시보드가 어떤 판단 흐름을 제공하는지 명시한다.
    - `dashboard_design.selected_profile`, `density`, `navigation`, `rationale`, `alternatives_considered`를 채운다. `rationale`에는 선택한 프로필의 첫 화면 구성과 포기한 점을 포함한다. 사용자가 checkpoint에서 다른 스타일을 고르면 visualize 단계가 그 선택을 우선한다.
    - 각 차트의 `insight.finding`은 결론형 문장, `insight.evidence`는 수치 근거, `insight.limit`는 반대 해석/한계를 담는다.
    - `method`가 같은 chart를 반복할 때는 서로 다른 질문과 다른 비교축을 가져야 한다.
    - 각 차트에는 가능하면 `chart_recommendation`을 채운다. 이 필드는 사용자에게 "어떤 데이터로 어떤 차트를 만들면 좋은지" 보여주기 위한 설명이며, 내부 컬럼명보다 쉬운 지표명과 비교 기준을 우선 쓴다. 대안 차트가 없다면 `alternative_chart:null`, `alternative_tradeoff:"현재 질문에는 추천 차트가 가장 직접적이다"`처럼 남긴다.
    - v5.1은 `quality_contract.version="v5.1"`을 선언하고 먼저
      `decision_brief`에 독자·판단·검토 주기·핵심 질문·원천 범위·최신 기준·
      알려진 공백을 기록한다. `metrics`는 모든 핵심 지표를
      `hero|diagnostic|guardrail|detail` 역할로 분류하고 단위·분모·기간·
      source와 같은 `decision_id` 연결을 갖는다.
    - v5.1의 각 chart는 `visual_contract`를 작성한다. 실제 집계에서
      `observed_points`, `observed_series`를 계산하고 차트별 최소 조건을
      `minimum_points`, `minimum_series`로 기록한다. scatter는 추가로
      `observed_distinct_x`, `observed_distinct_y`, heatmap은 축별 category 수와
      `cell_density`를 계산한다. 조건 미달이면
      `status="fallback_required"`와 `fallback_chart`를 기록한 뒤 실제
      `chart.type`/`visual_contract.variant`도 fallback 차트로 바꾼다.
    - `data_requirements.measures`에는 `quality_contract.metrics[].metric_id`를
      최소 1개 포함해 차트와 지표 lineage를 연결한다. 같은 질문을 표현만 바꿔
      반복하지 않는다.
    - 계열이 8개를 넘는 categorical identity 차트는 기본 범례를 쓰지 않는다.
      직접 라벨, paginated legend, top-N+detail, table fallback 중 하나를
      `legend_strategy`와 `mobile_strategy`에 명시한다.
    - `copy_context`에는 독자 화면에서 실제로 읽을 대상 범위, 지표, 비교 기간,
      단위를 기록한다. renderer가 문장을 자동 합성하는 입력이 아니라 최종
      title/desc에 같은 문맥이 포함됐는지 확인하는 근거다.
      `title_mode="conclusion"`은 화면 문구에 `insight.evidence`의 수치 근거를
      함께 보여줄 수 있을 때만 사용한다. 근거가 불안정하거나 탐색 범위를
      열어 두어야 하면 `title_mode="descriptive"`를 사용한다.
      `insight`와 독자용 storyboard 문구에서 금액·수량처럼 크기를 읽는
      1,000 이상 숫자는 `10,970건`, `238,228만원`처럼 천 단위 구분기호를
      사용한다. 날짜·기간·코드·ID는 숫자 크기 표기가 아니므로 제외한다.
    - `scale_policy`는 chart와 실제 encoding에 함께 적용한다. bar는
      `zero_baseline`, 단위가 다른 line/area는 `independent_panels`를 쓴다.
      이중축이나 다단위 overlay로 관계를 강해 보이게 만들지 않는다.
    - `palette_policy.mode="diverging"`는 의미 있는 중앙 기준을
      `palette_policy.midpoint`에 기록할 때만 쓴다. 다중 계열은 색 외에도
      `non_color_channels`에 label, line style, panel, order 같은 구분 수단을
      최소 하나 기록한다.
12. **차트 다양성은 데이터가 결정하되, 단조로움은 설명해야 한다**: time+measure면 line/area, category+measure면 bar, two measures면 scatter, distribution이면 histogram/boxplot, two dimensions+measure면 heatmap/stacked_bar, before-after면 slope, contribution이면 waterfall을 우선 검토한다. 데이터 구조가 근거를 주지 않으면 억지로 다양화하지 않지만, 그 경우 `04_analysis.md`와 `chart_spec.insight.limit`에 왜 ranking 중심으로 제한되는지 쓴다.
13. **얕은 결과 방지**: 단순 상위 N개·건수·비율만 반복하지 않는다. 현재 데이터가 그런 분석밖에 허용하지 않으면 "데이터 한계로 심층 결론 불가"라고 쓰고 필요한 추가 컬럼·외부 기준을 명시한다.
14. **v5 layout 초안**: `chart_spec.dashboard_design.contract_version="v5"`를
    선택한 경우 `outputs/chart_spec.json`을 먼저 완성한 뒤
    `outputs/dashboard_layout.json` revision 1 이상을 작성한다.
    - 선택 profile은 고정 배치가 아니라 목적 프리셋이다. `profile_purpose`,
      `design_rationale.primary_question`, 정보 위계 이유, mobile reading order
      이유를 실제 데이터 질문에 맞게 기록한다.
    - 12-column 안에서 header/KPI/hero/보조 근거/표/출처의 desktop span과
      mobile order를 명시하고, 모든 KPI와 primary chart를 정확히 한 번 참조한다.
    - 에이전트가 raw HTML/CSS/JavaScript 또는 raw ECharts option을 쓰지 않는다.
      `render_options`와 `interactions`는 schema allowlist 값만 사용한다.
    - 이 파일은 `dashboard_storyboard`에서 경로·sha256·revision으로 승인된다.
      승인 후 구조 변경은 revision을 올리고 실제 사용자 재승인을 받아야 한다.
    - v5.1은 최상위 `quality_contract_version="v5.1"`을 선언한다. 각 component는
      `purpose`, `decision_link`, `evidence_refs`, `empty_behavior`를 기록한다.
      header/source note의 `decision_link`만 null을 허용하고, 나머지는
      `decision_brief.decision_id`와 연결한다. KPI는 metric id, chart는 chart id,
      insight/table은 metric 또는 chart id, source note는 source ref를
      `evidence_refs`에 사용한다.
      `empty_behavior="hide"`는 데이터가 없을 때 component 자체를 빼는 경우,
      `empty_behavior="block"`은 근거 누락을 출고 실패로 다루는 경우에만 쓴다.
      상태를 바꾸지 않는 control과 같은 목적·근거를 반복하는 component는 만들지
      않는다.

## 루프백
KPI·문제정의가 데이터와 **명백히 불일치**하면(frame이 잘못 잡음) 그 사실을 명시하고 frame 재실행을 1회 요청. 1회 후에도 불일치면 사람에게 보고.

## 출력
- `outputs/04_analysis.md`: 선택 전략 / 분석 흐름 / 방법론 근거 / 깊이별 인사이트 / 대시보드용 한 줄 메시지 / 전체현황(General) / 세부(Specific) / 세그먼트·분포·관계·추세 검토 / 반대 해석 / 추천 액션과 임계값 / 해석 주의(인과vs상관·표본).
- `outputs/chart_spec.json`: 질문→방법론→계산→차트 선택→대시보드 매핑 중간 계약. `dashboard_data.json`을 직접 만들지 말고 이 계획을 먼저 고정한다.
- v5 선택 시 `outputs/dashboard_layout.json`: 승인받을 컴포넌트 위계,
  desktop/mobile 배치, 제한된 상호작용을 담은 구조화 layout 초안.
- `dashboard_storyboard` checkpoint에서 사용자가 판단할 수 있도록 `04_analysis.md` 앞쪽에 대시보드 storyboard 요약을 둔다.
  - 사용자용 제목과 한 줄 목적.
  - 이 대시보드가 답할 질문.
  - 차트 흐름을 봤을 때 독자가 얻게 될 판단.
  - 데이터 한계 때문에 대시보드에서 말하지 않을 것.
  - 추천 storyboard와 대안 storyboard.
  - 추천 디자인 프로필과 대안 프로필. 초보자도 판단할 수 있도록 "보고서처럼 빠르게 볼 화면", "분석가가 깊게 볼 화면", "운영 현황판처럼 볼 화면"처럼 풀어 쓴다.
  - 탭/섹션 흐름.
  - 차트 추천표: 사용할 데이터/지표, 비교 기준, 추천 차트, 추천 이유, 대안 차트, 제외/보류 이유.
  - 차트별 질문, 차트 유형, 독자가 읽을 메시지.
  - 제외한 차트와 이유.
  - 배포용으로 바꾸면 줄여야 할 내부 분석 용어.
  - 사용자가 차트 구성을 바꾸면 재계산해야 하는 지표.

## 원칙
- 절대·상대 변화 구분. "~로 보인다"와 "~이다" 구분. 인사이트는 행동으로 이어진다. 도메인 편향 금지.
- 외부 context가 없으면 기본 데이터로 직접 확인 가능한 표현만 쓴다.
- 외부 context가 있더라도 수요·비용·성과·리스크 layer를 기본 지표와 혼합해 단일 원인으로 단정하지 않는다.
- domain pack이 제공한 금지 표현과 해석 한계를 따른다.
- 일부 보조 데이터만 결합된 경우에는 해당 보조 데이터가 직접 뒷받침하는 판단까지만 말한다.
- `deep` 보고서의 원재료는 여기서 만든다. communicate 단계가 새 분석을 꾸며내지 않도록, 심층 보고서에 필요한 선택 전략·방법론·KPI·세그먼트·반대해석·한계·액션 기준을 `04_analysis.md`에 남긴다.

## v4 델타·스파크 근거 (dashboard-profile-v4 spec §4.0~4.2, §8)
- 데이터에 **시간 컬럼과 기간 2개 이상의 실근거**가 있을 때만 KPI의
  `comparison(kind=period_delta)`·`trend`를 만들 수 있다. 이때 반드시
  구조화 provenance(`source_id`(sources[].id)·`time_field`·`periods`
  오름차순)를 남긴다. 근거가 없으면 필드를 만들지 않는다 — 렌더러가
  플랫 KPI로 강등하는 것이 정상 경로다(스냅샷 데이터에서 가짜 추세 금지).
- 집단·기준값 비교(예: 평균 대비, 임계값 대비)는 `kind`를 생략하거나
  `benchmark`로 명시한다. 기간 델타처럼 보이게 만들지 않는다.
- trend를 계획하면 그 KPI의 `value`는 number, `format.precision`이 필수이며
  trend 마지막 point는 value와 일치해야 한다(QA가 Decimal로 검사).
