# 대시보드 디자인 시스템

`data-insight-kit` 대시보드는 단순한 차트 모음이 아니라, 분석 결과를 실제로
판단하고 검토할 수 있는 화면이어야 한다. 기본 렌더러는 계속 데이터 기반으로
동작하지만, 선택한 대시보드 프로필에 따라 정보 밀도, 레이아웃 강조점, 독자가
기대하는 사용 방식이 달라진다.

프로필은 `dashboard_storyboard` 체크포인트에서 선택하며, 다음 산출물에
기록한다.

- `checkpoint_answers.json`: 최신 `dashboard_storyboard` 답변
- `chart_spec.json`: 선택 항목인 `dashboard_design`
- `dashboard_data.json`: `meta.dashboard_profile`
- v5 `dashboard_layout.json`: 승인할 role·크기·desktop/mobile 읽기 순서

## 프로필 카탈로그

| 프로필 | 사용하면 좋은 경우 | 레이아웃 패턴 | 강점 | 피해야 할 경우 |
|---|---|---|---|---|
| `executive_brief` | 독자가 몇 분 안에 핵심 답을 파악해야 할 때 | KPI 스트립, 핵심 차트 1-2개, 명확한 스토리와 액션 | 빠른 요약, 리더십 리뷰, 읽기 쉬운 보고서 | 촘촘한 탐색용 표, 작은 차트 과다 배치 |
| `analyst_workspace` | 독자가 세그먼트와 예외를 직접 살펴봐야 할 때 | 촘촘한 그리드, 히트맵/산점도/표 지원, 더 많은 패널 | 진단, 세그먼트 비교, 관계 확인 | 장식적인 카드, 정보가 부족한 넓은 화면 |
| `operations_monitor` | 반복 지표를 기간별로 추적해야 할 때 | 상태 카드, 스파크라인, 추세/예외 패널, 필요 시 사이드 내비게이션 느낌 | 주간/월간 운영, 서비스 성과, 제품/마케팅 모니터링 | 업데이트 주기가 없는 일회성 전략 서사 |

`custom_domain`은 핵심 프로필이 아니다. 도메인 팩은 라벨, 강조색, KPI 문구,
차트 선호도를 덮어쓸 수 있지만, 기본 구조는 세 가지 핵심 프로필 중 하나를
기반으로 선택해야 한다.

## 선택 기준

다음 상황에서는 기본적으로 `executive_brief`를 사용한다.

- 독자가 `executive` 또는 `mixed`인 경우
- 사용자가 요약 보고서를 요청한 경우
- 강하게 답할 수 있는 차트 질문이 4개 미만인 경우
- 산출물을 정돈된 공유용 결과물로 전달해야 하는 경우

다음 상황에서는 `analyst_workspace`를 사용한다.

- 사용자가 심층 분석, 원인 탐색, 예외 검토를 요청한 경우
- 데이터가 추세, 분포, 관계, 구성비, 히트맵 중 최소 2개 이상의 관점을
  지원하는 경우
- 사용자가 세그먼트, 코호트, 지역 등을 비교하고 싶어 하는 경우

다음 상황에서는 `operations_monitor`를 사용한다.

- 반복되는 보고 기간, SLA, 퍼널, 캠페인, 제품, 서비스 지표가 있는 경우
- 현재 상태와 이전 기간 대비 변화를 함께 봐야 하는 경우
- 대시보드를 정기적으로 다시 열어볼 가능성이 높은 경우

## 사용자에게 보이는 문구 규칙

- 프로필 이름은 내부 계약이다. `executive_brief`, `analyst_workspace`,
  `operations_monitor` 같은 값을 화면에 그대로 노출하지 않는다.
- 대시보드 제목, 카드 라벨, 축 라벨, 보고서 도입부는 독자가 이해할 수 있는
  표현을 사용한다. `proxy`, `layer`, `grain`, `chart_spec`, `source_ref`, 원본
  컬럼명, 코드값 같은 내부 용어는 방법론이나 부록에만 둔다.
- 프로필은 근거 기준을 바꾸지 않는다. 정보 밀도와 레이아웃 강조점만 바꾼다.
- 사용자가 데이터와 맞지 않는 프로필을 선택하면 `dashboard_storyboard`
  체크포인트에서 장단점을 설명하고 더 안전한 프로필을 추천한다.
