# GUIDE.md

이 문서는 `data-insight-kit`을 처음 사용하는 사람이 데이터에서 분석 보고서와
대시보드까지 만드는 과정을 설명합니다.

## 1. 설치와 폴더를 준비합니다

먼저 `data-insight-kit` 저장소를 로컬에 준비합니다. Git을 사용할 수 있다면
저장소를 클론하고, 아니면 ZIP으로 내려받아 압축을 풀어도 됩니다.

공통 요구사항:

- Python 3.11 이상
- Git
- Bash 실행 환경

macOS와 Linux는 기본 터미널에서 바로 시작할 수 있습니다.

```bash
git clone <repo-url>
cd <repo>/data-insight-kit
python3 --version
bash scripts/run_codex_pipeline.sh _install-check --dry-run
```

Windows 사용자는 Git Bash 또는 WSL을 권장합니다. PowerShell만 사용할 경우
`bash scripts/...` 형태의 실행이 막힐 수 있습니다. 아래 명령은 Git Bash 또는
WSL 기준입니다.

```bash
git clone <repo-url>
cd <repo>/data-insight-kit
python --version
bash scripts/run_codex_pipeline.sh _install-check --dry-run
```

Windows에서 `python` 명령이 잡히지 않으면 Python 설치 후 PATH 설정을 확인하거나,
Python Launcher가 있는 환경에서 다음 명령으로 버전을 확인합니다.

```bash
py -3 --version
```

이미 `git clone`을 했거나 ZIP 파일을 내려받아 압축을 풀었다면, 새로
`git clone`하지 않아도 됩니다. 터미널에서 `data-insight-kit/` 폴더로 이동한
뒤 설치 확인만 실행합니다.

macOS/Linux:

```bash
cd data-insight-kit
python3 --version
bash scripts/run_codex_pipeline.sh _install-check --dry-run
```

Windows(Git Bash 또는 WSL):

```bash
cd data-insight-kit
python --version
bash scripts/run_codex_pipeline.sh _install-check --dry-run
```

`--dry-run`은 실제 분석 산출물을 만들기 전에 스크립트가 실행 가능한지 확인하는
용도입니다. 여기서 막히면 먼저 Python 경로, 셸 권한, 저장소 위치를 확인합니다.

API, 외부 데이터, DuckDB를 쓰는 경우에는 비밀값을 명령어에 직접 쓰지 말고
`connectors/.env`에 둡니다.

```bash
cp connectors/.env.example connectors/.env 2>/dev/null || touch connectors/.env
```

예를 들어 필요한 변수명만 만들고 값은 로컬에서 채웁니다.

```text
PUBLIC_DATA_API_KEY=
DATA_GO_KR_SERVICE_KEY=
SEOUL_OPEN_API_KEY=
DIK_DUCKDB_PATH=
```

데이터 파일은 run별 입력 폴더에 둡니다. 처음에는 작은 CSV나 샘플 파일 하나로
시작하는 편이 좋습니다.

```bash
mkdir -p runs/my-first-run/input
cp /path/to/data.csv runs/my-first-run/input/
```

`runs/`는 로컬 실행 산출물 폴더입니다. 분석 중간 파일, 대시보드, 보고서,
체크포인트 답변이 여기에 쌓이며, 기본적으로 Repo에는 포함되지 않습니다.

새 run은 기본적으로 새 분석입니다. 같은 데이터로 다시 실행하더라도 기존
`runs/*`의 보고서, 대시보드, 차트 설계를 자동으로 참고하지 않습니다. 이전
결과를 고치거나 비교하려면 "이전 run을 참고해서 수정", "지난 분석과 비교"처럼
명시적으로 요청합니다.

## 2. 먼저 실행 환경을 고릅니다

`data-insight-kit`은 Codex와 Claude Code 양쪽에서 사용할 수 있습니다. 두
환경 모두 핵심 원칙은 같습니다. 처음부터 바로 끝까지 만들지 않고, 먼저
사용자용 분석 기획안을 확인한 뒤 진행합니다.

