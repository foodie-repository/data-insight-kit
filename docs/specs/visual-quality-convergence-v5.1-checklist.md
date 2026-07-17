# Visual Quality Convergence v5.1 Implementation Checklist

> 단일 원천은 `docs/specs/visual-quality-convergence-v5.1.md`다. 이 문서는 설계
> 승인 뒤 실행 순서와 검증 증거를 기록한다.

상태: **설계 승인됨 — Task 2 구현 가능**
브랜치: `codex/dashboard-freeform-v5`

## Global constraints

- [x] 사용자에게 v5.1 spec 원문을 먼저 전달하고 다음 턴에서 설계 승인을 받음
- [x] 설계 승인 전 schema/planner/renderer/QA/adapter 구현을 수정하지 않음
- [x] spec 우선: 구현 판단이 달라지면 spec부터 수정하고 다시 확인받음
- [x] 실제 사용자 답변만 checkpoint에 기록하고 대리 승인하지 않음
- [x] checkpoint 근거 원문을 보여준 턴에서 끝내고 다음 턴에 선택을 받음
- [x] 대시보드 정지점 전에 모든 `outputs/qa_render_*.png`를 직접 열어 관찰 보고
- [x] 각 커밋 직전 정확히 `cd data-insight-kit && python3 -m pytest tests/ -q`
- [x] `runs/*` 커밋 금지
- [x] push 금지
- [x] 공식 Data Analytics/Visualize 코드·프롬프트·자산·runtime 복사 금지
- [x] 별도 사용자 설치 `/Users/foodie/.codex/skills/visualize` 참조 금지

## Task 0 — v5 baseline 마감

- [x] snapshot smoke `sbiz-gangnam-v5-freeform-smoke-20260714` 마감 확인
- [x] time-series smoke `apt-sale-v5-freeform-smoke-20260714` 실제 보고서 구성 승인 기록
- [x] communicate 및 qa-post 완료
- [x] desktop/mobile screenshot 직접 검토
- [x] 전체 pytest green 확인
- [x] v5 checklist/CHANGELOG 마감 커밋 (`2f8df35`)

## Task 1 — v5.1 설계 승인

### 문서

- [x] 제품 방향: 새 kit/독립 PoC 없이 data-insight-kit 본체 확장
- [x] 계획 품질과 표현·QA 품질을 별도 계약으로 정의
- [x] clean-room/비의존/비재배포 경계 정의
- [x] 기존 v5 renderer를 유지하는 opt-in v5.1 계약 정의
- [x] chart_spec decision brief/metric model/visual contract 필드 정의
- [x] chart 충분성·fallback 임곗값 정의
- [x] 문구·색·척도·라벨·범례 원칙 정의
- [x] layout 목적·결정·근거·empty behavior 정의
- [x] 1440/736/390/320 browser QA와 눈검토 기록 정의
- [x] Claude/Codex thin adapter 구조 정의
- [x] 두 smoke 이전/이후 비교 기준 정의
- [x] 사용자에게 raw design evidence 전달
- [x] 다음 사용자 턴의 실제 설계 승인 기록 — 원문 `설계 승인` (2026-07-17)

### 정지점

- [x] 승인 전 구현 diff가 없음을 `git status --short`로 확인 — 신규 spec/checklist만 존재
- [x] 승인 시 spec/checklist 상태를 `승인됨`으로 변경
- [x] 커밋 직전 전체 pytest green — 270 passed, 23 skipped, 128 subtests passed
- [x] spec/checklist만 좁게 커밋

## Task 2 — additive schema와 fixture

### Red

- [x] `chart_spec.quality_contract`가 없으면 기존 fixture가 계속 통과하는 테스트
- [x] v5.1 선언 시 decision brief/metric role 필수 테스트
- [x] chart `visual_contract` 필수·enum·variant 일치 테스트
- [x] `dashboard_layout.quality_contract_version` opt-in 테스트
- [x] component purpose/decision/evidence/empty behavior 필수 테스트
- [x] v5.1 한쪽 선언만 있는 cross-contract BLOCK 테스트

### Green

- [x] `schemas/chart_spec.schema.json` additive 확장
- [x] `schemas/dashboard_layout.schema.json` additive 확장
- [x] `tests/v5_fixtures.py`에 최소 v5.1 fixture 추가
- [x] 기존 legacy/v4/v5 schema 회귀 통과

### Verify/commit

- [x] schema 대상 테스트 — 36 passed
- [x] `python3 -m pytest tests/ -q` — 276 passed, 23 skipped, 128 subtests passed
- [x] `runs/*` 제외 확인 후 commit

