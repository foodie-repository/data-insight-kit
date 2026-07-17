"""dashboard.html 실렌더 DOM 회귀 테스트 (dashboard-profile-v4 커밋 3~).

legacy fixture = `meta.dashboard_profile_contract`가 없는 기존 dashboard_data.
v4 레이아웃(E2/E3)이 들어와도 legacy 데이터는 현행 탭 화면과 동일 구조로
렌더되어야 한다 (spec §5.0 렌더 하위 호환). Playwright 미설치/브라우저 실행
불가 환경에서는 skip한다.
"""
from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

KIT_ROOT = Path(__file__).resolve().parents[1]
TEMPLATE = KIT_ROOT / "templates" / "dashboard.html"

try:
    from playwright.sync_api import sync_playwright

    HAVE_PLAYWRIGHT = True
except ImportError:
    HAVE_PLAYWRIGHT = False


def _bar_chart(chart_id: str, title: str = "차트") -> dict:
    return {
        "id": chart_id,
        "type": "bar",
        "title": title,
        "encoding": {
            "x": {"type": "category", "label": "구", "values": ["강남", "서초"]},
            "series": [{"label": "건수", "unit": "건", "values": [10, 20]}],
            "stack": "none",
        },
    }


def legacy_dashboard_data() -> dict:
    """contract 필드 없는 기존 계약 데이터 — 탭 렌더 기준선."""
    return {
        "meta": {
            "title": "레거시 렌더 회귀",
            "domain": "테스트",
            "audience": "mixed",
            "mode": "directed",
            "generated_at": "2026-07-13T00:00:00Z",
            "language": "ko",
            "row_count": 30,
        },
        "sources": [{
            "id": "src1", "type": "file", "ref": "input/a.parquet",
            "snapshot_at": "2026-07-13T00:00:00Z",
            "sample_policy": {"sampled": False, "n": 30},
        }],
        "kpis": [
            {"id": "k1", "label": "총 건수는?", "value": 30, "unit": "건",
             "kind": "absolute", "status": "neutral"},
            {"id": "k2", "label": "전월 대비?", "value": 12, "unit": "건",
             "kind": "absolute", "status": "good",
             "comparison": {"basis": "수도권 평균 대비", "delta": 1.2, "direction": "up"}},
        ],
        "panels": [
            {"id": "p1", "title": "개요", "charts": [_bar_chart("c1"), _bar_chart("c2", "차트 2")]},
            {"id": "p2", "title": "상세", "charts": [_bar_chart("c3", "차트 3")]},
        ],
    }


def render_counts(data: dict, selectors: dict[str, str], viewport=(1280, 900)) -> dict:
    """템플릿에 data를 주입해 실렌더하고 selector별 요소 수를 돌려준다."""
    rendered = TEMPLATE.read_text(encoding="utf-8").replace(
        "{PLACE_DASHBOARD_DATA_HERE}", json.dumps(data, ensure_ascii=False)
    )
    tmp = Path(tempfile.mkdtemp()) / "dashboard.html"
    tmp.write_text(rendered, encoding="utf-8")
    counts: dict[str, int] = {}
    errors: list[str] = []
    with sync_playwright() as p:
        browser = p.chromium.launch()
        page = browser.new_page(viewport={"width": viewport[0], "height": viewport[1]})
        page.on("pageerror", lambda e: errors.append(str(e)))
        page.goto("file://" + str(tmp))
        page.wait_for_timeout(300)
        for name, selector in selectors.items():
            counts[name] = page.eval_on_selector_all(selector, "els=>els.length")
        browser.close()
    counts["pageerrors"] = len(errors)
    return counts


def _provenance(periods):
    return {"source_id": "src1", "time_field": "ym", "periods": list(periods)}


def v4_e1_dashboard_data() -> dict:
    """E1 검증용: k1=trend 스파크, k2=period_delta(good), k3=period_delta(warn)."""
    data = legacy_dashboard_data()
    data["kpis"] = [
        {"id": "k1", "label": "월 추세는?", "value": 123, "unit": "건",
         "kind": "absolute", "status": "neutral", "format": {"precision": 0},
         "trend": {"points": [98, 104, 111, 123], "period_label": "최근 4개월",
                   "provenance": _provenance(["2026-02", "2026-03", "2026-04", "2026-05"])}},
        {"id": "k2", "label": "전월 대비 증가?", "value": 12, "unit": "건",
         "kind": "absolute", "status": "good",
         "comparison": {"kind": "period_delta", "basis": "전월 대비", "delta": 6.5,
                        "direction": "up", "provenance": _provenance(["2026-04", "2026-05"])}},
        {"id": "k3", "label": "주의 지표?", "value": 7, "unit": "건",
         "kind": "absolute", "status": "warn",
         "comparison": {"kind": "period_delta", "basis": "전월 대비", "delta": -2.0,
                        "direction": "down", "provenance": _provenance(["2026-04", "2026-05"])}},
    ]
    return data