Codex Desktop과 Claude Code에서 시작할 때는 먼저 **Plan Mode**를 켜고 짧게
요청합니다.

```text
이 데이터로 분석 보고서와 대시보드를 만들어줘.
```

Plan Mode에서 받은 첫 질문 답변은 최종 계약이 아니라 `intake_draft.yaml`에
누적되는 초안입니다. 계획을 승인해 실행 모드로 넘어간 뒤에는 데이터 확인,
분석 방향, 대시보드 구성안, 보고서 구성안을 채팅창에서 다시 확인합니다.

Codex Desktop에서 `data-insight-kit`을 워크스페이스로 열면 `.codex/hooks.json`의
PreToolUse 훅이 적용됩니다. 처음 한 번 hook trust를 요청받으면 `/hooks`에서
신뢰해야 합니다. 이 훅은 Plan Mode 승인 문구를 중간 확인 답변으로 재사용하지
못하게 막고, 실제 사용자 답변이 `scripts/apply_checkpoint_answer.py`로
`checkpoint-answer.v3` 형식에 맞게 기록되기 전에는 최종 대시보드·보고서 산출물
생성을 차단합니다.

Plan Mode의 첫 응답은 사용자가 이해할 수 있는 **사용자용 분석 기획안**으로
시작해야 합니다. 다음처럼 기술 계획 제목이 먼저 나오면 올바른 첫 응답이
아닙니다.

```text
Summary
Key Changes
Pipeline
Test Plan
Assumptions
```

정상적인 첫 응답은 다음 흐름에 가깝습니다.

```text
이번 분석은 이렇게 진행합니다

한 줄 목적
...

답할 질문
...

이번 데이터로 볼 수 있는 것
...

이번 데이터만으로 판단하지 않을 것
...

질문
이 범위로 먼저 데이터 확인 단계부터 시작할까요?
```

run-id, 파일 경로, 검증 명령 같은 내부 실행 계획은 필요하더라도 뒤쪽
`기술 부록`으로 분리되어야 합니다.

Claude Code에서 plugin을 쓸 때도 기준은 같습니다. Plan Mode에서 사용자용
분석 기획안과 실행 계획을 먼저 확인한 뒤, 승인 후 `/run-pipeline`을
사용합니다.

```text
/plugin marketplace add /path/to/data-insight-kit
/plugin install data-insight-kit@data-insight-kit
# Plan Mode에서 사용자 요청과 실행 계획을 먼저 확인
/run-pipeline my-first-run
```

공개 v0.2.1 배포본은 GitHub 원격 marketplace에서 설치할 수 있습니다.

```bash
claude plugin marketplace add foodie-repository/data-insight-kit
claude plugin install data-insight-kit@data-insight-kit
```

터미널에서 직접 실행할 때는 `--guided-intake`를 사용합니다. 이 방식은 AI 앱의
질문 UI를 쓰지 않고 파일 기반 질문/답변 handoff를 직접 처리합니다.

```bash
DIK_USER_REQUEST="이 데이터로 분석 보고서와 대시보드를 만들어줘" \
  bash scripts/run_codex_pipeline.sh my-first-run --guided-intake
```

## 3. 분석 대상을 정합니다

처음부터 완벽한 요구사항을 쓸 필요는 없습니다. 다음 정도만 있으면 됩니다.

```text
이 데이터로 분석 보고서와 대시보드를 만들어줘.
```

조금 더 구체적으로 쓰면 더 좋습니다.

```text
이 데이터로 최근 12개월의 변화와 세그먼트별 차이를 보고 싶어.
대시보드와 심층 검토 보고서를 만들어줘.
```

요청이 짧으면 kit이 바로 끝까지 만들지 않고 질문부터 합니다. 질문은 보통
다음 결정을 좁히기 위한 것입니다.

