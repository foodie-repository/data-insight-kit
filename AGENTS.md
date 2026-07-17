# AGENTS.md — data-insight-kit (공유 운영 지침)

이 저장소는 표 데이터 소스(로컬 파일·원격 Parquet·선택 DuckDB·API 스냅샷)를 받아 8개 stage와 사용자 확인 checkpoint로 분석하고 데이터 주입형 대시보드를 만드는 키트다.
**단일 원천은 `docs/pipeline-contract.md`** 이다. 이 파일(AGENTS.md)은 실행기가 아니라 Codex와 Claude Code 어댑터가 공통으로 따라야 할 운영 규칙이다.

## 문서 역할
- `README.md`는 배포용 첫 진입점이다. 설치와 준비, 빠른 시작, 주요 문서 위치를 사용자 관점에서 짧게 안내한다.
- `GUIDE.md`는 처음 사용하는 사람이 설치부터 첫 실행, checkpoint 답변, QA까지 따라 하는 튜토리얼이다.
- `CUSTOMIZATION.md`와 `domains/README.md`는 회사·업무 도메인에 맞게 domain pack을 확장하는 사용자 문서다.
- `docs/pipeline-contract.md`는 stage, checkpoint, I/O, QA의 단일 기준이다. 구현·에이전트·문서가 충돌하면 이 문서를 우선한다.
- `docs/agent-guide/`는 에이전트 역할과 파이프라인 구조를 설명하는 보조 자료다. 실행 계약을 새로 정의하지 않는다.
- `docs/dashboard-design-system.md`, `docs/analysis-strategy-library.md`, `docs/report-quality-rubric.md`, `docs/source-adapters.md`는 각각 대시보드 표현, 분석 전략, 보고서 품질, 입력 소스 계약을 보강하는 기준문서다.
- `CLAUDE.md`는 Claude Code가 이 운영 규칙과 pipeline contract를 찾기 위한 얇은 redirect 문서다. 규칙을 중복해서 복제하지 않는다.

## 파이프라인 계약
- 단계는 반드시 이 순서로만: `intake → connect → explore → data_profile checkpoint → frame → analysis_strategy checkpoint → analyze → dashboard_storyboard checkpoint → visualize → qa(gate) → report_outline checkpoint → communicate`. wrapper/adapter는 communicate 이후 `qa-post`를 추가 실행해 보고서 깊이 계약을 확인한다.
- 각 단계의 상세 사양·입출력은 `docs/pipeline-contract.md` 와 `agents/<stage>.md`(상단 Claude frontmatter는 무시) 를 따른다. 단계 정의를 새로 만들지 않는다.
- **결정적 코어 우선**: 스크립트·스키마 검증 결과가 LLM 판단을 이긴다.
  - 기본 입력은 `runs/<run-id>/input/`의 CSV·Parquet·Excel·JSON, API 수집 계획(`source_api_manifest.json`), 또는 축약 Parquet 스냅샷이다.
  - DB 접근은 선택 경로이며 `connectors/source.py` 경유만 허용한다(read-only·SELECT/WITH 전용).
  - 원격 Parquet는 전체 다운로드하지 말고 projection/filter/층화 샘플링/limit 후 로컬 스냅샷으로 고정한다.
