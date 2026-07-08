# AGENTS.md — data-insight-kit (공유 운영 지침)

이 저장소는 표 데이터 소스(로컬 파일·원격 Parquet·선택 DuckDB·API 스냅샷)를 받아 8개 stage와 사용자 확인 checkpoint로 분석하고 데이터 주입형 대시보드를 만드는 키트다.
**단일 원천은 `docs/pipeline-contract.md`** 이다. 이 파일(AGENTS.md)은 실행기가 아니라 Codex와 Claude Code 어댑터가 공통으로 따라야 할 운영 규칙이다.

## 파이프라인 계약
- 단계는 반드시 이 순서로만: `intake → connect → explore → data_profile checkpoint → frame → analysis_strategy checkpoint → analyze → dashboard_storyboard checkpoint → visualize → qa(gate) → report_outline checkpoint → communicate`. wrapper/adapter는 communicate 이후 `qa-post`를 추가 실행해 보고서 깊이 계약을 확인한다.
- 각 단계의 상세 사양·입출력은 `docs/pipeline-contract.md` 와 `agents/<stage>.md`(상단 Claude frontmatter는 무시) 를 따른다. 단계 정의를 새로 만들지 않는다.
- **결정적 코어 우선**: 스크립트·스키마 검증 결과가 LLM 판단을 이긴다.
  - 기본 입력은 `runs/<run-id>/input/`의 CSV·Parquet·Excel·JSON, API 수집 계획(`source_api_manifest.json`), 또는 축약 Parquet 스냅샷이다.
  - DB 접근은 선택 경로이며 `connectors/source.py` 경유만 허용한다(read-only·SELECT/WITH 전용).
  - 원격 Parquet는 전체 다운로드하지 말고 projection/filter/층화 샘플링/limit 후 로컬 스냅샷으로 고정한다.
- `runs/*`는 사용자별 로컬 산출물이며 배포용 core에 포함하지 않는다. 예시·검증이 필요하면 새 run을 만들되, tracked baseline으로 다시 추가하지 않는다. 재현 가능한 fixture가 필요하면 `tests/fixtures/` 또는 별도 example package를 명시적으로 설계한다.
- `chart_spec.json` 은 `schemas/chart_spec.schema.json` 을 통과해야 한다. 범용 데이터에서는 질문→방법론→계산→차트 선택을 먼저 고정하고, `dashboard_data.json` 은 그 계획을 이행한다.
- 심층 분석은 `docs/analysis-strategy-library.md`를 기준으로 데이터 형태별 주 전략과 보조 전략을 고른다. 단순 상위 N개·건수·비율 반복은 deep 분석으로 보지 않는다.
- Plan Mode 또는 guided intake에서 사용자에게 보여주는 계획은 `docs/user-facing-planning.md`를 따른다. 항상 **사용자용 분석 기획안**을 먼저 쓰고, run-id·endpoint·pagination·QA 명령 같은 **내부 실행 계획**은 뒤쪽 기술 부록으로 분리한다. 사용자가 명시적으로 요구하지 않으면 내부 실행 계획은 5개 안팎의 짧은 요약만 보여준다. 초보자가 "내가 원하는 분석이 맞는지" 판단할 수 없는 기술 중심 계획은 실패로 본다.
- frame은 분석 방향 선택지 2~3개를 제안해야 하고, analyze는 추천 storyboard와 대안 storyboard를 만들어야 한다. 사용자가 승인하기 전에는 단순 ranking 중심 구성으로 고정하지 않는다.
- chart_spec의 각 차트는 서로 다른 질문에 답해야 하며 `insight.finding/evidence/limit`가 대시보드 설명과 보고서 핵심 발견으로 이어져야 한다. 차트 목록이나 상위 N개 반복은 대시보드 품질로 보지 않는다.
- `dashboard_storyboard` 체크포인트는 사용자에게 차트 추천표를 보여줘야 한다. 각 행에는 사용할 데이터/지표, 비교 기준, 추천 차트, 추천 이유, 대안 차트, 대안을 제외하거나 보류한 이유가 있어야 한다. `chart_spec`에는 가능하면 `chart_recommendation`을 채운다.
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
- intake 이후에도 사용자 확인 없이 끝까지 밀어붙이지 않는다. wrapper/adapter의 기본값은 중간 체크포인트 ON이다. `explore` 후에는 `data_profile`, `frame` 후에는 `analysis_strategy`, `analyze` 후에는 `dashboard_storyboard`, `qa` 통과 후에는 `report_outline` 질문을 `outputs/checkpoints/`에 만들고 exit code `3`으로 멈춘다. 각 checkpoint 질문은 deep-interview 형식의 `chat_prompt`와 초보자용 `user_review_brief`를 포함해야 하며, 형식은 반드시 "현재 이해 / 확인할 내용 / 막힌 결정 / 추천 답안 / 질문"이다. 상위 에이전트는 긴 artifact 전체보다 이 요약을 먼저 채팅창에 제시하고, 사용자의 자유 답변 또는 선택지를 `scripts/apply_checkpoint_answer.py`로 `checkpoint_answers.json`에 누적한다.
  - 승인 답변은 반드시 실제 사용자 답변을 포함해야 한다. 명령에는 `--source user_chat|ask_user_question|manual_cli`와 `--user-response "<사용자 실제 답변>"`가 필요하다.
  - 에이전트가 질문 파일의 추천 답안이나 기존 계획을 근거로 스스로 `continue_pipeline=true` 답변을 만들면 승인으로 인정하지 않는다. `source=agent_assumption`은 메모만 가능하며 다음 단계 진행을 허용하지 않는다.
  - 최신 답변이 `continue_pipeline=false`이면 관련 산출물을 수정하고 다시 승인받기 전까지 다음 단계로 진행하지 않는다. 완전 자동 실행은 사용자가 명시적으로 `--auto` 또는 `--no-checkpoints`를 선택한 경우만 허용한다.
