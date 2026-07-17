---
marp: true
theme: default
paginate: true
header: "data-insight-kit"
footer: "Agent pipeline for data visualization dashboards"
---

<style>
:root {
  --bg: #faf6ec;
  --paper-2: #f1e9d8;
  --fg: #2a241c;
  --accent: #8c2f1f;
  --accent-deep: #6f2417;
  --accent-warm: #e8a08a;
  --muted: #8a7d68;
  --line: rgba(42, 36, 28, .14);
  --serif: 'Noto Serif KR', 'Nanum Myeongjo', 'AppleMyungjo', serif;
  --sans: 'Pretendard', 'Apple SD Gothic Neo', 'Malgun Gothic', sans-serif;
}
section {
  background: var(--bg);
  color: var(--fg);
  font-family: var(--sans);
  font-size: 24px;
  line-height: 1.45;
  padding: 48px 70px 72px;
}
section:not(.lead) {
  justify-content: flex-start;
}
h1, h2, h3 {
  font-family: var(--serif);
  color: var(--fg);
  font-weight: 700;
  letter-spacing: 0;
}
h1 { font-size: 50px; line-height: 1.18; }
h2 {
  font-size: 34px;
  line-height: 1.3;
  margin-bottom: .55em;
  width: max-content;
  max-width: 100%;
}
h2::after {
  content: '';
  display: block;
  width: 100%;
  height: 2px;
  margin-top: .34em;
  background: var(--accent);
}
h3 { font-size: 28px; color: var(--accent-deep); }
strong { color: var(--accent); font-weight: 700; }
blockquote {
  font-family: var(--serif);
  font-size: 1.02em;
  line-height: 1.42;
  color: var(--fg);
  border-left: 2px solid var(--accent);
  background: transparent;
  padding: .1em 0 .1em 1em;
  margin: .7em 0;
}
code {
  font-family: 'SFMono-Regular', 'JetBrains Mono', Menlo, Consolas, monospace;
  background: var(--paper-2);
  color: var(--fg);
  border-radius: 4px;
  padding: .06em .34em;
  font-size: .9em;
}
pre {
  background: var(--paper-2);
  border: 1px solid var(--line);
  border-radius: 4px;
  padding: .75em 1em;
  line-height: 1.45;
  margin: .45em 0 .75em;
}
pre code, pre code * { background: transparent; padding: 0; color: var(--fg); }
table {
  border-collapse: collapse;
  width: 100%;
  font-size: .82em;
  line-height: 1.35;
}
th, td {
  padding: .5em .7em;
  text-align: left;
  vertical-align: top;
  border: none;
  border-bottom: 1px solid var(--line);
}
th {
  font-weight: 700;
  border-bottom: 1.5px solid var(--fg);
}
tr:nth-child(even) td { background: rgba(42, 36, 28, .035); }
section::after { color: var(--muted); }
header { color: var(--muted); font-size: .58em; letter-spacing: .04em; }
footer { display: none; }
section p,
section ul,
section ol {
  margin-top: .35em;
  margin-bottom: .65em;
}
section li + li {
  margin-top: .12em;
}
section.lead {
  background: #241d16;
  color: var(--bg);
  justify-content: center;
  text-align: center;
}
section.lead h1, section.lead h2, section.lead h3 { color: var(--bg); }
section.lead h2::after { margin-left: auto; margin-right: auto; background: var(--accent-warm); }
section.lead strong { color: var(--accent-warm); }
section.lead header, section.lead footer { display: none; }
section.lead code { background: rgba(255, 255, 255, .14); color: var(--bg); }
.compact {
  font-size: 21px;
  line-height: 1.36;
}
.compact h2 {
  font-size: 31px;
  margin-bottom: .38em;
}
.compact pre {
  font-size: .8em;
  line-height: 1.28;
  padding: .62em .8em;
  margin: .28em 0 .5em;
}
.compact table {
  font-size: .74em;
  line-height: 1.22;
}
.compact th,
.compact td {
  padding: .34em .5em;
}
.compact blockquote {
  font-size: .96em;
  line-height: 1.34;
  margin: .45em 0;
}
.small { font-size: .82em; color: var(--muted); }
</style>

<!-- _class: lead -->
<!-- _paginate: false -->

# data-insight-kit

### 데이터 분석 에이전트가 대시보드까지 이어지는 방식

`intake -> connect -> explore -> frame -> analyze -> visualize -> qa -> communicate -> qa-post`

---

## 오늘의 목표

- `data-insight-kit`이 **무엇을 자동화하는지** 이해한다.
- 8개 에이전트가 **각자 무엇을 맡는지** 구분한다.
- `dashboard_data.json`과 QA 게이트가 왜 핵심인지 이해한다.
- Claude Code와 Codex가 같은 코어를 쓰는 구조를 본다.