- `runs/*`는 사용자별 로컬 산출물이며 배포용 core에 포함하지 않는다. 예시·검증이 필요하면 새 run을 만들되, tracked baseline으로 다시 추가하지 않는다. 재현 가능한 fixture가 필요하면 `tests/fixtures/` 또는 별도 example package를 명시적으로 설계한다.
- 새 run의 기본값은 **fresh analysis**다. 기존 `runs/*`, 이전 `dashboard_data.json`, 이전 `chart_spec.json`, 이전 보고서, 과거 run-local builder 결과는 사용자가 명시적으로 "참고/비교/수정/이어받기"를 요청한 경우에만 입력이나 근거로 쓴다. wrapper는 `runs/<run-id>/input/run_context.json`에 이 정책을 남기고, QA는 fresh mode에서 과거 run 경로가 산출물에 섞이면 BLOCK한다.
- `chart_spec.json` 은 `schemas/chart_spec.schema.json` 을 통과해야 한다. 범용 데이터에서는 질문→방법론→계산→차트 선택을 먼저 고정하고, `dashboard_data.json` 은 그 계획을 이행한다.
- 심층 분석은 `docs/analysis-strategy-library.md`를 기준으로 데이터 형태별 주 전략과 보조 전략을 고른다. 단순 상위 N개·건수·비율 반복은 deep 분석으로 보지 않는다.
- Plan Mode 또는 guided intake에서 사용자에게 보여주는 계획은 `docs/user-facing-planning.md`를 따른다. 항상 **사용자용 분석 기획안**을 먼저 쓰고, run-id·endpoint·pagination·QA 명령 같은 **내부 실행 계획**은 뒤쪽 기술 부록으로 분리한다. 사용자가 명시적으로 요구하지 않으면 내부 실행 계획은 5개 안팎의 짧은 요약만 보여준다. 초보자가 "내가 원하는 분석이 맞는지" 판단할 수 없는 기술 중심 계획은 실패로 본다. 새 스레드의 첫 계획이 `Summary`, `Key Changes`, `Pipeline`, `Test Plan`, `Assumptions`로 시작하면 data-insight-kit 계획으로 보지 않고, `이번 분석은 이렇게 진행합니다` 형식의 사용자용 기획안으로 다시 작성한다.
- frame은 분석 방향 선택지 2~3개를 제안해야 하고, analyze는 추천 storyboard와 대안 storyboard를 만들어야 한다. 사용자가 승인하기 전에는 단순 ranking 중심 구성으로 고정하지 않는다.
- chart_spec의 각 차트는 서로 다른 질문에 답해야 하며 `insight.finding/evidence/limit`가 대시보드 설명과 보고서 핵심 발견으로 이어져야 한다. 차트 목록이나 상위 N개 반복은 대시보드 품질로 보지 않는다.
- `dashboard_storyboard` 체크포인트는 사용자에게 차트 추천표와 대시보드 디자인 프로필 선택지를 함께 보여줘야 한다. 각 차트 추천 행에는 사용할 데이터/지표, 비교 기준, 추천 차트, 추천 이유, 대안 차트, 대안을 제외하거나 보류한 이유가 있어야 한다. 디자인 프로필은 `executive_brief`, `analyst_workspace`, `operations_monitor` 중 목적에 맞는 추천안과 대안을 제시하고, 선택 결과를 `chart_spec.dashboard_design` 및 `dashboard_data.meta.dashboard_profile`로 이어간다. `chart_spec`에는 가능하면 `chart_recommendation`을 채운다.
- 입력 데이터만으로 결론을 확정하기 어려운 분석은 `docs/external-denominator-adapters.md`, `docs/external-adapter-registry.md`, `schemas/external_denominator_manifest.schema.json`을 선택 계약으로 사용한다. 외부 데이터가 없으면 기본 데이터의 건수·비율·집중도·순위를 수요·성과·원인·추천으로 재명명하지 않는다.
  반복 adapter 구현은 `scripts/external_adapter_utils.py`의 paged API, coverage, manifest, signed rank shift helper를 우선 사용하고, run-local script에는 원천별 해석과 계산만 둔다.