- `data_profile` 체크포인트에서는 가능한 경우 원본 파일에서 최대 20행 preview를 만들고, 불가능하면 profile/EDA 요약과 샘플링 불가 사유를 보여준다. 대용량 원본 전체를 열거나 복사하지 않는다.
- 사용자가 API URL만 주면 wrapper는 `scripts/prepare_primary_api_source.py`로 `input/source_api_manifest.json`을 만들고 connect 단계에 전달한다. connect는 endpoint/auth/pagination smoke test 후 `input/*.parquet|csv|jsonl` 스냅샷을 고정해야 한다. API 수집이 막히면 대체 데이터를 꾸미지 말고 source blocker로 중단한다.
- `analysis_strategy` 체크포인트는 KPI, 분모, 비교 기준, 분석 질문을 사용자가 승인하는 게 목적이다. 내부 분석 용어가 과하거나 사용자의 의도와 어긋나면 frame을 수정하고 재확인한다.
- `dashboard_storyboard` 체크포인트는 추천/대안 storyboard, 차트 추천표, chart_spec, 탭 흐름, 차트 유형, 배포용 표현 방향을 사용자가 승인하는 게 목적이다. 승인 전에는 `dashboard_data.json`을 만들지 않는다. 단순 순위·요약만 반복되거나 "어떤 데이터로 왜 이 차트를 쓰는지"가 불명확하면 `deepen_chart_story` 또는 `revise_chart_mix`로 돌아가 차트와 인사이트를 다시 설계한다.
- `report_outline` 체크포인트는 대시보드 QA가 통과한 뒤 최종 보고서의 독자, 깊이, 핵심 발견 순서, 문체, 결론 수위, 피해야 할 표현을 사용자가 승인하는 게 목적이다. 승인 전에는 `summary_report.md`와 `deep_report.md`를 만들지 않는다.
- 대시보드와 보고서는 기본적으로 배포용 독자 언어로 작성한다. `proxy`, `layer`, `grain`, `chart_spec`, `source_ref`, 원천 컬럼명, 코드값, 내부 지표명 같은 분석·구현 용어는 제목·KPI·축·요약 도입부에 노출하지 않는다. 필요하면 방법론 또는 부록에서 풀어쓴다.
- 외부 데이터나 도메인별 보정 지표가 결론 품질을 크게 바꾸는 요청이면 guided intake에서 `external_adapter_policy` 질문을 사용할 수 있다. 답변은 `intake.external_adapters`에 `selected_categories`, `unavailable_categories`, `interpretation_guards`, `registry_ref`로 남기고 실제 수집 가능 여부는 connect 단계에서 판정한다.
- wrapper/adapter는 최종 또는 draft intake의 `external_adapters`를 `input/external_adapter_plan.json`과 `external_adapter_plan.json`으로 정규화한다. 이 plan은 사용자 선택 정책이며 실제 외부 데이터 lineage가 아니다. 실제 외부 데이터가 있으면 `input/external_denominator_manifest.json` 또는 `external_denominators.json`이 별도로 있어야 한다.
- AI 앱에서 사용자가 짧게 실행을 요청하면 먼저 계획/승인 흐름을 사용한다. Codex Desktop과 Claude Code 모두 Plan Mode에서 사용자용 분석 기획안과 실행 계획을 먼저 확인하고, 승인 후에 실행한다. Codex CLI wrapper는 `--guided-intake` handoff를 사용하고, Claude Code plugin은 `/run-pipeline` 실행 전후로 동일한 사용자 확인 원칙을 따른다. `outputs/intake_questions.json`이 생성되면 그 내용을 선택지 UI 또는 채팅 질문으로 묻고, 답변은 `python3 scripts/apply_intake_answer.py <run-id> --option <option-id>` 또는 `--answer "<직접 답변>"`으로 `intake_draft.yaml`에 누적한다. 팝업/채팅 답변을 바로 `intake.yaml`로 쓰지 않는다. 질문이 더 필요하면 같은 흐름을 반복하고, 충분해졌을 때만 intake 단계가 최종 `intake.yaml`을 만든다.
- `dashboard_data.json` 은 `schemas/dashboard_data.schema.json` 을 통과해야 한다.
  - 출고 게이트는 `python qa/validate.py <dashboard_data.json> --chart-spec <chart_spec.json>` — BLOCK이면 통과 금지.
  - communicate 이후 게이트는 `python qa/validate.py <dashboard_data.json> --chart-spec <chart_spec.json> --no-render --post-communicate` — `depth=deep`인데 `deep_report.md`가 얕거나 `04_analysis.md` 복사본이면 BLOCK.
- 쓰기는 `runs/<run-id>/` 안에만. 원격 URI·조회일·row count·schema 요약·샘플링 방식은 manifest에 남기되, DB 경로·자격은 `.env`(커밋 금지), 로그·산출물에 남기지 않는다.

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
- `outputs/summary_report.md`
- `outputs/deep_report.md` (`report.depth=deep`일 때)
- `outputs/external_context.md` (`report.evidence_scope=web_context`일 때)
