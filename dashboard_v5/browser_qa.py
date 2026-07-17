"""Independent real-browser QA for compiled dashboard freeform v5 HTML."""

from __future__ import annotations

import os
import re
from pathlib import Path
from typing import Any

from dashboard_v5.visual_review import (
    ensure_visual_review_draft,
    validate_visual_review,
)


VIEWPORTS = {
    "desktop": {"width": 1440, "height": 1000},
    "compact": {"width": 736, "height": 1000},
    "mobile": {"width": 390, "height": 844},
    "narrow": {"width": 320, "height": 800},
}

METRICS_JS = """
() => {
  const transformedLocalRect = (group, rect) => {
    if (!group || !rect) return null;
    const matrix = group.getComputedTransform() || [1, 0, 0, 1, 0, 0];
    const points = [
      [rect.x, rect.y],
      [rect.x + rect.width, rect.y],
      [rect.x, rect.y + rect.height],
      [rect.x + rect.width, rect.y + rect.height]
    ].map(([x, y]) => ({
      x: matrix[0] * x + matrix[2] * y + matrix[4],
      y: matrix[1] * x + matrix[3] * y + matrix[5]
    }));
    return {
      left: Math.min(...points.map(point => point.x)),
      top: Math.min(...points.map(point => point.y)),
      right: Math.max(...points.map(point => point.x)),
      bottom: Math.max(...points.map(point => point.y))
    };
  };
  const transformedRect = group => transformedLocalRect(
    group,
    group && group.getBoundingRect ? group.getBoundingRect() : null
  );
  const transformedClipRect = group => {
    const clip = group && group.getClipPath ? group.getClipPath() : null;
    return transformedLocalRect(
      group,
      clip && clip.getBoundingRect ? clip.getBoundingRect() : null
    );
  };
  const chartVisuals = Object.entries(window.__DIK_ECHARTS__ || {}).map(([id, chart]) => {
    const model = chart.getModel();
    const gridModels = model.queryComponents({mainType: 'grid'});
    const plots = gridModels.map(gridModel => {
      const gridRect = gridModel && gridModel.coordinateSystem
        ? gridModel.coordinateSystem.getRect()
        : null;
      return gridRect ? {
        left: gridRect.x,
        top: gridRect.y,
        right: gridRect.x + gridRect.width,
        bottom: gridRect.y + gridRect.height
      } : null;
    }).filter(Boolean);
    const legendModel = model.getComponent('legend', 0);
    const legendView = legendModel && legendModel.get('show') !== false
      ? chart.getViewOfComponentModel(legendModel)
      : null;
    const labels = chart.getZr().storage.getDisplayList()
      .filter(item => item && item.type === 'text' && !item.ignore && !item.invisible)
      .map(item => transformedRect(item))
      .filter(rect => rect && rect.right - rect.left > 0 && rect.bottom - rect.top > 0);
    const tooltipModel = model.getComponent('tooltip', 0);
    const seriesCues = model.getSeries().map(seriesModel => {
      const itemStyle = seriesModel.get('itemStyle') || {};
      return {
        lineType: seriesModel.get('lineStyle.type') || 'solid',
        symbol: seriesModel.get('symbol') || null,
        endLabel: seriesModel.get('endLabel.show') === true,
        openFill: itemStyle.color === '#ffffff' && Number(itemStyle.borderWidth || 0) > 0
      };
    });
    return {
      id,
      canvas: {left: 0, top: 0, right: chart.getWidth(), bottom: chart.getHeight()},
      plot: plots[0] || null,
      plots,
      legend: transformedRect(legendView && legendView.group),
      legendViewport: transformedClipRect(legendView && legendView._containerGroup),
      labels,
      tooltipConfine: tooltipModel ? tooltipModel.get('confine') === true : false,
      decalEnabled: model.get('aria.decal.show') === true,
      seriesCues
    };
  });
  const essentialSelector = [
    '.component-desc', '.component-meta', '.source-meta', '.kpi-label',
    '.kpi-note', '.kpi-unit', '.story-label', '.story-desc',
    'th', 'td', '.control-status', '.source-ref'
  ].join(',');
  return {
    overflow: document.documentElement.scrollWidth > innerWidth + 1,
    qualityContract: document.getElementById('dashboard-root').dataset.qualityContract || null,
    components: Array.from(document.querySelectorAll('[data-component-id]')).map(el => {
    const r = el.getBoundingClientRect();
    return {
      id: el.dataset.componentId,
      kind: el.dataset.kind,
      role: el.dataset.role,
      left: r.left,
      top: r.top,
      right: r.right,
      bottom: r.bottom,
      width: r.width,
      height: r.height
    };
    }),
    chartHosts: Array.from(document.querySelectorAll('[data-kind="chart"] .chart-host')).map(el => {
    const r = el.getBoundingClientRect();
    const component = el.closest('[data-component-id]');
    const fallback = component && component.querySelector('.chart-fallback-table');
    const fallbackRect = fallback ? fallback.getBoundingClientRect() : null;
    return {
      id: component ? component.dataset.componentId : null,
      width: r.width,
      height: r.height,
      fallbackActive: component ? component.dataset.fallbackActive === 'true' : false,
      fallbackVisible: Boolean(fallbackRect && fallbackRect.width > 0 && fallbackRect.height > 0)
    };
    }),
    chartCount: Object.keys(window.__DIK_ECHARTS__ || {}).length,
    chartVisuals,
    revision: document.documentElement.dataset.layoutRevision || null,
    unnamedControls: Array.from(document.querySelectorAll('[data-kind="control_bar"] button,[data-kind="control_bar"] select,[data-kind="control_bar"] input'))
      .filter(el => !(el.getAttribute('aria-label') || el.getAttribute('aria-labelledby') || el.textContent.trim())).length,
    bodyFontSize: parseFloat(getComputedStyle(document.body).fontSize || '0'),
    smallEssentialText: Array.from(document.querySelectorAll(essentialSelector)).map(el => {
      const style = getComputedStyle(el);
      const component = el.closest('[data-component-id]');
      return {
        component: component ? component.dataset.componentId : 'unknown',
        selector: String(el.className || el.tagName).trim(),
        fontSize: parseFloat(style.fontSize || '0'),
        visible: style.display !== 'none' && style.visibility !== 'hidden' && el.getClientRects().length > 0
      };
    }).filter(item => item.visible && item.fontSize < 11)
  };
}
"""