E1_COLOR_PROBE_JS = """
() => {
  const probe = (role) => {
    const s = document.createElement('span');
    s.style.color = getComputedStyle(document.documentElement).getPropertyValue('--'+role).trim();
    document.body.appendChild(s);
    return getComputedStyle(s).color;
  };
  const deltas = [...document.querySelectorAll('.kpi-delta-v4')].map(e => getComputedStyle(e).color);
  const values = [...document.querySelectorAll('.kpi-v')].map(e => getComputedStyle(e).color);
  return {deltas, values, good: probe('good'), muted: probe('muted'), ink: probe('ink')};
}
"""


def render_probe(data: dict, selectors: dict[str, str], eval_js: str | None = None) -> dict:
    rendered = TEMPLATE.read_text(encoding="utf-8").replace(
        "{PLACE_DASHBOARD_DATA_HERE}", json.dumps(data, ensure_ascii=False)
    )
    tmp = Path(tempfile.mkdtemp()) / "dashboard.html"
    tmp.write_text(rendered, encoding="utf-8")
    result: dict = {}
    errors: list[str] = []
    with sync_playwright() as p:
        browser = p.chromium.launch()
        page = browser.new_page(viewport={"width": 1280, "height": 900})
        page.on("pageerror", lambda e: errors.append(str(e)))
        page.goto("file://" + str(tmp))
        page.wait_for_timeout(300)
        for name, selector in selectors.items():
            result[name] = page.eval_on_selector_all(selector, "els=>els.length")
        if eval_js:
            result["eval"] = page.evaluate(eval_js)
        browser.close()
    result["pageerrors"] = len(errors)
    return result


@unittest.skipUnless(HAVE_PLAYWRIGHT, "playwright 미설치 — 렌더 회귀 테스트 skip")
class LegacyRenderRegressionTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        try:
            cls.counts = render_counts(
                legacy_dashboard_data(),
                {
                    "tabs": ".tab",
                    "active_chart_svgs": ".panel.active .chart-card svg",
                    "all_svgs": ".panel.active svg",
                    "kpi_values": ".panel.active .kpi-v",
                },
            )
        except Exception as exc:  # 브라우저 실행 불가 환경(샌드박스 등)
            raise unittest.SkipTest(f"chromium 실행 불가: {exc}")

    def test_legacy_data_keeps_tab_layout(self):
        self.assertEqual(self.counts["tabs"], 2)

    def test_chart_card_selector_matches_chart_count(self):
        self.assertEqual(self.counts["active_chart_svgs"], 2)
        # v4 이전 기준선: 아직 스파크 SVG가 없으므로 전체 SVG == 차트 SVG
        self.assertEqual(self.counts["all_svgs"], self.counts["active_chart_svgs"])

    def test_kpis_render_without_v4_fields(self):
        self.assertEqual(self.counts["kpi_values"], 2)
        self.assertEqual(self.counts["pageerrors"], 0)


@unittest.skipUnless(HAVE_PLAYWRIGHT, "playwright 미설치 — 렌더 회귀 테스트 skip")
class V4KpiTileRenderTests(unittest.TestCase):
    """E1: 스파크 SVG는 chart-card 수와 분리, 델타 색은 good/bad만 상태색."""

    @classmethod
    def setUpClass(cls):
        try:
            cls.result = render_probe(
                v4_e1_dashboard_data(),
                {
                    "sparks": ".kpi-spark svg",
                    "active_chart_svgs": ".panel.active .chart-card svg",
                    "all_svgs": ".panel.active svg",
                    "v4_deltas": ".kpi-delta-v4",
                },
                eval_js=E1_COLOR_PROBE_JS,
            )
        except Exception as exc:
            raise unittest.SkipTest(f"chromium 실행 불가: {exc}")

    def test_spark_svg_renders_separately_from_chart_cards(self):
        self.assertEqual(self.result["sparks"], 1)
        self.assertEqual(self.result["active_chart_svgs"], 2)
        self.assertEqual(self.result["all_svgs"], 3)  # 차트 2 + 스파크 1
        self.assertEqual(self.result["pageerrors"], 0)

    def test_period_delta_colors_follow_v4_rule(self):
        ev = self.result["eval"]
        self.assertEqual(self.result["v4_deltas"], 2)
        # k2(status=good) → good색, k3(status=warn) → muted (세 번째 상태색 금지)
        self.assertEqual(ev["deltas"][0], ev["good"])
        self.assertEqual(ev["deltas"][1], ev["muted"])

    def test_kpi_main_values_stay_ink_colored(self):
        ev = self.result["eval"]
        for color in ev["values"]:
            self.assertEqual(color, ev["ink"])