- **직관 문구 원칙 (v4 smoke 사용자 피드백)**: 대시보드는 한눈에 읽혀야
  한다 — 카드 문구가 명사구 나열이면 독자가 여러 번 읽어야 한다.
  - story(현황/원인/결과/대응)·action의 value는 **완결된 결론 문장**으로
    쓴다. 가능하면 구체 수치·대상을 포함한다.
    나쁨: "월별 흐름 우선" / 좋음: "최신월만 보지 말고 12개월 흐름으로
    판단한다".
    나쁨: "가격과 거래량 분리 확인" / 좋음: "가격이 올라도 거래가 줄면
    강세로 단정하지 않는다".
  - action은 실행 문장(무엇을 하라)으로 쓴다. "추가 확인 대상 분리"(✗) →
    "가격↑·거래↓ 11개 구는 다음 달 다시 확인한다"(✓).
  - 축약된 분석 용어(괴리, 저거래 월, 분모 등)는 카드 첫 등장에서
    풀어 쓰거나 desc에서 한 문장으로 설명한다.
  - KPI 라벨은 기존 룰(결론형·질문형) 유지. desc·note도 "그래서 무엇을
    보라는 것인지"가 한 문장으로 읽히게 쓴다.
  - `시작월`, `끝월`, `최근 끝점`, `기간 가격`처럼 분석자가 계산 위치를
    가리키는 표현은 독자가 기준을 다시 찾게 만든다. 실제 날짜와 집계 의미를
    쓴다: `시작월보다 높다`(✗) → `2022-01보다 2026-06 가격이 8.7% 높다`(✓),
    `기간 가격`(✗) → `2022-01~2026-06 월별 중앙가격의 중앙값`(✓).
  - 금액 단위는 독자가 바로 읽을 수 있는 통화 단위로 확정한다. 원천 메타가
    없으면 원천 문서 → 도메인 관행+값 범위 → 사용자 확인 순으로 근거를
    보강하고 분석 기록에 남긴다. 끝까지 확인할 수 없으면 `단위 미확인`을
    화면에 내보내지 말고 해당 금액 수치를 제외하거나 출고를 막는다.
  - 금액·수량처럼 크기를 읽는 1,000 이상 숫자는 `10,970건`,
    `238,228만원`처럼 천 단위 구분기호를 사용한다. KPI, 차트 라벨·값축,
    표, story와 설명에서 같은 규칙을 유지하되 날짜·기간·코드·ID에는 적용하지
    않는다. 소수 자릿수와 단위는 원래 지표 계약을 유지한다.
  - **변명·면책 문장 금지**: "추가 확인 대상이다", "이 데이터만으로
    확정하지 않는다" 같은 문장은 카드에서 독자에게 아무 정보도 주지
    않는다. 과대해석 금지는 **단정 표현을 쓰지 않는 것**으로 지키고,
    카드 본문은 **보이는 현상을 수치로 서술**한다.
    나쁨: "가격 상승과 거래량 감소가 함께 나타난 추가 확인 대상이다.
    원인은 이 데이터만으로 확정하지 않는다."
    좋음: "가격이 +12.8% 오르는 동안 거래량은 -45.9% 줄었다."
    원인 보강은 intake의 evidence_scope가 web_context를 허용할 때만
    외부 근거로 하고, data_only면 관측 서술에 그친다. 데이터 한계 고지는
    방법론/부록·주의 문구(P 액션) 한 곳에 모은다 — 카드마다 반복하지
    않는다.

## 시각 언어

### `executive_brief`

- 차분한 블루 그레이 배경과 흰색 카드 조합을 사용한다.
- 큰 KPI 스트립을 먼저 두고, 가장 중요한 차트 1개를 메인 영역으로 크게
  배치한다.
- 첫 화면에는 KPI 카드 4-6개, 메인 차트 1개, 보조 차트 1-2개 정도를 둔다.
- 보조 차트와 story block은 메인 차트 옆 또는 아래에 놓고, 상세 표와 작은
  탐색 차트는 뒤쪽으로 보낸다.
