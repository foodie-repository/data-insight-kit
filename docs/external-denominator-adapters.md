# External Context Adapters

이 문서는 `data-insight-kit`이 선택적으로 결합할 수 있는 외부 context adapter 계약이다.
외부 context는 원본 데이터만으로는 부족한 규모, 사용 맥락, 비용, 성과, 안정성,
공간 보정 정보를 별도 layer로 붙이는 방식이다. category별 의미와 허용/금지
해석은 `docs/external-adapter-registry.md`를 따른다.

역사적 파일명은 `external-denominator-adapters.md`로 유지하지만, core 의미는
"분모 데이터"에 한정하지 않는다.

## 핵심 원칙

- 외부 context adapter는 선택 입력이다. 없어도 기본 데이터 분석은 가능하지만,
  데이터가 직접 지원하지 않는 수요, 성과, 비용, 원인, 추천 결론을 단정하지 않는다.
- 원본 데이터에서 계산한 count, ratio, rank, concentration, share는 관측 구조다.
  외부 context가 붙어도 해당 지표의 의미를 임의로 바꾸지 않는다.
- 외부 데이터는 반드시 `source_ref`, 기준일 또는 기간, 분석 grain, join key,
  coverage, 결측률, 허용 해석과 금지 해석을 남긴다.
- 외부 context가 여러 개이면 하나의 점수로 바로 합치지 말고 `demand`, `cost`,
  `performance`, `spatial`, `competition`, `context` layer를 분리한다.
- 결합 점수는 ranking 보조 신호이며 원천 KPI를 대체하지 않는다.
- 수집·조인·합산 품질은 분석 품질의 일부다. 페이지네이션 누락, grain 혼재,
  중복 분모, 낮은 join coverage는 결론 강도를 낮추거나 QA에서 막아야 한다.
- 반복 adapter 구현은 `scripts/external_adapter_utils.py`의 작은 helper를 우선
  사용한다. run-local script는 원천 해석과 feature 계산에 집중하고, coverage
  계산·manifest 작성·paged API 수집·signed rank shift 같은 공통 안정장치는
  core helper로 처리한다.

## Adapter 후보

| category | 예시 데이터 | 보강하는 판단 | 금지 해석 |
|---|---|---|---|
| `population` | 인구, 계정 수, 사용자 수, 조직 수 | 규모 대비 비교, 배후 규모 | 규모가 크다는 이유만으로 실제 수요·성과 확정 |
| `foot_traffic` | 방문량, 접속량, 사용량, 체류량 | 활동/접점 context, 시간대 비교 | 활동량을 구매·성과 전환으로 단정 |
| `rent` | 비용, 가격, 수수료, 임대료, 공실률 | 비용 압력, 진입장벽 | 비용이 낮다는 이유만으로 좋은 후보·수익성 단정 |
| `sales` | 매출, 소비, 거래액, 전환, outcome | 성과/소비/결과 proxy | 순이익·성공 가능성·원인 확정 |
| `business_dynamics` | 개시·종료, churn, 생존, 상태 변화 | 안정성, 이탈 리스크, 회전율 context | 낮은 이탈률을 추천·성공 가능성으로 단정 |
| `area` | 면적, 반경, 격자, 공간 범위 | 밀도 보정, 공간 규모 | 행정·임의 범위를 실제 활동 반경으로 단정 |
| `competition` | 동일/유사 대상 수, 공급자 수 | 경쟁 강도, 공급 구조 | 경쟁이 많다는 이유만으로 실패 단정 |
| `mobility` | 접근성, 거리, 이동시간, 네트워크 | 접근성, 이동 제약 | 접근성이 곧 성과라는 인과 단정 |
| `custom` | 도메인별 보조 데이터 | manifest에 선언한 범위 | 선언하지 않은 category 의미로 우회 |

## Manifest 파일

외부 context를 사용하는 run은 가능하면 다음 파일을 남긴다.

```text
runs/<run-id>/external_denominators.json
```

스키마는 `schemas/external_denominator_manifest.schema.json`이다. 최소 단위는
adapter 1개이며, 각 adapter는 다음 정보를 갖는다.

```json
{
  "schema_version": "data-insight-kit.external_denominator_manifest.v1",
  "run_id": "example-run",
  "status": "available",
  "adapters": [
    {
      "id": "account_count_segment",
      "category": "population",
      "source_ref": "accounts_2026_segment",
      "source_type": "local_file",
      "snapshot_at": "2026-03-31",
      "spatial_grain": "custom",
      "join_keys": [
        {"left": "segment_id", "right": "segment_id", "quality": "exact"}
      ],
      "coverage": {
        "grain_count": 120,
        "matched_count": 118,
        "match_rate": 0.983333,
        "null_rate": 0.016667
      },
      "acquisition": {
        "method": "file_snapshot",
        "pagination_checked": null,
        "page_count": null,
        "collected_row_count": 120,
        "expected_grain_source": "analysis segment_id distinct count"
      },
      "grain_quality": {
        "canonical_grain": "custom",
        "raw_grain_levels": ["segment"],
        "has_upper_lower_mix": false,
        "matched_grain_only": true,
        "denominator_aggregation_basis": "matched_grain",
        "duplicate_grain_policy": "segment_id 단위 중복 제거 후 exact match"
      },
      "fields": [
        {
          "name": "account_count",
          "meaning": "segment별 계정 수",
          "unit": "count",
          "denominator": "segment",
          "metric_layer": "demand",
          "allowed_uses": ["segment-normalized rate comparison"],
          "prohibited_interpretations": ["confirmed demand or revenue"]
        }
      ],
      "limitations": ["segment 정의가 원본 분석 grain과 완전히 같지 않을 수 있음"]
    }
  ]
}
```

