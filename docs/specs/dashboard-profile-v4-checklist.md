# Dashboard Profile v4 Checklist

Status: complete — 커밋 1~8 구현·검증 완료, smoke 2종 완주 (2026-07-14)
단일 원천: `docs/specs/dashboard-profile-v4.md`. 구현 중 결정이 바뀌면 먼저
spec과 이 checklist를 수정한 뒤 코드에 반영한다. 매 커밋 pytest green,
push 금지, runs/* 커밋 금지.

## 0. 기준문서 (커밋 1)

- [x] kickoff 노트 확정 결과 5건 기록 (2026-07-13 인터뷰)
- [x] `docs/specs/dashboard-profile-v4.md` 초안
- [x] `docs/specs/dashboard-profile-v4-checklist.md` 초안
- [x] Codex 교차검증(xhigh) — HIGH 5·MEDIUM 5 발견 전부 spec 반영
      (H1 comparison.kind 판별자, H2 구조화 provenance, H3 trend 시 value
      number+precision 강제+Decimal 공식, H4 contract v4 opt-in+surface,
      H5 커밋 재배치+selector 분리, M6 그룹 panel 제한+공통 domain,
      M7 인덱스 참조, M8 warn/neutral muted, M9 QA 보강, M10 chart_spec 계획)
- [x] 사용자 검토·승인 반영 (2026-07-13 "승인할게")
- [x] 커밋 1 (docs) — pytest green (148 passed, 110 subtests)

## 1. 스키마 확장 (커밋 2)

- [x] dashboard_data: `meta.dashboard_profile_contract`("v4"),
      `kpi.trend`(points 4~24 finite + provenance{source_id/time_field/periods}),
      `comparison.kind`(period_delta|benchmark)+`provenance`,
      `chart.small_multiple_group`, `panel.surface`, `table.cell_gradient`
      (value_column_indices unique int + scale)
- [x] 조건부 규칙: trend 있으면 value=number+format.precision 필수;
      kind=period_delta면 basis/delta/direction/provenance(periods 2) 필수
- [x] chart_spec: `dashboard_design.contract_version`,
      `dashboard_mapping[].surface/small_multiple_group/table_treatment`
- [x] required 목록 변경 없음 — 기존 dashboard_data/chart_spec fixture
      하위 호환 테스트
- [x] qa/validate 정적 validator 기초: trend provenance(sources[].id 대조·
      periods 정렬/중복/길이), Decimal 정합 공식, comparison 부호-방향 일치
- [x] 커밋 2 — pytest green

## 2. 렌더 QA 기반 정리 (커밋 3)

- [x] chart SVG selector와 spark SVG selector 분리 (`.chart-card svg` 기준
      개수 검사 유지 — 기존 run green 유지)
- [x] legacy fixture / v4 fixture 분리 (legacy = contract 필드 없는 기존
      dashboard_data → 현행 탭 화면과 동일 구조 렌더 회귀)
- [x] 커밋 3 — pytest green

## 3. E1 — KPI 스파크+델타 타일 (커밋 4)

- [x] kind=period_delta일 때만 ▲▼% 렌더: good→좋음색, bad→나쁨색,
      warn|neutral→muted 무채색, direction은 기호만. 본값 무채색 유지
- [x] kind 없음(benchmark 간주)·trend 없음 → 현행 타일 (강등)
- [x] trend 스파크: 중립색 polyline 40×140px 내외 + period_label 캡션
- [x] 3 프로필 공통 + fixture DOM 테스트 + computed style 색 검사
- [x] E1 정적 QA(§7.1 해당 행) 이 커밋에 포함
- [x] 커밋 4 — pytest green

## 4. E2+E3 — analyst 밀도·operations 레일 (커밋 5)

- [x] `dashboard_profile_contract=="v4"` 게이트 — 없으면 기존 탭 경로
- [x] analyst: 단일 스크롤 (KPI 블록+primary 차트 그리드+primary 표),
      패널 수 공식 = KPI블록(1)+primary chart+primary table, 목표 6~8,
      detail/appendix 하단 강등, 부족 시 채우기 금지
- [x] operations: 레일 = 기존 ACTIVE 패널 switcher의 레일 UI 재표현
      (패널 제목 파생, 브랜드 비의존), 좁은 화면 상단 탭 강등
- [x] fixture DOM 테스트: 첫 화면 패널 수·레일 클릭 전환·모바일 강등,
      legacy fixture 회귀 유지
- [x] analyst 밀도 WARN(9+) 이 커밋에 포함
- [x] 커밋 5 — pytest green

## 5. E4+E5 — 스몰 멀티플·셀 그라데이션 (커밋 6)

- [x] small_multiple_group: 같은 panel 내 2~9, type∈{line,area,bar},
      그룹 공통 y-domain 1회 계산, 탭 분산 제외, chart id 전역 유일
- [x] cell_gradient: 인덱스 참조(number 열), null=배경 없음, min==max=중립색,
      rows[:row_limit] 기준, 무채색 보간만
- [x] 해당 정적 QA + DOM 테스트(그리드·셀 background) 이 커밋에 포함
- [x] agents/analyze.md·agents/visualize.md 지침 (§8)
- [x] chart_spec 계획 ↔ dashboard_data 이행 일치 QA
- [x] 언어 게이트 수집기에 period_label·comparison.basis 추가
- [x] 커밋 6 — pytest green

## 6. 문서 개정 (커밋 7)

- [x] `docs/dashboard-design-system.md`: E1~E5 문법, 델타 색 룰 예외
      (warn/neutral muted 포함), "탭당 2색" 적용 범위 명시, §4 계약 예시
- [x] `docs/pipeline-contract.md` 갱신 (**필수** — chart_spec 계획 필드,
      dashboard_data 신규 필드, v4 opt-in 계약)
- [x] CHANGELOG v4 섹션
- [x] 커밋 7 — pytest green

## 7. 최종 검증 (커밋 8)

- [x] 전체 pytest green (176 passed, 12 skipped, 126 subtests passed) +
      `git diff --check` + schema JSON 13개 파싱 (2026-07-14)
- [x] smoke ① 시계열 데이터 (operations/analyst — E1~E5 체감, 사용자 참여,
      `apt-sale-v4-smoke-20260713`, qa-post BLOCK 0)
- [x] smoke ② 스냅샷 데이터 (강등 경로 — KPI comparison/trend 전부 null,
      가짜 추세 없음, count·share·%p 비교 의미 분리, 사용자 승인 5건,
      `sbiz-gangnam-v4-snapshot-smoke-20260714`, qa-post BLOCK 0)
- [x] CHANGELOG 마감 (smoke ① 발견 수정 5건 + smoke ② 사용자 언어 게이트
      수정·렌더 눈검토 기록)
- [x] runs/* 커밋 금지 확인 (`git ls-files 'runs/*'` 0건 + staged 0건)

## 8. 구현 기본값 (재판단 금지)

- [x] v4 레이아웃은 `meta.dashboard_profile_contract=="v4"`일 때만 —
      legacy run 재렌더 화면 동일
- [x] trend/provenance 없으면 스파크 없음 — 렌더러가 값을 계산·보간하지
      않는다
- [x] comparison.kind 없으면 benchmark 간주 — 델타 색·기호 미적용
- [x] KPI 본값은 어떤 경우에도 무채색 (#0a0a0a)
- [x] 델타 색은 status(good/bad만), warn|neutral은 muted, direction은 기호만
- [x] 색 토큰 단일 원천은 templates/dashboard.html 기존 토큰
- [x] 그라데이션은 무채색 보간만 — 상태 색 재사용 금지
- [x] 레일 내비는 패널 제목 파생 — 브랜드·아이콘 리소스 의존 금지
- [x] 6~8패널 부족 시 채우기용 차트 생성 금지
- [x] 신규 필드는 전부 optional — required 목록 불변 (스키마 하위 호환)
- [x] 순수 SVG — 외부 차트 라이브러리 도입은 v5에서만 논의
