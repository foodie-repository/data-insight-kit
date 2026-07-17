# Interview Loop v2 — 전 정지점 인터뷰 런타임

Status: draft for user review (설계 결정은 2026-07-10 인터뷰로 확정 —
`interview-loop-v2-kickoff.md` "확정 결과" 참조)

이 spec은 `expert-guided-analysis-routing.md`(이하 v1 spec)의 §8.3(domain expert
interview lifecycle)과 §12.2(v2: Domain Expert Workflow)를 계약 기반으로 삼는
v2 상세 spec이다. v1 spec의 계약(§9 술어, §10 QA, §11 사용자 표현, §15 구현
기본값)은 전부 유지되며, 이 문서는 그 위에 인터뷰 루프 런타임을 추가한다.
구현 중 이 문서와 코드가 달라지면 코드에 맞춰 조용히 넘어가지 않는다 — 먼저 이
spec을 수정하고 구현을 맞춘다.

## 1. 목표와 배경

v1 진단(CHANGELOG 발견 4): v1 아키텍처는 batch stage + 승인 게이트라서 사용자는
완성된 결과의 결재자가 된다. 게이트 레이어는 반복 강화됐지만 상호작용 레이어가
없어 체감이 변하지 않았다.

v2의 정의: **guided intake에서 검증된 패턴(질문 JSON 생성 → 상위 UI가
AskUserQuestion으로 표시 → 답변 누적 → 충분하면 확정)을 기존 정지점 전체에
이식하는 인터뷰 루프 런타임.** 사용자는 각 정지점에서 완성안을 결재하는 대신,
탐색 방향·해석 수위·차트·보고서 계약을 문답으로 함께 정한다.

## 2. 확정된 설계 결정 (2026-07-10 사용자 인터뷰)

- **D1 = 전 정지점 업그레이드, 새 정지점 0개.** 사용자가 짚은 분석가의 4개
  타이밍(전처리·결과 검토·차트 결정·보고서 전)은 v1 정지점(4 checkpoint +
  조건부 `analysis_result_review`) 및 v1 spec §8.3 lifecycle과 1:1로 일치한다.
  따라서 정지점을 추가하지 않고 **기존 정지점의 질문 레이어만 인터뷰 루프형으로
  교체**한다. 정지 횟수는 v1과 동일하고, 부담 증가는 선택적 후속 라운드뿐이다.
  단순 run에서는 §9 술어 유지로 `analysis_result_review`가 발동하지 않으며
  `dashboard_storyboard`가 1차 결과 검토를 겸한다.
- **D2 = 혼합형.** 기본은 선택지형(볼 만한 방향 후보 + 미리 계산한 미니 결과),
  각 라운드에 자유 질문 1개를 허용한다. 자유 질문은 미니 쿼리로 즉석 답변하되
  실행 경계(§7)를 지킨다.
- **D3 = 정지점당 최대 2라운드 × 라운드당 최대 3문항.** 매 라운드에 "충분함,
  분석 진행" 조기 종료 옵션을 포함한다. 충분 판정 = 조기 종료(승인) 선택 또는
  상한 도달. 상한 도달 시 누적 답변으로 확정하고 다음 단계로 넘어가거나, 승인
  불가 답변이면 기존 반려(revise) 흐름으로 합류한다.

## 3. 용어

| 용어 | 정의 |
|---|---|
| 인터뷰 라운드 | 한 정지점에서 질문 파일 1개 생성 → 사용자 답변 기록까지의 1회전. 정지점당 최대 2회 |
| 주 질문 | 라운드의 게이트 질문. 이 답변의 `continue_pipeline`만 파이프라인 진행을 결정한다 |
| companion 질문 | 주 질문과 같은 라운드에 붙는 정보 수집용 질문(최대 2개). 진행을 결정하지 않는다 |
| 탐색 방향 후보 | stage 에이전트가 사전 계산한 "볼 만한 방향" 선택지(미니 결과 포함) |
| 미니 결과 | 방향 후보에 딸린 사전 계산 요약(집계 표 ≤10행 등). 에이전트 산출물이며 게이트는 렌더만 한다 |
| 자유 질문 | 사용자가 라운드에서 직접 던지는 데이터 질문. 라운드당 최대 1개 |
| 미니 쿼리 | 자유 질문에 답하기 위한 제한된 즉석 계산(§7 경계 내) |
| 조기 종료 | "충분함, 진행" 옵션 선택 = 해당 정지점 승인(`continue_pipeline=true`) |

문항 수 계산: 라운드의 문항 수 = 주 질문 1 + companion 질문 수(≤2) ≤ 3.
자유 질문은 사용자가 내는 질문이므로 문항 수에 세지 않는다(라운드당 ≤1로 별도 제한).

