# 파이프라인 계약 (단일 원천)

이 문서는 data-insight-kit 분석 파이프라인의 **런타임 무관 단일 원천**이다.
Claude Code 어댑터(`agents/*.md`)와 Codex CLI wrapper(`scripts/run_codex_pipeline.sh`)는 **이 계약을 참조만** 하고 stage 정의를 다시 만들지 않는다.

## 원칙

- **소스 어댑터 우선**: 사용자는 DuckDB를 반드시 알 필요가 없다. CSV·Parquet·Excel·JSON 같은 로컬 파일, 사용자가 지정한 primary API, 원격 Parquet, DuckDB를 모두 소스 어댑터로 받아들이되, 반복 분석의 기준 입력은 `runs/<run-id>/input/`의 로컬 파일 또는 축약 스냅샷으로 고정한다. DuckDB는 선택 입력이자 내부 SQL 실행 엔진이다.
- **새 분석은 fresh-by-default**: 새 run은 기존 `runs/*` 산출물을 입력·근거·문구로 참조하지 않는다. 새 스레드나 새 run에서 같은 데이터를 다시 분석하는 경우에도 원천 데이터 또는 이번 run의 `input/` 스냅샷부터 다시 확인한다. 기존 분석을 이어서 수정·비교·재사용하려면 사용자가 명시적으로 요청해야 하며, wrapper는 `input/run_context.json`에 `allow_prior_run_reference:true`와 `reference_runs[]`를 남겨야 한다. `fresh_analysis`에서 과거 run 경로가 `dashboard_data.json`, `chart_spec.json`, `manifest.json`, 보고서에 섞이면 QA BLOCK이다.
- **데이터 주입형**: 분석 결과 값은 `dashboard_data.json`(스키마: `schemas/dashboard_data.schema.json`)으로 표현되고, 템플릿이 그것을 읽어 자동 렌더한다. legacy/v4는 이 파일이 렌더 계약이고, v5는 승인된 `dashboard_layout.json`을 함께 사용한다. 에이전트가 HTML·CSS·JavaScript 또는 raw ECharts option을 직접 주입하지 않는다.
- **범용 분석 계획형**: 도메인 특화 규칙 없이도 임의 표 데이터의 의미층을 추론하고, `chart_spec.json`(스키마: `schemas/chart_spec.schema.json`)으로 질문→방법론→계산→차트 선택→최종 대시보드 매핑을 먼저 고정한다. 도메인 힌트는 선택 보조 정보이며 core 계약을 대체하지 않는다.
- **도메인 pack은 보조 컨텍스트**: 회사·업무 도메인 규칙이 필요하면 `domains/<domain>/domain.yaml`을 선택한다. wrapper는 이를 `input/domain_pack_context.md`로 정리해 stage prompt에 전달한다. domain pack은 KPI 후보, 사용자 질문, 금지 표현, 보고서/대시보드 패턴을 돕지만 core 계약·스키마·QA를 대체하지 않는다.
- **질문별 스토리보드형 차트 설계**: 차트는 지표 목록이 아니라 질문에 답하는 증거다. deep 분석은 `dashboard_story`와 최소 2개 storyboard 후보를 갖고, 차트별 `finding/evidence/limit`가 보고서와 대시보드 문구로 이어져야 한다. `dashboard_storyboard` checkpoint에는 사용자가 판단할 수 있는 차트 추천표와 디자인 프로필 선택지가 있어야 하며, 각 행은 사용할 데이터/지표, 비교 기준, 추천 차트, 추천 이유, 대안 차트, 제외/보류 이유를 설명한다. v5에서는 analyze가 만든 `dashboard_layout.json`의 component 순서·desktop span·mobile order도 원문으로 보여주고, 해당 파일의 hash와 revision을 승인 target으로 잠근다. 단순 ranking/bar 반복은 데이터가 그 이상을 허용하지 않는 경우에만 허용하고 한계를 명시한다.
- **전략 라이브러리 기반 심층화**: `docs/analysis-strategy-library.md`를 기준으로 데이터 형태(지역/공간, 시계열, 범주형 분포, 고객/거래, 설문, 운영/재고, 텍스트성 표 데이터)에 맞는 주 전략과 보조 전략을 선택한다. 전략은 KPI·분모·비교축·차트·한계를 함께 정의해야 하며, 단순 상위 N개 반복은 심층 분석으로 보지 않는다.
- **분석 깊이 routing**: frame은 `outputs/method_route.json`(스키마: `schemas/method_route.schema.json`)에 분석 깊이 route를 기록한다. route는 `descriptive | diagnostic | statistical | ml_exploratory | predictive | causal_experiment` 중 하나이고, 선택 method는 `methods/method_registry.json`에 존재해야 한다. registry에 없는 방법은 쓰지 않는다. 데이터 조건(비교군, 표본, 분모, 타깃, 검증 기간, 처리군/대조군)이 부족하면 route를 강등하고 `downgraded_from`, `downgrade_reason`, `allowed_scope`를 기록한다. 강등은 사유 기록으로 허용하지만, `analysis_strategy` 승인 이후의 route 상향은 재승인이 필요하다. 기준 문서는 `docs/specs/expert-guided-analysis-routing.md`다.
- **dependency 승인형 설치**: 심화 route에 추가 패키지가 필요하면 frame 이후 `scripts/dependency_preflight.py`가 `input/dependency_plan.json`(스키마: `schemas/dependency_plan.schema.json`)을 만들고, 설치 승인은 별도 checkpoint가 아니라 `analysis_strategy` checkpoint 선택지로 받는다(`maps_to.dependency_decision: install|skip_install|adjust`). 설치 승인은 명시 옵션 선택만 인정하고 free-text는 설치 승인이 아니다. 설치 대상은 kit 자체 `pyproject.toml`이 정의하는 kit 전용 `.venv`뿐이며(extras: `stats`, `ml`), 전역/워크스페이스 환경에 설치하지 않는다. allowlist 외 패키지 설치와 승인 없는 설치는 hook이 실행 시점에 deny하고 QA가 사후 BLOCK한다. 승인 provenance는 `dependency_plan.json.approval.answer_id` ↔ `checkpoint_answers.json`으로 연결한다.
- **승인 시점 잠금**: `analysis_strategy` 질문 JSON은 생성 시점의 `method_route.json`·`dependency_plan.json` sha256을 `approval_targets`로 내장한다. 승인 후 두 파일이 상향 방향(route 격상, extra 추가)으로 달라지면 stage guard와 QA가 재승인 전 진행을 막는다.
- **조건부 결과 검토**: `analysis_result_review` checkpoint는 analyze 직후에 조건부로 발동하는 hard gate다. 발동 여부는 에이전트 판단이 아니라 결정적 술어 — `method_route.route ∈ {statistical, ml_exploratory, predictive, causal_experiment}` OR domain mode OR `report.depth=deep` OR `analysis_mode ∈ {candidate_prioritization, risk_screening}` — 로 계산하며, stage guard와 QA가 각자 재계산한다(에이전트가 남긴 플래그는 판정 근거가 아니다). 질문 파일은 고정 prefix `05_analysis_result_review_question.json|md`를 쓰고 기존 `01`~`04` prefix는 재배열하지 않는다. 파일명 번호는 식별자이지 실행 순서가 아니다.
- **domain expert intake와 readiness**: 도메인 데이터(내부 용어·코드값·KPI·제외 규칙이 필요한 데이터)는 run-local `input/domain_intake.json`(스키마: `schemas/domain_intake.schema.json`)에 도메인 전문가 답변을 구조화한다. `domain_readiness.status(ready|partial|insufficient)`는 필수 항목 충족에서 결정적으로 계산되며 QA가 재계산해 불일치 시 BLOCK한다. domain mode에서 intake가 없거나 `insufficient`이면 도메인 결론(추천·원인·성과·위험도 확정)은 차단하고 일반 구조 분석만 허용한다. `domain_intake.forbidden_claims`의 명시 문구가 dashboard/report visible text에 나오면 BLOCK, 그 외 과잉해석 휴리스틱 검사는 WARN으로 시작한다. domain pack 자동 수정은 금지한다.
- **외부 context adapter는 선택 layer**: 기본 입력 데이터만으로 결론을 확정하기 어려운 경우 보조 데이터와 보정 지표는 `docs/external-denominator-adapters.md`, `docs/external-adapter-registry.md`, `schemas/external_denominator_manifest.schema.json`을 따른다. 기본 데이터의 건수·비율·순위·집중도는 관찰된 구조일 뿐이며, 별도 근거 없이 수요·성과·원인·추천으로 재명명하지 않는다. 외부 context가 있어도 `source_ref`, 기준일, 분석 단위, join key, coverage, 결측률, 합산 기준이 없으면 결론 강도를 낮춘다.
- **사용자용 기획안 우선**: Plan Mode, guided intake, checkpoint 문서는 `docs/user-facing-planning.md`를 따른다. 사용자가 먼저 보는 부분은 분석 목적·답할 질문·가능/불가능한 판단·분석 방향 선택지여야 한다. run-id, endpoint, pagination, source_ref, chart_spec, QA 명령은 "기술 부록"으로 분리한다. 사용자가 요구하지 않으면 기술 부록은 짧은 실행 요약만 보여주고 상세 명령·스키마·파일 목록을 길게 펼치지 않는다.
- **질문형 intake**: 사용자가 목적을 명확히 주면 즉시 진행하고, 목적·의사결정·성공기준이 모호하면 AskUserQuestion 방식으로 가장 큰 불확실성 1개부터 묻는다. 질문은 deep-interview 원칙을 따라 "현재 이해 / 막힌 결정 / 추천 답안 / 질문" 구조로 제시한다. 답변은 `intake_draft.yaml`에 누적하고, 최대 3문항 안에서 충분해지면 최종 `intake.yaml`을 확정한다. non-interactive에서는 `outputs/intake_questions.md`와 AskUserQuestion 호환 `outputs/intake_questions.json`을 남기고 중단한다. 단, wrapper가 `--guided-intake`를 받은 검증 run에서는 요청이 명확해도 최소 1회 `intake_draft.yaml` 경유와 `finalization.finalized_by: guided_intake` 기록을 요구한다.
- **중간 사용자 체크포인트**: intake가 끝나도 곧바로 끝까지 생성하지 않는다. `explore` 후 데이터 프로파일, `frame` 후 분석 전략, `analyze` 후 대시보드 storyboard, `qa` 통과 후 보고서 outline을 사용자에게 보여주고 승인 또는 수정 요청을 받는다. non-interactive에서는 `outputs/checkpoints/*.json|*.md`와 샘플 preview를 남기고 exit code `3`으로 중단한다. 각 checkpoint는 deep-interview 원칙을 따른다. 즉 "현재 이해 / 막힌 결정 / 추천 답안 / 질문" 형식의 `chat_prompt`를 제공하고, 가장 큰 불확실성 하나만 묻는다. wrapper와 상위 에이전트는 파일 목록, 산출물 요약, 로그보다 이 `chat_prompt`와 선택지를 먼저 보여줘야 한다. 승인 답변은 `scripts/apply_checkpoint_answer.py`로만 `checkpoint_answers.json`에 기록하고, `continue_pipeline=false` 답변은 수정 전까지 다음 단계 진행을 막는다. 승인으로 인정되는 답변은 `source=user_chat|ask_user_question|manual_cli`, `human_confirmed=true`, `user_response`, `approval_contract_version=checkpoint-answer.v3`, `recorded_by`, `answer_id`, `question_ref` provenance를 모두 가져야 한다. `source=user_chat|ask_user_question` 답변은 실제 사용자 메시지나 팝업 답변을 가리키는 `transcript_ref`도 가져야 한다. Plan Mode 승인 문구나 에이전트 추천 답안을 checkpoint별 승인 문구로 쪼개 기록하면 안 된다. QA는 downstream 산출물이 checkpoint 승인보다 먼저 만들어진 경우도 BLOCK한다. 에이전트 추천 답안이나 기존 계획을 근거로 만든 `agent_assumption` 답변은 다음 단계 진행을 허용하지 않는다. 명시적 자동 실행이 필요한 경우에만 wrapper에서 `--auto` 또는 `--no-checkpoints`를 사용한다.
- **stage guard**: wrapper는 `frame`, `analyze`, `visualize`, `qa`, `communicate` 진입 전에 `scripts/stage_guard.py`로 필요한 이전 checkpoint 승인 provenance를 검사한다. 질문 파일 hash, 질문 생성 시각, 답변 시각, 전용 기록 스크립트 흔적이 맞지 않으면 후속 stage를 시작하지 않는다.
- **checkpoint lineage QA**: 최종 `dashboard_data.json`과 보고서는 `qa/validate.py`에서 checkpoint 증거도 검증한다. 일반 guided 실행은 `data_profile`, `analysis_strategy`, `dashboard_storyboard` 질문 artifact와 실제 사용자 승인 답변이 필요하며, `--post-communicate` 검증에서는 `report_outline`도 필요하다. wrapper가 아닌 run-local builder가 산출물을 직접 만들었거나 `checkpoint_answers.json`이 없거나 v3 provenance가 맞지 않으면 출고 BLOCK이다. 여러 checkpoint가 같은 시각·같은 Plan 승인 문장으로 일괄 승인된 흔적도 BLOCK한다. 자동 실행은 wrapper가 `input/checkpoint_policy.json`에 `mode=auto`, `explicit_skip=true`를 남긴 경우에만 예외로 본다.
- **배포용 언어 게이트**: 대시보드와 보고서의 제목, KPI, 축 라벨, 요약 도입부는 독자 언어로 작성한다. `proxy`, `layer`, `grain`, `chart_spec`, `source_ref`, 원천 컬럼명, 코드값, 내부 지표명 같은 분석·구현 용어는 방법론·부록·tooltip 수준으로 제한한다. QA는 내부 용어가 visible label에 과도하게 노출되면 WARN/BLOCK한다.
- **guided adapter 선택**: 외부 context가 판단을 크게 바꾸는 요청에서는 guided intake가 `external_adapter_policy` 질문을 만들 수 있다. 이 질문은 수집 실행이 아니라 원하는 adapter layer 정책을 `intake.external_adapters`에 남기는 단계다. wrapper/adapter는 intake 이후 이 정책을 `runs/<run-id>/input/external_adapter_plan.json`과 `runs/<run-id>/external_adapter_plan.json`으로 정규화해 connect 이후 stage prompt에 전달한다.
- **보고서 선택형**: 보고서의 깊이(`brief|standard|deep`), 독자(`executive|analyst|operator|mixed`), 근거 범위(`data_only|web_context`)를 분리한다. 범용 기본값은 `standard + mixed + data_only`이다. 사용자가 심층 검토를 원하거나 결과가 실제 의사결정에 쓰이면 `deep + mixed + data_only`를 추천할 수 있고, 사용자용 표현은 "요약 보고서와 심층 검토 보고서, 데이터 근거만 사용"이다. 외부 웹 맥락은 명시적으로 선택된 경우에만 별도 출처와 함께 보강한다.
- **보고서 루브릭 기반 커뮤니케이션**: `docs/report-quality-rubric.md`를 기준으로 `summary_report.md`와 `deep_report.md`의 역할을 분리한다. `summary_report.md`는 빠른 판단을 위한 요약이고, `deep_report.md`는 방법론·KPI·세그먼트·반대 해석·한계·액션 기준·lineage를 갖춘 심층 검토 문서다.
- **결정적 코어 우선**: 스크립트·스키마 검증 결과가 LLM 판단보다 우선한다. (`connectors/source.py`, `qa/validate.py`)
- **제한된 자동 교정 후 사람 에스컬레이션**: 루프백·QA 자동수정 모두 최대 1회, 그 뒤 사람에게 보고.
- **보안과 산출물 경계**: DB 접근은 `connectors/source.py` 경유만(read-only·SELECT/WITH 전용). 원격·대용량 데이터는 필요한 컬럼과 행으로 축약한 스냅샷만 로컬에 남기고, 대표성이 중요한 경우 층화 샘플링 방식을 manifest에 기록한다. 쓰기는 `runs/<run-id>/` 안에만. PII 기본 마스킹. DB 경로·자격은 `.env`(커밋 금지). `runs/*`는 사용자별 로컬 산출물로 간주하고 배포용 core에는 포함하지 않는다.

