# Dashboard Freeform v5 → v5.1 Smoke Comparison

검토일: 2026-07-18
기준: `docs/specs/visual-quality-convergence-v5.1.md` §12의 10개 항목

## 결론

v5.1은 기존 v5보다 차트를 더 많이 만들거나 화면을 더 화려하게 만드는 버전이
아니다. 같은 질문을 반복하는 카드와 차트를 줄이고, 판단 목적·지표 정의·척도·색·
라벨·반응형·눈검토를 구조화된 계약과 fail-closed QA로 고정한 품질 수렴 버전이다.

두 v5 baseline과 두 v5.1 smoke 모두 최종 hard BLOCK은 0이다. v5.1은 여기에
decision/metric/visual 계약, 4개 viewport, screenshot hash, 구조화된 눈검토,
숫자 표기 gate를 추가했다. 따라서 출고 신뢰성과 재현성은 v5.1이 높다. 다만
time-series v5에 있던 산점도·slope·heatmap 같은 탐색 폭은 줄었으므로, v5.1의
우위는 “더 많은 차트”가 아니라 “더 명확한 판단 흐름과 검증 가능한 표현”이다.

## 비교 대상

| 성격 | v5 baseline | v5.1 |
|---|---|---|
| snapshot·구성/분포 | `sbiz-gangnam-v5-freeform-smoke-20260714` | `sbiz-gangnam-v51-visual-quality-smoke-20260717` |
| time-series·다중 계열 | `apt-sale-v5-freeform-smoke-20260714` | `apt-sale-v51-visual-quality-smoke-20260717` |

time-series 두 run은 원천 SHA-256
`8a335059deee8836286728a1d5c6b339bfba659ac4b88587fec2cdd7ff08cde2`가
같다. v5.1은 baseline 산출물을 입력으로 복사하지 않고 원천 Parquet부터 다시
분석했다.

## 10개 공통 기준

| 기준 | v5 | v5.1 | 판정 |
|---|---|---|---|
| 1. 판단 목적과 지표 역할 | 질문과 insight는 있으나 decision brief와 metric role은 구조화되지 않음 | decision brief, 7개 metric의 hero/diagnostic/guardrail/detail 역할, 분모·기간·source를 계약으로 보존 | v5.1 개선 |
| 2. 질문 중복과 데이터 충분성 | 최종 화면은 유효하나 중복·최소 관측 수·fallback이 자동 계약이 아님 | chart question, observed count, distinct/category/series 수, fallback과 component evidence를 정적 검사 | v5.1 개선 |
| 3. 문구·기간·단위 | 사용자 피드백 뒤 실제 연월·만원 표현으로 보정 | 실제 연월·단위·범위에 더해 1,000 이상 측정값의 천 단위 구분기호를 KPI·축·라벨·tooltip·표·설명에 강제 | v5.1 개선 |
| 4. 척도와 패널 분리 | time-series revision에서 가격·거래량을 indexed 독립 패널로 보정 | 단위가 다른 계열은 독립 패널, 같은 단위 변화율은 음수를 보존하는 공유 0 기준축, bar는 0 포함을 계약으로 검사 | v5.1 개선 |
| 5. 색과 비색상 채널 | role 색과 heatmap 대비는 있으나 차트별 의미 계약은 제한적 | palette mode와 role mapping, pattern/line style/shape 등 비색상 채널을 chart contract에 명시 | v5.1 개선 |
| 6. 직접 라벨·범례 | desktop/mobile에서 최종 겹침은 없으나 긴 identity legend가 페이지형으로 남음 | direct/axis/legend 전략, 단일 계열 legend 제거, longest-label 여백, narrow fallback을 사전 계획 | v5.1 개선 |
| 7. 반응형 | desktop 1440px·mobile 390px 2개 screenshot | desktop 1440px·compact 736px·mobile 390px·narrow 320px 4개 screenshot과 browser BLOCK | v5.1 개선 |
| 8. 최소 구성 | time-series 6 KPI와 6개 차트로 탐색 폭이 넓음 | 4 KPI와 6개 차트로 서울 흐름→최근월 경고→구별 수준·변화·분포에 집중; 빈 component는 hide/block | v5.1 개선, 탐색 폭은 감소 |
| 9. QA와 수정 기록 | 최종 hard BLOCK 0이나 눈검토가 구조화 파일로 남지 않음 | 최종 hard BLOCK 0, screenshot hash와 6개 관찰 항목을 `visual_review.json`에 보존 | v5.1 개선 |
| 10. lineage와 재현성 | source·build manifest·checkpoint는 있으나 품질 계약과 눈검토 연결이 약함 | source→metric→chart→component evidence와 승인 layout hash, build manifest, visual review hash를 교차검사 | v5.1 개선 |

