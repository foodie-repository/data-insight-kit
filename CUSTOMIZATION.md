# CUSTOMIZATION.md

`data-insight-kit`은 범용 core와 도메인 확장을 분리합니다.

core는 데이터 연결, 탐색, 분석 설계, 차트 설계, 대시보드 렌더링, QA를 담당합니다.
도메인 지식은 **인터뷰**로 시작해 쌓고, 반복 사용할 지식만 `domain pack`으로
승격합니다 (상세 계약: `docs/specs/interview-loop-v2.md` §8).

## 시작은 인터뷰: domain pack 없이 (기본 경로)

처음 도메인 데이터를 다룰 때는 pack 파일을 만들 필요가 없습니다.

1. run의 `manifest.json`에 `"domain_mode": true`를 표시하면(또는 intake에서
   회사·업무 데이터라고 밝히면) 각 확인 단계 질문에 추가 확인 질문이 부족한
   항목 우선으로 붙습니다 — 행의 의미, 핵심 대상, 컬럼 의미, 제외 기준(데이터
   확인) → 지표 계산 기준, 비교 축, 기준 자료, 피해야 할 표현(분석 방향) →
   판단 범위(1차 결과 확인) → 용어(보고서).
2. 추가 확인 질문의 답변은 진행 여부와 무관하게 해석 기준으로만 쌓입니다.
   업무 기준이 부족한 채 진행하면 도메인 결론(추천·원인·성과 확정)은 QA가
   차단합니다 — 인터뷰는 기회를 늘릴 뿐 게이트를 약화하지 않습니다.
3. 답변이 쌓이면 도메인 확인 정보를 파생 생성합니다.

```bash
python3 scripts/build_domain_intake.py <run-id>
# -> runs/<run-id>/input/domain_intake.json (수동 작성 파일이 있으면 그 파일 우선)
```

4. run에서 검증된 재사용 지식은 `outputs/domain_pack_update_candidates.md`에
   후보로 남기고, 사람이 검토해 pack으로 승격합니다(아래 절차). run 중
   `domains/<domain>/` 자동 수정은 훅이 차단합니다.

pack이 이미 있으면 인터뷰는 pack이 못 덮는 이번 run의 불확실성만 묻게 되어
짧아집니다.

## domain pack이 필요한 경우

다음 중 하나라도 해당하면 domain pack을 만드는 것이 좋습니다.

- 회사 내부 용어가 일반 용어와 다르다.
- KPI 계산식, 분모, 단위, 비교 기준이 정해져 있다.
- 좋은 결과와 나쁜 결과의 기준이 업무마다 다르다.
- 특정 표현을 보고서에서 쓰면 안 된다.
- 자주 쓰는 세그먼트, 기간, 필터, 비교축이 있다.
- 대시보드에서 선호하는 차트 흐름이 있다.
- 보고서 독자와 문체가 정해져 있다.

## domain pack의 역할

domain pack은 자동으로 결론을 내리는 규칙 파일이 아닙니다. 다음을 돕는 보조
계약입니다.

- 사용자에게 더 정확한 질문을 하기
- 도메인 전문가의 의도를 intake와 checkpoint 답변으로 남기기
- KPI와 차트가 도메인 판단 질문에 맞는지 확인하기
- 보고서가 금지 표현이나 과한 결론을 쓰지 않게 하기
- 반복 업무에서 같은 기준을 재사용하기

core 계약과 충돌하면 항상 `docs/pipeline-contract.md`, schema, QA가 우선합니다.

## 만드는 순서

1. 템플릿을 복사합니다.

```bash
cp -R domains/template domains/my-domain
```

2. `domain.yaml`에 도메인 이름과 적용 조건을 씁니다.
3. `terminology.md`에 내부 용어와 사용자용 표현을 정리합니다.
4. `kpi-rules.md`에 KPI 정의, 분모, 단위, 비교 기준을 씁니다.
5. `interview-questions.md`에 도메인 전문가에게 물어볼 질문을 씁니다.
6. `dashboard-patterns.md`에 자주 쓰는 차트 흐름과 피해야 할 차트를 씁니다.
7. `report-rubric.md`에 보고서 구조와 독자별 강조점을 씁니다.
8. `qa-rules.md`에 금지 표현과 근거 요구사항을 씁니다.

## 파일별 작성 가이드

