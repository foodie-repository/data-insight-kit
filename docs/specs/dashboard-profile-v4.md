# Dashboard Profile v4 — 태블로 아키타입 시그니처 요소

Status: draft for user review (2026-07-13, Codex 교차검증 HIGH 5·MEDIUM 5 반영)
Branch: `dashboard-profile-v4`
결정 배경: `docs/specs/dashboard-profile-v4-kickoff-notes.md` (확정 결과 5건)
관련 단일 원천: `docs/dashboard-design-system.md`(시각 언어 — 본 spec 확정 시
함께 개정), `schemas/dashboard_data.schema.json`·`schemas/chart_spec.schema.json`
(데이터 계약), `docs/pipeline-contract.md`(산출물 계약 — 갱신 필수)

## 1. 목적

v2 smoke에서 확인된 갭을 닫는다: 프로필 3종(executive_brief / analyst_workspace /
operations_monitor)이 설계 문서·렌더러 분기까지 존재하지만, 아키타입 시그니처
요소가 구현에 없어 **어떤 프로필을 골라도 차이가 체감되지 않는다**. v4는 사용자
확정 5건(kickoff 노트)을 계약으로 굳혀 렌더러·데이터·QA에 반영한다.

## 2. 범위 / 비범위

범위 (확정 D-a·D-d — 높음+중간 5건):

| # | 요소 | 대상 프로필 | 갭 심각도 |
|---|---|---|---|
| E1 | KPI 타일: 스파크라인 + 전기 대비 델타 ▲▼% | 3종 공통 | 높음 |
| E2 | analyst 첫 화면 밀도: 단일 스크롤 6~8패널 | analyst_workspace | 높음 |
| E3 | 사이드 레일 내비 | operations_monitor | 중간 |
| E4 | 스몰 멀티플 (반복 지표 비교 그리드) | analyst·operations | 중간 |
| E5 | 매트릭스 표 셀 그라데이션 | analyst_workspace | 중간 |

비범위:

- 도넛/게이지·히어로 강화 (남용 위험·부분 존재 — 확정으로 제외)
- ECharts/Plotly 백엔드 결합 (확정 D-e — **v5 후보로 분리**, v4는 순수 SVG 유지)
- 프로필 신설·storyboard 선택 흐름 변경 (v2 계약 그대로)

## 3. 원칙 (확정 결정의 계약화)

- **순수 SVG**: E1~E5 전부 외부 라이브러리 없이 구현한다. 스파크라인은
  `<polyline>`, 그라데이션은 셀 배경색 보간, 레일은 CSS 레이아웃.
- **조건부 활성화 (D-b)**: 델타·스파크는 데이터에 시계열·비교 기간의
  **구조화된 provenance**(§4.2)가 있을 때만 채운다. 근거가 없으면 필드를
  생략하고 렌더러는 현행 플랫 KPI로 강등한다. 스냅샷 데이터에서 가짜 추세를
  만들지 않는다.
- **opt-in 렌더 계약 (Codex H4)**: v4 레이아웃(E2·E3)은
  `meta.dashboard_profile_contract: "v4"`가 있을 때만 활성화한다. 이 필드가
  없는 기존 `dashboard_data.json`은 **새 템플릿으로 다시 렌더해도 현행 탭
  화면과 동일**해야 한다. "스키마 하위 호환"(신규 필드 optional)과 "렌더
  하위 호환"(화면 동일)은 별개 조건이며 둘 다 지킨다.
