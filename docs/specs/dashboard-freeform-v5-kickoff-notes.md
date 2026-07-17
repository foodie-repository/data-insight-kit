# v5 Kickoff 노트 — 에이전트 자유 설계 대시보드 (freeform)

Status: v5 kickoff 인터뷰 F-a~F-e·설계 D1~D3·상세 spec 승인 완료
(2026-07-14 사용자 답변: "설계 승인").
상세 spec은 설계 섹션 승인 후 작성한다.

## 배경 (사용자 발화 요지)

- "대시보드가 기본적으로 정형화된 틀이 있어서 너무 거기에 맞춰서 만드는 것
  같다. 자유도를 높여서 만드는 건 어때?"
- "데이터 특징과 분석 결과에 맞춰 유연하게 대시보드를 설계하는 방향으로
  검토했었는데 가독성도 떨어지고 문구도 직관적이지 않다."

## 확정 방향 (2026-07-13 대화)

- **v5 1번 과제 = 자유도 확대 (b)**: 에이전트가 `dashboard.html`을 데이터
  특징에 맞춰 직접 설계·작성한다. kit은 스타일 토큰·컴포넌트 CSS·계약만
  제공하고, QA가 가드레일을 담당한다.
- 중간 단계 (a)(레이아웃 힌트 계약 확장)는 **별도 작업으로 하지 않는다** —
  (b)가 오면 대체될 중간 계단이라 버리는 작업이 된다. (a)의 유용한 아이디어
  (첫 화면 구성 결정권)는 (b) 설계에 흡수한다.
- 기존 v5 후보였던 **ECharts/Plotly 백엔드 결합 논의를 (b) 안에 흡수**한다 —
  "에이전트 자유 설계 + 어떤 렌더 기술 스택"은 한 몸의 질문이다.

## Kickoff 결정 기록 (진행 중)

### F-a. 자유도 경계 — 확정 (2026-07-14 사용자 답변: "1번")

- **컴포넌트 기반 자유 설계**를 채택한다.
- 에이전트가 데이터와 분석 결과에 맞춰 정보 순서, 차트 크기, 그리드, 강조
  위계, 반응형 배치를 자유롭게 결정한다.
- kit은 스타일 토큰, 핵심 컴포넌트, 데이터 계약, 계획-이행 일치, 언어 게이트,
  렌더 QA를 강제한다.
- 고정 프로필 템플릿에 내용을 끼워 맞추는 방식으로 회귀하지 않는다.

### F-b. 렌더 스택 — 확정 (2026-07-14 사용자 답변: "응")

- **ECharts + SVG/CSS 혼합**을 v5 core로 채택한다.
- 주요 분석 차트는 로컬 번들 ECharts로 렌더하고 CDN은 사용하지 않는다.
- KPI, 스파크라인, 상태 배지, 미니 UI는 SVG/CSS 컴포넌트를 사용한다.
- Matplotlib·Seaborn은 EDA, 통계 검증, 정적 보고서·부록 산출에 허용한다.
- Plotly는 ECharts와 중복되는 core renderer로 병행하지 않고, ECharts로
  표현하기 어려운 특수 진단 부록에만 선택적으로 허용한다.

### F-c. 재현성 계약 — 확정 (2026-07-14 사용자 답변: "1번")

- **구조 고정 + 시각 오차 허용**을 채택한다.
- 최초 설계에서는 에이전트가 자유롭게 구성하되, 승인된 컴포넌트 id·순서·
  크기·그리드 span·렌더러·반응형 규칙을 구조화된 설계안으로 저장한다.
- 같은 입력 데이터와 같은 승인 설계 revision으로 재실행하면 데이터와 DOM
  구조는 동일해야 한다. 브라우저·폰트 렌더링에 따른 작은 픽셀 차이는 허용한다.
- 의도적인 재설계는 설계 revision을 올리고 화면 근거를 다시 검토·승인한다.
- HTML byte hash나 screenshot pixel 완전 동일은 BLOCK 기준으로 삼지 않는다.

### F-d. 자유 HTML QA — 확정 (2026-07-14 사용자 답변: "1번")

- **중대 오류 BLOCK + 품질 문제 WARN**의 2단계 정책을 채택한다.
- BLOCK: 스키마·lineage·계획/설계 revision 불일치, 잘못된 값, 빈 차트,
  JavaScript 오류, 컴포넌트 겹침·잘림·viewport overflow, 외부 CDN/리소스,
  키보드 조작·접근 가능한 이름·색상 대비·색상 단독 인코딩의 핵심 위반.
- WARN: 과도한 여백·과밀, 약한 크기 위계, 문구·tooltip 가독성처럼 미적 판단이
  필요한 항목. 자동 점수만으로 출고를 막지 않는다.
- desktop/mobile 스크린샷을 항상 남기고, 오케스트레이터의 직접 눈검토와 관찰
  보고를 출고 전 필수 절차로 유지한다.

### F-e. 기존 프로필 3종 — 확정 (2026-07-14 사용자 답변: "1번")

- `executive_brief`, `analyst_workspace`, `operations_monitor`를 **목적 프리셋**으로
  유지한다.
- 프로필은 독자, 정보 우선순위, 밀도, 상호작용 기대를 안내하지만 고정 grid,
  rail, tab 또는 컴포넌트 배치를 강제하지 않는다.
- 에이전트는 선택된 목적 프리셋을 데이터에 맞는 자유 레이아웃으로 구현하고,
  설계안에 그 목적을 어떻게 반영했는지 설명한다.
- 기존 `chart_spec.dashboard_design.selected_profile`과
  `dashboard_data.meta.dashboard_profile` 계약은 하위 호환을 위해 유지한다.