## 4. 인터뷰 루프 런타임 계약

### 4.1 질문 파일과 라운드

- 라운드 1 질문 파일은 기존 이름을 그대로 쓴다:
  `outputs/checkpoints/01_data_profile_question.json|md` 등 (하위 호환, v1 spec
  §15 prefix 불변 원칙 유지).
- 라운드 2 질문 파일은 고정 접미사를 쓴다:
  `outputs/checkpoints/<prefix>_<checkpoint>_question.round2.json|md`.
  라운드별 파일 분리는 선택이 아니라 **기존 provenance 메커니즘의 요구**다 —
  답변이 `question_ref.sha256`으로 질문 파일을 고정하므로, 파일을 덮어쓰면
  라운드 1 승인 증거가 hash 불일치로 깨진다.
- 라운드 3 이상은 만들 수 없다. `checkpoint_gate.py`가 생성을 거부하고,
  stage_guard/hook/QA가 `*.round3*` 파일을 각각 차단한다(§9).
- 라운드 상한 판정은 파일 개수가 아니라 **유효 R2 체인**으로 계산한다:
  유효 R2 = `prior_round.question_sha256`이 현재 R1 파일의 sha256을 가리키는
  라운드 2 질문이며, 사이클당 유효 R2는 1개 이하다. 반려 후 R1이
  재생성되면(§4.4) 이전 R2는 고아가 되어 판정에서 무시된다(QA WARN). 반려
  사이클이 라운드 예산을 오염시키지 않기 위한 결정적 규칙이다.

### 4.2 checkpoint_question schema 확장 (v2)

`schemas/checkpoint_question.schema.json`의 `schema_version` enum에
`data-insight-kit.checkpoint_question.v2`를 추가한다. v1 값은 그대로 유효하다
(legacy run 검증 보호). v2 질문은 다음 optional 블록을 가질 수 있다.

```jsonc
"interview_loop": {
  "round": 1,                  // 1 | 2
  "max_rounds": 2,
  "free_question_used_this_round": false, // 현재 라운드 기준 파생 표시값 — 판정은 답변 레코드 집계(D2 라운드당 1개)
  "max_free_questions_per_round": 1,
  "prior_round": {             // round 2에서만: 라운드 1 요약
    "question_path": "...",
    "question_sha256": "...",  // 유효 R2 체인 판정 기준 (§4.1)
    "answer_id": "...",
    "trigger": "explore_direction|free_question|domain_readiness_gap",
    "mini_result_paths": ["outputs/exploration/..."]
  },
  "finalization_rule": "조기 종료 옵션 선택 또는 라운드 상한 도달 시 누적 답변으로 확정"
},
"companion_questions": [       // 최대 2개
  {
    "id": "row_meaning",
    "question": "...", "header": "...",
    "options": [ /* 선택지 또는 */ ], "allow_free_text": true,
    "maps_to": {"domain_field": "row_meaning"}   // §8 도메인 수집용
  }
],
"exploration": {               // data_profile 라운드 1 전용 (§6.1)
  "candidates_ref": "outputs/exploration_candidates.json",
  "free_question_slot": true
}
```

`interview_state`(guided intake) 패턴을 그대로 옮긴 것이며, 필드 의미가 같은
곳은 이름도 맞춘다(`max_*`, `finalization_rule`).

스키마는 조건부 규칙(JSON Schema if/then)으로 v2 구조를 강제한다.

- `schema_version`이 v2면 `interview_loop`는 required다.
- `interview_loop.round=2`면 `prior_round`는 required다.
- 옵션에 `maps_to.loop_action`이 있으면 그 옵션의 `continue_pipeline`은
  `false`여야 한다(불변식 I1의 스키마 층, §4.3).

legacy v1 required 목록은 그대로 유지한다 — 하위 호환은 enum·optional 추가로
지키고, v2 구조 강제는 조건부 규칙으로 지킨다.

### 4.3 답변 기록 확장

`scripts/apply_checkpoint_answer.py`는 v3 답변 계약을 유지한 채 다음을 추가한다.

- `--question-file`로 라운드 2 파일을 지정하는 기존 경로를 라운드 표준으로 삼고,
  답변 레코드에 `interview_round`(질문 파일의 `interview_loop.round`)를 기록한다.
- `--companion <id>`: companion 질문에 대한 답변을 별도 레코드로 누적한다.
  companion 답변은 `continue_pipeline`을 항상 `false`로 기록하며 게이트 판정에
  쓰이지 않는다(정보 수집 전용). `maps_to.domain_field`를 레코드에 복사한다.