## Task 3 — planner와 계획 품질 gate

### Red

- [x] decision/audience/cadence/source/freshness 누락·불일치 BLOCK
- [x] metric unit/denominator/window/source 누락·불일치 BLOCK
- [x] chart question 중복 BLOCK
- [x] metric/chart/component lineage 누락 BLOCK
- [x] 각 chart 충분성 임곗값과 fallback 테스트
- [x] family/variant/chart.type 불일치 BLOCK
- [x] 8개 초과 identity series 기본 legend BLOCK

### Green

- [x] analyze 산출물에 decision brief 생성 지침
- [x] metric을 hero/diagnostic/guardrail/detail로 분류하는 계약·지침
- [x] 차트별 visual contract 생성 지침
- [x] 실제 관측 수·series·distinct·cell density와 차트별 최소 조건 계산 지침
- [x] 조건 미달 chart의 안전한 fallback 계획·검증
- [x] storyboard 질문 원문에 판단 목적·표현 계획·component 연결 요약 포함

### Verify/commit

- [x] planner/checkpoint 집중 테스트 — 70 passed, 54 subtests passed
- [x] `python3 -m pytest tests/ -q` — 288 passed, 23 skipped, 128 subtests passed
- [x] `runs/*` 제외 확인 후 commit

## Task 4 — 문구·색·척도·최소 구성 gate

### Red

- [x] 실제 기간 자리표현과 unresolved unit 회귀 테스트
- [x] copy_context와 visible title/subtitle 문맥 불일치 BLOCK
- [x] 단위가 다른 overlay와 bar 비0 기준 BLOCK
- [x] 의미 없는 diverging scale BLOCK
- [x] 다중 series color-only 및 root 5개 초과 BLOCK
- [x] 빈 KPI/insight/chart와 무동작 control BLOCK
- [x] 같은 질문·근거 component 중복 BLOCK

### Green

- [x] validator가 범위·지표·기간·단위 문맥을 검사
- [x] 결론형/설명형 title mode를 과대해석 없이 적용
- [x] palette mode와 stable mapping 적용
- [x] non-color channel 적용
- [x] direct label/legend 전략 적용
- [x] empty behavior와 filler 제거 적용

### Verify/commit

- [x] language/contract/compiler 집중 테스트 — 105 passed
- [x] `python3 -m pytest tests/ -q` — 304 passed, 23 skipped, 128 subtests passed
- [x] `runs/*` 제외 확인 후 commit

## Task 5 — renderer와 반응형 표현

### Red

- [x] independent panels/indexed baseline/focused cue 렌더 테스트
- [x] direct label과 single-series legend 제거 테스트
- [x] paginated legend/top-N/table fallback 테스트
- [x] longest label 공간 예약 테스트
- [x] compact/narrow reflow 테스트

### Green

- [x] v5 compiler가 visual contract를 allowlist option으로 변환
- [x] 5개 초과 category를 색 추가 없이 강등
- [x] 8개 초과 identity series 모바일 전략 적용
- [x] 736/320px CSS layout과 chart resize 안정화
- [x] template/bundle checksum 재현성 유지

### Verify/commit

- [x] compiler/render 집중 테스트 — 118 passed
- [x] 실제 Chromium 집중 테스트 — 21 passed
- [x] `python3 -m pytest tests/ -q` — 317 passed, 28 skipped, 128 subtests passed
- [x] `runs/*` 제외 확인 후 commit

## Task 6 — browser QA와 눈검토 기록

### Red

- [x] compact/narrow screenshot 누락 실패 테스트
- [x] label/legend/plot/canvas 겹침·잘림 테스트
- [x] 11px 미만 essential text 테스트
- [x] tooltip viewport 이탈 테스트
- [x] 색만 구분하는 series 테스트
- [x] visual review record 누락·hash 불일치 테스트

### Green

- [x] 1440/736/390/320 browser QA 실행
- [x] 네 `qa_render_*.png` 생성
- [x] `outputs/visual_review.json` 초안/검증 구현
- [x] 기존 console/network/accessibility gate 유지
- [x] 눈검토 `revise`이면 checkpoint 전달 차단

### Verify/commit

- [x] 계약/renderer/browser QA 집중 테스트 — 125 passed
- [x] 실제 Chromium 네 viewport 확인 — 23 passed
- [x] 네 screenshot 직접 눈검토 — 최초 검토에서 단위 중복과 desktop support
  공백을 `revise`로 판정하고 수정·재생성함. 최종 검토에서 desktop 8:4 정렬과
  support 채움, compact/mobile 단일 열 흐름, narrow 표 fallback, label·legend·본문
  잘림 없음, 단위 중복 없음 확인