def v4_analyst_dashboard_data() -> dict:
    data = legacy_dashboard_data()
    data["meta"]["dashboard_profile"] = "analyst_workspace"
    data["meta"]["dashboard_profile_contract"] = "v4"
    data["panels"] = [
        {"id": "p1", "title": "개요", "charts": [_bar_chart("c1"), _bar_chart("c2", "차트 2")]},
        {"id": "p2", "title": "비교", "charts": [_bar_chart("c3", "차트 3")]},
        {"id": "p3", "title": "부록", "surface": "appendix", "charts": [_bar_chart("c4", "차트 4")]},
    ]
    return data


def v4_ops_dashboard_data() -> dict:
    data = legacy_dashboard_data()
    data["meta"]["dashboard_profile"] = "operations_monitor"
    data["meta"]["dashboard_profile_contract"] = "v4"
    return data


@unittest.skipUnless(HAVE_PLAYWRIGHT, "playwright 미설치 — 렌더 회귀 테스트 skip")
class V4AnalystSingleScrollTests(unittest.TestCase):
    """E2: contract v4 + analyst → 탭 없이 primary 단일 스크롤, 비-primary 접힘."""

    @classmethod
    def setUpClass(cls):
        try:
            cls.counts = render_probe(
                v4_analyst_dashboard_data(),
                {
                    "tabs": ".tab",
                    "scroll_roots": ".v4-scroll",
                    "primary_sections": ".v4-primary",
                    "demoted": ".v4-demoted",
                    "chart_svgs": ".panel .chart-card svg",
                    "kpi_values": ".panel .kpi-v",
                },
            )
        except Exception as exc:
            raise unittest.SkipTest(f"chromium 실행 불가: {exc}")

    def test_single_scroll_replaces_tabs(self):
        self.assertEqual(self.counts["tabs"], 0)
        self.assertEqual(self.counts["scroll_roots"], 1)
        self.assertEqual(self.counts["primary_sections"], 2)
        self.assertEqual(self.counts["demoted"], 1)
        self.assertEqual(self.counts["pageerrors"], 0)

    def test_all_charts_render_and_kpis_render_once(self):
        self.assertEqual(self.counts["chart_svgs"], 4)
        self.assertEqual(self.counts["kpi_values"], 2)


def v4_e4e5_dashboard_data() -> dict:
    """E4/E5 검증용: 같은 panel에 스몰 멀티플 2개 + 그라데이션 표."""
    data = v4_analyst_dashboard_data()
    data["panels"][0]["charts"] = [
        _bar_chart("c1"),
        dict(_bar_chart("g1", "팀 A"), small_multiple_group="team"),
        dict(_bar_chart("g2", "팀 B"), small_multiple_group="team"),
    ]
    data["panels"][0]["table"] = {
        "granularity": "aggregated",
        "row_limit": 5,
        "columns": [{"name": "구", "type": "string"}, {"name": "건수", "type": "number"}],
        "rows": [["강남", 10], ["서초", 25], ["송파", 40]],
        "cell_gradient": {"value_column_indices": [1], "scale": "column"},
    }
    return data


@unittest.skipUnless(HAVE_PLAYWRIGHT, "playwright 미설치 — 렌더 회귀 테스트 skip")
class V4SmallMultiplesAndGradientTests(unittest.TestCase):
    """E4: sm-grid 공통 그리드, E5: 무채색 셀 그라데이션."""

    @classmethod
    def setUpClass(cls):
        try:
            cls.counts = render_probe(
                v4_e4e5_dashboard_data(),
                {
                    "sm_grids": ".sm-grid",
                    "sm_cards": ".sm-grid .chart-card",
                    "chart_svgs": ".panel .chart-card svg",
                    "grad_cells": "td.grad-cell",
                },
            )
        except Exception as exc:
            raise unittest.SkipTest(f"chromium 실행 불가: {exc}")

    def test_small_multiple_group_renders_as_one_grid(self):
        self.assertEqual(self.counts["sm_grids"], 1)
        self.assertEqual(self.counts["sm_cards"], 2)
        # p1: solo 1 + 그룹 2, p2: 1, p3(접힘): 1 — 전부 DOM에 존재
        self.assertEqual(self.counts["chart_svgs"], 5)
        self.assertEqual(self.counts["pageerrors"], 0)

    def test_gradient_cells_render_on_number_column(self):
        self.assertEqual(self.counts["grad_cells"], 3)