- 회사·업무 도메인 기준이 필요하면 `domains/<domain>/domain.yaml`을 선택한다. 실행자는 `DIK_DOMAIN_PACK=domains/<domain>/domain.yaml` 또는 `runs/<run-id>/input/domain_pack_ref.txt`로 지정하고, wrapper가 만든 `input/domain_pack_context.md`를 이후 stage에서 참고한다. domain pack은 질문·KPI 후보·금지 표현·차트/보고서 패턴을 보조하지만 core 계약, 스키마, QA를 대체하지 않는다. domain pack 내용이 결론을 바꾸는 경우에도 사용자는 checkpoint에서 승인해야 한다.
- 보고서는 `schemas/report_config.schema.json` 계약의 `depth`, `audience`, `evidence_scope`를 분리해 따른다. 기본 산출물은 `summary_report.md`이며, "임원용"은 기본값이 아니라 `audience=executive` 옵션이다.
- 의사결정형 guided run에서 사용자가 심층 검토를 원하거나 결과가 실제 선택에 쓰이면 `report.depth=deep`, `audience=mixed`, `evidence_scope=data_only`를 추천할 수 있다. 사용자용 문장에서는 이를 "요약 보고서와 심층 검토 보고서, 데이터 근거만 사용"으로 풀어 쓴다.
- 보고서 품질은 `docs/report-quality-rubric.md`를 기준으로 한다. `summary_report.md`는 빠른 판단용 요약이고, `deep_report.md`는 방법론·KPI·세그먼트·반대 해석·한계·액션 기준·lineage를 갖춘 검토 문서다.
- 목적·의사결정·성공기준이 모호하면 intake에서 AskUserQuestion형 질문을 사용한다. 한 번에 하나의 핵심 불확실성만 묻고, 질문은 "현재 이해 / 막힌 결정 / 추천 답안 / 질문" 구조를 따른다. deep-interview 원칙에 따라 답변은 먼저 `intake_draft.yaml`에 누적하고, 최대 3문항 안에서 충분해졌을 때만 최종 `intake.yaml`을 확정한다. non-interactive에서 너무 모호하면 `outputs/intake_questions.md`와 상위 UI handoff용 `outputs/intake_questions.json`을 남기고 중단한다. 질문형 intake 자체를 검증할 때는 `--guided-intake`를 사용하며, 이 모드에서는 명확한 요청이어도 최소 1회 draft를 경유하고 최종 intake에 `finalization.finalized_by: guided_intake`를 남긴다.
- `outputs/intake_questions.json`에는 `user_analysis_brief`를 포함한다. 이 brief는 한 줄 목적, 답할 질문, 데이터로 가능한 판단, 데이터만으로 판단하지 않을 것, 분석 방향 선택지, 중간 확인 시점, 실행 전 준비사항, 승인 선택지, 승인 질문을 쉬운 말로 담아야 한다. `답할 질문`에는 사용자의 업무/판단 질문만 넣고, 단순 Top-N 금지, 차트 다양성, schema/QA 같은 내부 품질 기준은 내부 실행 계획이나 QA 기준으로 보낸다.
  - 사용자용 brief와 checkpoint review에는 `data_profile`, `analysis_strategy`, `dashboard_storyboard`, `report_outline`, `source_api_manifest`, `checkpoint_question`, `qa/validate.py`, 내부 지표명, 내부 스키마명, 대화 이력 관리 문구를 쓰지 않는다. 필요한 경우 "데이터 확인 단계", "분석 방향 확인 단계", "대시보드 구성안 확인 단계", "보고서 구성안 확인 단계", "상대적으로 두드러지는 대상", "추가로 확인할 대상"처럼 일반 명사로 바꾼다.
  - 승인 질문은 "실행을 시작하면..."처럼 시스템 동작을 설명하지 말고, "이 범위로 먼저 데이터 확인 단계부터 시작할까요, 아니면 분석 대상·범위를 바꿀까요?"처럼 사용자가 바로 답할 수 있는 선택 질문으로 쓴다.
