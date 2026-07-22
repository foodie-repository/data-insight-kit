# Expert-Guided Analysis Routing Checklist

Status: draft for implementation tracking

이 체크리스트는 `docs/specs/expert-guided-analysis-routing.md` 구현을 추적하기 위한
문서다. 구현 중 결정이 바뀌면 먼저 spec과 이 checklist를 수정한 뒤 코드에 반영한다.

상태 표기는 다음을 사용한다.

- `[ ]`: 아직 시작하지 않음
- `[x]`: 완료
- `[~]`: 진행 중 또는 부분 완료
- `[!]`: 차단 또는 재검토 필요

## 0. 기준문서

- [X] `docs/specs/expert-guided-analysis-routing.md` 초안 작성
- [X] `docs/specs/expert-guided-analysis-routing-checklist.md` 초안 작성
- [X] 통합 spec에 v1-v5 `Phased Roadmap` skeleton 추가
- [X] v2 이후 상세 spec/checklist는 v1 구현과 run 검증 이후 별도 작성하기로 명시
- [X] spec이 `docs/pipeline-contract.md`의 단일 원천 역할과 충돌하지 않는지 검토
- [X] spec의 design decisions가 이번 대화에서 확정한 결정을 빠짐없이 담는지 검토
- [X] 구현 시작 전 spec/checklist 변경 필요 여부 최종 확인
  (2026-07-10 구현 전 리뷰 반영: renumbering 철회, 결정적 발동 술어, kit 자체
  pyproject, extras stats/ml 2개, sha256 승인 잠금, 설치 승인 명시 옵션만,
  registry JSON 전환, hook install 명령 게이트)

## 1. 계약 문서 반영

- [X] `docs/pipeline-contract.md`에 analysis depth routing 계약 추가
- [X] `docs/pipeline-contract.md`에 `method_route.json` 산출물 계약 추가
- [X] `docs/pipeline-contract.md`에 `dependency_plan.json` 산출물 계약 추가
- [X] `docs/pipeline-contract.md`에 domain expert interview lifecycle 추가
  (원칙 bullet + run 레이아웃, 상세 단계는 spec §8.3이 기준)
- [X] `docs/pipeline-contract.md`에 `domain_intake.json`과 `domain_readiness` 계약 추가
- [X] `docs/pipeline-contract.md`에 조건부 `analysis_result_review` checkpoint 추가
  (H2.5, 고정 prefix 05_, 결정적 술어)
- [X] `docs/pipeline-contract.md`에 dependency approval/install provenance 추가
  (approval.answer_id 연결 + approval_targets sha256 잠금)
- [X] `docs/pipeline-contract.md`에 도메인/통계 과잉해석 BLOCK 기준 추가
  (forbidden_claims 명시 문구 BLOCK, 휴리스틱 WARN 시작)

## 2. 분석 전략 문서

- [ ] `docs/analysis-strategy-library.md`에 route 6종 추가
- [ ] `descriptive` route 조건과 한계 정리
- [ ] `diagnostic` route 조건과 한계 정리
- [ ] `statistical` route 조건, 대표 method, 금지 결론 정리
- [ ] `ml_exploratory` route 조건, 대표 method, 금지 결론 정리
- [ ] `predictive` route 조건, 누수 방지 기준, 강등 조건 정리
- [ ] `causal_experiment` route 조건, 인과 표현 금지 기준 정리
- [ ] route 강등 조건을 문서화

## 3. Domain Expert Intelligence 문서

- [ ] `CUSTOMIZATION.md`를 domain pack 중심에서 domain expert interview 중심으로 보강
- [ ] `domains/README.md`에 run-local domain intake와 domain pack 승격 흐름 추가
- [ ] `domains/template/interview-questions.md`에 단계별 질문 구조 추가
- [ ] `domains/template/kpi-rules.md`에 분모, 단위, 비교 기준, evidence class 강화
- [ ] `domains/template/qa-rules.md`에 도메인 과잉해석 BLOCK 예시 추가
- [ ] `domain_pack_update_candidates.md`의 역할 문서화

## 4. Schema

