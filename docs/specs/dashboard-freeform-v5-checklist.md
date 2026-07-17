# Dashboard Freeform v5 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 승인된 `dashboard_layout.json`을 로컬 ECharts 6.1.0과 SVG/CSS 컴포넌트로 결정적으로 조립하면서 legacy/v4 렌더를 그대로 보존하는 v5 대시보드 경로를 만든다.

**Architecture:** `analyze`가 `chart_spec.json`과 v5 layout 초안을 만들고 `dashboard_storyboard`가 layout hash+revision을 잠근다. 신규 `dashboard_v5` Python 패키지가 schema·교차계약·ECharts option·compiler를 분리해 담당하며, canonical v5 template에 승인된 JSON과 vendored bundle을 주입한다. `qa/validate.py`는 renderer를 명시적으로 선택하고 v5 정적·compile·browser 결과만 집계하며, v5 실패를 v4로 강등하지 않는다.

**Tech Stack:** Python 3.11+, JSON Schema Draft 2020-12, Apache ECharts 6.1.0(로컬 vendored bundle), HTML/CSS/JavaScript, Playwright, pytest/unittest 호환 테스트.

## Global Constraints

- 단일 원천은 `docs/specs/dashboard-freeform-v5.md`; 구현 판단이 바뀌면 spec을 먼저 고친다.
- 현재 브랜치 `codex/dashboard-freeform-v5`에서 작업하고 push하지 않는다.
- 모든 커밋 직전에 정확히 `cd data-insight-kit && python3 -m pytest tests/ -q`가 green이어야 한다.
- `runs/*`와 실제 사용자 데이터·스크린샷은 커밋하지 않는다.
- checkpoint 답변은 실제 사용자 메시지만 `scripts/apply_checkpoint_answer.py`로 기록한다. 에이전트가 승인 답변을 대신 만들지 않는다.
- 정지점은 질문·근거 원문을 먼저 보여준 턴에서 끝내고, 다음 턴에서 선택을 받는다.
- 대시보드 정지점 전달 전 `outputs/qa_render_desktop.png`와 `outputs/qa_render_mobile.png`를 직접 열어 관찰 결과를 보고한다.
- v5 contract인데 layout이 없거나 invalid이면 BLOCK한다. legacy/v4로 자동 강등하지 않는다.
- 에이전트 raw HTML·CSS·JavaScript·ECharts option 주입과 CDN/원격 font를 금지한다.
- ECharts bundle은 로컬 `echarts-visualize/node_modules/echarts/dist/echarts.min.js`의 6.1.0 파일을 사용하며 sha256은 `b66b25aeb4df84e33199dc21694014d336d222cbd9deb0e5a7c14bd6aa0d0fd0`이다.
- v5.0 filter는 chart encoding 안의 local 표시 필터만 허용한다. KPI·분모의 브라우저 재계산과 전역 cross-filter는 하지 않는다.
- screenshot pixel hash는 비교하지 않는다. DOM 구조·표시 값·layout revision을 검증한다.

## Implementation Record (2026-07-14)

| Task | commit | verification |
|---|---|---|
| 1 승인 기준선 | `3205610` | 181 passed, 12 skipped, 128 subtests passed |
| 2 layout contract | `430bb93` | 202 passed, 12 skipped, 128 subtests passed |
| 3 approval lock | `f1e372a` | 207 passed, 12 skipped, 128 subtests passed |
| 4 ECharts mapper | `d4d0296` | 223 passed, 12 skipped, 128 subtests passed |
| 5 compiler | `1f8c6ea` | 228 passed, 12 skipped, 128 subtests passed |
| 6 responsive components | `0905025` | 229 passed, 18 skipped, 128 subtests passed; actual Chromium 6 passed |
| 7 browser QA | `46dca81` | 231 passed, 21 skipped, 128 subtests passed; actual Chromium 62 passed, 5 subtests passed |
| 8 pipeline routing | `2df64da` | 236 passed, 21 skipped, 128 subtests passed |

Task 9까지의 기본 전체 테스트는 sandbox에서 Chromium 권한이 없는 browser test를
skip한다. Task 6·7은 macOS Playwright browser 경로를 명시한 실제 Chromium
실행으로 별도 green을 확인했다.

## File Structure

| 경로 | 책임 |
|---|---|
| `schemas/dashboard_layout.schema.json` | v5 layout 단독 JSON Schema |
| `dashboard_v5/contract.py` | renderer 선택, schema 및 chart/layout/data 교차검증 |
| `dashboard_v5/echarts_options.py` | dashboard chart encoding → 안전한 ECharts option |
| `dashboard_v5/compiler.py` | canonical template 주입, hash manifest, output 쓰기 |
| `dashboard_v5/browser_qa.py` | v5 전용 desktop/mobile Playwright 검사와 screenshot |
| `scripts/render_dashboard_v5.py` | compiler CLI만 담당하는 얇은 entrypoint |
| `templates/dashboard_v5.html` | v5 canonical DOM/CSS/interaction runtime |
| `templates/vendor/*` | ECharts 6.1.0 bundle, Apache-2.0 license, checksum manifest |
| `tests/v5_fixtures.py` | schema/compiler/browser 공용 최소 v5 fixture |
| `tests/test_dashboard_v5_contract.py` | schema·routing·approval lock 단위 테스트 |
| `tests/test_dashboard_v5_compiler.py` | option·compiler·security·manifest 단위 테스트 |
| `tests/test_dashboard_v5_render.py` | desktop/mobile DOM·interaction·접근성 회귀 테스트 |
| `qa/validate.py` | 기존 QA orchestration과 v5 issue 집계만 담당 |

기존 `templates/dashboard.html`은 legacy/v4 회귀 기준으로 유지하며 v5 코드를 넣지 않는다.

---

### Task 1: 승인 문서와 구현 체크리스트 기준선

**Files:**
- Modify: `.gitignore`
- Modify: `docs/specs/dashboard-freeform-v5-kickoff-notes.md`
- Modify: `docs/specs/dashboard-freeform-v5.md`
- Create: `docs/specs/dashboard-freeform-v5-checklist.md`

**Interfaces:**
- Consumes: 사용자 답변 `설계 승인`, kickoff F-a~F-e, D1~D3.
- Produces: 이후 모든 task가 참조하는 승인 spec과 checkbox 실행 기록.

- [x] **Step 1: 문서 상태와 무시 경계 확인**

Run from repository root:

```bash
git diff --check
git status --short
git check-ignore -v .superpowers/brainstorm/45888-1784034284/content/d4-spec-review-evidence-v2.html
```

Expected: whitespace 오류 없음, 승인 문서 2개와 checklist가 변경/신규로 보이고 `.superpowers/`는 root `.gitignore`에 의해 무시된다.

- [x] **Step 2: 전체 테스트 실행**

Run:

```bash
cd data-insight-kit && python3 -m pytest tests/ -q
```

Expected: 현재 기준 `181 passed, 12 skipped, 128 subtests passed` 이상이며 failure 0.

- [x] **Step 3: runs 제외와 staged 범위 확인**

Run from repository root:

```bash
git add .gitignore data-insight-kit/docs/specs/dashboard-freeform-v5-kickoff-notes.md data-insight-kit/docs/specs/dashboard-freeform-v5.md data-insight-kit/docs/specs/dashboard-freeform-v5-checklist.md
git diff --cached --name-only
git diff --cached --name-only -- 'data-insight-kit/runs/*'
```

Expected: 첫 출력은 위 4개 파일만, 두 번째 출력은 비어 있다.

- [x] **Step 4: 문서 기준선 커밋**

```bash
git commit -m "docs: approve dashboard freeform v5 design"
```

Expected: commit 성공. push하지 않는다.

---

### Task 2: v5 layout schema와 명시적 renderer routing

**Files:**
- Create: `schemas/dashboard_layout.schema.json`
- Create: `dashboard_v5/__init__.py`
- Create: `dashboard_v5/contract.py`
- Create: `tests/v5_fixtures.py`
- Create: `tests/test_dashboard_v5_contract.py`
- Modify: `schemas/chart_spec.schema.json`
- Modify: `schemas/dashboard_data.schema.json`

**Interfaces:**
- Consumes: `dict` 형태의 chart spec, layout, dashboard data.
- Produces: `select_renderer(chart_spec, data, layout) -> Literal["legacy", "v4", "v5"]`, `validate_layout(layout) -> list[str]`, `validate_v5_cross_contract(chart_spec, layout, data) -> list[str]`.

- [x] **Step 1: 공용 fixture와 실패 테스트 작성**

`tests/v5_fixtures.py`에 다음 factory를 만든다. 반환값은 호출마다 `deepcopy` 가능한 새 dict여야 한다.

