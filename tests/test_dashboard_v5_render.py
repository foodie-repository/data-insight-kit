"""Real-browser rendering tests for dashboard freeform v5."""

from __future__ import annotations

from copy import deepcopy
import json

import pytest

from dashboard_v5.compiler import compile_dashboard
from tests.test_dashboard_v5_compiler import KIT_ROOT, write_v5_fixture
from tests.v5_fixtures import (
    minimal_chart_spec_v51,
    minimal_dashboard_data_v5,
    minimal_dashboard_data_v51,
    minimal_layout_v5,
    minimal_layout_v51,
)


def _placement(order: int, span: int = 12, height: str = "auto") -> dict:
    return {
        "desktop": {
            "order": order,
            "column_start": 1,
            "span": span,
            "height": height,
        },
        "mobile": {"order": order, "span": 12, "height": height},
    }


@pytest.fixture
def render_page(tmp_path):
    from dashboard_v5.browser_qa import _launch_chromium_with_fallback

    try:
        from playwright.sync_api import sync_playwright
    except ImportError:
        pytest.skip("playwright 미설치")
    with sync_playwright() as playwright:
        try:
            browser, _browser_label = _launch_chromium_with_fallback(
                playwright.chromium
            )
        except Exception as exc:
            pytest.skip(f"chromium 실행 불가: {exc}")
        pages = []

        def factory(
            layout: dict | None = None,
            data: dict | None = None,
            chart_spec: dict | None = None,
            viewport: tuple[int, int] = (1440, 1000),
        ):
            case_dir = tmp_path / f"case-{len(pages)}"
            paths = write_v5_fixture(case_dir, data=data)
            if layout is not None:
                paths.layout.write_text(json.dumps(layout), encoding="utf-8")
            if chart_spec is not None:
                paths.chart_spec.write_text(json.dumps(chart_spec), encoding="utf-8")
            output = case_dir / "dashboard.html"
            compile_dashboard(*paths, output_path=output, kit_root=KIT_ROOT)
            page = browser.new_page(
                viewport={"width": viewport[0], "height": viewport[1]}
            )
            page.goto(output.as_uri())
            page.wait_for_function(
                "Object.keys(window.__DIK_ECHARTS__ || {}).length > 0"
            )
            pages.append(page)
            return page

        yield factory
        for page in pages:
            page.close()
        browser.close()


@pytest.fixture
def browser_qa_ready():
    from dashboard_v5.browser_qa import _launch_chromium_with_fallback

    try:
        from playwright.sync_api import sync_playwright
    except ImportError:
        pytest.skip("playwright 미설치")
    with sync_playwright() as playwright:
        try:
            browser, _browser_label = _launch_chromium_with_fallback(
                playwright.chromium
            )
        except Exception as exc:
            pytest.skip(f"chromium 실행 불가: {exc}")
        browser.close()


def interactive_layout() -> dict:
    layout = minimal_layout_v5()
    chart = next(item for item in layout["components"] if item["kind"] == "chart")
    chart["interactions"] = [
        "tooltip",
        "legend_toggle",
        "data_zoom",
        "local_filter",
        "reset",
    ]
    chart["render_options"]["legend"] = "top"
    layout["components"].insert(
        3,
        {
            "id": "controls",
            "kind": "control_bar",
            "role": "navigation",
            "renderer": "svg_css",
            "data_refs": ["c1"],
            "placement": _placement(4),
            "interactions": [
                "legend_toggle",
                "data_zoom",
                "local_filter",
                "reset",
            ],
            "render_options": {},
        },
    )
    for order, component in enumerate(layout["components"], start=1):
        component["placement"]["desktop"]["order"] = order
        component["placement"]["mobile"]["order"] = order
    return layout


def table_layout_and_data() -> tuple[dict, dict]:
    layout = deepcopy(minimal_layout_v5())
    data = deepcopy(minimal_dashboard_data_v5())
    data["panels"][0]["table"] = {
        "granularity": "aggregated",
        "row_limit": 2,
        "columns": [
            {"name": "항목", "type": "category"},
            {"name": "건수", "type": "number", "unit": "건"},
        ],
        "rows": [["A", 10], ["B", 20]],
    }
    layout["components"].insert(
        -1,
        {
            "id": "detail-table",
            "kind": "table",
            "role": "evidence",
            "renderer": "svg_css",
            "data_refs": ["p1"],
            "placement": _placement(5),
            "interactions": [],
            "render_options": {},
        },
    )
    for order, component in enumerate(layout["components"], start=1):
        component["placement"]["desktop"]["order"] = order
        component["placement"]["mobile"]["order"] = order
    return layout, data


