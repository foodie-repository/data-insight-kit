# data-insight-kit

`data-insight-kit`은 표 데이터를 받아 사용자와 단계적으로 의도를 확인하면서
분석 보고서와 데이터 주입형 대시보드를 만드는 범용 분석 키트입니다.

특정 업종이나 업무 도메인에 고정된 도구가 아닙니다. 기본 core는 CSV,
Parquet, Excel, JSON, API 스냅샷, 선택 DuckDB를 같은 방식으로 받아들이고,
회사나 업무별 판단 기준은 선택적인 `domain pack`으로 추가합니다.

## 언제 쓰나요?

- 데이터 파일은 있는데 어떤 분석 질문으로 시작해야 할지 모를 때
- 대시보드와 보고서를 한 번에 만들되, 중간에 사용자의 의도를 계속 확인하고 싶을 때
- 단순 상위 순위표가 아니라 분포, 변화, 차이, 예외, 한계를 함께 보고 싶을 때
- 회사나 팀 도메인에 맞는 KPI, 용어, 금지 표현, 보고서 기준을 재사용하고 싶을 때

## 어떻게 동작하나요?

```text
사용자 요청
  -> 질문형 intake
  -> 데이터 연결과 탐색
  -> 데이터 확인
  -> 분석 방향 확인
  -> 분석과 차트 설계
  -> 대시보드 구성안 확인
  -> 대시보드 생성과 QA
  -> 보고서 구성안 확인
  -> 보고서 작성과 QA
```

핵심은 **끝까지 자동으로 밀어붙이지 않는 것**입니다. 기본 실행은 다음 네 번의
중간 확인을 만듭니다.

| 확인 단계 | 사용자가 결정하는 것 |
|---|---|
| 데이터 확인 | 데이터 범위, 샘플, 품질, 분석 가능/불가능 범위가 맞는지 |
| 분석 방향 확인 | 어떤 질문, KPI, 비교 기준으로 볼지 |
| 대시보드 구성안 확인 | 어떤 데이터로 어떤 차트를 만들고 어떤 흐름으로 보여줄지 |
| 보고서 구성안 확인 | 독자, 깊이, 문체, 결론 수위가 맞는지 |

각 단계는 쉬운 검토 요약과 채팅용 질문을 만들고 멈춥니다. 사용자의 실제 답변이
기록되어야 다음 단계로 넘어갑니다.

## 빠른 시작

AI 앱에서 시작할 때는 먼저 계획/승인 흐름을 사용합니다.

- Codex Desktop: **Plan Mode**를 켜고 짧게 요청합니다.
- Claude Code: **Plan Mode**를 켜고 사용자용 분석 기획안과 실행 계획을 먼저
  확인한 뒤 `/run-pipeline <run-id>`를 실행합니다.

```text
이 데이터로 분석 보고서와 대시보드를 만들어줘.
```

CLI에서 직접 실행할 때는 `--guided-intake`를 사용합니다.

```bash
cd data-insight-kit
mkdir -p runs/my-run/input
cp /path/to/data.csv runs/my-run/input/

DIK_USER_REQUEST="이 데이터로 분석 보고서와 대시보드를 만들어줘" \
  bash scripts/run_codex_pipeline.sh my-run --guided-intake
```

질문 파일이 생성되면 답변을 draft에 누적하고 같은 명령을 다시 실행합니다.

```bash
python3 scripts/apply_intake_answer.py my-run --option <option-id>
bash scripts/run_codex_pipeline.sh my-run --guided-intake
```

중간 확인 단계에서 멈추면 사용자의 실제 답변을 기록합니다.

```bash
python3 scripts/apply_checkpoint_answer.py my-run data_profile \
  --option continue_with_current_data \
  --source user_chat \
  --user-response "샘플과 범위가 맞으니 이 기준으로 진행"
```

자세한 튜토리얼은 [GUIDE.md](GUIDE.md)를 보세요.

## 입력 데이터

가장 단순한 입력은 `runs/<run-id>/input/` 아래의 파일입니다.

```text
runs/<run-id>/input/
  data.csv
  data.parquet
  data.xlsx
  data.json
```

API URL을 줄 수도 있습니다. 이 경우에도 바로 분석하지 않고, 먼저 인증,
응답 형식, 페이지 수집, 행 수를 확인한 뒤 로컬 스냅샷으로 고정합니다. 인증이나
쿼터가 막히면 대체 데이터를 꾸미지 않고 원천 수집 문제로 멈춥니다.

고급 사용자는 DuckDB를 선택 입력으로 쓸 수 있습니다. DuckDB는 필수가 아닙니다.

입력 계약은 [docs/source-adapters.md](docs/source-adapters.md)를 기준으로 합니다.

## 산출물

성공한 run은 보통 다음 파일을 만듭니다.