```python
def _placement(order: int, span: int = 12, height: str = "auto") -> dict:
    return {
        "desktop": {"order": order, "column_start": 1, "span": span, "height": height},
        "mobile": {"order": order, "span": 12, "height": height},
    }

def minimal_layout_v5() -> dict:
    return {
        "schema_version": "data-insight-kit.dashboard_layout.v1",
        "run_id": "v5-fixture",
        "layout_version": 5,
        "revision": 1,
        "generated_at": "2026-07-14T00:00:00Z",
        "profile_purpose": "analyst_workspace",
        "design_rationale": {
            "primary_question": "어느 항목이 큰가",
            "hierarchy_reason": "비교 차트를 가장 크게 본다",
            "mobile_reading_order_reason": "요약 뒤에 근거를 읽는다",
        },
        "grid": {"columns": 12, "gap": "md", "max_width": "wide"},
        "components": [
            {"id": "header", "kind": "header", "role": "navigation", "renderer": "svg_css", "data_refs": ["meta"], "placement": _placement(1), "interactions": [], "render_options": {}},
            {"id": "kpis", "kind": "kpi_group", "role": "summary", "renderer": "svg_css", "data_refs": ["k1"], "placement": _placement(2), "interactions": [], "render_options": {}},
            {"id": "hero-chart", "kind": "chart", "role": "hero", "renderer": "echarts", "data_refs": ["c1"], "placement": _placement(3, 8, "xl"), "interactions": ["tooltip"], "render_options": {"orientation": "vertical", "legend": "none", "label_density": "standard"}},
            {"id": "insight", "kind": "insight", "role": "support", "renderer": "svg_css", "data_refs": ["p1"], "placement": _placement(4, 4, "xl"), "interactions": [], "render_options": {}},
            {"id": "source", "kind": "source_note", "role": "evidence", "renderer": "svg_css", "data_refs": ["src1"], "placement": _placement(5), "interactions": [], "render_options": {}},
        ],
    }

def minimal_chart_spec_v5() -> dict:
    return {
        "meta": {"run_id": "v5-fixture", "generated_at": "2026-07-14T00:00:00Z", "mode": "directed", "audience": "analyst", "domain": "test"},
        "semantic_profile_ref": "outputs/01_profile.md",
        "dashboard_design": {"selected_profile": "analyst_workspace", "density": "standard", "navigation": "none", "rationale": "비교 중심", "alternatives_considered": [], "contract_version": "v5"},
        "charts": [{
            "id": "c1",
            "question": "어느 항목이 큰가",
            "method": "ranking",
            "grain": {"row_meaning": "항목별 집계", "time_grain": None, "entity_grain": "item"},
            "data_requirements": {"measures": ["count"], "dimensions": ["item"], "time_columns": [], "filters": [], "sample_policy": None},
            "calculation": {"source_ref": "src1", "sql": "SELECT item, count(*) AS count FROM source GROUP BY item", "metric_definition": "항목별 건수", "unit": "건", "denominator": None},
            "chart": {"type": "bar", "why_this_chart": "항목 크기 비교", "encoding": {"x": "item", "y": "count", "color": None, "size": None, "series": None}},
            "insight": {"finding": "B가 크다", "evidence": "20건", "limit": "테스트 fixture"},
            "dashboard_mapping": {"panel_id": "p1", "chart_id": "c1", "priority": 1, "uses_kpi_ids": ["k1"], "surface": "primary"},
        }],
    }

def minimal_dashboard_data_v5() -> dict:
    return {
        "meta": {"title": "v5 fixture", "domain": "test", "audience": "analyst", "mode": "directed", "generated_at": "2026-07-14T00:00:00Z", "language": "ko", "row_count": 30, "dashboard_profile": "analyst_workspace", "dashboard_profile_contract": "v5"},
        "sources": [{"id": "src1", "type": "file", "ref": "input/source.csv", "snapshot_at": "2026-07-14T00:00:00Z", "sample_policy": {"sampled": False, "n": 30}}],
        "kpis": [{"id": "k1", "label": "전체 건수", "value": 30, "unit": "건", "kind": "absolute", "status": "neutral"}],
        "panels": [{
            "id": "p1", "title": "항목 비교",
            "story": {"now": {"value": "B 20건", "desc": "가장 크다"}, "why": {"value": "차이 10건", "desc": "A보다 크다"}, "so": {"value": "B 우선", "desc": "먼저 확인한다"}, "act": {"value": "원자료 확인", "desc": "상세 근거를 본다"}},
            "charts": [{"id": "c1", "type": "bar", "title": "어느 항목이 큰가", "desc": "항목별 건수", "encoding": {"x": {"type": "category", "label": "항목", "values": ["A", "B"]}, "series": [{"label": "건수", "unit": "건", "values": [10, 20]}], "stack": "none"}}],
            "surface": "primary",
        }],
    }
```

최소 layout의 component는 `header(meta)`, `kpi_group(k1)`, `chart(c1)`, `insight(p1)`, `source_note(src1)` 다섯 개다. desktop order는 1~5, mobile order는 1~5이며 chart placement는 desktop `span=8`, mobile `span=12`다.

`tests/test_dashboard_v5_contract.py`에 정확히 다음 동작을 먼저 고정한다.

```python
def test_select_renderer_requires_explicit_triple_v5_contract():
    assert select_renderer(minimal_chart_spec_v5(), minimal_dashboard_data_v5(), minimal_layout_v5()) == "v5"

def test_v5_without_layout_fails_closed():
    with pytest.raises(ContractError, match="v5.*dashboard_layout"):
        select_renderer(minimal_chart_spec_v5(), minimal_dashboard_data_v5(), None)

def test_legacy_and_v4_routes_stay_unchanged():
    chart_spec = minimal_chart_spec_v5()
    data = minimal_dashboard_data_v5()
    chart_spec["dashboard_design"].pop("contract_version")
    data["meta"].pop("dashboard_profile_contract")
    assert select_renderer(chart_spec, data, None) == "legacy"
    chart_spec["dashboard_design"]["contract_version"] = "v4"
    data["meta"]["dashboard_profile_contract"] = "v4"
    assert select_renderer(chart_spec, data, None) == "v4"

def test_layout_rejects_duplicate_component_id_and_mobile_order():
    layout = minimal_layout_v5()
    layout["components"].append(deepcopy(layout["components"][-1]))
    issues = validate_layout(layout)
    assert any("component id" in issue for issue in issues)
    assert any("mobile order" in issue for issue in issues)

def test_cross_contract_rejects_missing_chart_reference():
    layout = minimal_layout_v5()
    layout["components"][2]["data_refs"] = ["missing-chart"]
    assert any("missing-chart" in issue for issue in validate_v5_cross_contract(
        minimal_chart_spec_v5(), layout, minimal_dashboard_data_v5()
    ))
```

- [x] **Step 2: targeted test가 실패하는지 확인**

```bash
cd data-insight-kit && python3 -m pytest tests/test_dashboard_v5_contract.py -q
```

Expected: `ModuleNotFoundError: dashboard_v5` 또는 미정의 함수로 FAIL.

- [x] **Step 3: schema와 contract API 구현**

`dashboard_v5/contract.py`의 공개 API를 다음으로 고정한다.

```python
from typing import Literal

RendererMode = Literal["legacy", "v4", "v5"]

class ContractError(ValueError):
    pass

def select_renderer(chart_spec: dict, data: dict, layout: dict | None) -> RendererMode:
    chart_contract = ((chart_spec.get("dashboard_design") or {}).get("contract_version"))
    data_contract = ((data.get("meta") or {}).get("dashboard_profile_contract"))
    if chart_contract != data_contract:
        raise ContractError(f"chart/data renderer contract mismatch: {chart_contract!r} != {data_contract!r}")
    if chart_contract == "v5":
        if layout is None:
            raise ContractError("v5 contract requires dashboard_layout.json")
        if layout.get("layout_version") != 5:
            raise ContractError("v5 contract requires layout_version=5")
        return "v5"
    if layout is not None:
        raise ContractError("legacy/v4 contract cannot include dashboard_layout.json")
    return "v4" if chart_contract == "v4" else "legacy"
```

`validate_layout`은 JSON Schema 오류에 더해 다음 7개 결정적 오류를 문자열로 반환한다: component id 중복, desktop/mobile order 중복, `column_start+span-1>12`, mobile `span!=12`, kind/renderer 불일치, hero 2개 이상, support span이 hero span보다 큼.

`validate_v5_cross_contract`은 run id, profile, contract version, chart id, KPI id, panel story/table, source id를 각각 index해 모든 `data_refs`를 검사한다. primary chart는 정확히 1회, 모든 KPI는 정확히 1회 참조되어야 한다.

두 기존 schema의 `contract_version`/`dashboard_profile_contract` enum만 `["v4", "v5"]`로 확장하고 required 목록은 바꾸지 않는다.

- [x] **Step 4: targeted와 전체 테스트**

```bash
cd data-insight-kit && python3 -m pytest tests/test_dashboard_v5_contract.py -q
cd data-insight-kit && python3 -m pytest tests/ -q
```

Expected: targeted PASS, 전체 failure 0.

