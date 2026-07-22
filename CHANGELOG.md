# Changelog — data-insight-kit

기록 원칙: expert-guided analysis routing v1부터 단계별 커밋 요약과 검증 결과를 남긴다.
구현 중단·재개 시 이 파일의 "진행 상태"가 재개 지점이다.

## [0.2.2] — 2026-07-19 — 모델 지정 정책 정비

모델 세대가 바뀌어도 지정값이 조용히 낡지 않도록 양 런타임의 모델 지정 방식을 정비했다.
기능 변경은 없고, 어떤 모델로 각 단계가 도는지가 바뀐다.

- **Claude — 버전 고정 → 티어 별칭**: `agents/*.md`의 `model:`을 `claude-sonnet-4-6`·
  `claude-opus-4-8` 같은 고정값에서 `sonnet`/`opus` 별칭으로 바꿨다. sonnet 4.6→5처럼
  세대가 올라가도 파일 수정 없이 최신이 적용된다. 경량 단계(intake·qa)는 haiku에서
  **sonnet으로 승격** — 파이프라인 입구(의도 파악)와 출구(BLOCK/PASS 판정)의 품질이
  전체에 파급되므로 최하위 티어를 쓰지 않는다.
- **Codex — 현행값 갱신**: 기본 모델 `gpt-5.5` → **`gpt-5.6-sol`**. `codex debug models`
  실측 결과 gpt-5.5는 priority 7로 밀렸고 sol/terra/luna가 현행(1·2·3)이었다. budget
  값이던 `gpt-5.4-mini`는 이미 `visibility=hide` 상태여서 "fast and affordable"인
  **`gpt-5.6-luna`**로 교체했다.
- **Codex — 지정처 단일화**: Codex에는 Claude의 티어 별칭 같은 버전 없는 식별자가 없어
  고정이 불가피하다. 대신 모델명 지정처를 `docs/model-tier-map.md`와 wrapper 기본값
  **두 곳으로 축소**했다. 기존에는 AGENTS.md·agent-guide tutorial·slides까지 5개 파일
  ~15곳에 복붙돼 있어 세대 교체 때마다 조용히 낡았다. 이제 다른 문서는 effort 배분만
  적고 모델명은 단일 원천을 참조한다.
- 검증: wrapper dry-run 실측 `-m gpt-5.6-sol`, `DIK_MODEL` override `-m gpt-5.6-luna`.
  전체 `369 passed, 30 skipped, 128 subtests passed`, `ruff check .` All checks passed.

### 배포 증거 (2026-07-19)

배포 증거는 **소스 CHANGELOG에만** 기록하고 공개 배포 저장소에 직접 커밋하지 않는다.
v0.2.0 때는 `vk-dist`에 증거 commit을 직접 올려 source subtree와 distribution tree가
갈라졌고(그 divergence를 v0.2.1 배포 때 확인·해소했다), 같은 문제를 반복하지 않기 위해
증거는 source에 남기고 다음 release 미러링으로 전파한다.

- source release commit `f3c1b12`의 추적 subtree와 distribution tree가 Git tree hash
  `121cf31`로 일치함을 확인했다. 배포 tree에 `runs/*`·`.env`·`.venv`는 0건이다.
- 최신 `vk-dist/main`(v0.2.1 `7191a56`)을 부모로 distribution commit `6bfda3d`를 만들고
  일반 fast-forward push했다(`7191a56..6bfda3d`, force push 없음).
- 배포 tree에서 전체 테스트 `369 passed, 30 skipped, 128 subtests passed`, 입력 없는
  core `--dry-run` 통과. dry-run 출력의 실제 모델 옵션이 `-m gpt-5.6-sol`로 이번 release의
  기본 모델 변경이 배포본까지 도달했음을 확인했다.
- 원격 GitHub 저장소만 사용한 격리 설치 smoke: codex-cli `0.144.6`과 Claude Code
  `2.1.214`가 모두 `0.2.2`를 installed·enabled로 발견했다. Codex 설치본에서 skill 1개,
  hook 1개, agent 8개를 확인했고 agent frontmatter 모델이 별칭(`opus` 3, `sonnet` 5)으로
  적용된 것까지 확인했다. Claude 설치는 임시 `CLAUDE_CONFIG_DIR`로 격리했고 실제
  `~/.claude` 설정 오염은 0건이다.
- 원격 설치 smoke가 green인 distribution commit `6bfda3d`에 annotated tag `v0.2.2`
  (`8dd1973`)를 만들어 push했고, README가 안내하는 `--ref v0.2.2` 태그 고정 설치가
  `0.2.2`로 동작함을 확인했다. tag는 이후 문서 마감 commit으로 이동하지 않는다.
- 알려진 오기: `v0.2.2` tag 주석의 codex 버전이 `0.144.1`로 적혀 있으나 실제 smoke는
  `0.144.6`에서 수행했다(v0.2.1 값을 재확인 없이 옮겨 적은 실수). 공개된 tag는 옮기지
  않으므로 정확한 값은 이 기록을 기준으로 한다.
- 다음은 실제 사용자가 수행하는 블라인드 UAT다. domain/statistical end-to-end smoke도
  실제 사용자 답변이 필요하며 이번 release에서 대리 승인하지 않는다.

## [0.2.1] — 2026-07-18 — checkpoint gate 무결성 + domain-pack 저작 문서

Codex 교차검증에서 발견해 재현으로 확인한 체크포인트 게이트 우회 2건(High)을
차단하고 관련 정비를 묶었다. 두 우회 모두 hook docstring이 명시한 위협모델
(모델이 파이프라인을 직접 오케스트레이션할 때 승인을 우회)에 정확히 해당했다.
자기 오케스트레이션 에이전트가 checkpoint 강제를 우회할 수 있었으므로 업그레이드를
권장한다(원격 공격이 아니라 무결성 게이트 문제).

- **H1 — manifest 자기서명 정책 우회 제거**: `runs/<id>/manifest.json`에
  `checkpoint_policy`만 넣으면 stage_guard·hook·qa 3계층이 동시에 skip되던 폴백을
  제거했다. 정책 정본은 wrapper가 쓰는 `input/checkpoint_policy.json` 하나뿐이다.
  정책 술어를 `stage_guard.policy_allows_skip` 단일 함수로 통합해 qa/validate가
  재사용하고(계층 간 `no_checkpoints` 관용 불일치도 해소), 3계층 판정이 어긋나지
  않게 했다.
- **H2 — checkpoint 상태 파일 직접 위조 차단**: `dik_checkpoint_hook`가
  `checkpoint_answers.json`·`checkpoint_policy.json`에 대한 직접 Write/Edit/
  apply_patch와 shell 리다이렉트를 deny한다. 정상 생산자
  (`apply_checkpoint_answer.py`, `run_codex_pipeline.sh`)는 in-process write라
  통과한다.
- **회귀 테스트**: `tests/test_gate_bypass_regression.py`(9건) — 정상 경로 테스트가
  못 잡던 비정상 경로(우회 시도)가 실제로 BLOCK/deny되는지 검증.
- **정비**: `pyproject.toml`에 dev 의존성 그룹(pytest·ruff) 선언(새 환경
  `uv sync` 후 테스트 재현 가능), qa/validate.py 등 E402 noqa 정리(ruff clean),
  AGENTS.md·`.claude/settings.json` hook matcher를 `hooks.json`과 동기화.
- **domain-pack 저작 문서 보강** (da-viz 강점 선별 이식): `terminology.md`에
  "일반적 의미와 다른 점" 안티할루시네이션 열 추가, `CUSTOMIZATION.md`에 "흩어진
  회사 문서에서 팩 만들기" 섹션(3층 구조 + 스캔→초안→인터뷰→반영 저작 계약 +
  markitdown·polars+fastexcel·duckdb 의존성 계약 + 보안 주의), `domains/README.md`
  폴더 구조에 선택적 `references/`·`data/` 안내. 기존 7파일 구조·파이프라인 통합은
  그대로 유지.
- 검증: `ruff check .` All checks passed / 전체 `369 passed, 30 skipped, 128 subtests`.

## [0.2.0] — 2026-07-18 — distribution

### 진행 상태

- dashboard freeform v5.1을 로컬 `master`에 merge commit `5362043`으로 병합했고,
  병합 결과 전체 테스트는 `354 passed, 30 skipped, 128 subtests passed`다.
- v0.2.0 release spec/checklist를 추가하고 `pyproject.toml`, `uv.lock`, Claude Code,
  Codex manifest 버전을 0.2.0으로 맞췄다. marketplace에는 version을 중복하지 않는다.
- 최신 Codex plugin validator가 거부하는 manifest `hooks` 필드를 제거했다. hook은
  기본 발견 위치 `.codex/hooks.json`에 유지했고, 격리된 Codex 0.144.1에서
  marketplace 추가·v0.2.0 설치·hook/skill 발견·core dry-run까지 확인했다.
- Claude Code 2.1.212 strict validation을 통과했고, README/GUIDE에 GitHub 원격
  marketplace 설치 명령을 추가했다.
- release/adapter 집중 테스트는 25 passed, 전체 테스트는
  `360 passed, 30 skipped, 128 subtests passed`다.
- standalone 배포본이 상위 저장소 ignore에 의존하지 않도록 `.venv`, pytest/ruff,
  Playwright cache와 `.DS_Store` 제외 규칙을 제품 `.gitignore`에 추가했다.
- fresh distribution 검증에서 입력 없는 README 설치 확인 `--dry-run`이 source gate에
  막히는 결함을 발견했다. dry-run은 명령 계획을 출력하되 실제 실행은 기존처럼
  source가 없으면 차단하도록 wrapper와 clean-copy 회귀 테스트를 보강했다.
- source commit `0a2833c`의 추적 subtree와 distribution staging tree가 Git tree
  hash `8cc6cd5...`로 일치함을 확인했다. 배포본 전체 테스트는
  `360 passed, 30 skipped, 128 subtests passed`이며 Claude strict validation과
  Codex/Claude 로컬 격리 설치·hook/skill/core dry-run이 모두 green이다.
- 최신 `vk-dist/main`을 부모로 distribution commit `106f219`를 만들고 일반
  fast-forward push했다. GitHub 원격만 사용한 새 격리 환경에서 Codex 0.144.1과
  Claude Code 2.1.212가 모두 v0.2.0, skill 1개, agent 8개, hook 1개를 발견했고
  입력 없는 core dry-run을 통과했다.
- 원격 설치 smoke를 통과한 distribution commit `106f219`에 annotated tag
  `v0.2.0`을 생성해 push했다. tag는 이후 문서 마감 commit으로 이동하지 않는다.
- 다음은 실제 사용자가 수행하는 블라인드 UAT다. domain/statistical end-to-end
  smoke도 실제 사용자 답변이 필요하며 이번 release에서 대리 승인하지 않는다.

## [Unreleased] — dashboard freeform v5 (branch: codex/dashboard-freeform-v5)

### 진행 상태

- **설계 승인 완료**: 자유 레이아웃을 임의 HTML이 아니라 승인된
  `dashboard_layout.json` 계약으로 구현하는 spec/checklist를 확정했다
  (`3205610`).