## 실행 순서

```
0 intake → 1 connect → 2 explore → H1 data_profile → 3 frame (+ method_route
        + dependency_preflight) → H2 analysis_strategy (route·설치 승인 포함)
        → [승인 시 dependency 설치]
        → 4 analyze (+ v5 layout draft) → [H2.5 analysis_result_review — 결정적 술어 참일 때만]
        → H3 dashboard_storyboard (+ v5 layout hash·revision 승인)
        → 5 visualize → 6 qa → H4 report_outline
                                       ▲                                      │
                                       └── 루프백 1회 ───────────────────────┘─ 기계적 결함 시 5로 1회
        → 7 communicate
   (analyze가 "문제정의/지표가 데이터와 불일치" 명시 감지 시 frame으로 1회)
```

- **분기(intake)**: `directed`(질문 있음) → explore·frame 압축 / `exploratory`(데이터 우선) → 풀 실행. `intake.yaml`에 보고서 옵션이 없으면 범용 데이터는 `report{depth:"standard", audience:"mixed", evidence_scope:"data_only"}`를 쓴다. 목적이 막연한 상태에서 `deep` 또는 의사결정형 대시보드를 만들면 질문형 intake로 보강한다. 질문 답변이 충분하기 전에는 `intake.yaml`을 만들지 말고 `intake_draft.yaml`만 갱신한다.
- **run context**: wrapper는 실행 전 `input/run_context.json`을 만든다. 기본값은 `mode:"fresh_analysis"`, `allow_prior_run_reference:false`, `reference_runs:[]`이다. 사용자가 "기존 run을 참고", "이전 결과와 비교", "기존 대시보드 수정", "resume"을 명시한 경우에만 `mode:"revise_previous|compare_with_previous|resume_run"`과 `allow_prior_run_reference:true`를 쓴다. "이전 run을 참조하지 않는다/않고", "기존 결과를 재사용하지 않는다"처럼 같은 문장에 명시된 부정 표현은 과거 참조 키워드보다 우선하여 `fresh_analysis`로 판정한다. 각 stage는 이 파일을 읽고, fresh mode에서는 이전 `dashboard_data.json`, `chart_spec.json`, 보고서, old `runs/*` 스냅샷을 입력으로 쓰지 않는다.
- **guided intake 검증 모드(wrapper/adapter)**: AI 앱에서는 Codex Desktop과 Claude Code 모두 Plan Mode에서 사용자용 분석 기획안과 실행 계획을 먼저 확인한다. CLI 검증은 `bash scripts/run_codex_pipeline.sh <run-id> --guided-intake`를 사용하고, Claude Code plugin의 `/run-pipeline` guided 흐름도 첫 실행에서 `outputs/intake_questions.json/md`를 만들고 사용자 답변 전에는 멈춘다. 상위 UI 또는 사용자는 답변을 `intake_draft.yaml`에 누적하고 같은 흐름을 재실행한다. 기존 `intake.yaml`이 있더라도 `finalization.finalized_by: guided_intake|ask_user_question|user_popup` 흔적이 없으면 silently bypass하지 않고 중단한다. 외부 context 정책이 필요한 요청인데 최종 intake에 `external_adapters` 정책이 없으면 connect로 넘어가기 전에 `external_adapter_policy` 질문으로 다시 멈춘다.
- **질문 대기 상태 표현**: 질문 대기로 중단하더라도 `manifest.intake.mode`에는 `blocked` 같은 값을 쓰지 않는다. `mode`는 항상 `directed|exploratory`이고, 중단 상태는 `stages[].status="blocked_for_user_question"` 및 `interview.needed=true`로 표현한다.
- **human checkpoint 대기 상태 표현**: 중간 체크포인트 대기로 중단하면 `stages[].name="checkpoint:<id>"`, `stages[].status="blocked_for_user_checkpoint"`로 남긴다. 질문 파일은 `outputs/checkpoints/<NN>_<checkpoint_id>_question.json|md`이며 스키마는 `schemas/checkpoint_question.schema.json`이다. JSON에는 `created_at`, `interview_style:"deep_interview_checkpoint"`, 초보자용 `user_review_brief`, `recommended_answer`, `chat_prompt`, `response_instructions.human_response_required=true`가 있어야 한다. 상위 에이전트는 긴 artifact 요약보다 `user_review_brief`와 `chat_prompt`를 먼저 사용자에게 제시한다. CLI/adapter 출력도 `scripts/checkpoint_gate.py <run-id> <checkpoint-id> --print-existing` 형식의 채팅용 handoff를 우선 사용한다. 답변은 `scripts/apply_checkpoint_answer.py <run-id> <checkpoint-id> --option <option-id> --source user_chat --user-response "<사용자 실제 답변>" --transcript-ref "<thread/message id>"` 또는 free-text로 `checkpoint_answers.json`에 누적한다. `manual_cli` 출처는 로컬 운영자가 직접 입력한 경우에만 쓰며, 에이전트가 대신 작성하는 우회 경로로 쓰지 않는다. 이 스크립트는 질문 파일 hash와 생성 시각을 `question_ref`에 기록한다. `--source`와 `--user-response`가 없거나 legacy `source=chat`만 있는 답변, 또는 run-local builder가 직접 만든 답변 파일은 승인으로 인정하지 않는다.
- **사용자 발화 전달(wrapper/adapter)**: non-interactive wrapper는 원 채팅 UI를 직접 읽을 수 없으므로, 상위 에이전트는 `DIK_USER_REQUEST` 또는 `runs/<run-id>/user_request.txt`로 사용자 원 발화를 전달할 수 있다. 이 값은 각 stage prompt에 포함되어 intake 질문 판단의 근거가 된다.
- **루프백**: analyze→frame 정확히 1회(프레이밍 불일치 명시 시만). 1회 후에도 불일치면 에스컬레이션.
- **QA 게이트**: qa는 visualize 산출물을 검증한다. legacy/v4는 기존 schema·계획 정합·SVG/browser 검사를 유지한다. v5는 (1) layout schema와 chart/layout/data 교차계약, (2) compiler manifest의 input·template·vendored ECharts checksum, (3) desktop 1440×1000 및 mobile 390×844 browser QA, (4) 오케스트레이터의 screenshot 직접 눈검토 순서로 검사한다. v5.1 opt-in은 여기에 compact 736×1000과 narrow 320×800을 추가하고 `outputs/visual_review.json`을 현재 네 screenshot hash에 결합한다. 네 장을 직접 검토한 기록이 `status=pass`가 아니면 report_outline checkpoint로 전달하지 않는다. browser QA는 component 경계뿐 아니라 ECharts의 보이는 legend bounding box와 plot grid가 겹치거나 legend가 canvas 밖으로 잘리는 경우도 BLOCK한다. 눈검토는 문구·정보 위계·색 의미·척도·범례·축·라벨·plot·공백을 포함한다. v5 오류는 legacy/v4 렌더로 강등하지 않는다. 기계적 결함(콘솔·원격 요청·빈 차트·component/legend 겹침·overflow·잘림·상호작용 상태/리셋 누락) → visualize 1회 자동 재수정. 분석적 결함(데이터 무결성·표본 부족·모순) → 중단+보고. 통과해야 report_outline checkpoint로 가고, 보고서 구성 승인을 받아야 communicate로 간다.

