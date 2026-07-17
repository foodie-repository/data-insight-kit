# Dashboard Freeform v5 — 승인 레이아웃 기반 자유 설계

Status: approved for implementation planning (2026-07-14 사용자 답변: "설계 승인")
Branch: `codex/dashboard-freeform-v5`
결정 배경: `docs/specs/dashboard-freeform-v5-kickoff-notes.md`
관련 단일 원천: `docs/pipeline-contract.md`(단계·checkpoint),
`docs/dashboard-design-system.md`(시각 언어), `schemas/chart_spec.schema.json`·
`schemas/dashboard_data.schema.json`(분석·데이터 계약)

## 1. 목적

v4는 프로필별 표현 차이를 만들었지만 고정 renderer 문법 안에서 패널을
배치하므로, 데이터 질문마다 크게 봐야 할 차트·보조 근거·상세 표의 위계를
충분히 바꾸기 어렵다. v5의 목적은 에이전트가 데이터 특징과 분석 결과에 맞춰
레이아웃을 자유롭게 설계하면서도 다음을 잃지 않는 것이다.

- 승인된 화면 구조의 재현성과 checkpoint lineage
- `chart_spec.json` → `dashboard_data.json` 계획-이행 일치
- 값·lineage·언어·접근성·겹침에 대한 결정적 QA
- 기존 legacy/v4 run의 렌더 하위 호환

v5는 raw HTML 자유 작성을 허용하지 않는다. 에이전트는 구조화된
`dashboard_layout.json`으로 정보 위계를 설계하고, kit의 결정적 compiler가
승인된 구조를 HTML로 조립한다.

## 2. 범위 / 비범위

### 2.1 범위

- 신규 `dashboard_layout.json` 계약과 JSON Schema
- 목적 프리셋을 고정 배치가 아닌 설계 입력으로 사용하는 자유 12-column layout
- 주요 분석 차트의 로컬 ECharts 렌더와 KPI·스토리·표의 SVG/CSS 컴포넌트
- desktop/mobile의 명시적 reading order
- layout revision checkpoint 잠금과 변경 시 재승인
- v5 정적·compile·browser·사람 눈검토 QA
- legacy/v4와 v5의 명시적 이중 renderer 경로

### 2.2 비범위

- 에이전트가 임의 HTML·CSS·JavaScript 또는 ECharts option 객체를 직접 주입
- CDN 또는 실행 시 네트워크 의존 리소스
- 동일 screenshot의 pixel-perfect hash 강제
- 기존 run을 v5로 자동 마이그레이션
- 원자료가 없는 값을 브라우저에서 재계산하는 전역 cross-filter
- Plotly를 ECharts와 병행하는 두 번째 core renderer

Matplotlib·Seaborn은 EDA·통계 검증·정적 보고서 부록에 계속 허용하고, Plotly는
ECharts로 표현하기 어려운 특수 진단 부록에만 선택적으로 허용한다.

## 3. 파이프라인과 승인 흐름

```text
analyze
  ├─ chart_spec.json
  └─ dashboard_layout.json (draft revision N)
          ↓ sha256 approval target
dashboard_storyboard checkpoint
          ↓ 실제 사용자 승인 + answer provenance
visualize
  ├─ dashboard_data.json
  ├─ dashboard_build_manifest.json
  └─ dashboard.html (v5 compiler output)
          ↓
qa: static → compile → desktop/mobile render → screenshot 눈검토
```

1. `analyze`는 질문·방법·계산·차트 선택을 `chart_spec.json`에 먼저 기록하고,
   그 차트와 KPI·근거를 어떤 위계로 보여줄지 `dashboard_layout.json` revision
   초안에 기록한다.
2. `dashboard_storyboard` 질문의 `approval_targets.dashboard_layout`은 파일 경로,
   sha256, revision을 담는다. 사용자는 추천 차트표와 함께 실제 layout 근거를
   검토한다.