- [x] **Step 5: 커밋**

```bash
git add data-insight-kit/dashboard_v5 data-insight-kit/schemas/dashboard_layout.schema.json data-insight-kit/schemas/chart_spec.schema.json data-insight-kit/schemas/dashboard_data.schema.json data-insight-kit/tests/v5_fixtures.py data-insight-kit/tests/test_dashboard_v5_contract.py
git commit -m "feat: add v5 dashboard layout contract"
```

---

### Task 3: storyboard layout hash·revision 승인 잠금

**Files:**
- Modify: `schemas/checkpoint_question.schema.json`
- Modify: `scripts/checkpoint_gate.py`
- Modify: `scripts/stage_guard.py`
- Modify: `qa/validate.py`
- Modify: `tests/test_checkpoint_gate_routing.py`
- Modify: `tests/test_pipeline_guards.py`
- Modify: `tests/test_dashboard_v5_contract.py`

**Interfaces:**
- Consumes: `outputs/dashboard_layout.json`, dashboard_storyboard 질문·실제 사용자 답변.
- Produces: `approval_targets.dashboard_layout{path,sha256,revision,created_at}`, `dashboard_layout_lock_issues(run, answer) -> list[str]`.

- [x] **Step 1: 승인 target 실패 테스트 작성**

다음 helper와 세 테스트를 추가한다.

```python
def _write_layout_lock_fixture(tmp_path):
    run = tmp_path / "runs" / "layout-lock"
    checkpoints = run / "outputs" / "checkpoints"
    checkpoints.mkdir(parents=True)
    layout_path = run / "outputs" / "dashboard_layout.json"
    layout_path.write_text(json.dumps(minimal_layout_v5()), encoding="utf-8")
    target = {"path": str(layout_path), "sha256": sha256_file(layout_path), "revision": 1, "created_at": "2026-07-14T00:00:00Z"}
    question_path = checkpoints / "03_dashboard_storyboard_question.json"
    question_path.write_text(json.dumps({"approval_targets": {"dashboard_layout": target}}), encoding="utf-8")
    answer = {"question_ref": {"path": str(question_path)}}
    return run, layout_path, question_path, answer

def test_storyboard_question_locks_layout_hash_and_revision(tmp_path):
    run, layout_path, _question_path, answer = _write_layout_lock_fixture(tmp_path)
    target = approval_targets_for(run, "dashboard_storyboard")["dashboard_layout"]
    assert target["sha256"] == sha256_file(run / "outputs/dashboard_layout.json")
    assert target["revision"] == 1

def test_visualize_guard_rejects_layout_changed_after_storyboard_approval(tmp_path):
    run, layout_path, _question_path, answer = _write_layout_lock_fixture(tmp_path)
    layout = json.loads(layout_path.read_text())
    layout["revision"] = 2
    layout_path.write_text(json.dumps(layout), encoding="utf-8")
    assert any("재승인" in issue for issue in dashboard_layout_lock_issues(run, answer))

def test_qa_independently_blocks_layout_hash_mismatch(tmp_path):
    run, layout_path, _question_path, _answer = _write_layout_lock_fixture(tmp_path)
    layout = json.loads(layout_path.read_text())
    layout["components"][2]["placement"]["desktop"]["span"] = 12
    layout_path.write_text(json.dumps(layout), encoding="utf-8")
    assert any("재승인" in issue for issue in qa_dashboard_layout_lock_issues(run, answer))
```

테스트의 승인 fixture는 `scripts/apply_checkpoint_answer.py`가 만드는 v3 형태를 그대로 모사하되, 실제 smoke용 `runs/*`에는 쓰지 않는다.

- [x] **Step 2: targeted test 실패 확인**

```bash
cd data-insight-kit && python3 -m pytest tests/test_checkpoint_gate_routing.py tests/test_pipeline_guards.py tests/test_dashboard_v5_contract.py -q
```

Expected: dashboard_layout approval target 또는 lock 함수 미정의로 FAIL.

- [x] **Step 3: checkpoint target과 stage guard 구현**

`checkpoint_gate.py`의 target map을 checkpoint별로 바꾼다.

```python
APPROVAL_TARGET_FILES = {
    "analysis_strategy": {
        "method_route": ("outputs", "method_route.json"),
        "dependency_plan": ("input", "dependency_plan.json"),
    },
    "dashboard_storyboard": {
        "dashboard_layout": ("outputs", "dashboard_layout.json"),
    },
}

def approval_targets_for(run: Path, checkpoint_id: str) -> dict[str, dict[str, Any]]:
    targets = {}
    for key, (folder, name) in APPROVAL_TARGET_FILES.get(checkpoint_id, {}).items():
        path = run / folder / name
        if not path.exists():
            continue
        document = load_json(path)
        target = {"path": rel(path), "sha256": stage_guard.sha256_file(path), "created_at": document.get("generated_at") or document.get("created_at")}
        if key == "dashboard_layout":
            target["revision"] = document.get("revision")
        targets[key] = target
    return targets
```

질문 생성은 analysis strategy와 dashboard storyboard 각각 자기 target만 넣는다. checkpoint schema에는 `dashboard_layout` 전용 def를 추가해 `revision >= 1`을 필수로 한다.

`stage_guard.dashboard_layout_lock_issues`는 답변이 가리키는 storyboard 질문을 읽고 현재 layout의 path/hash/revision을 비교한다. layout 없음, hash 변경, revision 변경은 모두 재승인 오류다. 이 함수는 `visualize`, `qa`, `communicate` 진입에서 호출한다.

`qa/validate.py`는 stage guard 함수를 호출하지 않고
`qa_dashboard_layout_lock_issues(run: Path, answer: dict) -> list[str]`에서 같은 세 비교를 독립
구현하고, 반환 문자열을 `block()`으로 집계한다.

- [x] **Step 4: targeted와 전체 테스트**

```bash
cd data-insight-kit && python3 -m pytest tests/test_checkpoint_gate_routing.py tests/test_pipeline_guards.py tests/test_dashboard_v5_contract.py -q
cd data-insight-kit && python3 -m pytest tests/ -q
```

Expected: failure 0.

- [x] **Step 5: 커밋**

```bash
git add data-insight-kit/schemas/checkpoint_question.schema.json data-insight-kit/scripts/checkpoint_gate.py data-insight-kit/scripts/stage_guard.py data-insight-kit/qa/validate.py data-insight-kit/tests/test_checkpoint_gate_routing.py data-insight-kit/tests/test_pipeline_guards.py data-insight-kit/tests/test_dashboard_v5_contract.py
git commit -m "feat: lock v5 layout at storyboard approval"
```

---

### Task 4: ECharts 6.1.0 vendor와 안전 option mapper

**Files:**
- Create: `templates/vendor/echarts.min.js`
- Create: `templates/vendor/LICENSE.echarts.txt`
- Create: `templates/vendor/manifest.json`
- Create: `dashboard_v5/echarts_options.py`
- Create: `tests/test_dashboard_v5_compiler.py`

**Interfaces:**
- Consumes: 단일 `dashboard_data.panels[].charts[]`, layout `render_options`, `interactions`.
- Produces: `build_echarts_option(chart: dict, render_options: dict, interactions: list[str]) -> dict`.

- [x] **Step 1: mapper와 vendor 실패 테스트 작성**

```python
def chart_fixture(chart_type: str) -> dict:
    category = {"x": {"type": "category", "label": "항목", "values": ["A", "B"]}, "series": [{"label": "값", "unit": "건", "values": [10, 20]}], "stack": "none"}
    encodings = {
        "line": category,
        "area": category,
        "bar": category,
        "stacked_bar": {**category, "stack": "stacked"},
        "histogram": {"x": {"label": "값", "unit": "건"}, "bin_inclusion": "[lo,hi)", "bins": [{"range": [0, 10], "count": 3}, {"range": [10, 20], "count": 5}]},
        "scatter": {"x": {"label": "x", "unit": "점"}, "y": {"label": "y", "unit": "점"}, "points": [{"x": 1, "y": 2}, {"x": 2, "y": 3}]},
        "heatmap": {"x": {"label": "x", "values": ["A"]}, "y": {"label": "y", "values": ["B"]}, "value": {"label": "값", "unit": "건"}, "cells": [{"x": "A", "y": "B", "value": 4}]},
        "boxplot": {"x": {"label": "그룹"}, "y": {"label": "값", "unit": "점"}, "boxes": [{"label": "A", "min": 1, "q1": 2, "median": 3, "q3": 4, "max": 5}]},
        "waterfall": {"x": {"label": "단계"}, "y": {"label": "값", "unit": "건"}, "steps": [{"label": "시작", "value": 10, "kind": "start"}, {"label": "증가", "value": 3, "kind": "increase"}, {"label": "합계", "value": 13, "kind": "total"}]},
        "slope": {"x": {"label": "시점", "start_label": "전", "end_label": "후"}, "y": {"label": "값", "unit": "건"}, "series": [{"label": "A", "start": 10, "end": 15}]},
    }
    return {"id": f"{chart_type}-chart", "type": chart_type, "title": chart_type, "desc": None, "encoding": deepcopy(encodings[chart_type])}

@pytest.mark.parametrize("chart_type,series_type", [
    ("line", "line"), ("area", "line"), ("bar", "bar"),
    ("stacked_bar", "bar"), ("histogram", "bar"),
    ("scatter", "scatter"), ("heatmap", "heatmap"),
    ("boxplot", "boxplot"), ("waterfall", "bar"), ("slope", "line"),
])
def test_all_chart_types_map_to_pinned_echarts_series(chart_type, series_type):
    option = build_echarts_option(chart_fixture(chart_type), {}, ["tooltip"])
    assert option["series"][0]["type"] == series_type
    assert option["aria"]["enabled"] is True

def test_mapper_rejects_unknown_option_and_interaction():
    with pytest.raises(OptionError, match="render option"):
        build_echarts_option(chart_fixture("bar"), {"raw_js": "alert(1)"}, [])
    with pytest.raises(OptionError, match="interaction"):
        build_echarts_option(chart_fixture("bar"), {}, ["cross_filter"])

def test_vendor_manifest_matches_local_bundle():
    manifest = json.loads((KIT_ROOT / "templates/vendor/manifest.json").read_text())
    assert manifest["version"] == "6.1.0"
    assert manifest["sha256"] == sha256_file(KIT_ROOT / "templates/vendor/echarts.min.js")
    assert manifest["sha256"] == "b66b25aeb4df84e33199dc21694014d336d222cbd9deb0e5a7c14bd6aa0d0fd0"
```