- [X] `schemas/method_route.schema.json` 추가
- [X] `method_route`에 route, selected_methods, downgrade, dependency_groups 포함
- [X] `schemas/dependency_plan.schema.json` 추가
- [X] `dependency_plan`에 required_extras, installed, missing, approval, install_result 포함
- [X] `schemas/domain_intake.schema.json` 추가
- [X] `domain_intake`에 row_meaning, entity_grain, terminology, column_semantics 포함
- [X] `domain_intake`에 kpi_definitions, exclusion_rules, forbidden_claims 포함
- [X] `domain_intake`에 evidence_boundaries와 open_questions 포함
- [X] `domain_readiness` 구조 추가 또는 schema에 포함
- [X] `schemas/checkpoint_question.schema.json`에 `analysis_result_review` 추가
- [X] `schemas/checkpoint_question.schema.json`에 optional `approval_targets`
  (method_route/dependency_plan sha256) 추가
- [ ] `schemas/chart_spec.schema.json`에 optional route metadata 추가
  (커밋 2~7 확인 결과 미구현 — `chart_spec.schema.json`에 route 관련 필드 없음)
- [ ] 기존 chart_spec fixture와 schema 호환성 확인
  (위 항목이 구현되지 않아 확인할 변경 자체가 없음)

## 5. Method Registry

- [X] `methods/method_registry.json` 추가 (JSON — 결정적 코어의 stdlib+jsonschema 원칙)
- [X] core methods 추가: ranking, distribution, composition, trend, quality
- [X] stats methods 추가: group difference candidate, correlation candidate
- [X] stats methods 추가: simple regression candidate, confidence interval candidate
- [X] ml methods 추가: clustering candidate, anomaly candidate, dimensionality reduction candidate
- [X] 각 method에 data_conditions 추가
- [X] 각 method에 domain_conditions 추가
- [X] 각 method에 dependency_groups 추가
- [X] 각 method에 allowed_questions와 blocked_claims 추가
- [X] 각 method에 recommended_charts 추가

## 6. Dependency Management

- [X] data-insight-kit 자체 `pyproject.toml` 추가 (kit 전용 `.venv` 기준, C3 확정)
- [X] optional extra `stats` 정의
- [X] optional extra `ml` 정의
- [X] `interactive-viz`/`echarts` extra는 v4로 연기 (v1에서 만들지 않음)
- [X] `scripts/dependency_preflight.py` 추가
- [X] preflight가 kit 전용 `.venv` 기준으로 설치 여부를 확인 (타 환경 설치는 무시)
- [X] 이미 설치된 group은 `already_installed`로 기록하되 route 승인은 동일하게 요구
  (plan.installed에 기록, analysis_strategy는 approval_targets로 여전히 잠금 —
  tests/test_checkpoint_gate_routing.py::test_default_options_when_extras_already_installed)
- [X] preflight가 allowlist 외 패키지를 거부
  (VALID_EXTRAS 밖 dependency_groups는 issues로 보고, dependency_allowlist가 유일
  허용 목록 — 실제 설치 시점 차단은 dik_checkpoint_hook.py가 담당, §10.2 QA 참고)
- [X] preflight가 `runs/<run-id>/input/dependency_plan.json` 작성
- [X] dry-run에서 설치 없이 필요한 명령만 출력
- [X] 승인 후 `uv sync --extra <group>` 실행 흐름 연결
- [X] 설치 실패 시 fallback route 기록

## 7. Wrapper Flow

- [X] `scripts/run_codex_pipeline.sh`에서 frame 이후 method route 확인 또는 생성
  (agents/frame.md 3-bis 단계가 `outputs/method_route.json` 생성)
- [X] frame 이후 dependency preflight 실행
- [X] analysis_strategy checkpoint에 dependency 선택지 포함
- [X] 사용자가 설치 승인 시 uv extra 설치 실행
- [X] 설치 미승인 시 route 강등 처리
- [ ] domain mode 감지 단계 추가
  (wrapper에 전용 감지 단계 없음 — domain mode는 `domain_intake.json` 존재/
  `manifest.domain_mode`로만 판정되고, 이를 세팅하는 명시적 wrapper 단계는 아직 없음)
