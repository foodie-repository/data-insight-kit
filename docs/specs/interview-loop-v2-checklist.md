# Interview Loop v2 Checklist

Status: complete — 커밋 1~12 구현·검증 완료, smoke 3종 완주 (2026-07-13)

이 체크리스트는 `docs/specs/interview-loop-v2.md` 구현을 추적하기 위한 문서다.
구현 중 결정이 바뀌면 먼저 spec과 이 checklist를 수정한 뒤 코드에 반영한다.
섹션 번호는 spec의 커밋 플랜(§12)과 1:1로 맞춘다.

상태 표기: `[ ]` 미시작 / `[x]` 완료 / `[~]` 진행 중 / `[!]` 차단·재검토.

## 0. 기준문서 (커밋 1)

- [X] D1~D3 설계 결정 사용자 인터뷰 확정 (2026-07-10, kickoff "확정 결과")
- [X] `docs/specs/interview-loop-v2.md` 초안 작성
- [X] `docs/specs/interview-loop-v2-checklist.md` 초안 작성
- [X] 사용자 검토·승인 반영 (2026-07-11, Codex 교차검증 9건 반영 후 승인)
- [X] spec이 v1 spec §8.3/§12.2/§15와 충돌하지 않는지 최종 확인
  (§15 파일명 규칙은 `.round2` 접미사로 유지 — Codex M3 정정에서 재확인)
- [X] `CHANGELOG.md` 진행 상태를 v2로 갱신
- [X] 커밋 1 (docs) — pytest green (111 passed, 56 subtests)

## 1. v1.1 — hook uv add 전면 deny (커밋 2)

- [X] `dik_checkpoint_hook.py`: kit run 컨텍스트에서 `uv add` 무조건 deny
  (유효 승인이 있어도 deny — `uv sync --extra <allowlist>`만 허용)
- [X] deny 메시지가 `uv sync --extra` 대체 경로를 안내
- [X] 회귀 테스트: 승인 있음+`uv add` → deny(체인 포함), 승인 있음+
  `uv sync --extra stats` → allow (tests/test_expert_routing.py)
- [X] CHANGELOG 발견 3 항목을 "수정 완료"로 갱신
- [X] 커밋 2 — pytest green (113 passed, 58 subtests)

## 2. Schema (커밋 3)

- [X] `checkpoint_question.schema.json`: `schema_version` enum에 v2 추가 (v1 유지)
- [X] optional `interview_loop` 블록 (round/max_rounds/
  free_question_used_this_round/max_free_questions_per_round/
  prior_round(question_sha256·trigger 포함)/finalization_rule)
- [X] 조건부 규칙(if/then): v2면 interview_loop 필수, round=2면 prior_round
  필수, maps_to.loop_action 옵션은 continue_pipeline=false (I1 스키마 층)
- [X] optional `companion_questions[]` (최대 2, maps_to.domain_field 지원 —
  옵션 스키마에 continue_pipeline 자체가 없음)
- [X] optional `exploration` 블록 (candidates_ref, free_question_slot)
- [X] `schemas/exploration_candidates.schema.json` 신설 (candidates 2~3,
  mini_result 필수 필드: summary/table_path/computation/source_columns/row_count_used)
- [X] `docs/pipeline-contract.md`에 인터뷰 라운드·자유 질문·companion 계약 반영
- [X] 기존 v1 질문 fixture가 스키마를 계속 통과하는지 확인 (하위 호환 —
  test_legacy_v1_question_still_validates + 기존 gate 생성 질문 검증 회귀)
- [X] 커밋 3 — pytest green (120 passed, 75 subtests)

## 3. 런타임 코어 1 — 답변·질문 생성 (커밋 4)

- [X] `apply_checkpoint_answer.py`: 답변 레코드에 `interview_round` 기록
- [X] `--companion <id>` 답변 누적 (continue_pipeline 항상 false, maps_to 복사)
- [X] `--free-question` 답변 누적 (loop_action=free_question, continue_pipeline=false,
  라운드당 1개 기록 시점 거부)
- [X] 탐색 방향 옵션 maps_to.loop_action=explore_direction 경로 동작
  (helper I1 강제 + gate 트리거 — 방향 옵션 렌더는 커밋 6)
- [X] `checkpoint_gate.py`: 라운드 2 질문 파일 `<prefix>_<checkpoint>_question.round2.json|md` 생성

