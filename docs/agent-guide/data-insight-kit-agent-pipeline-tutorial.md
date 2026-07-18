# data-insight-kit 에이전트 파이프라인 튜토리얼

이 문서는 `data-insight-kit`의 에이전트 역할과 파이프라인 흐름을 설명하는
구조 안내서다. 발표용 요약은
[data-insight-kit-agent-pipeline.slides.md](data-insight-kit-agent-pipeline.slides.md)에
있다.

## 문서 위치

에이전트 구조 설명 자료는 `data-insight-kit` 루트에 바로 두기보다
`data-insight-kit/docs/agent-guide/` 아래에 둔다.

이유는 세 가지다.

1. `data-insight-kit/docs/`에는 이미 `pipeline-contract.md`, `model-tier-map.md`
   같은 기준 문서가 있다. 에이전트 구조 설명도 같은 문서 계층 안에 있어야
   찾기 쉽다.
2. 루트에는 `README.md`, `AGENTS.md`, `schemas/`, `connectors/`, `qa/`,
   `templates/`처럼 실행과 배포에 직접 필요한 파일이 있다. 구조 설명 자료를
   루트에 두면 키트의 실행 표면이 흐려진다.
3. 나중에 역할별 설명, 발표용 슬라이드, 데모 시나리오를 추가할 수 있으므로
   `docs/agent-guide/`라는 별도 폴더가 확장에 유리하다.

현재 구조:

```text
data-insight-kit/docs/agent-guide/
├── data-insight-kit-agent-pipeline.slides.md
└── data-insight-kit-agent-pipeline-tutorial.md
```

## data-insight-kit은 무엇인가

`data-insight-kit`은 표 데이터 소스에서 출발해 분석, 시각화, QA, 보고서까지 이어지는 데이터 시각화 파이프라인 키트다. 사용자는 DuckDB를 반드시 준비할 필요가 없고, CSV·Parquet·Excel·JSON 같은 로컬 파일이나 원격 Parquet 스냅샷만으로도 시작할 수 있다. 목표는 LLM이 즉흥적으로 HTML이나 SVG를 만드는 것이 아니라, 단계별 에이전트가 정해진 계약을 따라 분석 결과를 만들고, 그 결과를 `dashboard_data.json`이라는 데이터 계약으로 표현한 뒤, 템플릿이 이를 읽어 대시보드를 렌더하는 것이다.

핵심 흐름은 다음과 같다.

```text
소스 어댑터
  -> 로컬 입력/스냅샷
  -> intake
  -> connect
  -> explore
  -> frame
  -> analyze
  -> visualize
  -> qa
  -> communicate
  -> qa-post
  -> dashboard.html + summary_report.md
```

가장 중요한 설계 문서는 `docs/pipeline-contract.md`다. 이 문서는 런타임과 무관하게 파이프라인의 단일 원천 역할을 한다. Claude Code와 Codex는 실행 방식이 다르지만, 단계 순서와 산출물 계약은 이 문서를 따른다.

## 왜 에이전트를 단계별로 나누는가

데이터 시각화 자동화에서 가장 위험한 문제는 한 번의 프롬프트가 너무 많은 일을 동시에 하게 되는 것이다. 분석 목적 확인, 데이터 연결, EDA, KPI 정의, 인사이트 도출, 차트 설계, HTML 생성, QA를 한 번에 맡기면 중간 판단이 흐려진다. 결과적으로 다음 문제가 생긴다.

- 분석 목적과 청중이 불명확한 상태에서 차트가 만들어진다.
- KPI 이름은 있지만 계산식, 단위, 분모가 없다.
- 탐색에서 발견한 패턴과 최종 대시보드 메시지가 맞지 않는다.
- HTML은 예쁘지만 어떤 수치가 어떤 원천에서 왔는지 추적하기 어렵다.
- QA 없이 `dashboard.html` 파일 생성만으로 작업이 끝났다고 착각한다.

`data-insight-kit`은 이 문제를 줄이기 위해 역할을 8개 단계로 분리한다. 각 단계는 입력과 출력이 정해져 있고, 다음 단계는 이전 단계의 산출물을 기준으로 움직인다. 이 구조 덕분에 어디서 문제가 생겼는지 추적하고, 필요한 단계만 다시 실행할 수 있다.

## 전체 파이프라인 계약

파이프라인 순서는 고정이다.