```text
runs/<run-id>/outputs/01_profile.md
runs/<run-id>/outputs/02_eda.md
runs/<run-id>/outputs/03_frame.md
runs/<run-id>/outputs/04_analysis.md
runs/<run-id>/outputs/chart_spec.json
runs/<run-id>/outputs/dashboard_data.json
runs/<run-id>/outputs/dashboard.html
runs/<run-id>/outputs/summary_report.md
runs/<run-id>/outputs/deep_report.md   # deep 보고서 선택 시
```

`chart_spec.json`은 질문, 방법론, 계산, 차트 선택을 고정하는 분석 설계서입니다.
`dashboard_data.json`은 렌더러가 읽는 정식 데이터 계약입니다. 대시보드는 이
데이터를 읽어 순수 SVG로 렌더링합니다.

## QA

대시보드와 보고서는 QA를 통과해야 완료로 봅니다.

```bash
python3 qa/validate.py runs/my-run/outputs/dashboard_data.json \
  --chart-spec runs/my-run/outputs/chart_spec.json

python3 qa/validate.py runs/my-run/outputs/dashboard_data.json \
  --chart-spec runs/my-run/outputs/chart_spec.json \
  --no-render --post-communicate
```

QA는 스키마, 차트 데이터, 렌더링, 라벨 겹침, 빈 차트, 보고서 깊이, 근거 누락을
확인합니다. BLOCK이 있으면 완료가 아닙니다.

## 범용 core와 domain pack

기본 core는 도메인 독립적입니다. 특정 회사나 업무 도메인에서 자주 쓰는 기준이
있다면 `domains/template/`을 복사해 domain pack을 만듭니다.

```bash
cp -R domains/template domains/my-domain

DIK_DOMAIN_PACK=domains/my-domain/domain.yaml \
  DIK_USER_REQUEST="이 데이터로 분석 보고서와 대시보드를 만들어줘" \
  bash scripts/run_codex_pipeline.sh my-run --guided-intake
```

domain pack은 용어, KPI 후보, 질문 후보, 차트 흐름, 보고서 기준, 금지 표현을
제공합니다. 다만 core 계약, 스키마, QA를 대체하지 않으며, 도메인 기준이 결론을
바꾸는 경우에도 중간 확인 단계에서 사용자가 승인해야 합니다.

자세한 내용은 [CUSTOMIZATION.md](CUSTOMIZATION.md)와
[domains/README.md](domains/README.md)를 보세요.

## 문서 구조

| 문서 | 용도 |
|---|---|
| [GUIDE.md](GUIDE.md) | 처음 사용하는 사람을 위한 튜토리얼 |
| [CUSTOMIZATION.md](CUSTOMIZATION.md) | 회사·업무 도메인에 맞게 확장하는 방법 |
| [docs/pipeline-contract.md](docs/pipeline-contract.md) | stage, checkpoint, I/O, QA의 단일 기준 |
| [docs/user-facing-planning.md](docs/user-facing-planning.md) | 사용자에게 보여줄 기획안 작성 기준 |
| [docs/analysis-strategy-library.md](docs/analysis-strategy-library.md) | 데이터 유형별 분석 전략 |
| [docs/report-quality-rubric.md](docs/report-quality-rubric.md) | 보고서 품질 기준 |
| [docs/teaching/](docs/teaching/) | 강의·설명용 보조 자료. 배포용 시작점은 아님 |

## 런타임

`data-insight-kit`은 Codex CLI wrapper와 Claude Code plugin 어댑터를 함께 제공합니다.
둘 다 같은 `docs/pipeline-contract.md`를 기준으로 움직입니다.

Codex Desktop:

```text
Plan Mode를 켠 뒤 "이 데이터로 분석 보고서와 대시보드를 만들어줘"처럼 요청
```

Claude Code:

```text
Plan Mode를 켠 뒤 사용자 요청과 실행 계획을 먼저 확인하고,
승인 후 /run-pipeline <run-id> 실행
```

Codex CLI:

```bash
bash scripts/run_codex_pipeline.sh <run-id>
bash scripts/run_codex_pipeline.sh <run-id> --guided-intake
bash scripts/run_codex_pipeline.sh <run-id> --dry-run
```

Claude Code plugin 설치:

```text
/plugin marketplace add /path/to/data-insight-kit
/plugin install data-insight-kit
```

어떤 런타임을 쓰더라도 기본 원칙은 같습니다. 첫 요청은 사용자용 분석 기획안과
질문으로 시작하고, 데이터 확인·분석 방향·대시보드 구성안·보고서 구성안은
사용자의 실제 답변이 있어야 다음 단계로 넘어갑니다.

## 보안과 파일 관리

- `runs/*`는 사용자별 로컬 산출물이며 배포 core에 포함하지 않습니다.
- `.env`, API 키, DB 경로, 비공개 원천 데이터는 커밋하지 않습니다.
- 원격 또는 API 데이터는 필요한 범위만 스냅샷으로 고정하고 출처와 조회 시점을 남깁니다.
- 기존 사용자의 산출물을 덮어쓰지 않기 위해 새 작업은 새 `run-id`로 시작합니다.

## 라이선스

MIT.