- [~] 라운드 2 생성 트리거: (a) 최신 결정 레코드(companion 제외) loop_action 완료,
  (b) domain readiness 필수 필드 잔존은 커밋 9 — prior_round.trigger 기록 완료

- [X] 결정 레코드 선택자 — companion만 제외 (spec §4.3 정정 반영: 자유 질문은
  I1로 승인 불가라 라운드 전이만 유발)
- [X] `--free-question`·`--companion`과 `--continue-pipeline` 상호 배타 (helper 거부)
- [X] `--question-file` 허용 집합 검사 (§4.6 resolver와 동일 규칙)
- [X] canonical/mirror 병합 동작 코드 확인 → H2 확정(mirror가 answers[-1]로
  우선) → canonical 단일화 + 불일치 fail-closed 반영
- [X] 라운드 3 생성 거부
- [X] 라운드 2 질문에 prior_round(question_path/question_sha256/answer_id/
  trigger/mini_result_paths) 내장

- [~] companion 질문 수 ≤2 강제 — 스키마 층(maxItems) 완료, gate 생성부는
  companion을 렌더하는 커밋 9에서

- [X] `--print-existing`이 라운드 2 파일도 chat-first로 출력 (라운드 2 우선)
- [X] 커밋 4 — pytest green (125 passed, 78 subtests)

## 4. 런타임 코어 2 — 가드 (커밋 5)

- [X] `stage_guard.py`: §4.6 공통 resolver (허용 집합·유효 R2 체인·prior
  answer_id 존재·created_at 순서)
- [X] 불변식 I1 위반 레코드 승인 후보 제외 + 차단 (validate_answer)
- [X] canonical/mirror 불일치 fail-closed (answer_store_issues +
  latest_answers canonical 단일화·companion 제외)
- [X] `round3+` 파일 존재 시 차단 (resolver가 stray 라운드 파일 보고)
- [X] qa/validate round-aware lineage 최소 확장: R2 승인 인정(_resolve_answer_
  question_path, §9 독립 재계산) + analysis_strategy approval_targets를
  resolved 질문 기준으로 읽음 (커밋 7 smoke의 전제 — H4)
- [X] 승인 판정은 기존 그대로 (최신 답변 continue_pipeline + v3 provenance,
  라운드 무관) 회귀 확인 — 전체 pytest green
- [X] `dik_checkpoint_hook.py`: stage_guard 라운드 검증 공유 (단일 스크립트 원칙 —
  validate_answer/latest_answers 재사용으로 자동 상속)
- [X] 라운드 질문 파일도 배포용 언어 게이트 대상 (USER_FACING_SUFFIXES에
  `.round2` 추가 — endswith 매칭 누락 보정. 미니 결과 파일 게이트는 자유
  질문 artifact를 만드는 커밋 8에서)
- [X] `validate_user_facing_text.py` FORBIDDEN_TERMS 추가: interview_loop,
  exploration_candidates, companion_question, free_question, mini_result,
  loop_action, frame_focus (user 필드만 스캔 — v2 JSON 구조 자기 차단 없음
  확인, 생성 질문 언어 게이트 통과 테스트 고정)
- [X] 커밋 5 — pytest green (134 passed, 87 subtests)

## 5. data_profile 부착 (커밋 6)

- [X] gate: exploration_candidates.json schema 검증 후 방향 옵션 렌더
  (없거나 불일치 → v1형 질문으로 강등 + 사유 기록)
- [X] 라운드 1 옵션: 바로 진행(승인) + 방향 후보 ≤3 (description에 미니 결과
  1줄, I1로 continue_pipeline=false 강제 생성)
- [X] 라운드 2: 선택 방향 미니 결과 표 내장(≤14줄 snippet) + 확정/재선택 옵션
- [X] 방향 확정 답변 maps_to.frame_focus 기록 (confirm_direction 옵션)
- [X] `agents/explore.md`: exploration_candidates 산출 계약 추가
  (실데이터 계산 필수, 계산 불가 후보는 제시 금지)
- [X] `agents/frame.md`: frame_focus를 03_frame.md 분석 질문·비교축에 반영 +
  근거 명시 + 미니 결과 직접 복사 금지
