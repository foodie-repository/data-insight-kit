# Analysis Strategy Library

이 문서는 `data-insight-kit`이 임의 표 데이터에서 단순 요약을 넘어서기 위해 사용하는
범용 분석 전략 라이브러리다. 특정 도메인 팩이 없어도 `explore -> frame ->
analyze -> visualize -> communicate` 단계는 이 문서를 기준으로 데이터 형태에 맞는
전략을 고른다.

## 사용 원칙

- 먼저 데이터 형태를 판정하고, 그 형태가 허용하는 질문만 만든다.
- 모든 전략은 `KPI 정의 -> 분해 축 -> 비교 기준 -> 한계 -> 액션 기준`을 가져야 한다.
- 상위 N개, 단순 건수, 단순 비율만 반복하면 심층 분석으로 보지 않는다.
- 분모, 기준 기간, 비교군, 표본 크기가 없으면 결론 강도를 낮추고 필요한 추가 데이터를 쓴다.
- 여러 전략이 가능하면 주 전략 1개와 보조 전략 1~2개만 고른다. 차트 다양성을 위해
  근거 없는 전략을 억지로 추가하지 않는다.
- 외부 보정 데이터가 있으면 기존 지표의 의미를 바꾸지 말고 별도 근거 layer로 결합한다.
  기본 데이터의 건수·비율·순위·집중도는 관찰된 구조이고, 외부 데이터는
  수요·비용·성과·맥락·공간 보정 같은 별도 판단 근거다.

## 전략 선택 매트릭스

| 데이터 형태 | 탐지 신호 | 주 전략 | 보조 전략 | 대표 차트 |
|---|---|---|---|---|
| 지역/공간 | 주소, 행정구역, 위경도, 권역 코드 | spatial concentration | ranking, heatmap, gap analysis | bar, heatmap, scatter/map 대체 |
| 시계열 | 날짜, 월, 분기, 이벤트 시점 | temporal diagnostics | trend, seasonality, before-after | line, area, slope |
| 범주형 분포 | 범주 열이 많고 측정값이 제한적 | composition and concentration | ranking, long-tail, Pareto | bar, stacked_bar, histogram |
| 고객/거래 | 고객/계정/거래 ID, 금액, 빈도 | segment economics | cohort, contribution, retention proxy | scatter, bar, waterfall |
| 설문/응답 | 문항, 응답값, 리커트 척도, 응답자 속성 | response segmentation | distribution, cross-tab, disagreement | stacked_bar, heatmap, boxplot |
| 운영/재고 | 처리량, 리드타임, 재고, 상태, SLA | bottleneck diagnostics | anomaly, capacity, variance | line, bar, boxplot |
| 텍스트성 표 데이터 | 제목, 설명, 카테고리, 태그, 문장형 컬럼 | taxonomy and signal extraction | frequency, co-occurrence, quality | bar, heatmap, table |

## 전략별 요구사항

### 지역/공간 데이터

- 핵심 질문: 어디에 집중되어 있고, 어떤 범위나 세그먼트가 상대적으로 두드러지는가?
- KPI 패턴: 밀도, 점유/비중, 지역 내 점유율, 집중도, 보정 지수.
- 분해 축: 행정구역, 권역, 카테고리, 가격대, 외부 보정 지표.
- 차트 후보: 지역별 ranking bar, 지역 x 카테고리 heatmap, 좌표 scatter, 후보군 table.
- 주의: 면적·대상 규모·수요 분모가 없으면 단순 건수나 좌표 밀집을 좋은/나쁜 판단으로 바로 바꾸지 않는다.

#### 외부 보정 데이터 결합 전략

기본 지역/공간 데이터만으로 결론 강도가 부족할 때는
`docs/external-denominator-adapters.md`의 optional adapter 또는 domain pack을 사용한다.
adapter가 없으면 "확정 판단"이 아니라 "현재 데이터에서 보이는 구조"로 표현한다.

| layer | adapter category | 대표 KPI | 보강하는 질문 | 주의 |
|---|---|---|---|---|
| 기본 구조 | 입력 데이터 | 건수, 비율, 순위, 집중도 | 현재 데이터 안에서 무엇이 두드러지는가 | 원인·성과·추천으로 재명명 금지 |
| 규모 보정 | domain pack 정의 | 대상 1천 단위당 지표, 면적당 지표 | 모집단이나 면적 차이를 보정했는가 | 보정 기준과 coverage 명시 |
| 수요/사용 맥락 | domain pack 정의 | 수요 대비 지표, 사용량 대비 지표 | 관찰된 구조가 수요·사용량과도 일치하는가 | 구매·성과 전환으로 단정 금지 |
| 비용/제약 맥락 | domain pack 정의 | 비용 분위, 제약 점수 | 후보나 위험 신호를 비용·제약이 뒤집는가 | 낮은 비용만으로 좋은 판단 단정 금지 |
| 성과 맥락 | domain pack 정의 | 성과/대상, 성과/비용 | 관찰된 구조가 성과와 연결되는가 | 표본·추정·인과 한계 명시 |
| 안정성/리스크 맥락 | domain pack 정의 | 변동률, 이탈률, 실패율, 상태 변화 | 구조가 안정적인가, 변동성이 큰가 | 낮은 리스크만으로 추천 단정 금지 |