def test_desktop_role_hierarchy_and_all_component_refs(render_page):
    page = render_page()
    assert page.locator('[data-component-id="hero-chart"]').count() == 1
    assert (
        page.locator('[data-role="hero"]').evaluate(
            "e => getComputedStyle(e).gridColumnEnd"
        )
        == "span 8"
    )
    assert page.locator("[data-component-id]").count() == len(
        minimal_layout_v5()["components"]
    )
    hero = page.locator('[data-component-id="hero-chart"]').bounding_box()
    support = page.locator('[data-component-id="insight"]').bounding_box()
    assert hero["y"] == pytest.approx(support["y"], abs=1)
    assert hero["x"] + hero["width"] <= support["x"] + 1
    story_grid = page.locator('[data-component-id="insight"] .story-grid')
    assert story_grid.bounding_box()["height"] >= support["height"] * 0.8


def test_mobile_uses_explicit_order_without_page_overflow(render_page):
    page = render_page(viewport=(390, 844))
    orders = page.locator("[data-component-id]").evaluate_all(
        "els => els.map(e => +getComputedStyle(e).order)"
    )
    assert orders == sorted(orders)
    assert page.evaluate("document.documentElement.scrollWidth <= innerWidth")


@pytest.mark.parametrize("viewport", [(736, 1000), (320, 800)])
def test_v51_compact_and_narrow_reflow_without_page_overflow(render_page, viewport):
    page = render_page(
        layout=minimal_layout_v51(),
        data=minimal_dashboard_data_v51(),
        chart_spec=minimal_chart_spec_v51(),
        viewport=viewport,
    )

    assert page.evaluate("document.documentElement.scrollWidth <= innerWidth")
    assert page.locator('[data-component-id="hero-chart"]').bounding_box()[
        "width"
    ] <= viewport[0]
    if viewport[0] == 320:
        columns = page.locator('[data-component-id="kpis"] .kpi-grid').evaluate(
            "e => getComputedStyle(e).gridTemplateColumns.split(' ').length"
        )
        assert columns == 1


def test_v51_narrow_table_fallback_replaces_chart_canvas(render_page):
    chart_spec = minimal_chart_spec_v51()
    chart_spec["charts"][0]["visual_contract"][
        "mobile_strategy"
    ] = "table_fallback"
    page = render_page(
        layout=minimal_layout_v51(),
        data=minimal_dashboard_data_v51(),
        chart_spec=chart_spec,
        viewport=(320, 800),
    )
    component = page.locator('[data-component-id="hero-chart"]')

    assert component.get_attribute("data-fallback-active") == "true"
    assert component.locator(".chart-host").is_hidden()
    assert component.locator(".chart-fallback-table").is_visible()
    assert component.locator(".chart-fallback-table").get_by_text(
        "B", exact=True
    ).is_visible()


def test_v51_narrow_top_n_keeps_chart_and_shows_full_detail_table(render_page):
    chart_spec = minimal_chart_spec_v51()
    data = minimal_dashboard_data_v51()
    visual = chart_spec["charts"][0]["visual_contract"]
    visual["mobile_strategy"] = "top_n_with_detail"
    visual["data_sufficiency"]["observed_points"] = 12
    categories = [f"항목 {index:02d}" for index in range(12)]
    chart = data["panels"][0]["charts"][0]
    chart["encoding"]["x"]["values"] = categories
    chart["encoding"]["series"][0]["values"] = list(range(12))
    page = render_page(
        layout=minimal_layout_v51(),
        data=data,
        chart_spec=chart_spec,
        viewport=(320, 800),
    )
    component = page.locator('[data-component-id="hero-chart"]')

    assert component.locator(".chart-host").is_visible()
    assert component.locator(".chart-fallback-table").is_visible()
    assert component.locator(".chart-fallback-table tbody tr").count() == 12
    assert page.evaluate(
        "window.__DIK_ECHARTS__['hero-chart'].getOption().xAxis[0].data.length"
    ) == 8


