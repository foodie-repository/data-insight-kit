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