## 단계별 계약 (티어는 `docs/model-tier-map.md`)

| # | 단계 | 티어 | 입력 | 출력 |
|---|------|------|------|------|
| 0 | **intake** | 경량 | 사용자 목적·발화, `input/run_context.json`, 선택 `intake_draft.yaml` | `manifest.intake{mode,objective,decision_context,analysis_mode,user_expertise,known_questions,success_criteria,exclusions,constraints,open_questions,interview,report{depth,audience,evidence_scope}}` (`intake.yaml` 있으면 확정 계약. 없고 목적이 모호하면 `outputs/intake_questions.md` + `outputs/intake_questions.json` 생성 후 중단. 답변은 `intake_draft.yaml`에 누적하고 충분하면 `intake.yaml` 확정. 새 분석은 prior run 참조 금지 정책을 유지) |
| 1 | **connect** | 실행 | intake, 선택 `domain_pack_context.md`, `external_adapter_plan.json`, 소스 어댑터(`input/` 파일·스냅샷 / `source_api_manifest.json` / 선택 DuckDB), 선택 외부 context manifest | `intermediate/*.parquet`, `outputs/01_profile.md`(semantic profile 포함), `manifest.sources[]`, 선택 `external_denominators.json`(schema 검증·coverage·grain 품질 메모 포함), 사용 불가 adapter category 메모 |
| 2 | **explore** | 사고 | 01_profile, 정제 데이터, analysis strategy library | `outputs/02_eda.md` (데이터 형태 판정, 주/보조 전략 후보, 방법론 후보, 분석 모드 후보, 핵심 질문) |
| H1 | **data_profile checkpoint** | 결정적 hook | 01_profile, 02_eda, input sample | `outputs/checkpoints/01_data_profile_question.json|md`, 가능하면 `outputs/checkpoints/data_preview.*`. 승인 전 frame 금지 |
| 3 | **frame** | 사고 | 02_eda, strategy 후보, 선택 `domain_pack_context.md`, 선택 `domain_intake.json`, `external_adapter_plan.json`, 선택 external context manifest | `outputs/03_frame.md` (문제정의 MECE + 선택 전략 + 분석 방향 선택지 2~3개 + KPI 정의: 이름·계산식·단위·분모 + metric_layer + 성공기준 매핑) + `outputs/method_route.json` + (심화 route 시) `input/dependency_plan.json` (preflight 경유) |
| H2 | **analysis_strategy checkpoint** | 결정적 hook | 03_frame, method_route, dependency_plan, checkpoint answers | `outputs/checkpoints/02_analysis_strategy_question.json|md` (`approval_targets` sha256 내장, 설치 필요 시 dependency 선택지 포함). 승인 전 analyze 금지 |
| 4 | **analyze** | 사고 | 03_frame, method_route, 정제 데이터, 선택 전략, 선택 `domain_pack_context.md`, 선택 `domain_intake.json`, `external_adapter_plan.json`, 선택 external context manifest | `outputs/04_analysis.md` (General→Specific 인사이트·근거·한계·액션·반대해석·전략 적용 결과. 추천/대안 storyboard, 기본 데이터와 외부 context layer 분리) + `outputs/chart_spec.json`; v5이면 `outputs/dashboard_layout.json` 초안 추가 |
| H2.5 | **analysis_result_review checkpoint (조건부)** | 결정적 hook | 04_analysis, method_route, 선택 domain_intake, checkpoint answers | `outputs/checkpoints/05_analysis_result_review_question.json|md`. 결정적 술어 참인 run에서 승인 전 visualize 금지 |
| H3 | **dashboard_storyboard checkpoint** | 결정적 hook | 04_analysis, chart_spec, 선택 dashboard_layout, checkpoint answers | `outputs/checkpoints/03_dashboard_storyboard_question.json|md`. 사용자용 차트 추천표와 디자인 프로필 선택지 포함. v5이면 layout path·revision·component 표를 표시하고 layout hash+revision을 `approval_targets`로 잠금. 승인 전 visualize 금지 |
| 5 | **visualize** | 실행 | chart_spec, 04_analysis, 03_frame, 선택 `domain_pack_context.md`, 스키마, 템플릿, v5이면 승인된 dashboard_layout | `outputs/dashboard_data.json`; legacy/v4는 기존 `templates/dashboard.html`, v5는 `scripts/render_dashboard_v5.py` compiler로 `outputs/dashboard.html`과 `outputs/dashboard_build_manifest.json` 생성 |
| 6 | **qa** | 경량 | dashboard_data.json, dashboard.html, chart_spec, v5이면 dashboard_layout·build manifest | `qa/validate.py` 실행 결과 → `manifest.qa{block,warn,blocked_reason}`. v5는 static→compile manifest→browser→screenshot 직접 검토의 4단계이고, v5.1은 1440×1000·736×1000·390×844·320×800 및 `outputs/visual_review.json`을 요구한다. BLOCK 시 게이트 차단. communicate 이후 `--post-communicate`로 보고서 깊이도 검증 |
| H4 | **report_outline checkpoint** | 결정적 hook | dashboard_data, chart_spec, 04_analysis, report contract | `outputs/checkpoints/04_report_outline_question.json|md`. 승인 전 communicate 금지 |
| 7 | **communicate** | 실행 | manifest.intake.report, 04_analysis, chart_spec, dashboard_data.json, 선택 `domain_pack_context.md`, report rubric | `outputs/summary_report.md` (동일 데이터 참조, 재계산 금지). `depth=deep`이면 `outputs/deep_report.md`, `evidence_scope=web_context`이면 `outputs/external_context.md` 추가 |