- **구현 커밋 2~8 완료**: layout schema·renderer routing(`430bb93`), storyboard
  hash/revision 잠금(`f1e372a`), 로컬 ECharts 6.1.0 안전 mapper(`d4d0296`),
  결정적 compiler(`1f8c6ea`), 반응형·접근성 component(`0905025`), browser QA와
  screenshot 게이트(`46dca81`), guided pipeline 연결(`2df64da`).
- 보안 회귀에서 상태형 chart의 visible control/reset 누락과 vendored ECharts
  checksum 변조를 BLOCK하도록 보강했다. legacy/v4 경로는 별도 routing으로
  유지하며 v5 실패를 하위 렌더러로 강등하지 않는다.
- **snapshot smoke 완주**: `sbiz-gangnam-v5-freeform-smoke-20260714`에서
  상가 64,239개 fresh 분석, 실제 사용자 checkpoint 4종, v5 렌더, 보고서,
  qa-post까지 완료했다. 최종 browser QA는 BLOCK 0건, WARN 3건이며
  desktop/mobile screenshot에서 component·범례·축·라벨·plot 겹침과 잘림이
  없음을 직접 확인했다. `runs/*`는 커밋하지 않았다.
- snapshot smoke 피드백으로 16:9 폭, 의미 기반 단일 강조색, 고대비 heatmap,
  독자용 문구·단위·출처 표현을 보정했고, 단일 계열 legend 제거와 보이는
  legend-plot/canvas 겹침 BLOCK을 추가했다.
- **time-series smoke 완주**: `apt-sale-v5-freeform-smoke-20260714`에서
  실제 사용자 checkpoint 답변으로 fresh 시계열 분석, layout revision 2
  재승인, `report_outline`의 `보고서 구성 승인`, `communicate`, `qa-post`까지
  완료했다. 최종 보고서는 `standard`·`mixed`·`data_only` 계약으로 생성했으며,
  dashboard/chart 수치를 재계산하지 않고 인용했다. 시작 과정에서 "이전 run을
  참조하지 않고"라는 부정문을 wrapper가 과거 참조 요청으로 잘못 분류하는
  문제도 발견해 spec·통합 회귀 테스트와 함께 수정했다.
- time-series 화면 점검에서 발견한 KPI 단위·기간 변화율 혼용, 값축 라벨 밀도,
  모바일 범례 잘림을 회귀 테스트와 함께 보정했다. KPI 단위와 변화율을 분리하고,
  값축 눈금을 제한·정렬했으며, 다중 계열 범례는 작은 화면에서 plot 아래의
  scroll 범례로 전환했다. browser QA도 실제 범례 viewport를 기준으로 잘림을
  판정하도록 고쳤다.
- time-series revision 2에서는 독자 화면에 `시작월`·`끝월`·`기간 가격`·
  `가격 단위 미확인` 같은 상대적·내부 표현을 금지하고 실제 연월과 `만원` 단위를
  사용하도록 spec·validator를 보강했다. 변동폭 차이가 4배 이상인 다중 선은 같은
  월축의 위아래 패널로 분리하며, 산점도·slope는 데이터의 의미 role 색을 보존한다.
  browser QA는 여러 plot의 상호 겹침과 canvas 잘림까지 검사한다. revision 2는
  desktop/mobile 모두 browser QA `BLOCK 0`이며 직접 눈검토에서도 component·축·
  라벨·범례·plot의 겹침과 잘림이 없었다.
- 최종 browser QA는 `BLOCK 0`, `WARN 3`이며, qa-post는 `BLOCK 0`, `WARN 2`다.
  재생성된 desktop/mobile screenshot을 직접 열어 카드·차트·축·라벨·범례·plot의
  겹침과 잘림이 없고 heatmap 축·월 레이블·색 범례가 보이는 것을 확인했다.
  모바일의 25개 구 변화 비교 범례는 작고 페이지형이라 v5.1 시각 품질 수렴의
  개선 후보로 남긴다.
- **dashboard freeform v5 마감**: snapshot/time-series 두 smoke, 실제 사용자
  checkpoint provenance, browser QA, 눈검토, 보고서, qa-post를 모두 완료했다.
  최종 전체 테스트는 `270 passed, 23 skipped, 128 subtests passed`다.
- **v5.1 설계 승인**: 새 kit/독립 PoC 없이 제품 본체를 확장하고, Data
  Analytics의 계획 품질과 Visualize의 표현·QA 원칙을 clean-room 방식으로
  독립 구현하는 opt-in spec/checklist를 사용자 원문 `설계 승인`으로 확정했다
  (`f98dfe8`).
- **v5.1 구현 Task 2~6 완료**: additive schema(`9297d18`), 계획 품질
  gate(`94f34a3`), 실행 품질 gate(`219012e`), renderer 표현 정책(`d431a23`),
  4-viewport browser/눈검토 gate(`b511b4f`)를 순서대로 구현했다. v5.1은 v5
  renderer를 유지하면서 decision brief, metric role/lineage, data sufficiency,
  visual contract를 강제한다.
- browser QA는 1440/736/390/320px 네 화면, label·legend·plot·canvas 충돌,
  11px 미만 필수 문구, tooltip 이탈, 색만 쓰는 계열을 검사한다. 오케스트레이터
  눈검토는 네 screenshot hash와 `visual_review.json`에 묶이며 `status=pass`가
  아니면 fail-closed한다. 최초 직접 검토에서 단위 중복과 desktop support 공백을
  `revise`로 판정해 수정했고, 최종 네 화면에서 겹침·잘림·단위 중복 없음과
  narrow 표 fallback을 확인했다.
- **Claude Code thin adapter 패키징 완료**: manifest를 v0.2.0으로 올리고,
  marketplace root source·strict mode·단일 version 권한을 확정했다. Claude Code
  2.1.212 strict validator와 격리된 `/tmp` 설정에서 marketplace 추가·설치,
  `run-pipeline` skill·8개 stage agent·checkpoint hook 발견, core dry-run을
  확인했다. 외부 plugin cache·widget runtime 의존은 없다.
- **Codex thin adapter 패키징 완료**: `.codex-plugin/plugin.json` v0.2.0과
  marketplace interface metadata를 추가하고 공유 skill·`.codex/hooks.json`을
  연결했다. Codex CLI 0.144.1의 격리된 `CODEX_HOME`에서 marketplace 발견,
  설치·enable, cache의 manifest/hook/skill/wrapper/template, 설치 root core
  dry-run을 확인했다. 공유 skill은 설치 위치에서 `KIT_ROOT`를 찾도록 Claude
  Code/Codex 런타임 중립으로 정리했다.
- **v5.1 snapshot smoke 진행 중**:
  `sbiz-gangnam-v51-visual-quality-smoke-20260717`을 새 run으로 만들고 v5
  baseline은 읽기 전용으로 유지했다. 원천 SHA-256 일치와 과거 승인 미복사를
  확인했고, `data_profile` 근거 원문 전달 뒤 사용자 실제 답변
  `현재 데이터로 진행`을 v3 provenance로 기록했다. 스모크 중 정지점 생성기가
  connect 단계에서 제거한 상호·주소·좌표를 원천에서 되살리는 문제를 발견해,
  제한 샘플 우선 사용과 식별 가능 컬럼 redaction을 회귀 테스트와 함께 수정했다
  (`73e6635`).
- 같은 run의 `analysis_strategy` 근거 원문 전달 뒤 사용자 실제 답변
  `핵심 질문, 핵심 지표, 분모, 비교 기준이 분석 목적과 맞으면 전략을 승인한다.
  원하는 판단이 다르거나 지표가 낯설면 질문·지표 수정을 선택한다.`를 free-text
  승인으로 기록했다. 승인된 방향으로 현재 원천을 다시 집계해 행정동 규모, 전체
  업종 구성, 지역별 구성비 배수, 예상 구성과의 상가 수 차이, 세부 분류 복잡도를
  분리한 v5.1 차트 계획과 탐색형 layout revision 1을 만들었다. schema·layout·계획
  품질 검사는 모두 issue 0이다.
- `dashboard_storyboard` 근거 원문과 탐색형 layout revision 1 전달 뒤 사용자
  실제 답변 `탐색형 화면으로 승인`을 기록하고 visualize·qa를 실행했다. 첫 네 화면
  직접 검토에서는 히트맵 제목의 `강남구 전체보다 3.83배 높다`가 배수 수준과
  증가량을 혼동시킬 수 있어 `revise`로 기록했다. 이를 `강남구 전체의 3.83배다`로
  수정하고 네 화면을 다시 생성·직접 검토한 결과 문구·위계·색·척도·축·라벨·범례·
  공백·겹침·잘림에 이상이 없어 `visual_review.status=pass`로 기록했다.
- v5.1 snapshot 최종 browser QA는 `BLOCK 0`, `WARN 5`다. WARN은 분류 복잡도
  막대의 method 조합 확인, 표 컨테이너용 보조 chart의 계획 미매핑, human checkpoint
  증거 검사 안내, 기본 Playwright 실패 후 고정 fallback 사용, mobile hero/support
  면적 비교다. 네 screenshot hash와 눈검토 기록은 현재 산출물과 일치한다.
- **v5.1 snapshot smoke 완주**: `report_outline` 근거 원문 전달 뒤 사용자 실제
  답변 `보고서 구성 승인`을 기록하고 `standard`·`mixed`·`data_only` 범위의
  `summary_report.md`를 작성했다. qa-post는 `BLOCK 0`, `WARN 3`이며 보고서 수치는
  최종 dashboard 값을 재계산하지 않고 인용했다.
- v5 baseline과 v5.1 snapshot을 spec의 10개 공통 기준으로 비교했다. 두 run 모두
  hard BLOCK 0이며, v5.1은 decision/metric/visual 계약, 4-viewport QA, source·
  screenshot hash와 구조화된 눈검토를 추가했다. 사용자 전달 뒤 추가 수정은 0회였고,
  내부 눈검토 수정은 배수 문구 1회다. WARN 수는 검사 범위가 달라 우열 지표로 쓰지
  않았다.
- **v5.1 time-series smoke 시작**:
  `apt-sale-v51-visual-quality-smoke-20260717`을 새 run으로 만들고 기존 v5
  baseline은 읽기 전용으로 유지했다. 원천 Parquet만 복사해 SHA-256
  `8a335059...08cde2` 일치를 확인했으며 과거 checkpoint 답변과 분석 산출물은
  복사하지 않았다. 새 run은 `fresh_analysis`, prior-run 참조 불허로 기록했다.
- connect·explore를 현재 원천에서 다시 수행해 1,350행, 서울 25개 구 × 54개월,
  결측·중복 조합 0건을 확인했다. 2026-06은 25개 구 행이 모두 있지만 거래량이
  504건으로 2026-05 6,656건보다 매우 낮아 월 집계 완결성 또는 신고 지연 가능성을
  data_profile 한계로 명시했다. 사용자 정지점 생성 중 `시작월`·`끝월` 표현을 언어
  게이트가 차단해 실제 연월과 상반기 비교 표현으로 수정했고 재검증은 green이다.