- 핵심 차트 영역은 한 번에 하나의 판단 질문에 답하도록 구성한다.
- 액션 카드는 분석 근거가 충분할 때만 사용한다.

### `analyst_workspace`

- 간격을 좁히고 카드를 더 촘촘하게 배치한다.
- 한 패널에 더 많은 차트를 둘 수 있지만, 각 차트는 서로 다른 질문에 답해야
  한다.
- 서로 다른 관점을 드러낼 수 있다면 히트맵, 산점도, 비교 막대, 분포, 표,
  예외 목록을 우선 고려한다.
- 렌더러는 12칸 그리드를 기준으로 line/area/scatter/heatmap/boxplot 같은
  진단형 차트를 더 넓게 배치하고, 단순 막대 차트는 작은 카드로 배치한다.
- 색은 절제해서 사용한다. 장식이 아니라 그룹 구분이나 신호 표현에만 쓴다.
- 단위가 다르거나 변화폭 차이 때문에 한 선이 눌리는 시계열은 한 축에
  겹치지 않는다. 같은 시간축을 공유하는 위아래 패널로 분리하고 각 패널에
  지표명·단위를 직접 표시한다. 지수화했더라도 관측 범위가 크게 다르면 같은
  검사를 적용한다.

### `operations_monitor`

- 현재 기간, 이전 기간 대비, 추세/예외 패널을 앞세우는 상태 중심 레이아웃을
  사용한다.
- 같은 지표가 팀, 채널, 제품, 기간별로 반복될 때는 스몰 멀티플과
  스파크라인이 유용하다.
- 내비게이션은 레일 또는 사이드바처럼 보일 수 있지만, 렌더러가 특정 브랜드
  텍스트, 내부 프로필 라벨, 아이콘에 의존해서는 안 된다.
- 렌더러는 KPI와 story/action을 상태 영역에 모으고, line/area/slope 또는
  시간축 차트를 추세 영역에 우선 배치한다.
- 강한 강조색은 상태 표시나 선택된 내비게이션에만 제한적으로 사용한다.

## 렌더러 레이아웃 문법

기본 `templates/dashboard.html`은 같은 `dashboard_data.json`을 받아도
`meta.dashboard_profile`에 따라 다음과 같이 배치한다.

| 프로필 | 첫 화면 우선순위 | 차트 배치 | 표/액션 배치 |
|---|---|---|---|
| `executive_brief` | KPI strip → 큰 메인 차트 → 보조 차트/story | 첫 chart를 메인 카드로 크게 배치하고, 2-3번째 chart를 보조 카드로 둔다. 나머지는 secondary 영역에 둔다. | 상세 표는 뒤쪽에 두고, 액션은 근거가 충분할 때만 표시한다. |
| `analyst_workspace` | story → KPI → 촘촘한 분석 그리드 | 12칸 그리드에서 히트맵·산점도·분포·추세 차트를 넓게, 단순 막대는 작게 둔다. | 표와 예외 목록을 탐색 근거로 적극 표시한다. |
| `operations_monitor` | KPI/상태 영역 → 추세 영역 → 예외/액션 | 시간축·상태 변화 chart를 우선 추세 영역에 놓고, 나머지는 보조 영역에 둔다. | story와 action은 상태 영역에 묶어 반복 확인하기 쉽게 둔다. |

프로필은 시각적 취향이 아니라 독자의 작업 방식이다. 같은 데이터라도
요약형은 "핵심 판단", 탐색형은 "비교와 예외", 모니터링형은 "상태와 변화"를
먼저 보이게 한다.

## v5 자유 레이아웃 문법 (dashboard-freeform-v5)

v5의 자유도는 임의 HTML 작성이 아니라 승인 가능한 component 배치에서 나온다.
analyze가 `dashboard_layout.json` 초안을 만들고, `dashboard_storyboard`가
component 순서·desktop span·mobile order와 layout hash/revision을 승인한다.

### role과 크기 위계

- role은 `navigation`, `summary`, `hero`, `primary`, `support`, `evidence`만 쓴다.
- `hero`는 화면 전체에서 최대 하나이며 가장 중요한 판단 질문에 배정한다.
  support component는 desktop에서 hero보다 넓게 배치하지 않는다.