## 분석 전략 라이브러리와 보고서 루브릭

- `docs/analysis-strategy-library.md`는 데이터 형태별 전략 선택의 기준이다. explore는 데이터 형태를 판정하고, frame은 선택 전략을 KPI와 성공 기준에 연결하고, analyze는 그 전략으로 실제 인사이트와 chart_spec을 만든다.
- `docs/external-denominator-adapters.md`는 선택 외부 context adapter 수집·조인 기준이고, `docs/external-adapter-registry.md`는 category별 의미·허용 해석·금지 해석 기준이다. 외부 context를 쓰는 run은 가능하면 `runs/<run-id>/external_denominators.json`을 남기고, schema는 `schemas/external_denominator_manifest.schema.json`을 따른다.
- `external_adapter_plan.json`은 guided intake 선택 정책이다. 실제 외부 데이터 lineage가 아니다. 이 plan의 `selected_categories`는 사용자 의도이고, connect가 실제 manifest/source를 확인해 `available_categories`와 `unavailable_categories`를 구분한다.
- `docs/report-quality-rubric.md`는 communicate와 qa-post의 기준이다. communicate는 보고서를 루브릭 구조에 맞춰 작성하고, qa-post는 필수 구조·키워드·복사 유사도·lineage 신호를 검증한다.
- 도메인 팩이 추가되더라도 이 두 문서가 core 품질 기준이다. 도메인 팩은 전략 선택을 보조할 수 있지만, KPI 분모·비교 기준·한계·근거 추적성을 생략하게 만들 수 없다.
- 선택된 domain pack은 `DIK_DOMAIN_PACK=domains/<domain>/domain.yaml` 또는 `runs/<run-id>/input/domain_pack_ref.txt`로 지정할 수 있다. wrapper는 `scripts/prepare_domain_pack_context.py`로 `runs/<run-id>/input/domain_pack_context.md`를 만들고, intake를 포함한 이후 stage prompt에 전달한다. 이 context는 질문·KPI 후보·금지 표현·차트/보고서 패턴의 보조 자료이며, domain pack이 결론을 바꾸는 경우에도 해당 checkpoint에서 사용자가 승인해야 한다.

## 외부 context adapter lifecycle

외부 context를 쓰는 run은 다음 lifecycle을 따른다.

1. **snapshot**: 원천이 API·공개 조회 화면·원격 파일이면 분석에 필요한 grain까지
   로컬 스냅샷으로 고정한다. 페이지네이션·커서·지역 반복 조회가 필요한 경우
   `acquisition.pagination_checked`, `page_count`, `collected_row_count`를 기록한다.
   start/end index 방식 JSON API나 반복 수집 메타는 `scripts/external_adapter_utils.py`
   의 `fetch_paged_json` 같은 core helper를 우선 사용한다.
2. **canonicalize**: 분석 기준 grain을 먼저 정하고, 상위/하위 행정구역이나 중복
   key가 섞인 원천은 그대로 합산하지 않는다.
3. **join audit**: `join_keys`, `coverage.grain_count`, `matched_count`,
   `match_rate`, `null_rate`를 기록한다. `match_rate < 0.80` 또는
   `null_rate > 0.20`이면 분석적 BLOCK 대상, `match_rate < 0.95` 또는
   `null_rate > 0.05`이면 WARN 대상이다. coverage 계산은
   `coverage_audit` helper를 우선 사용한다.
4. **aggregation basis**: 전체 합계·비율·지수·보정 기준은 raw source
   total이 아니라 matched grain 또는 명시된 가중 기준으로 계산한다.
   새 manifest는 가능하면 `grain_quality.denominator_aggregation_basis`와
   `matched_grain_only`를 기록한다.
   `fine grain -> coarse grain`, `custom -> macro group`처럼 거친 집계·수동 매핑을
   하면 `grain_quality.coarse_aggregation=true`와 `aggregation_grain`을 기록하고,
   보고서·대시보드에 정밀 join이 아님을 표시한다.