- data_profile 근거 원문 전달 뒤 사용자 실제 답변 `현재 데이터로 진행`을
  v3 provenance로 기록했다. 이 범위로 frame을 새로 생성해 서울 전체 월별 가격·
  거래량 흐름을 메인, 구별 가격 수준과 2022년 상반기 대비 2026년 상반기
  변화 차이를 보조로 고정했다. 분석 깊이는 예측·인과·통계적 우열 확정을 제외한
  `diagnostic`으로 강등했고 추가 설치 항목은 없다.
- analysis_strategy 근거 원문 전달 뒤 사용자 실제 답변 `전략 승인`을 v3
  provenance로 기록하고 analyze를 실행했다. 월별 서울 가격선은 구별 중앙값의
  거래량 가중 평균으로 한정했으며, 2025-06 거래량 10,970건, 2025-02 가격선
  129,385만원, 2025H1 대비 2026H1 가격 -7.6%·거래량 -24.5%를 계산했다.
  2026-06 거래량 504건은 신고 지연 또는 집계 미완결 가능성을 배제할 수 없어
  최근월 주의 신호로 분리했다.
- analysis_result_review는 diagnostic·non-domain·standard report 경로의 결정적
  술어가 거짓(`required=False`)이어서 발동하지 않았다. 차트 계획은 서로 단위가
  다른 가격·거래량을 같은 시간축의 독립 패널로 분리하고, 실제 연월·만원 단위,
  구별 상하위 막대·전후 반기 발산 막대·가격대 히스토그램·최근월 주의 막대를
  사용한다. chart spec과 layout schema, 독자용 문구 검사는 모두 통과했다.
- dashboard_storyboard 근거 생성 중 분석 문서에 남은 `시작월`·`끝월`·`기간 가격`
  및 내부 구현 표현을 다시 발견해 실제 연월과 독자용 표현으로 고치고 질문을
  재생성했다. 탐색형 layout revision 1의 근거 원문을 전달한 뒤 사용자 실제 답변
  `탐색형 화면으로 승인`을 v3 provenance로 기록했다.
- 첫 visualize·qa에서 revision 1의 월별 hero가 `data_zoom`을 요청하면서 연결된
  control/reset이 없어 QA `BLOCK 1`이 발생했다. 실행 중 승인받지 않은 control
  추가와 최근 변화율 `stacked_panels→overlay` 변경으로 layout hash가 달라진 것도
  발견해 실행을 중단하고 승인본 hash `6609ee...f5b`를 복구·대조했다.
- 중단 직전 생성된 desktop/compact/mobile/narrow 네 초안 screenshot을 모두 직접
  열었다. 차트·범례의 직접 겹침은 없었지만 desktop에서 control이 hero 높이만큼
  늘어나 큰 공백이 생겼고, 최근 전년동월 변화율 막대는 값축 `min=0` 때문에 음수
  관측값이 화면에서 사라졌으며, mobile/narrow의 상세 표는 내부 가로 스크롤이
  필요했다. 이 초안은 승인 hash와 다르므로 최종 눈검토로 인정하지 않는다.
- smoke에서 발견한 문제를 제품 본체에 반영했다. `zero_baseline`은 0을 포함하되
  음수 관측값을 자르지 않도록 renderer와 회귀 테스트를 고쳤고, stateful chart의
  control/reset 연결을 storyboard 질문 생성 전에 검사한다. 승인 뒤 QA 구조 수정은
  revision 증가와 immutable round 2 `artifact_revision` 재승인을 요구한다.
- layout revision 2는 hero·insight를 같은 desktop 행에 두고 data zoom control을
  별도 전폭 행으로 연결했으며, 같은 단위의 최근 변화율은 음수를 보존하는 공유
  0 기준축 grouped bar로 확정했다. 새 hash 근거 원문 전달 뒤 사용자 실제 답변
  `탐색형 화면으로 승인`을 round 2 provenance로 기록했다.
- revision 2 visualize 결과는 desktop/compact/mobile/narrow 네 화면을 직접 열어
  문구·위계·색·척도·축·라벨·범례·공백을 검토했고 `visual_review.status=pass`,
  browser QA `BLOCK 0`, `WARN 6`을 확인했다. WARN은 trend/bar method 확인,
  human checkpoint 검사 안내, Playwright fallback, 세 화면의 hero/support 면적
  비교이며 출고 차단 항목은 아니다.
- report_outline 정지점에서 사용자는 보고서 방향에는 동의하면서 대시보드의
  `10970` 같은 큰 숫자를 `10,970`처럼 표시하는 공통 규칙을 요청했다. 이를
  조건부 수정으로 기록해 communicate는 계속 차단했다. v5.1 spec·design system·
  pipeline contract·agent 지침에 측정값의 천 단위 구분기호를 추가하고, renderer가
  KPI·값축·직접 라벨·tooltip·histogram 구간·표를 일관되게 표시하도록 보강했다.
  자유 문구에 단위가 붙은 네 자리 이상 숫자가 구분기호 없이 남으면 static QA가
  BLOCK한다.
- 현재 time-series dashboard를 새 규칙으로 재생성했다. `107,892`, `10,970`,
  `6,656`, `238,228`과 `50,000–75,000` 구간이 네 화면에서 유지되고 숫자 길이로
  새 겹침·잘림이 생기지 않았음을 직접 확인했다. 최종 browser QA는 `BLOCK 0`,
  `WARN 6`이며 새 screenshot hash에 묶인 눈검토 기록은 `pass`다.
- 수정된 대시보드와 report_outline 근거를 다시 전달한 다음 사용자 실제 답변
  `보고서 구성 승인`을 v3 provenance로 기록했다. `standard`·`mixed`·`data_only`
  계약으로 `summary_report.md`를 만들고 communicate·qa-post를 완료했다.
- 보고서 검토에서 `04_analysis.md`에는 있으나 최종 dashboard/chart spec에는 없는
  2022년 상반기 집계값과 모니터링 임곗값이 추가 인용된 것을 발견했다. 새 계산을
  추가하지 않고 해당 수치를 제거해 승인된 대시보드 근거 범위로 좁혔다. 실제
  Chromium을 포함한 최종 qa-post는 `BLOCK 0`, `WARN 6`이다.
- snapshot/time-series v5와 v5.1을 spec의 10개 공통 기준으로 비교해
  `docs/v5-v51-smoke-comparison.md`에 기록했다. v5.1은 탐색 차트 수를 늘리는 대신
  decision/metric/visual 계약, 4-viewport, screenshot hash 눈검토, 숫자 표기 gate로
  판단 흐름과 출고 재현성을 높였다. time-series 두 run의 원천 SHA-256은 같다.
- **v5.1 release close 완료**: clean-room·Claude/Codex adapter/docs 집중 검사는
  19 passed, 전체 테스트는 `354 passed, 30 skipped, 128 subtests passed`다.
  `git diff --check`와 `runs/*` staged 제외를 확인하고 비교 문서·체크리스트·
  CHANGELOG만 제품 core와 함께 최종 커밋한다.
- **다음 작업**: v5.1 범위의 필수 작업은 없다. 이후 기능은 별도 spec과 실제
  사용자 승인으로 시작하며, marketplace 배포·push는 이 작업에서 수행하지 않는다.
- push하지 않으며 두 smoke의 `runs/*` 산출물은 커밋하지 않는다.

## [Unreleased] — dashboard profile v4 (branch: dashboard-profile-v4)

### 진행 상태

- 완료: 커밋 1~7 — 설계 확정(사용자 인터뷰 5문답 2026-07-13 + Codex
  교차검증 HIGH 5·MEDIUM 5 전부 반영), 스키마 확장, 렌더 QA selector 분리,
  E1~E5 구현, QA·언어 게이트·agent 지침, 문서 개정.
  단일 원천: `docs/specs/dashboard-profile-v4.md`(+checklist).
- **smoke ① 완주** (`apt-sale-v4-smoke-20260713`, 2026-07-13~14, 실사용자
  참여): 아래 "커밋 8 — smoke ①" 참조. 발견 수정 5건 커밋 완료.
- **smoke ② 완주** (`sbiz-gangnam-v4-snapshot-smoke-20260714`, 2026-07-14,
  실사용자 참여): 아래 "커밋 8 — smoke ②" 참조. 스냅샷 강등 경로와 보고서
  출고까지 완료했다.
- **커밋 8 마감**: smoke 2종, checklist §7, 전체 pytest·schema JSON·diff,
  `runs/*` 제외 확인 완료. 작업 이관 기록은
  `docs/handoff-codex-20260714.md`에 보존한다.
- **master 병합**: `kit-v2.1`(6be4550) 다음 순서로 2026-07-14 로컬 병합.
- 다음: v5 kickoff(자유 설계,
  `docs/specs/dashboard-freeform-v5-kickoff-notes.md`).

### 커밋 8 — smoke ② (강남구 상가 스냅샷, analyst_workspace + contract v4)

- 경로: 강남구 활성 상가 Parquet 64,239행(행정동 22개·업종 대분류 10개,
  시간 컬럼 0개) → H1 "현재 데이터로 진행" → H2 "전략 승인" → H2.5
  "1차 결과 승인" → H3 "탐색형 화면" → H4 "보고서 구성 승인" →
  communicate→qa-post 완주. 다섯 답변 모두 실제 사용자 대화 원문과
  `checkpoint-answer.v3` provenance로 기록했다.
- `analyst_workspace`·contract v4를 적용하되 KPI 6개의 `comparison`과
  `trend`를 전부 비워 **가짜 증감·추세·스파크라인을 만들지 않았다**. 대신
  행정동 규모(count), 업종 구성(share), 강남구 전체 대비 구성 차이(%p)를
  별도 차트·표로 나눠 스냅샷 집단 비교의 의미를 보존했다.
- 직접 렌더 눈검토: desktop 1280px와 mobile 390px 모두 겹침·잘림 없이
  읽혔고, 증감 기호·스파크라인이 없음을 확인했다. 모바일은 2열 KPI와 세로
  적층으로 강등되었다. 비차단 관찰로 desktop 차트 오른쪽 여백이 크고
  mobile 5열 상세표가 촘촘해, 자유 레이아웃 v5의 밀도 후보로 남긴다.
- 출고 QA: 실제 브라우저 렌더 포함 `BLOCK 0건, WARN 2건`(human checkpoint
  증거 검사 안내, 기본 브라우저 실패 후 Playwright fallback 사용). 최종
  `summary_report.md`는 standard·mixed·data_only 범위로 생성했다.
- 발견·수정: 첫 보고서 초안의 내부 계약 용어가 사용자 언어 게이트에서
  BLOCK되어, 같은 run 안에서 독자 언어로 다시 작성한 뒤 통과했다. 제품 코드
  결함이나 추가 구현 변경은 없었다.
- 최종 검증: pytest **176 passed, 12 skipped, 126 subtests passed**,
  schema JSON 13개 파싱, `git diff --check` 통과, tracked/staged `runs/*` 0건.

### 커밋 8 — smoke ① (서울 아파트 매매 월별, operations_monitor + contract v4)