- [X] domain mode에서 domain expert intake가 부족하면 다음 단계 차단
  (전용 wrapper 단계는 아니지만 `run_stage`가 매 단계 전 `stage_guard.py`를 호출하고,
  `analyze_domain_entry_issues()`가 그 안에서 analyze 진입을 차단 — 목적은 충족)
- [X] 조건부 `analysis_result_review` 실행 지점 추가
- [X] `--dry-run` 출력에 새 단계가 명확히 표시되는지 확인

## 8. Checkpoint Gate

- [X] `scripts/checkpoint_gate.py`에 `analysis_result_review` 설정 추가
- [X] analysis_strategy 질문에 route와 dependency 정보를 포함
- [X] analysis_strategy 선택지가 설치/기본분석/방향수정을 표현
- [ ] data_profile 질문이 데이터 grain, 품질, 전처리 필요성을 더 잘 보여주는지 확인
  (이번 커밋들의 변경 범위 밖 — data_profile 질문 구성은 손대지 않음)
- [ ] dashboard_storyboard 질문이 단순 분석 run에서 1차 결과 요약을 포함
  (checkpoint_gate.py의 dashboard_storyboard 설정은 이번 커밋에서 수정되지 않음)
- [X] `--print-existing`이 새 checkpoint도 chat-first로 출력
  (checkpoint_id별 분기 없는 공통 로직이라 analysis_result_review에도 동일 적용)
- [X] 질문 artifact에서 내부 용어 노출을 피하는지 확인
  (tests/test_checkpoint_gate_routing.py의 assert_user_facing_clean)

## 9. Stage Guard and Hooks

- [X] `scripts/stage_guard.py`에 조건부 checkpoint 요구사항 추가 (spec §9 술어를 guard가
  직접 재계산, 에이전트 기록 플래그 불신)
- [X] `analysis_strategy` 승인 시점 `approval_targets` sha256과 현재
  method_route/dependency_plan 비교 — 상향 변경이면 차단
- [X] domain mode에서 domain_intake/domain_readiness 부족 시 차단 (readiness는 결정적
  재계산)
- [ ] dependency approval 없이 심화 route 실행 시 차단
  (실제 구현은 "차단"이 아니라 "자동 강등" — apply_approval이 skip_install/설치
  실패 시 analyze 전에 method_route를 core-only로 낮춘다. 목적은 동일하게
  충족하지만 항목 문구가 뜻하는 hard block은 아니라서 미체크로 둠)
- [X] `scripts/dik_checkpoint_hook.py`에 새 산출물 보호 추가 (`method_route.json` 포함)
- [X] hook이 kit run 컨텍스트의 Bash install 명령(`pip install`, `python -m pip install`,
  `uv add`, `uv sync --extra`)을 감지해 유효한 dependency 승인 provenance가 없거나
  allowlist 외 패키지면 deny
- [X] hook이 run 진행 중 `domains/<domain>/` 자동 수정 write를 deny
- [X] Codex hook이 새 checkpoint와 새 공식 산출물을 보호
  (Claude Code Write/Edit/Bash와 Codex apply_patch가 같은 gated_checkpoints_for
  경로를 공유하는 단일 스크립트)
- [X] Claude Code hook 계약과 동일하게 동작
- [X] 자동 실행 예외 정책이 기존 `checkpoint_policy.json`과 충돌하지 않는지 확인
- [X] `scripts/validate_user_facing_text.py` `FORBIDDEN_TERMS`에 신규 내부 용어 추가:
  `method_route`, `dependency_plan`, `domain_readiness`, `domain_intake`,
  `analysis_result_review`, route 내부명(`descriptive|diagnostic|statistical| ml_exploratory|predictive|causal_experiment`) — spec §11 대체 표현 사용

## 10. QA

- [X] `qa/validate.py`가 `method_route.json` schema를 검증
- [X] route와 method가 registry에 존재하는지 검증
- [X] route 조건 부족 시 WARN/BLOCK
- [X] spec §9 술어를 QA가 재계산해 참인데 `analysis_result_review` 승인 provenance가
  없으면 BLOCK