- `--free-question "<질문 원문>"`: 자유 질문을 `loop_action=free_question`
  레코드로 누적한다(`continue_pipeline=false`). 미니 쿼리 결과가 나오기 전
  기록이 선행되어야 한다 — QA가 "질문 없이 만들어진 미니 결과"를 잡는 근거.
  `--free-question`·`--companion`은 `--continue-pipeline`과 상호 배타이며
  동시 지정 시 helper가 거부한다.
- 탐색 방향 선택은 옵션의 `maps_to.loop_action=explore_direction`으로 표현한다.
  별도 플래그는 없다.

**불변식 I1**: `loop_action ∈ {free_question, explore_direction}` 레코드와
companion 레코드는 어떤 경로로도 `continue_pipeline=true`가 될 수 없다.
강제 지점은 3곳이다 — (1) helper가 기록 시점에 거부, (2) stage_guard/hook이
stage 진입 전에 위반 레코드를 승인 후보에서 제외하고 차단, (3) QA BLOCK(§9).

**canonical 단일화**: 진행 판정(gate·stage_guard·hook·QA)의 입력은
`runs/<run-id>/checkpoint_answers.json` 하나다. `input/` mirror는 판정에
쓰지 않는다. mirror가 존재하면 canonical과 sha256·`updated_at` 일치를
검사하고 불일치 시 fail-closed(진행 차단 + 복구 안내)한다. helper는
canonical 기록 성공 후 mirror를 쓴다. 구현 시 `answer_candidates`/
`latest_answer`(checkpoint_gate.py)·stage_guard의 실제 병합 동작을 코드로
확인한 뒤 이 계약에 맞춘다(Codex 교차검증 H2 단서).

**결정 레코드 선택**: 진행 판정과 라운드 전이는 **companion 레코드만 제외한
최신 레코드**로 결정한다. 자유 질문 레코드는 I1에 의해 항상
`continue_pipeline=false`이므로 승인을 만들 수 없고 라운드 전이만 유발한다.
companion 레코드는 진행에도 라운드 전이에도 관여하지 않는다 — 승인 뒤
companion이 append되어도 상태가 뒤집히지 않는다(M1의 보호 목적).
(구현 중 정정: 애초 "자유 질문도 선택에서 제외"로 썼으나, 그러면 트리거
(a)가 영영 발동하지 않는 모순이 있어 이 정의로 통합했다.)

기존 규칙 불변: `--source`/`--user-response`/`--transcript-ref` 요구, human
confirmation 없는 진행 금지, `checkpoint_answers.json` append-only 누적.

**전달 순서(턴 분리) 강제** (v4 smoke 발견, 2026-07-13 추가): gate가 핸드오프
원문을 출력할 때마다 `outputs/checkpoints/handoff_log.json`에
{question_file, question_sha256, printed_at} 스탬프를 남긴다(`--quiet` 생성은
스탬프 없음). `--source ask_user_question` 답변은 **같은 질문 sha의 스탬프가
선행하지 않으면 기록이 거부된다**(fail-closed) — 근거 원문 출력 없이 팝업만
띄우는 경로를 기계적으로 차단한다. 통과한 레코드에는 `handoff_printed_at`·
`handoff_to_answer_seconds`가 감사 필드로 남고, QA는 스탬프 없는 팝업 답변을
WARN으로 표시한다(스탬프 도입 전 legacy run 호환). Claude Code 어댑터의
PreToolUse 훅은 스탬프 없는 pending 질문이 있을 때 AskUserQuestion 자체를
deny한다. 한계(정직하게): 이 장치가 강제하는 것은 "원문 출력 행위의 선행"
까지다 — 사용자가 실제로 읽었는지는 코드로 강제할 수 없고, 그 구간은
AGENTS.md/SKILL.md의 턴 분리 규칙(산문)이 담당한다.

### 4.4 라운드 진행 상태 머신

정지점 1곳의 흐름은 결정적으로 다음과 같다.

```text
[stage 완료] → gate: 라운드1 질문 생성 (기존 파일명) → 사용자 답변
  ├─ 조기 종료/승인 옵션 (continue_pipeline=true) → 정지점 종료, 다음 stage
  ├─ 반려 옵션 (revise 계열, loop_action 없음)   → 기존 반려 흐름 (라운드 소비 없음*)
  ├─ 탐색 방향 선택 (loop_action=explore_direction)
  │    → 오케스트레이터: 방향 상세 미니 결과 확인/보강 → gate: 라운드2 질문
  └─ 자유 질문 (loop_action=free_question)
       → 오케스트레이터: 미니 쿼리 실행(§7) → 결과 artifact 기록
       → gate: 라운드2 질문 (미니 결과 요약 + artifacts 링크 포함)
[라운드2] → 사용자 답변
  ├─ 승인/확정 옵션 → 정지점 종료
  └─ 그 외 (수정 요청, 새 자유 질문 등) → 라운드 상한 도달:
       continue_pipeline=false로 기록되고 기존 반려 흐름 합류.
       인터뷰 루프는 소진 — 산출물 수정 후 재승인은 v1 반려 절차 그대로.
```