- intake 이후에도 사용자 확인 없이 끝까지 밀어붙이지 않는다. wrapper/adapter의 기본값은 중간 체크포인트 ON이다. `explore` 후에는 `data_profile`, `frame` 후에는 `analysis_strategy`, `analyze` 후에는 `dashboard_storyboard`, `qa` 통과 후에는 `report_outline` 질문을 `outputs/checkpoints/`에 만들고 멈춘다. 정지 강제 방식은 실행기마다 다르다: Codex CLI wrapper는 `checkpoint_gate.py`의 exit code `3`으로, Claude Code plugin은 `hooks/hooks.json`의 PreToolUse 훅(`scripts/dik_checkpoint_hook.py`)이 승인 없는 다음 stage 산출물 쓰기를 deny해서 멈춘다. Plan Mode 승인은 파이프라인 전체 자동 실행 허가가 아니다 — 승인 이후에도 각 checkpoint에서 실제로 멈추고 다시 물어야 한다. 각 checkpoint 질문은 deep-interview 형식의 `chat_prompt`와 초보자용 `user_review_brief`를 포함해야 하며, 형식은 반드시 "현재 이해 / 확인할 내용 / 막힌 결정 / 추천 답안 / 질문"이다. 상위 에이전트는 파일 목록, 산출물 요약, 실행 로그보다 이 요약과 선택지를 먼저 채팅창에 제시하고, 사용자의 자유 답변 또는 선택지를 `scripts/apply_checkpoint_answer.py`로 `checkpoint_answers.json`에 누적한다. 승인 요청 시 표시 의무: 자체 요약만으로 승인을 받지 않는다 — 질문 md 원문 경로(클릭 가능 링크), `data_profile`의 실제 데이터 샘플(`data_snapshot.sample_preview_path` 내용), 질문 JSON의 `artifacts[]` 근거 파일 링크를 반드시 함께 제시한다. 요약은 보조이며 원문을 대체할 수 없다. 필요한 경우 `python3 scripts/checkpoint_gate.py <run-id> <checkpoint-id> --print-existing`으로 기존 질문 파일을 채팅용 handoff로 다시 출력한다.
  - 탐색 문답(interview loop v2, 단일 원천 `docs/specs/interview-loop-v2.md`): 각 checkpoint는 승인 전 최대 2라운드 문답을 가진다. 사용자가 방향 선택지(데이터 확인 단계)나 자유 질문을 고르면 gate가 같은 prefix에 `.round2` 접미사가 붙은 라운드 2 질문을 만든다(라운드 3은 없음, `--print-existing`은 라운드 2 우선). 자유 질문은 라운드당 1개 — `apply_checkpoint_answer.py --free-question "<질문>"`으로 **먼저 기록**한 뒤 이번 run input 한정 조회·집계로 답을 계산하고 `scripts/record_free_question_result.py`로 결과 쌍을 남긴다(순서 위반·직접 인용은 QA가 잡는다). companion(추가 확인 질문) 답변은 `--companion <id>`로 기록한다. 방향 선택·자유 질문·companion 레코드는 어떤 경우에도 진행을 결정하지 않는다(불변식 I1) — 진행은 주 질문 승인 답변 하나로만 결정된다. domain mode에서는 답변이 쌓이면 `scripts/build_domain_intake.py`로 도메인 확인 정보를 파생 생성한다(수동 파일 우선). 표시 의무는 라운드 2 질문·미니 결과 파일에도 동일하게 적용하며, **링크와 팝업 미리보기는 "보여준 것"이 아니다**: 데이터 샘플·미리 본 결과의 '내용'을 채팅 본문에 표 그대로 출력한 뒤 선택을 받고, 팝업/선택 UI는 선택 수집용으로만 쓴다(preview 렌더는 환경에 따라 보이지 않음 — smoke 검증에서 확인). gate의 `--print-existing` 핸드오프가 근거 원문을 내장하므로 그것을 그대로 출력하는 것이 기본이다. **전달 순서(턴 분리)**: 근거 출력과 선택 수집을 같은 턴에 두지 않는다 — 같은 턴에 본문+선택 팝업을 함께 보내면 팝업이 먼저 렌더되어 사용자가 근거를 읽기 전에 선택을 요구받는다(v4 smoke 발견). 근거 본문으로 턴을 끝내고, 사용자가 읽은 뒤 다음 턴에서 선택을 받는다(팝업 또는 채팅 답변 — 채팅 답변도 `--source user_chat`으로 동일하게 기록). **대시보드 눈검토 의무**: 대시보드가 생성·수정된 정지점을 사용자에게 전달하기 전에, 오케스트레이터는 qa가 남긴 모든 렌더 스크린샷을 **직접 열어 보고** 관찰 결과(문구·위계·색·척도·라벨/범례·공백·겹침·잘림)를 보고와 함께 전달한다. v5.1은 `outputs/qa_render_desktop.png`·`outputs/qa_render_compact.png`·`outputs/qa_render_mobile.png`·`outputs/qa_render_narrow.png` 네 장 모두가 대상이다. `outputs/visual_review.json`은 오케스트레이터의 실제 관찰, 네 screenshot hash, `status=pass`를 가져야 하며 hash가 달라지거나 `revise`이면 checkpoint 전달을 차단한다. 테스트나 에이전트가 눈검토를 대리할 수 없다 — 기계 검사는 프로그램된 항목만 잡으므로 QA 통과가 "화면이 멀쩡하다"를 뜻하지 않는다(v4 smoke에서 카드 겹침이 QA를 통과한 실사례). **채팅 전달 규칙(원문 우선 + 보강)**: 질문·선택지 문구는 질문 파일의 원문 그대로 옮긴다(재작성 금지). 보강은 그 아래에만 허용한다 — 근거 표의 마크다운 렌더, 원문 파일 링크, "읽는 법" 해설. 질문 md는 채팅과 동일한 완결성을 가진다(근거 원문·추가 확인 질문·직접 질문 안내 내장) — md만 열어도 같은 결정을 내릴 수 있어야 한다.
  - 승인 답변은 반드시 실제 사용자 답변을 포함해야 한다. 명령에는 `--source user_chat|ask_user_question|manual_cli`와 `--user-response "<사용자 실제 답변>"`가 필요하다. `user_chat` 또는 `ask_user_question` 답변은 `--transcript-ref "<thread/message id>"`도 필요하다. Plan Mode의 `PLEASE IMPLEMENT THIS PLAN` 또는 에이전트 추천 답안을 checkpoint별 승인 문구로 쪼개 기록하지 않는다.
  - 에이전트가 질문 파일의 추천 답안이나 기존 계획을 근거로 스스로 `continue_pipeline=true` 답변을 만들면 승인으로 인정하지 않는다. `source=agent_assumption`은 메모만 가능하며 다음 단계 진행을 허용하지 않는다.
  - 최신 답변이 `continue_pipeline=false`이면 관련 산출물을 수정하고 다시 승인받기 전까지 다음 단계로 진행하지 않는다. 완전 자동 실행은 사용자가 명시적으로 `--auto` 또는 `--no-checkpoints`를 선택한 경우만 허용한다.
  - `checkpoint_answers.json`은 `scripts/apply_checkpoint_answer.py`로만 생성·수정한다. 답변은 `approval_contract_version=checkpoint-answer.v3`, `recorded_by=scripts/apply_checkpoint_answer.py`, `answer_id`, `question_ref.path`, `question_ref.sha256`, `question_ref.created_at`, `answered_at`을 포함해야 한다. QA는 downstream 산출물이 해당 checkpoint 승인보다 먼저 만들어졌으면 공식 완료로 인정하지 않는다.
  - `scripts/stage_guard.py`는 `frame`, `analyze`, `visualize`, `qa`, `communicate` 진입 전에 필요한 이전 checkpoint의 v3 승인 provenance를 검사한다. 승인 증거가 없거나 질문 파일 hash와 맞지 않으면 다음 stage를 시작하지 않는다.
  - 모델이 직접 오케스트레이션하는 실행기(Claude Code plugin, 자연어로 구동하는 Codex Desktop)에서는 래퍼의 exit 3 루프가 돌지 않으므로, PreToolUse 훅(`scripts/dik_checkpoint_hook.py`)이 같은 `stage_guard` 검증을 결정적으로 강제한다. 승인 provenance가 없으면 `03_frame.md`, `04_analysis.md`, `chart_spec.json`, `dashboard_data.json`, `dashboard.html`, `summary_report.md`, `deep_report.md` 쓰기(Claude=`Write/Edit`, Codex=`apply_patch`)와 run-local builder 실행을 deny한다. 훅은 서브에이전트 도구 호출에도 발동하며, checkpoint/intake 질문 파일에 내부 용어가 노출되면 배포용 언어 게이트로도 deny한다. 한 스크립트가 두 런타임 deny 계약(`hookSpecificOutput.permissionDecision=deny`)을 공유한다.
    - Claude Code: `hooks/hooks.json`(matcher `Write|Edit|Bash`). plugin에 포함되므로 설치 후 `/reload-plugins` 또는 재시작해야 활성.
    - Codex: `.codex/hooks.json`(matcher `apply_patch|Bash`). 프로젝트 `.codex/` 훅이라 처음 한 번 Codex `/hooks`에서 신뢰(trust)해야 활성화되고, 훅 파일이 바뀌면 다시 신뢰해야 한다. 스크립트 경로는 git root 기준으로 해석하며 못 찾으면 fail-open(허용)이다.
  - `checkpoint_gate.py`도 `stage_guard.validate_answer`를 재사용해 v3 provenance를 검사한다. provenance 없는 자작 답변은 이제 checkpoint gate 자체에서 거부된다(과거에는 `is_human_confirmed`만 봐서 통과했다).
  - `qa/validate.py`는 최종 산출물에서 checkpoint lineage도 검사한다. `outputs/checkpoints/*_question.json|md`와 v3 provenance가 있는 실제 사용자 승인 증거가 없으면 수동 builder로 만든 `dashboard_data.json`이라도 출고 BLOCK이다. 자동 실행은 wrapper가 `input/checkpoint_policy.json`에 `mode=auto`, `explicit_skip=true`를 남긴 경우에만 예외다.
  - run-local builder는 wrapper 장애 진단·초안 산출·입력 정규화 보조에는 쓸 수 있지만, 사용자 checkpoint 승인 없이 `03_frame.md`, `04_analysis.md`, `chart_spec.json`, `dashboard_data.json`, `summary_report.md`, `deep_report.md`를 공식 완료 산출물로 만들거나 checkpoint 답변을 직접 쓰면 안 된다.
