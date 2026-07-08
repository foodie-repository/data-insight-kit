# 소스 어댑터 계약

`data-insight-kit`의 입력 계약은 사용자가 가진 원천과 파이프라인이 반복해서 읽는 표준 입력을 분리한다.
사용자는 DuckDB를 반드시 준비할 필요가 없다. DuckDB는 선택 입력이자 내부 SQL 실행 엔진이다.

## 기본 흐름

```text
사용자 원천
  -> source adapter
  -> runs/<run-id>/input/ 또는 connectors/.env
  -> connect
  -> intermediate/*.parquet
  -> analyze/visualize/communicate
```

반복 실행과 QA는 로컬에 고정된 입력을 기준으로 한다. 원격·대용량 데이터는 필요한 컬럼과 행만 축약해 `input/*.parquet`로 저장한 뒤 분석한다. 지역·세그먼트 커버리지가 중요한 경우에는 층화 샘플링으로 단순 앞부분 제한 편향을 줄인다.

`runs/*`는 사용자별 로컬 산출물이다. 입력 스냅샷과 중간 Parquet는 재현을 위해
run 안에 남기지만, 배포용 core에는 포함하지 않는다. 예제나 테스트 fixture가
필요하면 `runs/`가 아니라 별도 위치를 설계한다.

## 지원 어댑터

| adapter | 사용자 원천 | 표준 입력 | 사용 상황 |
|---|---|---|---|
| `local_file` | CSV, Parquet, Excel, JSON | `runs/<run-id>/input/` | 기본 경로. 가장 이식성이 좋다. |
| `primary_api` | 공공데이터·OpenAPI URL 또는 API 문서 페이지 | `runs/<run-id>/input/source_api_manifest.json` → `input/*.parquet|csv|jsonl` 스냅샷 | 사용자가 API URL만 준 경우의 주 입력. endpoint/auth/pagination을 확인한 뒤 로컬 스냅샷으로 고정한다. |
| `remote_parquet` | `hf://`, `https://`, `s3://` 등 | `runs/<run-id>/input/*.parquet` 스냅샷 | Hugging Face·공개 Parquet·클라우드 파일. 전체 다운로드 금지. |
| `duckdb` | 기존 DuckDB 파일 | `connectors/.env`의 `DIK_DUCKDB_PATH` | 이미 분석 DB가 있거나 SQL 중심으로 조인·집계해야 하는 경우. |

## Domain Pack Context

domain pack은 데이터 소스가 아니다. 회사·업무 도메인의 용어, KPI 후보, 금지
표현, 차트/보고서 패턴을 stage agent에 전달하는 보조 계약이다.

선택 경로:

- `DIK_DOMAIN_PACK=domains/<domain>/domain.yaml`
- `runs/<run-id>/input/domain_pack_ref.txt`
- intake 또는 external adapter 선택 결과의 `registry_ref`

wrapper는 선택된 pack을 읽어 다음 파일을 만든다.

```text
runs/<run-id>/input/domain_pack_context.md
runs/<run-id>/domain_pack_context.md
```

이 context는 intake를 포함한 이후 stage prompt에 전달된다. 단, domain pack은
`docs/pipeline-contract.md`, 스키마, QA를 대체하지 않는다. domain pack 기준이
결론을 바꾸거나 추가 도메인 판단을 요구하면, 해당 내용은 사용자 checkpoint에서
확인받아야 한다.

## 로컬 파일

```bash
mkdir -p runs/my-run/input
cp /path/to/source.csv runs/my-run/input/
bash scripts/run_codex_pipeline.sh my-run
```

파일 입력은 `connect` 단계에서 스키마, 행 수, 결측, 기본 의미층을 프로파일링하고 `intermediate/*.parquet`로 정리한다.

## Primary API

사용자가 공공데이터/OpenAPI URL만 주면 wrapper는 `source_api_manifest.json`을 먼저 만든다.
이 파일은 수집 완료 데이터가 아니라 connect 단계가 검증해야 할 수집 계획이다.

```bash
DIK_USER_REQUEST="공개 API에서 데이터를 수집하고 분석 보고서와 대시보드를 만들어줘. API URL: https://example.com/openapi" \
  bash scripts/run_codex_pipeline.sh my-run --guided-intake
```

