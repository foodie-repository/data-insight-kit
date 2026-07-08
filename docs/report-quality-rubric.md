# Report Quality Rubric

이 문서는 `summary_report.md`와 `deep_report.md`의 품질 기준이다. 목적은 보고서가
대시보드 수치를 단순 재서술하지 않고, 사용자의 의사결정에 필요한 판단 구조를
제공하게 만드는 것이다.

## 역할 분리

| 산출물 | 목적 | 독자 경험 | 금지 |
|---|---|---|---|
| `summary_report.md` | 빠른 이해와 다음 행동 요약 | 3~5분 안에 핵심 판단, 주요 근거, 주의점 파악 | 긴 방법론 설명, 모든 차트 재서술 |
| `deep_report.md` | 분석 검토와 실행 기준 확정 | 방법론, KPI, 세그먼트 차이, 반대 해석, 한계, 액션 기준까지 검토 | `04_analysis.md` 복사, 차트 목록 나열, 근거 없는 권고 |
| `external_context.md` | 선택적 외부 맥락 보강 | 데이터 기반 발견과 외부 맥락의 차이를 분리해 확인 | 웹 자료를 데이터셋 검증 사실처럼 표현 |

`audience`는 표현의 강조점이고, `depth`는 분석 상세 수준이다. 따라서
`audience=executive`라고 해서 보고서 이름을 임원용으로 고정하지 않는다.

## Deep Report 필수 구조

`report.depth=deep`이면 `outputs/deep_report.md`는 아래 구조를 갖는다.

```markdown
# <주제> 심층 보고서
## 의사결정 질문
## 방법론과 데이터 한계
## KPI 정의
## 핵심 발견
## 세그먼트/분포/관계/추세 분석
## 반대 해석과 리스크
## 실행 시나리오
## 추가 분석 설계
## 부록: chart_spec / lineage
```

데이터가 특정 섹션을 충분히 지원하지 않으면 섹션을 삭제하지 않는다. 대신
"현재 데이터로 불가능한 이유"와 "필요한 추가 데이터"를 쓴다.

## 품질 루브릭

| 항목 | 통과 기준 | 미달 신호 |
|---|---|---|
| 의사결정 연결 | 첫 부분에서 사용자가 내릴 판단과 선택지를 명시 | 데이터 소개만 있고 판단 질문이 없음 |
| 방법론 | 데이터 형태에 맞는 전략과 선택 이유를 설명 | 차트가 왜 필요한지 설명 없음 |
| KPI 정의 | 이름, 계산식, 단위, 분모, 비교 기준 포함 | 수치만 있고 분모·단위가 없음 |
| 세그먼트 분석 | 전체 평균과 다른 주요 세그먼트 차이를 설명 | 상위 N개 목록만 반복 |
| 다각도 분석 | 분포/관계/추세/구성 중 가능한 2개 이상 검토 | 같은 막대 차트 해석만 반복 |
| 차트 스토리 | chart_spec의 각 차트가 서로 다른 질문에 답하고, dashboard_story가 판단 흐름을 제공 | 차트 목록만 있고 사용자가 무엇을 봐야 하는지 불명확 |
| 차트-보고서 연결 | 보고서 핵심 발견이 chart_spec의 finding/evidence/limit와 연결 | 차트는 있는데 보고서가 수치를 다시 나열하거나 별개로 서술 |
| 반대 해석 | 핵심 발견마다 대체 설명 또는 리스크 제시 | 단정적 결론만 있음 |
| 한계 | 표본, 기간, 누락 컬럼, 외부 기준 부족을 구분 | "한계 있음"만 쓰고 영향 설명 없음 |
| 액션 기준 | 실행/보류/추적 조건이나 임계값 제시 | "검토 필요" 같은 일반론 |
| lineage | chart_spec, source_ref, 계산 근거와 연결 | 보고서 수치 출처를 따라갈 수 없음 |
| external adapter lineage | 외부 context 사용 시 adapter category, metric layer, source_ref, 기준일, 분석 grain, join key, coverage/null rate, acquisition, aggregation basis, coarse join 여부 포함 | 외부 데이터를 썼지만 수집 범위·조인 품질·정밀도 한계가 없음 |
| adapter interpretation guard | registry의 허용/금지 해석을 지키고 layer별로 결론을 분리 | risk/context layer만으로 추천·성공 가능성을 단정 |

## 깊이별 최소 기준

- `brief`: 핵심 발견 1~3개, 바로 볼 액션, 주요 한계 1개.
- `standard`: 핵심 KPI, 발견 3~5개, 차트별 해석 요약, 액션/다음 질문, 데이터 신뢰성 메모.
- `deep`: 위 필수 구조 전체, 발견 5~7개 이하, 세그먼트 비교, 반대 해석, 액션 기준,
  추가 분석 설계, chart_spec/lineage 부록.

## QA 판정 기준

post-communicate QA는 다음을 BLOCK으로 본다.

- `depth=deep`인데 `deep_report.md`가 없다.
- `deep_report.md`가 필수 구조를 상당 부분 누락했다.
- `deep_report.md`가 `04_analysis.md`와 과도하게 유사해 단순 복사로 보인다.
- 방법론, KPI, 세그먼트/분포/관계/추세, 반대 해석, 한계, 액션 기준, lineage 중
  핵심 요소가 빠졌다.
- `chart_spec.json`에 dashboard_story가 없거나, deep 분석인데 질문별 차트 수·방법론·차트 유형이 지나치게 단조롭다.
- 차트별 `insight.finding/evidence/limit`가 너무 짧거나 질문을 반복할 뿐이다.
- `evidence_scope=web_context`인데 `external_context.md`가 없거나 데이터 기반 발견과
  외부 맥락을 분리하지 않는다.

다음은 WARN으로 본다.

- `summary_report.md`가 지나치게 길어 deep report와 역할이 흐려진다.
- `chart_spec.json`이 충분한 데이터 구조를 가졌는데도 방법론과 차트 유형이 지나치게 단조롭다.
- `dashboard_data.json`의 차트 설명이 chart_spec의 수치 근거를 충분히 전달하지 못한다.
- deep report가 차트 ID나 source_ref를 거의 언급하지 않아 추적성이 약하다.
- 외부 denominator/context adapter를 썼는데 dashboard에는 coarse/context join 한계가 약하게만 표시된다.
- 외부 adapter category를 `custom`으로 썼지만 반복 패턴이어서 registry 승격 검토가 필요하다.
