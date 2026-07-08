---
name: run-pipeline
description: 표 데이터 소스(로컬 파일·API 스냅샷·원격 Parquet 스냅샷·선택 DuckDB)를 받아 8개 stage와 사용자 확인 checkpoint를 순서대로 실행하고 대시보드·보고서를 생성한다. manifest로 상태·체크포인트 관리, QA 게이트 강제. 계약은 docs/pipeline-contract.md.
argument-hint: "[run-id] (없으면 새로 생성. runs/<run-id>/input/ 파일·스냅샷, source_api_manifest.json, 또는 선택 connectors/.env DuckDB 필요)"
tools: Read, Write, Bash, Glob, Agent
---

# /run-pipeline

`docs/pipeline-contract.md` 의 8개 stage와 4개 사용자 확인 checkpoint를 순차 실행하는 오케스트레이터. 단계 정의·I/O·정책은 계약 문서가 단일 원천이며, 이 스킬은 **순서·체크포인트·게이트·루프백**만 관장한다.

## 실행 전
0. **Plan Mode 확인**: Claude Code에서 일반 분석 작업을 시작할 때는 먼저 Plan Mode에서 사용자용 분석 기획안과 실행 계획을 확인한다. 사용자가 계획을 승인한 뒤에 `/run-pipeline` 실행으로 넘어간다. 단순 회귀 테스트나 배치 실행처럼 사용자가 명시적으로 자동 실행을 요청한 경우만 예외다.
1. **run-id 결정**: 인자로 받거나 새로 생성(예: 주제 슬러그 또는 타임스탬프). `runs/<run-id>/{input,intermediate,outputs}/` 준비.
2. **소스 확인**: `runs/<run-id>/input/` 에 CSV·Parquet·Excel·JSON, 원격 Parquet 스냅샷, `source_api_manifest.json` 이 있거나, 선택적으로 `connectors/.env` 의 `DIK_DUCKDB_PATH` 가 있어야 한다. 둘 다 없으면 안내하고 중단:
   > "runs/<run-id>/input/에 데이터 파일/스냅샷을 넣어주세요. DuckDB 사용자는 connectors/.env에 DIK_DUCKDB_PATH를 설정하세요."
3. **manifest 초기화/로드**: `runs/<run-id>/manifest.json`. 없으면 생성(`run_id, created_at, stages[]`).

## 단계 순서 (계약과 동일)
```
intake → connect → explore → data_profile 확인 → frame → analysis_strategy 확인
       → analyze → dashboard_storyboard 확인 → visualize → qa
       → report_outline 확인 → communicate → qa-post
```
각 단계는 해당 **에이전트**(`agents/<stage>.md`)에 Agent 도구로 위임한다. 모델은 frontmatter(티어)대로.

사용자 확인 checkpoint는 자동 승인하지 않는다. 실제 사용자 답변을
`scripts/apply_checkpoint_answer.py`로 기록해야 다음 단계로 진행한다.

## 체크포인트 (mtime 아님 — 상태+산출물+체크섬)
각 단계 실행 **전** 확인:
- `manifest.stages[<stage>].status == "ran"` 이고 그 단계 산출물이 존재하면 → `✅ <stage> (cached)` 출력 후 건너뜀.
- 아니면 에이전트 실행 → 산출물 존재 확인 → `manifest.stages[]` 에 `{name, status:"ran"|"failed", at}` 기록.
- **소스 변경 감지**: `manifest.sources[].checksum`(파일), `source_snapshot.json`의 `snapshot_at`(원격 스냅샷), 또는 `snapshot_at`(DB)이 바뀌면 connect 이후 단계를 무효화(stale)하고 재실행.
- 강제 재실행: 사용자가 "처음부터"라고 하면 manifest의 stages를 비우거나 `outputs/` 를 비운다.

## QA 게이트 (visualize 직후)
- `qa` 단계 BLOCK 0 → communicate로.
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