- `data_profile` 체크포인트에서는 가능한 경우 원본 파일에서 최대 20행 preview를 만들고, 불가능하면 profile/EDA 요약과 샘플링 불가 사유를 보여준다. 대용량 원본 전체를 열거나 복사하지 않는다.
- 사용자가 API URL만 주면 wrapper는 `scripts/prepare_primary_api_source.py`로 `input/source_api_manifest.json`을 만들고 connect 단계에 전달한다. connect는 endpoint/auth/pagination smoke test 후 `input/*.parquet|csv|jsonl` 스냅샷을 고정해야 한다. API 수집이 막히면 대체 데이터를 꾸미지 말고 source blocker로 중단한다.
- `analysis_strategy` 체크포인트는 KPI, 분모, 비교 기준, 분석 질문을 사용자가 승인하는 게 목적이다. 내부 분석 용어가 과하거나 사용자의 의도와 어긋나면 frame을 수정하고 재확인한다.
- `dashboard_storyboard` 체크포인트는 추천/대안 storyboard, 차트 추천표, 디자인 프로필, chart_spec, 탭 흐름, 차트 유형, 배포용 표현 방향을 사용자가 승인하는 게 목적이다. 승인 전에는 `dashboard_data.json`을 만들지 않는다. 단순 순위·요약만 반복되거나 "어떤 데이터로 왜 이 차트를 쓰는지"가 불명확하거나 선택한 디자인 프로필과 차트 밀도가 맞지 않으면 `deepen_chart_story` 또는 `revise_chart_mix`로 돌아가 차트와 인사이트를 다시 설계한다.
- `report_outline` 체크포인트는 대시보드 QA가 통과한 뒤 최종 보고서의 독자, 깊이, 핵심 발견 순서, 문체, 결론 수위, 피해야 할 표현을 사용자가 승인하는 게 목적이다. 승인 전에는 `summary_report.md`와 `deep_report.md`를 만들지 않는다.
- 대시보드와 보고서는 기본적으로 배포용 독자 언어로 작성한다. `proxy`, `layer`, `grain`, `chart_spec`, `source_ref`, 원천 컬럼명, 코드값, 내부 지표명 같은 분석·구현 용어는 제목·KPI·축·요약 도입부에 노출하지 않는다. 필요하면 방법론 또는 부록에서 풀어쓴다.
- 외부 데이터나 도메인별 보정 지표가 결론 품질을 크게 바꾸는 요청이면 guided intake에서 `external_adapter_policy` 질문을 사용할 수 있다. 답변은 `intake.external_adapters`에 `selected_categories`, `unavailable_categories`, `interpretation_guards`, `registry_ref`로 남기고 실제 수집 가능 여부는 connect 단계에서 판정한다.
- wrapper/adapter는 최종 또는 draft intake의 `external_adapters`를 `input/external_adapter_plan.json`과 `external_adapter_plan.json`으로 정규화한다. 이 plan은 사용자 선택 정책이며 실제 외부 데이터 lineage가 아니다. 실제 외부 데이터가 있으면 `input/external_denominator_manifest.json` 또는 `external_denominators.json`이 별도로 있어야 한다.
- AI 앱에서 사용자가 짧게 실행을 요청하면 먼저 계획/승인 흐름을 사용한다. Codex Desktop과 Claude Code 모두 Plan Mode에서 사용자용 분석 기획안과 실행 계획을 먼저 확인하고, 승인 후에 실행한다. Codex CLI wrapper는 `--guided-intake` handoff를 사용하고, Claude Code plugin은 `/run-pipeline` 실행 전후로 동일한 사용자 확인 원칙을 따른다. `outputs/intake_questions.json`이 생성되면 그 내용을 선택지 UI 또는 채팅 질문으로 묻고, 답변은 `python3 scripts/apply_intake_answer.py <run-id> --option <option-id>` 또는 `--answer "<직접 답변>"`으로 `intake_draft.yaml`에 누적한다. 팝업/채팅 답변을 바로 `intake.yaml`로 쓰지 않는다. 질문이 더 필요하면 같은 흐름을 반복하고, 충분해졌을 때만 intake 단계가 최종 `intake.yaml`을 만든다.
- 새 스레드에서 같은 데이터를 다시 분석하는 요청은 기본적으로 "새 분석"으로 해석한다. 이전 결과를 일부 수정하거나 비교하려면 사용자가 "이전 run을 참고", "기존 대시보드 수정", "지난 분석과 비교"처럼 명시해야 하며, 그때도 참조한 run id를 `run_context.reference_runs`에 남긴다.
- `dashboard_data.json` 은 `schemas/dashboard_data.schema.json` 을 통과해야 한다.
  - 출고 게이트는 `python qa/validate.py <dashboard_data.json> --chart-spec <chart_spec.json>` — BLOCK이면 통과 금지.
  - communicate 이후 게이트는 `python qa/validate.py <dashboard_data.json> --chart-spec <chart_spec.json> --no-render --post-communicate` — `depth=deep`인데 `deep_report.md`가 얕거나 `04_analysis.md` 복사본이면 BLOCK.
