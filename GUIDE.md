# GUIDE.md

이 문서는 `data-insight-kit`을 처음 사용하는 사람이 데이터에서 분석 보고서와
대시보드까지 만드는 과정을 설명합니다.

## 1. 먼저 실행 환경을 고릅니다

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

Claude Code에서 plugin을 쓸 때도 기준은 같습니다. Plan Mode에서 사용자용
분석 기획안과 실행 계획을 먼저 확인한 뒤, 승인 후 `/run-pipeline`을
사용합니다.

```text
/plugin marketplace add /path/to/data-insight-kit
/plugin install data-insight-kit
# Plan Mode에서 사용자 요청과 실행 계획을 먼저 확인
/run-pipeline my-first-run
```

터미널에서 직접 실행할 때는 `--guided-intake`를 사용합니다. 이 방식은 AI 앱의
질문 UI를 쓰지 않고 파일 기반 질문/답변 handoff를 직접 처리합니다.

```bash
DIK_USER_REQUEST="이 데이터로 분석 보고서와 대시보드를 만들어줘" \
  bash scripts/run_codex_pipeline.sh my-first-run --guided-intake
```

## 2. 분석 대상을 정합니다

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

## 3. 입력 파일을 둡니다

```bash
cd data-insight-kit
mkdir -p runs/my-first-run/input
cp /path/to/data.csv runs/my-first-run/input/
```

CSV, Parquet, Excel, JSON을 사용할 수 있습니다. 파일이 여러 개면 같은
`input/` 폴더에 둡니다.

API URL을 입력으로 줄 수도 있습니다. 이 경우에는 먼저 원천 연결과 수집 가능
여부를 확인하고, 성공하면 로컬 스냅샷을 만든 뒤 분석합니다.

## 4. guided intake로 시작합니다

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

AI 앱을 쓰는 경우에는 위 파일을 직접 열어보는 대신, 상위 에이전트가 질문 요약을
채팅창이나 팝업으로 보여줍니다. 중요한 점은 동일합니다. 사용자의 실제 답변이
기록되기 전에는 다음 단계로 넘어가지 않습니다.

## 5. 데이터 확인 단계에서 멈춥니다

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

## 6. 분석 방향을 고릅니다

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

## 7. 대시보드 구성안을 고릅니다

분석이 끝나면 바로 대시보드를 만들지 않고, 먼저 차트 구성을 보여줍니다.

확인할 것:

- 각 차트가 어떤 질문에 답하는가?
- 어떤 데이터와 지표를 쓰는가?
- 왜 이 차트가 추천되는가?
- 대안 차트는 무엇이고 왜 보류했는가?
- 제목과 설명이 배포용 독자에게 이해되는가?

진행하려면:

```bash
python3 scripts/apply_checkpoint_answer.py my-first-run dashboard_storyboard \
  --option approve_storyboard \
  --source user_chat \
  --user-response "추천 구성안으로 진행하고, 차트 제목은 독자가 바로 이해할 수 있게 풀어 써 주세요."
```

단순 순위표가 반복되거나 원하는 판단에 답하지 못하면 이 단계에서 수정 요청을
남기는 것이 좋습니다.

## 8. 보고서 구성안을 확인합니다

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

## 9. 최종 산출물을 확인합니다

주요 산출물:

```text
runs/my-first-run/outputs/dashboard.html
runs/my-first-run/outputs/summary_report.md
runs/my-first-run/outputs/deep_report.md
runs/my-first-run/outputs/chart_spec.json
runs/my-first-run/outputs/dashboard_data.json
```

대시보드는 브라우저에서 열어 보고, 보고서는 결론 수위와 한계를 확인합니다.

## 10. QA를 실행합니다

```bash
python3 qa/validate.py runs/my-first-run/outputs/dashboard_data.json \
  --chart-spec runs/my-first-run/outputs/chart_spec.json

python3 qa/validate.py runs/my-first-run/outputs/dashboard_data.json \
  --chart-spec runs/my-first-run/outputs/chart_spec.json \
  --no-render --post-communicate
```

BLOCK이 있으면 완료가 아닙니다. 원인을 고친 뒤 다시 실행합니다.

## 11. 도메인용으로 쓰고 싶다면

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

## 12. 자동 실행이 필요한 경우

회귀 테스트나 배치 실행처럼 사람 확인을 건너뛰어야 할 때만 `--auto` 또는
`--no-checkpoints`를 명시합니다.

```bash
bash scripts/run_codex_pipeline.sh my-first-run --auto
```

일반 분석 작업에서는 권장하지 않습니다. 사용자 의도와 차트 구성을 놓치기 쉽기
때문입니다.