```text
0 intake -> 1 connect -> 2 explore -> 3 frame -> 4 analyze -> 5 visualize -> 6 qa -> 7 communicate -> qa-post
```

두 가지 제한된 루프백만 허용된다.

첫째, `analyze` 단계가 문제정의나 KPI가 데이터와 명백히 불일치한다고 판단하면 `frame`으로 한 번 되돌아갈 수 있다. 예를 들어 frame에서 "매출 감소 원인"을 핵심 문제로 잡았는데 실제 데이터에는 매출 컬럼이 없거나, 매출이 아니라 거래 수만 존재한다면 프레이밍을 다시 해야 한다.

둘째, `qa` 단계가 기계적 결함을 찾으면 `visualize`로 한 번 되돌아갈 수 있다. 예를 들어 `dashboard_data.json`의 series 길이가 x축 길이와 다르거나, placeholder가 남아 있거나, 시뮬레이터 테스트 케이스가 없는 경우다.

셋째, `communicate` 이후에는 `qa-post`가 보고서 깊이와 근거 계약을 확인한다. 예를 들어 `depth=deep`인데 `deep_report.md`가 없거나, `04_analysis.md`의 단순 복사본이거나, 필수 섹션이 빠졌다면 통과하지 않는다.

반대로 분석적 결함은 자동수정하지 않는다. 표본 부족, 데이터 모순, 핵심 지표 부재처럼 판단이 필요한 문제는 사람에게 보고하고 멈추는 것이 원칙이다.

## 산출물 구조

각 실행은 `runs/<run-id>/` 아래에서 이루어진다.

```text
runs/<run-id>/
├── input/
├── intermediate/
├── outputs/
│   ├── 01_profile.md
│   ├── 02_eda.md
│   ├── 03_frame.md
│   ├── 04_analysis.md
│   ├── dashboard_data.json
│   ├── dashboard.html
│   └── summary_report.md
└── manifest.json
```

이 레이아웃은 두 가지 목적을 가진다.

첫째, 실행 단위가 명확해진다. 같은 데이터라도 `run-id`가 다르면 입력, 중간 산출물, 최종 산출물을 분리해서 관리할 수 있다.

둘째, 쓰기 경계가 명확해진다. `data-insight-kit`은 원칙적으로 `runs/<run-id>/` 안에만 산출물을 쓴다. DB 경로와 자격 증명은 `.env`에 두고 커밋하지 않는다.

## 단계별 에이전트 역할

### 0. intake

`intake`는 분석의 출발점을 고정한다. 이 분석이 누구를 위한 것인지, 어떤 의사결정에 답해야 하는지, 이미 알려진 질문이 있는지를 정리한다.

주요 판단은 `directed`와 `exploratory` 모드다.

- `directed`: 사용자가 답하고 싶은 질문이 이미 분명한 경우다. 예를 들어 "지역별 전세가 상승률 차이를 보고 싶다"처럼 분석 질문이 정해져 있다.
- `exploratory`: 먼저 데이터를 보고 질문을 발견해야 하는 경우다. 예를 들어 "이 데이터로 대시보드를 만들어줘"처럼 목적이 넓다.

출력은 `manifest.json`의 `intake` 영역이다.

```json
{
  "mode": "exploratory",
  "audience": "mixed",
  "objective": "데이터에서 주요 패턴을 찾아 대시보드화한다",
  "known_questions": []
}
```

목적이 모호하면 intake는 조용히 기본값으로 진행하지 않는다. 한 번에 하나의 핵심 불확실성만 묻고, 질문은 다음 구조를 따른다.

```text
현재 이해 / 막힌 결정 / 추천 답안 / 질문
```

예를 들어 "이 데이터로 대시보드를 만들어줘"처럼 넓은 요청이면, 먼저 이 결과로 사용자가 무엇을 판단하려는지 확인한다. non-interactive 실행에서 질문할 수 없고 목적이 너무 모호하면 `outputs/intake_questions.md`를 남기고 중단한다.

질문형 UX 자체를 검증할 때는 `--guided-intake`를 사용한다. 이 모드는 명확한 요청이어도 첫 답변을 바로 `intake.yaml`로 확정하지 않고 `intake_draft.yaml`에 누적한 뒤, 충분해졌을 때 `finalization.finalized_by: guided_intake` 흔적과 함께 최종 계약으로 승격한다.