- desktop은 12-column grid다. `column_start + span - 1`이 12를 넘을 수 없고,
  height는 `sm|md|lg|xl|auto` 중 하나다.
- profile은 목적을 정하고 layout은 실제 위계를 정한다. 프로필 이름만 바꿔
  같은 그리드를 반복하지 않는다.
- v5 desktop `max_width`는 `standard=1180px`, `wide=1720px`,
  `full=viewport`로 고정한다. 탐색형 16:9 화면은 `wide`를 사용해 차트의 축과
  라벨 공간을 확보한다.

### v5 강조색과 표시 문구

- 단일 계열 비교 차트의 기본색은 중립색이다. 강조할 근거가 있을 때만
  `series[].point_roles`로 한 항목에 role 색을 부여한다.
- series 전체 role은 계열 간 의미 구분에 쓰고, point role은 계열 안의 단일
  강조에 쓴다. 데이터와 layout에 실제 hex를 기록하지 않는다.
- heatmap 연속값은 `낮음 → 높음` sequential scale을 사용한다. 최대·최소 대비가
  화면에서 구분되어야 하며 의미 있는 중앙 기준이 없으면 diverging 색을 쓰지 않는다.
- KPI 본값은 계속 무채색으로 유지한다. 값이 없거나 데이터 한계를 문장으로만
  반복하는 KPI 카드는 만들지 않고 header·주석·한계 설명으로 내린다.
- 단위는 `(단위: 개)`처럼 본문과 구분하고, `스냅샷`, `내부 기준` 같은 구현·분석
  용어는 `기준일`, `지역 규모를 감안한 기준`처럼 사용자 언어로 풀어 쓴다.
- 출처는 전체 폭의 큰 카드 대신 compact footer 주석으로 표시하되 source ref,
  기준일, 표본 정책의 provenance는 잃지 않는다.

### ECharts와 SVG/CSS 책임 분리

| component kind | renderer | 책임 |
|---|---|---|
| `chart` | 로컬 ECharts 6.1.0 canvas | line, area, bar, stacked_bar, histogram, scatter, heatmap, boxplot, waterfall, slope |
| `header`, `control_bar`, `kpi_group`, `insight`, `table`, `source_note` | canonical SVG/CSS/DOM | 문서 구조, 수치, 설명, 표, 출처, 보이는 조작 상태 |

에이전트는 raw HTML·CSS·JavaScript·ECharts option을 넣지 않는다. 차트 option은
`dashboard_data.json`의 검증된 encoding과 layout의 제한된 `render_options`에서
mapper가 만든다. CDN, 외부 URL, 원격 font도 허용하지 않는다.

### 안전한 상호작용

- tooltip은 읽기 보조이며 원 데이터를 다시 계산하지 않는다.
- legend toggle, data zoom, local filter처럼 화면 상태를 바꾸는 기능은 해당
  chart를 참조하는 `control_bar`에 같은 interaction과 `reset`이 있어야 한다.
- local filter는 chart encoding 안에서 보이는 series/category만 좁힌다.
  KPI·분모를 브라우저에서 재계산하거나 전역 cross-filter를 만들지 않는다.
- 모든 control은 키보드로 접근 가능하고 이름이 있어야 하며, 현재 상태와
  원복 방법이 화면에 보여야 한다.

### mobile reading order

- mobile의 모든 component는 `span=12`로 한 열에 쌓고 order를 중복 없이
  명시한다. desktop 위치를 CSS 자동 줄바꿈에 맡겨 mobile 순서를 추론하지 않는다.
- 기본 흐름은 맥락/요약 → 핵심 질문 → 보조 근거 → 상세 표 → 출처다. 실제
  순서가 다르면 `design_rationale.mobile_reading_order_reason`에 판단 이유를 쓴다.
- QA는 1440×1000과 390×844에서 component 겹침·overflow·빈 차트·revision·
  control 이름뿐 아니라 ECharts legend와 plot grid의 내부 겹침·legend 잘림을
  검사하고 두 screenshot을 남긴다. 출고 전에는 사람이 두 장을 직접 보고
  범례·축·라벨·plot의 시각 충돌, hero/support 위계와 문구 직관성까지 확인한다.