5. **calculation guards**: 순위 차이(`rank_delta`, `rank_shift`)는 signed integer로
   계산한다. `signed_rank_shift_expr` helper를 우선 사용하고, unsigned overflow로
   비정상적으로 큰 순위 차이가 나오면 QA BLOCK이다.
6. **language guard**: 외부 context가 일부만 붙은 경우에도 해당 context가
   직접 뒷받침하는 판단까지만 말한다. 필요한 수요·비용·성과·원인 layer가
   없으면 추천, 원인 확정, 성과 확정 같은 강한 결론 표현을 금지한다.
7. **metric layer guard**: adapter category와 field metric_layer는 충돌하면 안 된다.
   `population`과 `foot_traffic`은 demand/context, `rent`는 cost/context,
   `sales`는 performance/context, `business_dynamics`는 context/coverage를
   기본으로 하며, 모든 adapter는 coverage layer를 품질 지표에만 쓴다.

## intake 계약 상세

`manifest.intake`는 이후 모든 단계가 공유하는 요구사항 계약이다. 에이전트는 다음 필드를 가능한 범위에서 채운다.

```json
{
  "mode": "directed | exploratory",
  "run_context": {
    "mode": "fresh_analysis | revise_previous | compare_with_previous | resume_run",
    "allow_prior_run_reference": false,
    "reference_runs": []
  },
  "objective": "분석의 최종 목적",
  "decision_context": "이 결과로 사용자가 내릴 판단 또는 다음 행동",
  "analysis_mode": "candidate_prioritization | status_diagnosis | risk_screening | growth_diagnosis | operations_monitoring | segment_discovery | data_quality | custom",
  "user_expertise": "beginner | intermediate | advanced | unknown",
  "known_questions": ["이미 명시된 질문"],
  "success_criteria": ["완성 판단 기준"],
  "exclusions": ["하지 않을 분석"],
  "constraints": ["시간, 데이터, 도구, 정책 제약"],
  "open_questions": ["아직 불확실하지만 진행 가능한 질문"],
  "interview": {
    "needed": true,
    "style": "ask_user_question + deep_interview",
    "question_count": 1,
    "unresolved": ["남은 불확실성"]
  },
  "external_adapters": {
    "mode": "ask_user_selected | auto_recommended | none",
    "selected_categories": ["population", "foot_traffic", "rent", "sales", "business_dynamics"],
    "unavailable_categories": [],
    "interpretation_guards": [
      "do_not_overclaim_without_supporting_context",
      "layer_separation_required",
      "no_recommendation_from_single_context_layer"
    ],
    "registry_ref": "docs/external-adapter-registry.md"
  },
  "finalization": {
    "finalized_by": "manual | guided_intake | ask_user_question | user_popup",
    "finalized_at": "ISO-8601 timestamp",
    "draft_path": "runs/<run-id>/intake_draft.yaml",
    "question_count": 1
  },
  "report": {
    "depth": "brief | standard | deep",
    "audience": "executive | analyst | operator | mixed",
    "evidence_scope": "data_only | web_context"
  }
}
```

질문형 intake 규칙:

- 코드나 데이터 프로파일에서 추론 가능한 것은 사용자에게 묻지 않는다.
- 한 번에 하나의 핵심 불확실성만 묻고, 최대 3문항까지만 이어간다.
- 질문 형식은 `현재 이해`, `막힌 결정`, `추천 답안`, `질문`, `선택지`를 포함한다.
- 사용자가 "잘 모르겠다"고 답하면 추천 답안을 기본값으로 삼고, 남은 불확실성은 `open_questions`에 남긴다.
- 사용자의 답변은 먼저 `intake_draft.yaml`에 누적한다. draft는 확정 계약이 아니며, 충분한 정보가 모였을 때만 최종 `intake.yaml`을 작성한다.
- 최종 `intake.yaml`을 작성할 때는 `interview.question_count`와 `finalization.finalized_by`를 남긴다. guided intake 검증 모드는 이 trace가 없으면 통과한 것으로 보지 않는다.
- `external_adapter_policy` 질문에 답한 경우 `external_adapters.mode`, `selected_categories`, `unavailable_categories`, `interpretation_guards`, `registry_ref`를 draft와 최종 intake에 남긴다.
- non-interactive 실행에서 목적이 너무 모호하면 `outputs/intake_questions.md`와 `outputs/intake_questions.json`을 만들고 중단한다. 얕은 기본 보고서로 조용히 진행하지 않는다.

권장 deep-interview 질문 순서:

1. `decision_context`: 이 결과로 내릴 판단 또는 다음 행동.
2. `scope_focus`: 지역·범주·기간·세그먼트 중 결과를 크게 바꾸는 분석 범위.
3. `external_adapter_policy`: 외부 보정 데이터가 결론 품질을 크게 바꾸거나 사용자가 명시적으로 요청했을 때만 묻는다.
4. `report_contract`: 보고서 깊이, 독자, 근거 범위. 사용자가 명시하지 않았고 기본값이 안전하면 생략한다.

`outputs/intake_questions.json`은 상위 에이전트나 IDE가 실제 `AskUserQuestion`/선택지 UI로 바꿔 표시하기 위한 handoff 계약이다. 스키마는 `schemas/intake_questions.schema.json`이며, 핵심 필드는 다음과 같다.
`user_analysis_brief.answerable_questions`에는 사용자 업무 질문만 쓴다. 차트 다양성, QA BLOCK, 단순 Top-N 금지, schema 검증처럼 에이전트가 내부적으로 지켜야 할 품질 기준은 `internal_execution_plan`, agent 지침, QA 기준으로 보내고 사용자 질문으로 섞지 않는다.
사용자용 brief에는 `preflight_requirements`와 `approval_options`를 반드시 포함해, 실행 전에 필요한 준비사항과 사용자가 바로 고를 수 있는 선택지를 분리한다.
사용자용 brief 값에는 `data_profile`, `analysis_strategy`, `dashboard_storyboard`, `report_outline`, `source_api_manifest`, `checkpoint_question`, `qa/validate.py`, 내부 스키마명, 내부 지표명, 대화 이력 관리 문구를 쓰지 않는다. 해당 표현은 기술 부록이나 내부 실행 계획으로 보내고, 사용자용 본문에는 "데이터 확인 단계", "분석 방향 확인 단계", "대시보드 구성안 확인 단계", "보고서 구성안 확인 단계", "추가로 확인할 대상", "상대적으로 두드러지는 대상"으로 바꾼다. 첫 승인 전에는 "선택된 방향" 대신 "추천 방향" 또는 "우선 제안하는 방향"이라고 쓴다. 분모나 보조 맥락이 없는 단순 건수 데이터에는 "리스크 진단", "위험도", "안전도"를 기본 표현으로 쓰지 않고 "분포·집중도 진단", "구조 진단"으로 제한한다. 승인 질문은 시스템 동작 설명이 아니라 사용자가 바로 고를 수 있는 선택 질문으로 작성한다.