3. 승인 뒤 layout 내용이나 revision이 달라지면 기존 답변은 무효다. 새 질문과
   실제 사용자 재승인 전에는 `visualize`가 진행되지 않는다.
4. `visualize`는 승인된 layout과 완성된 data를 compiler에 전달할 뿐, raw HTML을
   다시 작성하지 않는다.

checkpoint 승인 provenance는 기존 `checkpoint_answers.json`과
`scripts/apply_checkpoint_answer.py`가 단일 원천이다. layout 파일에 승인 답변을
복제해 신뢰하지 않는다.

## 4. renderer 선택과 fail-closed 계약

`chart_spec.dashboard_design.contract_version`과
`dashboard_data.meta.dashboard_profile_contract`의 허용값에 `"v5"`를 추가한다.
두 파일과 layout은 다음 표대로 선택된다.

| chart/data 계약 | layout | renderer | 결과 |
|---|---|---|---|
| 둘 다 v5 | 유효한 `layout_version: 5` | v5 compiler | 진행 |
| 둘 다 v5 | 없음·invalid·revision 불일치 | 없음 | **BLOCK** |
| 둘 다 v4 | 없음 | 현행 v4 renderer | 진행 |
| 계약 필드 없음 | 없음 | 현행 legacy renderer | 진행 |
| v4/legacy | layout 있음 | 없음 | **BLOCK** |
| chart와 data 계약 불일치 | 유무 무관 | 없음 | **BLOCK** |

v5 실패 시 v4 renderer로 자동 강등하지 않는다. 호환성은 기존 run을 원래
renderer로 계속 여는 것으로 보장하며, 신규 v5 오류는 수정·재검증한다.

## 5. `dashboard_layout.json` 계약

신규 `schemas/dashboard_layout.schema.json`은 `additionalProperties: false`를
기본으로 하고 다음 최상위 필드를 요구한다.

```json
{
  "schema_version": "data-insight-kit.dashboard_layout.v1",
  "run_id": "example-run",
  "layout_version": 5,
  "revision": 1,
  "generated_at": "2026-07-14T00:00:00Z",
  "profile_purpose": "analyst_workspace",
  "design_rationale": {
    "primary_question": "어느 지역에 상가가 집중되어 있는가",
    "hierarchy_reason": "분포를 hero로, 구성 차이를 보조 근거로 둔다",
    "mobile_reading_order_reason": "결론 뒤에 해석과 상세 근거를 읽게 한다"
  },
  "grid": {
    "columns": 12,
    "gap": "md",
    "max_width": "wide"
  },
  "components": []
}
```

- `run_id`는 `chart_spec.meta.run_id`와 일치한다.
- `revision`은 1 이상의 정수다. 승인 뒤 구조 변경은 반드시 증가한다.
- `profile_purpose`는 기존 `executive_brief | analyst_workspace |
  operations_monitor` 중 하나이며, chart/data의 선택 profile과 일치한다.
- `grid.columns`는 v5에서 12로 고정한다. 자유도는 span·순서·role·reading order로
  제공하고 임의 CSS grid 문법은 허용하지 않는다.
- 토큰은 allowlist다: `gap = sm | md | lg`, `max_width = standard | wide | full`.
- desktop 폭 토큰은 `standard=1180px`, `wide=1720px`, `full=viewport`로
  결정적으로 매핑한다. `wide`는 16:9 화면의 좌우 공간을 활용하되 desktop
  바깥 여백과 mobile 12px 안전 여백은 유지한다.

### 5.1 component 공통 필드

각 component는 다음을 필수로 가진다.

```json
{
  "id": "hero-store-count-by-dong",
  "kind": "chart",
  "role": "hero",
  "renderer": "echarts",
  "data_refs": ["chart_store_count_by_dong"],
  "placement": {
    "desktop": {"order": 3, "column_start": 1, "span": 8, "height": "xl"},
    "mobile": {"order": 3, "span": 12, "height": "lg"}
  },
  "interactions": ["tooltip", "data_zoom"],
  "render_options": {
    "orientation": "vertical",
    "legend": "none",
    "label_density": "standard"
  }
}
```