- 단일 계열 legend는 중복 정보이므로 숨긴다. 다중 계열 legend는 `top|right|bottom`
  위치에 맞춰 grid 여백을 먼저 예약한 뒤 표시한다.

## v5.1 계획·시각 품질 계약

단일 원천은
`docs/specs/visual-quality-convergence-v5.1.md`다. v5.1은 별도 렌더러나 별도
kit가 아니라 v5 입력과 QA에 추가하는 opt-in이다. chart spec은
`quality_contract.version = "v5.1"`, layout은
`quality_contract_version = "v5.1"`을 함께 선언한다.

- **계획 품질 계약**은 의사결정·독자·검토 주기·원천과 freshness를 먼저
  고정하고, metric을 hero·diagnostic·guardrail·detail 역할로 나눈다. 각 chart는
  하나의 질문, metric lineage, 관측 수·계열 수·최소 조건과 fallback을 갖는다.
- **시각 품질 계약**은 `copy_context`, `scale_policy`, `palette_policy`,
  `non_color_channels`, label·legend·mobile 전략을 구현 전에 고정한다. 서로 다른
  단위를 한 축에 겹치지 않고, 막대는 0 기준을 사용하며, 색만으로 계열을
  구분하지 않는다.
- `copy_context`는 범위·지표·실제 기간·단위 문맥을 검증하는 근거다. renderer가
  문장을 조립하는 **문장 생성기**가 아니며, analyze가 근거가 있는 독자 문구를
  작성한다.
- 구조화된 측정값은 locale에 맞는 천 단위 구분기호로 렌더하고, 단위가 붙은
  네 자리 이상 수량·금액이 자유 문구에 구분기호 없이 남으면 출고를 막는다.
  날짜·기간·식별 숫자는 이 검사에서 제외한다.
- 단일 측정값은 중립색을 기본으로 하고, 의미 있는 강조·identity·연속값·중앙
  기준이 있는 차이에만 그 목적에 맞는 색을 쓴다. 색을 쓰면 label, shape,
  line style, open fill, panel, order 중 하나 이상을 함께 사용한다.
- 1440×1000, 736×1000, 390×844, 320×800에서 browser QA를 실행한다. 320px에서
  차트를 읽기 어렵다면 계획된 table fallback을 사용한다. 생성된 네 screenshot은
  모두 오케스트레이터가 직접 검토하며, 검토 기록이 현재 screenshot hash와
  일치하고 `status=pass`일 때만 사용자 checkpoint로 전달한다.

## v4 시그니처 요소 (dashboard-profile-v4)

계약 상세는 `docs/specs/dashboard-profile-v4.md`가 단일 원천이다.

| 요소 | 프로필 | 문법 |
|---|---|---|
| E1 KPI 스파크+델타 | 3종 공통 | 값(무채색) / 델타 ▲▼%(아래 색 규칙) / 중립색 polyline 스파크 + 기간 캡션. `trend`·`comparison(kind=period_delta)`가 데이터에 있을 때만 — 없으면 플랫 타일로 강등 |
| E2 단일 스크롤 | analyst | `meta.dashboard_profile_contract:"v4"`일 때 탭 대신 primary 패널 스택. 첫 화면 = KPI 블록 + primary 차트 + primary 표, 목표 6~8. detail/appendix는 접힘 강등 |
| E3 레일 내비 | operations | 좌측 레일 = 패널 제목 파생 switcher(브랜드 비의존), 좁은 화면에서 상단 가로 배치로 강등. 선택 상태만 강조색 |
| E4 스몰 멀티플 | analyst·operations | 같은 panel의 `small_multiple_group` 차트 2~9개를 공통 y축 그리드로. type은 line/area/bar만 |
| E5 셀 그라데이션 | analyst | `table.cell_gradient` — 무채색 보간만(밀도 표현). 인덱스로 number 열 참조 |

### 색 규칙 예외 (v4에서 확정)

- KPI 본값 무채색 원칙은 그대로다. **델타 ▲▼%만** 상태색을 가질 수 있다:
  `status=good`→좋음색, `status=bad`→나쁨색, **`warn`·`neutral`→muted 무채색**
  (세 번째 상태색을 만들지 않는다). `comparison.direction`은 기호만 결정한다.