## 설계 검토 기록 (진행 중)

### D1. 아키텍처·데이터 흐름 — 확정 (2026-07-14 사용자 답변: "2번")

- **자유 레이아웃 명세 + 결정적 렌더러**를 채택한다.
- analyze는 기존 `chart_spec.json`과 함께 신규 `dashboard_layout.json` 초안을
  만들고, `dashboard_storyboard`에서 layout revision을 승인받는다.
- `dashboard_layout.json`은 컴포넌트 id·순서·크기·grid span·renderer·반응형
  규칙을 저장하며 승인된 화면 구조의 단일 원천이다.
- visualize는 `dashboard_layout.json` + `dashboard_data.json` + 로컬 ECharts
  번들 + SVG/CSS 컴포넌트를 결정적으로 조립해 `dashboard.html`을 만든다.
- 에이전트가 정보 위계와 자유 레이아웃을 직접 설계하되, 승인 이후 raw HTML을
  임의로 다시 쓰지 않는다. 기존 v4/legacy renderer 경로는 하위 호환으로 남긴다.

### D2. 컴포넌트·상호작용·반응형 — 확정 (2026-07-14 사용자 답변: "A")

- **적응형 의미 계층**을 v5 기본 레이아웃 문법으로 채택한다.
- desktop 첫 화면은 12-column grid 위에서 KPI row 다음에 `hero 8 + 핵심 해석 4`,
  이어서 primary analysis `6 + 6`, 마지막에 전체 폭 근거표를 두는 구성을 기본
  출발점으로 삼는다. 데이터 질문에 따라 span과 컴포넌트 수는 바꿀 수 있지만,
  hero와 보조 정보의 크기 위계는 분명해야 한다.
- mobile은 desktop 위치를 축소 복제하지 않고 같은 의미 계층을 명시적 reading
  order로 적층한다. KPI는 2열, hero·해석·분석·근거표는 1열을 기본으로 하며
  가로 스크롤을 만들지 않는다.
- 주요 분석 차트는 ECharts의 tooltip·legend·filter·data zoom을 질문에 필요한
  범위에서 사용한다. KPI·스파크·상태·짧은 근거 UI는 SVG/CSS로 유지한다.
- 상세 근거는 화면에서 제거하지 않고 표 또는 drill-down 컴포넌트로 남긴다.
  필터 적용 상태와 데이터 기준일은 사용자가 항상 확인할 수 있어야 한다.

### D3. QA·실패 처리·v4 호환 — 확정 (2026-07-14 사용자 답변: "A")

- **명시적 이중 경로 + v5 실패 차단(fail-closed)**을 채택한다.
- 기존 v4/legacy run은 기존 renderer로 계속 열 수 있게 유지한다. 신규 v5 run은
  `layout_version: 5`와 승인 revision을 명시하고 v5 compiler만 사용한다.
- v5 schema·revision·lineage·compile·browser QA가 실패하면 BLOCK한다. 승인된
  v5 구조와 다른 v4 화면으로 자동 강등해 오류를 숨기지 않는다.
- 검사는 정적 계약 → 결정적 compile → desktop/mobile browser QA → 필수
  screenshot 눈검토 순서로 실행한다.
- 기존 run 호환, v5 negative fixture, DOM 구조 재현, desktop/mobile E2E를 테스트
  축으로 삼는다. screenshot pixel 완전 동일은 요구하지 않는다.

## v4에서 이월되는 자산 (렌더러가 바뀌어도 유지)

- 데이터 계약: trend/comparison provenance, 델타 색 룰(본값 무채색·델타만
  2색·warn/neutral muted), 스몰 멀티플 의미론, surface, cell_gradient
- 계획-이행 일치(chart_spec 우선), 언어 게이트, 렌더 QA의 **카드 겹침
  BLOCK**(v4 smoke 발견으로 추가 — 자유 HTML의 필수 안전망)

## 품질 기준 (v4 smoke ① 사용자 피드백, 2026-07-14)

- **크기 위계**: 크게 봐야 할 차트는 크게, 보조 카드는 작게 — 현재는 전부
  작아서 가독성이 떨어진다. 화면 여백 과다·배치 두서없음도 해소 대상.
- **레퍼런스 기준선**: 사용자가 원래 참고한
  `실습 파일/Part 2. 시각화 전략 자동 설계/ai-pipeline-kit/dashboard-sample.html`
  보다 부족하면 안 된다 — v5 설계 전 이 샘플의 배치·위계·밀도를 분석해
  기준으로 삼는다.
- **태블로 요소의 강점 계승**: v4 kickoff 노트의 아키타입 시그니처
  (KPI 스파크+델타·레일·스몰 멀티플·매트릭스·첫 화면 밀도)를 자유 설계
  안에서도 유지·발전.
- **문구**: 직관 문구 원칙 + 변명·면책 문장 금지 (design system 문구 규칙
  — v4 smoke에서 확정).

## kickoff 인터뷰에서 결정할 것 (후보)

- F-a. 자유도 경계: 완전 자유 HTML vs 컴포넌트 킷 조립 (스타일 토큰 강제 수위)
- F-b. 렌더 스택: 순수 SVG 유지 vs ECharts/Plotly 허용 (CDN 금지 룰과의 관계)
- F-c. 재현성 계약: 같은 데이터로 재실행 시 화면 변동 허용 범위, diff 검증
- F-d. QA 강화 범위: 임의 HTML에 대한 겹침·색·언어·데이터 정합·접근성 검사
- F-e. 프로필 3종의 지위: 자유 설계의 출발 가이드로 유지 vs 폐지