- 분석 목적: 현황 파악, 후보 탐색, 리스크 점검, 성과 진단 등
- 분석 범위: 기간, 지역, 제품, 고객군, 조직, 세그먼트 등
- 보고서 수준: 빠른 요약인지, 심층 검토인지
- 보조 데이터 필요 여부: 기본 데이터만 쓸지, 외부 데이터도 검토할지

## 4. 입력 파일을 둡니다

```bash
cd data-insight-kit
mkdir -p runs/my-first-run/input
cp /path/to/data.csv runs/my-first-run/input/
```

CSV, Parquet, Excel, JSON을 사용할 수 있습니다. 파일이 여러 개면 같은
`input/` 폴더에 둡니다.

API URL을 입력으로 줄 수도 있습니다. 이 경우에는 먼저 원천 연결과 수집 가능
여부를 확인하고, 성공하면 로컬 스냅샷을 만든 뒤 분석합니다.

## 5. guided intake로 시작합니다

```bash
DIK_USER_REQUEST="이 데이터로 분석 보고서와 대시보드를 만들어줘" \
  bash scripts/run_codex_pipeline.sh my-first-run --guided-intake
```

질문이 필요하면 파이프라인은 멈추고 다음 파일을 만듭니다.

```text
runs/my-first-run/outputs/intake_questions.md
runs/my-first-run/outputs/intake_questions.json
```

질문에 답한 뒤 draft에 누적합니다.

```bash
python3 scripts/apply_intake_answer.py my-first-run --option <option-id>
```

직접 답변도 가능합니다.

```bash
python3 scripts/apply_intake_answer.py my-first-run \
  --answer "최근 12개월, 제품군별 성과 차이를 우선 보고 싶습니다."
```

그 다음 같은 명령을 다시 실행합니다.

```bash
bash scripts/run_codex_pipeline.sh my-first-run --guided-intake
```

질문이 더 필요하면 다시 멈추고, 충분하면 최종 `intake.yaml`을 만들고 다음 단계로
넘어갑니다.

이때 wrapper는 `runs/my-first-run/input/run_context.json`에 새 분석 정책을
남깁니다. 기본값은 기존 run 참조 금지입니다. 이전 결과를 일부러 참고하는 분석은
해당 run id가 이 파일에 기록되어야 합니다.

AI 앱을 쓰는 경우에는 위 파일을 직접 열어보는 대신, 상위 에이전트가 질문 요약을
채팅창이나 팝업으로 보여줍니다. 중요한 점은 동일합니다. 사용자의 실제 답변이
기록되기 전에는 다음 단계로 넘어가지 않습니다.

## 6. 데이터 확인 단계에서 멈춥니다

데이터를 읽은 뒤 kit은 샘플, 컬럼, 행 수, 결측, 기간, 분석 가능/불가능 범위를
요약하고 멈춥니다.

확인할 것:

- 내가 의도한 데이터 범위가 맞는가?
- 분석 단위가 맞는가? 예: 일별, 월별, 고객별, 상품별, 지역별
- 중요한 컬럼이 빠지지 않았는가?
- 데이터만으로 판단할 수 없는 내용이 무엇인가?

진행해도 되면 답변을 기록합니다.

```bash
python3 scripts/apply_checkpoint_answer.py my-first-run data_profile \
  --option continue_with_current_data \
  --source user_chat \
  --user-response "데이터 범위와 샘플이 맞으니 이 기준으로 진행"
```

범위가 틀리면 수정 요청을 남깁니다.

```bash
python3 scripts/apply_checkpoint_answer.py my-first-run data_profile \
  --answer "최근 12개월만 쓰고, 테스트 고객은 제외해 주세요." \
  --source user_chat \
  --user-response "최근 12개월만 쓰고, 테스트 고객은 제외해 주세요."
```

수정 요청이 있으면 관련 산출물을 고친 뒤 다시 확인받아야 합니다.

### 6-1. 궁금한 방향을 먼저 좁힐 수 있습니다 (탐색 문답)

