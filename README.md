# data-insight-kit

`data-insight-kit`은 표 데이터를 받아 사용자와 단계적으로 의도를 확인하면서
분석 보고서와 데이터 주입형 대시보드를 만드는 범용 분석 키트입니다.

특정 업종이나 업무 도메인에 고정된 도구가 아닙니다. 기본 core는 CSV,
Parquet, Excel, JSON, API 스냅샷, 선택 DuckDB를 같은 방식으로 받아들이고,
회사나 업무별 판단 기준은 선택적인 `domain pack`으로 추가합니다.

## 설치와 준비

처음 사용할 때는 저장소를 받은 뒤 `data-insight-kit/` 폴더에서 시작합니다.

공통 요구사항은 Python 3.11 이상, Git, Bash 실행 환경입니다. macOS와 Linux는
기본 터미널에서 바로 시작할 수 있고, Windows는 **Git Bash** 또는 **WSL** 사용을
권장합니다. PowerShell만 사용할 경우 `bash scripts/...` 형태의 실행이 막힐 수
있습니다.

macOS/Linux:

```bash
git clone <repo-url>
cd <repo>/data-insight-kit
python3 --version
bash scripts/run_codex_pipeline.sh _install-check --dry-run
```

Windows(Git Bash 또는 WSL):

```bash
git clone <repo-url>
cd <repo>/data-insight-kit
python --version
bash scripts/run_codex_pipeline.sh _install-check --dry-run
```

Windows에서 `python` 명령이 잡히지 않으면 Python 설치 후 PATH 설정을 확인하거나
Python Launcher가 있는 환경에서 `py -3 --version`으로 버전을 확인합니다. 별도
패키지 설치가 필요한 데이터 형식이나 커넥터를 사용하는 경우에는 해당 프로젝트
환경에서 의존성을 준비합니다.

AI 앱에서 사용할 때는 실행 전에 계획/승인 흐름을 켭니다.

- Codex Desktop: **Plan Mode**를 켠 뒤 짧게 요청합니다.
- Claude Code: **Plan Mode**에서 사용자용 분석 기획안과 실행 계획을 먼저
  확인한 뒤 `/run-pipeline <run-id>`를 실행합니다.
- 터미널/CLI: `--guided-intake`를 붙여 질문형 흐름을 사용합니다.

API 키, DB 경로, 사내 데이터 경로가 필요하면 값을 문서나 명령어에 직접 쓰지
말고 `connectors/.env`에 둡니다.

```bash
cp connectors/.env.example connectors/.env 2>/dev/null || touch connectors/.env
```

예시는 변수명만 남기고 값은 로컬에서만 채웁니다.

```text
PUBLIC_DATA_API_KEY=
DATA_GO_KR_SERVICE_KEY=
SEOUL_OPEN_API_KEY=
DIK_DUCKDB_PATH=
```

실행 산출물은 `runs/<run-id>/` 아래에 만들어지며, 이 폴더는 로컬 전용입니다.
Repo에 분석 이력이나 비공개 데이터가 올라가지 않도록 기본적으로 ignore됩니다.

새 `run-id`로 시작하는 분석은 기본적으로 **새 분석**으로 처리됩니다. 같은
데이터를 다시 분석하더라도 기존 `runs/*`의 대시보드, 보고서, 차트 설계를
자동으로 참고하지 않습니다. 이전 결과를 일부 수정하거나 비교하고 싶다면
"이전 run을 참고해서", "기존 대시보드를 수정해서", "지난 분석과 비교해서"처럼
명시적으로 요청합니다.

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
| 대시보드 구성안 확인 | 어떤 데이터로 어떤 차트를 만들고, 어떤 화면 스타일로 보여줄지 |
| 보고서 구성안 확인 | 독자, 깊이, 문체, 결론 수위가 맞는지 |

각 단계는 쉬운 검토 요약과 채팅용 질문을 만들고 멈춥니다. 사용자의 실제 답변이
기록되어야 다음 단계로 넘어갑니다.

## 분석 깊이와 도메인 전문가 확인

`data-insight-kit`은 대시보드만 빨리 만드는 도구가 아니라, 분석가의 사고 절차를
따라갑니다. `분석 방향 확인` 단계에서 데이터와 목적에 맞춰 분석 깊이를 추천합니다.

| 사용자 표현 | 무엇을 하는가 | 내부 route |
|---|---|---|
| 기본 현황 파악 | 무엇이 많고 적은지, 분포는 어떤지 요약 | `descriptive` |
| 진단 확인 | 어떤 세그먼트가 두드러지는지, 예외는 무엇인지 확인 | `diagnostic` |
| 통계적 확인 | 차이나 관계가 우연인지 통계적으로 확인 | `statistical` |
| 패턴 탐색 | 자연스럽게 묶이는 그룹이나 이상치 탐색 | `ml_exploratory` |
| 예측 후보 확인 | 예측 가능한 대상과 검증 조건 확인 | `predictive` |
| 실험/효과 검토 | 조치 전후 변화나 처리 효과 검토 | `causal_experiment` |

