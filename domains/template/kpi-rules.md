# KPI Rules

도메인 KPI는 이름, 계산식, 단위, 분모, 비교 기준을 명확히 적는다.

| KPI | 계산식 | 단위 | 분모 | 비교 기준 | 필요한 데이터 | 주의 |
|---|---|---|---|---|---|---|
| `<kpi_name>` | `<formula>` | `<unit>` | `<denominator>` | `<baseline>` | `<columns/sources>` | `<limitations>` |

## KPI 작성 원칙

- 절대값과 상대값을 섞지 않는다.
- 분모가 없으면 비율이나 효율로 표현하지 않는다.
- 표본이 작으면 결론이 아니라 후보 신호로 표현한다.
- 외부 context가 필요한 KPI는 source_ref와 coverage를 요구한다.

## 증거 출처 구분 (evidence class)

KPI 해석에는 증거 출처를 구분해 적는다 (spec §8.6).

| evidence class | 의미 | KPI 규칙에서의 쓰임 |
|---|---|---|
| `observed_from_data` | 이번 run 입력에서 직접 계산한 사실 | 계산식·분모가 데이터 컬럼만으로 완결 |
| `domain_rule` | 전문가·domain pack이 제공한 업무 기준 | 임계값·등급 기준·비교 baseline의 출처 표기 |
| `inferred` | 데이터 사실 + 업무 기준의 결합 해석 | "기준 대비 낮음" 같은 판정 — 두 출처 모두 명시 |
| `unsupported` | 현재 데이터·기준으로 말할 수 없음 | 결론 금지 — 필요한 데이터를 주의 칸에 적는다 |