데이터 확인 단계에서는 "바로 진행" 외에 kit이 실제 데이터에서 미리 계산한
"볼 만한 방향" 선택지가 함께 나올 수 있습니다. 방향을 고르면 미리 본 결과
표를 보여주는 확인 질문이 한 번 더 나오고(단계당 최대 2회), 확정하면 그
방향이 분석 질문과 비교 기준에 반영됩니다. 어느 확인 단계에서든 데이터에
대해 직접 질문(단계당 1회)을 할 수도 있습니다 — 확인 결과를 본 뒤 이어서
결정하면 됩니다. 회사·업무 데이터(domain mode)라면 행의 의미, 제외 기준 같은
추가 확인 질문이 함께 나오는데, 이 답변은 진행 여부와 무관하게 해석 기준에만
반영됩니다.

## 7. 분석 방향을 고릅니다

다음 단계에서는 kit이 가능한 분석 방향 2~3개를 제안합니다.

예시:

- 세그먼트별 차이를 우선 보기
- 시간 흐름과 변동성을 우선 보기
- 규모와 변화율을 함께 보며 예외를 찾기
- 구성비와 집중도를 우선 보기

이때 KPI, 분모, 비교 기준도 함께 확인합니다. 예를 들어 "증가율"을 볼 때는
전월 대비인지, 전년 대비인지, 시작점 대비인지가 명확해야 합니다.

진행하려면:

```bash
python3 scripts/apply_checkpoint_answer.py my-first-run analysis_strategy \
  --option approve_strategy \
  --source user_chat \
  --user-response "추천 분석 방향으로 진행하되, 세그먼트별 차이를 더 강조해 주세요."
```

### 추가 분석 기능 설치가 필요하면

통계적 확인이나 패턴 탐색처럼 더 깊은 분석을 추천받으면, 이 단계에 설치 승인
선택지가 함께 나타납니다. 고를 때 볼 것:

- 왜 추가 기능이 필요한지 (예: 그룹 차이가 우연인지 확인하려면 통계 계산이 필요)
- 설치하면 어떤 분석까지 가능해지는지
- 설치하지 않으면 어떤 기본/진단 분석으로 대신 진행하는지
- 설치가 실패하면 어떻게 되는지 (자동으로 기본 분석으로 낮춰서 계속 진행)

"설치하고 심화 분석 진행"을 고르면 data-insight-kit 전용 환경에만 필요한 기능을
설치합니다. 다른 프로젝트나 시스템 전체 Python 환경에는 영향을 주지 않습니다.
"설치 없이 기본/진단 분석 진행"을 고르면 설치 없이 바로 이어서 진행합니다.
자유롭게 쓴 답변만으로는 설치를 진행하지 않습니다 — 설치는 반드시 제시된
선택지를 골라야 승인됩니다.

## 7-1. 필요하면 1차 결과를 한 번 더 확인합니다 (조건부)

다음 중 하나에 해당하면 대시보드 구성안을 보여주기 전에 1차 분석 결과를 먼저
확인하는 단계가 한 번 더 나타납니다.

- 통계적 확인, 패턴 탐색, 예측 후보, 실험/효과 검토처럼 심화 분석을 진행한 경우
- 회사·업무 도메인 데이터를 다루는 경우
- 심층 검토 보고서를 만드는 경우
- 후보·우선순위를 정하거나 위험을 점검하는 의사결정형 분석인 경우

해당하지 않으면 이 단계는 나타나지 않고 바로 대시보드 구성안 확인으로
넘어갑니다. 나타나면 다음을 확인합니다.

- 1차 발견이 원래 목적과 맞는가?
- 더 깊게 볼지, 기본 분석 수준으로 낮출지
- 도메인 전문가 관점에서 해석이 말이 되는가?
- 결론을 너무 강하게 표현하고 있지는 않은가?

진행하려면:

```bash
python3 scripts/apply_checkpoint_answer.py my-first-run analysis_result_review \
  --option approve_analysis_result \
  --source user_chat \
  --user-response "1차 결과가 목적과 맞으니 이 수준으로 대시보드 구성안을 진행해 주세요."
```