- `id`: layout 안에서 유일한 안정 ID. DOM의 `data-component-id`가 된다.
- `kind`: `header | control_bar | kpi_group | chart | insight | table |
  source_note`.
- `role`: `navigation | summary | hero | primary | support | evidence`.
- `renderer`: `echarts | svg_css`. `kind=chart`는 ECharts,
  `header|control_bar|kpi_group|insight|table|source_note`는 SVG/CSS만 허용한다.
- `data_refs`: 기존 data 계약의 안정 ID를 참조한다. 참조하지 않는 장식용
  component는 허용하지 않는다.
- `placement.desktop`: `order`, `span(1~12)`, 선택 `column_start(1~12)`,
  `height(sm|md|lg|xl|auto)`.
- `placement.mobile`: `order`, `span=12`, `height`. KPI group 내부만 2열을
  허용한다.
- viewport별 `order`는 유일해야 한다. `column_start + span - 1 <= 12`다.

### 5.2 kind별 `data_refs`

| kind | 허용 참조 | 수량 |
|---|---|---:|
| `header` | `dashboard_data.meta` | 1 |
| `control_bar` | 상호작용 대상 chart id | 1개 이상 |
| `kpi_group` | `kpis[].id` | 1~8 |
| `chart` | `panels[].charts[].id` | 1 |
| `insight` | story가 있는 `panels[].id` | 1 |
| `table` | table이 있는 `panels[].id` | 1 |
| `source_note` | `sources[].id` | 1개 이상 |

모든 KPI와 primary chart는 정확히 한 번 참조되어야 한다. detail/appendix chart를
의도적으로 화면에서 제외하려면 chart_spec에도 같은 제외 사유가 있어야 하며,
근거표·출처를 모두 제거할 수는 없다.

### 5.3 role과 기본 크기 위계

- 기본 출발점은 `KPI row → hero 8 + insight 4 → primary 6 + 6 → evidence 12`다.
- 데이터 질문에 따라 span과 component 수는 바꿀 수 있다. 다만 hero는 최대 1개,
  hero의 desktop span은 7~12, support는 hero보다 크게 둘 수 없다.
- `executive_brief`는 summary/hero 우선, `analyst_workspace`는 primary/evidence
  밀도 우선, `operations_monitor`는 navigation/상태 변화 우선이라는 목적만
  제공한다. 고정 rail·tab·grid를 강제하지 않는다.
- 채우기용 빈 카드나 근거 없는 KPI·차트를 만들지 않는다.

## 6. 렌더 스택과 컴포넌트

### 6.1 ECharts

- `templates/vendor/echarts.min.js`에 버전과 checksum을 고정하고 라이선스를
  함께 둔다. 허용 버전·파일 checksum은 `templates/vendor/manifest.json`이
  단일 원천이다.
- `templates/dashboard_v5.html`의 build placeholder에 bundle을 inline해 최종
  `dashboard.html`을 self-contained로 만든다. 런타임 CDN 요청은 0건이어야 한다.
- 기존 chart type은 결정적으로 매핑한다.

| dashboard_data type | ECharts series |
|---|---|
| line / area | line (`areaStyle`만 차이) |
| bar / stacked_bar / histogram | bar |
| scatter | scatter |
| heatmap | heatmap + visualMap |
| boxplot | boxplot |
| waterfall | stacked bar bridge |
| slope | line with endpoint symbols |

에이전트는 raw ECharts option이나 formatter JavaScript를 넣지 않는다. compiler가
`dashboard_data.encoding`과 allowlist `render_options`를 option으로 변환한다.
allowlist 첫 버전은 `orientation`, `legend`, `label_density`이고, 정의되지 않은
옵션은 schema BLOCK이다.

### 6.2 SVG/CSS