이 단계가 중요한 이유는 이후 모든 단계가 같은 목적과 청중을 기준으로 움직이기 때문이다.

### 1. connect

`connect`는 데이터 소스를 안전하게 연결하고 다음 단계가 사용할 정제 데이터를 만든다. 분석을 본격적으로 수행하기보다, 데이터의 구조와 품질을 파악하는 단계다.

입력 소스는 세 가지 방식이다.

- `runs/<run-id>/input/`에 들어 있는 CSV, Parquet, Excel, JSON 파일
- 원격 Parquet를 필요한 컬럼·행만 줄이고 필요시 층화 샘플링해 만든 `runs/<run-id>/input/*.parquet` 스냅샷
- 선택적으로 `connectors/.env`의 `DIK_DUCKDB_PATH`가 가리키는 DuckDB 파일

DuckDB는 필수 입력이 아니라 선택 입력이자 내부 SQL 실행 엔진이다. 기존 DB에 접근할 때는 반드시 `connectors/source.py`를 통해 이루어진다. 이 어댑터는 read-only 접근과 SELECT/WITH 중심의 쿼리 경계를 강제한다. 직접 `duckdb.connect(...)`로 연결하지 않는 이유는 보안과 재현성을 지키기 위해서다.

원격 Parquet는 전체 다운로드하지 않는다. `scripts/snapshot_remote_parquet.py`로 필요한 컬럼과 행 수를 제한해 로컬 스냅샷을 만든 뒤 그 파일을 분석 기준으로 삼는다. 지역·세그먼트 대표성이 중요하면 `--stratify-by`로 층화 샘플링한다.

`connect`가 만드는 대표 산출물은 다음과 같다.

- `intermediate/*.parquet`: 다음 단계가 쓸 정제 데이터
- `outputs/01_profile.md`: 데이터 프로파일
- `manifest.sources[]`: 소스 메타데이터

`01_profile.md`에는 컬럼 구조, 결측 비율, 이상치 후보, 조인 주의점, 원화 단위, 행정구역, 날짜 포맷 같은 의미층 메모가 들어간다.

### 2. explore

`explore`는 정제 데이터를 탐색해 의미 있는 패턴을 찾는다. 단순히 "평균이 얼마"를 나열하는 단계가 아니라, 다음 의사결정으로 이어질 수 있는 질문을 만드는 단계다.

주요 작업은 다음과 같다.

- 수치형 컬럼의 분포, 극단값, 범위 확인
- 범주형 컬럼의 최빈값, 희귀 범주, 그룹 차이 확인
- 날짜 컬럼의 기간, 밀도, 추세, 변곡 확인
- 수치와 수치 간 상관, 범주와 수치 간 차이 확인
- 데이터 특성에 맞는 방법론 후보 제안
- 분석 모드 후보와 심층 분석 기회 제안

출력은 `outputs/02_eda.md`다. 이 문서에는 주요 발견, 분석 모드 후보, 방법론 후보, 심층 분석 기회, 핵심 질문 3~5개, frame 단계에 넘길 주의점이 들어간다.

`explore`의 품질은 이후 단계에 큰 영향을 준다. 이 단계에서 중요한 패턴을 놓치면 `frame`과 `analyze`는 그 패턴을 기반으로 문제를 정의할 수 없다.

### 3. frame

`frame`은 탐색 결과를 비즈니스 문제와 KPI로 바꾼다. 여기서 "무엇을 분석할 것인가"가 아니라 "어떤 문제를 어떤 지표로 판단할 것인가"가 확정된다.

주요 산출은 세 가지다.

1. 메인 문제 정의
2. MECE 원인 구조
3. KPI 정의표

KPI 정의표에는 반드시 다음 항목이 포함되어야 한다.

- 이름
- 계산식
- 실제 컬럼
- 단위
- 분모
- 비교 기준
- 유형, 예를 들어 결과 지표 또는 선행 지표

예를 들어 "가격 상승률"이라는 지표만 적으면 부족하다. 어떤 가격 컬럼을 쓰는지, 전월 대비인지 전년 대비인지, 단위가 퍼센트포인트인지 퍼센트인지, 기준 기간이 무엇인지까지 정해야 한다.

출력은 `outputs/03_frame.md`다. 이 문서는 이후 `dashboard_data.json`의 KPI와 metric 정의의 씨앗이 된다.

### 4. analyze