> 핵심은 "대시보드를 직접 그리는 AI"가 아니라, **분석 계약을 따라 데이터를 주입하는 파이프라인**입니다.

---

## data-insight-kit이 해결하는 문제

대시보드 자동화에서 자주 생기는 문제:

- 분석 목적이 중간에 바뀐다.
- KPI 정의 없이 차트부터 만든다.
- LLM이 SVG 좌표와 숫자를 손으로 만들다가 값이 어긋난다.
- 멋진 HTML은 나오지만 검증 가능한 데이터 계약이 없다.

> `data-insight-kit`은 분석 절차, 데이터 계약, 렌더링, QA를 한 흐름으로 묶습니다.

---

## 전체 구조

```text
소스 어댑터
  ↓
로컬 입력/스냅샷
  ↓
8단계 에이전트 파이프라인
  ↓
dashboard_data.json
  ↓
templates/dashboard.html
  ↓
검증된 dashboard.html + summary_report.md
필요 시 deep_report.md
```

핵심 원칙:

- 분석 결과는 `dashboard_data.json` 하나로 표현
- HTML은 JSON을 읽어 순수 SVG로 렌더
- `qa/validate.py`가 출고 전 게이트 역할

---

## 단일 원천

`data-insight-kit`에서 가장 중요한 문서:

```text
docs/pipeline-contract.md
```

이 문서가 정하는 것:

- 단계 순서
- 각 단계의 입력과 출력
- 루프백 규칙
- QA 차단 기준
- 보안과 쓰기 경계
- 런타임 무관 코어 산출물

> Claude Code와 Codex는 실행 방식이 달라도 같은 계약을 봅니다.

---

<!-- _class: compact -->

## 파이프라인 지도

```text
0 intake
  -> 1 connect
  -> 2 explore
  -> 3 frame
  -> 4 analyze
  -> 5 visualize
  -> 6 qa(gate)
  -> 7 communicate
  -> qa-post
```

제한된 되돌림:

- `analyze`가 KPI와 데이터의 명백한 불일치를 찾으면 `frame`으로 1회
- `qa`가 기계적 결함을 찾으면 `visualize`로 1회
- `qa-post`가 보고서 깊이 미달을 찾으면 `communicate`로 1회

무한 자동수정은 금지합니다.

---

## 0. intake

역할:

- 이 분석이 **누구를 위해 무엇에 답하는지** 확정
- `directed`와 `exploratory` 모드 결정
- 목적이 모호하면 질문형 intake로 의사결정 맥락 확인
- `--guided-intake` 검증 모드는 draft 경유와 finalization trace 강제

출력:

```text
manifest.json#intake
mode, objective, decision_context, analysis_mode, report
```

좋은 intake는 이후 모든 단계의 기준점입니다.

---

<!-- _class: compact -->

## 1. connect

역할:

- 로컬 파일·원격 Parquet 스냅샷·선택 DuckDB를 연결
- 목적에 맞는 테이블과 컬럼을 선별
- 품질 진단과 의미층을 정리

출력:

```text
intermediate/*.parquet
outputs/01_profile.md
manifest.sources[]
```

> connect는 분석하지 않습니다. 안전하게 연결하고 다음 단계가 믿고 쓸 데이터를 만듭니다.

---

<!-- _class: compact -->

## 2. explore

역할:

- 정제 데이터를 탐색해 패턴을 찾음
- 방법론 후보와 핵심 질문을 도출

보는 것:

- 일변량 분포
- 다변량 관계
- 시계열 추세와 변곡
- 범주별 차이

출력:

```text
outputs/02_eda.md
```

---

<!-- _class: compact -->

## 3. frame

역할:

- 발견한 패턴을 **답해야 할 비즈니스 문제**로 바꿈
- KPI를 이름, 계산식, 단위, 분모까지 확정

출력:

```text
outputs/03_frame.md
```

여기서 정하는 것:

- 메인 문제
- MECE 원인 구조
- KPI 정의표
- 핵심 질문 Top 3

---

<!-- _class: compact -->

## 4. analyze

역할:

- KPI와 질문을 데이터로 검증
- General -> Specific 흐름으로 인사이트와 액션 도출
- 차트에 들어갈 수치를 계산

출력:

```text
outputs/04_analysis.md
intermediate/<chart-ready>.parquet
```

> 대시보드의 가치는 화려한 화면보다 이 단계의 비자명한 인사이트에서 나옵니다.

---

<!-- _class: compact -->

## 5. visualize

역할:

- 분석 결과를 `dashboard_data.json` 스키마에 맞게 구성
- 템플릿에 JSON을 주입해 `dashboard.html` 생성

금지:

- 분석에 없는 지표 임의 추가
- 수치 자체에 색 부여
- CDN 차트 라이브러리 추가
- 근거 없는 시뮬레이터 생성