- [x] **Step 2: targeted test 실패 확인**

```bash
cd data-insight-kit && python3 -m pytest tests/test_dashboard_v5_compiler.py -q
```

Expected: mapper module 또는 vendor manifest 없음으로 FAIL.

- [x] **Step 3: pinned vendor 복사와 manifest 생성**

Run from repository root:

```bash
cp echarts-visualize/node_modules/echarts/dist/echarts.min.js data-insight-kit/templates/vendor/echarts.min.js
cp echarts-visualize/node_modules/echarts/LICENSE data-insight-kit/templates/vendor/LICENSE.echarts.txt
shasum -a 256 data-insight-kit/templates/vendor/echarts.min.js
```

Expected sha256: `b66b25aeb4df84e33199dc21694014d336d222cbd9deb0e5a7c14bd6aa0d0fd0`.

`manifest.json`의 전체 내용:

```json
{
  "name": "Apache ECharts",
  "version": "6.1.0",
  "license": "Apache-2.0",
  "file": "echarts.min.js",
  "sha256": "b66b25aeb4df84e33199dc21694014d336d222cbd9deb0e5a7c14bd6aa0d0fd0"
}
```

- [x] **Step 4: allowlist mapper 구현**

`dashboard_v5/echarts_options.py`는 다음 상수와 예외를 공개한다.

```python
ALLOWED_RENDER_OPTIONS = {"orientation", "legend", "label_density"}
ALLOWED_INTERACTIONS = {"tooltip", "legend_toggle", "data_zoom", "local_filter", "reset"}

class OptionError(ValueError):
    pass
```

`build_echarts_option`은 먼저 unknown key를 거부하고 공통 option을 만든다.

```python
option = {
    "animation": False,
    "aria": {"enabled": True, "decal": {"show": True}},
    "textStyle": {"fontFamily": "system-ui, sans-serif"},
    "tooltip": {"show": "tooltip" in interactions, "trigger": "axis"},
    "legend": {"show": render_options.get("legend", "top") != "none"},
    "grid": {"left": 48, "right": 24, "top": 48, "bottom": 44, "containLabel": True},
}
```

category chart는 `encoding.x.values`와 `encoding.series`를 그대로 사용하고, stack은 `stacked|stacked_100`일 때만 동일 stack key를 준다. histogram은 `bins[].range`를 `"lo–hi"` label로 만든다. scatter는 `[x,y]`, heatmap은 `[x_index,y_index,value]`, boxplot은 `[min,q1,median,q3,max]`, waterfall은 transparent bridge+visible delta, slope는 start/end 두 category line으로 변환한다. `data_zoom`이 있을 때만 inside+slider를 추가한다. 숫자를 재집계하거나 보간하지 않는다.

- [x] **Step 5: targeted와 전체 테스트**

```bash
cd data-insight-kit && python3 -m pytest tests/test_dashboard_v5_compiler.py -q
cd data-insight-kit && python3 -m pytest tests/ -q
```

Expected: 10 chart type parameter case 전부 PASS, 전체 failure 0.

- [x] **Step 6: 커밋**

```bash
git add data-insight-kit/templates/vendor data-insight-kit/dashboard_v5/echarts_options.py data-insight-kit/tests/test_dashboard_v5_compiler.py
git commit -m "feat: vendor echarts and map v5 chart options"
```

---

### Task 5: 결정적 v5 compiler와 canonical template

**Files:**
- Create: `dashboard_v5/compiler.py`
- Create: `scripts/render_dashboard_v5.py`
- Create: `templates/dashboard_v5.html`
- Modify: `tests/test_dashboard_v5_compiler.py`

**Interfaces:**
- Consumes: 승인된 chart spec/layout/data 파일과 kit root.
- Produces: `compile_dashboard(chart_spec_path, layout_path, data_path, output_path, kit_root) -> dict` manifest, `outputs/dashboard.html`, `outputs/dashboard_build_manifest.json`.

- [x] **Step 1: compiler 실패 테스트 작성**

```python
class FixturePaths(NamedTuple):
    chart_spec: Path
    layout: Path
    data: Path

def write_v5_fixture(root: Path, data: dict | None = None) -> FixturePaths:
    root.mkdir(parents=True, exist_ok=True)
    paths = FixturePaths(root / "chart_spec.json", root / "dashboard_layout.json", root / "dashboard_data.json")
    paths.chart_spec.write_text(json.dumps(minimal_chart_spec_v5()), encoding="utf-8")
    paths.layout.write_text(json.dumps(minimal_layout_v5()), encoding="utf-8")
    paths.data.write_text(json.dumps(data or minimal_dashboard_data_v5()), encoding="utf-8")
    return paths

def compile_fixture(root: Path, data: dict | None = None) -> str:
    paths = write_v5_fixture(root, data=data)
    output = root / "dashboard.html"
    compile_dashboard(*paths, output_path=output, kit_root=KIT_ROOT)
    return output.read_text(encoding="utf-8")

def extract_embedded_constant(html: str, name: str) -> dict:
    match = re.search(rf"const {name} = (.+);\\n", html)
    assert match is not None
    return json.loads(match.group(1))

def test_compile_writes_self_contained_html_and_hash_manifest(tmp_path):
    paths = write_v5_fixture(tmp_path)
    manifest = compile_dashboard(*paths, output_path=tmp_path / "dashboard.html", kit_root=KIT_ROOT)
    html = (tmp_path / "dashboard.html").read_text()
    assert "{PLACE_" not in html
    assert "echarts.init" in html
    assert "https://" not in html and "http://" not in html
    assert manifest["layout_revision"] == 1
    assert manifest["inputs"]["dashboard_layout"]["sha256"] == sha256_file(paths.layout)

def test_compile_escapes_script_breakout(tmp_path):
    data = minimal_dashboard_data_v5()
    data["meta"]["title"] = "</script><script>alert(1)</script>"
    html = compile_fixture(tmp_path, data=data)
    assert "</script><script>alert(1)" not in html
    assert "\\u003c/script\\u003e" in html

def test_compile_is_structurally_deterministic(tmp_path):
    first = compile_fixture(tmp_path / "a")
    second = compile_fixture(tmp_path / "b")
    assert extract_embedded_constant(first, "LAYOUT") == extract_embedded_constant(second, "LAYOUT")
    assert extract_embedded_constant(first, "OPTIONS_BY_COMPONENT") == extract_embedded_constant(second, "OPTIONS_BY_COMPONENT")
```

- [x] **Step 2: targeted test 실패 확인**

```bash
cd data-insight-kit && python3 -m pytest tests/test_dashboard_v5_compiler.py -q
```

Expected: compiler module 또는 template 없음으로 FAIL.

- [x] **Step 3: compiler 구현**

공개 함수와 JSON escaping을 다음처럼 고정한다.