`analyze`는 정의된 KPI와 질문을 실제 데이터로 검증한다. 이 단계는 단순 집계가 아니라 해석 단계다.

분석 흐름은 General -> Specific이다.

1. 전체 현황을 먼저 본다.
2. 영향이 큰 차원으로 분해한다.
3. 원인을 탐색한다.
4. 이상 또는 기회를 찾는다.
5. 액션으로 연결한다.

`analyze`는 보고서 깊이에 맞춰 인사이트 수와 분석 레이어를 조정한다. `brief`는 1~3개, `standard`는 3~5개, `deep`은 5~7개의 인사이트를 목표로 한다. 각 인사이트는 다음 구조를 가져야 한다.

- 발견
- 근거 수치
- 왜 중요한가
- 한계
- 추천 액션
- 반대 해석 또는 대체 설명(`depth=deep`일 때 필수)

또한 `visualize` 단계가 차트를 만들 수 있도록 시계열, 비교, 분포, 산점도 등에 필요한 집계 수치를 명시하거나 `intermediate/`에 chart-ready parquet로 저장한다.

출력은 `outputs/04_analysis.md`다.

### 5. visualize

`visualize`는 분석 결과를 화면으로 표현할 수 있는 데이터 계약으로 변환한다. 중요한 점은 이 단계가 직접 SVG를 손으로 그리는 단계가 아니라는 것이다.

`visualize`가 만드는 핵심 산출물은 두 개다.

- `outputs/dashboard_data.json`
- `outputs/dashboard.html`

`dashboard_data.json`은 `schemas/dashboard_data.schema.json`을 따라야 한다. KPI에는 값, 단위, 분모, 상태, metric 정보가 들어가야 하고, 차트에는 x축과 series 길이가 맞아야 하며, 색은 hex 값이 아니라 role로 표현해야 한다.

예를 들어 좋은 설계는 다음과 같다.

```json
{
  "label": "전년 대비 상승률",
  "value": 12.4,
  "unit": "%",
  "kind": "relative",
  "denominator": "전년 동일 기간",
  "status": "warn"
}
```

반대로 분석에 없는 지표를 화면 구성을 위해 임의로 추가하거나, 근거 없는 시뮬레이터를 만드는 것은 금지된다.

`dashboard.html`은 `templates/dashboard.html`에 JSON을 주입해서 만들어진다. 따라서 대시보드의 렌더링 방식은 템플릿이 담당하고, 에이전트는 렌더러가 읽을 데이터를 정확히 만드는 데 집중한다.

### 6. qa

`qa`는 출고 게이트다. 이 단계의 핵심은 "LLM이 괜찮다고 판단했는가"가 아니라, 결정적 검증 스크립트가 통과했는가다.

실행 명령은 다음과 같다.

```bash
python qa/validate.py runs/<run-id>/outputs/dashboard_data.json --chart-spec runs/<run-id>/outputs/chart_spec.json
python qa/validate.py runs/<run-id>/outputs/dashboard_data.json --chart-spec runs/<run-id>/outputs/chart_spec.json --no-render --post-communicate
```

검증 대상은 다음을 포함한다.

- JSON schema 통과 여부
- metric과 source reference 유효성
- x축 values 길이와 series 길이 일치
- chart type별 허용 stack 값
- placeholder 잔존 여부
- 시뮬레이터 test case 존재 여부
- Playwright가 있으면 모든 탭을 desktop·mobile 폭에서 열어 콘솔 에러, 빈 화면, 라벨 겹침, 라벨 잘림, 과대 SVG 여부
- post-communicate 검증에서는 `summary_report.md`, `deep_report.md`, `external_context.md`의 존재와 필수 구조

BLOCK이 나오면 communicate 단계로 넘어갈 수 없다. 기계적 문제는 `visualize`를 한 번 다시 실행해 고칠 수 있지만, 분석적 문제는 자동수정하지 않는다.

Codex CLI wrapper에서는 QA를 LLM 단계로 실행하지 않고 `qa/validate.py`를 직접 실행한다. `agents/qa.md`는 Claude Code 어댑터와 파이프라인 설명을 위한 단계 지침으로 보면 된다.

### 7. communicate

`communicate`는 최종 보고서 작성 단계다. 보고서의 깊이(`brief|standard|deep`)와 독자(`executive|analyst|operator|mixed`)를 분리하고, 선택된 설정에 맞춰 결과를 정리한다.

