# 모델 티어 매핑

단계별 **사고 강도**를 3티어로 나누고, 런타임별 모델·추론강도를 매핑한다.
런타임 어댑터는 이 표만 참조한다 (Claude `model:`과 Codex/OpenAI `model + effort` 정책을 다른 문서에 흩뜨리지 않는다).

## 티어 원칙

모델 체급이 **출력 품질을 실제로 바꾸는 곳**에만 상위 모델을 쓴다.
- **사고두뇌(explore→frame→analyze)** 에서만 품질이 복리로 커진다 → 상위 모델.
- **실행·작성(connect·visualize·communicate)** 은 가드레일(스키마·QA)과 중급 모델로 충분 — 상위 모델 한계이득 작음.
- **경량(intake·qa)** 은 분류·스크립트 실행이라 하위 모델로 충분.

## 매핑

| 티어 | 단계 | Claude — quality | Claude — budget | Codex/OpenAI — quality | Codex/OpenAI — budget |
|------|------|:---:|:---:|:---:|:---:|
| 경량 | intake, qa | haiku | haiku | `gpt-5.5` + effort **low** | `gpt-5.4-mini` + effort **low** |
| 실행 | connect, visualize, communicate | sonnet | sonnet | `gpt-5.5` + effort **medium** | `gpt-5.5` + effort **medium** |
| 사고 | explore, frame, analyze | **opus** | sonnet | `gpt-5.5` + effort **high** | `gpt-5.5` + effort **medium** |

- **기본 Codex/OpenAI 모델**: `gpt-5.5`. `scripts/run_codex_pipeline.sh`는 `DIK_MODEL`이 없으면 이 값을 쓴다.
- **xhigh**(Codex/OpenAI): 모호한 KPI·충돌 증거·반복 실패·고위험 결정일 때만 사고 단계에 한시 적용.
- **gpt-5.4-mini**(Codex/OpenAI): 비용 절감 시 경량 단계 대안. 분석·프레이밍·최종 보고서 기본값으로 쓰지 않는다.
- **spark**(`gpt-5.3-codex-spark`): preview·Pro 전용. 빠른 초안용 선택 프로파일로만, fallback 필수.

## 런타임별 적용 방법

**Claude Code**: `agents/<stage>.md` frontmatter `model:` 에 위 값. quality/budget 두 프로파일은 frontmatter 기본을 quality로 두고, budget은 문서로 안내(또는 사용자가 frontmatter 교체).

**Codex/OpenAI**: frontmatter 자동적용이 없으므로 wrapper가 모델과 effort를 단계별 `codex exec` 호출에 부여한다 (`scripts/run_codex_pipeline.sh`).
```bash
DIK_MODEL=gpt-5.5 bash scripts/run_codex_pipeline.sh <run-id> --dry-run
```
기본 모델은 `DIK_MODEL` 환경변수로 바꾼다.
```bash
DIK_MODEL=gpt-5.5 bash scripts/run_codex_pipeline.sh <run-id>
```
또는 `--profile <name>`으로 `$CODEX_HOME/<name>.config.toml` 레이어링.
가용 모델·effort는 `codex debug models`로 확인(사양 변동 가능 — none/minimal은 기본값으로 박지 않는다).

## 근거
- 강사 키트는 분석 전 단계를 haiku로 묶어 인사이트 깊이를 깎았음(병목). 사고두뇌에만 투자하는 게 품질·비용 최적.
- Codex 최신·기본 = gpt-5.5(기본 effort medium, 지원 low/medium/high/xhigh) — 로컬 codex-cli 0.137.0 + 공식문서 확인(2026-06).
