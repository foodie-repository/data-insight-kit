---
name: run-pipeline
description: 표 데이터 소스(로컬 파일·API 스냅샷·원격 Parquet 스냅샷·선택 DuckDB)를 받아 8개 stage와 사용자 확인 checkpoint를 순서대로 실행하고 대시보드·보고서를 생성한다. manifest로 상태·체크포인트 관리, QA 게이트 강제. 계약은 docs/pipeline-contract.md.
argument-hint: "[run-id] (없으면 새로 생성. runs/<run-id>/input/ 파일·스냅샷, source_api_manifest.json, 또는 선택 connectors/.env DuckDB 필요)"
tools: Read, Write, Bash, Glob, Agent
---

# /run-pipeline

이 skill은 **Claude Code와 Codex가 함께 사용하는 marketplace 진입점**이다.
Claude Code에서는 `/run-pipeline` 명령으로, Codex에서는 data-insight-kit skill로
호출한다. 두 런타임 모두 같은 `scripts/run_codex_pipeline.sh` wrapper와
`docs/pipeline-contract.md`를 사용한다.

실행 전에 현재 읽은 `SKILL.md`의 절대 경로에서 두 단계 위인 제품 root를
`KIT_ROOT`로 정한다(`.../skills/run-pipeline/SKILL.md` → `KIT_ROOT`). 아래의
`scripts/`, `docs/`, `runs/` 경로와 모든 명령은 반드시 `KIT_ROOT` 기준으로
해석·실행한다. marketplace cache나 사용자의 전역 skill 경로를 하드코딩하지
않는다.

`docs/pipeline-contract.md` 의 8개 stage와 4개 사용자 확인 checkpoint를 순차 실행하는 오케스트레이터. 단계 정의·I/O·정책은 계약 문서가 단일 원천이며, 이 스킬은 **순서·체크포인트·게이트·루프백**만 관장한다.

## 실행 전
0. **Plan Mode 확인**: Claude Code에서 일반 분석 작업을 시작할 때는 먼저 Plan Mode에서 사용자용 분석 기획안과 실행 계획을 확인한다. 사용자가 계획을 승인한 뒤에 `/run-pipeline` 실행으로 넘어간다. 단순 회귀 테스트나 배치 실행처럼 사용자가 명시적으로 자동 실행을 요청한 경우만 예외다. 첫 계획은 `docs/user-facing-planning.md`를 따른다. `Summary`, `Key Changes`, `Pipeline`, `Test Plan`, `Assumptions` 같은 개발 계획 템플릿으로 시작하지 말고, `이번 분석은 이렇게 진행합니다` 또는 `사용자용 분석 기획안`으로 시작한다. run-id, 파일 경로, 검증 명령은 뒤쪽 `기술 부록`에만 둔다.
1. **run-id 결정**: 인자로 받거나 새로 생성(예: 주제 슬러그 또는 타임스탬프). `runs/<run-id>/{input,intermediate,outputs}/` 준비.
2. **새 분석 정책 기록**: 새 run은 기본적으로 `fresh_analysis`다. 기존 `runs/*`, 이전 `dashboard_data.json`, 이전 `chart_spec.json`, 이전 보고서는 사용자가 명시적으로 "기존 run 참고", "지난 분석과 비교", "기존 대시보드 수정", "resume"을 요청한 경우에만 참조한다. wrapper는 `runs/<run-id>/input/run_context.json`에 `allow_prior_run_reference`와 `reference_runs[]`를 남긴다.
3. **소스 확인**: `runs/<run-id>/input/` 에 CSV·Parquet·Excel·JSON, 원격 Parquet 스냅샷, `source_api_manifest.json` 이 있거나, 선택적으로 `connectors/.env` 의 `DIK_DUCKDB_PATH` 가 있어야 한다. 둘 다 없으면 안내하고 중단:
   > "runs/<run-id>/input/에 데이터 파일/스냅샷을 넣어주세요. DuckDB 사용자는 connectors/.env에 DIK_DUCKDB_PATH를 설정하세요."