(*) 반려 후 재질문은 새 인터뷰가 아니라 재승인이다. 사실 관계(Codex 교차검증
M3 반영): v1 gate는 반려 시 재생성 없이 종료(exit 4)하고, 재생성은 산출물
수정 후 오케스트레이터가 gate를 다시 호출할 때 일어난다(R1 덮어쓰기 허용).
승인 검증은 최종 승인 답변의 hash만 대조하므로 과거 반려 답변의 hash
불일치는 허용된다(기록은 append-only로 보존). R1이 재생성되면 이전 사이클의
R2는 고아가 되어 라운드 판정에서 무시된다(§4.1 유효 R2 체인).

### 4.5 실행기별 구동

v1과 동일한 이중 구동을 유지한다.

- Codex CLI wrapper: `checkpoint_gate.py` exit 3 루프. gate는 최신 답변의
  `loop_action`과 라운드 파일 존재를 보고 "라운드 2 질문 생성"을 스스로 판단한다.
  단, 미니 결과 계산은 gate가 하지 않는다 — wrapper가 답변 후 미니 결과 단계
  (에이전트)를 실행하고 나서 gate를 다시 부른다.
- Claude Code plugin / 자연어 오케스트레이션: 상위 에이전트가 §4.4 상태 머신을
  직접 밟되, `dik_checkpoint_hook.py`가 라운드 상한·승인 없는 진행을 결정적으로
  deny한다. 표시 의무(AGENTS.md)는 라운드 질문에도 동일 적용 — 질문 md 원문
  경로, 데이터/미니 결과 원문, artifacts 링크를 요약과 함께 제시한다.

### 4.6 질문 파일 resolver 계약

승인 검증 4곳(checkpoint_gate·stage_guard·dik_checkpoint_hook·qa/validate)은
공통 resolver로 질문 파일을 확정한다(Codex 교차검증 H3 반영).

- `question_ref.path` 허용 집합: {canonical R1 경로, 동일 prefix `.round2`
  경로} ∩ 해당 run의 `outputs/checkpoints/` 내부. 허용 집합 밖 경로는 위조로
  간주하고 차단한다.
- resolver는 파일의 `run_id`·`checkpoint_id`·`interview_loop.round` 일치,
  (R2면) `prior_round.answer_id` 존재와 유효 R2 체인(§4.1), R1보다 늦은
  `created_at` 순서를 검증한다.
- `apply_checkpoint_answer.py --question-file`도 기록 시점에 같은 허용 집합
  검사를 수행한다 — 임의 파일을 provenance 대상으로 삼을 수 없다.
- `approval_targets` sha256 검사(§5.2)는 resolver가 확정한 **최종 승인 질문
  파일** 기준으로 동작한다.

## 5. 정지점별 업그레이드 계약

모든 정지점 공통: 라운드 1 옵션에 조기 종료(승인) 옵션이 반드시 존재하고
recommended일 수 있다. 자유 질문 슬롯(`allow_free_text` + free_question 안내)은
전 정지점 라운드 공통이다. 아래는 정지점별 델타만 적는다.

### 5.1 data_profile — 탐색 문답 (가장 큰 델타)

- 라운드 1 옵션 구성(≤4): `현재 이해로 바로 진행`(승인·조기종료, 기존
  `continue_with_current_data` 유지) + 탐색 방향 후보 최대 3개
  (`explore_direction`, §6.1의 exploration_candidates에서 렌더, 각 옵션
  description에 미니 결과 1줄 요약 포함). 방향 옵션은 gate가 생성 시점에
  `continue_pipeline=false`로 강제한다(불변식 I1). 기존 `revise_scope`/
  `add_or_replace_data`는 라운드 1에서 옵션 수 초과 시 라운드 2와 자유 답변
  경로로 흡수한다 — 자유 답변(반려 의사)은 v1과 동일하게 계속 유효하다.
- 방향 선택 → 라운드 2: 선택 방향의 미니 결과 표(≤10행)를 질문 md에 내장하고
  `이 방향으로 분석 확정`(승인, `maps_to.frame_focus=<direction_id>`) /
  `방향 다시 선택`(반려) 옵션을 준다.