## 화면 직접 비교 관찰

### snapshot

- v5.1은 행정동·업종 구성·상대 집중도를 decision 흐름으로 묶고, 사용자가 화면을
  받은 뒤 추가 수정은 없었다.
- 첫 내부 눈검토에서 배수 문구 1건을 `revise`로 판정해 전달 전에 수정했다.
- v5 baseline도 최종 화면은 hard BLOCK 0이지만, 네 viewport와 구조화된 눈검토
  증거는 없다.

### time-series

- v5는 월별 지수, 구별 가격·거래량 순위, 산점도, slope, heatmap으로 탐색 폭이
  넓다. 다만 KPI가 6개이고 서로 다른 질문이 한 화면에 많아 첫 판단이 분산된다.
- v5.1은 KPI를 4개로 줄이고 서울 전체 가격·거래량 흐름을 첫 질문으로 고정했다.
  가격과 거래량은 같은 월축의 독립 패널로, 전년동월 변화율은 공유 0 기준축으로
  보여 단위와 척도 해석이 명확하다.
- v5.1 내부 QA가 control/reset 연결과 음수 막대 소실을 사용자 최종 전달 전에
  발견해 layout revision 2 재승인으로 복구했다.
- 사용자 전달 뒤에는 숫자 구분기호 불일치 1건이 남았고, 이를 단일 run 수정이
  아니라 제품 공통 static/render QA 규칙으로 승격했다.
- 최종 네 화면에서 `107,892`, `10,970`, `6,656`, `238,228`,
  `50,000–75,000`이 일관되며 숫자 길이로 생긴 새 겹침·잘림은 없다.

## QA 수치 해석

WARN 개수는 v5와 v5.1의 검사 범위가 달라 우열 지표로 사용하지 않는다. v5.1은
두 viewport가 추가되고 hero/support 면적, visual review, tooltip, fallback 같은
새 검사를 수행한다. 공통 출고 조건은 hard BLOCK 0이다.

- v5.1 snapshot: browser QA `BLOCK 0`, qa-post `BLOCK 0`
- v5.1 time-series: browser/qa-post 실제 Chromium `BLOCK 0`, `WARN 6`
- time-series qa-post의 render 제외 계약 검사는 `BLOCK 0`, `WARN 2`

남은 WARN은 trend method와 bar 표현 조합 확인, human checkpoint 검사 안내,
Playwright 고정 fallback 사용, 일부 화면의 hero/support 면적 비교다. 현재 데이터·
표현·checkpoint lineage의 hard failure는 아니다.

## Release 판단

v5.1은 두 smoke에서 다음 완료 조건을 충족하므로 release close가 가능하다.

- 실제 사용자 checkpoint 답변으로 두 run 완료
- 두 run hard BLOCK 0, 보고서 qa-post 완료
- 네 viewport와 직접 눈검토 완료
- 반복 피드백이었던 내부 문구, 단위, 척도, 색, 범례, 숫자 표기를 제품 계약으로 고정
- Claude Code/Codex adapter가 같은 core wrapper와 checkpoint gate를 호출
- 공식 plugin 코드·prompt·asset·runtime과 개인 `~/.codex/skills/visualize`에 의존하지 않음

`runs/*`는 비교 근거로만 보존하며 git commit 대상이 아니다.