- header: 제목, 기준일, 표본/행 수, 현재 상태를 사용자 언어로 표시
- KPI group: 본값 무채색, 근거가 있는 period delta만 상태색, trend가 있을 때만
  SVG sparkline
- insight: panel story의 `now/why/so/act` 중 값이 있는 항목을 위계 있게 배치
- table: 기존 table 계약과 cell gradient를 사용하고 component 내부 가로
  스크롤만 허용
- source note: 출처·기준일·sample policy를 표시
- control bar: 현재 활성 상태와 reset을 HTML control로 표시

색은 기존 role token을 사용하고 component가 임의 hex를 선언하지 않는다.

- 단일 계열 막대는 기본 `neutral`로 렌더하고, 의미상 한 항목을 강조할 때만
  `series[].point_roles`를 값 배열과 같은 길이로 선언한다. 비교 대상을
  무지개색으로 나누거나 모든 항목에 강조색을 반복하지 않는다.
- `point_roles`와 `series[].role`의 실제 색은 compiler의 고정 role 팔레트가
  매핑한다. 데이터와 layout은 임의 hex를 넣을 수 없다.
- 단일 계열 차트에는 장식용 decal을 쓰지 않는다. 다중 계열을 색으로만
  구분할 위험이 있을 때만 decal을 보조 표현으로 사용할 수 있다.
- heatmap의 연속 수치는 `낮음 → 높음` 순서의 고대비 sequential scale을 쓰고,
  범례에 `낮음`과 `높음`을 함께 표시한다. 의미 있는 중앙 기준이 없는 값에
  diverging scale을 쓰지 않는다.
- 차트 단위는 제목 아래에 `(단위: 개)` 형식으로 분리해 표시한다. header와
  source note에는 `스냅샷` 같은 내부 용어 대신 `분석 기준`, `기준일`을 쓴다.
- 원천 메타에 단위가 없더라도 화면에 `단위 미확인`, `가격 단위 후보`,
  `원천 단위` 같은 작업 중 문구를 그대로 노출하지 않는다. 단위는 원천 문서·
  스키마를 우선하고, 그것도 없으면 도메인 관행과 값 범위를 함께 검토해
  사용자 checkpoint에서 명시적으로 확인받은 표시 단위를 쓴다. 추론 근거는
  `04_analysis.md`와 lineage에 남긴다. 근거가 부족하면 해당 금액 수치를
  출고 화면에서 제외하거나 BLOCK하며 임의로 단위를 확정하지 않는다.
- source note는 큰 카드가 아니라 하단의 compact 주석으로 표시한다. 화면에는
  source basename·기준일·표본 정책만 보이고 전체 ref는 접근 가능한 메타데이터로
  보존한다.
- 값이나 판단 정보를 제공하지 않는 KPI는 채우기용 카드로 만들지 않는다.

### 6.3 독자 언어와 비교 척도

- 계산 과정의 상대 위치인 `시작월`, `끝월`, `최근 끝점`, `기간 가격`을 제목·
  KPI·설명·축에 그대로 쓰지 않는다. 실제 기간을 알고 있으면 `2022-01 대비
  2026-06`, `2022-01~2026-06 월별 중앙가격`처럼 비교 시점과 집계 의미를 직접
  쓴다.
- 제목은 지표 이름이나 추상 질문보다 독자가 확인할 관찰을 먼저 말한다.
  예: `가격과 거래량은 같은 속도로 움직였는가`보다 `2022-01보다 2026-06
  가격은 8.7% 올랐고 거래량은 43.2% 줄었다`를 우선한다.
- line/area의 여러 계열을 한 값축에 겹치는 것은 **단위가 같고 변화폭도
  비슷할 때만** 기본값이다. 단위가 다르거나, 같은 기준 지수로 바꿨어도 한
  계열의 관측 범위가 다른 계열의 1/4 이하로 눌리면 같은 시간축의 위아래
  패널로 분리한다. v5 allowlist는 `render_options.series_layout`의
  `overlay | stacked_panels`를 사용하며, `stacked_panels`는 계열별 값축과 직접
  라벨을 유지하고 마지막 패널에만 공통 시간 라벨을 표시한다.