```python
import hashlib
import json
from pathlib import Path

from dashboard_v5.contract import ContractError, select_renderer, validate_layout, validate_v5_cross_contract
from dashboard_v5.echarts_options import build_echarts_option

def read_json(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))

def sha256_file(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()

def build_options_by_component(layout: dict, data: dict) -> dict[str, dict]:
    charts = {
        chart["id"]: chart
        for panel in data["panels"]
        for chart in panel["charts"]
    }
    result = {}
    for component in layout["components"]:
        if component["kind"] != "chart":
            continue
        chart = charts[component["data_refs"][0]]
        result[component["id"]] = build_echarts_option(
            chart,
            component.get("render_options") or {},
            component.get("interactions") or [],
        )
    return result

def _file_record(path: Path, display_path: str) -> dict:
    return {"path": display_path, "sha256": sha256_file(path)}

def build_manifest(chart_spec_path: Path, layout_path: Path, data_path: Path, kit_root: Path, layout: dict) -> dict:
    return {
        "compiler_version": "dashboard-v5.1",
        "layout_revision": layout["revision"],
        "inputs": {
            "chart_spec": _file_record(chart_spec_path, chart_spec_path.name),
            "dashboard_layout": _file_record(layout_path, layout_path.name),
            "dashboard_data": _file_record(data_path, data_path.name),
        },
        "template": _file_record(kit_root / "templates/dashboard_v5.html", "templates/dashboard_v5.html"),
        "echarts_bundle": _file_record(kit_root / "templates/vendor/echarts.min.js", "templates/vendor/echarts.min.js"),
    }

def _json_for_script(value: object) -> str:
    return json.dumps(value, ensure_ascii=False, separators=(",", ":"), sort_keys=True).replace("<", "\\u003c").replace(">", "\\u003e").replace("&", "\\u0026")

def compile_dashboard(
    chart_spec_path: Path,
    layout_path: Path,
    data_path: Path,
    output_path: Path,
    kit_root: Path,
) -> dict:
    chart_spec = read_json(chart_spec_path)
    layout = read_json(layout_path)
    data = read_json(data_path)
    if select_renderer(chart_spec, data, layout) != "v5":
        raise ContractError("render_dashboard_v5 only accepts the v5 contract")
    issues = validate_layout(layout) + validate_v5_cross_contract(chart_spec, layout, data)
    if issues:
        raise ContractError("; ".join(issues))
    options = build_options_by_component(layout, data)
    template = (kit_root / "templates/dashboard_v5.html").read_text(encoding="utf-8")
    bundle = (kit_root / "templates/vendor/echarts.min.js").read_text(encoding="utf-8")
    rendered = template.replace("{PLACE_ECHARTS_BUNDLE_HERE}", bundle).replace("{PLACE_LAYOUT_HERE}", _json_for_script(layout)).replace("{PLACE_DATA_HERE}", _json_for_script(data)).replace("{PLACE_OPTIONS_HERE}", _json_for_script(options))
    if "{PLACE_" in rendered:
        raise ContractError("v5 template placeholder remains")
    output_path.write_text(rendered, encoding="utf-8")
    manifest = build_manifest(chart_spec_path, layout_path, data_path, kit_root, layout)
    (output_path.parent / "dashboard_build_manifest.json").write_text(json.dumps(manifest, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return manifest
```

manifest는 compiler version `dashboard-v5.1`, layout revision, 3개 input, template, bundle 각각의 상대 path와 sha256을 기록한다. 현재 시각·절대 경로는 넣지 않는다.

- [x] **Step 4: canonical template 최소 DOM 구현**

template은 inline CSS, `#dashboard-root`, JSON 상수 3개, vendored ECharts, runtime 순서로 둔다. runtime은 component를 `placement.desktop.order`로 안정 정렬하고 다음 attribute를 반드시 남긴다.

```javascript
el.dataset.componentId = component.id;
el.dataset.renderer = component.renderer;
el.dataset.dataRef = component.data_refs.join(",");
el.style.setProperty("--desktop-order", component.placement.desktop.order);
el.style.setProperty("--mobile-order", component.placement.mobile.order);
el.style.setProperty("--desktop-span", component.placement.desktop.span);
```

사용자 문자열은 `innerHTML`이 아니라 `textContent`로 삽입한다. `chart` component만 `echarts.init(node, null, {renderer:"canvas"})`와 사전 계산 option을 사용한다. 모든 instance는 `window.__DIK_ECHARTS__`에 component id key로 등록하고 resize listener에서 `instance.resize()`를 호출한다.

- [x] **Step 5: CLI 구현**

`scripts/render_dashboard_v5.py`는 argparse로 `--chart-spec`, `--layout`, `--data`, `--output`을 모두 required로 받고 `compile_dashboard`만 호출한다. 성공 시 output과 manifest 상대 경로를 두 줄 출력하고, `ContractError`면 stderr에 한 줄을 출력한 뒤 exit 2다.

- [x] **Step 6: targeted와 전체 테스트**

```bash
cd data-insight-kit && python3 -m pytest tests/test_dashboard_v5_compiler.py -q
cd data-insight-kit && python3 -m pytest tests/ -q
```

Expected: failure 0.

- [x] **Step 7: 커밋**

```bash
git add data-insight-kit/dashboard_v5/compiler.py data-insight-kit/scripts/render_dashboard_v5.py data-insight-kit/templates/dashboard_v5.html data-insight-kit/tests/test_dashboard_v5_compiler.py
git commit -m "feat: compile approved v5 dashboard layouts"
```

---

### Task 6: 컴포넌트 위계·반응형·상호작용·접근성

**Files:**
- Modify: `templates/dashboard_v5.html`
- Create: `tests/test_dashboard_v5_render.py`
- Modify: `tests/test_dashboard_v5_compiler.py`

**Interfaces:**
- Consumes: compiler가 주입한 `LAYOUT`, `DATA`, `OPTIONS_BY_COMPONENT`.
- Produces: kind별 DOM, local control state/reset, desktop/mobile reading order.

- [x] **Step 1: browser 실패 테스트 작성**

Playwright가 없으면 기존 방식처럼 module-level availability로 skip한다. 설치되어 있으면 다음을 검증한다.

```python
@pytest.fixture
def render_page(tmp_path):
    try:
        from playwright.sync_api import sync_playwright
    except ImportError:
        pytest.skip("playwright 미설치")
    with sync_playwright() as playwright:
        try:
            browser = playwright.chromium.launch()
        except Exception as exc:
            pytest.skip(f"chromium 실행 불가: {exc}")
        pages = []
        def factory(layout: dict | None = None, viewport: tuple[int, int] = (1440, 1000)):
            case_dir = tmp_path / f"case-{len(pages)}"
            paths = write_v5_fixture(case_dir)
            if layout is not None:
                paths.layout.write_text(json.dumps(layout), encoding="utf-8")
            output = case_dir / "dashboard.html"
            compile_dashboard(*paths, output_path=output, kit_root=KIT_ROOT)
            page = browser.new_page(viewport={"width": viewport[0], "height": viewport[1]})
            page.goto(output.as_uri())
            page.wait_for_function("Object.keys(window.__DIK_ECHARTS__ || {}).length > 0")
            pages.append(page)
            return page
        yield factory
        for page in pages:
            page.close()
        browser.close()

def interactive_layout() -> dict:
    layout = minimal_layout_v5()
    chart = next(item for item in layout["components"] if item["kind"] == "chart")
    chart["interactions"] = ["tooltip", "legend_toggle", "data_zoom", "reset"]
    layout["components"].insert(3, {
        "id": "controls", "kind": "control_bar", "role": "navigation", "renderer": "svg_css",
        "data_refs": ["c1"], "placement": _placement(4), "interactions": ["legend_toggle", "data_zoom", "reset"], "render_options": {},
    })
    for order, component in enumerate(layout["components"], start=1):
        component["placement"]["desktop"]["order"] = order
        component["placement"]["mobile"]["order"] = order
    return layout

def test_desktop_role_hierarchy_and_all_component_refs(render_page):
    page = render_page()
    assert page.locator('[data-component-id="hero-chart"]').count() == 1
    assert page.locator('[data-role="hero"]').evaluate("e => getComputedStyle(e).gridColumnEnd") == "span 8"
    assert page.locator('[data-component-id]').count() == len(minimal_layout_v5()["components"])

def test_mobile_uses_explicit_order_without_page_overflow(render_page):
    page = render_page(viewport=(390, 844))
    orders = page.locator('[data-component-id]').evaluate_all("els => els.map(e => +getComputedStyle(e).order)")
    assert orders == sorted(orders)
    assert page.evaluate("document.documentElement.scrollWidth <= innerWidth")

def test_zoom_filter_and_legend_have_visible_state_and_reset(render_page):
    page = render_page(interactive_layout())
    assert page.get_by_role("button", name="보기 초기화").is_visible()
    state = page.get_by_role("status")
    assert "전체" in state.text_content()
    page.get_by_role("button", name="보기 초기화").click()
    assert "전체" in state.text_content()

def test_controls_have_keyboard_focus_and_accessible_name(render_page):
    page = render_page(interactive_layout())
    page.keyboard.press("Tab")
    assert page.evaluate("document.activeElement.matches('button,select')")
    assert page.evaluate("document.activeElement.getAttribute('aria-label') || document.activeElement.textContent.trim()")
```

- [x] **Step 2: targeted test 실패 확인**