- 승인 답변의 `maps_to.frame_focus`는 frame stage 입력 계약이다: frame
  에이전트는 `checkpoint_answers.json`에서 frame_focus를 읽어 `03_frame.md`의
  분석 질문·비교축에 반영하고, 반영 근거를 명시한다.
- v1 checklist §8 미결 항목 "data_profile 질문이 grain·품질·전처리 필요성을 더
  잘 보여주는지"를 이 업그레이드가 흡수한다: companion 질문 슬롯에 grain/제외
  규칙 질문(§8)을 배치할 수 있고, 데이터 샘플 표시는 기존 `data_snapshot`
  계약을 그대로 쓴다.

### 5.2 analysis_strategy — KPI·비교축 문답

- 기존 옵션(승인/질문·지표 수정/방향 재선택/단순화)과 dependency 옵션 병합
  로직을 유지한다. 델타: 자유 질문 슬롯 + 라운드 2 + companion 질문(도메인
  mode에서 KPI 분모·비교군, §8).
- 자유 질문 예: "이 지표를 월별로도 볼 수 있어?" → 미니 쿼리 답변 후 라운드
  2에서 전략 확정.
- `approval_targets` sha256 잠금(v1 §7.2)은 라운드와 무관하게 최종 승인 답변
  기준으로 동작한다 — 라운드 2 승인이면 라운드 2 질문의 approval_targets가
  기준이며, gate가 라운드 2 파일 생성 시점에 최신 산출물로 재계산한다.
  검증 측(stage_guard·QA)은 §4.6 resolver가 확정한 같은 파일을 읽는다 —
  현행 코드는 R1 경로만 읽으므로 커밋 5에서 교정한다.

### 5.3 analysis_result_review — 결과 검토 문답 (조건부 유지)

- §9 술어와 발동 조건은 v1 그대로다. 단순 run에서는 발동하지 않는다.
- 델타: 자유 질문 슬롯("상위 5개만 다시 보여줘" 류 → 미니 쿼리) + 라운드 2
  (결론 수위 조정 확인). 기존 옵션(승인/수위 조정/기본 분석 전환)은 유지.
- 도메인 mode에서는 companion 질문으로 §8.3-4(결과가 업무적으로 말이 되는가)를
  수집하고, 그 답변이 `domain_intake.open_questions`/`forbidden_claims` 보강으로
  파생될 수 있다(§8).

### 5.4 dashboard_storyboard — 차트 결정 문답

- 기존 차트 추천표·디자인 프로필 3택·대안 사유 계약(AGENTS.md)은 이미
  선택지형이므로 유지한다. 델타: 자유 질문 슬롯(차트 관련 데이터 질문) +
  라운드 2(수정된 storyboard 재확인).
- v1 checklist §8 미결 항목 "단순 run에서 1차 결과 요약 포함"을 이 업그레이드가
  흡수한다: 단순 run(=`analysis_result_review` 미발동)에서는 라운드 1 질문
  `current_understanding`에 1차 결과 핵심 발견 요약을 포함해 이 정지점이 결과
  검토를 겸함을 명시한다.

### 5.5 report_outline — 보고서 계약 문답

- 델타: 자유 질문 슬롯 + 라운드 2 + companion 질문(§8.3-5: 독자별 용어, 문체,
  공개 범위, 피해야 할 표현 — 도메인 mode에서 `terminology`/`forbidden_claims`
  파생 입력).

## 6. 탐색 방향 후보와 미니 결과

### 6.1 exploration_candidates 계약

방향 후보와 미니 결과는 **explore stage 에이전트의 산출물**이다. 게이트
(결정적 코어, stdlib+jsonschema)는 계산하지 않고 렌더만 한다.

- 위치: `runs/<run-id>/outputs/exploration_candidates.json`
  (+ 사람이 읽는 `outputs/exploration/candidate_<id>.md` 미니 결과 표).
- 신규 schema `schemas/exploration_candidates.schema.json`:

```jsonc
{
  "schema_version": "data-insight-kit.exploration_candidates.v1",
  "run_id": "...",
  "created_at": "...",
  "candidates": [   // 정확히 2~3개
    {
      "id": "by_region",
      "label": "지역별로 나눠 보기",             // 사용자 표현 (§11 준수)
      "why_interesting": "...",                  // 탐색 근거 1~2문장
      "mini_result": {
        "summary": "상위 3개 구가 전체의 41%",   // 옵션 description용 1줄
        "table_path": "outputs/exploration/candidate_by_region.md",
        "computation": "지역 컬럼 groupby 건수 집계, 결측 제외",
        "source_columns": ["sido", "sigungu"],
        "row_count_used": 64231
      },
      "maps_to": {"frame_focus": "by_region"}
    }
  ]
}
```