- **색 룰 (Codex M8 정합화)**: KPI 본값은 무채색(#0a0a0a) 유지. 델타 ▲▼%
  색은 `status=good`→좋음색, `status=bad`→나쁨색, `status=warn|neutral`→muted
  무채색. `comparison.direction`은 **기호(▲▼→)만** 결정한다 — 세 번째
  상태색을 만들지 않는다(확정 "델타만 2색"의 계약화). 색 값의 단일 원천은
  `templates/dashboard.html`의 기존 색 토큰이다(kickoff의 #35c995/#ef7d86은
  ai-pipeline-kit 룰의 참고값 — 렌더러 토큰과 다르면 렌더러 토큰을 따른다).
- **브랜드 비의존**: 레일 내비는 패널 구조에서 파생하며, 특정 브랜드 텍스트·
  내부 프로필 라벨·아이콘 리소스에 의존하지 않는다(기존 룰 유지).
- **계획 우선 (Codex M10)**: v4 표현 결정(스몰 멀티플 그룹, surface 배치,
  그라데이션)은 `chart_spec.json`에 먼저 기록되고 `dashboard_data.json`이
  이를 이행한다 — 기존 파이프라인 계약(계획→이행)을 따른다.

## 4. 데이터 계약

### 4.0 공용 시간 provenance 블록 (Codex H2)

델타·스파크의 근거는 임의 문자열이 아니라 검증 가능한 구조로 기록한다:

```json
{
  "source_id": "sbiz_store_gangnam_20260708",
  "time_field": "ym",
  "periods": ["2026-01", "2026-02", "2026-03", "2026-04", "2026-05"]
}
```

- `source_id`: **`sources[].id` 중 하나여야 한다** (QA 대조)
- `time_field`: 시간축 컬럼명
- `periods`: 실제 기간 문자열 배열 — **중복 없이 오름차순**

### 4.1 KPI 델타 — `comparison`에 판별자 추가 (Codex H1)

기존 run의 `comparison`은 기간 비교 전용이 아니다(집단·기준값 비교가 실존).
의미 파손을 막기 위해 optional 판별자 `kind`를 추가한다:

```json
{
  "kind": "period_delta",
  "basis": "전월 대비",
  "delta": 6.5,
  "direction": "up",
  "provenance": { "source_id": "...", "time_field": "ym", "periods": ["2026-04", "2026-05"] }
}
```

- `kind`: `period_delta | benchmark`. **없으면 `benchmark`로 간주하고 현행
  렌더 유지** — 기존 run 의미 보존.
- E1 델타 ▲▼%+색은 `kind=period_delta`일 때만 활성화.
- `period_delta`면 `basis`(minLength 1)·`delta`·`direction`·`provenance`
  (periods 길이 2) 필수. `direction`과 `delta` 부호 일치(QA).

### 4.2 KPI 스파크라인 — 신규 optional `trend`

```json
{
  "id": "kpi_sales", "label": "...", "value": 123, "unit": "건",
  "kind": "absolute", "status": "good",
  "format": { "precision": 0 },
  "trend": {
    "points": [98, 104, 111, 108, 123],
    "period_label": "최근 5개월",
    "provenance": { "source_id": "...", "time_field": "ym", "periods": ["...5개..."] }
  }
}
```

- `points`: **finite number 4~24개** (3개 이하는 추세로 오독 위험 — 생략)
- `provenance.periods` 길이 == `points` 길이
- `period_label`: 사용자 표현(언어 게이트 수집 대상), 캡션으로 렌더
- **trend가 있으면 조건부 강제 (Codex H3)**: `kpi.value`는 number만 허용,
  `format.precision` 필수. 문자열 KPI(범위·범주값 등)에는 trend를 금지하고
  플랫 타일로 강등 — D-b와 충돌하지 않는다.
- 정합 공식(결정적): `abs(Decimal(last_point) - Decimal(value)) <=
  0.5 × 10^(-precision)` (ROUND_HALF_UP 기준). value와 points는 모두 표시
  스케일 값(display_scale 재적용 금지).

### 4.3 스몰 멀티플 — 신규 optional `chart.small_multiple_group` (Codex M6)

- 그룹 범위는 **같은 panel 내부**로 제한. 같은 그룹 문자열(minLength 1)을
  가진 chart **2~9개**를 렌더러가 균등 그리드(최소 2열)로 묶는다.
- 허용 chart `type`은 우선 `line | area | bar`로 제한.
- 그룹 내 `type`·x축 유형·`unit`·`format`이 모두 일치해야 한다(QA BLOCK).
- 렌더러는 **그룹 전체 값으로 공통 y-domain을 한 번 계산**해 각 chart에
  적용한다 — "같은 축 스케일"의 결정적 구현.
- chart `id`는 dashboard 전역 유일(QA BLOCK — 그룹 참조 안정성).

### 4.4 매트릭스 셀 그라데이션 — table 확장 (Codex M7)

`panels[].table`에 optional `cell_gradient`:

```json
{ "cell_gradient": { "value_column_indices": [2, 3], "scale": "column" } }
```

- `value_column_indices`: **unique integer 배열** (표시명 `columns[].name`은
  중복 가능하므로 인덱스 참조) — 참조 열은 `type=number`여야 한다.
- 셀 값은 number/null만: null은 배경 없음, min==max(퇴화)면 동일 중립색.
- `scale`: `column`(열별) | `table`(전체). 계산 기준은 **렌더되는
  `rows[:row_limit]`**로 고정.
- 그라데이션 색은 **무채색(그레이 스케일) 보간만** 허용 — 밀도 표현이지
  상태 표현이 아니며, "델타만 2색" 확정과 충돌하지 않는다.

### 4.5 chart_spec 확장 (Codex M10 — 계획 우선)

`schemas/chart_spec.schema.json`에 optional 추가:

- `dashboard_design.contract_version`: `"v4"`
- `dashboard_mapping[].surface`: `primary | detail | appendix`
- `dashboard_mapping[].small_multiple_group`: string
- `dashboard_mapping[].table_treatment`: `{ "cell_gradient": ... }` 계획

QA는 chart_spec의 계획과 dashboard_data의 이행(그룹·surface·contract_version)
일치를 검사한다.

### 4.6 dashboard_data 스키마 반영

`schemas/dashboard_data.schema.json`은 `additionalProperties: false`이므로
`meta.dashboard_profile_contract`·`kpi.trend`·`comparison.kind/provenance`·
`chart.small_multiple_group`·`panel.surface`·`table.cell_gradient`를 명시적으로
추가한다. **전부 optional — required 목록 변경 없음** (스키마 하위 호환).

## 5. 렌더러 계약 (`templates/dashboard.html`)

### 5.0 활성화 게이트 (Codex H4)

- `meta.dashboard_profile_contract == "v4"`일 때만 §5.1 신규 레이아웃 활성화.
- 없으면 현행 탭 렌더러 경로 그대로 — 기존 run 재렌더 화면 동일.
- `panel.surface`(§4.5와 동일 enum): v4 계약에서 `primary`는 첫 화면,
  `detail`·`appendix`는 강등 영역(탭/접힘). 필드가 없는 panel은 `primary`.

### 5.1 프로필별 v4 첫 화면 문법

| 프로필 | v4 첫 화면 문법 |
|---|---|
| `executive_brief` | KPI 스트립(E1 타일) → 큰 메인 차트 → 보조. 현행 구조 유지 + E1만 반영 |
| `analyst_workspace` | **단일 스크롤**: KPI 블록 + primary 차트 그리드(12칸) + primary 표. 첫 화면 패널 수의 결정적 정의 = **KPI 블록(1) + primary chart 카드 수 + primary table 수**, 목표 6~8. detail/appendix는 하단 접힘/탭 강등. 패널 부족 시 있는 만큼만 — 채우기 금지 |
| `operations_monitor` | **좌측 레일 내비**: 기존 `ACTIVE` 패널 switcher를 레일 UI로 재표현(패널 제목 파생 앵커, 선택 상태만 강조색). 본문은 E1 KPI 상단 + 추세 영역 + E4 스몰 멀티플. 좁은 화면에서는 동일 항목을 상단 탭으로 렌더(반응형 강등) |

- E1 타일: 값(무채색·크게) / 델타 ▲▼%(§3 색 룰·작게) / 스파크(중립색
  polyline, 40×140px 내외) / 라벨. trend·period_delta 없으면 현행 타일.
- 스파크 SVG는 chart SVG와 **별도 selector**(예: `.kpi-spark svg` vs
  `.chart-card svg`)로 구분한다 — 렌더 QA의 개수 검사와 충돌 방지(Codex H5).

## 6. 디자인 시스템 문서 개정

`docs/dashboard-design-system.md`에 반영:

- 시각 언어 3절에 E1~E5 문법 추가 (프로필별 표)
- "KPI 수치 색상 금지" 룰에 예외 명시: 델타 ▲▼%만 상태 2색(good/bad),
  warn/neutral은 muted 무채색, direction은 기호만
- "탭당 2색"의 적용 범위 명시: 상태 accent 예산(good/bad)을 뜻하며,
  무채색 계열·중립 categorical 팔레트는 별도
- 구현 계약 절에 §4 신규 필드 예시 추가

## 7. QA 확장 (`qa/validate.py`) — 전부 결정적 검사

### 7.1 정적(BLOCK)

| 검사 |
|---|
| `trend.points` finite number 4~24 + `provenance` 필수(source_id∈sources[].id, periods 길이 일치·중복 없음·오름차순) |
| trend 있는데 `kpi.value`가 number가 아니거나 `format.precision` 없음 |
| 마지막 point ↔ value 정합: `abs(Decimal(last)-Decimal(value)) > 0.5×10^(-precision)` |
| `comparison.kind=period_delta`인데 basis(minLength 1)/delta/direction/provenance(periods 2개) 누락, 또는 delta 부호와 direction 불일치 |
| `small_multiple_group`: panel 밖 참조·그룹 크기 1 또는 10+·type∉{line,area,bar}·그룹 내 type/x유형/unit/format 불일치 |
| chart id 전역 중복 |
| `cell_gradient`: 인덱스 범위 밖·참조 열 type≠number |
| chart_spec 계획 ↔ dashboard_data 이행 불일치 (그룹·surface·contract_version) |
| `dashboard_profile_contract` 값이 "v4" 외 문자열 |

### 7.2 정적(WARN)

| 검사 |
|---|
| analyst v4 계약에서 첫 화면 패널 수(§5.1 공식) 9 이상 |
| v4 계약인데 E1~E5 요소가 하나도 없음 (계약 선언만 있고 이행 없음) |

### 7.3 언어 게이트 (기존 수집기 확장 — Codex M9)

visible-text 수집기에 `trend.period_label`·렌더되는 `comparison.basis` 추가.

### 7.4 렌더 QA (Playwright)

- selector 분리 후: chart SVG 수 검사는 `.chart-card svg` 기준으로 유지,
  spark SVG는 별도 검사 (Codex H5)
- v4 fixture: analyst 단일 스크롤 DOM(첫 화면 패널 수), operations 레일
  존재·클릭 전환·모바일 폭 탭 강등, 그라데이션 셀 background 존재
- 색 룰: KPI 본값·델타의 computed style 검사 (본값 무채색, warn|neutral
  델타 muted)
- legacy fixture: `dashboard_profile_contract` 없는 기존 dashboard_data가
  현행 탭 화면과 동일 구조로 렌더되는지 (렌더 하위 호환 회귀)

## 8. analyze/visualize 에이전트 지침

- `agents/analyze.md`: 시간 컬럼과 기간 2개 이상의 실근거가 있을 때만
  comparison(kind=period_delta)/trend를 기록하고 §4.0 provenance를 남긴다.
  근거가 없으면 필드를 만들지 않는다(강등은 렌더러 몫). benchmark 비교는
  kind=benchmark로 명시.
- `agents/visualize.md`: 반복 지표 2~9개면 small_multiple_group을 chart_spec
  계획에 먼저 기록, 매트릭스형 표에는 cell_gradient 계획 검토. surface 배치
  (primary/detail/appendix)를 chart_spec에 기록.

## 9. 검증 계획

- 매 커밋 pytest green (스키마 하위 호환 fixture, QA 각 BLOCK/WARN 단위
  테스트, 렌더러 DOM fixture 검사)
- 최종: smoke 2종 (사용자 참여) —
  ① 시계열 있는 데이터로 operations/analyst 프로필: E1~E5 체감 확인,
  ② 스냅샷 데이터(예: 강남 상가)로 강등 경로: 가짜 추세·의미 왜곡이 없는지
- runs/* 커밋 금지, push 금지 (기존 규칙)

## 10. 커밋 계획 (Codex H5 재배치 반영 — 상세는 checklist)

1. 확정 spec/checklist docs (사용자 승인 후)
2. 스키마 확장: dashboard_data + chart_spec + 정적 validator 기초 +
   하위 호환 fixture (기능 렌더 전에 계약부터)
3. 렌더 QA 기반 정리: chart/spark SVG selector 분리, legacy/v4 fixture 분리
   (기존 검사 green 유지한 채 v4 수용 준비)
4. E1 (KPI 스파크+델타 타일) + E1 정적/DOM QA
5. E2+E3 (analyst 단일 스크롤·operations 레일·반응형) + 해당 QA
6. E4+E5 (스몰 멀티플·셀 그라데이션) + 해당 QA + agent 지침
7. 문서 개정 (design system·pipeline contract 필수 갱신·CHANGELOG)
8. smoke 2종 + 발견 수정

각 기능의 validator·DOM 검사는 해당 기능 커밋에 함께 들어간다 — "매 커밋
pytest green"이 커밋 순서와 양립한다.