> 직접 SVG를 그리는 단계가 아니라, 렌더러가 읽을 데이터를 만드는 단계입니다.

---

<!-- _class: compact -->

## 6. qa

역할:

- 출고 게이트
- `dashboard_data.json`과 렌더 결과 검증
- 라벨 겹침·잘림·과대 차트 차단

실행:

```bash
python qa/validate.py runs/<run-id>/outputs/dashboard_data.json \
  --chart-spec runs/<run-id>/outputs/chart_spec.json
```

BLOCK이면 communicate로 넘어가지 않습니다.

---

<!-- _class: compact -->

## 7. communicate

역할:

- 분석과 대시보드를 선택된 독자와 깊이에 맞는 요약 보고서로 정리
- 같은 `dashboard_data.json`의 수치를 인용
- `depth=deep`이면 심층 보고서 작성

출력:

```text
outputs/summary_report.md
outputs/deep_report.md  # depth=deep
```

원칙:

- 재계산 금지
- post-communicate QA 통과
- 핵심 발견
- 판단과 우선순위 액션
- 데이터 신뢰성 메모

---

<!-- _class: compact -->

## 에이전트별 한 줄 요약

| 단계 | 질문 | 산출물 |
|---|---|---|
| intake | 왜, 누구를 위해 분석하나 | manifest intake |
| connect | 어떤 데이터를 믿고 쓸 수 있나 | profile, parquet |
| explore | 데이터가 어떤 패턴을 보이나 | EDA |
| frame | 무엇을 문제와 KPI로 잡을까 | frame |
| analyze | 어떤 의미와 액션이 나오나 | analysis |
| visualize | 어떤 데이터로 화면을 만들까 | dashboard data/html |
| qa | 출고해도 되는가 | gate result |
| communicate | 무엇을 알리고 실행할까 | summary report |

---

## 데이터 계약이 중심인 이유

`dashboard_data.json`은 분석과 화면 사이의 계약입니다.

담는 것:

- KPI 값, 단위, 분모, 계산 근거
- 차트 x축과 series 값
- 색상 role
- 스토리와 액션
- 시뮬레이터 모델과 테스트 케이스

> 렌더러는 이 계약만 읽습니다. 그래서 값과 화면의 불일치를 줄일 수 있습니다.

---

## QA가 보는 것

스키마만 보는 것이 아닙니다.

- KPI와 series의 metric 시드
- source reference 유효성
- x축 길이와 series 길이
- 허용된 chart stack 값
- placeholder 잔존 여부
- 시뮬레이터 test case
- Playwright 렌더 시 콘솔 에러와 빈 화면
- 모든 탭의 desktop/mobile 라벨 겹침·잘림·과대 SVG

> "파일이 만들어졌다"가 아니라 "출고 가능한가"를 묻습니다.

---

<!-- _class: compact -->

## Claude Code와 Codex의 경계

공유 코어:

```text
docs/ schemas/ connectors/ qa/ templates/ themes/
```

Claude Code 어댑터:

```text
.claude-plugin/
agents/*.md frontmatter
skills/run-pipeline/
```

Codex 어댑터:

```text
AGENTS.md
scripts/run_codex_pipeline.sh
```

> 어댑터는 다르지만, 파이프라인 계약과 코어는 하나입니다.

---

<!-- _class: compact -->

## Codex 실행 흐름

```bash
cd data-insight-kit
bash scripts/run_codex_pipeline.sh <run-id>
```

wrapper가 하는 일:

- 단계별로 `codex exec` 실행
- 단계별 reasoning effort 부여
- 산출물이 있으면 캐시 재사용
- QA는 `qa/validate.py`로 강제

```bash
bash scripts/run_codex_pipeline.sh <run-id> --dry-run
bash scripts/run_codex_pipeline.sh <run-id> --fresh
```

---

<!-- _class: compact -->

## run 폴더 구조

```text
runs/<run-id>/
├── input/                 # CSV/Parquet/Excel/JSON 또는 원격 snapshot
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

이 경계가 재현성과 보안을 지킵니다.

---

<!-- _class: compact -->

## 모델 티어

| 티어 | 단계 | Codex/OpenAI quality |
|---|---|---|
| 경량 | intake, qa | gpt-5.5 + low |
| 실행 | connect, visualize, communicate | gpt-5.5 + medium |
| 사고 | explore, frame, analyze | gpt-5.5 + high |

상위 모델과 높은 reasoning은 모든 곳이 아니라, 판단 품질을 바꾸는 단계에 집중합니다.

---

<!-- _class: lead -->

## 정리

`data-insight-kit`은 대시보드 생성기가 아니라,

### 분석 목적 -> 데이터 탐색 -> KPI 정의 -> 인사이트 -> 데이터 계약 -> 렌더 -> QA -> 보고서

까지 이어지는 **검증 가능한 에이전트 파이프라인**입니다.