외부 context 결합 시 frame은 KPI 정의표에 `metric_layer`를 적고, analyze는 결합
점수를 만들더라도 원천 layer별 KPI와 반대 해석을 함께 남긴다.

### 시계열 데이터

- 핵심 질문: 변화가 지속 추세인지, 일시 변동인지, 구조적 전환인지?
- KPI 패턴: 성장률, 이동평균, 전년동기 대비, 변동성, 전후 차이, 최근 구간 기울기.
- 분해 축: 기간, 세그먼트, 이벤트 전후, 지역/상품/고객군.
- 차트 후보: line, area, slope, before-after bar.
- 주의: 기간이 짧으면 추세보다 현재 스냅샷 또는 변동성 진단으로 낮춘다.

### 범주형 분포 데이터

- 핵심 질문: 어느 범주가 전체를 설명하고, 롱테일은 얼마나 큰가?
- KPI 패턴: 점유율, 누적 점유율, concentration ratio, entropy proxy, 희소 범주 비율.
- 분해 축: 주요 범주, 상위/하위 그룹, 기타 그룹, 교차 범주.
- 차트 후보: horizontal bar, Pareto-style bar, stacked_bar, heatmap.
- 주의: 긴 라벨과 많은 범주는 축에 모두 얹지 말고 상위 N + 기타 + table로 나눈다.

### 고객/거래 데이터

- 핵심 질문: 매출/사용량/빈도는 어떤 세그먼트가 만들고, 위험 또는 기회는 어디인가?
- KPI 패턴: 객단가, 빈도, 총액, 재방문 proxy, 기여도, 고가치/저활성 세그먼트.
- 분해 축: 고객군, 상품군, 채널, 기간, 거래 상태.
- 차트 후보: scatter, bar, waterfall, cohort proxy heatmap.
- 주의: 고객 생애가 없으면 retention이나 LTV를 확정값처럼 쓰지 않는다.

### 설문/응답 데이터

- 핵심 질문: 평균보다 중요한 응답 분포, 양극화, 세그먼트 차이는 무엇인가?
- KPI 패턴: 긍정률, 부정률, 중립률, top-box, bottom-box, 문항별 격차.
- 분해 축: 문항, 응답자 속성, 세그먼트, 시간 또는 캠페인.
- 차트 후보: stacked_bar, heatmap, boxplot, diverging bar 대체.
- 주의: 표본 수가 작은 세그먼트는 결론이 아니라 후보 신호로 표시한다.

### 운영/재고 데이터

- 핵심 질문: 병목, 지연, 과잉/부족, 변동성은 어디에서 발생하는가?
- KPI 패턴: 처리량, 리드타임, SLA 초과율, 재고 회전 proxy, 결품/과잉률, 변동계수.
- 분해 축: 단계, 상태, 담당/센터, 품목군, 시간대.
- 차트 후보: line, boxplot, bar, heatmap.
- 주의: 상태 전이 로그가 없으면 원인-결과 흐름을 단정하지 않는다.

### 텍스트성 표 데이터

- 핵심 질문: 어떤 주제·태그·문구가 반복되고, 분류 품질은 충분한가?
- KPI 패턴: 키워드 빈도, 카테고리 점유, 중복률, 누락률, 텍스트 길이 분포.
- 분해 축: 카테고리, 출처, 기간, 작성자/채널, 품질 플래그.
- 차트 후보: bar, heatmap, histogram, evidence table.
- 주의: 의미 분석 모델이 없으면 감성·의도 추론을 확정하지 않는다.

## 심층 분석 체크리스트

`report.depth=deep` 또는 의사결정형 분석에서는 다음을 최소 기준으로 한다.

- 주 전략과 보조 전략을 명시한다.
- KPI마다 계산식, 단위, 분모, 비교 기준을 쓴다.
- 전체 현황과 최소 1개 이상의 세그먼트 비교를 연결한다.
- 분포, 관계, 추세, 구성 중 데이터가 허용하는 2개 이상의 관점을 검토한다.
- 가장 강한 발견마다 반대 해석 또는 대체 설명을 붙인다.
- 액션 기준은 "무엇을 보면 실행/보류/추적할지"의 임계값 또는 조건으로 쓴다.
- 불가능한 분석은 생략하지 말고 필요한 추가 컬럼이나 외부 기준을 적는다.