```bash
cd data-insight-kit && python3 -m pytest tests/test_dashboard_v5_render.py -q
```

Expected: selector/control/mobile style 누락으로 FAIL 또는 환경상 skip.

- [x] **Step 3: kind별 component와 12-column CSS 구현**

desktop root는 `display:grid; grid-template-columns:repeat(12,minmax(0,1fr))`이고 component는 CSS variable을 사용한다. mobile media query `max-width: 720px`에서 모든 component를 `grid-column:1 / -1; order:var(--mobile-order)`로 바꾸고 KPI 내부만 2열이다.

kind별 출력:

- header: meta title, period, row_count, source snapshot 최신값
- kpi_group: data_refs 순서대로 KPI, v4 trend/comparison 규칙 재사용
- chart: title, desc, unit summary, canvas host, accessible data summary
- insight: panel story now→why→so→act
- table: header/rows, `.table-scroll` 내부 overflow-x만 허용
- source_note: source ref, snapshot_at, sample_policy
- control_bar: 대상 chart의 현재 legend/filter/zoom 상태와 reset button

`data-role`, `data-kind`, `aria-labelledby`를 모든 component에 둔다. chart에는 화면 독자가 읽을 수 있는 숨김 데이터 요약을 연결한다.

- [x] **Step 4: local interaction runtime 구현**

`legendselectchanged`와 `datazoom` 이벤트는 linked control bar의 `[role=status]` text를 갱신한다. reset은 `legendAllSelect`와 `dataZoom {start:0,end:100}` action만 dispatch한다. `local_filter`는 encoding에 이미 있는 series/category의 `selected` 상태만 바꾸며 data/KPI 객체를 수정하지 않는다.

- [x] **Step 5: targeted와 전체 테스트**

```bash
cd data-insight-kit && python3 -m pytest tests/test_dashboard_v5_render.py tests/test_dashboard_v5_compiler.py -q
cd data-insight-kit && python3 -m pytest tests/ -q
```

Expected: Playwright 가능 환경 PASS, 불가 환경은 명시적 skip, 전체 failure 0.

- [x] **Step 6: 커밋**

```bash
git add data-insight-kit/templates/dashboard_v5.html data-insight-kit/tests/test_dashboard_v5_render.py data-insight-kit/tests/test_dashboard_v5_compiler.py
git commit -m "feat: render responsive accessible v5 components"
```

---

### Task 7: v5 browser QA와 screenshot 출고 게이트

**Files:**
- Create: `dashboard_v5/browser_qa.py`
- Modify: `qa/validate.py`
- Modify: `tests/test_dashboard_v5_render.py`
- Modify: `tests/test_pipeline_guards.py`

**Interfaces:**
- Consumes: compiler output HTML, layout, dashboard data, output directory.
- Produces: `run_browser_qa(html_path, layout, data, output_dir) -> tuple[list[str], list[str]]`의 `(blocks, warns)`와 두 screenshot.

- [x] **Step 1: QA 실패 테스트 작성**

```python
@pytest.fixture
def valid_v5_html(tmp_path):
    paths = write_v5_fixture(tmp_path / "valid")
    output = tmp_path / "valid" / "dashboard.html"
    compile_dashboard(*paths, output_path=output, kit_root=KIT_ROOT)
    return output

def test_browser_qa_writes_both_screenshots_and_reports_no_blocks(valid_v5_html, tmp_path):
    blocks, warns = run_browser_qa(valid_v5_html, minimal_layout_v5(), minimal_dashboard_data_v5(), tmp_path)
    assert blocks == []
    assert (tmp_path / "qa_render_desktop.png").exists()
    assert (tmp_path / "qa_render_mobile.png").exists()

def test_browser_qa_blocks_console_error_empty_chart_and_overflow(valid_v5_html, tmp_path):
    broken = tmp_path / "broken.html"
    injection = '<style>[data-kind="chart"]{width:200vw}.chart-host{display:none}</style><script>console.error("qa-probe")</script>'
    broken.write_text(valid_v5_html.read_text().replace("</body>", injection + "</body>"), encoding="utf-8")
    blocks, _warns = run_browser_qa(broken, minimal_layout_v5(), minimal_dashboard_data_v5(), tmp_path)
    assert any("console" in issue for issue in blocks)
    assert any("0 size" in issue or "empty chart" in issue for issue in blocks)
    assert any("overflow" in issue for issue in blocks)

def test_browser_qa_blocks_http_request(valid_v5_html, tmp_path):
    broken = tmp_path / "remote.html"
    injection = '<img src="https://example.invalid/a.png" alt="probe">'
    broken.write_text(valid_v5_html.read_text().replace("</body>", injection + "</body>"), encoding="utf-8")
    blocks, _warns = run_browser_qa(broken, minimal_layout_v5(), minimal_dashboard_data_v5(), tmp_path)
    assert any("network request" in issue for issue in blocks)

def test_validate_does_not_fallback_when_v5_layout_is_missing(monkeypatch, tmp_path):
    calls = []
    monkeypatch.setattr(qa, "render_checks", lambda *args, **kwargs: calls.append("legacy"))
    qa.BLOCKS.clear()
    qa.dispatch_render_checks(
        tmp_path / "dashboard_data.json",
        minimal_dashboard_data_v5(),
        minimal_chart_spec_v5(),
        None,
        KIT_ROOT / "templates/dashboard.html",
    )
    assert calls == []
    assert any("dashboard_layout" in issue for issue in qa.BLOCKS)
```

두 번째 fixture는 template test hook으로 `console.error`, 0×0 chart host, `width:200vw`를 각각 삽입해 세 BLOCK code가 모두 나오는지 검사한다. 세 번째는 image `https://example.invalid/a.png`를 삽입하고 request listener가 차단하는지 검사한다.

- [x] **Step 2: targeted test 실패 확인**

```bash
cd data-insight-kit && python3 -m pytest tests/test_dashboard_v5_render.py tests/test_pipeline_guards.py -q
```

Expected: browser_qa 모듈 또는 v5 dispatcher 없음으로 FAIL.

- [x] **Step 3: 독립 browser QA 구현**

`run_browser_qa`는 desktop `1440×1000`, mobile `390×844`를 각각 새 page로 연다. 각 viewport에서 다음을 수집한다.

```javascript
() => ({
  overflow: document.documentElement.scrollWidth > innerWidth + 1,
  components: Array.from(document.querySelectorAll('[data-component-id]')).map(el => {
    const r = el.getBoundingClientRect();
    return {id: el.dataset.componentId, left:r.left, top:r.top, right:r.right, bottom:r.bottom, width:r.width, height:r.height};
  }),
  chartCount: Object.keys(window.__DIK_ECHARTS__ || {}).length,
  revision: document.documentElement.dataset.layoutRevision
})
```

BLOCK: pageerror/console error, http(s) request, component 0 size, component pair overlap(1px tolerance), viewport overflow, chart component 수와 ECharts instance 수 불일치, revision 불일치, accessible name 없는 control. WARN: hero 면적이 모든 support보다 작음, chart title 48자 초과, body font 11px 미만.

- [x] **Step 4: `qa/validate.py` renderer dispatcher 통합**

CLI에 optional `--layout`을 추가한다. 생략하면 data sibling `dashboard_layout.json`을 찾는다. chart/data contract를 읽어 `select_renderer`를 호출한다. 분기 함수 signature는 다음으로 고정한다.

```python
def dispatch_render_checks(
    data_path: pathlib.Path,
    data: dict,
    chart_spec: dict,
    layout: dict | None,
    legacy_template: pathlib.Path,
) -> None:
    """Select one renderer path; v5 errors never call legacy render_checks."""
```

- legacy/v4: 현행 `render_checks`를 그대로 호출
- v5: static cross-contract → compiler manifest 검사 → `run_browser_qa`
- v5 오류: `block(message)` 후 return; legacy/v4 render 호출 금지

v5 blocks/warns는 기존 전역 `block()`/`warn()`으로 한 번씩 집계한다.

- [x] **Step 5: targeted와 전체 테스트**

```bash
cd data-insight-kit && python3 -m pytest tests/test_dashboard_v5_render.py tests/test_pipeline_guards.py -q
cd data-insight-kit && python3 -m pytest tests/ -q
```

Expected: failure 0, 기존 legacy/v4 render tests 유지.

- [x] **Step 6: 커밋**

```bash
git add data-insight-kit/dashboard_v5/browser_qa.py data-insight-kit/qa/validate.py data-insight-kit/tests/test_dashboard_v5_render.py data-insight-kit/tests/test_pipeline_guards.py
git commit -m "feat: gate v5 dashboards with browser qa"
```

---

### Task 8: pipeline·hook·agent의 v5 layout 경로 연결

**Files:**
- Modify: `scripts/run_codex_pipeline.sh`
- Modify: `scripts/dik_checkpoint_hook.py`
- Modify: `scripts/checkpoint_gate.py`
- Modify: `agents/analyze.md`
- Modify: `agents/visualize.md`
- Modify: `agents/qa.md`
- Modify: `tests/test_pipeline_guards.py`
- Modify: `tests/test_checkpoint_gate_routing.py`