def _overlaps(first: dict[str, Any], second: dict[str, Any]) -> bool:
    horizontal = min(first["right"], second["right"]) - max(
        first["left"], second["left"]
    )
    vertical = min(first["bottom"], second["bottom"]) - max(
        first["top"], second["top"]
    )
    return horizontal > 1 and vertical > 1


def _append_unique(target: list[str], message: str) -> None:
    if message not in target:
        target.append(message)


def _component_has_data(component: dict[str, Any], data: dict[str, Any]) -> bool:
    kind = component.get("kind")
    refs = [str(value) for value in component.get("data_refs") or []]
    if kind == "kpi_group":
        kpis = {
            str(item.get("id")): item
            for item in data.get("kpis") or []
            if isinstance(item, dict)
        }
        return any(
            (kpis.get(ref) or {}).get("value") not in {None, ""} for ref in refs
        )
    if kind == "chart":
        charts = {
            str(chart.get("id")): chart
            for panel in data.get("panels") or []
            for chart in panel.get("charts") or []
            if isinstance(chart, dict)
        }
        for ref in refs:
            encoding = (charts.get(ref) or {}).get("encoding") or {}
            if any(
                isinstance(values, list) and values
                for values in (
                    encoding.get("points"),
                    encoding.get("cells"),
                    encoding.get("bins"),
                    encoding.get("boxes"),
                    encoding.get("steps"),
                )
            ):
                return True
            if any(
                (series.get("values") or [])
                or series.get("start") is not None
                or series.get("end") is not None
                for series in encoding.get("series") or []
                if isinstance(series, dict)
            ):
                return True
        return False
    if kind in {"insight", "table"}:
        panels = {
            str(panel.get("id")): panel
            for panel in data.get("panels") or []
            if isinstance(panel, dict)
        }
        for ref in refs:
            panel = panels.get(ref) or {}
            if kind == "table" and ((panel.get("table") or {}).get("rows") or []):
                return True
            if kind == "insight" and any(
                str(value or "").strip()
                for item in (panel.get("story") or {}).values()
                if isinstance(item, dict)
                for value in (item.get("value"), item.get("desc"))
            ):
                return True
        return False
    return True