- 쓰기는 `runs/<run-id>/` 안에만. 원격 URI·조회일·row count·schema 요약·샘플링 방식은 manifest에 남기되, DB 경로·자격은 `.env`(커밋 금지), 로그·산출물에 남기지 않는다.

## Expert-guided analysis routing (v1)
- `method_route.json`은 frame 단계의 필수 산출물이다(`methods/method_registry.json` 기준으로 route와 selected_methods를 고른다). frame이 이 파일 없이 완료됐다고 보지 않는다.
- 추가 분석 기능(`stats`/`ml` extra) 설치는 사용자가 `analysis_strategy` checkpoint에서 명시 옵션으로 승인한 뒤 `scripts/dependency_preflight.py --apply-approval`(wrapper가 자동 호출)만 실행한다. 에이전트가 직접 `pip install`/`uv add`/`uv sync --extra`를 실행하지 않는다 — `dik_checkpoint_hook.py`가 승인 provenance 없는 설치 명령을 deny한다.
- `analysis_result_review` 조건부 게이트는 spec §9의 결정적 술어(route/domain_mode/report.depth/analysis_mode)를 stage_guard와 QA가 각자 재계산해서 발동 여부를 정한다. `method_route.json`에 기록된 `review_predicate`나 에이전트가 남긴 플래그는 provenance일 뿐 판정 근거가 아니다 — 플래그 값을 신뢰하거나 그것만으로 게이트를 건너뛰지 않는다.
- `domains/<name>/`는 자동 수정 금지다. 이번 run에서 나온 도메인 지식 후보는 `outputs/domain_pack_update_candidates.md`에 후보로만 남기고 domain pack 파일을 직접 고치지 않는다.
- route/dependency 강등(하향)은 `downgrade_reason` 기록만으로 허용하지만, 승인 시점 이후 route 상향이나 dependency 확장은 `analysis_strategy` 재승인이 필요하다 — `approval_targets`의 sha256 잠금을 우회해 조용히 상향하지 않는다.