def test_v51_empty_hide_removes_component_without_filler_card(render_page):
    layout = minimal_layout_v51()
    data = minimal_dashboard_data_v51()
    kpi_component = next(
        item for item in layout["components"] if item["kind"] == "kpi_group"
    )
    kpi_component["empty_behavior"] = "hide"
    data["kpis"][0]["value"] = ""

    page = render_page(
        layout=layout,
        data=data,
        chart_spec=minimal_chart_spec_v51(),
    )

    assert page.locator('[data-component-id="kpis"]').count() == 0
    assert page.locator(".kpi-card").count() == 0


def test_components_render_contract_data_and_accessible_summary(render_page):
    page = render_page()
    assert page.locator('[data-component-id="header"]').get_by_text(
        "v5 fixture"
    ).is_visible()
    assert page.locator('[data-component-id="kpis"]').get_by_text(
        "전체 건수"
    ).is_visible()
    assert "30" in page.locator('[data-component-id="kpis"]').text_content()
    assert page.locator('[data-component-id="insight"]').get_by_text(
        "B 20건"
    ).is_visible()
    assert "source.csv" in page.locator(
        '[data-component-id="source"]'
    ).text_content()
    assert "A: 10" in page.locator(
        '[data-component-id="hero-chart"] .sr-only'
    ).text_content()
    assert page.locator("[data-component-id][aria-labelledby]").count() == len(
        minimal_layout_v5()["components"]
    )


def test_wide_layout_uses_16_by_9_canvas_and_compact_source_footer(render_page):
    page = render_page(viewport=(1920, 1080))
    root = page.locator("#dashboard-root")
    source = page.locator('[data-component-id="source"]')

    assert root.bounding_box()["width"] == pytest.approx(1720, abs=1)
    assert source.bounding_box()["height"] < 120
    assert source.evaluate("e => getComputedStyle(e).boxShadow") == "none"


def test_units_header_story_labels_and_source_use_reader_facing_copy(render_page):
    data = deepcopy(minimal_dashboard_data_v5())
    data["meta"]["period"] = "2026-07-14"
    page = render_page(data=data)
    header = page.locator('[data-component-id="header"]')
    chart = page.locator('[data-component-id="hero-chart"]')
    insight = page.locator('[data-component-id="insight"]')
    source = page.locator('[data-component-id="source"]')

    assert "분석 기준 2026-07-14" in header.text_content()
    assert "데이터 기준" not in header.text_content()
    assert "(단위: 건)" in chart.text_content()
    assert "단위 건" not in chart.text_content()
    assert insight.get_by_text("현재", exact=True).is_visible()
    assert insight.get_by_text("확인 기준", exact=True).is_visible()
    assert source.get_by_text("source.csv", exact=True).is_visible()
    assert "input/source.csv" not in source.text_content()
    assert source.locator(".source-ref").get_attribute("title") == "input/source.csv"


def test_v51_chart_unit_is_not_duplicated_when_desc_already_contains_it(render_page):
    page = render_page(
        layout=minimal_layout_v51(),
        data=minimal_dashboard_data_v51(),
        chart_spec=minimal_chart_spec_v51(),
    )
    chart_text = page.locator('[data-component-id="hero-chart"]').text_content()

    assert chart_text.count("(단위: 건)") == 1


def test_table_uses_local_horizontal_scroll_container(render_page):
    layout, data = table_layout_and_data()
    page = render_page(layout=layout, data=data)
    table = page.locator('[data-component-id="detail-table"]')
    assert table.get_by_role("columnheader", name="항목").is_visible()
    assert table.get_by_role("cell", name="B").is_visible()
    assert table.locator(".table-scroll").evaluate(
        "e => getComputedStyle(e).overflowX"
    ) == "auto"


def test_zoom_filter_and_legend_have_visible_state_and_reset(render_page):
    page = render_page(interactive_layout())
    reset = page.get_by_role("button", name="보기 초기화")
    assert reset.is_visible()
    state = page.get_by_role("status")
    assert "전체" in state.text_content()
    local_filter = page.get_by_role("combobox", name="로컬 항목 필터")
    local_filter.select_option("A")
    assert "A" in state.text_content()
    page.evaluate(
        "window.__DIK_ECHARTS__['hero-chart'].dispatchAction({type:'dataZoom',start:20,end:80})"
    )
    assert "선택 항목" in state.text_content()
    page.evaluate(
        "window.__DIK_ECHARTS__['hero-chart'].dispatchAction({type:'legendUnSelect',name:'건수'})"
    )
    assert "계열 0/1" in state.text_content()
    reset.click()
    assert "전체" in state.text_content()