- [x] `python3 -m pytest tests/ -q` — 324 passed, 30 skipped,
  128 subtests passed
- [x] `runs/*` 제외 확인 후 commit (`b511b4f`)

## Task 7 — 문서와 운영 계약

- [x] `docs/dashboard-design-system.md`에 v5.1 원칙 연결
- [x] `docs/pipeline-contract.md`에 quality contract와 눈검토 artifact 연결
- [x] `README.md` 산출물·QA·marketplace 설명 갱신
- [x] `AGENTS.md` 모든 screenshot 직접 검토 의무 갱신
- [x] `skills/run-pipeline/SKILL.md` 네 viewport/visual review 갱신
- [x] `CHANGELOG.md` 재개 지점 갱신
- [x] 문서 경로/용어 일관성 검사 — 5 passed
- [x] `python3 -m pytest tests/ -q` — 329 passed, 30 skipped,
  128 subtests passed
- [x] `runs/*` 제외 확인 후 commit (`0872e05`)

## Task 8 — Claude Code thin adapter

- [x] `.claude-plugin/plugin.json` manifest 검증 — v0.2.0
- [x] `.claude-plugin/marketplace.json` package 경로 검증 — `source: "./"`,
  `strict: true`, version 권한은 manifest 한 곳
- [x] `hooks/hooks.json`이 core checkpoint hook만 호출하는지 검증
- [x] 공유 `skills/run-pipeline/SKILL.md` 연결 검증
- [x] core 규칙 중복과 proprietary/plugin cache 의존 없음 검사
- [x] 설치/발견/dry-run 테스트 — Claude Code 2.1.212 strict validate 통과,
  격리된 `/tmp` 설정에서 marketplace 추가·설치 성공, skill 1·agent 8·hook 1
  발견, core dry-run 성공
- [x] adapter 집중 테스트 — 6 passed; 문서 계약 포함 11 passed
- [x] `python3 -m pytest tests/ -q` — 335 passed, 30 skipped,
  128 subtests passed
- [x] `runs/*` 제외 확인 후 commit (`4fc9f95`)

## Task 9 — Codex thin adapter

- [x] `.codex-plugin/plugin.json` 독립 manifest 작성 — v0.2.0
- [x] Codex marketplace metadata 작성 — interface display/description/capability
- [x] 공유 skill과 `.codex/hooks.json` 연결 — `PLUGIN_ROOT` 우선, project root fallback
- [x] standalone HTML/checkpoint 흐름 유지
- [x] `window.openai`, inline widget, proprietary asset 의존 없음 검사
- [x] 설치/발견/dry-run 테스트 — Codex CLI 0.144.1, 격리된 `CODEX_HOME`에서
  marketplace 발견·설치·enable 성공; 설치 cache에 manifest/hook/skill/wrapper/
  template 확인; 설치된 root에서 core dry-run 성공
- [x] adapter 집중 테스트 — Claude/Codex/docs 합계 17 passed
- [x] `python3 -m pytest tests/ -q` — 341 passed, 30 skipped,
  128 subtests passed
- [x] `runs/*` 제외 확인 후 commit (`7a544f5`)

## Task 10 — snapshot smoke 이전/이후 비교

- [x] baseline run/artifact read-only 확인
- [x] 원천만 재사용한 새 v5.1 run-id 생성 — source SHA-256 일치
- [x] 기존 checkpoint 답변 미복사 확인 — 새 run에 승인 레코드 없음
- [x] data_profile preview가 connect 단계의 제한 샘플을 우선 사용하고 식별 가능 컬럼을 다시 노출하지 않는지 확인
- [x] data_profile raw evidence 전달 후 실제 사용자 답변 `현재 데이터로 진행` 기록
- [x] analysis_strategy raw evidence 전달 후 실제 사용자 답변 기록 — 원문
  `핵심 질문, 핵심 지표, 분모, 비교 기준이 분석 목적과 맞으면 전략을 승인한다.
  원하는 판단이 다르거나 지표가 낯설면 질문·지표 수정을 선택한다.`
- [x] analysis_result_review 결정적 술어 미발동 확인 — diagnostic route,
  non-domain, standard report, status diagnosis
- [x] dashboard_storyboard raw evidence 전달 후 실제 사용자 답변 기록 — 원문
  `탐색형 화면으로 승인`