def _expected_component_ids(
    layout: dict[str, Any], data: dict[str, Any]
) -> list[str]:
    return [
        str(component.get("id"))
        for component in layout.get("components") or []
        if not (
            layout.get("quality_contract_version") == "v5.1"
            and component.get("empty_behavior") == "hide"
            and not _component_has_data(component, data)
        )
    ]


def _chart_visual_blockers(
    viewport_name: str, metrics: dict[str, Any]
) -> list[str]:
    blocks: list[str] = []
    for visual in metrics.get("chartVisuals", []):
        legend = visual.get("legendViewport") or visual.get("legend")
        plots = visual.get("plots") or ([visual.get("plot")] if visual.get("plot") else [])
        canvas = visual.get("canvas")
        if any(_overlaps(first, second) for index, first in enumerate(plots) for second in plots[index + 1 :]):
            _append_unique(
                blocks,
                f"{viewport_name} chart plots overlap: {visual.get('id')}",
            )
        if canvas and any(
            plot["left"] < canvas["left"] - 1
            or plot["top"] < canvas["top"] - 1
            or plot["right"] > canvas["right"] + 1
            or plot["bottom"] > canvas["bottom"] + 1
            for plot in plots
        ):
            _append_unique(
                blocks,
                f"{viewport_name} chart plot clipped by canvas: {visual.get('id')}",
            )
        if legend and any(_overlaps(legend, plot) for plot in plots):
            _append_unique(
                blocks,
                f"{viewport_name} chart legend overlaps plot: {visual.get('id')}",
            )
        if legend and canvas and (
            legend["left"] < canvas["left"] - 1
            or legend["top"] < canvas["top"] - 1
            or legend["right"] > canvas["right"] + 1
            or legend["bottom"] > canvas["bottom"] + 1
        ):
            _append_unique(
                blocks,
                f"{viewport_name} chart legend clipped by canvas: {visual.get('id')}",
            )
    return blocks


def _visual_quality_blockers(
    viewport_name: str, metrics: dict[str, Any]
) -> list[str]:
    blocks = _chart_visual_blockers(viewport_name, metrics)
    for item in metrics.get("smallEssentialText") or []:
        _append_unique(
            blocks,
            f"{viewport_name} essential text below 11px: "
            f"{item.get('component')}/{item.get('selector')}",
        )

    quality_v51 = metrics.get("qualityContract") == "v5.1"
    for visual in metrics.get("chartVisuals") or []:
        chart_id = visual.get("id")
        canvas = visual.get("canvas")
        labels = visual.get("labels") or []
        if any(
            _overlaps(first, second)
            for index, first in enumerate(labels)
            for second in labels[index + 1 :]
        ):
            _append_unique(
                blocks,
                f"{viewport_name} chart labels overlap: {chart_id}",
            )
        if canvas and any(
            label["left"] < canvas["left"] - 1
            or label["top"] < canvas["top"] - 1
            or label["right"] > canvas["right"] + 1
            or label["bottom"] > canvas["bottom"] + 1
            for label in labels
        ):
            _append_unique(
                blocks,
                f"{viewport_name} chart label clipped by canvas: {chart_id}",
            )
        if quality_v51 and visual.get("tooltipConfine") is not True:
            _append_unique(
                blocks,
                f"{viewport_name} chart tooltip is not confined: {chart_id}",
            )
        cues = visual.get("seriesCues") or []
        cue_signatures = {
            (
                cue.get("lineType"),
                cue.get("symbol"),
                bool(cue.get("endLabel")),
                bool(cue.get("openFill")),
            )
            for cue in cues
        }
        if (
            quality_v51
            and len(cues) > 1
            and len(cue_signatures) <= 1
            and not visual.get("decalEnabled")
            and len(visual.get("plots") or []) <= 1
        ):
            _append_unique(
                blocks,
                f"{viewport_name} chart series rely on color only: {chart_id}",
            )
    return blocks


def _playwright_browser_roots() -> list[Path]:
    roots: list[Path] = []
    env_path = os.environ.get("PLAYWRIGHT_BROWSERS_PATH")
    if env_path and env_path != "0":
        roots.extend(Path(part).expanduser() for part in env_path.split(os.pathsep) if part)
    roots.extend(
        [
            Path.home() / "Library" / "Caches" / "ms-playwright",
            Path.home() / ".cache" / "ms-playwright",
            Path.home() / "AppData" / "Local" / "ms-playwright",
        ]
    )
    output: list[Path] = []
    seen: set[str] = set()
    for root in roots:
        key = str(root)
        if key not in seen and root.exists():
            seen.add(key)
            output.append(root)
    return output