4. **manifest 초기화/로드**: `runs/<run-id>/manifest.json`. 없으면 생성(`run_id, created_at, stages[]`).

## 단계 순서 (계약과 동일)
```
intake → connect → explore → data_profile 확인 → frame → method_route 생성
       → dependency preflight → analysis_strategy 확인(설치 승인 포함) → 승인 반영(설치/강등)
       → analyze → analysis_result_review 확인(조건부) → dashboard_storyboard 확인
       → visualize → qa → report_outline 확인 → communicate → qa-post
```
각 단계는 해당 **에이전트**(`agents/<stage>.md`)에 Agent 도구로 위임한다. 모델은 frontmatter(티어)대로.

`frame`은 `methods/method_registry.json`을 기준으로 `outputs/method_route.json`을
생성해야 한다(분석 깊이 route + selected_methods). 그 직후 wrapper가
`scripts/dependency_preflight.py`로 `input/dependency_plan.json`을 준비하고,
`analysis_strategy` 확인 질문에 설치 필요 여부와 설치 승인 선택지를 함께
포함한다. 사용자가 설치를 승인하면 wrapper가 `--apply-approval`로 승인 직후
kit 전용 `.venv`에 설치를 반영하고(미승인/실패 시 route를 core-only로 강등),
`analyze` 단계로 넘어간다.

`analyze` 직후에는 조건부 checkpoint `analysis_result_review`(고정 prefix
`05_`, 사용자 표현 "1차 결과 확인")가 있다. 발동 여부는 spec §9의 결정적
술어(route가 통계/ML/예측/실험 심화 route이거나, domain mode이거나,
`report.depth=deep`이거나, 의사결정형 `analysis_mode`)로 매 run 다시 계산되며,
조건이 아니면 이 단계는 나타나지 않고 바로 `dashboard_storyboard` 확인으로
넘어간다.

사용자 확인 checkpoint는 자동 승인하지 않는다. 실제 사용자 답변을
`scripts/apply_checkpoint_answer.py`로 기록해야 다음 단계로 진행한다.

**승인 요청 시 표시 의무**: 상위 에이전트는 자체 요약만으로 승인을 받으면 안
된다. 매 checkpoint마다 반드시 (1) 질문 md 원문 경로를 클릭 가능한 링크로,
(2) `data_profile`이면 `data_snapshot.sample_preview_path`의 실제 데이터 샘플
내용을, (3) 질문 JSON의 `artifacts[]` 목록(근거 파일)을 링크로 함께 제시한다.
에이전트 요약은 보조 수단이며 원문을 대체할 수 없다 — 요약이 원문과 어긋나면
사용자가 잘못된 근거로 승인하게 된다. `dashboard.html`이 생성된 뒤의
checkpoint에서는 대시보드를 열어 볼 수 있는 경로도 함께 준다.
**눈검토 의무**: 대시보드 경로를 사용자에게 주기 전에 qa가 남긴 모든 렌더를
직접 열어 본다. v5.1은 `outputs/qa_render_desktop.png`,
`outputs/qa_render_compact.png`, `outputs/qa_render_mobile.png`,
`outputs/qa_render_narrow.png` 네 장 모두가 대상이다. 오케스트레이터는
문구·정보 위계·색 의미·척도·라벨/범례·공백·겹침·잘림 관찰을
`outputs/visual_review.json`에 기록한다. 네 screenshot hash가 현재 파일과
일치하고 `status=pass`일 때만 checkpoint로 전달한다. `revise`, 누락, hash
불일치는 BLOCK이며 테스트나 에이전트가 눈검토를 대리할 수 없다. QA 통과는
프로그램된 검사의 통과일 뿐 "화면이 멀쩡하다"의 증명이 아니다(v4 smoke에서
카드 겹침이 QA를 통과한 실사례).