`acquisition`과 `grain_quality`는 기존 manifest 호환을 위해 선택 필드지만, 새
adapter는 가능한 한 채운다. 특히 원천이 API·공개 조회 화면·페이지 단위
다운로드이면 `pagination_checked`, `page_count`, `collected_row_count`를 남긴다.
`spatial_grain=custom`이거나 수동·정규화 조인으로 더 거친 분석 grain에 붙인
경우에는 `grain_quality.coarse_aggregation=true`와 `aggregation_grain`을 남기고,
보고서와 대시보드에 "정밀 join이 아니라 coarse/context layer"임을 명시한다.

## Core Helper 사용 기준

`scripts/external_adapter_utils.py`는 외부 adapter smoke test에서 반복된 공통
패턴만 제공한다. 특정 API나 도메인 규칙을 core로 끌어올리지 않는다.

| helper | 쓰는 단계 | 목적 |
|---|---|---|
| `fetch_paged_json` | connect | start/end index 방식 JSON API를 수집하고 `page_count`, `collected_row_count`, `pagination_checked` 메타를 만든다. |
| `coverage_audit` | connect | `grain_count`, `matched_count`, `match_rate`, `null_rate`를 일관되게 계산한다. |
| `make_manifest`, `write_external_manifest` | connect | `input/external_denominator_manifest.json`과 `external_denominators.json`을 같은 내용으로 쓴다. |
| `ADAPTER_REGISTRY`, `CATEGORY_ALLOWED_METRIC_LAYERS` | frame/analyze/qa | category와 metric layer 혼동을 막는다. |
| `signed_rank_shift`, `signed_rank_shift_expr`, `add_signed_rank_shift` | analyze | rank_delta/rank_shift를 signed integer 기준으로 계산해 unsigned overflow를 방지한다. |

helper는 품질 guard일 뿐 분석 방법론을 대신하지 않는다. adapter script는 여전히
원천 기준일, grain, join key, coverage 한계, 금지 해석을 분석 산출물에 설명해야 한다.

## 수집·조인 QA 기준

외부 context는 다음 순서로 검증한다.

1. **전체 수집 확인**: API·공개 조회 화면·원격 스냅샷은 첫 페이지만 수집하지
   않았는지 확인한다. 페이지·커서·segment 반복 조회가 필요하면 `acquisition`에
   page count와 수집 행 수를 남긴다.
2. **canonical grain 고정**: 분석 기준 grain을 먼저 고정한다. 원천에 상위·하위
   grain이 함께 있으면 단순 합산하지 않는다.
3. **중복 grain 점검**: 같은 join key가 중복되거나 grain이 섞이면 제거·집계·가중
   처리 기준을 `grain_quality.duplicate_grain_policy`에 남긴다.
4. **coarse aggregation 표시**: source grain과 analysis grain이 다르면
   `grain_quality.coarse_aggregation`과 `aggregation_grain`을 남긴다.
5. **coverage 임계값**: `coverage.match_rate < 0.80` 또는
   `coverage.null_rate > 0.20`이면 분석적 BLOCK 대상이다. `match_rate < 0.95`
   또는 `null_rate > 0.05`이면 WARN으로 보고하고 결론은 "부분 coverage"로 낮춘다.
6. **분모·집계 기준**: 합계·평균·비율·index 계산은 raw source total이 아니라
   `denominator_aggregation_basis=matched_grain` 또는 명시된 가중 기준을 사용한다.
   이 기준이 없으면 결론에 "집계 기준 미확정" 한계를 붙인다.
7. **순위 차이 계산**: `rank_delta`, `rank_shift`처럼 순위 차이를 계산할 때는
   unsigned integer를 빼지 않는다. rank 컬럼은 signed integer로 캐스팅한 뒤
   차이를 계산하고, 비정상적으로 큰 양수 값이 나오면 overflow 의심으로 본다.
8. **layer 일관성**: adapter category와 field metric_layer가 충돌하면 core QA가
   BLOCK한다.

## 분석 적용 규칙

1. `frame`은 외부 context가 있는지 먼저 판정하고, 없는 경우 필요한 보조 데이터와
   한계를 KPI 정의표에 남긴다.
2. `analyze`는 원본 데이터의 직접 지표와 외부 context layer를 따로 계산한다.
   예: `rate_per_1k_accounts`, `performance_per_unit`, `cost_pressure_index`.
3. `visualize`는 결합 점수를 만들더라도 원천 layer별 KPI를 함께 보여준다.
4. `communicate`는 외부 context가 없으면 데이터가 직접 지원하지 않는 수요, 성과,
   비용, 원인, 추천 표현을 피한다.
5. `qa`는 외부 context를 사용했다는 표현이 있는 보고서에서 source_ref, 기준일,
   grain, join key, coverage 또는 결측률 설명이 빠졌는지 확인한다.
6. 외부 context가 하나뿐이면 해당 layer가 보강하는 범위까지만 말한다. 예를 들어
   규모 보정만 있으면 규모 대비 신호이고, performance layer만 있으면 성과 proxy다.
   종합 추천이나 원인 확정은 별도 근거와 반대 해석이 있을 때만 허용한다.