- explore 에이전트 계약(`agents/explore.md` 갱신): profile/EDA 산출에 더해
  후보 2~3개를 반드시 만든다. 후보는 실제 데이터에서 계산한 미니 결과를
  가져야 하며, 계산 불가(권한/규모)면 그 후보를 제시하지 않는다.
- gate는 candidates가 없거나 schema 불일치면 방향 옵션 없이 v1형 질문으로
  강등하고 질문에 그 사실을 남긴다(런타임 도입이 기존 흐름을 깨지 않는 안전판).

### 6.2 미니 결과 렌더 규칙

- 옵션 description: `mini_result.summary` 1줄 + 방향 label.
- 질문 md: 후보별 표(≤10행)를 `read_text_snippet` 규칙으로 내장하고
  `artifacts[]`에 table_path를 추가한다(표시 의무 대상).
- 수치는 계산 결과 그대로 쓰고 해석 단정(원인·추천)은 금지 — v1 §10.2 언어
  게이트가 질문 파일에도 적용된다(기존 동작 유지).

## 7. 자유 질문 미니 쿼리 실행 경계

자유 질문은 "진짜 공동 탐색"과 "결정적 코어 철학"의 긴장 지점이므로 경계를
명시한다.

- 대상: 이번 run의 `input/` 스냅샷(및 explore가 만든 파생 산출물)만. 외부
  네트워크, 타 run, DB 신규 연결 금지(DuckDB는 v1 원칙 그대로 read-only 기존
  연결만).
- 연산: 조회·집계·필터·정렬·상위 N. 모델 학습, 신규 파일 다운로드, 설치 금지
  (설치는 기존 hook 게이트가 이미 deny).
- 산출물: `outputs/exploration/free_question_<checkpoint>_<n>.md` — 반드시
  포함: 사용자 질문 원문, 계산 방법 설명(사용 컬럼·필터·집계), 결과 표(≤20행),
  한계(결측·표본). 대응 provenance JSON
  `outputs/exploration/free_question_<checkpoint>_<n>.json`에
  `answer_id`(자유 질문 답변 레코드) 연결.
- 순서 강제: 자유 질문 답변 레코드(§4.3)가 미니 결과 파일보다 먼저 기록되어야
  한다. QA는 `answer_id` 연결과 타임스탬프 순서를 검증한다.
- 미니 쿼리 결과는 참고 자료다: 공식 분석 산출물(`04_analysis.md`,
  `dashboard_data.json`)에 직접 복사되지 않으며, 반영하려면 frame/analyze
  경로를 거친다(파이프라인 lineage 유지). 보고서·대시보드가 미니 결과 수치를
  직접 인용하면 QA WARN(대표 run 보정 후 BLOCK 승격 검토).

## 8. 도메인 인터뷰 런타임화 (§8.3 × §12.2)

### 8.1 lifecycle → 정지점 매핑

v1 spec §8.3의 5단계를 새 정지점 없이 매핑한다.

| §8.3 단계 | 정지점 | companion 질문이 수집하는 domain_intake 필드 |
|---|---|---|
| 1. 시작 전 | guided intake (기존) | domain_scope, objective |
| 2. 데이터 확인 후 | data_profile 라운드 | row_meaning, entity_grain, column_semantics, exclusion_rules |
| 3. 분석 전략 전 | analysis_strategy 라운드 | kpi_definitions(분모·단위·비교 기준), segments, reference_data, forbidden_claims |
| 4. 결과 검토 시 | analysis_result_review 라운드 | evidence_boundaries 보강, open_questions, 결론 수위 |
| 5. 보고서 전 | report_outline 라운드 | terminology(독자별), forbidden_claims 보강 |

### 8.2 domain_intake.json 파생 생성

- 답변 원천은 단일하다: companion 답변도 `checkpoint_answers.json`에만 쌓인다.
- 신규 `scripts/build_domain_intake.py`가 `maps_to.domain_field`를 가진 답변
  레코드에서 `input/domain_intake.json`을 **결정적으로 파생**한다.
  `domain_readiness.status`는 기존 재계산 규칙(v1 §8.5) 그대로 계산한다.
  파일에 `generated_by: build_domain_intake`, 근거 `answer_id` 목록을 남긴다.