- 이중축으로 겹쳐 보이는 관계를 만들지 않는다. 비교 목적이 절대값이면 각
  단위를 보존한 정렬 패널을, 상대 변화면 명시한 기준일의 지수·증감률을 쓰되
  한 계열이 시각적으로 평평해지는지 다시 검사한다.

## 7. 상호작용과 반응형

### 7.1 상호작용 allowlist

`interactions`는 `tooltip | legend_toggle | data_zoom | local_filter | reset`만
허용한다.

- tooltip: 키보드 focus와 pointer에서 같은 핵심 값을 읽을 수 있어야 한다.
- legend toggle: 숨긴 series와 현재 상태를 텍스트로 확인할 수 있어야 한다.
- data zoom: reset control과 현재 범위를 제공한다.
- local filter: 이미 encoding에 포함된 series/category의 표시 범위만 바꾼다.
  계산식·분모·KPI를 브라우저에서 새로 계산하지 않는다.
- control은 `<button>`·`<select>` 등 native HTML을 우선하고 accessible name,
  focus indicator, keyboard 동작을 제공한다.
- `local_filter | data_zoom | legend_toggle`을 가진 chart는 같은 chart id를
  참조하는 `control_bar` 또는 동등한 chart 내부 HTML control을 가져야 한다.
  현재 선택·범위와 reset 동작이 보이지 않으면 BLOCK한다.

v5.0의 `filter`는 **현재 chart encoding 안의 표시 필터**다. 여러 chart와 KPI를
동시에 재집계하는 전역 cross-filter는 normalized slice/data contract 없이는
값을 꾸밀 위험이 있으므로 비범위다. 향후 도입 시 별도 spec과 data lineage가
필요하다.

### 7.2 반응형

- desktop 기준 viewport는 1440×1000, mobile 기준은 390×844로 QA한다.
- mobile은 desktop을 비율 축소하지 않고 `placement.mobile.order`로 다시 쌓는다.
- KPI group은 mobile 2열, 그 외 component는 1열이다.
- page-level 가로 스크롤은 BLOCK이다. 표만 자체 scroll container를 가질 수 있다.
- mobile에서 정보 component를 임의로 숨기지 않는다. 복잡한 chart는 label 밀도를
  낮추거나 높이를 조정하되 제목·단위·근거는 유지한다.

## 8. 결정적 compiler

신규 `scripts/render_dashboard_v5.py`는 다음 입력만 받는다.

```bash
python3 scripts/render_dashboard_v5.py \
  --chart-spec runs/<run-id>/outputs/chart_spec.json \
  --layout runs/<run-id>/outputs/dashboard_layout.json \
  --data runs/<run-id>/outputs/dashboard_data.json \
  --output runs/<run-id>/outputs/dashboard.html
```

compiler 규칙:

1. 세 JSON의 schema와 v5 contract/revision/ref를 먼저 검증한다.
2. component는 viewport order와 원본 배열 순서의 안정 tie-break로 직렬화한다.
   schema가 order 중복을 허용하지 않으므로 tie-break는 방어 코드일 뿐이다.
3. DOM에는 `data-layout-version`, `data-layout-revision`, `data-component-id`,
   `data-data-ref`, `data-renderer`를 남긴다.
4. 현재 시각·random id·환경별 절대 경로를 HTML에 새로 넣지 않는다.
5. compiler는 layout을 수정하거나 누락 component를 추론해 보충하지 않는다.
6. 같은 chart/data/layout과 같은 ECharts bundle·template checksum이면 component
   순서, DOM 구조, 표시 값이 동일해야 한다. 폰트·브라우저의 작은 픽셀 차이는
   허용한다.

`dashboard_build_manifest.json`에는 입력 세 파일과 template·ECharts bundle의
sha256, compiler version, layout revision을 기록한다. 이 manifest는 재현 근거이며
승인 답변을 대체하지 않는다.