| 파일 | 작성할 내용 |
|---|---|
| `domain.yaml` | domain id, 적용 조건, 기본 분석 모드 후보, 참조 문서 목록 |
| `terminology.md` | 내부 용어, 사용자용 표현, 피해야 할 약어 |
| `kpi-rules.md` | KPI 이름, 계산식, 단위, 분모, 비교 기준, 해석 한계 |
| `interview-questions.md` | 시작 질문, 데이터 확인 후 질문, 분석 전략 질문, 보고서 질문 |
| `dashboard-patterns.md` | 추천 차트 흐름, 차트 선택 기준, 보류할 차트 |
| `report-rubric.md` | 요약 보고서와 심층 보고서의 필수 구조 |
| `qa-rules.md` | 금지 표현, 근거 부족 시 경고, 독자용 문구 기준 |

## 실행에 연결하기

Codex Desktop이나 Claude Code에서 사용할 때는 일반 실행과 동일하게 먼저
**Plan Mode**에서 사용자용 분석 기획안과 domain pack 적용 범위를 확인합니다.
도메인 기준이 결론, KPI, 차트 구성, 보고서 문체를 바꿀 수 있기 때문에 승인 없이
바로 `/run-pipeline`이나 최종 생성으로 넘어가지 않습니다.

가장 단순한 방법은 `DIK_DOMAIN_PACK`을 지정하는 것입니다.

```bash
DIK_DOMAIN_PACK=domains/my-domain/domain.yaml \
  DIK_USER_REQUEST="이 데이터로 분석 보고서와 대시보드를 만들어줘" \
  bash scripts/run_codex_pipeline.sh my-run --guided-intake
```

run 입력 폴더에 참조 파일을 둘 수도 있습니다.

```bash
mkdir -p runs/my-run/input
printf 'domains/my-domain/domain.yaml\n' > runs/my-run/input/domain_pack_ref.txt
bash scripts/run_codex_pipeline.sh my-run --guided-intake
```

wrapper는 선택된 domain pack을 다음 파일로 정리합니다.

```text
runs/my-run/input/domain_pack_context.md
runs/my-run/domain_pack_context.md
```

이 컨텍스트는 이후 stage가 참고합니다. 다만 domain pack 내용이 결론을 바꾸거나
추가 도메인 판단을 요구하면, 해당 내용은 중간 확인 단계에서 사용자에게 다시
물어야 합니다.

## 좋은 domain pack의 기준

- 초보 사용자에게도 질문이 쉬운 말로 제시된다.
- 도메인 전문가는 KPI와 보고서 기준이 맞는지 검토할 수 있다.
- 데이터에 없는 판단을 보고서가 단정하지 않는다.
- 차트는 하나의 질문에 답하고, 보고서의 핵심 발견과 연결된다.
- 금지 표현은 "왜 금지인지"와 "어떤 근거가 있으면 가능한지"를 함께 적는다.
- 모호한 도메인 판단은 자동 결론이 아니라 사용자 질문으로 전환된다.

## 피해야 할 방식

- domain pack에 특정 결론을 하드코딩하기
- 데이터에 없는 수요, 비용, 성과, 원인을 단정하기
- 모든 도메인에 같은 KPI와 차트 흐름을 강제하기
- 사용자 확인 없이 도메인 기준으로 결론 수위를 높이기
- 보고서용 표현에 내부 컬럼명이나 약어를 그대로 노출하기

## 최소 예시

`domains/my-domain/interview-questions.md`에는 다음처럼 질문 후보를 둘 수 있습니다.

```md
# Interview Questions

## 시작 질문
- 이번 분석으로 어떤 판단을 하시려나요?
- 분석 대상과 기간은 어디까지로 볼까요?
- 결과를 볼 독자는 누구인가요?

## 데이터 확인 후 질문
- 데이터 샘플과 분석 단위가 업무 기준과 맞나요?
- 제외해야 할 테스트 데이터나 특수 케이스가 있나요?

## 대시보드 구성 질문
- 규모, 변화, 차이, 예외 중 무엇을 첫 화면에서 우선 보여줄까요?
- 특정 세그먼트를 별도 탭으로 분리해야 하나요?
```

`domains/my-domain/qa-rules.md`에는 다음처럼 표현 규칙을 둘 수 있습니다.

```md
# QA Rules

- 데이터에 없는 원인은 단정하지 않는다.
- 성과 지표가 없으면 "성과가 좋다/나쁘다"라고 쓰지 않는다.
- 추천 표현은 필요한 근거 데이터가 모두 있을 때만 쓴다.
- 내부 코드값은 제목이나 요약 문장에 노출하지 않는다.
```

이 정도만 있어도 guided intake와 checkpoint 질문이 도메인에 더 맞게 바뀝니다.