- 경로: 시계열 스냅샷(25개 구×54개월, analysis.duckdb에서 축약) → guided
  intake 1문답 → H1(탐색 후보 3종 근거 내장) → H2 전략 승인 → H3
  모니터링형 승인 → visualize가 **v4 계약을 자발 이행**(contract v4,
  period_delta+trend 2 KPI+provenance, 스몰 멀티플, cell_gradient, surface)
  → 사용자 피드백 3회 반영(visualize 재실행 2회) → H4 승인.
- **smoke 발견 수정 5건** (모두 사용자 실피드백, 각각 커밋):
  1. 전달 순서(턴 분리) — 산문 규칙(630375b) + 코드 강제 3중 장치(926f808):
     gate handoff_log 스탬프, ask_user_question 답변 fail-closed, 훅
     AskUserQuestion deny. spec §4.3에 계약·한계 명문화
  2. ops grid blowout(잠복 CSS 특이도 버그가 E1 스파크와 결합해 폭발)·
     장식 가짜 레일 제거·**QA 카드 겹침 BLOCK 신설**(f3d6220 — 겹침 6→0
     실측). v5(자유 설계) 과제 확정·기록
  3. qa 렌더 스크린샷 산출물 + **눈검토 의무**(669e6a4 — QA 통과≠화면
     멀쩡, 오케스트레이터가 직접 보고 보고)
  4. 직관 문구 원칙(97958ed — story/action 명사구 나열 금지, 완결 문장)
  5. 변명·면책 문장 금지 + v5 품질 기준(b39e4d5 — 카드 본문은 수치 관측
     서술, 한계 고지는 한 곳에. 크기 위계·레퍼런스·태블로 강점은 v5로)
- E1 스파크+델타·E3 레일·E5 그라데이션은 최종 화면에서 체감 확인, E4
  스몰 멀티플은 2차 이터레이션에서 체감 확인(최종본은 에이전트가 계획-이행
  QA에 맞춰 4선 비교 라인으로 재구성 — 의도된 게이트 작동).
- 마지막 구간(communicate→qa-post) 완료(2026-07-14): `summary_report.md`
  생성, **qa-post 출고 가능 BLOCK 0건, WARN 3건**(참고성). smoke ① 완주.

### 커밋 1 — v4 설계 문서 (spec/checklist/kickoff 확정)

- 확정 결정 5건: 범위=높음+중간 5건(E1 KPI 스파크+델타·E2 analyst 단일
  스크롤·E3 레일·E4 스몰 멀티플·E5 셀 그라데이션, 도넛 제외), 델타/스파크
  조건부 활성화, analyst 첫 화면 6~8패널, 색=델타만 2색(본값 무채색),
  백엔드=순수 SVG 유지(ECharts/Plotly는 v5 분리).
- Codex 교차검증 반영: H1 comparison.kind 판별자(benchmark 의미 보존),
  H2 구조화 provenance(source_id/time_field/periods), H3 trend 시 value
  number+precision 강제(Decimal 정합 공식), H4 contract v4 opt-in+
  panel.surface(렌더 하위 호환 분리), H5 커밋 재배치(QA selector 분리 선행),
  M6 그룹 panel 한정+공통 y-domain, M7 그라데이션 인덱스 참조,
  M8 warn/neutral muted(3색 금지)+색 토큰 단일 원천, M9 QA 결정성 보강,
  M10 chart_spec 계획 우선+일치 검사.

### 커밋 2 — 스키마 확장 + E1 계약 정적 validator

- dashboard_data: timeProvenance $def, meta.dashboard_profile_contract,
  kpi.trend, comparison.kind/provenance, chart.small_multiple_group,
  panel.surface, table.cell_gradient — 전부 optional(required 불변).
  조건부 규칙 2종(trend→value number+precision, period_delta→basis/
  delta/direction/provenance 2기간). chart_spec: contract_version,
  dashboard_mapping.surface/small_multiple_group/table_treatment.
- qa profile_v4_contract_checks: provenance 대조(sources[].id·정렬·중복·
  길이), Decimal 정합(±0.5×10^-precision), delta 부호-방향 일치.
- 검증: pytest 164 passed, 112 subtests (하위 호환 fixture 포함 +16).

### 커밋 3 — 렌더 QA selector 분리 + legacy 렌더 회귀 fixture

- template card()에 chart-card 클래스, 렌더 QA 차트 수 검사를
  `.panel.active .chart-card svg`로 전환 (스파크 SVG와 분리, Codex H5).
- tests/test_dashboard_render.py 신설: legacy fixture 실렌더 DOM 기준선
  (탭 2·차트 SVG 2·전체 SVG==차트 SVG·KPI 2·페이지 에러 0).
- 검증: pytest 168 passed, 112 subtests.

### 커밋 4 — E1 KPI 스파크라인 + 델타 타일

- kpiSpark(중립색 polyline 140×40 + 기간 캡션, trend 없으면 미렌더),
  kpiDelta(period_delta만 v4 스타일 — good/bad 상태색·warn/neutral muted·
  direction은 기호만, benchmark는 현행 렌더 유지), 본값 무채색 유지.
- DOM 테스트: 스파크/차트 SVG 분리 카운트, computed style 색 룰 검증.
- 검증: pytest 171 passed, 112 subtests.

### 커밋 5 — E2 analyst 단일 스크롤 + E3 operations 레일

- `meta.dashboard_profile_contract=="v4"` opt-in 게이트 — legacy 데이터는
  기존 탭 경로 그대로(회귀 테스트로 잠금). analyst: primary 단일 스크롤+
  detail/appendix 접힘 강등. operations: 레일=기존 ACTIVE switcher 재표현,
  좁은 화면 가로 강등.
- 렌더 QA v4 인지형(analyst 탭 0·전체 카운트 / operations 레일 순회),
  WARN 2종(analyst 첫 화면 9+ 결정적 공식, v4 선언인데 이행 없음).
- DOM 테스트: 단일 스크롤 구조·레일 클릭 전환·모바일 유지.
- 검증: pytest 176 passed, 112 subtests.

### 커밋 6 — E4 스몰 멀티플 + E5 셀 그라데이션 + 계획-이행 QA

- E4: panel 내 그룹을 sm-grid로, 그룹 공통 y-domain 1회 계산 후 line/area/
  bar 렌더러에 전달. operations lead/rest 분배에서 그룹 제외.
- E5: cell_gradient 무채색 보간(null 배경 없음·min==max 중립색·
  rows[:row_limit] 기준).
- QA(BLOCK): 그룹 2~9·type 제한·축/unit 일치·panel 간 걸침 금지·chart id
  전역 중복·그라데이션 인덱스/number 열. profile_v4_plan_alignment_checks
  (chart_spec 계획↔이행). 언어 게이트에 comparison.basis·trend.period_label.
- agents/analyze.md·visualize.md v4 지침.
- 검증: pytest 182 passed, 124 subtests.

### 커밋 7 — 문서 개정

- `docs/dashboard-design-system.md`: v4 시그니처 요소 표(E1~E5), 색 규칙
  예외(델타만 2색·warn/neutral muted·"탭당 2색"=상태 accent 예산·색 토큰
  단일 원천), 구현 계약 v4 예시.
- `docs/pipeline-contract.md`: 대시보드 v4 표현 계약 절(provenance·계획
  우선·opt-in·렌더 하위 호환) — 필수 갱신으로 반영.
- CHANGELOG v4 섹션.

## kit v2.1 (branch: kit-v2.1 — **master 병합됨 2026-07-14, 6be4550**)

### 진행 상태

- 완료: v2 smoke가 남긴 마찰 2건 수정 및 master 병합 (2026-07-14).

### 커밋 1 — wrapper `--domain-mode` 플래그 (4222c4f)

- 갭: domain smoke에서 확인 — intake만으로 domain mode를 세울 경로가 없어
  manifest.json 수동 패치가 필요했음 (v1 checklist §7 알려진 공백).
- wrapper `--domain-mode` 파싱 + `write_run_context_policy`가
  `input/run_context.json`에 `domain_mode` 스탬프. 이 파일은 wrapper 재실행마다
  재작성되므로 기존 스탬프를 sticky 병합 — resume에서 플래그 생략 가능.
- 술어 확장(spec-first): spec §9 domain_mode 정의에 run_context 추가,
  `stage_guard.domain_mode_active` + `qa/validate.py` 2곳(독립 재계산) 동일 확장.
  기존 manifest.domain_mode / domain_intake.json 경로는 그대로 인식.
- domains/README 인터뷰 우선 경로 안내를 플래그 방식으로 갱신.
- 테스트: 술어 run_context 변형(true/false), QA 측 술어+결론 게이트,
  wrapper 통합(guided-intake exit 3 정지점 — codex 불필요, 스탬프·sticky·기본
  false 실검증). pytest 151 passed, 112 subtests.

### 커밋 2 — data_preview cp949 재인코딩 (f55e253)

- 단순 smoke 발견 종결: `write_csv_preview`가 utf-8 `errors="replace"`로만
  읽어 cp949 한글이 U+FFFD로 뭉개진 채 미리보기에 실림.
- strict 디코딩 폴백 체인(utf-8-sig → cp949 → utf-8-sig replace)으로 판별 후
  UTF-8로 기록. 회귀 테스트 2개(cp949 한글 보존·utf-8 원본 유지).
- 검증: pytest 153 passed, 112 subtests.

## interview loop v2 (branch: interview-loop-v2 — **master 병합됨 2026-07-13, 035e738**)

### 진행 상태

- 완료: 설계 단계 — D1~D3 사용자 인터뷰 확정(2026-07-10), spec/checklist 초안,
  Codex 교차검증(gpt-5.6-sol) 발견 9건(HIGH 4·MEDIUM 3·LOW 2) 전부 반영, 사용자
  최종 승인(2026-07-11). 단일 원천: `docs/specs/interview-loop-v2.md`(+checklist).
- **커밋 12 완료: smoke 3종 전체 완주 (2026-07-11~12, 전부 실사용자 참여).**
  다음: master 병합 검토 → v3/v4 kickoff (v4 후보 1번 = 태블로 아키타입 프로필,
  `docs/specs/dashboard-profile-v4-kickoff-notes.md` 준비됨).
- **domain smoke 완주** (`sbiz-gangnam-domain-v2-smoke-20260712`, 강남 상가
  6.4만 행, **domain_intake.json 없이 인터뷰 파생 경로**): manifest
  domain_mode 수동 표시(발견: wrapper 자동 감지 없음 — v1 checklist §7 기존
  미구현이 인터뷰 경로의 실마찰로 확인, v2.1 후보) → 데이터 확인 질문에
  companion 자동 부착(행의 의미·핵심 대상, 부족 필드 우선) → 방향
  '행정동×업종 두드러짐' R2 확정(frame_focus) → companion 답변 3건으로
  `build_domain_intake.py` **파생 생성**(readiness partial, 근거 answer_id
  기록) → 사용자 '소분류 확대' 답변이 frame 핵심 질문·report depth=deep으로
  일관 반영 → forbidden_claims 답변('단정 금지, 근거와 함께 후보 추천')이
  analyze 해석 수위에 반영 → H2.5 3중 조건 발동 → 탐색형 승인 → qa/qa-post
  **출고 가능 BLOCK 0, WARN 3** + 비샌드박스 렌더 QA BLOCK 0 +
  `deep_report.md`(142줄/10섹션, 요약 47줄과 분리) 깊이 게이트 통과.
