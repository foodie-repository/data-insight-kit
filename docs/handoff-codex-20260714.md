# Codex 인수인계 — dashboard-profile-v4 마무리 + 다음 작업 (2026-07-14)

Claude Code 세션에서 Codex로 작업을 이관하기 위한 문서. 아래 "Codex 시작
프롬프트"를 그대로 붙여넣으면 된다.

## 단일 원천 (먼저 읽을 것)

| 문서 | 역할 |
|---|---|
| `data-insight-kit/CHANGELOG.md` 최상단 "진행 상태" | **재개 지점** — 어디까지 했고 다음이 무엇인지 |
| `data-insight-kit/AGENTS.md` | 운영 규칙 전부 (표시 의무·전달 순서(턴 분리)·눈검토 의무 포함) |
| `docs/specs/dashboard-profile-v4.md` + `-checklist.md` | v4 계약과 커밋 추적 (§7 최종 검증만 남음) |
| `docs/specs/dashboard-freeform-v5-kickoff-notes.md` | v5(자유 설계) 과제·품질 기준 |
| `docs/dashboard-design-system.md` "문구 규칙" | 직관 문구·변명 금지 원칙 |

## 필수 규칙 (요약 — 원문은 AGENTS.md)

- spec 우선(코드와 어긋나면 spec부터 수정), **매 커밋 pytest green**
  (`cd data-insight-kit && python3 -m pytest tests/ -q`, 현재 188 passed·126 subtests)
- **push 금지, runs/* 커밋 금지**, 실제 설치 금지(`uv add`는 훅이 deny)
- 체크포인트 대리 승인 금지 — 답변은 실제 사용자 발화만
  `apply_checkpoint_answer.py --source user_chat --user-response --transcript-ref`
- **전달 순서(턴 분리)**: 근거 원문(`checkpoint_gate.py <run> <cp> --print-existing`)을
  본문에 먼저 출력해 턴을 끝내고, 사용자가 읽은 뒤 다음 턴에 선택 수집.
  팝업 답변은 핸드오프 스탬프(handoff_log.json)가 선행해야 기록됨(fail-closed)
- **눈검토 의무**: 대시보드 정지점 전달 전 `outputs/qa_render_desktop.png`·
  `qa_render_mobile.png`를 직접 열어 보고 관찰 결과를 보고와 함께 전달
- fablize 진행 추적: 설치 환경에서 `FABLIZE_ROOT`를 설정한 뒤 repo 루트에서
  `python3 "${FABLIZE_ROOT}/scripts/goals.py" status`
  (v4 세트 G007 `commit8-smoke`만 in_progress — 완료 시 `--verify-cmd`/`--verify-evidence` 필수)

## 현재 상태 (2026-07-14)

- 브랜치 `dashboard-profile-v4`: 커밋 1~7 + smoke 발견 수정 5건 완료
  (전달 순서 턴 분리 규칙+3중 강제 장치, ops grid blowout·가짜 레일 수정,
  QA 카드 겹침 BLOCK, 렌더 스크린샷+눈검토 의무, 직관 문구·변명 금지 원칙)
- **smoke ①** `runs/apt-sale-v4-smoke-20260713` (서울 아파트 매매 월별,
  operations_monitor + contract v4): H1~H4 전부 실사용자 승인, 문구·레이아웃
  사용자 피드백 3회 반영(visualize 2회 재실행). E1 스파크+델타·E3 레일·E5
  그라데이션 체감 확인, E4는 이전 이터레이션에서 체감 확인(최종본은
  에이전트가 4선 비교 라인으로 재구성 — 계획-이행 QA 정상 작동 결과).
  마지막 구간(communicate→qa-post) 결과는 CHANGELOG 진행 상태 참조.
- 별도 브랜치 `kit-v2.1`(--domain-mode 플래그, cp949 preview) 병합 대기.
  master는 interview-loop-v2까지 병합됨(push는 사용자 결정).

## 다음 작업 (순서)

1. **smoke ②** — 스냅샷 강등 경로 (사용자 참여 필수):
   - 새 run 생성, input은 강남 상가 원본 재사용:
     `cp runs/sbiz-gangnam-domain-v2-smoke-20260712/input/sbiz_store_gangnam_20260708.parquet runs/<새-run-id>/input/`
   - 검증 목표: 시간 컬럼 없는 스냅샷에서 **trend/period_delta가 생성되지
     않고 플랫 KPI로 강등**되는지, benchmark 비교 의미가 왜곡되지 않는지
   - 진행 방식은 smoke ①과 동일: guided intake → H1~H4, 각 정지점마다
     근거 먼저(턴 분리)·눈검토 보고
2. **커밋 8 마감**: checklist §7 체크(전체 pytest·diff --check·schema 파싱·
   smoke ①②·CHANGELOG 마감·runs/* 미커밋), fablize G007 complete
3. **병합 검토** (사용자 결정 받기): kit-v2.1 → master, dashboard-profile-v4
   → master 순서. CHANGELOG 충돌은 사소(섹션 겹침)
4. **v5 kickoff 설계 인터뷰**: dashboard-freeform-v5-kickoff-notes.md의
   F-a~F-e + 품질 기준(차트 크기 위계·여백,
   `실습 파일/Part 2. 시각화 전략 자동 설계/ai-pipeline-kit/dashboard-sample.html`
   레퍼런스 분석, 태블로 강점 계승). 결정 확정 → spec/checklist 초안 →
   교차검증(다른 모델 계열) → 사용자 승인 → 커밋 단위 구현

## Codex 시작 프롬프트 (복사용)

```text
data-insight-kit 작업을 이어받는다. 먼저 다음을 순서대로 읽어라:
1) data-insight-kit/docs/handoff-codex-20260714.md (이 문서 — 인수인계 전체)
2) data-insight-kit/CHANGELOG.md 최상단 "진행 상태" (재개 지점)
3) data-insight-kit/AGENTS.md (운영 규칙 — 표시 의무·턴 분리·눈검토 의무)

규칙: spec 우선, 매 커밋 pytest green(cd data-insight-kit && python3 -m pytest tests/ -q),
push 금지, runs/* 커밋 금지, 체크포인트 대리 승인 금지(실제 사용자 답변만 기록),
정지점마다 근거 원문을 먼저 보여주고 턴을 끝낸 뒤 다음 턴에서 선택을 받는다.
대시보드 정지점 전달 전에는 outputs/qa_render_*.png를 직접 보고 관찰 결과를 보고한다.

다음 작업 1번(smoke ② — 스냅샷 강등 경로)부터 시작하되, 시작 전에 CHANGELOG
진행 상태에서 smoke ① 마감 여부를 확인하고 미완이면 그것부터 마감하라.
진행 순서와 상세 조건은 인수인계 문서의 "다음 작업" 절을 따른다.
```