- [X] 질문 md `artifacts[]`에 미니 결과 table_path 포함 (표시 의무 — R1은
  후보 전체, R2는 선택 방향)
- [X] 커밋 6 — pytest green (132 passed, 85 subtests — 하네스 리팩터로 중복
  실행 5개 제거 + 신규 3개)

## 6. 중간 smoke 게이트 (커밋 7)

- [X] 전제: 커밋 5의 round-aware lineage로 R2 승인 run이 qa BLOCK 0 가능한지 확인 (H4)
- [X] 단순 CSV run 실제 완주: 방향 선택 → 라운드 2(실계산 미니 결과 내장) →
  frame_focus 확정 → 전 stage_guard 통과 (실데이터, runs/ 실경로, 28체크
  ALL PASS — LLM 스테이지 포함 완주는 커밋 12 smoke 범위)
- [X] 조기 종료 경로 회귀: 후보 없음 → 기본 질문 강등 → 바로 승인 → v1 동일
  흐름 (라운드 2 파일 0개)
- [X] qa lineage BLOCK 0 (승인 판정+provenance 함수, R2 resolve 포함 — 전체
  qa/validate.py 렌더 QA는 커밋 12에서)
- [X] 발견 결함 수정 + CHANGELOG 기록 — 결함 0건, 커밋 8~9 착수 가능
- [X] 커밋 7 — pytest green (132 passed, 85 subtests)

## 7. 나머지 정지점 부착 (커밋 8)

- [X] analysis_strategy: 자유 질문 슬롯 + 라운드 2 (기존 옵션·dependency 병합
  유지 — 런타임은 커밋 4~5 generic, 안내 노출 + 테스트 고정)
- [X] analysis_strategy 라운드 2 생성 시 approval_targets 최신 재계산 (테스트:
  자유 질문 뒤 method_route 변경 → R2 새 sha 잠금)
- [X] analysis_result_review: 자유 질문 슬롯 + 라운드 2 (§9 술어·발동 조건 불변)
- [X] dashboard_storyboard: 자유 질문 슬롯 + 라운드 2 (차트 추천표 계약 유지)
- [X] dashboard_storyboard: 단순 run에서 current_understanding에 1차 결과 요약
  포함 (v1 checklist §8 미결 항목 흡수 — 심화 run에서는 미표기)
- [X] report_outline: 자유 질문 슬롯 + 라운드 2 (chat handoff 직접 질문 안내 포함)
- [X] 자유 질문 미니 결과 artifact 계약 (§7): record_free_question_result.py —
  md 필수 요소 + provenance JSON + answer_id 연결(선행 필수·중복 거부·
  ≤20행). 미니 결과 파일은 언어 게이트 제외(사용자 원문 인용 — spec §9 정정)
- [X] 커밋 8 — pytest green (137 passed, 96 subtests)

## 8. 도메인 인터뷰 런타임화 (커밋 9)

- [X] companion 질문 domain_field 매핑 (§8.1 표: 정지점별 수집 필드 —
  CHECKPOINT_DOMAIN_FIELDS + 사용자 표현 질문 사전)
- [X] `scripts/build_domain_intake.py`: checkpoint_answers.json → input/domain_intake.json
  결정적 파생 (generated_by + 근거 answer_id — 스키마 optional 필드 추가)
- [X] domain_readiness.status 재계산 규칙 v1 그대로 재사용
  (stage_guard.compute_domain_readiness, deterministic-v1)
- [X] 주입 파일 우선 규칙: 기존 domain_intake.json 있으면 인터뷰 답변은
  open_questions 보강으로만 병합 (테스트 고정)
- [X] readiness 부족 필드 우선 R2 재질문 — 트리거 (b),
  prior_round.trigger=domain_readiness_gap, 재확인형 주 질문 (결정적 선택)
- [X] domain pack 자동 수정 금지 회귀 확인 (전체 pytest green — 기존 hook
  deny 테스트 유지, 이번 커밋은 domains/ 미접촉)
- [X] 커밋 9 — pytest green (140 passed, 102 subtests)

## 9. QA 확장 (커밋 10)

- [X] 유효 R2 체인 기준 사이클당 R2 ≤1, round3+ BLOCK, 고아 R2 WARN
  (라운드 파일 스윕 + 근거 답변 없는 R2 위조 BLOCK)