- **statistical smoke 완주** (`sbiz-stat-v2-smoke-20260712`, 2026-07-12, 272만
  행 Parquet, 실사용자 참여): intake 1문답 확정(분포·집중도 진단 — H2.5 route
  단독 검증 목적) → explore가 **통계적 방향 후보 3종**(카이제곱·Cramér's V·
  기여 분해·구성 거리) 실계산 렌더 → 사용자 '차이 주도 조합' 선택 → R2
  확정(**커밋 12a 수정 실전 작동**: 핸드오프에 근거 표 내장) →
  **route=statistical 발동**(group_difference_candidate, deps stats
  already_installed 경로) → **v1.1 실전 프로브**: `uv add scipy` 무조건
  deny·승인 없는 `uv sync --extra` fail-closed 확인 → 실제 카이제곱 검정
  (p<1e-300, V≈0.077 — p값·효과크기 분리 서술, 기대빈도<5 조건 표기) →
  **H2.5 route 조건 단독 발동**(`matched_conditions: [route_requires_review]`)
  → storyboard 탐색형 승인 → qa/qa-post **출고 가능 BLOCK 0, WARN 3**(참고성)
  + 렌더 포함 QA 비샌드박스 재실행 BLOCK 0 확정. 발견: 렌더 QA Playwright
  실패는 **codex 샌드박스 내부 한정** 환경 제약으로 종결(wrapper qa 게이트는
  셸 실행이라 정상), 프로필 체감 갭(위 v4 노트), qa-post WARN
  `method_limit_reference` chart_spec 매핑 없음(보조 차트 참고성 — 후보).
- **단순 smoke 완주** (`police-crime-v2-smoke-20260711`, 2026-07-11~12,
  실사용자 참여): guided intake 2문답 → 데이터 확인 단계에서 LLM 계산 방향
  후보 3종 렌더 → 사용자가 '지역×유형 두드러짐' 선택 → R2 확정(frame_focus)
  → frame·analyze에 선택이 일관 반영 → H2.5 발동(candidate_prioritization
  술어) → **자유 질문 1회 실사용**(서울 자치구 상대 두드러짐 — 기록→미니
  쿼리→provenance 저장→R2 연결 전체 고리 검증) → storyboard 탐색형 승인 →
  visualize → **네트워크 중단 발생 후 승인 기록 무손실 재개** → qa/qa-post
  **출고 가능 BLOCK 0, WARN 2**(KPI 큰 수치 축약 권장·정책 안내), 대시보드
  6차트 + summary_report 출고. 발견: 커밋 12a(수정 완료), data_preview
  cp949 인코딩(후보), 렌더 QA의 로컬 Playwright 실행 실패 1회(환경 문제
  가능성 — statistical smoke 전 확인), 태블로 VOTD 스타일 프로필은
  region-dashboard 전용 합의로 kit 미적용 확인 → **v4 kickoff 후보 1번으로
  기록**. statistical smoke 검토 중 추가 발견: 프로필 3종은 설계 문서·렌더러
  분기까지 존재하나 시그니처 요소(KPI 스파크+델타·레일 내비·스몰 멀티플·
  첫 화면 밀도) 부재로 **프로필 차이가 체감되지 않음** — 갭 분석과 샘플
  아키타입 요약을 `docs/specs/dashboard-profile-v4-kickoff-notes.md`로 기록
  (참고 자산: region-dashboard `mockup/build_v2.py` v7 — 히어로
  헤드라인·진단 배지·압력맵·KPI 타일+스파클라인. kit 현행 룰(순수 SVG·KPI
  무채색·색 2종)과의 긴장은 v4 설계 인터뷰에서 결정).

### 커밋 12b~12d — smoke 중 상호작용 모델 확정·발견 수정

- 사용자 결정: 상호작용 모델 확정 — 파일(md/json)=계약·증거, 채팅=전달·답변
  창구, 채팅 전달은 "원문 우선 + 보강"(질문·선택지 재작성 금지). AGENTS/SKILL
  명문화.
- 12b(22387fd): 질문 md를 채팅과 동일 완결성으로 — 근거 원문·추가 확인
  질문·직접 질문 안내 내장(검토 발견 3건 해소). collect_evidence 공용화.
- 12c(afdf366): chat_prompt를 불릿 포인트로 재구성(벽 텍스트 가독성 피드백).
- 12d(08e9f09): **12b가 만든 자기 차단 발견·수정** — companion 기록 명령의
  checkpoint_id(내부 용어)가 md 사용자 구역에 노출되어 언어 게이트가 자기
  질문 파일을 차단(domain run report_outline에서 실발생, v1 발견 1과 동류).
  기록 명령을 '답변 반영'(기술 부록 뒤)으로 이동 + companion md 언어 게이트
  회귀 테스트. 12b~12d 모두 pytest green (최종 148 passed, 110 subtests).

### 커밋 12a — smoke 발견 1 수정: 선택 순간에 근거가 안 보임

- 사용자 실검증에서 발견: 방향 확정 질문에서 "아무것도 안 보여주고 질문만
  한다" — 원인 2겹. (1) 질문 JSON 본문에는 미리 본 결과 표가 있으나
  `chat_prompt`가 650자 압축을 거치며 표 탈락(2,828→355자 확인), (2) 상위
  오케스트레이터가 팝업 preview에 근거를 실었으나 이 환경에서 preview가
  렌더되지 않음 — 링크·팝업 미리보기는 "보여준 것"이 아니다.
- 수정: `checkpoint_gate.py` 채팅 핸드오프(`render_question_for_chat`)가
  미리 본 결과 원문(후보 표·직접 질문 확인 결과 md)을 그대로 내장. AGENTS/
  SKILL 표시 의무에 "근거 내용을 본문에 직접 출력, 팝업 UI preview 의존
  금지" 명문화. 회귀 테스트 1개(print-existing에 표 내용 포함).
- 후보(미수정): `data_preview.csv`가 cp949 원본 그대로라 미리보기가 깨져
  보임 — UTF-8 재인코딩 후보로 기록.
- 검증: pytest 148 passed, 107 subtests + 실전 run 핸드오프에 표 내장 확인.
- 결정 요약: D1=전 정지점 업그레이드(새 정지점 0 — 기존 4 checkpoint + 조건부
  H2.5의 질문 레이어를 인터뷰 루프로 교체), D2=혼합형(선택지형 + 라운드당 자유
  질문 1), D3=정지점당 최대 2라운드×3문항 + 조기 종료. 핵심 계약: 불변식 I1
  (탐색·수집 레코드 진행 불가), canonical 답변 단일화, 질문 파일 resolver(§4.6),
  유효 R2 체인.

### 커밋 1 — v2 설계 문서 (spec/checklist/kickoff)

- `docs/specs/interview-loop-v2.md` 신설(런타임 계약 13섹션),
  `docs/specs/interview-loop-v2-checklist.md` 신설(12커밋 추적),
  kickoff에 D1~D3 확정 결과 기록.
- Codex 교차검증 반영: H1 게이트 우회→I1 불변식, H2 mirror 역전→canonical
  단일화+fail-closed, H3 R2 resolver 부재→§4.6 신설, H4 커밋 순서 결함→
  round-aware QA를 커밋 5로 이동, M1 주 질문 선택자, M2 readiness 트리거 (b),
  M3 반려 전이 사실 정정+유효 R2 체인, L1 조건부 스키마, L2 용어 명확화.
  첫 Codex 실행은 프로세스 사망(좀비 상태 파일)으로 폐기하고 xhigh로 재실행 —
  이후 백그라운드 잡 감시에 pid 생존 검사를 포함하기로 함.
- 검증: pytest 111 passed, 56 subtests.

### 커밋 2 — v1.1: hook `uv add` 전면 deny

- `dik_checkpoint_hook.py` install 게이트: `uv add`는 kit `pyproject.toml`을
  변경하므로 allowlist·승인과 무관하게 deny하고 `uv sync --extra <group>`
  대체 경로를 안내. pip/`uv sync --extra` 경로는 기존 동작 유지.
- 회귀 테스트 2개: 유효 승인+allowlist 패키지 `uv add` deny(체인 명령 포함),
  유효 승인 `uv sync --extra stats` 통과 유지.
- v1 발견 3을 수정 완료로 종결.
- 검증: pytest 113 passed, 58 subtests. (Pyright 힌트 hook:351·tests:640/658은
  이번 diff 밖 기존 baseline — git diff 대조로 확인)

### 커밋 3 — schema: 인터뷰 루프 계약

- `checkpoint_question.schema.json`: `schema_version` enum에 v2 추가(v1 유지),
  optional `interview_loop`(round·max_rounds·free_question_used_this_round·
  prior_round(question_sha256/trigger)·finalization_rule), `companion_questions`
  (≤2, 옵션 스키마에 continue_pipeline 자체가 없음 — I1 스키마 층),
  `exploration`(candidates_ref/free_question_slot). 조건부 if/then: v2면
  interview_loop 필수, round=2면 prior_round 필수, `maps_to.loop_action` 옵션은
  continue_pipeline=false.
- `schemas/exploration_candidates.schema.json` 신설: 후보 2~3, mini_result 필수
  필드(summary/table_path/computation/source_columns/row_count_used),
  maps_to.frame_focus 필수.
- `docs/pipeline-contract.md` "중간 체크포인트 계약"에 "인터뷰 라운드" 절 추가
  (라운드 파일명·유효 R2 체인·문항 예산·I1·canonical 단일화·후보 산출물 계약).
- 테스트: InterviewLoopSchemaTests 7개(legacy v1 하위 호환, v2 필수 구조,
  round2 prior_round, I1 옵션, companion 상한·게이트 무관, exploration 형태,
  후보 스키마 경계) — 스키마만 바뀌고 gate는 아직 v1을 생성하므로 기존 생성
  질문 검증 테스트가 하위 호환 회귀를 겸한다.
- 검증: schemas 13개 JSON 파싱, pytest 120 passed, 75 subtests.

### 커밋 4 — 런타임 코어 1: 답변 기록·라운드 생성

- `apply_checkpoint_answer.py`: `--free-question`(loop_action 레코드, 라운드당
  1개를 기록 시점에도 거부)·`--companion`(정보 수집 전용) 추가,
  `--continue-pipeline`과 상호 배타(I1), `maps_to.loop_action` 옵션은 기록
  시점에 continue_pipeline 강제 false(I1 이중 방어), `interview_round` 기록,
  질문 파일 허용 집합 검사(run outputs/checkpoints 내부 +
  `<NN>_<cp>_question[.round2].json` 형식만).
- `checkpoint_gate.py`: 질문 v2 스탬프 + `interview_loop`, 라운드 2 파일
  `.round2` 생성(트리거 (a): 결정 레코드의 loop_action, prior_round에 R1
  sha256·answer_id·trigger·미니 결과 연결), 라운드 3 생성 거부, 상한 도달·고아
  레코드 안내(exit 4), canonical 단일화 + mirror 불일치 fail-closed,
  companion 제외 결정 레코드 선택(M1), `--print-existing` 라운드 2 우선.
  **H2 코드 확정**: 기존 `latest_answer`가 canonical 뒤에 mirror를 이어붙여
  `answers[-1]`을 취했음을 확인 — Codex 지적 그대로.