```json
{
  "schema_version": "data-insight-kit.intake_question.v1",
  "run_id": "<run-id>",
  "status": "blocked_for_user_question",
  "question_id": "decision_context",
  "question_kind": "decision_context",
  "header": "분석 목적",
  "user_analysis_brief": {
    "plain_title": "이번 분석으로 무엇을 판단할지 먼저 정합니다",
    "analysis_goal": "데이터를 분석하기 전에 결과물로 어떤 판단을 돕고 싶은지 확인합니다.",
    "answerable_questions": [
      "어떤 후보나 영역을 비교해야 하나요?",
      "분포·집중도·예외 중 무엇을 우선 봐야 하나요?"
    ],
    "data_can_support": [
      "입력 데이터에 들어 있는 범위, 기간, 컬럼으로 직접 계산 가능한 지표"
    ],
    "not_answerable": [
      "데이터에 없는 매출, 수요, 비용, 성과를 확정하는 판단"
    ],
    "analysis_options": [
      {
        "label": "후보·우선순위 판단",
        "description": "여러 대상을 비교해 우선순위를 정합니다.",
        "recommended": true
      },
      {
        "label": "분포·집중도 진단",
        "description": "현재 구조, 집중 구간, 예외적으로 두드러지는 대상을 확인합니다."
      }
    ],
    "checkpoint_plan": [
      "데이터 샘플과 품질 요약을 보여주고 범위와 품질을 확인합니다.",
      "핵심 지표와 분석 방향 선택지를 제안하고 다시 확인합니다."
    ],
    "preflight_requirements": [
      "원천 파일이나 API 키처럼 데이터 접근에 필요한 준비사항을 먼저 확인합니다.",
      "데이터가 없거나 인증이 막히면 대체 데이터를 꾸미지 않고 수집 문제로 멈춥니다."
    ],
    "approval_options": [
      {
        "label": "추천 방향으로 진행",
        "description": "후보·우선순위 판단을 기준으로 데이터 확인 단계부터 시작합니다.",
        "recommended": true
      },
      {
        "label": "범위나 대상을 바꾸기",
        "description": "지역, 기간, 범주, 고객군 같은 분석 범위를 먼저 조정합니다."
      }
    ],
    "approval_question": "추천 방향으로 데이터 확인 단계부터 시작할까요, 아니면 목적·범위를 바꿀까요?"
  },
  "current_understanding": "...",
  "blocked_decision": "...",
  "recommended_option_id": "decision_support",
  "question": "이번 분석은 무엇을 판단하기 위한 것인가?",
  "options": [
    {
      "id": "decision_support",
      "label": "후보·우선순위 판단",
      "description": "여러 대상이나 세그먼트를 비교해 우선순위를 정한다.",
      "recommended": true,
      "maps_to": {
        "analysis_mode": "candidate_prioritization"
      }
    },
    {
      "id": "diagnosis",
      "label": "분포·집중도 진단",
      "description": "현재 구조, 집중 구간, 예외적으로 두드러지는 대상을 확인한다.",
      "maps_to": {
        "analysis_mode": "status_diagnosis"
      }
    },
    {
      "id": "exploration",
      "label": "데이터 탐색",
      "description": "아직 명확한 의사결정보다 데이터의 구조와 주요 세그먼트를 발견한다.",
      "maps_to": {
        "analysis_mode": "segment_discovery"
      }
    }
  ],
  "allow_free_text": true,
  "adapter_selection": null,
  "interview_state": {
    "question_index": 1,
    "max_questions": 3,
    "answered_decisions": {},
    "remaining_decisions": [
      "scope_focus",
      "report_contract"
    ],
    "can_finalize_after_answer": false,
    "finalization_rule": "답변 후 남은 결정이 기본값으로 안전하게 채워지면 intake.yaml을 확정한다."
  },
  "response_instructions": {
    "mode": "draft",
    "write_to": "runs/<run-id>/intake_draft.yaml",
    "finalize_to": "runs/<run-id>/intake.yaml",
    "apply_command": "python3 scripts/apply_intake_answer.py <run-id> --option <option-id>",
    "resume_command": "bash scripts/run_codex_pipeline.sh <run-id>"
  }
}
```

상위 에이전트가 Plan mode의 `AskUserQuestion` 팝업으로 답변을 받으면, 답변을 바로 `intake.yaml`에 쓰지 않고 다음 helper로 `intake_draft.yaml`에 누적한다. helper는 `intake_questions.json`의 `question_id`, 선택지 `maps_to`, `remaining_decisions`를 읽어 `answered_decisions`, `answers[]`, `interview.question_count`, `draft_status`를 갱신한다.

```bash
python3 scripts/apply_intake_answer.py <run-id> --option <option-id>
python3 scripts/apply_intake_answer.py <run-id> --answer "직접 입력한 답변"
```

## 중간 체크포인트 계약

중간 체크포인트는 분석가가 실제로 일하는 순서를 반영한다. 데이터 구조를 본 뒤 질문을 조정하고, KPI·분모를 합의한 뒤 분석하고, 차트 구성안을 확인한 뒤 대시보드를 만들고, 최종 보고서 작성 전에는 독자·깊이·문체·결론 수위를 다시 확인한다.

| checkpoint_id | 위치 | 사용자가 확인할 것 | 통과 조건 |
|---|---|---|---|
| `data_profile` | `explore` 직후 | 데이터 범위·기간·grain·샘플·품질·분석 가능/불가능 범위 | `continue_with_current_data` 또는 free-text `--continue-pipeline` 답변 |
| `analysis_strategy` | `frame` 직후 | 핵심 질문, KPI, 분모, 비교축, 분석 전략, 분석 방향 선택지, 보고서 깊이 | `approve_strategy` 또는 free-text `--continue-pipeline` 답변 |
| `analysis_result_review` (조건부) | `analyze` 직후, `dashboard_storyboard` 앞 | 1차 발견이 목적과 맞는지, 심화 결과를 더 볼지 기본 분석으로 낮출지, 도메인 관점에서 해석이 타당한지, 결론 수위 | 결정적 술어 참인 run에서만 생성. `approve_analysis_result` 또는 free-text `--continue-pipeline` 답변 |
| `dashboard_storyboard` | `analyze` 직후(조건부 결과 검토가 있으면 그 다음) | 추천/대안 storyboard, chart_spec, 사용할 데이터/지표, 비교 기준, 추천 차트, 대안 차트, 디자인 프로필, 탭 흐름, 메시지, 배포용 표현 방향 | `approve_storyboard`/`approve_analyst_workspace`/`approve_operations_monitor` 또는 free-text `--continue-pipeline` 답변 |
| `report_outline` | `qa` 통과 직후, `communicate` 직전 | 보고서 독자, 깊이, 핵심 발견 흐름, 문체, 결론 수위, 피해야 할 표현 | `approve_report_outline` 또는 free-text `--continue-pipeline` 답변 |

체크포인트 파일은 `outputs/checkpoints/` 아래에 남긴다. `data_profile`은 가능한 경우 최대 20행 preview를 별도 파일로 만든다. connect 단계가 `outputs/data_preview.*`를 만들었다면 이 제한·비식별 preview를 우선 사용하고, 원천에서 직접 추출할 때도 상호·개체 ID·상세주소·건물·우편번호·층/호·전화·이메일·좌표처럼 개별 대상을 식별할 수 있는 컬럼은 제외한다. 데이터가 커도 전체를 보여주지 않고 sample preview, 01_profile, 02_eda를 함께 보여준다. 안전하게 보여줄 컬럼이 없거나 Parquet 샘플링 환경이 없으면 원천 preview를 만들지 않고 그 이유를 `data_snapshot.notes`에 남긴다.

각 체크포인트 JSON은 `user_review_brief`를 포함한다. 이 brief는 기술 산출물 목록보다 먼저 사용자에게 보여줄 요약이며, 다음을 쉬운 말로 설명한다.

- 이 단계가 왜 중요한지.
- 사용자가 무엇을 확인해야 하는지.
- 승인하면 다음에 무엇이 일어나는지.
- 이 단계에서 확정하지 않는 것은 무엇인지.
- 사용자가 답해야 할 승인 질문.

답변 helper:

```bash
python3 scripts/apply_checkpoint_answer.py <run-id> data_profile --option continue_with_current_data --source user_chat --user-response "<사용자 실제 답변>" --transcript-ref "<thread/message id>"
python3 scripts/apply_checkpoint_answer.py <run-id> analysis_strategy --option approve_strategy --source ask_user_question --user-response "<팝업 답변 원문>" --transcript-ref "<popup/message id>"
python3 scripts/apply_checkpoint_answer.py <run-id> dashboard_storyboard --option approve_storyboard --source user_chat --user-response "<사용자 실제 답변>" --transcript-ref "<thread/message id>"
python3 scripts/apply_checkpoint_answer.py <run-id> dashboard_storyboard --option approve_analyst_workspace --source user_chat --user-response "<사용자 실제 답변>" --transcript-ref "<thread/message id>"
python3 scripts/apply_checkpoint_answer.py <run-id> dashboard_storyboard --option approve_operations_monitor --source user_chat --user-response "<사용자 실제 답변>" --transcript-ref "<thread/message id>"
python3 scripts/apply_checkpoint_answer.py <run-id> report_outline --option approve_report_outline --source user_chat --user-response "<사용자 실제 답변>" --transcript-ref "<thread/message id>"
python3 scripts/apply_checkpoint_answer.py <run-id> data_profile --answer "이 기간만 보고 진행" --continue-pipeline --source user_chat --user-response "이 기간만 보고 진행" --transcript-ref "<thread/message id>"
```