OVERLAP_COUNT_JS = """
() => {
  const blocks = [...document.querySelectorAll('.panel.active .card, .panel.active .kpi, .panel.active .story, .panel.active .actions, .panel.active table.dt')]
    .map(el => { const r = el.getBoundingClientRect(); return {el, l:r.left, r:r.right, t:r.top, b:r.bottom, w:r.width, h:r.height}; })
    .filter(b => b.w > 8 && b.h > 8);
  let overlaps = 0;
  for (let i=0;i<blocks.length;i++) for (let j=i+1;j<blocks.length;j++) {
    const a=blocks[i], c=blocks[j];
    if (a.el.contains(c.el) || c.el.contains(a.el)) continue;
    const ox=Math.min(a.r,c.r)-Math.max(a.l,c.l), oy=Math.min(a.b,c.b)-Math.max(a.t,c.t);
    if (ox>8 && oy>8) overlaps++;
  }
  const fakeRail = getComputedStyle(document.querySelector('.wrap'), '::before').display;
  return {overlaps, fakeRail};
}
"""


def v4_ops_e1_dashboard_data() -> dict:
    """grid blowout 회귀 fixture: ops v4 + E1 스파크 KPI (스파크 140px가
    좁은 상태 스택에서 blowout을 일으키던 조합)."""
    data = v4_ops_dashboard_data()
    data["kpis"] = v4_e1_dashboard_data()["kpis"]
    data["panels"][0]["story"] = {
        "now": {"value": "가격 상승", "desc": "요약"},
        "why": {"value": "저거래", "desc": "요약"},
        "so": {"value": "분리 확인", "desc": "요약"},
        "act": {"value": "상세 검토", "desc": "요약"},
    }
    return data


@unittest.skipUnless(HAVE_PLAYWRIGHT, "playwright 미설치 — 렌더 회귀 테스트 skip")
class V4OpsBlowoutRegressionTests(unittest.TestCase):
    """v4 smoke 발견 회귀: 구형 ops 4열 규칙 특이도 + E1 스파크 → grid blowout."""

    def test_ops_v4_with_sparks_has_no_overlap_and_no_fake_rail(self):
        try:
            result = render_probe(v4_ops_e1_dashboard_data(), {}, eval_js=OVERLAP_COUNT_JS)
        except Exception as exc:
            raise unittest.SkipTest(f"chromium 실행 불가: {exc}")
        self.assertEqual(result["eval"]["overlaps"], 0)
        self.assertEqual(result["eval"]["fakeRail"], "none")
        self.assertEqual(result["pageerrors"], 0)


@unittest.skipUnless(HAVE_PLAYWRIGHT, "playwright 미설치 — 렌더 회귀 테스트 skip")
class V4OperationsRailTests(unittest.TestCase):
    """E3: contract v4 + operations → 레일이 패널 switcher (기존 ACTIVE 재표현)."""

    def test_rail_switches_active_panel_and_survives_mobile(self):
        data = v4_ops_dashboard_data()
        rendered = TEMPLATE.read_text(encoding="utf-8").replace(
            "{PLACE_DASHBOARD_DATA_HERE}", json.dumps(data, ensure_ascii=False)
        )
        tmp = Path(tempfile.mkdtemp()) / "dashboard.html"
        tmp.write_text(rendered, encoding="utf-8")
        try:
            with sync_playwright() as p:
                browser = p.chromium.launch()
                page = browser.new_page(viewport={"width": 1280, "height": 900})
                page.goto("file://" + str(tmp))
                page.wait_for_timeout(300)
                self.assertEqual(page.eval_on_selector_all(".tab", "els=>els.length"), 0)
                self.assertEqual(
                    page.eval_on_selector_all(".v4-rail .rail-item", "els=>els.length"), 2
                )
                active_first = page.evaluate(
                    "[...document.querySelectorAll('.v4-ops-body .panel')].map(e=>e.classList.contains('active'))"
                )
                self.assertEqual(active_first, [True, False])
                page.eval_on_selector_all(".v4-rail .rail-item", "(els)=>els[1].click()")
                page.wait_for_timeout(150)
                active_second = page.evaluate(
                    "[...document.querySelectorAll('.v4-ops-body .panel')].map(e=>e.classList.contains('active'))"
                )
                self.assertEqual(active_second, [False, True])
                # 좁은 화면: 레일 항목은 유지 (CSS가 상단 가로 배치로 강등)
                page.set_viewport_size({"width": 390, "height": 900})
                page.wait_for_timeout(150)
                self.assertEqual(
                    page.eval_on_selector_all(".v4-rail .rail-item", "els=>els.length"), 2
                )
                browser.close()
        except unittest.SkipTest:
            raise
        except Exception as exc:
            raise unittest.SkipTest(f"chromium 실행 불가: {exc}")


if __name__ == "__main__":
    unittest.main()