- 기존 경로(사전 작성한 `domain_intake.json` 주입)는 계속 유효하다. 파생
  생성은 domain mode인데 파일이 없을 때의 새 기본 경로다. 두 경로가 겹치면
  주입 파일이 우선하고 인터뷰 답변은 `open_questions` 보강으로만 병합한다.
- domain pack 자동 수정 금지(v1 non-goal)는 불변 —
  `domain_pack_update_candidates.md` 경로만 쓴다.

### 8.3 readiness 기반 라운드 2 재질문 (§12.2 "질문 재시도")

- domain mode에서 라운드 1 companion 답변 후에도 readiness 공통 필수 항목이
  비면, gate가 라운드 2 companion 질문을 **부족 필드 우선**으로 채운다
  (결정적: 필수 필드 목록 − 채워진 필드, §8.1 매핑 내에서). 이 경로는 R2
  생성 트리거 (b)(§9)이며 `prior_round.trigger=domain_readiness_gap`을
  기록한다. R2 주 질문은 "부족 항목 보완 후 진행 여부" 재확인형으로 생성한다.
- 라운드 상한(D3) 안에서도 readiness가 `insufficient`면 진행은 막지 않되 기존
  v1 QA가 도메인 결론을 차단한다 — 인터뷰는 기회를 늘릴 뿐 게이트 자체는 v1
  그대로다.

## 9. 게이트·QA 확장

기존 v1 게이트(§10.1 유지 목록)는 전부 불변. 추가분만 적는다.

- `checkpoint_gate.py`: 라운드 2 생성은 결정적 트리거 2가지 중 하나로만 —
  (a) 최신 결정 레코드(companion 제외, §4.3)에 `loop_action` 존재,
  (b) domain mode이고 companion 반영 후 readiness 공통 필수 필드 잔존(§8.3). 라운드 3 생성 거부,
  exploration_candidates schema 검증 후 렌더, companion 질문 수 ≤2 강제,
  방향 옵션 `continue_pipeline=false` 강제 생성(I1).
- `stage_guard.py`: 정지점 승인 판정은 "최신 **주 질문** 답변의
  continue_pipeline + v3 provenance"다(§4.3 선택 계약, 라운드 무관). 추가:
  §4.6 resolver 검증(허용 집합 밖 경로·유효하지 않은 R2 체인은 위조로 차단),
  불변식 I1 위반 레코드 차단, `round3` 이상 파일 존재 시 차단,
  canonical/mirror 불일치 fail-closed(§4.3).
- `dik_checkpoint_hook.py`: 위 stage_guard 검증을 공유(단일 스크립트 원칙).
  라운드 질문 파일은 배포용 언어 게이트 대상. 미니 결과 파일은 사용자 질문
  원문을 그대로 인용하므로 언어 게이트 대상에서 제외한다(오탐 방지 — 구현 중
  정정). 대신 `record_free_question_result.py`가 고정 골격(질문·계산 방법·
  결과 표 ≤20행·한계·참고 자료 고지)으로만 작성하고 QA가 answer_id
  provenance를 검증한다. **v1.1 반영:
  kit run 컨텍스트에서 `uv add`는 승인 여부와 무관하게 전면 deny** —
  `uv sync --extra <allowlist>`만 유효 승인 시 허용(CHANGELOG 발견 3).
- `qa/validate.py` 추가 항목:
  - 유효 R2 체인(§4.1) 기준 사이클당 R2 ≤1, `round3+` 존재 시 BLOCK, 고아
    R2는 WARN.
  - 자유 질문 미니 결과의 `answer_id` 연결·순서(§7) 불일치 BLOCK.
  - 자유 질문 수 > 라운드당 1이면 BLOCK.
  - 불변식 I1 위반(companion·자유 질문·탐색 방향 레코드의
    `continue_pipeline=true`)은 BLOCK(게이트 우회 시도).
  - canonical/mirror `checkpoint_answers.json` 불일치 BLOCK(§4.3).
  - domain mode에서 파생 `domain_intake.json`의 `generated_by`/근거 answer_id
    무결성 검증, readiness 재계산 불일치 BLOCK(기존 규칙 확장).
  - 보고서·대시보드의 미니 결과 직접 인용 WARN(§7).
- `validate_user_facing_text.py` FORBIDDEN_TERMS 추가: `interview_loop`,
  `exploration_candidates`, `companion_question`, `free_question`,
  `mini_result`, `loop_action`, `frame_focus` — 사용자 표현은 "탐색 문답",
  "볼 만한 방향", "추가 확인 질문", "직접 질문", "미리 본 결과" 등을 쓴다.

## 10. §3 domain 문서 보강 (v1 이연분)

인터뷰 워크플로우 실물이 생기므로 v1에서 이연한 문서를 함께 작성한다
(v1 checklist §3 항목 그대로).