## 9. QA와 실패 처리

### 9.1 정적 계약 — BLOCK

- 세 schema invalid, v5 contract 또는 run id 불일치
- layout approval target의 path/hash/revision과 실제 파일 불일치
- component id·viewport order 중복, span 범위 밖, 잘못된 renderer/kind 조합
- 존재하지 않는 KPI/chart/panel/source 참조, primary chart 누락·중복
- chart_spec 계획 ↔ layout ↔ dashboard_data type/profile/ref 불일치
- 실제 기간을 알 수 있는데 visible text가 `시작월`·`끝월`·`기간 가격` 같은
  계산용 자리표현을 사용하거나, 화면 단위가 `단위 미확인`·`가격 단위 후보`·
  `원천 단위`로 남음
- multi-series line/area를 `overlay`로 그렸을 때 계열 관측 범위가 4배 이상
  차이 나 작은 계열이 평평해짐. 단, 승인된 `stacked_panels`는 허용
- raw HTML/JS/ECharts option 필드, 외부 URL·CDN·원격 font
- ECharts bundle/template checksum이 allowlist manifest와 불일치

### 9.2 compile — BLOCK

- compiler exception 또는 placeholder 잔존
- manifest 입력 hash와 실제 산출 입력 불일치
- component DOM 누락·중복, layout revision DOM 불일치
- ECharts option 변환 실패 또는 지원하지 않는 chart type

### 9.3 browser QA — BLOCK

- JavaScript error, ECharts instance 미생성, 데이터가 있는데 빈 chart
- component bounding box 겹침, 잘림, 0 크기
- ECharts에서 보이는 legend bounding box가 plot grid와 1px 초과로 겹치거나
  chart canvas 밖으로 잘림. 단일 계열의 불필요한 legend는 숨기고, 다중 계열
  legend는 위치에 맞게 grid 여백을 예약해야 한다.
- desktop/mobile page-level viewport overflow
- title·unit·source·active filter 상태가 DOM에서 읽히지 않음
- keyboard로 control 접근·조작 불가, accessible name 누락
- 핵심 대비 실패 또는 색상만으로 상태 구분
- 네트워크 요청 발생

### 9.4 시각 품질 — WARN + 필수 눈검토

- 과한 여백·과밀, hero가 support보다 약함, 지나치게 긴 title/tooltip
- 작은 축·범례·표 글자, 어색한 label 생략, 정보 reading order 불명확
- 목적 프리셋과 체감 밀도 불일치

QA는 항상 `outputs/qa_render_desktop.png`와
`outputs/qa_render_mobile.png`를 남긴다. 대시보드 정지점을 사용자에게 전달하기
전에 오케스트레이터가 두 파일을 직접 열어 component뿐 아니라 차트 내부의
범례·축·라벨과 plot 겹침, 잘림, 문구, 위계 관찰 결과를 채팅에 보고한다.
자동 점수만으로 눈검토를 대체하지 않는다.

기존 파이프라인처럼 기계적 BLOCK은 visualize 자동 교정 1회까지만 허용한다.
같은 BLOCK이 남으면 v4로 강등하지 않고 중단·보고한다. 분석 값/lineage BLOCK은
자동 교정하지 않는다.

## 10. 하위 호환과 변경 경계

- 현행 `templates/dashboard.html`은 legacy/v4 renderer의 회귀 기준으로 유지한다.
- v5는 별도 `templates/dashboard_v5.html`과 compiler를 사용해 기존 template의
  대규모 조건 분기를 피한다.
- 기존 dashboard_data/chart_spec의 required 목록은 바꾸지 않는다.
  `dashboard_profile_contract="v5"`만 enum에 추가한다.
- v5 전용 required 정보는 별도 layout schema와 v5 교차검증에서 강제한다.
- 기존 run에 layout을 자동 생성하지 않는다. 사용자가 재설계를 요청하면 새
  revision과 `dashboard_storyboard` 승인을 거쳐 v5 run으로 만든다.