## 권장 Codex/OpenAI model+effort (단계별)
실제 모델과 effort는 wrapper(`scripts/run_codex_pipeline.sh`)의 `codex exec` 옵션이 부여한다. 단일 원천은 `docs/model-tier-map.md`다.
- 기본 모델: `gpt-5.5` (`DIK_MODEL` 로 override 가능)
- `intake`, `qa`: `gpt-5.5` + **low** (budget 대안: `gpt-5.4-mini` + low)
- `connect`, `visualize`, `communicate`: `gpt-5.5` + **medium**
- `explore`, `frame`, `analyze`: `gpt-5.5` + **high** (모호·고위험 시 xhigh)

가용 모델·effort는 `codex debug models` 로 확인한다(사양 변동 가능).

## 자동 교정 정책 (계약: 제한된 1회 후 사람 에스컬레이션)
- analyze가 "문제정의/지표가 데이터와 불일치" 명시 → frame 1회 재실행 후 analyze 재실행. 1회 후에도면 중단·보고.
- QA 기계적 BLOCK(chart_spec 매핑·SVG값·죽은 시뮬·콘솔·렌더·플레이스홀더·라벨 겹침·라벨 잘림·과대 차트) → visualize 1회 재실행 후 재검. 그래도면 중단·보고.
- QA 분석적 BLOCK(데이터 무결성·표본 부족·모순) → 자동수정 없이 즉시 중단·보고.
- QA POST BLOCK(심층 보고서 필수 구조 누락·단순 복사·web_context 출처 누락) → communicate 1회 재실행 후 재검. 그래도면 중단·보고.