**Interfaces:**
- Consumes: `chart_spec.dashboard_design.contract_version="v5"`.
- Produces: analyze layout draft, storyboard artifact/approval target, visualize compiler call, qa `--layout` call.

- [x] **Step 1: pipeline 경로 실패 테스트 작성**

```python
def test_hook_allows_layout_write_only_after_analysis_strategy_approval(self):
    with tempfile.TemporaryDirectory() as t:
        tmp = Path(t)
        run = self._make_kit(tmp)
        target = "runs/hook-run/outputs/dashboard_layout.json"
        self.assertEqual(self._write(tmp, target, json.dumps(minimal_layout_v5())), "deny")
        answers = [
            self._valid_answer(run, "data_profile", "01_data_profile_question", 1),
            self._valid_answer(run, "analysis_strategy", "02_analysis_strategy_question", 2),
        ]
        (run / "checkpoint_answers.json").write_text(json.dumps({"answers": answers}), encoding="utf-8")
        self.assertEqual(self._write(tmp, target, json.dumps(minimal_layout_v5())), "allow")

def test_hook_denies_v5_dashboard_data_before_storyboard_layout_approval(self):
    with tempfile.TemporaryDirectory() as t:
        tmp = Path(t)
        run = self._make_kit(tmp)
        answers = [
            self._valid_answer(run, "data_profile", "01_data_profile_question", 1),
            self._valid_answer(run, "analysis_strategy", "02_analysis_strategy_question", 2),
        ]
        (run / "checkpoint_answers.json").write_text(json.dumps({"answers": answers}), encoding="utf-8")
        self.assertEqual(self._write(tmp, "runs/hook-run/outputs/dashboard_data.json", "{}"), "deny")

def test_storyboard_chat_handoff_lists_layout_original_path_and_revision(self):
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        run = root / "runs" / "unit-run"
        (run / "outputs").mkdir(parents=True)
        (run / "outputs" / "04_analysis.md").write_text("# 분석 결과\n", encoding="utf-8")
        (run / "outputs" / "chart_spec.json").write_text(json.dumps(minimal_chart_spec_v5()), encoding="utf-8")
        (run / "outputs" / "dashboard_layout.json").write_text(json.dumps(minimal_layout_v5()), encoding="utf-8")
        previous = Path.cwd()
        os.chdir(root)
        try:
            question, question_json, question_md = self.checkpoint_gate.create_question("unit-run", "dashboard_storyboard")
            handoff = self.checkpoint_gate.render_question_for_chat(question, question_json, question_md)
        finally:
            os.chdir(previous)
        self.assertIn("dashboard_layout.json", handoff)
        self.assertIn("revision 1", handoff)
        self.assertIn("hero-chart", handoff)

def test_wrapper_contains_v5_compiler_and_layout_qa_arguments(self):
    script = (KIT_ROOT / "scripts/run_codex_pipeline.sh").read_text(encoding="utf-8")
    self.assertIn("scripts/render_dashboard_v5.py", script)
    self.assertIn('--layout "$RUN/outputs/dashboard_layout.json"', script)
    self.assertIn('--data "$RUN/outputs/dashboard_data.json"', script)
```

첫 테스트는 `outputs/dashboard_layout.json`을 analyze stage 산출물로 분류하고 analysis_strategy 승인 없이는 deny, 승인 후 allow를 기대한다. 두 번째는 storyboard 승인 target hash가 없으면 dashboard_data/dashboard.html 쓰기를 deny한다.

- [x] **Step 2: targeted test 실패 확인**

```bash
cd data-insight-kit && python3 -m pytest tests/test_pipeline_guards.py tests/test_checkpoint_gate_routing.py -q
```

Expected: layout stage mapping 또는 dry-run command 누락으로 FAIL.

- [x] **Step 3: hook과 wrapper 연결**

`dik_checkpoint_hook.py`에 `dashboard_layout.json: "analyze"`를 추가한다. visualize 산출물 쓰기 전 기존 storyboard 답변 검증에 layout lock을 포함한다.

wrapper의 analyze expected outputs에 `dashboard_layout.json`을 v5 조건부로 추가하고, visualize prompt는 raw HTML 주입 대신 다음 CLI를 호출하게 한다.

```bash
python3 scripts/render_dashboard_v5.py --chart-spec "$RUN/outputs/chart_spec.json" --layout "$RUN/outputs/dashboard_layout.json" --data "$RUN/outputs/dashboard_data.json" --output "$RUN/outputs/dashboard.html"
```

QA는 v5일 때 `--layout "$RUN/outputs/dashboard_layout.json"`을 붙인다. legacy/v4 명령은 바꾸지 않는다.

- [x] **Step 4: checkpoint 표시 의무와 agent 지침 갱신**

storyboard `artifacts[]`에 layout path·revision 설명을 추가하고 chat handoff 원문에 component 순서, desktop span, mobile order 표를 넣는다.

- `agents/analyze.md`: chart_spec 뒤 layout draft 작성; profile 목적과 rationale; raw ECharts option 금지
- `agents/visualize.md`: 승인 hash 확인; dashboard_data만 채운 뒤 compiler CLI; template 직접 수정 금지
- `agents/qa.md`: v5 static/compile/browser 순서; screenshot 두 장 직접 검토 필요 문구

- [x] **Step 5: targeted와 전체 테스트**

```bash
cd data-insight-kit && python3 -m pytest tests/test_pipeline_guards.py tests/test_checkpoint_gate_routing.py -q
cd data-insight-kit && python3 -m pytest tests/ -q
```

Expected: failure 0.

- [x] **Step 6: 커밋**

```bash
git add data-insight-kit/scripts/run_codex_pipeline.sh data-insight-kit/scripts/dik_checkpoint_hook.py data-insight-kit/scripts/checkpoint_gate.py data-insight-kit/agents/analyze.md data-insight-kit/agents/visualize.md data-insight-kit/agents/qa.md data-insight-kit/tests/test_pipeline_guards.py data-insight-kit/tests/test_checkpoint_gate_routing.py
git commit -m "feat: route guided pipeline through v5 layouts"
```

---

### Task 9: 계약 문서·보안 회귀·전체 정합 마감

**Files:**
- Modify: `docs/pipeline-contract.md`
- Modify: `docs/dashboard-design-system.md`
- Modify: `README.md`
- Modify: `GUIDE.md`
- Modify: `CHANGELOG.md`
- Modify: `tests/test_dashboard_v5_contract.py`
- Modify: `tests/test_dashboard_v5_compiler.py`
- Modify: `tests/test_dashboard_v5_render.py`
- Modify: `docs/specs/dashboard-freeform-v5-checklist.md`

**Interfaces:**
- Consumes: Task 2~8의 완성 동작.
- Produces: 사용자·agent·QA가 같은 v5 계약을 읽는 문서와 최종 회귀 기준.

- [x] **Step 1: 누락 회귀 테스트를 먼저 추가**

아래 negative matrix를 parameterized test로 고정한다.

| case | expected BLOCK |
|---|---|
| v5 chart contract + v4 data contract | contract mismatch |
| v5 + layout 없음 | layout required |
| v5 layout hash 변경 | storyboard reapproval |
| raw render option key | option allowlist |
| component data_ref 없음 | missing reference |
| external URL 문자열 | remote resource |
| bundle checksum 변경 | vendor checksum |
| mobile span 6 | mobile span must be 12 |
| chart interaction + control 없음 | visible state/reset required |

기존 `test_dashboard_render.py` 전체도 같은 test run에서 실행해 legacy/v4 회귀를 확인한다.

- [x] **Step 2: targeted test 실행**

```bash
cd data-insight-kit && python3 -m pytest tests/test_dashboard_v5_contract.py tests/test_dashboard_v5_compiler.py tests/test_dashboard_v5_render.py tests/test_dashboard_render.py -q
```

Expected: failure가 있으면 문서보다 구현/테스트를 먼저 최소 수정해 green으로 만든다.

실행 결과: 기본 환경 `50 passed, 21 skipped`; macOS Playwright browser 경로를
명시한 실제 Chromium render/legacy 회귀 `21 passed`.

- [x] **Step 3: 단일 원천 문서 갱신**

- pipeline contract 실행 순서에 analyze의 layout draft, storyboard layout approval target, visualize v5 compiler, qa 4단계를 추가
- design system에 role/size hierarchy, ECharts/SVG 분리, safe interaction, mobile reading order 추가
- README/GUIDE에 v5 명령과 legacy/v4/v5 routing 표 추가
- CHANGELOG 진행 상태에 구현 커밋 1~8과 아직 남은 smoke 2건을 정확히 기록
- checklist Task 1~8을 실제 commit hash와 test count로 체크

- [x] **Step 4: 전체 검증**