- [x] 네 screenshot 자동 QA BLOCK 0 — WARN 5
- [x] 네 screenshot 직접 검토와 관찰 보고 — 1차 `revise`: 히트맵 배수 문구
  모호성 발견, 문구 수정·네 화면 재생성 후 2차 `pass`; component·chart·축·label·
  legend·plot·표·출처의 겹침과 잘림 없음, 320px 계획된 table fallback 확인
- [x] report_outline 실제 사용자 답변 기록 — 원문 `보고서 구성 승인`
- [x] qa-post BLOCK 0 — WARN 3
- [x] v5 baseline/v5.1 rubric 비교 기록 — spec 10개 항목, hard BLOCK은 양쪽 0;
  v5.1 사용자 전달 뒤 수정 0회·내부 눈검토 수정 1회, WARN 수는 검사 범위가 달라
  우열 지표에서 제외

## Task 11 — time-series smoke 이전/이후 비교

- [x] baseline run/artifact read-only 확인
- [x] 원천만 재사용한 새 v5.1 run-id 생성 — source SHA-256 일치
- [x] 기존 checkpoint 답변 미복사 확인 — 새 run에 승인 레코드 없음
- [x] data_profile raw evidence 전달 후 실제 사용자 답변 기록 — 원문
  `현재 데이터로 진행`
- [x] analysis_strategy raw evidence 전달 후 실제 사용자 답변 기록 — 원문
  `전략 승인`
- [x] analysis_result_review 결정적 술어 미발동 확인 — `required=False`,
  diagnostic route, non-domain, standard report
- [x] dashboard_storyboard revision 1 raw evidence 전달 후 실제 사용자 답변 기록 —
  원문 `탐색형 화면으로 승인`
- [x] 단위·척도·분리 패널·다중 series 전략 확인 — 실제 연월·만원, 가격/거래량
  독립 패널, 같은 단위의 전년동월 변화율은 공유 0 기준축과 색·범례로 구분
- [x] 첫 visualize QA 결함을 제품 회귀로 전환 — stateful chart의 control/reset
  사전 검사, 승인 뒤 layout revision round 2 재승인, `zero_baseline` 음수 값 보존
- [x] 첫 네 screenshot 직접 검토 — 승인 hash와 다른 초안이라 최종 검토로는
  불인정; desktop control 공백, 음수 막대 소실, mobile/narrow 표 스크롤 필요 관찰
- [x] dashboard_storyboard revision 2 raw evidence 전달과 실제 사용자 재승인 —
  원문 `탐색형 화면으로 승인`
- [x] 네 screenshot 자동 QA BLOCK 0 — WARN 6
- [x] 네 screenshot 직접 검토와 관찰 보고 — desktop/compact/mobile/narrow에서
  문구·위계·색·척도·축·라벨·범례·공백, 상세표의 계획된 가로 탐색 확인
- [x] report_outline 조건부 수정 요청 기록 — 사용자가 `10,970`처럼 천 단위
  구분기호를 공통 규칙으로 요청했으며 `continue_pipeline=false`로 communicate 차단
- [x] 숫자 표기 제품 규칙과 현재 smoke 반영 — KPI·값축·직접 라벨·tooltip·
  histogram 구간·표·자유 문구 검사, 네 화면 재검토 `pass`, QA BLOCK 0/WARN 6
- [x] report_outline 실제 사용자 답변 기록 — 조건부 수정 반영 뒤 원문
  `보고서 구성 승인`
- [x] communicate 완료 — `standard`·`mixed`·`data_only` 계약의
  `summary_report.md`, dashboard/chart spec에 없는 추가 수치 제거
- [x] qa-post BLOCK 0 — 실제 Chromium 포함 WARN 6, render 제외 보고서 계약 WARN 2
- [x] v5 baseline/v5.1 rubric 비교 기록 —
  `docs/v5-v51-smoke-comparison.md`, 같은 원천 SHA-256과 spec 10개 항목

## Task 12 — release close

- [x] 두 smoke hard BLOCK 0
- [x] 반복 피드백 항목과 수정 횟수의 이전/이후 표 완성
- [x] clean-room 비의존 검사 green — adapter/docs 집중 테스트 19 passed,
  `window.openai`·proprietary asset·plugin cache·개인 skill 비의존
- [x] Claude/Codex adapter 설치 검증 green — 기존 격리 설치·발견·core dry-run
  증거와 현재 adapter/docs 집중 테스트 19 passed
- [x] `python3 -m pytest tests/ -q` — 354 passed, 30 skipped,
  128 subtests passed
- [x] `git diff --check`
- [x] `runs/*` staged 없음 확인
- [x] CHANGELOG 진행 상태를 release close로 갱신
- [x] 최종 commit
- [x] push하지 않음