### 인터뷰 라운드 (interview loop v2)

각 checkpoint는 승인 전 최대 2라운드의 탐색 문답을 가질 수 있다. 상세 계약은
`docs/specs/interview-loop-v2.md`가 단일 원천이다.

- 라운드 1 질문 파일은 기존 이름을 그대로 쓰고, 라운드 2는 같은 prefix에
  `.round2` 고정 접미사(`<NN>_<checkpoint>_question.round2.json|md`)를 쓴다.
  라운드 3 이상은 생성·승인 모두 차단된다. 유효한 라운드 2는
  `interview_loop.prior_round.question_sha256`이 현재 라운드 1 파일을 가리키는
  것뿐이며, 사이클당 1개 이하다(반려 후 라운드 1 재생성 시 이전 라운드 2는
  고아로 무시).
- 질문 JSON(스키마 v2)은 `interview_loop`(v2에서 필수), 정보 수집용
  `companion_questions`(최대 2개), data_profile 라운드 1의 `exploration`
  (탐색 방향 후보 참조)을 가질 수 있다. 문항 예산은 주 질문 1 +
  companion ≤2 = 라운드당 ≤3이고, 사용자 자유 질문은 라운드당 1개다.
- 진행을 결정하는 것은 주 질문 답변 하나뿐이다. companion 답변과 자유 질문
  (`loop_action=free_question`) 레코드는 어떤 경우에도
  `continue_pipeline=true`가 될 수 없다(불변식 I1) — helper·stage guard·QA가
  각각 강제한다. 진행 판정 입력은 canonical
  `runs/<run-id>/checkpoint_answers.json` 하나이며 `input/` mirror는 정합
  검사만 한다.
- 탐색 방향 후보와 미니 결과는 explore 에이전트 산출물
  `outputs/exploration_candidates.json`(스키마:
  `schemas/exploration_candidates.schema.json`)이며, gate는 계산하지 않고
  렌더만 한다.

`source`, `user_response`, `human_confirmed=true`가 없는 답변은 승인으로 인정하지 않는다. `continue_pipeline=false` 답변은 다음 단계 진행을 허용하지 않는다. 사용자가 "범위 수정", "데이터 보강", "차트 변경"을 선택하면 에이전트는 관련 입력이나 산출물을 수정한 뒤 다시 체크포인트 승인을 받아야 한다.

## 스키마로 강제 못 하는 것 → qa가 검사 (validate.py)

- **v5.1 opt-in 품질 계약**: `chart_spec.quality_contract.version = "v5.1"`과
  `dashboard_layout.quality_contract_version = "v5.1"`은 함께 선언한다. 계획
  단계에서 decision brief, metric role/lineage, 차트별 data sufficiency와
  visual contract를 검사하고, 실행 단계에서 문구 문맥, 척도, 색 외 구분 채널,
  빈 구성요소와 중복 질문을 검사한다.
- v5.1 browser QA는 1440×1000, 736×1000, 390×844, 320×800 네 화면에서
  console/network/accessibility, overflow, 빈 chart, label·legend·plot·canvas
  겹침/잘림, 11px 미만 필수 문구, tooltip viewport 이탈, 색만으로 구분한 계열을
  BLOCK한다.
- v5.1 숫자 표기는 금액·수량처럼 크기를 읽는 1,000 이상 측정값에 locale
  **천 단위 구분기호**를 요구한다. 구조화된 KPI·차트 라벨·분포 구간·표는 renderer가
  표시하고, 자유 문구의 `10970건`·`238228만원` 같은 표기는 static QA가
  BLOCK한다. 날짜·기간·코드·ID는 대상이 아니다.
- browser QA가 만든 `outputs/qa_render_desktop.png`,
  `outputs/qa_render_compact.png`, `outputs/qa_render_mobile.png`,
  `outputs/qa_render_narrow.png`를 오케스트레이터가 모두 직접 열어 본 뒤
  `outputs/visual_review.json`에 문구·위계·색·척도·라벨/범례·공백 관찰을 남긴다.
  레코드의 screenshot hash가 현재 파일과 다르거나 검사하지 않은 화면이 있거나
  `status=pass`가 아니면 fail-closed BLOCK한다. 에이전트나 테스트 성공을 실제
  눈검토로 대리하지 않는다.

- KPI/series `metric` 시드(v2 재현), 시뮬레이터 `test_cases` ≥1(죽은 시뮬 차단), `sources[].id` 유일성, `metric.source_ref` 실존, `x.values` 길이 = series 길이, chart type별 `stack` 허용값, `chart_spec.json` ↔ `dashboard_data.json` chart id 매핑, 렌더 후 시뮬레이터 실화면 값 일치, 모든 탭의 desktop·mobile 렌더에서 SVG blank·과대 크기·텍스트 겹침·텍스트 잘림.
- `chart_spec.json`의 각 차트는 가능하면 `chart_recommendation`을 포함한다. 없더라도 `dashboard_storyboard` checkpoint는 `data_requirements`, `chart.why_this_chart`, `insight.limit`로 사용자용 차트 추천표를 만들어야 한다.
- `chart_spec.json`은 가능하면 `dashboard_design.selected_profile`을 포함하고, `dashboard_data.json`은 `meta.dashboard_profile`에 최종 선택 프로필을 기록한다. 둘이 다를 경우 사용자 checkpoint 답변으로 설명 가능해야 하며, 설명 없이 불일치하면 QA에서 BLOCK한다. 공식 프로필은 `executive_brief`, `analyst_workspace`, `operations_monitor`이고 상세 기준은 `docs/dashboard-design-system.md`를 따른다.
- `report.depth=deep`일 때 `04_analysis.md`가 선택 전략·방법론·KPI·세그먼트/분포/관계/추세·한계·액션 기준·반대 해석·추천/대안 storyboard를 갖췄는지, `chart_spec.json`의 dashboard_story·질문별 insight·방법론/차트 유형 다양성이 데이터 구조에 비해 지나치게 단조롭지 않은지, post-communicate 검증에서 `deep_report.md`가 보고서 루브릭의 필수 구조를 갖추고 `04_analysis.md`의 단순 복사가 아닌지 검사한다.
- `source_api_manifest.json`이 있으면 schema, API 키 노출 여부, status, pagination, snapshot path·row_count·columns를 확인한다. `planned|smoke_tested` 상태로 dashboard/report가 생성되면 수집 전 출고로 보고 BLOCK한다. `blocked` 상태면 source blocker로 보고하고 대체 데이터를 꾸미지 않는다.
- 외부 context를 썼거나 기본 입력 데이터만으로 확정하기 어려운 수요·성과·비용·원인·추천 표현이 있으면, `source_ref`, 기준일, 분석 단위, join key, coverage 또는 결측률이 보고서와 lineage에 남아 있는지 확인한다. 외부 근거가 없는데 기본 건수·비율·집중도를 수요·성과·추천으로 표현하면 분석적 BLOCK 또는 사용자 보고 대상이다.
- 외부 context manifest가 있으면 schema, `source_ref` linkage, coverage 임계값, null rate, grain 품질 메모, 집계 기준, rank overflow 징후를 정적 QA에서 확인한다. 선택 품질 메타가 없는 기존 manifest는 호환하되 WARN으로 보강 필요성을 알린다.
- **대시보드 v4 표현 계약** (`docs/specs/dashboard-profile-v4.md`가 단일 원천):
  KPI `trend`·`comparison(kind=period_delta)`는 구조화 provenance(`source_id`가
  `sources[].id`, `time_field`, `periods` 오름차순)가 있을 때만 허용되고 QA가
  Decimal 공식으로 마지막 point↔value 정합을 검사한다. `kind` 없는 comparison은
  benchmark로 간주해 현행 렌더를 유지한다. 스몰 멀티플(`small_multiple_group`)·
  surface(primary/detail/appendix)·`table.cell_gradient`는 chart_spec 계획
  (`dashboard_design.contract_version`, `dashboard_mapping.surface/
  small_multiple_group/table_treatment`)에 먼저 기록되고 dashboard_data가
  이행해야 하며 QA가 일치를 검사한다. v4 레이아웃(analyst 단일 스크롤·
  operations 레일)은 `meta.dashboard_profile_contract: "v4"` opt-in일 때만
  활성화되고, 이 필드가 없는 기존 run은 렌더 화면이 현행과 동일해야 한다.