def test_controls_have_keyboard_focus_and_accessible_name(render_page):
    page = render_page(interactive_layout())
    page.keyboard.press("Tab")
    assert page.evaluate("document.activeElement.matches('button,select')")
    assert page.evaluate(
        "document.activeElement.getAttribute('aria-label') || "
        "document.activeElement.textContent.trim()"
    )


@pytest.fixture
def valid_v5_html(tmp_path):
    paths = write_v5_fixture(tmp_path / "valid")
    output = tmp_path / "valid" / "dashboard.html"
    compile_dashboard(*paths, output_path=output, kit_root=KIT_ROOT)
    return output


def test_browser_qa_launcher_uses_cached_executable_after_default_failure(
    monkeypatch, tmp_path
):
    import dashboard_v5.browser_qa as browser_qa

    executable = tmp_path / "chrome-headless-shell"
    executable.write_text("fixture", encoding="utf-8")
    executable.chmod(0o755)
    monkeypatch.setattr(
        browser_qa,
        "_browser_executable_candidates",
        lambda: [executable],
        raising=False,
    )

    sentinel = object()

    class FakeChromium:
        def __init__(self):
            self.calls = []

        def launch(self, **kwargs):
            self.calls.append(kwargs)
            if not kwargs:
                raise RuntimeError("bundled browser missing")
            return sentinel

    chromium = FakeChromium()
    launcher = getattr(browser_qa, "_launch_chromium_with_fallback", None)
    assert callable(launcher), "v5 browser QA fallback launcher is missing"
    browser, label = launcher(chromium)

    assert browser is sentinel
    assert chromium.calls == [{}, {"executable_path": str(executable)}]
    assert str(executable) in label


def test_chart_visual_gate_blocks_legend_plot_overlap_and_canvas_clipping():
    import dashboard_v5.browser_qa as browser_qa

    metrics = {
        "chartVisuals": [
            {
                "id": "overlap-chart",
                "canvas": {"left": 0, "top": 0, "right": 320, "bottom": 220},
                "plot": {"left": 40, "top": 40, "right": 290, "bottom": 190},
                "legend": {"left": 250, "top": 80, "right": 315, "bottom": 110},
            },
            {
                "id": "clipped-chart",
                "canvas": {"left": 0, "top": 0, "right": 320, "bottom": 220},
                "plot": {"left": 40, "top": 40, "right": 250, "bottom": 190},
                "legend": {"left": 280, "top": 80, "right": 340, "bottom": 110},
            },
        ]
    }

    blocks = browser_qa._chart_visual_blockers("desktop", metrics)

    assert "desktop chart legend overlaps plot: overlap-chart" in blocks
    assert "desktop chart legend clipped by canvas: clipped-chart" in blocks


def test_chart_visual_gate_uses_scroll_legend_viewport_not_full_content_bounds():
    import dashboard_v5.browser_qa as browser_qa

    metrics = {
        "chartVisuals": [
            {
                "id": "scroll-legend-chart",
                "canvas": {"left": 0, "top": 0, "right": 320, "bottom": 220},
                "plot": {"left": 40, "top": 30, "right": 250, "bottom": 160},
                "legend": {"left": 24, "top": 190, "right": 1800, "bottom": 215},
                "legendViewport": {
                    "left": 24,
                    "top": 190,
                    "right": 296,
                    "bottom": 215,
                },
            }
        ]
    }

    assert browser_qa._chart_visual_blockers("mobile", metrics) == []


def test_chart_visual_gate_accepts_legend_outside_plot_inside_canvas():
    import dashboard_v5.browser_qa as browser_qa

    metrics = {
        "chartVisuals": [
            {
                "id": "clean-chart",
                "canvas": {"left": 0, "top": 0, "right": 320, "bottom": 220},
                "plot": {"left": 40, "top": 40, "right": 230, "bottom": 190},
                "legend": {"left": 250, "top": 80, "right": 315, "bottom": 110},
            }
        ]
    }

    assert browser_qa._chart_visual_blockers("desktop", metrics) == []