입력은 다음과 같다.

- `outputs/04_analysis.md`
- `outputs/chart_spec.json`
- `outputs/dashboard_data.json`
- `outputs/03_frame.md`
- `manifest.json#intake.report`

중요한 원칙은 재계산 금지다. 보고서에 쓰는 수치는 `dashboard_data.json`의 값을 그대로 인용한다. 이렇게 해야 대시보드와 보고서의 수치가 서로 어긋나지 않는다.

기본 출력은 `outputs/summary_report.md`다. 보통 다음 구성을 가진다.

- 한 줄 요약
- 분석 배경
- 핵심 KPI 현황표
- 주요 발견
- 액션 플랜
- 데이터 신뢰성 메모
- 추가 분석 제안

`depth=deep`이면 `outputs/deep_report.md`가 추가된다. 이 파일은 `04_analysis.md`를 복사하는 문서가 아니라, 의사결정 질문, 방법론, KPI, 세그먼트/분포/관계/추세 분석, 반대 해석, 실행 시나리오, 추가 분석 설계, 부록을 갖춘 심층 보고서여야 한다.

## 데이터 계약: dashboard_data.json

`dashboard_data.json`은 `data-insight-kit`의 중심 산출물이다. 분석과 렌더링 사이의 계약이며, QA가 검증하는 대상이다.

이 파일이 중요한 이유는 세 가지다.

첫째, 재현성이 생긴다. 어떤 값이 어떤 metric과 source에서 왔는지 추적할 수 있다.

둘째, 렌더링이 안정된다. LLM이 SVG 좌표와 라벨을 직접 만들지 않고, 템플릿이 구조화된 데이터를 읽어 화면을 그린다.

셋째, QA가 가능해진다. JSON schema와 추가 검증 규칙으로 시각화 오류를 기계적으로 잡을 수 있다.

특히 다음 원칙이 중요하다.

- `value`는 이미 표시할 값이다. `format.display_scale`은 메타데이터이지 렌더러가 다시 나눌 값이 아니다.
- 색상은 `good`, `bad`, `warn`, `neutral`, `info` 같은 role로 표현한다.
- 시뮬레이터는 `linear`, `percentage`, `lookup` 같은 명명된 모델만 사용한다.
- 시뮬레이터에는 최소 1개 이상의 `test_cases`가 있어야 한다.
- 모든 KPI와 차트 수치는 단위, 분모, 출처를 동반해야 한다.

## 런타임 어댑터 구조

`data-insight-kit`은 Claude Code와 Codex 양쪽에서 사용할 수 있도록 설계되어 있다. 다만 두 런타임은 같은 방식으로 skill을 읽지 않으므로 어댑터가 분리되어 있다.

공유 코어는 다음이다.

```text
docs/
schemas/
connectors/
qa/
templates/
themes/
```

Claude Code 쪽 어댑터는 다음이다.

```text
.claude-plugin/
agents/*.md
skills/run-pipeline/
```

Codex 쪽 어댑터는 다음이다.

```text
AGENTS.md
scripts/run_codex_pipeline.sh
```

`agents/*.md` 파일의 frontmatter는 Claude Code 어댑터용 메타데이터다. Codex는 frontmatter 자체를 실행 설정으로 쓰지 않고, wrapper가 각 단계의 본문 지침을 프롬프트로 넘긴다.

## Codex에서 실행하기

Codex에서는 `data-insight-kit` 루트에서 다음 명령을 실행한다.

```bash
cd "/Users/foodie/Data-Visualization/Fast-Campus-DataBridge/data-insight-kit"
bash scripts/run_codex_pipeline.sh <run-id>
```

입력 데이터는 둘 중 하나로 제공한다.

1. `runs/<run-id>/input/`에 파일을 넣는다.
2. 원격 Parquet는 `scripts/snapshot_remote_parquet.py`로 스냅샷을 만든다. 필요하면 `--stratify-by`로 지역·세그먼트별 최소 표본을 보존한다.
3. 기존 분석 DB를 쓸 때만 `connectors/.env`에 `DIK_DUCKDB_PATH`를 지정한다.

실행 전에 명령만 확인하려면 `--dry-run`을 쓴다.

```bash
bash scripts/run_codex_pipeline.sh <run-id> --dry-run
```