- 구현 중 spec 정정 1건: §4.3 "주 질문 답변 선택"이 자유 질문을 제외하면
  트리거 (a)가 영영 발동하지 않는 모순 → "결정 레코드 = companion만 제외"로
  통합(자유 질문은 I1로 승인 불가라 라운드 전이만 유발). spec §4.3/§9 갱신.
- 테스트: InterviewLoopRuntimeTests 5개 — 라운드1 v2→자유 질문→라운드2 생성
  체인(prior_round sha 검증), 자유 질문 예산·상호 배타, 허용 집합 밖 질문
  파일 거부, mirror 불일치 fail-closed, 승인 후 companion append 상태 유지.
  테스트 픽스처 시각 버그 1건 수정(미래 created_at을 가드가 정확히 거부).
- 검증: pytest 125 passed, 78 subtests. Pyright 신규 지적은 전부 diff 밖
  기존 코드 재표면화(631~639행 차트 요약부 — git diff 대조 0건, stage_guard
  sys.path import).

### 커밋 5 — 가드·round-aware lineage (커밋 7 smoke의 전제, H4 재배열)

- `stage_guard.py`: `answer_store_issues`(canonical/mirror 불일치 fail-closed),
  `latest_answers` canonical 단일화 + companion 제외(M1),
  `resolve_answer_question`(§4.6 resolver — 허용 집합·유효 R2 체인·prior
  answer_id 존재·created_at 순서·round3+ 파일 차단), `validate_answer`에 I1
  위반(loop_action/companion 레코드 승인 불가)·store·resolver 검증 통합,
  `analysis_strategy_lock_issues`가 승인된 라운드의 approval_targets를 읽도록
  resolver 사용. hook은 stage_guard 재사용으로 자동 상속.
- `qa/validate.py`: `_latest_checkpoint_answers` companion 제외,
  `_resolve_answer_question_path` 신설(§9 독립 재계산 원칙대로 guard와 별도
  구현), provenance 검사가 R2 승인을 인정 + I1 위반 BLOCK.
- `dik_checkpoint_hook.py`: `.round2` 질문 파일이 endswith 매칭에서 빠지던
  것을 USER_FACING_SUFFIXES 확장으로 배포용 언어 게이트에 포함.
- `validate_user_facing_text.py` FORBIDDEN_TERMS 7종 추가(interview_loop,
  exploration_candidates, companion_question, free_question, mini_result,
  loop_action, frame_focus). 언어 게이트는 user 필드만 스캔하므로 v2 질문
  JSON 구조가 자기 차단되지 않음을 사전 확인(v1 발견 1 재발 방지) — 생성된
  R1·R2 질문의 언어 게이트 통과를 테스트로 고정.
- 테스트: InterviewLoopGuardTests 4개 — R2 승인이 gate·stage_guard·QA
  provenance·언어 게이트를 전부 통과(end-to-end, H4 해소 증명), 고아 R2
  차단, round3 파일·위조 loop_action 승인(I1) 차단, QA companion 제외 단위.
- 검증: pytest 134 passed, 87 subtests.

### 커밋 6 — data_profile 부착: 탐색 방향 후보 렌더·frame_focus 연결

- `checkpoint_gate.py`: `load_exploration_candidates`(스키마 검증, 없거나
  불일치 시 기본 질문 강등+사유 — §6.1 안전판), 라운드 1 옵션 재구성
  [바로 진행 + 방향 ≤3](방향 옵션은 I1로 continue_pipeline=false 강제 생성,
  description에 미니 결과 1줄), `exploration` 블록(candidates_ref·자유 질문
  슬롯), 후보 표를 artifacts에 연결(표시 의무). 라운드 2(explore_direction
  트리거): 선택 방향 미니 결과 표(≤14줄)를 질문에 내장하고 `confirm_direction`
  옵션 maps_to.frame_focus로 frame 입력 계약 생성.
- `agents/explore.md`: exploration_candidates 산출 계약(실데이터 계산 필수,
  계산 불가 후보 제시 금지, 원인·추천 단정 금지). `agents/frame.md`:
  frame_focus 반영+근거 명시, 미니 결과 직접 복사 금지(재계산 원칙).
- 테스트: 하네스 리팩터(InterviewLoopHarness — guard 서브클래싱으로 런타임
  테스트가 중복 실행되던 것 제거) + InterviewLoopExplorationTests 3개(방향
  옵션 렌더·I1·언어 게이트, 방향 선택→R2 frame_focus→승인→stage_guard 통과,
  후보 불일치 강등).
- 검증: pytest 132 passed, 85 subtests (중복 5 제거 + 신규 3 = 정합).

### 커밋 7 — 중간 smoke 게이트 (결함 0)

- 실데이터 CSV(45행 합성, 지역·월·업종·건수)로 **결정적 기계 전체를 실제
  runs/ 디렉터리에서 완주** — 28개 체크 ALL PASS, 발견 결함 0건:
  - run A(탐색 문답): R1 방향 옵션 렌더 → `explore_by_region` 선택 → R2에
    실계산 미니 결과 표 내장 → `confirm_direction`(frame_focus=by_region)
    확정 → gate 승인 → 4개 checkpoint 순차 승인 →
    frame/analyze/visualize/communicate **전 stage_guard 통과** → qa lineage
    함수(승인 판정+provenance, R2 resolve 포함) **BLOCK 0** → 전 질문 파일
    언어 게이트 통과.
  - run B(조기 종료 회귀): 후보 파일 없음 → 기본 질문 강등+사유 표기 →
    바로 승인 → v1 동일 흐름, 라운드 2 파일 0개.
- 범위 명시: 산출물은 드라이버가 실제 CSV에서 stdlib로 계산해 작성했고
  (산출물에 명시), LLM 에이전트 스테이지를 포함한 완주와 전체 qa/validate.py
  (대시보드 렌더 QA 포함)는 계획대로 커밋 12 smoke 3종에서 검증한다.
- smoke run 2개는 `runs/`(gitignore)에 남기고 커밋하지 않음. 드라이버는
  세션 스크래치패드(레포 밖).

### 커밋 8 — 나머지 정지점 부착 + §7 미니 결과 artifact 계약

- 라운드·자유 질문 런타임은 커밋 4~5에서 정지점-불문으로 이미 동작 — 전
  정지점(analysis_strategy/analysis_result_review/dashboard_storyboard/
  report_outline)에서 자유 질문→R2 생성을 테스트로 고정.
- `checkpoint_gate.py`: 전 정지점 질문에 자유 질문 안내 노출(chat handoff
  1줄 + `response_instructions.free_question_command`, 스키마 optional 필드
  추가), dashboard_storyboard 단순 run(§9 술어 거짓)에서 "1차 분석 결과
  검토를 겸합니다" + 04_analysis 요약 내장(v1 checklist §8 미결 흡수 —
  심화 run에서는 미표기).
- `scripts/record_free_question_result.py` 신설(§7 계약 실물): 자유 질문
  답변 선행 필수(answer_id 연결), md 고정 골격(질문 원문·계산 방법·결과 표
  ≤20행·한계·참고 자료 고지) + provenance JSON, answer_id당 1개, R2
  prior_round.mini_result_paths로 자동 연결.
- analysis_strategy R2 생성 시 approval_targets 최신 재계산을 테스트로 증명
  (자유 질문 뒤 method_route 변경 → R2가 새 sha 잠금).
- 구현 중 spec 정정 1건(§9): 미니 결과 파일을 언어 게이트 대상에서 제외 —
  사용자 질문 원문 인용 파일이라 오탐 유발. helper 고정 골격 + QA provenance
  검증으로 대체.
- 테스트: InterviewLoopRemainingStopsTests 5개(전 정지점 R2, targets 재계산,
  storyboard 요약 조건부, artifact 계약 오류 경로 4종 포함, chat 안내).
- 검증: pytest 137 passed, 96 subtests.

### 커밋 9 — 도메인 인터뷰 런타임화 (§8)

- `checkpoint_gate.py`: §8.1 매핑(CHECKPOINT_DOMAIN_FIELDS)과 사용자 표현
  질문 사전(DOMAIN_FIELD_QUESTIONS), `domain_interview_state`(주입 파일+companion
  답변을 합쳐 readiness 부족 필드를 stage_guard와 같은 규칙으로 계산),
  `domain_companions_for`(부족 필드 우선 ≤2 결정적 선택) — domain mode의 모든
  질문에 companion 자동 렌더 + chat handoff 표시(진행 무관 명시). **R2 트리거
  (b)**: 결정 레코드 없음 + 현재 R1에 대한 companion 답변 존재 + 정지점 관련
  readiness 필수 필드 잔존 → R1 재생성 대신 재확인형 라운드 2 생성
  (`prior_round.trigger=domain_readiness_gap`, 미확인 업무 기준을 사용자
  표현으로 나열).
- `scripts/build_domain_intake.py` 신설(§8.2): companion 답변에서
  `input/domain_intake.json` 결정적 파생 — canonical/mirror 정합 검사,
  `generated_by`/`source_answer_ids`/`generated_at` provenance(스키마 optional
  필드 추가), readiness는 deterministic-v1 규칙으로 계산. 수동 주입 파일이
  있으면 필드를 덮지 않고 open_questions 보강만(주입 우선). 자유 서술의
  구조화 배열 매핑 한계(고정 라벨 래핑)를 docstring에 명시.
- 테스트: InterviewLoopDomainTests 3개 — 우선순위 companion 렌더(비도메인
  run 미렌더·chat 표시 포함), readiness gap→트리거(b) R2→승인→파생 생성
  (스키마 검증·partial readiness·근거 answer_id), 수동 주입 우선+보강 병합.
- 검증: pytest 140 passed, 102 subtests.

### 커밋 10 — QA 확장 (§9 잔여 항목)

- `qa/validate.py` `interview_loop_checks` 신설(메인 검증 흐름에 연결, auto
  정책 skip 존중): canonical/mirror 불일치 BLOCK, 불변식 I1 위반 전체
  BLOCK(companion·자유 질문·방향 선택 레코드의 continue_pipeline=true), 자유
  질문 라운드당 >1 BLOCK, 라운드 파일 스윕(round3+ BLOCK·고아 R2 WARN·근거
  답변 없는 R2 위조 BLOCK), 미니 결과 provenance(비존재 answer_id·비자유질문
  연결·질문 기록보다 앞선 생성 BLOCK), 미니 결과 표 행의 보고서·대시보드 직접
  인용 WARN(§7 — 대표 run 보정 후 승격 검토), 파생 domain_intake 무결성
  (generated_by 표기·source_answer_ids 존재·companion 답변 여부).
- 테스트: InterviewLoopQaTests 5개 — 정상 R2 완주 run은 BLOCK/WARN 0,
  I1·예산 위반, 라운드 스윕(BLOCK+WARN), 미니 결과 3경로+직접 인용 WARN,
  파생 domain_intake 위조 근거 BLOCK.
- 검증: pytest 145 passed, 105 subtests.