def test_chart_visual_gate_blocks_overlapping_or_clipped_stacked_plots():
    import dashboard_v5.browser_qa as browser_qa

    metrics = {
        "chartVisuals": [
            {
                "id": "stacked-panels",
                "canvas": {"left": 0, "top": 0, "right": 320, "bottom": 220},
                "plots": [
                    {"left": 40, "top": 30, "right": 296, "bottom": 130},
                    {"left": 40, "top": 120, "right": 340, "bottom": 215},
                ],
                "legend": None,
            }
        ]
    }

    blocks = browser_qa._chart_visual_blockers("mobile", metrics)

    assert "mobile chart plots overlap: stacked-panels" in blocks
    assert "mobile chart plot clipped by canvas: stacked-panels" in blocks


def test_browser_qa_writes_all_release_screenshots_and_reports_no_blocks(
    valid_v5_html, tmp_path, browser_qa_ready
):
    from dashboard_v5.browser_qa import run_browser_qa

    blocks, _warns = run_browser_qa(
        valid_v5_html,
        minimal_layout_v5(),
        minimal_dashboard_data_v5(),
        tmp_path,
    )
    assert blocks == []
    for viewport_name in ("desktop", "compact", "mobile", "narrow"):
        assert (tmp_path / f"qa_render_{viewport_name}.png").exists()


def test_v51_browser_qa_blocks_until_matching_eyes_on_review(
    tmp_path, browser_qa_ready
):
    from dashboard_v5.browser_qa import run_browser_qa
    from dashboard_v5.visual_review import record_visual_review

    outputs = tmp_path / "v51-review"
    paths = write_v5_fixture(outputs, data=minimal_dashboard_data_v51())
    chart_spec = minimal_chart_spec_v51()
    chart_spec["charts"][0]["visual_contract"][
        "mobile_strategy"
    ] = "table_fallback"
    layout = minimal_layout_v51()
    data = minimal_dashboard_data_v51()
    paths.chart_spec.write_text(json.dumps(chart_spec), encoding="utf-8")
    paths.layout.write_text(json.dumps(layout), encoding="utf-8")
    output = outputs / "dashboard.html"
    compile_dashboard(*paths, output_path=output, kit_root=KIT_ROOT)

    first_blocks, _first_warns = run_browser_qa(output, layout, data, outputs)

    assert any("visual review is not complete" in issue for issue in first_blocks)
    assert (outputs / "visual_review.json").exists()
    record_visual_review(
        outputs,
        status="pass",
        reviewer_role="orchestrator",
        reviewed_at="2026-07-17T12:00:00+09:00",
        observations={
            "copy_clarity": ["범위·기간·단위가 읽힌다."],
            "information_hierarchy": ["요약 다음에 근거가 배치된다."],
            "color_meaning": ["단일 측정값은 한 색으로 표현된다."],
            "scale_integrity": ["막대가 0 기준선을 사용한다."],
            "labels_legends": ["축 라벨이 plot과 겹치지 않는다."],
            "spacing_density": ["네 화면에서 잘림이 없다."],
        },
    )

    second_blocks, _second_warns = run_browser_qa(output, layout, data, outputs)

    assert second_blocks == []


def test_browser_qa_blocks_console_error_empty_chart_and_overflow(
    valid_v5_html, tmp_path, browser_qa_ready
):
    from dashboard_v5.browser_qa import run_browser_qa

    broken = tmp_path / "broken.html"
    injection = (
        '<style>[data-kind="chart"]{width:200vw}.chart-host{display:none}</style>'
        '<script>console.error("qa-probe")</script>'
    )
    broken.write_text(
        valid_v5_html.read_text().replace("</body>", injection + "</body>"),
        encoding="utf-8",
    )
    blocks, _warns = run_browser_qa(
        broken,
        minimal_layout_v5(),
        minimal_dashboard_data_v5(),
        tmp_path,
    )
    assert any("console" in issue for issue in blocks)
    assert any("0 size" in issue or "empty chart" in issue for issue in blocks)
    assert any("overflow" in issue for issue in blocks)


def test_browser_qa_blocks_http_request(valid_v5_html, tmp_path, browser_qa_ready):
    from dashboard_v5.browser_qa import run_browser_qa

    broken = tmp_path / "remote.html"
    injection = '<img src="https://example.invalid/a.png" alt="probe">'
    broken.write_text(
        valid_v5_html.read_text().replace("</body>", injection + "</body>"),
        encoding="utf-8",
    )
    blocks, _warns = run_browser_qa(
        broken,
        minimal_layout_v5(),
        minimal_dashboard_data_v5(),
        tmp_path,
    )
    assert any("network request" in issue for issue in blocks)