- [X] 자유 질문 answer_id 연결·타임스탬프 순서 불일치 BLOCK
- [X] 자유 질문 라운드당 >1 BLOCK
- [X] 불변식 I1 위반 전체 BLOCK (companion·자유 질문·탐색 방향 true)
- [X] canonical/mirror checkpoint_answers 불일치 BLOCK
- [X] 파생 domain_intake의 generated_by/근거 answer_id 무결성 검증
- [X] 보고서·대시보드의 미니 결과 직접 인용 WARN (대표 run 보정 후 승격 검토)
- [X] 기존 checkpoint lineage/render/report QA 회귀 확인 (전체 pytest green,
  interview_loop_checks는 auto 정책 skip 존중)
- [X] 커밋 10 — pytest green (145 passed, 105 subtests)

## 10. 문서 (커밋 11)

- [X] `CUSTOMIZATION.md` domain expert interview 중심 보강 (인터뷰 우선 경로 신설)
- [X] `domains/README.md` run-local intake 파생 + 승격 흐름
  (+훅 오탐 수정: domains 루트 문서를 pack 쓰기로 오인하던 것 — 회귀 테스트)
- [X] `domains/template/interview-questions.md` §8.1 매핑 기반 질문 구조
  (kit 기본 질문과 역할 구분 + 결과 검토·보고서 전 절)
- [X] `domains/template/kpi-rules.md` 분모·단위·비교 기준·evidence class(§8.6 표)
- [X] `domains/template/qa-rules.md` 과잉해석 BLOCK 예시 4종
- [X] `domain_pack_update_candidates.md` 역할 문서화 (domains/README 승격 흐름)
- [X] `README.md`/`GUIDE.md` 탐색 문답 사용자 안내 (사용자 표현만)
- [X] `AGENTS.md` 라운드·표시 의무·자유 질문 운영 규칙 반영
- [X] `skills/run-pipeline/SKILL.md` 인터뷰 루프 흐름 반영
- [X] 커밋 11 — pytest green (147 passed, 107 subtests)

## 11. 최종 검증 (커밋 12)

- [X] `git diff --check` + Python compile + schema JSON 파싱 (13개, 2026-07-13)
- [X] 전체 pytest green (148 passed, 110 subtests)
- [X] wrapper `--dry-run` 스모크 (`v2-final-dryrun-20260713` 완주)
- [X] 단순 CSV smoke (탐색 문답 경로, spec §13 기준 —
  `police-crime-v2-smoke-20260711`, BLOCK 0)
- [X] statistical smoke (자유 질문 provenance 경로 —
  `sbiz-stat-v2-smoke-20260712`, route 단독 H2.5, BLOCK 0)
- [X] domain smoke (파생 domain_intake + readiness 재질문 경로 —
  `sbiz-gangnam-domain-v2-smoke-20260712`, BLOCK 0 + deep 게이트 통과)
- [X] 회귀: 조기 종료만 선택한 run이 v1과 동일 흐름 (smoke 3종에서 R2 미발동
  정지점들이 v1 동일 단일 승인 흐름으로 진행 + pytest 조기 종료 회귀)
- [X] CHANGELOG 마감 (발견·수정 기록 포함 — 12a~12d, v4 kickoff 노트)
- [X] runs/* 커밋 금지 확인 (`.gitignore:2 runs/*` + staged 0건)

## 12. 구현 기본값 (재판단 금지)

- [X] 라운드 2 파일명 접미사는 `.round2` 고정 (prefix 재배열 금지, v1 §15 유지)
- [X] 문항 예산: 주 질문 1 + companion ≤2 = 라운드당 ≤3, 자유 질문은 별도 ≤1
- [X] companion 답변은 어떤 경우에도 진행을 결정하지 않는다
- [X] 미니 결과는 에이전트 산출물 — gate는 계산하지 않는다
- [X] domain_intake 파생은 주입 파일이 있으면 병합 보강만 한다
- [X] 미니 쿼리 대상은 이번 run input 스냅샷 한정 (외부 접근 금지)
- [X] 진행 판정 입력은 canonical checkpoint_answers.json 단일 (mirror는 정합 검사만)
- [X] 유효 R2 = prior_round.question_sha256이 현재 R1을 가리키는 것, 사이클당 ≤1
- [X] 불변식 I1: loop_action·companion 레코드는 continue_pipeline=true 불가