- `CUSTOMIZATION.md`: domain pack 중심 → domain expert interview 중심 보강.
- `domains/README.md`: run-local domain intake(파생 생성 포함)와 domain pack
  승격 흐름.
- `domains/template/interview-questions.md`: §8.1 매핑 기반 단계별 질문 구조.
- `domains/template/kpi-rules.md`: 분모·단위·비교 기준·evidence class 강화.
- `domains/template/qa-rules.md`: 도메인 과잉해석 BLOCK 예시.
- `domain_pack_update_candidates.md` 역할 문서화.

## 11. 하지 않을 일

- 새 정지점 추가, checkpoint prefix 재배열(v1 §15 불변).
- 라운드 3 이상, 정지점당 자유 질문 2개 이상(라운드당 1 유지).
- gate 스크립트에서의 데이터 계산(미니 결과는 에이전트 산출물, gate는 렌더만).
- 미니 쿼리의 외부 네트워크 접근·설치·타 run 참조.
- 미니 결과의 공식 산출물 직접 인용(파이프라인 lineage 우회).
- v3 답변 계약 필드 제거·변경(추가만 허용).
- domain pack 자동 수정, 산업별 전용 kit(v1 non-goal 유지).
- ECharts/Plotly renderer 확장(v4), 통계/ML 자동화 확대(v3).

## 12. 구현 순서 (커밋 플랜)

매 커밋 pytest green. 실제 설치·push 금지, runs/* 커밋 금지. 발견→수정은
CHANGELOG에 기록.

| # | 커밋 | 내용 |
|---|---|---|
| 1 | docs | 이 spec + checklist + kickoff 확정 기록 + CHANGELOG 진행 상태 |
| 2 | v1.1 | hook `uv add` 전면 deny + 회귀 테스트 (독립 소커밋) |
| 3 | schema | checkpoint_question v2 블록, exploration_candidates.schema.json, pipeline-contract 반영 |
| 4 | 런타임 코어 1 | apply_checkpoint_answer 라운드/companion/자유 질문, checkpoint_gate 라운드 생성·거부 |
| 5 | 런타임 코어 2 | stage_guard/hook: §4.6 resolver·I1·라운드 검증 + qa/validate round-aware lineage 최소 확장(R2 승인 인정·approval_targets 재계산) — 커밋 7 smoke의 전제 |
| 6 | data_profile 부착 | exploration_candidates 렌더, frame_focus 연결, agents/explore.md·frame.md 갱신 |
| 7 | 중간 smoke 게이트 | 단순 CSV run 실제 완주(탐색 문답 경로), 발견 수정 반영 |
| 8 | 나머지 정지점 | analysis_strategy/result_review/storyboard/report_outline 라운드·자유 질문 |
| 9 | 도메인 런타임 | companion domain_field, build_domain_intake.py, readiness 기반 재질문 |
| 10 | QA 확장 | qa/validate.py 확장 항목(자유 질문 수·순서, I1 전체, domain 무결성, 직접 인용 WARN, 고아 R2 WARN) + 테스트 |
| 11 | 문서 | §10 domain 문서 + README/GUIDE/SKILL/AGENTS 갱신 |
| 12 | 최종 검증 | smoke 3종(단순/statistical/domain) 재검증 + CHANGELOG 마감 |

커밋 7이 중간 게이트다: 여기서 런타임 결함이 나오면 8~9로 가기 전에 코어를
고친다(v1 마감 세션의 "대표 run 검증 후 확장" 원칙).

## 13. 완료 기준 (대표 run 시나리오)

| 시나리오 | 검증 경로 | 통과 기준 |
|---|---|---|
| 단순 CSV run | data_profile 탐색 문답(방향 선택→라운드 2→frame_focus 반영), storyboard가 1차 결과 요약 포함, 나머지 정지점 조기 종료 | 완주, qa/qa-post BLOCK 0, frame에 방향 반영 근거 존재 |
| statistical run | 기존 v1 경로(설치 승인·H2.5) + 결과 검토 라운드에서 자유 질문 1회(미니 쿼리 provenance) | 완주, BLOCK 0, 자유 질문 순서·연결 검증 통과 |
| domain run | domain_intake.json 없이 시작 → companion 답변으로 파생 생성 → readiness 재질문(라운드 2) → 도메인 게이트 기존 동작 | 완주, BLOCK 0, 파생 domain_intake 무결성 통과 |
| 회귀 | 조기 종료만 선택한 run이 v1 run과 동일한 산출물 흐름 | 기존 pytest 전체 green + legacy fixture BLOCK 유지 |