### 커밋 11 — 문서 (§10 domain 이연분 + 사용자·운영 문서) + 훅 오탐 수정

- v1 이연분(§3): `CUSTOMIZATION.md`를 인터뷰 우선 경로 중심으로 보강(§8 계약
  연결, pack은 승격 결과물로 재배치), `domains/README.md`에 "인터뷰로 시작"
  (build_domain_intake·수동 파일 우선·readiness 게이트 불변)과 "run 지식의
  승격 흐름"(domain_pack_update_candidates.md 역할) 추가,
  `domains/template/interview-questions.md`에 kit 기본 질문과의 역할 구분 +
  1차 결과 검토·보고서 전 질문 절, `kpi-rules.md`에 evidence class 표(§8.6),
  `qa-rules.md`에 과잉해석 BLOCK 예시 4종.
- 사용자·운영 문서: `README.md`·`GUIDE.md`에 탐색 문답 안내(사용자 표현만),
  `AGENTS.md`·`skills/run-pipeline/SKILL.md`에 라운드·자유 질문(기록→미니
  쿼리→record_free_question_result 순서)·companion·I1·표시 의무 확장 운영 규칙.
- **훅 오탐 발견→수정**: `domains/README.md` 편집을 kit 자체 훅이 pack 쓰기로
  오인 차단(`domains/<이름>/` 매칭이 domains 루트 파일까지 포함). pack 콘텐츠는
  `domains/<name>/` 안쪽 경로여야 한다는 가드 추가 — pack 내부 차단·template
  예외는 회귀 테스트로 유지 확인.
- 검증: pytest 147 passed, 107 subtests.

## [Unreleased] — expert-guided analysis routing v1 (branch: expert-routing-v1)

### 진행 상태

- 완료: v1 전체 — 1단계(커밋 1~4), 2단계(커밋 5~8), §16 대표 run 검증(smoke 3종 전부
  실제 codex exec로 완주·출고), 검증 중 발견 결함 2건 수정(커밋 9~10), §2 route 문서.
- 다음: master 병합 검토 → **v2 spec 착수** ("interview loop 런타임": guided-intake의
  질문 JSON→답변 누적→확정 패턴을 explore↔frame 사이와 domain intake에 이식,
  spec §8.3/§12.2 기반). §3 domain 문서(`CUSTOMIZATION.md`/`domains/*`)는 인터뷰
  워크플로우 실물과 함께 v2에서 작성한다 (아직 없는 흐름의 선문서화 방지).
- 주의: kit 전용 `.venv`는 사용자가 `analysis_strategy`에서 설치를 승인한 시점에만
  wrapper(`dependency_preflight.py --apply-approval`)가 생성/설치한다 — repo에는 커밋되지
  않는다. 이번 statistical smoke에서 실제로 생성됐고 `uv.lock`은 untracked로 남아 있다.

### 대표 run 검증 (§16) — smoke 3종 (2026-07-10, 커밋 8 이후 실행)

| run | 데이터 | 검증한 경로 | 결과 |
|---|---|---|---|
| `police-crime-simple-smoke-20260710` | 경찰 범죄통계 (CSV) | descriptive route, H2.5 **미발동**(술어 거짓), 설치 선택지 미표시, 기존 4-checkpoint 회귀 | 완주, qa-post BLOCK 0 |
| `sbiz-stat-route-smoke-20260710` | 전국 상가 272만 행 (Parquet) | statistical route 발동 → 설치 승인 4옵션 → 실제 `uv sync --extra stats`(kit `.venv` 생성, provenance 완결) → 실제 Welch 검정 → **H2.5 발동(route 조건)** → 재개 시 상태 머신 전체 재검증 | 완주, qa/qa-post BLOCK 0 |
| `sbiz-gangnam-domain-smoke-20260710` | 강남 상가 6.4만 행 + `domain_intake.json` | diagnostic route인데 **H2.5 발동(domain_mode 단독 조건)**, analyze 진입 도메인 게이트, readiness 재계산 일치, forbidden_claims 3종 미검출 통과 | 완주, qa/qa-post BLOCK 0 |

검증 중 발견 (수정 완료 2건 + v1.1 후보 1건 + v2 이연 1건):

1. **[수정: e9678de]** `checkpoint_gate.py` 정적 문구 'KPI strip'이 FORBIDDEN_TERMS
   'KPI'와 충돌 — 모든 run이 dashboard_storyboard에서 배포 언어 게이트에 BLOCK되던
   잠재 결함. 게이트가 자기 자신의 문구를 잡아낸 사례.
2. **[수정: 2730f56]** data_profile "데이터 샘플 미리보기"가 실제 데이터가 아니라
   `input/checkpoint_policy.json`을 샘플링 — `source_files()`가 wrapper 생성 메타데이터
   JSON을 걸러내지 않았고 알파벳 정렬로 그게 먼저 옴. smoke 3종 전부에서 재현.
   KIT_INTERNAL_INPUT_FILES 제외 + 표 형식 우선 정렬로 수정. 같은 커밋에
   오케스트레이터 표시 의무(질문 md 원문·데이터 샘플·artifacts 링크 필수 제시,
   요약은 원문 대체 불가)를 SKILL/AGENTS에 명문화.
3. **[수정: v2 커밋 2]** hook 설치 게이트가 `uv add <allowlist pkg>`를 (유효 승인 시) 허용
   — `uv add`는 `pyproject.toml`을 변경하므로 `uv sync --extra`만 허용하고 `uv add`는
   전면 deny하는 것이 더 안전. statistical smoke 중 analyze 에이전트가 실제로
   `uv add`를 1회 실행(추적 파일 변경은 자체 복구)한 것이 발견 계기.
4. **[v2 이연 — 구조 진단]** "비전문가와 함께 탐색"하는 상호작용 모델이 v1에 없음.
   v1 아키텍처는 batch stage + 승인 게이트라 사용자는 완성된 결과의 결재자가 되고,
   spec §4(분석가 사고 절차 안내)·§8.3(단계별 인터뷰)의 공동 탐색 경험은 guided
   intake 한 곳에만 존재. git 이력상 반복된 checkpoint 수정(8fa391a→3255cc2→bba8329→
   96d8b3b→800859a→f189520)이 전부 게이트 레이어 강화였고 상호작용 레이어는 미구현
   — 체감이 안 변한 원인. v2를 "interview loop 런타임"으로 정의하는 근거.

### 커밋 9 — 게이트 정적 문구 사용자 표현화 (e9678de)

- `checkpoint_gate.py` 정적 옵션/프로필 문구 'KPI strip' → '핵심 지표 카드'.
- 검증: 재생성 질문 `validate_user_facing_text` 통과, pytest 108 passed 56 subtests.

### 커밋 10 — data preview 버그 수정 + 표시 의무 명문화 (2730f56)

- `checkpoint_gate.py`: `KIT_INTERNAL_INPUT_FILES` 제외 집합 + 표 형식 우선
  정렬(`parquet/csv/tsv` → 사용자 JSON)로 `source_files()` 수정.
- `tests/test_checkpoint_gate_routing.py`: 회귀 테스트 3개(메타데이터 제외,
  표 형식 우선, build_data_preview가 실제 데이터 선택).
- `SKILL.md`/`AGENTS.md`: 체크포인트 승인 요청 시 표시 의무 명문화.
- 검증: pytest 111 passed 56 subtests.

### 커밋 1 — 계약/spec 문서 (코드 0줄)

구현 전 리뷰(2026-07-10)에서 확정한 결정을 spec·checklist·pipeline-contract에 반영.

- 체크포인트 renumbering 철회: `analysis_result_review`는 고정 prefix `05_`,
  기존 `01`~`04` 불변, legacy dual-read 불필요.
- `analysis_result_review` 발동 조건을 결정적 술어로 확정 (route ∈ 심화 4종 OR
  domain mode OR report.depth=deep OR analysis_mode ∈ {candidate_prioritization,
  risk_screening}). stage guard와 QA가 각자 재계산, 에이전트 플래그 불신.
- dependency 설치 대상을 kit 자체 `pyproject.toml` + kit 전용 `.venv`로 확정.
  optional extras는 v1에서 `stats`, `ml` 2개만 (`interactive-viz`/`echarts`는 v4).
- `analysis_strategy` 질문 JSON에 `approval_targets`(method_route/dependency_plan
  sha256) 내장 — 승인 후 상향 변경은 재승인, 강등은 사유 기록으로 허용.
- 설치 승인은 명시 옵션 선택만 인정 (`maps_to.dependency_decision`), free-text 불인정.
- method registry를 YAML → **JSON**(`methods/method_registry.json`)으로 변경.
  사유: 결정적 코어는 stdlib+jsonschema만 사용하는데 런타임에 pyyaml이 없고(검증:
  `python3 -c "import yaml"` 실패), registry를 읽으려고 의존성 설치가 필요하면
  승인형 설치 흐름과 모순.
- hook의 install 명령 게이트(`pip install|python -m pip|uv add|uv sync --extra` deny),
  `domains/` 자동 수정 deny, FORBIDDEN_TERMS 신규 용어 추가를 checklist에 명시.
- 도메인/통계 과잉해석 언어 게이트: forbidden_claims 명시 문구만 BLOCK,
  일반 휴리스틱은 WARN 시작.
- pipeline-contract: 실행 순서에 H2.5(조건부 결과 검토), frame 출력에
  method_route.json/dependency_plan.json, 체크포인트 표·run 레이아웃·코어 산출물
  목록 갱신.

검증: `python3 -m pytest tests/test_pipeline_guards.py` — 48 passed (문서만 변경,
기존 guard 회귀 없음 확인).

### 커밋 2 — schemas (8cffd02)

- 신규: `schemas/method_route.schema.json`, `schemas/dependency_plan.schema.json`,
  `schemas/domain_intake.schema.json`.
- `schemas/checkpoint_question.schema.json`: `checkpoint_id`에
  `analysis_result_review`, `checkpoint_kind`에 `result_review`, optional
  `approval_targets`(sha256 잠금) 추가.
- 검증: 12개 schema meta-check OK, 신규 3종 샘플 인스턴스 검증 OK,
  기존 checkpoint 질문 파일 27개 변경 전후 판정 동일(regression 0),
  pytest 48 passed.

### 커밋 3 — method registry + dependency preflight + kit pyproject (2d244dd)

- `methods/method_registry.json`: spec §6의 12개 method(core 5/stats 4/ml 3),
  dependency_allowlist 단일 원천, predictive/causal_experiment는 v1
  downgrade-only 명시.
- `pyproject.toml`(kit 자체): base jsonschema, extras `stats`/`ml`만.
  `.venv` 생성은 하지 않음(설치는 사용자 승인 후 wrapper).
- `scripts/dependency_preflight.py`: stdlib 전용, kit `.venv`만 판정 기준,
  절대 설치하지 않음(소스에 subprocess 부재를 테스트로 강제),
  required_extras 변경 시 기존 승인 무효화.
- 검증: pytest 59 passed(신규 11), CLI 스모크(스크래치 runs-root) exit 0·설치 없음.

### 커밋 4 — checkpoint_gate 확장