데이터 조건(비교군, 표본 수, 분모, 타깃 등)이 부족하면 심화 route는 자동으로
기본/진단 수준으로 낮아지고, 낮춘 이유가 산출물에 기록됩니다.

통계/패턴 탐색 분석에는 추가 분석 기능(`scipy`, `statsmodels`, `scikit-learn` 등)이
필요할 수 있습니다. 이 기능은 사용자가 `분석 방향 확인` 단계에서 명시적으로
승인해야만, data-insight-kit 전용 가상환경(`.venv`)에만 설치됩니다. 승인하지
않으면 설치하지 않고 기본/진단 분석으로 진행합니다. 워크스페이스 전역 Python
환경에는 어떤 경우에도 설치하지 않습니다.

통계/패턴 탐색/예측/실험 분석이거나, 회사·업무 도메인 데이터이거나, 심층 검토
보고서를 만들거나, 후보·우선순위를 정하는 의사결정형 분석이면 `대시보드 구성안
확인` 전에 **1차 결과 확인** 단계가 한 번 더 추가됩니다. 1차 발견이 목적과
맞는지, 결론 수위를 낮춰야 하는지 확인한 뒤에만 대시보드로 넘어갑니다. 이 단계는
조건이 맞을 때만 나타나며, 조건은 kit이 매번 다시 계산합니다.

회사나 업무 도메인 데이터(내부 용어, 코드값, 제외 규칙, KPI 기준이 필요한
데이터)에서는 도메인 전문가에게 필요한 정보를 단계별로 짧게 확인합니다. 확인이
부족하면 도메인 결론(추천, 원인, 성과, 위험도 확정)은 만들지 않고 일반 구조
분석만 제공합니다.

## 탐색 문답: 결재가 아니라 함께 좁히기

각 확인 단계는 완성안을 승인만 받는 결재가 아니라 짧은 문답입니다(단계당 최대
2회). 데이터 확인 단계에서는 kit이 실제 데이터에서 미리 계산한 "볼 만한 방향"
2~3개를 미리 본 결과와 함께 제시하고, 방향을 고르면 그 방향이 분석 질문과 비교
기준에 반영됩니다. 어느 단계에서든 데이터에 대해 직접 질문(단계당 1회)을 하면
확인 결과를 본 뒤 이어서 결정할 수 있습니다. 회사·업무 데이터라면 행의 의미,
제외 기준, 지표 계산 기준 같은 추가 확인 질문이 함께 나오고, 답변이 쌓이면
도메인 확인 정보로 정리되어 해석 기준에 반영됩니다.

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

`my-run`처럼 새 run으로 시작하면 이전 분석 산출물은 자동 재사용하지 않습니다.
원천 데이터나 이번 run의 `input/` 스냅샷을 기준으로 데이터 확인 단계부터 다시
진행합니다.

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
runs/<run-id>/outputs/dashboard_layout.json       # v5 자유 레이아웃
runs/<run-id>/outputs/dashboard_data.json
runs/<run-id>/outputs/dashboard.html
runs/<run-id>/outputs/dashboard_build_manifest.json # v5 compiler 재현 기록
runs/<run-id>/outputs/qa_render_desktop.png          # v5.1 시각 QA
runs/<run-id>/outputs/qa_render_compact.png
runs/<run-id>/outputs/qa_render_mobile.png
runs/<run-id>/outputs/qa_render_narrow.png
runs/<run-id>/outputs/visual_review.json             # screenshot 눈검토 기록
runs/<run-id>/outputs/summary_report.md
runs/<run-id>/outputs/deep_report.md   # deep 보고서 선택 시
```

`chart_spec.json`은 질문, 방법론, 계산, 차트 선택을 고정하는 분석 설계서입니다.
`dashboard_data.json`은 렌더러가 읽는 정식 데이터 계약입니다. legacy/v4는
기존 순수 SVG 템플릿으로 렌더링합니다. v5는 storyboard에서 승인한
`dashboard_layout.json`을 함께 읽어 로컬 ECharts chart와 SVG/CSS component를
결정적으로 조립합니다.

대시보드 화면은 기본적으로 세 가지 프로필 중 하나를 고릅니다.

- `요약형 화면`: 핵심 KPI, 큰 메인 차트, 1-2개 보조 차트를 빠르게 공유할 때
- `탐색형 화면`: 세그먼트, 예외, 관계, 표와 진단 차트를 더 촘촘히 살펴볼 때
- `모니터링형 화면`: 반복 지표, 전 기간 대비, 상태 변화를 꾸준히 추적할 때

상세 기준은 [docs/dashboard-design-system.md](docs/dashboard-design-system.md)를
확인하세요.

### 렌더러 routing

| 경로 | 선택 조건 | layout | 렌더 방식 | 실패 처리 |
|---|---|---|---|---|
| legacy | chart/data contract 없음 | 금지 | 기존 탭형 순수 SVG | 기존 QA |
| v4 | chart/data contract 모두 `v4` | 금지 | 프로필별 순수 SVG | 기존 QA |
| v5 | chart/data contract 모두 `v5` | 승인된 파일 필수 | 로컬 ECharts 6.1.0 + SVG/CSS | 누락·불일치 시 BLOCK, fallback 금지 |

v5.1은 별도 renderer나 별도 kit가 아닙니다. v5 chart/layout이 품질 계약을 함께
선언하면 계획 품질(판단·지표 역할·질문·데이터 충분성)과 시각 품질(문구·척도·색·
라벨·범례·반응형)을 더 엄격하게 검사하는 opt-in입니다. 설계 단일 원천은
[visual-quality-convergence-v5.1](docs/specs/visual-quality-convergence-v5.1.md)입니다.
두 snapshot/time-series smoke의 v5 대비 결과와 trade-off는
[v5-v51-smoke-comparison](docs/v5-v51-smoke-comparison.md)에 기록했습니다.

v5 compiler를 직접 재현할 때는 다음 명령을 사용합니다. 평소 guided wrapper는
승인된 v5 run에서 이 명령을 자동으로 호출합니다.

```bash
python3 scripts/render_dashboard_v5.py \
  --chart-spec runs/my-run/outputs/chart_spec.json \
  --layout runs/my-run/outputs/dashboard_layout.json \
  --data runs/my-run/outputs/dashboard_data.json \
  --output runs/my-run/outputs/dashboard.html