## 어댑터 경계
- `.claude-plugin/`, `agents/*.md` 의 frontmatter는 Claude Code 어댑터용 — Codex는 `agents/*.md`의 **본문(지침)만** 참고한다.
- 코어(`schemas/ connectors/ qa/ templates/ themes/ docs/`)는 런타임 공유.

## 실행
```bash
bash scripts/run_codex_pipeline.sh <run-id>     # 단계별 codex exec + 결정적 게이트
bash scripts/run_codex_pipeline.sh <run-id> --guided   # 중간 사용자 체크포인트 명시(기본값)
bash scripts/run_codex_pipeline.sh <run-id> --auto     # 중간 체크포인트를 명시적으로 건너뜀
bash scripts/run_codex_pipeline.sh <run-id> --dry-run   # 실행 명령만 출력(과금 없음)
bash scripts/run_codex_pipeline.sh <run-id> --guided-intake   # AskUserQuestion handoff 검증
```

## 핵심 산출물
- `outputs/01_profile.md`
- `outputs/02_eda.md`
- `outputs/03_frame.md`
- `outputs/04_analysis.md`
- `outputs/chart_spec.json`
- `outputs/checkpoints/*.json|*.md` (중간 사용자 체크포인트)
- `outputs/dashboard_data.json`
- `outputs/dashboard.html`
- `outputs/qa_render_desktop.png`, `outputs/qa_render_compact.png`,
  `outputs/qa_render_mobile.png`, `outputs/qa_render_narrow.png` (v5.1)
- `outputs/visual_review.json` (v5.1 오케스트레이터 눈검토·hash 기록)
- `outputs/summary_report.md`
- `outputs/deep_report.md` (`report.depth=deep`일 때)
- `outputs/external_context.md` (`report.evidence_scope=web_context`일 때)