```bash
cd data-insight-kit && python3 -m pytest tests/ -q
cd data-insight-kit && python3 - <<'PY'
import json
from pathlib import Path
for path in sorted(Path('schemas').glob('*.json')):
    json.loads(path.read_text())
print('schema-json-ok')
PY
git diff --check
git ls-files 'runs/*'
git diff --cached --name-only -- 'runs/*'
```

Expected: 전체 failure 0, `schema-json-ok`, diff 오류 없음, 마지막 두 명령 출력 없음.

실행 결과: `238 passed, 21 skipped, 128 subtests passed`, `schema-json-ok`,
`git diff --check` 통과, tracked/staged `runs/*` 0건.

- [x] **Step 5: 커밋**

```bash
git add data-insight-kit/docs/pipeline-contract.md data-insight-kit/docs/dashboard-design-system.md data-insight-kit/README.md data-insight-kit/GUIDE.md data-insight-kit/CHANGELOG.md data-insight-kit/docs/specs/dashboard-freeform-v5-checklist.md data-insight-kit/tests/test_dashboard_v5_contract.py data-insight-kit/tests/test_dashboard_v5_compiler.py data-insight-kit/tests/test_dashboard_v5_render.py
git commit -m "docs: complete dashboard freeform v5 contract"
```

---

### Task 10: 사용자 참여 smoke 2종과 최종 마감

**Files:**
- Modify after successful smoke only: `CHANGELOG.md`
- Modify after successful smoke only: `docs/specs/dashboard-freeform-v5-checklist.md`
- Never commit: `runs/sbiz-gangnam-v5-freeform-smoke-20260714/**`
- Never commit: `runs/apt-sale-v5-freeform-smoke-20260714/**`

**Interfaces:**
- Consumes: 원천 입력과 실제 사용자 checkpoint 답변.
- Produces: snapshot 자유 레이아웃과 time-series 자유 레이아웃의 QA·눈검토 근거, 최종 CHANGELOG 기록.

- [x] **Step 1: snapshot smoke를 fresh run으로 시작**

Run id: `sbiz-gangnam-v5-freeform-smoke-20260714`.

이전 run의 `dashboard_data.json`, `chart_spec.json`, layout, 보고서를 복사하거나 근거로 쓰지 않는다. 원천 파일 또는 새 input snapshot만 넣고 guided wrapper를 실행한다.

```bash
cd data-insight-kit
bash scripts/run_codex_pipeline.sh sbiz-gangnam-v5-freeform-smoke-20260714 --guided
```

각 checkpoint에서 `checkpoint_gate.py --print-existing` 원문을 먼저 보여주고 턴을 끝낸다. 다음 턴의 실제 사용자 답변만 기록한다.

완료 근거(2026-07-15): `data_profile`, `analysis_strategy`,
`dashboard_storyboard`, `report_outline` 네 checkpoint 모두 실제 사용자 답변과
checkpoint-answer.v3 provenance로 승인되었고 communicate·qa-post까지 진행했다.

- [x] **Step 2: snapshot dashboard 정지점 눈검토**

QA 완료 뒤 다음 두 파일을 직접 연다.

```text
runs/sbiz-gangnam-v5-freeform-smoke-20260714/outputs/qa_render_desktop.png
runs/sbiz-gangnam-v5-freeform-smoke-20260714/outputs/qa_render_mobile.png
```

보고 항목: component 겹침, 잘림, page overflow, hero/support 위계, 문구 직관성, tooltip/control 상태, mobile reading order. 관찰 결과를 보고한 턴에서 끝내고 다음 턴에 사용자 승인을 받는다.

완료 근거(2026-07-15): browser QA BLOCK 0건, WARN 3건. desktop/mobile을
직접 열어 component·범례·축·라벨·plot 겹침과 잘림이 없고, heatmap 범례와
mobile reading order가 분리되어 읽히는 것을 확인했다. 보고서 qa-post는
BLOCK 0건, WARN 2건이다.

- [x] **Step 3: time-series smoke를 fresh run으로 시작**

Run id: `apt-sale-v5-freeform-smoke-20260714`. 이전 run output은 사용하지 않고 원천 시계열 input에서 새로 시작한다.

```bash
cd data-insight-kit
bash scripts/run_codex_pipeline.sh apt-sale-v5-freeform-smoke-20260714 --guided
```

같은 checkpoint·턴 분리·답변 provenance 규칙을 반복한다. ECharts zoom/legend, KPI trend provenance, desktop/mobile hierarchy를 확인한다.

완료 근거(2026-07-17): fresh 원천 25개 구 x 54개월에서 시작해 실제 사용자
답변으로 `data_profile`, `analysis_strategy`, 수정 후 `dashboard_storyboard`,
`report_outline`을 승인했다. 마지막 실제 답변 `보고서 구성 승인`은
`approve_report_outline`·`source=user_chat`·checkpoint-answer.v3 provenance로
기록했고, `communicate`가 standard·mixed·data_only `summary_report.md`를 만든 뒤
qa-post까지 완료했다.

- [x] **Step 4: time-series dashboard 정지점 눈검토**

```text
runs/apt-sale-v5-freeform-smoke-20260714/outputs/qa_render_desktop.png
runs/apt-sale-v5-freeform-smoke-20260714/outputs/qa_render_mobile.png
```

직접 관찰 보고 후 다음 턴에서 실제 사용자 승인을 받는다.

완료 근거(2026-07-17): 사용자가 기존 화면의
`시작월`·`기간 가격`·미확정 가격 단위와 한 축에 겹친 가격·거래량 선을 수정하라고
실제 답변했고, 이를 `revise_chart_mix`로 기록해 이전 storyboard 승인을
무효화했다. 두 참고 문서의 결론형 제목, 명시적 기간·단위, 단위/변동폭이 다른
시계열의 정렬된 분리 패널 원칙을 spec과 QA에 반영했다. 가격은 원천 값 범위,
국내 아파트 거래가격 관행, 사용자의 명시적 확인을 근거로 `만원`으로 표시한다.
revision 2의 browser QA는 desktop/mobile 모두 BLOCK 0이며, 두 screenshot을 직접
열어 component·축·라벨·범례·plot의 겹침과 잘림이 없고 모바일 읽기 순서가
유지됨을 확인했다. 사용자는 다음 턴에서 revision 2를 `탐색형 화면으로 승인`했고,
최종 qa-post 직전에 재생성된 두 screenshot도 다시 직접 열어 같은 결과와 heatmap
축·월 레이블·색 범례 표시를 확인했다. 모바일의 25개 구 변화 비교 범례는 작고
페이지형이지만 plot과 겹치거나 잘리지는 않아 v5.1 개선 후보로 남긴다.

- [x] **Step 5: smoke 마감 문서와 전체 테스트**

두 smoke의 실제 승인·BLOCK 0·WARN 처리·눈검토 관찰을 CHANGELOG와 checklist에만 기록한다. run 파일은 stage하지 않는다.

```bash
cd data-insight-kit && python3 -m pytest tests/ -q
git diff --check
git ls-files 'data-insight-kit/runs/*'
git diff --cached --name-only -- 'data-insight-kit/runs/*'
```

Expected: tests failure 0, diff 오류 없음, 두 runs 명령 출력 없음.

실행 결과(2026-07-17): `270 passed, 23 skipped, 128 subtests passed`,
`git diff --check` 통과, tracked/staged `runs/*` 0건. time-series 최종 browser QA는
`BLOCK 0`, `WARN 3`, qa-post는 `BLOCK 0`, `WARN 2`다.

- [x] **Step 6: 최종 마감 커밋**

```bash
git add data-insight-kit/CHANGELOG.md data-insight-kit/docs/specs/dashboard-freeform-v5-checklist.md
git commit -m "docs: close dashboard freeform v5 smoke"
```

push하지 않는다.

## Self-Review Record

- [x] Spec coverage: spec §1~§13은 Task 2(contract), 3(approval), 4(ECharts), 5(compiler), 6(interaction/responsive), 7(QA), 8(pipeline), 9(docs/regression), 10(smoke)에 각각 대응한다.
- [x] Placeholder scan: 생략형 함수 본문이나 후속 판단에 맡기는 구현 지시 없음.
- [x] Type consistency: `select_renderer`, `validate_layout`, `validate_v5_cross_contract`, `build_echarts_option`, `compile_dashboard`, `run_browser_qa`, `dashboard_layout_lock_issues` 이름과 입력/출력을 task 간 동일하게 사용한다.
- [x] Compatibility: 기존 `templates/dashboard.html` 수정 없음, contract enum만 additive, legacy/v4 browser regression을 Task 9에서 다시 실행한다.
- [x] Safety: v5 missing/invalid layout은 BLOCK, raw code·remote resource 차단, 실제 checkpoint 답변만 허용한다.
- [x] Visual QA: 두 viewport screenshot 생성뿐 아니라 오케스트레이터 직접 열람과 턴 분리 승인을 Task 10에 포함한다.