- **대시보드 v5 자유 레이아웃 계약** (`docs/specs/dashboard-freeform-v5.md`가
  단일 원천): chart/data contract가 모두 `v5`일 때만
  `dashboard_layout.json`을 받는다. layout은 12-column desktop 배치와 12-span
  mobile reading order, component role·kind·renderer·data_refs, 제한된
  interaction/render option만 선언한다. chart는 로컬 ECharts 6.1.0 canvas,
  header·KPI·insight·table·source·control은 canonical SVG/CSS runtime이 맡는다.
  storyboard 질문을 만들기 전에 layout schema·위계와 상태형 interaction의
  visible control/reset 연결을 검사하며 issue가 있으면 승인 질문 자체를 만들지
  않는다. storyboard 승인의 layout hash/revision과 현재 파일이 다르면 재승인 전
  BLOCK한다. QA에서 구조 변경이 필요해진 경우 기존 승인 답변은 이력으로 보존하고,
  layout revision을 올린 뒤 기존 질문·답변 hash에 연결된 immutable round 2
  `artifact_revision` 질문으로 새 hash를 실제 사용자에게 다시 승인받는다.
  compiler는 고정 template·bundle checksum과 세 입력 hash를 manifest에 남기며,
  CDN·원격 font·raw code·raw ECharts option을 허용하지 않는다. 상태가 바뀌는
  legend/zoom/local filter는 연결된 visible control과 reset이 있어야 한다.
  v5 layout 누락·invalid·compile/browser 오류는 legacy/v4로 fallback하지 않는다.

## run 레이아웃

```
runs/<run-id>/
├── input/                 # (파일 소스 시) 원본
├── input/source_api_manifest.json # (선택) primary API 수집 계획
├── input/domain_pack_ref.txt # (선택) domain pack 참조
├── input/domain_pack_context.md # (선택) wrapper가 만든 domain pack prompt context
├── input/domain_intake.json  # (domain mode) 도메인 전문가 intake + readiness
├── input/domain_knowledge_brief.md # (domain mode, 선택) 사용자용 도메인 이해 요약
├── input/dependency_plan.json # (심화 route) preflight 결과 + 승인 + install_result
├── input/external_adapter_plan.json # guided intake adapter 선택 정책
├── input/checkpoint_answers.json # 중간 사용자 체크포인트 답변 mirror
├── intermediate/          # Parquet 중간산출 (gitignore)
├── domain_pack_context.md # (선택) 위 context의 canonical copy
├── external_adapter_plan.json # 위 plan의 canonical copy
├── external_denominators.json # (선택) 외부 context adapter manifest
├── checkpoint_answers.json # 중간 사용자 체크포인트 답변 원본
├── outputs/               # 01_profile.md, 02_eda.md, 03_frame.md, 04_analysis.md,
│                          # method_route.json (분석 깊이 route canonical)
│                          # chart_spec.json, 선택 dashboard_layout.json (v5)
│                          # dashboard_data.json, dashboard.html,
│                          # 선택 dashboard_build_manifest.json (v5), summary_report.md
│                          # chart_spec.json
│                          # deep_report.md, external_context.md (선택)
│                          # domain_pack_update_candidates.md (domain mode, 선택)
│   └── checkpoints/        # data preview, checkpoint question json/md
└── manifest.json          # run_id·created_at·intake·sources[]·stages[]·artifacts[]·qa
```

`runs/*`는 `.gitignore`에 의해 로컬 전용이다. 배포용 core에 과거 분석 산출물이나
사용자별 run을 넣지 않는다. 예제 데이터가 꼭 필요하면 `runs/`가 아니라 별도
fixture/example package로 분리하고, 포함 이유와 비밀정보 검사를 문서화한다.

## 입력 소스 계약

공식 입력은 "사용자가 가진 원천"과 "파이프라인이 반복해서 읽는 표준 입력"을 분리한다.

| adapter | 사용자 원천 | 파이프라인 입력 | 원칙 |
|---|---|---|---|
| `local_file` | CSV, Parquet, Excel, JSON | `runs/<run-id>/input/` | 가장 기본 경로. 사용자는 DB 없이 파일만 넣어도 된다. |
| `primary_api` | 공공데이터·OpenAPI URL 또는 API 문서 페이지 | `input/source_api_manifest.json` → `input/*.parquet|csv|jsonl` 스냅샷 | API URL만 준 요청의 주 입력. connect가 endpoint/auth/pagination smoke test 후 스냅샷으로 고정한다. 키 값은 산출물에 남기지 않는다. |
| `remote_parquet` | `hf://`, `https://`, `s3://` 등 Parquet | 축약 Parquet 스냅샷 | 전체 다운로드 금지. projection/filter/층화 샘플링/limit 후 로컬 스냅샷을 만든다. rate limit 원격 소스는 candidate pool 안에서 검증 스냅샷을 만들 수 있다. |
| `duckdb` | 기존 DuckDB 분석 DB | `connectors/.env`의 `DIK_DUCKDB_PATH` | 고급/대용량/SQL 중심 사용자용. read-only SELECT/WITH만 허용한다. |

반복 실행과 QA 재현성은 로컬에 고정된 입력을 기준으로 한다. 따라서 API/원격 데이터는 먼저 `input/*.parquet|csv|jsonl` 스냅샷으로 물리화하고, 원천 URL·조회 시점·endpoint·컬럼·행 수·pagination·샘플링 방식·candidate 사용 여부를 `manifest.sources[]`, `source_api_manifest.json`, 또는 별도 snapshot manifest에 남긴다.

## 코어 산출물 (런타임 무관, 양 어댑터 공유)

- `schemas/dashboard_data.schema.json` — 데이터 계약 (canonical)
- `schemas/chart_spec.schema.json` — 질문·방법론·계산·차트 선택 중간 계약
- `schemas/report_config.schema.json` — 보고서 깊이·독자·근거 범위 선택 계약
- `schemas/method_route.schema.json` — 분석 깊이 route·method·강등 기록 계약
- `schemas/dependency_plan.schema.json` — dependency preflight·승인·설치 결과 계약
- `schemas/domain_intake.schema.json` — 도메인 전문가 intake·readiness 계약
- `methods/method_registry.json` — route별 허용 method·전제 조건·금지 결론 registry
- `scripts/dependency_preflight.py` — kit 전용 `.venv` 기준 설치 여부 판정과 dependency_plan 작성 (설치는 승인 후에만)
- `schemas/external_denominator_manifest.schema.json` — 선택 외부 context adapter 계약
- `schemas/external_adapter_plan.schema.json` — guided intake adapter 선택 정책 계약
- `docs/analysis-strategy-library.md` — 데이터 형태별 심층 분석 전략 기준
- `docs/external-denominator-adapters.md` — 외부 context adapter 계약과 lineage 기준
- `docs/external-adapter-registry.md` — 외부 adapter category별 metric layer, 허용/금지 해석, QA 기준
- `docs/user-facing-planning.md` — 사용자용 분석 기획안과 내부 실행 계획 분리 기준
- `docs/report-quality-rubric.md` — summary/deep 보고서 품질 기준과 QA 루브릭
- `connectors/source.py` — read-only DuckDB 어댑터 (+ →Polars)
- `scripts/snapshot_remote_parquet.py` — 원격 Parquet를 projection/limit/층화 샘플링/candidate pool 가능한 bounded local snapshot으로 물리화
- `scripts/prepare_primary_api_source.py` — 사용자 요청의 API URL을 `source_api_manifest.json`으로 정규화하고 connect 단계에 primary API 수집 계획을 전달
- `scripts/external_adapter_utils.py` — 외부 context adapter의 paged API 수집, coverage audit, manifest 작성, signed rank shift helper
- `scripts/prepare_external_adapter_plan.py` — `intake.external_adapters`를 core stage가 읽는 `external_adapter_plan.json`으로 정규화하고, 필요한 경우 adapter 선택 질문으로 중단
- `qa/validate.py` — 출고 게이트 (정적 + 렌더 검증)
- `templates/dashboard.html` — 데이터 주입형 렌더러
- `themes/{light,dark}.json` — role→색 매핑