**탐색 문답(interview loop v2)**: 각 checkpoint는 승인 전 최대 2라운드 문답을
가진다. 방향 선택지·확정 질문을 보여줄 때는 미리 본 결과의 '내용'을 채팅
본문에 표 그대로 출력한 뒤 선택을 받는다 — 링크·팝업 preview에 의존하면
사용자가 내용을 모른 채 선택하게 된다(gate 핸드오프가 근거 원문을 내장한다).
**전달 순서(턴 분리)**: 근거 출력과 선택 수집을 같은 턴에 두지 않는다 —
같은 턴에 본문+선택 팝업을 함께 보내면 팝업이 먼저 렌더되어 사용자가 근거를
읽기 전에 선택을 요구받는다(v4 smoke 발견). 근거 본문을 먼저 보내 턴을
끝내고, 사용자가 읽은 뒤 다음 턴에서 선택을 받는다(팝업 또는 채팅 답변 —
채팅 답변도 `--source user_chat`으로 동일하게 기록된다).
채팅 전달은 **원문 우선 + 보강**: 질문·선택지 문구는 원문 그대로(재작성
금지), 표 렌더·링크·해설 보강만 그 아래에 허용. 질문 md도 같은 완결성을
갖는다(근거·추가 확인 질문·직접 질문 안내 내장). 사용자가 방향 선택지나 자유 질문(라운드당 1개)을 고르면
`checkpoint_gate.py`를 다시 실행해 `.round2` 질문을 만들고 그 원문을 다시
보여준다. 자유 질문은 `apply_checkpoint_answer.py --free-question`으로 먼저
기록한 뒤 이번 run input에서만 조회·집계로 답을 계산하고
`scripts/record_free_question_result.py`로 결과 쌍을 남긴다 — 미니 결과는
참고 자료라서 보고서·대시보드에 직접 인용하지 않는다(반영은 분석 단계에서
재계산). domain mode에서는 질문에 추가 확인 질문(companion)이 붙는다: 답변은
`--companion <id>`로 기록하고, 쌓이면 `scripts/build_domain_intake.py`로
도메인 확인 정보를 파생 생성한다. 방향 선택·자유 질문·companion 답변은
진행을 결정하지 않는다(불변식 I1) — 진행은 주 질문 승인 답변 하나뿐이다.
이 plugin의 PreToolUse 훅(`hooks/hooks.json` → `scripts/dik_checkpoint_hook.py`)이
승인 없는 다음 stage 산출물 쓰기(`03_frame.md`·`04_analysis.md`·`chart_spec.json`·
`dashboard_data.json`·`dashboard.html`·`summary_report.md`·`deep_report.md`)와
run-local builder 실행을 결정적으로 deny한다. 따라서 Plan 승인 직후 곧바로 다음
산출물을 만들려 하면 훅이 막는다. 각 checkpoint에서 실제로 멈추고 사용자에게
질문한 뒤 답변을 기록해야만 훅이 통과시킨다. 훅이 deny하면 그 사유(질문 제시 →
`apply_checkpoint_answer.py` 기록)를 따르고, 우회하지 않는다.
이 스크립트가 남기는 `checkpoint-answer.v3` provenance(`recorded_by`,
`answer_id`, `question_ref.path`, `question_ref.sha256`,
`question_ref.created_at`, `answered_at`)가 없으면 승인으로 인정하지 않는다.
`source=user_chat|ask_user_question` 답변은 실제 사용자 메시지나 팝업 답변을
가리키는 `transcript_ref`도 필요하다. Plan Mode의 구현 승인 문구나 에이전트
추천 답안을 checkpoint별 승인 문구로 쪼개 기록하지 않는다.
후속 단계 진입 전에는 `scripts/stage_guard.py`가 이전 checkpoint 승인 상태를
검사한다.
최종 QA는 checkpoint lineage도 검사한다. 질문 artifact와 실제 사용자 승인 기록이
없거나 provenance가 맞지 않으면 수동 builder로 만든 대시보드라도 출고하지
않는다. downstream 산출물이 해당 checkpoint 승인보다 먼저 만들어졌어도
출고하지 않는다. run-local builder는 입력 정규화나 초안 생성 보조에는 쓸 수
있지만, 사용자 승인 없이 공식 대시보드·보고서 산출물이나
`checkpoint_answers.json`을 직접 만들면 안 된다.

