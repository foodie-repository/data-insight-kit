# QA Rules

도메인 특화 QA 기준을 적는다.

## 금지 표현

| 표현 | BLOCK/WARN | 허용 조건 | 대체 표현 |
|---|---|---|---|
| `<phrase>` | BLOCK | `<required_evidence>` | `<replacement>` |

## 근거 요구사항

- 외부 context를 사용하면 source_ref, 기준일, 분석 단위, join key, coverage를 보고서에 남긴다.
- 데이터에 없는 원인, 성과, 미래 결과는 확정하지 않는다.
- 도메인 전문가가 승인하지 않은 KPI 가중치는 종합 점수로 쓰지 않는다.