- `analysis_result_review` checkpoint 추가: 고정 prefix `05_`, 기존 01~04 불변.
  옵션 4종(승인/결론 수위 낮추기/기본 분석 전환/재분석), 사용자용 brief 포함.
- `analysis_strategy` 질문에 승인 시점 잠금: 존재하는
  `method_route.json`/`dependency_plan.json`의 sha256을 `approval_targets`로 내장.
- 설치 승인이 필요한 run(missing extras)에서는 옵션을 dependency 결정 포함
  4종으로 교체(`install_and_deepen`/`proceed_without_install`/수정 2종,
  `maps_to.dependency_decision=install|skip_install|adjust`). 설치 승인은 명시
  옵션 선택만 — free-text 불인정 문구 포함. 이미 설치된 경우 기존 옵션 유지.
- current_understanding에 분석 깊이·추가 기능 요약(사용자 언어) 추가.
- 검증: pytest 64 passed(신규 gate-routing 5), 생성 질문 schema 검증 +
  용어 게이트(validate_user_facing_text) clean, CLI 스모크로 채팅 handoff 확인.

### 커밋 5 — stage_guard/hook 확장: §9 술어, install 게이트, 승인 잠금 (4ad5ea1)

- `stage_guard.py`: spec §9 `analysis_result_review` 술어(route_requires_review/
  domain_mode/report_depth_deep/decision_analysis_mode)를 결정적으로 재계산 —
  `method_route.json`의 `review_predicate` 필드는 신뢰하지 않는다. run별
  `effective_stage_requirements()`가 술어가 참인 run의 `visualize`/`qa`/
  `communicate`에 `analysis_result_review`를 `dashboard_storyboard` 앞에 삽입한다.
  `compute_domain_readiness()`(spec §8.5 결정적 규칙)로 domain mode인데 intake가
  없거나 insufficient인데 도메인 조건이 필요한 method가 선택되면 `analyze` 진입을
  차단한다. `analysis_strategy_lock_issues()`가 승인 시점 `approval_targets`
  sha256과 현재 `method_route.json`/`dependency_plan.json`을 비교해 상향 변경은
  재승인을, 강등은 사유 기록만 요구한다.
- `dik_checkpoint_hook.py`: kit run 컨텍스트의 Bash install 명령
  (`pip install`/`python -m pip install`/`uv add`/`uv sync --extra`)을 registry
  allowlist·승인 provenance 기준으로 deny하고, `domains/<name>/` 자동 수정
  write(Write/Edit/apply_patch/Bash 공통)를 전면 deny한다. `method_route.json`도
  `03_frame.md`와 동일하게 checkpoint 보호 대상에 추가.
- `validate_user_facing_text.py`: `FORBIDDEN_TERMS`에 `method_route`,
  `dependency_plan`, `domain_readiness`, `domain_intake`, `analysis_result_review`,
  route 내부명을 추가(spec §11 대체 표현 강제).
- 수동 보안 리뷰(이 환경에는 Codex CLI 교차검증 불가)에서 랜딩 전 발견·수정한 실제
  우회 3건: `uv sync --all-extras`가 allowlist·provenance 검사를 모두 건너뜀,
  체인 명령(`pip install ok && pip install bad`)이 첫 세그먼트만 검사됨,
  `bash_targets()`의 runs/-scoped 필터 때문에 Bash 리다이렉트/cp/tee 경유
  domain-pack write 게이트가 전혀 발동하지 않음.
- 검증: `python3 -m pytest tests/ -q` — 64 passed, 17 subtests passed(문서
  이후 최초 코드 커밋, 회귀 없음 확인).

### 커밋 6 — wrapper 배선: route 생성 → preflight → 승인 시 설치 → 조건부 H2.5 (c90d748)

- `agents/frame.md`: 새 3-bis 단계로 frame이 `methods/method_registry.json`
  기준 실제 데이터 조건과 대조해 route + selected_methods를 정하고
  `outputs/method_route.json`을 쓴다. `predictive`/`causal_experiment`는 v1
  registry 정책상 downgrade-only로 유지.
- `dependency_preflight.py`: 새 `--apply-approval` 모드 — wrapper가
  `analysis_strategy` checkpoint 통과 직후 호출한다. 승인 답변을 stage_guard로
  재검증한 뒤 `maps_to.dependency_decision`으로 분기: `install`이면 missing
  extra마다 `uv sync --extra <group>`를 실행하고 `install_result`를 기록,
  `skip_install`과 설치 실패는 둘 다 `method_route.json`을 core-only route로
  강등하고 `downgrade_reason`을 남긴다.
- `run_codex_pipeline.sh`: `frame → dependency preflight → analysis_strategy
  checkpoint → apply-approval → analyze → 조건부 H2.5(`analysis_result_review`,
  `stage_guard.review_predicate_required`로 게이트) → dashboard_storyboard`
  순서를 배선. `--dry-run`이 새 단계를 모두 표시하며, H2.5가 이번 run에서
  발동할지 여부도 함께 출력한다.
- `tests/test_dependency_preflight.py`: "설치하지 않는다" 가드를 새 설계에
  맞춰 조정 — `subprocess.run`은 `apply_approval` 안에서 정확히 1회만,
  `--apply-approval` 뒤에서만 도달 가능해야 하고, 기본(플래그 없는) preflight
  경로는 여전히 설치하지 않는다.
- 검증: pytest 64 passed, 17 subtests passed. scratch run에서 skip_install/
  install-success/install-failed/empty-missing 경로를 실제 네트워크 설치 없이
  스모크 테스트, `--dry-run`으로 새 단계 순서 노출 확인.

### 커밋 7 — qa/validate.py 확장: routing/dependency/domain 게이트 (eae5673)

- §9 술어를 `_review_predicate_required()`로 독립 재계산 —
  `method_route.json`의 `review_predicate`나 에이전트 플래그는 신뢰하지 않는다.
  `checkpoint_lineage_checks()`가 이 술어에 따라 `analysis_result_review`를
  `analysis_strategy`와 `dashboard_storyboard` 사이에 동적으로 요구하므로 기존
  lineage BLOCK(질문/답변 누락, provenance, 일괄 승인, 산출물 순서)이 H2.5에도
  그대로 적용된다.
- legacy 경계(spec §15 명시): QA의 `analysis_result_review` 요구는
  `outputs/method_route.json`이 있는 run(v1 routing run)에만 적용한다. routing
  도입 이전 fixture는 BLOCK 수가 그대로 유지된다. 런타임 가드(stage_guard·hook)는
  이 경계 없이 무조건 적용하므로 신규 run이 이 경계를 우회 경로로 쓸 수 없다.
- `method_route_and_dependency_checks`: schema/registry 존재 BLOCK,
  downgrade-only route WARN, predictive에 `data_condition_evidence` 없으면
  BLOCK, dependency allowlist BLOCK, install provenance BLOCK
  (`approval.answer_id`가 `maps_to.dependency_decision=install`인 유효한
  `analysis_strategy` 답변과 연결돼야 함).
- `approval_target_lock_checks`: sha256 승인 잠금을 QA가 독립 재검증(상향/
  미기록 변경 → BLOCK, 사유 기록된 강등은 허용).
- `domain_readiness_checks`: spec §8.5 재계산, 기록값-재계산 불일치 BLOCK,
  insufficient에서 확정 표현 BLOCK. `domain_forbidden_claims_checks`: intake의
  명시 금지 문구가 visible text에 나오면 BLOCK(`allowed_when`은 사람 검토
  메모일 뿐 자동 우회 아님). `statistical_overclaim_checks`: p-value/상관계수 +
  단정 표현 조합만 WARN(부정문은 `SAFE_FORBIDDEN_CONTEXT_TERMS`로 스킵).
- 검증: pytest 64 passed, 17 subtests passed. legacy fixture 3종 BLOCK 수
  변화 없음(1/2/2), 각 +1 WARN(신규 `method_route.json` 부재 안내). statistical
  route + H2.5 미승인 + dependency_plan 없음 조합의 positive smoke에서 신규
  BLOCK이 의도대로 발동함을 확인.

### 커밋 8 — 테스트 커버리지 + 사용자 문서 + CHANGELOG 마감 (이 커밋)

- 신규 `tests/test_expert_routing.py`: 15개 `TestCase` 클래스, 44 test
  methods(39 subtests)로 커밋 5~7의 신규 함수를 커버 — `stage_guard.py`의
  §9 술어/도메인 readiness/`effective_stage_requirements`/승인 잠금/analyze
  진입 차단, `dik_checkpoint_hook.py`의 install 명령 게이트(allowlist·체인
  명령·blanket extra·hyphen 오탐 방지·provenance 누락)와 domain-pack write
  타깃/`bash_write_destinations`, `dependency_preflight.py`의
  `downgrade_method_route`와 `apply_approval`(skip_install e2e,
  `subprocess.run` 스텁으로 install 성공/실패 양쪽), `qa/validate.py`의
  routing/dependency/domain 신규 게이트 전부 — 특히
  `stage_guard.compute_domain_readiness`와 `qa._compute_domain_readiness`가
  같은 입력에서 항상 같은 결과를 내는지 확인하는 교차-구현 일치 테스트를
  포함한다. 모든 fixture는 `tempfile.TemporaryDirectory`만 사용하고
  `runs/`에는 아무것도 남기지 않는다.
- 문서: `README.md`에 분석 깊이 route 6종 + 조건부 1차 결과 확인 + 설치 승인
  + 도메인 전문가 확인을 사용자 표현으로 요약하는 절을 추가. `GUIDE.md`에
  설치 승인 선택 기준, 조건부 "1차 결과 확인" 단계가 언제 나타나는지, 도메인
  전문가 확인 정보가 왜 필요한지 설명을 추가. `AGENTS.md`에 새 운영 규칙
  5개(method_route.json 필수 산출물, 설치는 승인 후 wrapper만, §9 술어는
  재계산만 신뢰, domains/ 자동 수정 금지, 강등/상향 비대칭)를 추가.
  `skills/run-pipeline/SKILL.md`의 단계 순서를 route 생성 → preflight →
  승인 반영 → 조건부 H2.5 흐름으로 갱신.
- `docs/specs/expert-guided-analysis-routing-checklist.md`: 커밋 2~8에서
  실제로 구현된 항목만 `[x]`로 반영(§1/§4~§10/§15/§16/§17 대부분). §2(분석
  전략 문서), §3(domain expert intelligence 문서), §11~§14(대표 run
  검증·routing/domain/regression 시나리오는 코드로 확인됐으나 실제 run
  산출물로는 미검증)는 대부분 미체크로 유지 — 정확성을 완결성보다 우선했다.
- 검증: `python3 -m pytest tests/ -q` → 108 passed, 56 subtests passed
  (기존 64/17 + 신규 44/39, 회귀 없음). `py_compile`
  qa/validate.py·stage_guard.py·dik_checkpoint_hook.py·dependency_preflight.py
  OK. `bash -n scripts/run_codex_pipeline.sh` OK. `git diff --check` clean.
  legacy fixture(`sbiz-store-depth-v2-20260705`) 재검증 BLOCK 1건 유지.
  wrapper `--dry-run --fresh`로 새 단계 순서와 H2.5 미발동 판정을 확인 후
  scratch run 디렉터리 삭제.