기존 산출물을 무시하고 다시 만들려면 `--fresh`를 쓴다.

```bash
bash scripts/run_codex_pipeline.sh <run-id> --fresh
```

모델을 바꾸려면 `DIK_MODEL` 환경변수를 사용한다.

```bash
DIK_MODEL=<모델명> bash scripts/run_codex_pipeline.sh <run-id>
```

## 모델 티어와 Codex/OpenAI model+effort

모든 단계에 같은 모델과 같은 reasoning effort를 쓰지 않는다. 판단 품질이 큰 영향을 주는 단계에만 높은 effort를 배정한다.
**기본 모델명은 `docs/model-tier-map.md`가 단일 원천이다**(모델 세대가 바뀌어도 이 표는 그대로 유효하도록 effort만 적는다).

| 티어 | 단계 | effort | 이유 |
|---|---|---|---|
| 경량 | intake, qa | low | 분류와 검증 중심 |
| 실행 | connect, visualize, communicate | medium | 계약과 스키마가 보조 |
| 사고 | explore, frame, analyze | high | 인사이트 품질을 결정 |

`explore`, `frame`, `analyze`는 데이터에서 의미를 찾고 문제를 정의하는 단계이므로 가장 중요하다. 반면 `qa`는 결정적 스크립트가 중심이므로 LLM reasoning을 높이는 것보다 검증 코어를 신뢰하는 편이 맞다.

## 좋은 실행을 위한 체크리스트

실행 전에 확인할 것:

- 분석 목적과 청중이 분명한가
- `intake.yaml`을 만들지, 대화에서 목적을 받을지 정했는가
- input 파일 또는 원격 스냅샷이 준비되어 있는가
- DuckDB를 쓰는 경우 read-only `.env`가 준비되어 있는가
- DB 경로와 자격 증명이 산출물에 노출되지 않는가
- `run-id`가 의미 있게 정해졌는가

실행 중 확인할 것:

- `outputs/01_profile.md`가 실제 데이터 구조를 잘 설명하는가
- `outputs/02_eda.md`가 단순 요약이 아니라 질문으로 이어지는가
- `outputs/03_frame.md`의 KPI가 계산식, 단위, 분모를 갖는가
- `outputs/04_analysis.md`의 인사이트가 근거 수치와 한계를 포함하는가
- `depth=deep`이면 `04_analysis.md`에 방법론, KPI, 반대 해석, 액션 임계값이 있는가
- `dashboard_data.json`이 schema와 QA를 통과하는가

실행 후 확인할 것:

- `dashboard.html`에서 주요 KPI와 차트가 보이는가
- 대시보드 수치와 `summary_report.md` 수치가 일치하는가
- QA BLOCK 또는 WARN이 남아 있지 않은가
- 분석 한계와 표본 경고가 보고서에 반영되었는가
- `depth=deep`이면 `deep_report.md`가 단순 복사가 아니라 심층 보고서 구조를 갖는가

## 교육할 때 강조할 포인트

첫째, `data-insight-kit`은 "예쁜 HTML을 만들어주는 프롬프트 묶음"이 아니다. 목적 정의, 데이터 품질, KPI, 인사이트, 데이터 계약, QA를 연결한 파이프라인이다.

둘째, 가장 중요한 산출물은 `dashboard.html`만이 아니다. `01_profile.md`, `02_eda.md`, `03_frame.md`, `04_analysis.md`, `chart_spec.json`, `dashboard_data.json`, `summary_report.md`, 필요 시 `deep_report.md`가 함께 있어야 분석 재현성이 생긴다.

셋째, QA는 선택 사항이 아니다. `qa/validate.py`가 BLOCK을 내면 출고하지 않는 것이 원칙이다.

넷째, Claude Code와 Codex는 같은 skill 파일을 그대로 공유하는 구조가 아니라, 같은 코어와 계약을 공유하고 각자 어댑터를 가진 구조다. 따라서 `data-insight-kit`을 유지보수할 때는 `docs/pipeline-contract.md`와 shared core를 먼저 생각하고, 런타임별 wrapper는 얇게 유지해야 한다.

## 한 문장 정리

`data-insight-kit`은 데이터에서 대시보드까지 이어지는 일을 8개 에이전트의 계약형 파이프라인으로 나누고, `dashboard_data.json`과 QA 게이트로 재현성과 출고 품질을 지키는 데이터 시각화 키트다.