생성되는 파일:

```text
runs/my-run/input/source_api_manifest.json
runs/my-run/source_api_manifest.json
```

connect 단계는 이 manifest를 기준으로 다음을 수행한다.

- 공식 API 문서 또는 endpoint 확인
- 인증 필요 여부와 serviceKey/env 이름 확인. 키 값은 출력·저장 금지
- 1페이지 smoke test
- pagination, 총 수집 범위, row count 확인
- `runs/<run-id>/input/*.parquet` 우선, 불가 시 CSV/JSONL 스냅샷 생성
- `snapshot.path`, `row_count`, `columns`, `fetched_at`, `pagination_checked`, `page_count`, `collected_row_count` 업데이트
- endpoint/auth/quota/network/pagination이 막히면 `status=blocked`와 `blocker`를 남기고 중단

`connectors/.env`가 있더라도 `source_api_manifest.json`이 있으면 API가 주 입력이다.
사용자가 명시하지 않은 DuckDB로 조용히 대체하지 않는다.

## 원격 Parquet

원격 Parquet는 직접 전체 다운로드하지 않는다. 먼저 필요한 컬럼과 행을 줄인 snapshot을 만든다. 표본의 지역·세그먼트 정합성이 중요하면 `--stratify-by`를 함께 쓴다.

```bash
python3 scripts/snapshot_remote_parquet.py my-run \
  "hf://datasets/nvidia/Nemotron-Personas-Korea@~parquet/default/train/*.parquet" \
  --columns uuid,age,sex,province,district,occupation,housing_type,education_level \
  --stratify-by province \
  --limit 50000 \
  --seed 42 \
  --output nemotron_personas_sample.parquet
```

원격 서버가 rate limit에 민감한 경우 전수 층화 count가 여러 파티션을 읽으면서 막힐 수 있다. 이때는 먼저 `--candidate-limit`으로 제한된 후보군을 만들고 그 안에서 층화해 검증용 스냅샷을 만든다. 이 방식은 full-source 대표성이 아니라 candidate-prefix 대표성이므로 `source_snapshot.json`의 `sampling_frame`을 보고서 한계에 반영한다.

```bash
python3 scripts/snapshot_remote_parquet.py my-run \
  "hf://datasets/nvidia/Nemotron-Personas-Korea@~parquet/default/train/*.parquet" \
  --columns uuid,age,sex,province,district,occupation,housing_type,education_level \
  --stratify-by province,sex \
  --candidate-limit 10000 \
  --limit 1000 \
  --seed 42 \
  --output nemotron_personas_probe.parquet
```

이 명령은 다음을 만든다.

```text
runs/my-run/input/nemotron_personas_sample.parquet
runs/my-run/source_snapshot.json
```

`source_snapshot.json`에는 원격 URI, 조회 시점, 컬럼, 행 수, schema, 샘플링 방식, candidate 사용 여부가 들어간다. 보고서에 표본 한계가 필요하면 이 정보를 근거로 쓴다.

## DuckDB

DuckDB는 선택 입력이다. 기존 분석 DB를 쓰는 경우에만 `connectors/.env`를 둔다.

```bash
cp connectors/.env.example connectors/.env
```

```text
DIK_DUCKDB_PATH=/path/to/your.duckdb
```

DB 접근은 `connectors/source.py` 경유만 허용한다. read-only 연결과 SELECT/WITH 전용 가드가 LLM 판단보다 우선한다.

## Lineage 규칙

모든 소스는 `manifest.sources[]` 또는 `source_snapshot.json`에 다음 정보를 남긴다.

- `adapter`: `local_file`, `primary_api`, `remote_parquet`, `duckdb`
- `ref`: 파일명, 원격 URI, 또는 DB 참조
- `snapshot_at`: 조회 또는 스냅샷 생성 시각
- `n`: 사용한 행 수
- `columns`: 사용한 컬럼
- `schema`: 컬럼 타입 요약
- `sampling`: 층화 기준, seed, candidate 사용 여부, sampling frame

원격 데이터의 원천 URI는 남기되, 토큰·자격증명·민감 경로는 산출물에 남기지 않는다.