def _browser_cache_version(path: Path) -> int:
    match = re.search(r"(?:chromium(?:_headless_shell)?)-(\d+)", str(path))
    return int(match.group(1)) if match else -1


def _browser_executable_candidates() -> list[Path]:
    candidates: list[Path] = []
    for env_name in (
        "DIK_PLAYWRIGHT_EXECUTABLE",
        "VK_PLAYWRIGHT_EXECUTABLE",
        "PLAYWRIGHT_CHROMIUM_EXECUTABLE",
    ):
        env_value = os.environ.get(env_name)
        if env_value:
            candidates.append(Path(env_value).expanduser())

    patterns = [
        "chromium_headless_shell-*/chrome-headless-shell-*/chrome-headless-shell",
        "chromium-*/chrome-linux/chrome",
        "chromium-*/chrome-win/chrome.exe",
        "chromium-*/chrome-mac*/Chromium.app/Contents/MacOS/Chromium",
        "chromium-*/chrome-mac*/Google Chrome for Testing.app/Contents/MacOS/Google Chrome for Testing",
        "chromium-*/**/chrome",
        "chromium-*/**/Google Chrome for Testing",
    ]
    for root in _playwright_browser_roots():
        for pattern in patterns:
            candidates.extend(root.glob(pattern))

    usable: list[Path] = []
    seen: set[str] = set()
    for path in candidates:
        path = path.expanduser()
        key = str(path)
        if key in seen or not path.is_file() or not os.access(path, os.X_OK):
            continue
        seen.add(key)
        usable.append(path)

    def sort_key(path: Path) -> tuple[int, int, str]:
        text = str(path)
        prefer_headless = 0 if ("headless_shell" in text or "chrome-headless-shell" in text) else 1
        return (-_browser_cache_version(path), prefer_headless, text)

    return sorted(usable, key=sort_key)


def _one_line_error(exc: Exception) -> str:
    text = str(exc).strip().splitlines()
    return text[0] if text else exc.__class__.__name__


def _launch_chromium_with_fallback(chromium):
    attempts: list[tuple[str, str]] = []
    try:
        return chromium.launch(), "playwright default"
    except Exception as exc:
        attempts.append(("playwright default", _one_line_error(exc)))

    for executable in _browser_executable_candidates():
        label = f"fallback executable {executable}"
        try:
            return chromium.launch(executable_path=str(executable)), label
        except Exception as exc:
            attempts.append((label, _one_line_error(exc)))

    details = "; ".join(f"{label}: {error}" for label, error in attempts[:5])
    raise RuntimeError(
        "Playwright 브라우저 실행 실패. dashboard_data 계약 실패와 분리된 로컬 렌더 환경 문제입니다. "
        f"시도한 실행 경로: {details}"
    )