- [X] `approval_targets` sha256 대비 상향 변경 BLOCK
- [X] dependency 승인/설치 provenance 검증 (`approval.answer_id` 연결 확인)
- [X] allowlist 외 dependency 설치 시도 BLOCK
- [X] domain mode에서 domain_intake 누락 시 도메인 결론 BLOCK
- [X] `domain_readiness=insufficient`(QA 재계산 기준)에서 추천/원인/성과 판단 BLOCK
- [X] domain forbidden_claims **명시 문구**가 visible text에 나오면 BLOCK
- [X] 원인/효과/추천 단정의 일반 휴리스틱 검사는 WARN으로 시작 (부정문 오탐 방지,
  대표 run 보정 후 BLOCK 승격)
- [ ] 예측 route에서 타깃/검증기간/누수 기준 누락 시 BLOCK
  (구현은 `data_condition_evidence` 객체의 존재 여부만 확인 — 타깃/검증기간/누수
  금지 기준을 개별 필드로 검증하지는 않음. `additionalProperties: true`라 형식이
  자유로워 세부 구성 검증은 아직 없음)
- [X] 기존 checkpoint lineage QA 회귀 확인
  (legacy fixture BLOCK 1건 유지, 전체 pytest 회귀 없음)
- [X] 기존 render/report QA 회귀 확인
  (동일 legacy fixture 재검증, WARN/BLOCK 외 항목 변화 없음)

## 11. Representative Statistical Route

- [ ] 그룹 차이 후보 판정 결과를 `04_analysis.md`와 chart_spec에 기록
- [ ] 상관 분석 후보 판정 결과를 기록
- [ ] 단순 회귀 후보 판정 결과를 기록
- [ ] 표본 수, 결측, 비교군, 분모 한계를 함께 기록
- [ ] p-value 또는 상관계수만으로 원인/추천을 단정하지 않음
- [ ] stats dependency가 없으면 계산 대신 route 강등 또는 후보만 기록

## 12. Domain Mode Tests

- [ ] domain pack이 지정되면 domain mode 후보로 감지
- [ ] 사용자가 회사/업무/전문 도메인 데이터라고 밝히면 domain mode 후보로 감지
- [ ] domain_intake 부족 시 도메인 결론 차단
- [ ] domain_readiness partial에서 강한 결론 차단
- [ ] domain_readiness ready에서 제한적 도메인 진단 허용
- [ ] domain expert answer가 run-local artifact에 기록
- [ ] domain_pack_update_candidates.md 생성 조건 확인
- [ ] domain pack 자동 수정이 발생하지 않음

## 13. Routing Tests

- [ ] 단순 범주형 데이터는 descriptive/diagnostic으로 남음
  (route 최초 선택은 frame 단계 에이전트 판단 — 결정적 코드로 아직 테스트 불가)
- [ ] 비교군과 수치형 지표가 충분하면 statistical 추천
  (위와 동일 사유 — 에이전트 판단 영역)
- [ ] 비교군 부족 시 statistical 강등
  (강등 트리거 판정은 frame 에이전트 몫 — dependency_preflight의 강등 메커니즘
  자체는 아래 두 항목으로 커버)
- [ ] 타깃 변수 부족 시 predictive 강등
- [ ] 처리군/대조군 부족 시 causal_experiment 강등
- [X] dependency 미승인 시 심화 route 강등
  (tests/test_expert_routing.py::DependencyPreflightApplyApprovalTests
  ::test_skip_install_downgrades_route_and_clears_missing)
- [X] route 강등 사유가 method_route에 기록
  (tests/test_expert_routing.py::DependencyPreflightDowngradeTests +
  DependencyPreflightApplyApprovalTests, downgrade_reason 필드 검증)

## 14. Regression Tests

- [X] 기존 단순 CSV guided run 흐름 유지
  (전체 pytest 108 passed 회귀 없음 + legacy fixture QA BLOCK 1건 유지 +
  wrapper `--dry-run` 스모크, 커밋 8 Part D)
- [X] 기존 checkpoint chat handoff가 질문을 먼저 출력
  (기존 tests/test_pipeline_guards.py::CheckpointGateTests
  ::test_checkpoint_chat_handoff_puts_question_before_files,
  CheckpointAnswerCliTests::test_checkpoint_print_existing_cli_uses_chat_first_handoff)