## 8. 대시보드 구성안을 고릅니다

분석이 끝나면 바로 대시보드를 만들지 않고, 먼저 차트 구성을 보여줍니다.

확인할 것:

- 각 차트가 어떤 질문에 답하는가?
- 어떤 데이터와 지표를 쓰는가?
- 왜 이 차트가 추천되는가?
- 대안 차트는 무엇이고 왜 보류했는가?
- 요약형, 탐색형, 모니터링형 중 어떤 화면 구성이 맞는가?
- 제목과 설명이 배포용 독자에게 이해되는가?
- v5 자유 레이아웃이면 hero/support 크기, desktop 배치, mobile 읽기 순서가
  판단 흐름에 맞는가?

진행하려면:

```bash
python3 scripts/apply_checkpoint_answer.py my-first-run dashboard_storyboard \
  --option approve_storyboard \
  --source user_chat \
  --user-response "추천 구성안으로 진행하고, 차트 제목은 독자가 바로 이해할 수 있게 풀어 써 주세요."
```

스타일을 바꾸고 싶으면 다른 승인 선택지를 사용합니다.

```bash
python3 scripts/apply_checkpoint_answer.py my-first-run dashboard_storyboard \
  --option approve_analyst_workspace \
  --source user_chat \
  --user-response "분석가가 세그먼트와 예외를 더 깊게 볼 수 있는 화면으로 진행해 주세요."

python3 scripts/apply_checkpoint_answer.py my-first-run dashboard_storyboard \
  --option approve_operations_monitor \
  --source user_chat \
  --user-response "주간 운영 현황판처럼 반복 지표와 전 기간 대비 변화를 잘 보이게 해 주세요."
```

단순 순위표가 반복되거나 원하는 판단에 답하지 못하면 이 단계에서 수정 요청을
남기는 것이 좋습니다.

## 9. 보고서 구성안을 확인합니다

대시보드 QA를 통과한 뒤 보고서 작성 전에 다시 멈춥니다.

확인할 것:

- 요약 보고서만 필요한가, 심층 검토 보고서도 필요한가?
- 독자는 경영진, 실무자, 분석가, 혼합 독자 중 누구인가?
- 결론을 얼마나 강하게 표현해도 되는가?
- 데이터에 없는 판단을 단정하고 있지는 않은가?

진행하려면:

```bash
python3 scripts/apply_checkpoint_answer.py my-first-run report_outline \
  --option approve_report_outline \
  --source user_chat \
  --user-response "요약 보고서와 심층 검토 보고서를 모두 만들고, 결론은 데이터 근거 범위 안에서만 써 주세요."
```

## 10. 최종 산출물을 확인합니다

주요 산출물:

```text
runs/my-first-run/outputs/dashboard.html
runs/my-first-run/outputs/summary_report.md
runs/my-first-run/outputs/deep_report.md
runs/my-first-run/outputs/chart_spec.json
runs/my-first-run/outputs/dashboard_layout.json       # v5일 때
runs/my-first-run/outputs/dashboard_data.json
runs/my-first-run/outputs/dashboard_build_manifest.json # v5일 때
```

대시보드는 브라우저에서 열어 보고, 보고서는 결론 수위와 한계를 확인합니다.

## 11. QA를 실행합니다

렌더러는 다음처럼 선택됩니다.

| 경로 | chart/data contract | `dashboard_layout.json` | 결과 |
|---|---|---|---|
| legacy | 둘 다 없음 | 없음 | 기존 탭형 순수 SVG |
| v4 | 둘 다 `v4` | 없음 | 프로필별 순수 SVG |
| v5 | 둘 다 `v5` | 승인본 필수 | 로컬 ECharts + SVG/CSS 자유 레이아웃 |

v5인데 layout이 없거나 승인 후 hash/revision이 바뀌면 v4로 낮추지 않고
재승인 전까지 멈춥니다. v5 산출물을 직접 다시 만들려면 다음을 실행합니다.