def run_browser_qa(
    html_path: Path,
    layout: dict[str, Any],
    data: dict[str, Any],
    output_dir: Path,
) -> tuple[list[str], list[str]]:
    """Render both release viewports and return deterministic block/warn lists."""
    blocks: list[str] = []
    warns: list[str] = []
    html_path = Path(html_path).resolve()
    output_dir = Path(output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)
    expected_component_ids = _expected_component_ids(layout, data)
    expected_charts = sum(
        1
        for component in layout.get("components", [])
        if component.get("kind") == "chart"
        and str(component.get("id")) in expected_component_ids
    )

    for panel in data.get("panels", []):
        for chart in panel.get("charts", []):
            if len(str(chart.get("title") or "")) > 48:
                _append_unique(
                    warns,
                    f"chart title exceeds 48 characters: {chart.get('id')}",
                )

    try:
        from playwright.sync_api import sync_playwright
    except ImportError:
        return ["browser QA unavailable: playwright is not installed"], warns

    try:
        with sync_playwright() as playwright:
            browser, browser_label = _launch_chromium_with_fallback(playwright.chromium)
            if browser_label != "playwright default":
                _append_unique(
                    warns,
                    f"Playwright 기본 브라우저 실행 실패 후 fallback 사용: {browser_label}",
                )
            for viewport_name, viewport in VIEWPORTS.items():
                page = browser.new_page(viewport=viewport)
                page_errors: list[str] = []
                console_errors: list[str] = []
                remote_requests: list[str] = []
                page.on("pageerror", lambda exc: page_errors.append(str(exc)))
                page.on(
                    "console",
                    lambda message: console_errors.append(message.text)
                    if message.type == "error"
                    else None,
                )
                page.on(
                    "request",
                    lambda request: remote_requests.append(request.url)
                    if request.url.startswith(("http://", "https://"))
                    else None,
                )
                page.route("http://**/*", lambda route: route.abort())
                page.route("https://**/*", lambda route: route.abort())
                page.goto(html_path.as_uri(), wait_until="load")
                page.wait_for_timeout(250)
                metrics = page.evaluate(METRICS_JS)
                page.screenshot(
                    path=str(output_dir / f"qa_render_{viewport_name}.png"),
                    full_page=True,
                )

                if page_errors:
                    _append_unique(
                        blocks,
                        f"{viewport_name} pageerror: {'; '.join(page_errors)}",
                    )
                if console_errors:
                    _append_unique(
                        blocks,
                        f"{viewport_name} console error: {'; '.join(console_errors)}",
                    )
                if remote_requests:
                    _append_unique(
                        blocks,
                        f"{viewport_name} network request blocked: {remote_requests[0]}",
                    )

                components = metrics["components"]
                actual_component_ids = [item.get("id") for item in components]
                if set(actual_component_ids) != set(expected_component_ids):
                    _append_unique(
                        blocks,
                        f"{viewport_name} component visibility mismatch: "
                        f"expected {expected_component_ids}, got {actual_component_ids}",
                    )
                for component in components:
                    if component["width"] <= 0 or component["height"] <= 0:
                        _append_unique(
                            blocks,
                            f"{viewport_name} component 0 size: {component['id']}",
                        )
                for index, first in enumerate(components):
                    for second in components[index + 1 :]:
                        if _overlaps(first, second):
                            _append_unique(
                                blocks,
                                f"{viewport_name} component overlap: {first['id']} / {second['id']}",
                            )

                off_viewport = any(
                    component["left"] < -1 or component["right"] > viewport["width"] + 1
                    for component in components
                )
                if metrics["overflow"] or off_viewport:
                    _append_unique(blocks, f"{viewport_name} viewport overflow")

                for issue in _visual_quality_blockers(viewport_name, metrics):
                    _append_unique(blocks, issue)

                if len(metrics["chartHosts"]) != expected_charts:
                    _append_unique(
                        blocks,
                        f"{viewport_name} empty chart: host count {len(metrics['chartHosts'])} != {expected_charts}",
                    )
                for index, host in enumerate(metrics["chartHosts"]):
                    valid_fallback = host.get("fallbackActive") and host.get(
                        "fallbackVisible"
                    )
                    if (
                        host["width"] <= 0 or host["height"] <= 0
                    ) and not valid_fallback:
                        _append_unique(
                            blocks,
                            f"{viewport_name} empty chart or 0 size: chart host {index}",
                        )
                if metrics["chartCount"] != expected_charts:
                    _append_unique(
                        blocks,
                        f"{viewport_name} ECharts instance count {metrics['chartCount']} != {expected_charts}",
                    )
                if str(metrics["revision"]) != str(layout.get("revision")):
                    _append_unique(
                        blocks,
                        f"{viewport_name} layout revision mismatch: {metrics['revision']} != {layout.get('revision')}",
                    )
                if metrics["unnamedControls"]:
                    _append_unique(
                        blocks,
                        f"{viewport_name} controls without accessible name: {metrics['unnamedControls']}",
                    )
                if metrics["bodyFontSize"] < 11:
                    _append_unique(
                        warns,
                        f"{viewport_name} body font is below 11px",
                    )

                heroes = [item for item in components if item.get("role") == "hero"]
                supports = [item for item in components if item.get("role") == "support"]
                if heroes and supports:
                    hero_area = max(item["width"] * item["height"] for item in heroes)
                    if any(item["width"] * item["height"] > hero_area for item in supports):
                        _append_unique(
                            warns,
                            f"{viewport_name} hero area is smaller than a support component",
                        )
                page.close()
            browser.close()
    except Exception as exc:
        _append_unique(blocks, f"browser QA environment error: {exc}")

    if layout.get("quality_contract_version") == "v5.1":
        record = ensure_visual_review_draft(output_dir, VIEWPORTS)
        for issue in validate_visual_review(record, output_dir, VIEWPORTS):
            _append_unique(blocks, issue)

    return blocks, warns