```

## QA

대시보드와 보고서는 QA를 통과해야 완료로 봅니다.

```bash
python3 qa/validate.py runs/my-run/outputs/dashboard_data.json \
  --chart-spec runs/my-run/outputs/chart_spec.json

# v5는 승인된 layout을 명시합니다.
python3 qa/validate.py runs/my-run/outputs/dashboard_data.json \
  --chart-spec runs/my-run/outputs/chart_spec.json \
  --layout runs/my-run/outputs/dashboard_layout.json

python3 qa/validate.py runs/my-run/outputs/dashboard_data.json \
  --chart-spec runs/my-run/outputs/chart_spec.json \
  --no-render --post-communicate
```

QA는 스키마, 차트 데이터, 렌더링, 라벨 겹침, 빈 차트, 보고서 깊이, 근거 누락을
확인합니다. v5는 추가로 layout 교차계약, compiler manifest/checksum과 browser
렌더를 검사합니다. v5.1은 desktop 1440px, compact 736px, mobile 390px, narrow
320px screenshot을 모두 만들고, 오케스트레이터가 직접 본 관찰과 현재 파일
hash를 `outputs/visual_review.json`에 기록합니다. `status=pass`가 아니거나 렌더가
바뀌어 hash가 달라지면 다음 checkpoint로 넘어갈 수 없습니다. BLOCK이 있으면
완료가 아닙니다.

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
| [docs/v5-v51-smoke-comparison.md](docs/v5-v51-smoke-comparison.md) | v5와 v5.1 두 smoke의 이전·이후 품질 비교 |
| [docs/agent-guide/](docs/agent-guide/) | 에이전트 역할과 파이프라인 구조 설명 자료 |

## 런타임

`data-insight-kit`은 Codex와 Claude Code에서 같은 제품 본체를 사용합니다. 플랫폼별
패키지는 core를 복제하는 새 별도 kit가 아니라 manifest·hook·공유 skill만 잇는
**얇은 어댑터**입니다. 둘 다 같은 `docs/pipeline-contract.md`, schema, validator,
standalone HTML renderer를 사용하며 특정 플러그인 widget runtime에 의존하지
않습니다.

Codex Desktop:

```text
Plan Mode를 켠 뒤 "이 데이터로 분석 보고서와 대시보드를 만들어줘"처럼 요청
```

`data-insight-kit`을 워크스페이스로 열면 `.codex/hooks.json`의 Codex
PreToolUse 훅이 활성화됩니다. 처음 한 번 Codex가 hook trust를 요청하면
`/hooks`에서 신뢰해야 합니다. 이 훅은 Plan 승인만으로 중간 checkpoint를
통과한 것처럼 처리하지 못하게 막고, 실제 사용자 답변이
`scripts/apply_checkpoint_answer.py`로 `checkpoint-answer.v3` provenance와 함께
기록되기 전에는 `chart_spec.json`, `dashboard_data.json`, 보고서 산출물, run-local
builder 실행을 차단합니다.

Codex plugin 설치:

```bash
codex plugin marketplace add /path/to/data-insight-kit
codex plugin add data-insight-kit@data-insight-kit
```

공개 v0.2.1 배포본을 설치할 때는 tag를 고정합니다.

```bash
codex plugin marketplace add foodie-repository/data-insight-kit --ref v0.2.1
codex plugin add data-insight-kit@data-insight-kit
```

설치 후 `@data-insight-kit` 또는 data-insight-kit skill로 시작합니다. plugin은
공유 `skills/run-pipeline/SKILL.md`와 `.codex/hooks.json`을 통해 같은 core와
checkpoint gate를 사용합니다.

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
/plugin install data-insight-kit@data-insight-kit
```

터미널에서 공개 배포본을 설치할 때는 다음 명령을 사용합니다.

```bash
claude plugin marketplace add foodie-repository/data-insight-kit
claude plugin install data-insight-kit@data-insight-kit
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