- `kind`가 없는 comparison(benchmark)은 기존 렌더 그대로다 — 기간 델타처럼
  보이게 바꾸지 않는다.
- "탭당 최대 2색"은 상태 accent(good/bad) 예산을 뜻한다. 무채색 계열과
  중립 categorical 팔레트는 이 예산에 포함되지 않는다. 셀 그라데이션은
  무채색만 허용되므로 예산을 소비하지 않는다.
- 색 값의 단일 원천은 `templates/dashboard.html`의 색 토큰이다.

## 스토리보드 체크포인트 요구사항

`dashboard_storyboard` 체크포인트는 사용자에게 다음 두 가지를 모두 확인받아야
한다.

- 차트 계획: 어떤 데이터, 지표, 비교 기준, 차트, 대안을 사용할지
- 대시보드 프로필: `executive_brief`, `analyst_workspace`,
  `operations_monitor` 중 무엇을 사용할지
- v5일 때 자유 레이아웃: component 역할·desktop span·mobile order와 revision

추천 답변에는 해당 프로필이 사용자의 목적에 왜 맞는지 포함해야 한다.
사용자가 자유 서술로 답하면 에이전트는 원문 요청을 `checkpoint_answers.json`에
보존하고, `visualize` 단계에서 이를 `meta.dashboard_profile` 값으로 변환한다.

## 구현 계약

`dashboard_data.json`:

```json
{
  "meta": {
    "dashboard_profile": "executive_brief"
  }
}
```

`chart_spec.json`:

```json
{
  "dashboard_design": {
    "selected_profile": "executive_brief",
    "density": "standard",
    "navigation": "tabs",
    "rationale": "Fast summary with KPI strip and a small number of decision charts.",
    "alternatives_considered": [
      {
        "profile": "analyst_workspace",
        "tradeoff": "Better for diagnosis, but too dense for the requested summary."
      }
    ]
  }
}
```

v4 표현 요소를 쓰는 run은 다음을 추가한다 (전부 optional — 계약 상세와
provenance 규칙은 `docs/specs/dashboard-profile-v4.md`):

```json
{
  "meta": { "dashboard_profile_contract": "v4" },
  "kpis": [{
    "comparison": { "kind": "period_delta", "basis": "전월 대비", "delta": 6.5,
                    "direction": "up",
                    "provenance": { "source_id": "src1", "time_field": "ym",
                                    "periods": ["2026-04", "2026-05"] } },
    "trend": { "points": [98, 104, 111, 123], "period_label": "최근 4개월",
               "provenance": { "source_id": "src1", "time_field": "ym",
                               "periods": ["2026-02", "2026-03", "2026-04", "2026-05"] } }
  }],
  "panels": [{ "surface": "primary",
               "charts": [{ "small_multiple_group": "team_trends" }],
               "table": { "cell_gradient": { "value_column_indices": [1], "scale": "column" } } }]
}
```

`chart_spec.json`에는 같은 결정을 계획으로 먼저 기록한다
(`dashboard_design.contract_version`, `dashboard_mapping.surface/
small_multiple_group/table_treatment`) — QA가 계획↔이행 일치를 검사한다.

렌더러는 `meta.dashboard_profile`이 없는 과거 run도 처리해야 한다. 이 경우
`executive_brief`로 fallback한다. `dashboard_profile_contract`가 없는 run은
v4 레이아웃 없이 현행 탭 화면 그대로 렌더된다 (렌더 하위 호환).

v5는 chart spec과 dashboard data가 모두 contract `v5`를 선언하고 승인된
`dashboard_layout.json`이 있을 때만 선택된다. 세 조건 중 하나라도 어긋나면
fallback하지 않고 BLOCK한다. 정식 생성 명령은 다음과 같다.

```bash
python3 scripts/render_dashboard_v5.py \
  --chart-spec runs/<run-id>/outputs/chart_spec.json \
  --layout runs/<run-id>/outputs/dashboard_layout.json \
  --data runs/<run-id>/outputs/dashboard_data.json \
  --output runs/<run-id>/outputs/dashboard.html
```