- v4의 trend/comparison provenance, surface, small multiple, cell gradient,
  색·언어 규칙은 v5 data 계약에서도 그대로 유효하다.

## 11. 테스트 계약

| 층 | 필수 테스트 |
|---|---|
| schema | 최소 유효 layout, 각 required/enum/range negative fixture |
| cross-contract | v5 삼중 일치, missing layout, revision/hash mismatch, legacy+layout 거부 |
| compiler unit | kind별 DOM, chart type별 ECharts option, 안정 순서·manifest hash |
| security | raw HTML/JS/remote URL/CDN 차단, bundle checksum |
| browser desktop | ECharts 생성, component ref, overlap/clip/overflow, control 동작 |
| browser mobile | explicit order, KPI 2열, 나머지 1열, 표 내부 scroll |
| accessibility | accessible name, focus, keyboard, 색상 외 텍스트/기호 |
| regression | legacy fixture와 v4 fixture의 기존 DOM·동작 유지 |
| human smoke | 시계열 1건 + snapshot 1건의 desktop/mobile 직접 눈검토 |

매 커밋 전에 정확히 다음 전체 테스트가 green이어야 한다.

```bash
cd data-insight-kit && python3 -m pytest tests/ -q
```

`runs/*`는 커밋하지 않고 push하지 않는다.

## 12. 문서·에이전트 변경 범위

구현 시 다음 단일 원천을 함께 갱신한다.

- `docs/pipeline-contract.md`: layout 산출물·승인 target·renderer routing·QA 순서
- `docs/dashboard-design-system.md`: role/size hierarchy·ECharts/SVG·interaction
  문법
- `agents/analyze.md`: chart_spec 이후 layout revision 작성
- `agents/visualize.md`: raw HTML 금지, compiler 입력 생성·호출
- `agents/qa.md`: v5 static/compile/browser/눈검토
- `scripts/checkpoint_gate.py`와 schema: storyboard의 layout approval target
- `CHANGELOG.md`: 커밋별 진행 상태와 smoke 관찰

## 13. 자체 설계 검토 결과

초안 작성 뒤 승인 결정·기존 계약·실행 가능성을 다시 대조했다.

### 반영한 충돌 방지

1. **layout 유실 시 무음 v4 강등 위험**: layout 존재만으로 renderer를 고르지
   않고 chart/data의 명시적 v5 계약을 함께 요구한다. v5인데 layout이 없으면
   BLOCK한다.
2. **승인 뒤 layout 변경 위험**: storyboard `approval_targets`에 layout
   sha256+revision을 추가하고 visualize stage guard가 다시 대조한다.
3. **자유 설계가 raw ECharts code로 변질될 위험**: 자유도는 component·span·
   role·order·안전 옵션으로 제한하고 raw option/JS는 금지한다.
4. **필터가 근거 없는 재계산을 만들 위험**: v5.0 filter를 encoding 안의 표시
   필터로 한정하고 전역 재집계는 별도 data contract 전까지 제외한다.
5. **v5 조건 분기가 v4를 깨뜨릴 위험**: v5 template/compiler를 분리하고 현행
   template을 legacy/v4 회귀 기준으로 유지한다.
6. **눈검토가 자동 QA에 묻힐 위험**: 두 screenshot 생성과 오케스트레이터의
   직접 관찰 보고를 별도 출고 절차로 명시한다.

### 승인 후 구현 계획에서 구체화할 항목

- vendored ECharts 정확한 버전·라이선스·checksum
- layout schema의 regex/minLength 등 기계적 세부 제약
- chart type별 ECharts option mapping fixture 값
- 기존 `qa/validate.py`에 compiler 호출을 통합하는 함수 경계

이 네 항목은 승인된 구조를 바꾸지 않는 구현 상세이며, 상세 실행 계획에서
테스트와 커밋 단위로 고정한다.