checkpoint가 exit code `3`으로 멈추면 파일 목록이나 생성 요약을 먼저 설명하지
않는다. `scripts/checkpoint_gate.py <run-id> <checkpoint-id> --print-existing`
출력 또는 질문 JSON의 `chat_prompt`를 먼저 사용자에게 보여주고, 선택지나 수정
요청을 채팅창 답변으로 받는다. 파일 경로와 반영 명령은 그 다음 기술 정보로
제시한다.

## 체크포인트 (mtime 아님 — 상태+산출물+체크섬)
각 단계 실행 **전** 확인:
- `manifest.stages[<stage>].status == "ran"` 이고 그 단계 산출물이 존재하면 → `✅ <stage> (cached)` 출력 후 건너뜀.
- 아니면 에이전트 실행 → 산출물 존재 확인 → `manifest.stages[]` 에 `{name, status:"ran"|"failed", at}` 기록.
- **소스 변경 감지**: `manifest.sources[].checksum`(파일), `source_snapshot.json`의 `snapshot_at`(원격 스냅샷), 또는 `snapshot_at`(DB)이 바뀌면 connect 이후 단계를 무효화(stale)하고 재실행.
- 강제 재실행: 사용자가 "처음부터"라고 하면 manifest의 stages를 비우거나 `outputs/` 를 비운다.

## QA 게이트 (visualize 직후)
- `qa` 단계 BLOCK 0 → communicate로.
- v5.1은 1440×1000·736×1000·390×844·320×800 browser QA와 현재 screenshot
  hash에 결합된 `outputs/visual_review.json`의 `status=pass`를 모두 요구한다.
- `fresh_analysis`인데 기존 run 경로가 산출물에 섞이면 BLOCK. 이전 결과를
  의도적으로 참고하는 경우에는 `run_context.reference_runs[]`에 명시되어야 한다.
- checkpoint 질문 파일과 `checkpoint_answers.json`의 실제 사용자 승인 증거가
  없거나 `checkpoint-answer.v3` provenance가 맞지 않으면 BLOCK.
- **기계적 BLOCK** → visualize 1회 재실행 후 qa 재검. 그래도 BLOCK이면 중단+보고.
- **분석적 BLOCK** → 즉시 중단+사용자 보고.

## 루프백 (analyze)
- analyze가 "문제정의/지표가 데이터와 불일치"를 명시하면 frame 1회 재실행 후 analyze 재실행. 1회 후에도면 중단+보고.

## 단계 실패
산출물이 안 생기면 해당 단계 실패로 보고 후 중단(다음 단계로 진행 금지).

## 완료 메시지
전체 성공 시 산출물 경로 목록 출력(캐시된 단계는 `(cached)`):
```
✅ 파이프라인 완료 (run-id: <id>)
📄 outputs/01_profile.md
📄 outputs/02_eda.md
📄 outputs/03_frame.md
📄 outputs/04_analysis.md
🌐 outputs/dashboard.html        ← QA 통과
📄 outputs/summary_report.md
📄 outputs/deep_report.md        ← depth=deep일 때
🧾 manifest.json
```

## 보안 (계약)
- 기본 입력은 `runs/<run-id>/input/` 파일·스냅샷이다. API URL은 먼저 `source_api_manifest.json`으로 계획을 남기고, connect 단계에서 인증·pagination·스냅샷을 확인한다. 원격 데이터는 전체 다운로드하지 않고 projection/filter/층화 샘플링/limit 후 로컬 스냅샷으로 고정한다. rate limit 원격 소스의 검증 표본은 candidate pool 안에서 만들 수 있다.
- 회사·업무 도메인 기준이 필요하면 `DIK_DOMAIN_PACK=domains/<domain>/domain.yaml` 또는 `runs/<run-id>/input/domain_pack_ref.txt`로 domain pack을 지정한다. wrapper가 `input/domain_pack_context.md`를 만들고 stage에 전달한다.
- DB 접근은 선택 경로이며 `connectors/source.py` 경유만(read-only·SELECT). 쓰기는 `runs/<run-id>/` 안에만.
- 자격·경로를 로그·산출물에 남기지 않는다.