```bash
python3 scripts/render_dashboard_v5.py \
  --chart-spec runs/my-first-run/outputs/chart_spec.json \
  --layout runs/my-first-run/outputs/dashboard_layout.json \
  --data runs/my-first-run/outputs/dashboard_data.json \
  --output runs/my-first-run/outputs/dashboard.html
```

```bash
python3 qa/validate.py runs/my-first-run/outputs/dashboard_data.json \
  --chart-spec runs/my-first-run/outputs/chart_spec.json

python3 qa/validate.py runs/my-first-run/outputs/dashboard_data.json \
  --chart-spec runs/my-first-run/outputs/chart_spec.json \
  --layout runs/my-first-run/outputs/dashboard_layout.json

python3 qa/validate.py runs/my-first-run/outputs/dashboard_data.json \
  --chart-spec runs/my-first-run/outputs/chart_spec.json \
  --no-render --post-communicate
```

BLOCK이 있으면 완료가 아닙니다. 원인을 고친 뒤 다시 실행합니다.

## 12. 도메인용으로 쓰고 싶다면

회사나 업무 도메인에 맞는 용어, KPI, 보고서 구조, 차트 흐름이 있다면
domain pack을 만듭니다.

```bash
cp -R domains/template domains/my-domain
```

그 다음 실행할 때 지정합니다.

```bash
DIK_DOMAIN_PACK=domains/my-domain/domain.yaml \
  DIK_USER_REQUEST="이 데이터로 분석 보고서와 대시보드를 만들어줘" \
  bash scripts/run_codex_pipeline.sh my-first-run --guided-intake
```

domain pack은 자동 결론을 강제하지 않습니다. 에이전트가 더 좋은 질문을 하고,
도메인 기준을 반영한 차트와 보고서를 제안하도록 돕는 보조 장치입니다.

### 도메인 전문가 확인 정보가 왜 필요한가요

컬럼명과 코드값만 보고는 행 하나가 무엇을 의미하는지, 어떤 값을 제외해야
하는지, KPI를 어떤 분모로 계산해야 하는지 알 수 없는 경우가 많습니다. 이런
정보는 domain pack이 있어도 이번 데이터에 그대로 맞는다는 보장이 없습니다.
그래서 kit은 이번 분석에 실제로 필요한 최소한의 정보(행의 의미, 핵심 대상,
컬럼/코드값 의미, 제외 규칙, 분석 목적, 금지 표현)를 짧게 확인합니다.

확인된 정보가 부족하면 일반적인 구조 분석(순위, 분포, 구성, 추세)만 제공하고,
추천·원인·성과·위험도를 확정하는 도메인 결론은 만들지 않습니다. 충분히
확인되면 도메인 기준에 맞춘 제한적인 진단까지 제공합니다. 확인이 부족한
상태에서도 강한 결론이 대시보드나 보고서에 나타나면 QA가 출고를 막습니다.

## 13. 자동 실행이 필요한 경우

회귀 테스트나 배치 실행처럼 사람 확인을 건너뛰어야 할 때만 `--auto` 또는
`--no-checkpoints`를 명시합니다.

```bash
bash scripts/run_codex_pipeline.sh my-first-run --auto
```

일반 분석 작업에서는 권장하지 않습니다. 사용자 의도와 차트 구성을 놓치기 쉽기
때문입니다.

## 14. 에이전트 구조를 더 알고 싶다면

이 가이드는 실제 사용 절차를 중심으로 설명합니다. `data-insight-kit` 내부에서
intake, connect, explore, frame, analyze, visualize, qa, communicate 단계가 각각
어떤 역할을 하는지 더 자세히 보고 싶다면
[docs/agent-guide/](docs/agent-guide/)를 확인하세요.

실행 계약의 단일 기준은 [docs/pipeline-contract.md](docs/pipeline-contract.md)이고,
`docs/agent-guide/`는 에이전트 역할과 파이프라인 흐름을 이해하기 위한 보조
설명 자료입니다.