- [X] Plan Mode 승인 문구가 checkpoint 승인으로 재사용되지 않음
  (기존 tests/test_pipeline_guards.py::UserFacingTextTests
  ::test_plan_mode_output_blocks_preapproval_selected_direction_and_risk_label 등)
- [X] forged/batch approval BLOCK 유지
  (기존 tests/test_pipeline_guards.py::QaQualityGuardTests
  ::test_checkpoint_lineage_blocks_forged_batch_answers,
  CheckpointHookTests::test_denies_batch_fabricated_v1_answers)
- [X] downstream artifact before approval BLOCK 유지
  (기존 tests/test_pipeline_guards.py::QaQualityGuardTests
  ::test_checkpoint_lineage_blocks_artifacts_generated_before_approval)
- [X] fresh-run prior reference BLOCK 유지
  (기존 tests/test_pipeline_guards.py::QaQualityGuardTests
  ::test_run_context_blocks_prior_run_reference_in_fresh_analysis)
- [ ] police-crime source-only 유형에서 인구 보정, 안전도, 원인 주장 차단
  (해당 이름의 전용 회귀 테스트를 찾지 못함 — `runs/police-crime-...` fixture는
  존재하나 이 항목을 검증하는 자동화 테스트로 연결되어 있지 않음)
- [X] dashboard profile QA 유지
  (기존 tests/test_pipeline_guards.py::QaQualityGuardTests
  ::test_dashboard_profile_mismatch_blocks, test_dashboard_profile_layout_sanity_warns)
- [ ] report depth QA 유지
  (`analysis_depth_checks`를 명시적으로 exercising하는 이름 붙은 기존 단위
  테스트를 찾지 못해 미체크로 둠 — 전체 회귀 스위트는 통과하지만 이 항목을
  직접 가리키는 테스트가 없어 정확성을 우선함)

## 15. User-Facing Docs and Skills

- [X] `README.md`에 expert-guided analysis 방향 요약 추가
- [X] `GUIDE.md`에 domain mode, dependency approval, 조건부 result review 설명 추가
- [X] `AGENTS.md`에 새 운영 규칙 반영
- [X] `skills/run-pipeline/SKILL.md`에 새 흐름 반영
- [ ] 설치된 `~/.codex/skills/data-insight-kit/SKILL.md` 갱신 필요 여부 확인
  (파일 존재 확인함 — repo 밖 사용자 로컬 설치본이라 이번 커밋(repo 파일만 변경)
  범위 밖으로 두고 수동 갱신 필요 여부만 남겨둠)
- [X] 사용자용 문구에서 내부 용어 노출을 피하는지 확인
  (README/GUIDE 추가분은 사용자 표현을 우선하고, 내부 route명은 "내부 route"로
  명시적으로 라벨링된 참고용 열/괄호에만 둠)

## 16. Final Verification

- [X] `git diff --check`
- [X] 관련 Python 파일 compile check
- [X] 관련 JSON schema format check (schemas/*.schema.json 전체 JSON 파싱 확인)
- [X] focused unit tests 또는 `tests/test_pipeline_guards.py`
  (전체 `python3 -m pytest tests/ -q` 108 passed, 56 subtests passed)
- [X] wrapper `--dry-run`
- [ ] 단순 분석 smoke (실제 `codex exec`로 end-to-end 실행한 대표 run 없음 — 다음 작업)
- [ ] domain mode smoke (실제 domain mode run 없음 — 다음 작업)
- [ ] statistical route smoke (실제 statistical route run 없음 — 다음 작업)
- [X] 최종 변경 파일 검토

## 17. Implementation Defaults To Preserve

- [X] `domain_readiness`는 `domain_intake.json` 내부 객체로 구현 (status는 결정적 계산)
- [X] `method_route.json` canonical 위치는 `runs/<run-id>/outputs/method_route.json`
- [X] `dependency_plan.json` canonical 위치는 `runs/<run-id>/input/dependency_plan.json`
- [X] dependency 설치 결과는 `dependency_plan.json.install_result`에 기록
- [X] 조건부 결과 검토 질문 파일은 고정 prefix `05_analysis_result_review_question.json|md`
- [X] 기존 checkpoint prefix `01`~`04`는 재배열하지 않음 (renumbering 금지, legacy
  dual-read 불필요 — 실행 순서는 contract가 정의)
