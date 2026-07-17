#!/usr/bin/env python3
"""
data-insight-kit QA 검증기.

데이터 주입형 대시보드의 출고 게이트. run-pipeline이 이 스크립트를 반드시 실행하고
BLOCK이 하나라도 있으면 출고를 차단한다. (스키마 검증만으론 못 잡는 것들을 여기서 강제)

설계:
- 정적 검사(스키마 + 구조)는 항상 실행 — 의존성: jsonschema.
- 렌더 검사(playwright 헤드리스)는 playwright가 있을 때만 — 모든 탭의 desktop/mobile 렌더에서 blank, 콘솔 에러,
  시뮬레이터 화면값, SVG 크기, 텍스트 겹침/잘림을 본다. 없으면 SKIP(경고). 재배포 시 브라우저 강제 안 함.

심각도(오류 class별 정책 기본값 — 계획 §10.6):
- BLOCK: 출고 차단. schema 실패 / 죽은 시뮬레이터 / 값-라벨 불일치 / 콘솔 에러 / 렌더 레이아웃 오류 / 플레이스홀더 잔존 / 길이 불일치.
- WARN : 경고만(표시는 하되 차단 안 함). metric 시드 누락(v2 재현 권장) / 표본 작음.

사용법:
  python qa/validate.py <dashboard_data.json> [--chart-spec outputs/chart_spec.json] [--layout outputs/dashboard_layout.json] [--template templates/dashboard.html] [--no-render] [--post-communicate]
종료코드: 0 = 출고 가능(BLOCK 없음) / 1 = 차단(BLOCK 있음) / 2 = 사용 오류.
"""
import argparse
import difflib
import hashlib
import json
import math
import os
import pathlib
import re
import sys
from datetime import datetime

KIT_ROOT = pathlib.Path(__file__).resolve().parent.parent
if str(KIT_ROOT) not in sys.path:
    sys.path.insert(0, str(KIT_ROOT))

from dashboard_v5.browser_qa import run_browser_qa
from dashboard_v5.compiler import build_manifest
from dashboard_v5.contract import (
    ContractError,
    select_renderer,
    validate_layout,
    validate_v5_cross_contract,
)

BLOCK, WARN = [], []
def block(msg): BLOCK.append(msg)
def warn(msg): WARN.append(msg)

try:
    from scripts.external_adapter_utils import CATEGORY_ALLOWED_METRIC_LAYERS
except Exception:
    CATEGORY_ALLOWED_METRIC_LAYERS = {
        "population": {"demand", "context", "coverage"},
        "foot_traffic": {"demand", "context", "coverage"},
        "rent": {"cost", "context", "coverage"},
        "sales": {"performance", "context", "coverage"},
        "business_dynamics": {"context", "coverage"},
        "area": {"spatial", "context", "coverage"},
        "competition": {"competition", "context", "coverage"},
        "mobility": {"spatial", "context", "coverage"},
        "custom": {"demand", "cost", "performance", "spatial", "competition", "context", "coverage"},
    }

# ── 시뮬레이터 모델 계산 (templates/dashboard.html 의 computeModel 과 동일 규약) ──
def compute_model(model, inputs, vals):
    def get(iid):
        inp = next((i for i in inputs if i["id"] == iid), None)
        v = vals[iid]
        return v - (inp["default"] if inp else 0) if model.get("input_basis") == "delta_from_default" else v
    t = model["type"]
    if t == "linear":
        out = model["base"] + sum(term["coefficient"] * get(term["input"]) for term in model["terms"])
    elif t == "percentage":
        s = sum(term["pct_per_unit"] * get(term["input"]) for term in model["terms"])
        out = model["base"] * (1 + s / 100)
    elif t == "lookup":
        x = vals[model["input"]]
        tb = model["table"]
        if x <= tb[0]["in"]:
            out = float("nan") if (x < tb[0]["in"] and model.get("out_of_range") == "error") else tb[0]["out"]
        elif x >= tb[-1]["in"]:
            out = float("nan") if (x > tb[-1]["in"] and model.get("out_of_range") == "error") else tb[-1]["out"]
        else:
            out = next(tb[i]["out"] + (x - tb[i]["in"]) / (tb[i+1]["in"] - tb[i]["in"]) * (tb[i+1]["out"] - tb[i]["out"])
                       for i in range(len(tb)-1) if tb[i]["in"] <= x <= tb[i+1]["in"])
    else:
        return None
    r = model.get("rounding")
    return round(out, r) if (r is not None and not math.isnan(out)) else out

STACK_OK = {"line": {"none"}, "area": {"none"}, "bar": {"none", "grouped"}, "stacked_bar": {"stacked", "stacked_100"}}
PLACEHOLDERS = ("PLACE_DASHBOARD_DATA_HERE", "TODO", "FIXME", "{{", "placeholder")
DASHBOARD_PROFILES = {"executive_brief", "analyst_workspace", "operations_monitor"}
PROFILE_LABEL_VISIBLE_TERMS = ("요약 보고서형", "분석가 작업형", "운영 모니터링형")
RELATIVE_PERIOD_VISIBLE_TERMS = ("시작월", "끝월", "최근 끝점", "기간 가격")
UNRESOLVED_UNIT_VISIBLE_TERMS = (
    "가격 단위 미확인",
    "단위 미확인",
    "가격 단위 후보",
    "원천 단위",
)
DIAGNOSTIC_CHART_TYPES = {"heatmap", "scatter", "histogram", "boxplot", "stacked_bar", "slope"}
TIME_STATUS_CHART_TYPES = {"line", "area", "slope"}
REQUIRED_PRE_REPORT_CHECKPOINTS = ("data_profile", "analysis_strategy", "dashboard_storyboard")
REQUIRED_POST_REPORT_CHECKPOINTS = REQUIRED_PRE_REPORT_CHECKPOINTS + ("report_outline",)
HUMAN_CONFIRMATION_SOURCES = {"ask_user_question", "user_chat", "manual_cli"}
CHECKPOINT_ANSWER_RECORDER = "scripts/apply_checkpoint_answer.py"
CHECKPOINT_DOWNSTREAM_ARTIFACTS = {
    "data_profile": [
        "outputs/03_frame.md",
        "outputs/04_analysis.md",
        "outputs/chart_spec.json",
        "outputs/dashboard_data.json",
        "outputs/dashboard.html",
        "outputs/summary_report.md",
        "outputs/deep_report.md",
    ],
    "analysis_strategy": [
        "outputs/04_analysis.md",
        "outputs/chart_spec.json",
        "outputs/dashboard_data.json",
        "outputs/dashboard.html",
        "outputs/summary_report.md",
        "outputs/deep_report.md",
    ],
    "dashboard_storyboard": [
        "outputs/dashboard_data.json",
        "outputs/dashboard.html",
        "outputs/summary_report.md",
        "outputs/deep_report.md",
    ],
    # H2.5는 실행 순서상 analyze 직후·dashboard_storyboard 앞이므로 downstream 집합이 같다.
    "analysis_result_review": [
        "outputs/dashboard_data.json",
        "outputs/dashboard.html",
        "outputs/summary_report.md",
        "outputs/deep_report.md",
    ],
    "report_outline": [
        "outputs/summary_report.md",
        "outputs/deep_report.md",
    ],
}
CHECKPOINT_PREFIXES = {
    "data_profile": "01_data_profile_question",
    "analysis_strategy": "02_analysis_strategy_question",
    "dashboard_storyboard": "03_dashboard_storyboard_question",
    "report_outline": "04_report_outline_question",
    # 고정 prefix 05_ — 파일명 번호는 식별자일 뿐 실행 순서가 아니다 (spec §15).
    "analysis_result_review": "05_analysis_result_review_question",
}

# ── expert-guided analysis routing v1 (spec §7·§8.5·§9·§10) ──
# stage_guard.py와 같은 판정을 "각자 재계산"한다 — import 없이 독립 구현 (spec §9).
DEEP_REVIEW_ROUTES = {"statistical", "ml_exploratory", "predictive", "causal_experiment"}
DECISION_ANALYSIS_MODES = {"candidate_prioritization", "risk_screening"}
V1_DOWNGRADE_ONLY_ROUTES = {"predictive", "causal_experiment"}
# stage_guard.ROUTE_RANK와 의도적으로 동일한 표 (spec §15 implementation default).
ROUTE_RANK = {
    "descriptive": 0,
    "diagnostic": 0,
    "statistical": 1,
    "ml_exploratory": 1,
    "predictive": 2,
    "causal_experiment": 2,
}
# spec §8.5 공통 필수 domain intake 항목 (stage_guard.compute_domain_readiness와 동일 규칙).
DOMAIN_REQUIRED_INTAKE_FIELDS = (
    "row_meaning",
    "entity_grain",
    "column_semantics",
    "exclusion_rules",
    "objective",
    "forbidden_claims",
)
# domain_readiness=insufficient에서 BLOCK되는 확정 표현 (spec §10.2). 짧고 고정밀 위주.
DOMAIN_CONCLUSION_TERMS = (
    "추천한다",
    "추천합니다",
    "원인이다",
    "원인입니다",
    "원인으로 확인",
    "성과가 입증",
    "성과를 입증",
    "위험도를 확정",
    "확정적으로",
)
# 일반 통계 과잉해석 휴리스틱 (spec §10.2 — WARN으로 시작, 부정문 오탐 방지).
STAT_EVIDENCE_TERMS = ("p-value", "p값", "p 값", "상관계수", "correlation")
STAT_CONCLUSION_TERMS = ("증명", "입증", "인과관계", "원인이다", "원인입니다", "확실하다")
RUN_REF_RE = re.compile(r"(?:^|[^A-Za-z0-9_.-])runs/([A-Za-z0-9_.-]+)")
ABS_RUN_REF_RE = re.compile(r"/data-insight-kit/runs/([A-Za-z0-9_.-]+)")

ANALYSIS_DEEP_KEYWORDS = [
    ("선택 전략", ("선택 전략", "분석 전략", "strategy")),
    ("방법론", ("방법론", "분석법", "method")),
    ("KPI", ("KPI", "지표", "metric")),
    ("세그먼트/분포/관계/추세", ("세그먼트", "분포", "관계", "추세", "segment", "distribution", "relationship", "trend")),
    ("한계", ("한계", "제약", "limit")),
    ("액션 기준", ("액션", "실행", "우선순위", "임계", "기준", "action", "threshold")),
    ("반대 해석", ("반대 해석", "대체 설명", "리스크", "risk")),
]

DEEP_REPORT_KEYWORDS = [
    ("의사결정", ("의사결정", "판단", "질문", "decision", "question")),
    ("방법론", ("방법론", "분석법", "방법", "method", "methodology")),
    ("KPI", ("KPI", "지표", "metric")),
    ("세그먼트/분포/관계/추세", ("세그먼트", "분포", "관계", "추세", "segment", "distribution", "relationship", "trend")),
    ("반대 해석", ("반대 해석", "대체 설명", "리스크", "counter", "alternative", "risk")),
    ("한계", ("한계", "제약", "limit", "limitation")),
    ("액션 기준", ("실행 시나리오", "액션", "임계", "기준", "보류", "추적", "action", "threshold")),
    ("추가 분석", ("추가 분석", "후속 분석", "추가 데이터", "follow-up", "additional")),
    ("lineage", ("부록", "chart_spec", "lineage", "source_ref", "출처", "appendix")),
    ("품질 점검", ("품질 점검", "루브릭", "quality", "rubric")),
]

DEEP_REPORT_HEADINGS = [
    ("의사결정 질문", ("의사결정 질문", "판단 질문", "decision")),
    ("방법론과 데이터 한계", ("방법론과 데이터 한계", "방법론", "데이터 한계", "method")),
    ("KPI 정의", ("KPI 정의", "지표 정의", "metric")),
    ("핵심 발견", ("핵심 발견", "주요 발견", "finding")),
    ("세그먼트/분포/관계/추세 분석", ("세그먼트", "분포", "관계", "추세", "segment", "distribution", "relationship", "trend")),
    ("반대 해석과 리스크", ("반대 해석", "리스크", "대체 설명", "risk")),
    ("실행 시나리오", ("실행 시나리오", "액션", "action")),
    ("추가 분석 설계", ("추가 분석", "후속 분석", "additional")),
    ("부록: chart_spec / lineage", ("부록", "chart_spec", "lineage", "source_ref", "appendix")),
]

ADMIN_GRAINS = {"admin_dong", "sigungu", "province"}
COARSE_GRAINS = {"trade_area", "custom"}
COARSE_JOIN_QUALITIES = {"manual", "normalized", "unknown"}
COVERAGE_WARN_MATCH_RATE = 0.95
COVERAGE_BLOCK_MATCH_RATE = 0.80
COVERAGE_WARN_NULL_RATE = 0.05
COVERAGE_BLOCK_NULL_RATE = 0.20
RANK_OVERFLOW_ABS_LIMIT = 100000
RANK_TERMS = ("rank_delta", "rank_shift", "ranking shift", "baseline_rank", "population_rank", "순위 변화", "순위차")
ASSERTIVE_FORBIDDEN_TERMS = (
    "수요 확정",
    "수익성",
    "시장성 확정",
    "매출 잠재력 확정",
    "성공 가능성 확정",
    "원인 확정",
    "성과 확정",
    "성공 확정",
)
PUBLIC_TITLE_FORBIDDEN_TERMS = (
    "접점 후보",
    "후보 우선순위",
    "fresh snapshot",
    "data_only",
)
INTERNAL_VISIBLE_TERMS = (
    "proxy",
    "metric layer",
    "layer",
    "grain",
    "chart_spec",
    "source_ref",
    "rank_delta",
    "rank_shift",
    "data_only",
    "mixed",
)
RAW_ADMIN_CODE_RE = re.compile(r"\(\d{7,}\)")
RAW_COLUMN_RE = re.compile(r"\b[A-Z]{2,}_[A-Z0-9_]{2,}\b")
SAFE_FORBIDDEN_CONTEXT_TERMS = (
    "아니",
    "아님",
    "않",
    "금지",
    "한계",
    "주의",
    "부재",
    "없",
    "제외",
    "단정",
    "확정할 수",
    "prohibited",
    "limit",
)
COARSE_DISCLOSURE_TERMS = (
    "coarse",
    "manual",
    "normalized",
    "custom",
    "trade_area",
    "정밀",
    "직접 join",
    "정확한 join",
    "조인 한계",
    "수동",
    "권역",
    "집계",
)
ACQUISITION_DISCLOSURE_TERMS = (
    "acquisition",
    "pagination",
    "page",
    "collected_row_count",
    "수집",
    "페이지",
    "다운로드",
)
AGGREGATION_BASIS_TERMS = (
    "denominator_aggregation_basis",
    "matched_grain",
    "not_summed",
    "raw_source_total",
    "가중",
    "matched",
    "합산 기준",
    "분모 합산",
)
LAYOUT_CHECK_JS = """
() => {
  const issues = [];
  const active = document.querySelector('.panel.active');
  if (!active) {
    return ['active panel missing'];
  }
  const cards = Array.from(active.querySelectorAll('.card'));
  cards.forEach((card, cardIndex) => {
    const title = (card.querySelector('.cc-t')?.textContent || `chart ${cardIndex + 1}`).trim();
    Array.from(card.querySelectorAll('svg')).forEach((svg, svgIndex) => {
      const sr = svg.getBoundingClientRect();
      if (sr.width < 40 || sr.height < 40) {
        issues.push(`${title}: SVG too small ${Math.round(sr.width)}x${Math.round(sr.height)}px`);
      }
      if (sr.width > Math.min(window.innerWidth - 24, 660)) {
        issues.push(`${title}: SVG too wide ${Math.round(sr.width)}px`);
      }
      if (sr.height > 390) {
        issues.push(`${title}: SVG too tall ${Math.round(sr.height)}px`);
      }
      const texts = Array.from(svg.querySelectorAll('text')).map((el, index) => {
        const r = el.getBoundingClientRect();
        return {
          index,
          text: (el.textContent || '').trim(),
          left: r.left,
          right: r.right,
          top: r.top,
          bottom: r.bottom,
          width: r.width,
          height: r.height
        };
      }).filter(t => t.width > 0.5 && t.height > 0.5);
      for (const t of texts) {
        if (t.left < sr.left - 5 || t.right > sr.right + 5 || t.top < sr.top - 5 || t.bottom > sr.bottom + 5) {
          issues.push(`${title}: label clipped "${t.text}"`);
        }
      }
      for (let i = 0; i < texts.length; i++) {
        for (let j = i + 1; j < texts.length; j++) {
          const a = texts[i], b = texts[j];
          const ox = Math.min(a.right, b.right) - Math.max(a.left, b.left);
          const oy = Math.min(a.bottom, b.bottom) - Math.max(a.top, b.top);
          const area = Math.max(0, ox) * Math.max(0, oy);
          if (area > 18 && ox > 3 && oy > 3) {
            issues.push(`${title}: label overlap "${a.text}" / "${b.text}"`);
          }
        }
      }
    });
  });
  // 카드 블록 간 겹침 (v4 smoke 발견: grid blowout이 QA를 통과했음 — 카드 단위 검사 부재)
  const blocks = Array.from(
    active.querySelectorAll('.card, .kpi, .story, .actions, .sim, table.dt')
  ).map(el => {
    const r = el.getBoundingClientRect();
    const name = (el.querySelector('.cc-t, .kpi-l')?.textContent || el.className.toString()).trim().slice(0, 40);
    return {el, name, left: r.left, right: r.right, top: r.top, bottom: r.bottom,
            w: r.width, h: r.height};
  }).filter(b => b.w > 8 && b.h > 8);
  for (let i = 0; i < blocks.length; i++) {
    for (let j = i + 1; j < blocks.length; j++) {
      const a = blocks[i], b = blocks[j];
      if (a.el.contains(b.el) || b.el.contains(a.el)) continue;
      const ox = Math.min(a.right, b.right) - Math.max(a.left, b.left);
      const oy = Math.min(a.bottom, b.bottom) - Math.max(a.top, b.top);
      if (ox > 8 && oy > 8) {
        issues.push(`카드 겹침: "${a.name}" ↔ "${b.name}" (${Math.round(ox)}x${Math.round(oy)}px)`);
      }
    }
  }
  return issues.slice(0, 16);
}
"""

def _is_selectish(sql):
    s = re.sub(r"--.*?$|/\*.*?\*/", " ", sql or "", flags=re.S | re.M).strip().rstrip(";").strip()
    return s.lower().startswith(("select ", "with "))

def _read_optional_text(path):
    p = pathlib.Path(path)
    if not p.exists():
        return None
    return p.read_text(encoding="utf-8", errors="replace")

def _internal_term_hits(text):
    lowered = text.lower()
    hits = []
    for term in INTERNAL_VISIBLE_TERMS:
        if term.lower() in lowered:
            hits.append(term)
    if RAW_COLUMN_RE.search(text):
        hits.append("raw_column_name")
    return hits

def _number_tokens(text):
    return set(re.findall(r"(?:top\s*)?\d+(?:[.,]\d+)?%?", str(text), flags=re.I))

def _compact_compare(text):
    return re.sub(r"\s+", "", str(text or "").lower())

def _dashboard_visible_texts(data):
    meta = data.get("meta") or {}
    for key in ("title", "subtitle", "domain"):
        if meta.get(key):
            yield f"meta.{key}", str(meta[key])
    for idx, kpi in enumerate(data.get("kpis") or []):
        for key in ("label", "unit", "note", "status"):
            if kpi.get(key):
                yield f"kpis[{idx}].{key}", str(kpi[key])
        # v4 E1: 렌더되는 델타 basis·스파크 캡션도 사용자 노출 텍스트 (Codex M9)
        comparison = kpi.get("comparison")
        if isinstance(comparison, dict) and comparison.get("basis"):
            yield f"kpis[{idx}].comparison.basis", str(comparison["basis"])
        trend = kpi.get("trend")
        if isinstance(trend, dict) and trend.get("period_label"):
            yield f"kpis[{idx}].trend.period_label", str(trend["period_label"])
    for pidx, panel in enumerate(data.get("panels") or []):
        for key in ("title", "subtitle", "description", "summary"):
            if panel.get(key):
                yield f"panels[{pidx}].{key}", str(panel[key])
        for cidx, chart in enumerate(panel.get("charts") or []):
            for key in ("title", "desc", "description", "method", "note"):
                if chart.get(key):
                    yield f"panels[{pidx}].charts[{cidx}].{key}", str(chart[key])
            enc = chart.get("encoding") or {}
            x = enc.get("x") or {}
            for key in ("label", "title"):
                if x.get(key):
                    yield f"panels[{pidx}].charts[{cidx}].encoding.x.{key}", str(x[key])
            for vidx, value in enumerate(x.get("values") or []):
                if isinstance(value, str):
                    yield f"panels[{pidx}].charts[{cidx}].encoding.x.values[{vidx}]", value
            y = enc.get("y") or {}
            for key in ("label", "title"):
                if y.get(key):
                    yield f"panels[{pidx}].charts[{cidx}].encoding.y.{key}", str(y[key])
            for sidx, series in enumerate(enc.get("series") or []):
                if series.get("label"):
                    yield f"panels[{pidx}].charts[{cidx}].series[{sidx}].label", str(series["label"])
        table = panel.get("table") or {}
        for cidx, column in enumerate(table.get("columns") or []):
            yield f"panels[{pidx}].table.columns[{cidx}]", str(column)
        for ridx, row in enumerate(table.get("rows") or []):
            for cidx, cell in enumerate(row):
                if isinstance(cell, str):
                    yield f"panels[{pidx}].table.rows[{ridx}][{cidx}]", cell
        for aidx, action in enumerate(panel.get("actions") or []):
            for key in ("title", "why", "description"):
                if isinstance(action, dict) and action.get(key):
                    yield f"panels[{pidx}].actions[{aidx}].{key}", str(action[key])

def reader_facing_dashboard_checks(data):
    meta = data.get("meta") or {}
    title = str(meta.get("title") or "")
    for term in PUBLIC_TITLE_FORBIDDEN_TERMS:
        if term.lower() in title.lower():
            block(f"배포용 제목 품질 실패: meta.title에 내부 작업용 표현 '{term}' 포함")
    title_hits = _internal_term_hits(title)
    if title_hits:
        block(f"배포용 제목 품질 실패: meta.title 내부 용어 노출({sorted(set(title_hits))})")

    kpis = data.get("kpis") or []
    if len(kpis) > 6:
        warn(f"첫 화면 KPI가 {len(kpis)}개로 많음 — 배포용 대시보드는 핵심 4~6개 우선 권장")
    for kpi in kpis:
        label = str(kpi.get("label") or "")
        unit = str(kpi.get("unit") or "")
        value = kpi.get("value")
        if "코드" in label:
            warn(f"KPI '{label}'가 원천 식별자 관점을 전면 노출함 — 독자용 지표명으로 치환 권장")
        if "Top" in label or "top" in label:
            warn(f"KPI '{label}'가 내부 스크리닝 축약어를 사용함 — 상위 20개/상위 50개처럼 풀어쓰기 권장")
        if re.search(r"\b[A-Z]{2,}\b", label) or re.search(r"\b[A-Z]{2,}\b", unit):
            warn(f"KPI '{label}'가 내부 약어를 그대로 노출할 수 있음 — 독자가 이해할 수 있는 지표 설명으로 풀어쓰기 권장")
        if isinstance(value, (int, float)) and abs(value) >= 1_000_000:
            fmt = kpi.get("format") or {}
            if not fmt.get("display_value") and fmt.get("display_scale", 1) == 1:
                warn(f"KPI '{label}' 큰 수치가 축약 표시값 없이 노출될 수 있음 — 만/천명 단위 표시 권장")

    raw_code_examples = []
    internal_examples = []
    for path, text in _dashboard_visible_texts(data):
        for term in PUBLIC_TITLE_FORBIDDEN_TERMS:
            if term.lower() in text.lower():
                block(f"배포용 visible text 품질 실패: {path}에 내부 작업용 표현 '{term}' 포함")
        for term in PROFILE_LABEL_VISIBLE_TERMS:
            if term in text:
                block(f"배포용 visible text 품질 실패: {path}에 내부 대시보드 프로필 라벨 '{term}' 포함")
        for term in RELATIVE_PERIOD_VISIBLE_TERMS:
            if term in text:
                block(
                    f"배포용 visible text 품질 실패: {path}에 계산용 기간 표현 '{term}' 포함 — "
                    "실제 YYYY-MM 비교 시점과 집계 의미를 직접 표시"
                )
        for term in UNRESOLVED_UNIT_VISIBLE_TERMS:
            if term in text:
                block(
                    f"배포용 visible text 품질 실패: {path}에 미확정 단위 '{term}' 포함 — "
                    "근거 있는 독자용 단위를 확정하거나 해당 수치를 제외"
                )
        if RAW_ADMIN_CODE_RE.search(text):
            raw_code_examples.append(f"{path}: {text[:80]}")
        hits = _internal_term_hits(text)
        if hits and not path.startswith("meta.audience"):
            internal_examples.append(f"{path}: {sorted(set(hits))}")
    if raw_code_examples:
        block(
            "배포용 라벨 품질 실패: 차트/표 visible label에 행정동 코드가 직접 노출됨 "
            f"예: {'; '.join(raw_code_examples[:3])}"
        )
    if len(internal_examples) >= 8:
        warn(
            "대시보드 visible text에 내부 분석 용어가 많음 — 제목/축/카드 문구를 독자 언어로 재작성 권장 "
            f"예: {'; '.join(internal_examples[:4])}"
            )


def v5_series_scale_checks(data, layout):
    """Block overlaid v5 line/area series when one series becomes unreadably flat."""
    if (data.get("meta") or {}).get("dashboard_profile_contract") != "v5":
        return
    if not isinstance(layout, dict):
        return
    layout_by_chart = {
        str(component.get("data_refs", [""])[0]): component
        for component in layout.get("components") or []
        if component.get("kind") == "chart" and component.get("data_refs")
    }
    for panel in data.get("panels") or []:
        for chart in panel.get("charts") or []:
            if chart.get("type") not in {"line", "area"}:
                continue
            series = (chart.get("encoding") or {}).get("series") or []
            if len(series) < 2:
                continue
            component = layout_by_chart.get(str(chart.get("id"))) or {}
            series_layout = (component.get("render_options") or {}).get(
                "series_layout", "overlay"
            )
            if series_layout == "stacked_panels":
                continue
            units = {str(item.get("unit")) for item in series if item.get("unit")}
            spans = []
            for item in series:
                values = [
                    float(value)
                    for value in item.get("values") or []
                    if isinstance(value, (int, float))
                    and not isinstance(value, bool)
                    and math.isfinite(value)
                ]
                if values and max(values) > min(values):
                    spans.append(max(values) - min(values))
            span_ratio = max(spans) / min(spans) if len(spans) >= 2 else 1
            if len(units) > 1 or span_ratio >= 4:
                block(
                    f"v5 차트 '{chart.get('id')}' 여러 선의 단위 또는 관측 범위가 달라 "
                    f"한 축에서 작은 변화가 눌림(관측 범위 비율 {span_ratio:.1f}배) — "
                    "series_layout=stacked_panels 사용"
                )

def chart_spec_quality_checks(chart_spec, deep=False):
    charts = chart_spec.get("charts") or []
    story = chart_spec.get("dashboard_story") or {}
    if deep:
        missing_story = [key for key in ("headline", "decision", "caveat") if not (isinstance(story, dict) and story.get(key))]
        if missing_story:
            block(f"depth=deep chart_spec.dashboard_story 필수 필드 누락: {', '.join(missing_story)}")
        if len(charts) < 4:
            block(f"depth=deep chart_spec 차트 수 부족: {len(charts)}개 — 최소 4개 이상의 질문별 차트 필요")

    methods = [str(c.get("method") or "") for c in charts if isinstance(c, dict)]
    chart_types = [str((c.get("chart") or {}).get("type") or "") for c in charts if isinstance(c, dict)]
    if len(charts) >= 4:
        unique_methods = {m for m in methods if m}
        unique_types = {t for t in chart_types if t}
        if deep and len(unique_methods) < 3:
            block(f"depth=deep chart_spec 방법론 다양성 부족: {sorted(unique_methods)}")
        elif len(unique_methods) < 3:
            warn(f"chart_spec 방법론 다양성 낮음: {sorted(unique_methods)}")
        if deep and len(unique_types) < 3:
            block(f"depth=deep chart_spec 차트 유형 다양성 부족: {sorted(unique_types)}")
        elif len(unique_types) < 2:
            warn(f"chart_spec 차트 유형 다양성 낮음: {sorted(unique_types)}")
        for method in unique_methods:
            share = methods.count(method) / max(1, len(methods))
            if share > 0.60:
                message = f"chart_spec method '{method}' 비중이 {share:.0%}로 높음 — 질문/비교축 반복 가능성"
                block(message) if deep else warn(message)

    expected_types = {
        "trend": {"line", "area", "slope"},
        "ranking": {"bar"},
        "distribution": {"histogram", "boxplot"},
        "relationship": {"scatter", "heatmap"},
        "composition": {"stacked_bar", "bar", "heatmap"},
        "contribution": {"waterfall", "bar"},
        "cohort": {"line", "area", "heatmap"},
        "segmentation": {"bar", "stacked_bar", "heatmap", "boxplot", "slope"},
        "anomaly": {"scatter", "bar", "line"},
        "forecast_signal": {"line", "area"},
        "quality": {"bar", "heatmap", "histogram"},
    }
    questions = []
    weak = []
    for chart in charts:
        if not isinstance(chart, dict):
            continue
        cid = chart.get("id", "<unknown>")
        question = str(chart.get("question") or "")
        questions.append((cid, question))
        if len(question.strip()) < 12:
            weak.append(f"{cid}: question too short")
        method = str(chart.get("method") or "")
        chart_type = str((chart.get("chart") or {}).get("type") or "")
        if method in expected_types and chart_type and chart_type not in expected_types[method]:
            warn(f"chart_spec '{cid}' method={method}와 chart.type={chart_type} 조합 확인 필요")
        insight = chart.get("insight") or {}
        finding = str(insight.get("finding") or "")
        evidence = str(insight.get("evidence") or "")
        limit = str(insight.get("limit") or "")
        if len(finding.strip()) < 16:
            weak.append(f"{cid}: finding too shallow")
        if len(evidence.strip()) < 12:
            weak.append(f"{cid}: evidence too shallow")
        if len(limit.strip()) < 12:
            weak.append(f"{cid}: limit too shallow")
        if _compact_compare(finding) and _compact_compare(finding) == _compact_compare(question):
            weak.append(f"{cid}: finding repeats question")
    for idx, (cid, question) in enumerate(questions):
        for other_cid, other_question in questions[idx + 1:]:
            if question and other_question:
                similarity = difflib.SequenceMatcher(None, _compact_compare(question), _compact_compare(other_question)).ratio()
                if similarity > 0.90:
                    weak.append(f"{cid}/{other_cid}: duplicated question")
    if weak:
        msg = "chart_spec 인사이트 품질 미달: " + "; ".join(weak[:6])
        block(msg) if deep else warn(msg)

def dashboard_story_alignment_checks(data, chart_spec):
    spec_by_chart_id = {}
    for spec in chart_spec.get("charts", []) or []:
        if not isinstance(spec, dict):
            continue
        mapped = (spec.get("dashboard_mapping") or {}).get("chart_id") or spec.get("id")
        if mapped:
            spec_by_chart_id[str(mapped)] = spec
    missing_evidence = []
    shallow_desc = []
    for panel in data.get("panels", []) or []:
        for chart in panel.get("charts", []) or []:
            cid = str(chart.get("id") or "")
            spec = spec_by_chart_id.get(cid)
            title = str(chart.get("title") or "")
            desc = str(chart.get("desc") or chart.get("description") or "")
            visible = f"{title} {desc}"
            if len(desc.strip()) < 18:
                shallow_desc.append(cid)
            if not spec:
                continue
            insight = spec.get("insight") or {}
            evidence_tokens = _number_tokens(insight.get("evidence") or "")
            finding_tokens = _number_tokens(insight.get("finding") or "")
            tokens = evidence_tokens | finding_tokens
            if tokens and not (_number_tokens(visible) & tokens):
                missing_evidence.append(cid)
    if shallow_desc:
        warn(f"차트 설명이 짧아 독자가 해석하기 어려울 수 있음: {shallow_desc[:6]}")
    if missing_evidence:
        warn(
            "dashboard_data 차트 설명이 chart_spec의 수치 근거를 충분히 전달하지 못함: "
            f"{missing_evidence[:6]}"
        )

def reader_facing_report_checks(outputs_dir):
    for report_name in ("summary_report.md", "deep_report.md"):
        path = pathlib.Path(outputs_dir) / report_name
        text = _read_optional_text(path)
        if not text:
            continue
        first_block = text[:1800]
        first_line = next((line.strip() for line in text.splitlines() if line.strip()), "")
        for term in PUBLIC_TITLE_FORBIDDEN_TERMS:
            if term.lower() in first_line.lower():
                block(f"{report_name} 제목 품질 실패: 내부 작업용 표현 '{term}' 포함")
        if RAW_ADMIN_CODE_RE.search(first_block):
            block(f"{report_name} 도입부에 행정동 코드가 visible 문장으로 노출됨 — 식별자는 부록/표로 이동")
        raw_columns = sorted(set(RAW_COLUMN_RE.findall(first_block)))
        if raw_columns:
            block(f"{report_name} 도입부에 원천 컬럼명 노출: {raw_columns[:5]}")
        hits = []
        for line in first_block.splitlines():
            hits.extend(_internal_term_hits(line))
        unique_hits = sorted(set(hits))
        if len(unique_hits) >= 4:
            warn(
                f"{report_name} 도입부 내부 용어 과다 노출({unique_hits}) — "
                "핵심 요약은 독자 언어로, 계산/lineage는 방법론·부록으로 분리 권장"
            )

def _load_manifest(data_path):
    p = pathlib.Path(data_path).resolve()
    candidates = [
        p.parent.parent / "manifest.json",
        p.parent / "manifest.json",
    ]
    for cand in candidates:
        if cand.exists():
            try:
                return json.loads(cand.read_text(encoding="utf-8"))
            except Exception as e:
                warn(f"manifest.json 읽기 실패({cand}): {e}")
                return {}
    return {}

def _read_json_if_exists(path):
    p = pathlib.Path(path)
    if not p.exists():
        return None
    try:
        return json.loads(p.read_text(encoding="utf-8"))
    except Exception as e:
        block(f"JSON 읽기 실패({p}): {e}")
        return None

def _report_config(manifest):
    report = (manifest.get("intake") or {}).get("report") or {}
    return {
        "depth": report.get("depth", "standard"),
        "audience": report.get("audience", "mixed"),
        "evidence_scope": report.get("evidence_scope", "data_only"),
    }

def _missing_keywords(text, required):
    missing = []
    hay = text or ""
    for label, terms in required:
        if not any(term in hay for term in terms):
            missing.append(label)
    return missing

def _missing_heading_sections(text, required):
    missing = []
    lines = [line.strip() for line in (text or "").splitlines()]
    headings = [re.sub(r"^#{1,6}\s*", "", line).strip() for line in lines if re.match(r"^#{1,6}\s+", line)]
    heading_blob = "\n".join(headings)
    for label, terms in required:
        if not any(term.lower() in heading_blob.lower() for term in terms):
            missing.append(label)
    return missing

def _normalize_for_compare(text):
    return re.sub(r"\s+", " ", (text or "").strip())

def _run_dir_for_data_path(data_path):
    return pathlib.Path(data_path).resolve().parent.parent

def _checkpoint_policy_candidates(run_dir):
    return [
        run_dir / "input" / "checkpoint_policy.json",
        run_dir / "checkpoint_policy.json",
    ]

def _load_checkpoint_policy(run_dir, run_manifest):
    policy = run_manifest.get("checkpoint_policy") if isinstance(run_manifest, dict) else None
    if isinstance(policy, dict):
        return policy, pathlib.Path("<manifest.checkpoint_policy>")
    for cand in _checkpoint_policy_candidates(run_dir):
        if cand.exists():
            return _read_json_if_exists(cand), cand
    return None, None

def _checkpoint_policy_allows_skip(policy):
    if not isinstance(policy, dict):
        return False
    mode = str(policy.get("mode") or "").strip()
    return mode in {"auto", "no_checkpoints"} and policy.get("explicit_skip") is True

def _run_context_candidates(run_dir):
    return [
        run_dir / "input" / "run_context.json",
        run_dir / "run_context.json",
    ]

def _load_run_context(run_dir, run_manifest):
    ctx = run_manifest.get("run_context") if isinstance(run_manifest, dict) else None
    if isinstance(ctx, dict):
        return ctx, pathlib.Path("<manifest.run_context>")
    for cand in _run_context_candidates(run_dir):
        if cand.exists():
            return _read_json_if_exists(cand), cand
    return None, None

def _normalize_reference_run(value):
    raw = str(value or "").strip().rstrip("/")
    if not raw:
        return ""
    if raw.startswith("runs/"):
        return pathlib.PurePosixPath(raw).name
    if "/runs/" in raw:
        return pathlib.PurePosixPath(raw).name
    return raw

def _prior_run_refs_from_text(text, current_run_id):
    refs = set()
    hay = str(text or "")
    for match in RUN_REF_RE.finditer(hay):
        ref = match.group(1)
        if ref and ref != current_run_id:
            refs.add(ref)
    for match in ABS_RUN_REF_RE.finditer(hay):
        ref = match.group(1)
        if ref and ref != current_run_id:
            refs.add(ref)
    return refs

def _collect_run_reference_texts(run_dir, data, chart_spec, run_manifest):
    texts = [
        ("dashboard_data.json", json.dumps(data, ensure_ascii=False)),
        ("manifest.json", json.dumps(run_manifest, ensure_ascii=False)),
    ]
    if chart_spec is not None:
        texts.append(("chart_spec.json", json.dumps(chart_spec, ensure_ascii=False)))
    for name in ("summary_report.md", "deep_report.md", "external_context.md"):
        path = run_dir / "outputs" / name
        if path.exists():
            texts.append((name, path.read_text(encoding="utf-8", errors="replace")))
    return texts

def run_context_checks(data_path, data, chart_spec=None):
    run_dir = _run_dir_for_data_path(data_path)
    run_manifest = _load_manifest(data_path)
    run_context, run_context_path = _load_run_context(run_dir, run_manifest)
    if run_context is None:
        warn("run_context.json 없음 — 새 분석의 prior-run 참조 정책을 증명할 수 없음")
        return

    root = pathlib.Path(__file__).resolve().parents[1]
    schema_path = root / "schemas" / "run_context.schema.json"
    if schema_path.exists():
        try:
            import jsonschema
            schema = json.loads(schema_path.read_text(encoding="utf-8"))
            jsonschema.validate(run_context, schema)
        except ModuleNotFoundError:
            warn("jsonschema 미설치 — run_context 스키마 검증 건너뜀")
        except Exception as e:
            block(f"run_context 스키마 검증 실패({run_context_path}): {str(e).splitlines()[0]}")

    current_run_id = run_dir.name
    refs_by_source = {}
    for label, text in _collect_run_reference_texts(run_dir, data, chart_spec, run_manifest):
        refs = _prior_run_refs_from_text(text, current_run_id)
        if refs:
            refs_by_source[label] = refs
    all_refs = sorted({ref for refs in refs_by_source.values() for ref in refs})
    if not all_refs:
        return

    allow_prior = run_context.get("allow_prior_run_reference") is True
    declared_refs = {
        _normalize_reference_run(item)
        for item in (run_context.get("reference_runs") or [])
    }
    declared_refs.discard("")
    if not allow_prior:
        details = "; ".join(f"{label}: {sorted(refs)}" for label, refs in sorted(refs_by_source.items()))
        block(
            "fresh_analysis run에서 기존 run 산출물 참조 감지: "
            f"{details} — 새 분석은 원천 데이터 또는 이번 run input snapshot만 사용해야 함"
        )
        return
    undeclared = sorted(set(all_refs) - declared_refs)
    if undeclared:
        block(
            "prior run 참조가 reference_runs[]에 선언되지 않음: "
            f"{undeclared} — 기존 run을 비교/수정 근거로 쓰려면 run_context.reference_runs에 명시 필요"
        )

def _checkpoint_answers_candidates(run_dir):
    return [
        run_dir / "checkpoint_answers.json",
        run_dir / "input" / "checkpoint_answers.json",
    ]

def _load_checkpoint_answers(run_dir):
    for cand in _checkpoint_answers_candidates(run_dir):
        if cand.exists():
            return _read_json_if_exists(cand), cand
    return None, None

def _checkpoint_question_exists(run_dir, checkpoint_id):
    base = CHECKPOINT_PREFIXES.get(checkpoint_id)
    if not base:
        return False
    checkpoint_dir = run_dir / "outputs" / "checkpoints"
    return (checkpoint_dir / f"{base}.json").exists() and (checkpoint_dir / f"{base}.md").exists()

def _checkpoint_question_json_path(run_dir, checkpoint_id):
    base = CHECKPOINT_PREFIXES.get(checkpoint_id)
    if not base:
        return None
    return run_dir / "outputs" / "checkpoints" / f"{base}.json"

def _sha256_file(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()

def _parse_iso_datetime(value):
    if not value:
        return None
    text = str(value)
    if text.endswith("Z"):
        text = text[:-1] + "+00:00"
    try:
        return datetime.fromisoformat(text)
    except ValueError:
        return None

def _recorded_path_matches(run_dir, recorded, actual_path):
    if not recorded:
        return False
    candidate = pathlib.Path(str(recorded))
    actual = pathlib.Path(actual_path).resolve()
    candidates = [candidate]
    if not candidate.is_absolute():
        kit_root = pathlib.Path(run_dir).resolve().parent.parent
        candidates.append(kit_root / candidate)
    return any(path.resolve() == actual for path in candidates)

def _latest_checkpoint_answers(answers):
    latest = {}
    for answer in (answers or {}).get("answers") or []:
        if not isinstance(answer, dict):
            continue
        # companion 레코드는 결정에서 제외 (interview-loop-v2 §4.3, M1) —
        # 승인 뒤 companion append가 최신 승인을 덮으면 안 된다.
        if answer.get("companion_id"):
            continue
        checkpoint_id = answer.get("checkpoint_id")
        if checkpoint_id:
            latest[str(checkpoint_id)] = answer
    return latest

def _is_human_checkpoint_approval(answer):
    if not isinstance(answer, dict):
        return False
    if answer.get("continue_pipeline") is not True:
        return False
    if answer.get("source") not in HUMAN_CONFIRMATION_SOURCES:
        return False
    if answer.get("human_confirmed") is not True:
        return False
    return bool(str(answer.get("user_response") or "").strip())

def _resolve_answer_question_path(run_dir, checkpoint_id, answer):
    """interview-loop-v2 §4.6: 답변이 라운드 2 질문(`.round2`)을 참조하면 유효 R2
    체인(§4.1 — prior_round.question_sha256이 현재 R1을 가리킴)을 검증한 뒤 그
    파일 기준으로 provenance를 검사한다. QA는 stage_guard와 독립적으로 같은
    규칙을 재계산한다. round3 이상 파일은 존재 자체가 BLOCK 사유다."""
    base = CHECKPOINT_PREFIXES.get(checkpoint_id)
    if not base:
        return None, [f"{checkpoint_id}: unknown checkpoint id"]
    checkpoint_dir = run_dir / "outputs" / "checkpoints"
    r1 = checkpoint_dir / f"{base}.json"
    r2 = checkpoint_dir / f"{base}.round2.json"
    issues = []
    for stray in sorted(checkpoint_dir.glob(f"{base}.round*.json")):
        if stray.name != r2.name:
            issues.append(f"{checkpoint_id}: 허용되지 않는 라운드 질문 파일 {stray.name} (추가 문답은 최대 2회)")
    qref = answer.get("question_ref") if isinstance(answer.get("question_ref"), dict) else {}
    ref_name = pathlib.Path(str(qref.get("path") or "")).name
    if ref_name and ref_name not in {r1.name, r2.name}:
        issues.append(f"{checkpoint_id}: 답변이 허용 집합 밖 질문 파일을 참조합니다 ({ref_name})")
        return r1, issues
    if ref_name != r2.name:
        return r1, issues
    if not r2.exists():
        issues.append(f"{checkpoint_id}: 답변이 참조한 라운드 2 질문 파일이 없습니다")
        return r1, issues
    question2 = _read_json_if_exists(r2) or {}
    loop = question2.get("interview_loop") if isinstance(question2.get("interview_loop"), dict) else {}
    prior = loop.get("prior_round") if isinstance(loop.get("prior_round"), dict) else {}
    if not r1.exists():
        issues.append(f"{checkpoint_id}: 라운드 2가 있는데 라운드 1 질문 파일이 없습니다")
    elif str(prior.get("question_sha256") or "") != _sha256_file(r1):
        issues.append(f"{checkpoint_id}: 라운드 2가 현재 라운드 1 질문을 가리키지 않습니다 (고아 라운드 2)")
    return r2, issues


def _checkpoint_answer_provenance_issues(run_dir, checkpoint_id, answer):
    issues = []
    if not isinstance(answer, dict):
        return [f"{checkpoint_id}: answer is not an object"]
    if answer.get("companion_id") or answer.get("loop_action"):
        issues.append(
            f"{checkpoint_id}: 탐색·수집 레코드(companion·자유 질문·방향 선택)는 승인이 될 수 없습니다 (불변식 I1)"
        )
    qpath, round_issues = _resolve_answer_question_path(run_dir, checkpoint_id, answer)
    issues.extend(round_issues)
    if qpath is None or not qpath.exists():
        issues.append(f"{checkpoint_id}: question JSON artifact missing")
        return issues
    question = _read_json_if_exists(qpath) or {}
    qref = answer.get("question_ref") if isinstance(answer.get("question_ref"), dict) else {}
    if answer.get("approval_contract_version") != "checkpoint-answer.v3":
        issues.append(f"{checkpoint_id}: approval_contract_version must be checkpoint-answer.v3")
    if answer.get("recorded_by") != CHECKPOINT_ANSWER_RECORDER:
        issues.append(f"{checkpoint_id}: recorded_by must be {CHECKPOINT_ANSWER_RECORDER}")
    if not answer.get("answer_id"):
        issues.append(f"{checkpoint_id}: answer_id missing")
    if answer.get("source") in {"user_chat", "ask_user_question"} and not str(answer.get("transcript_ref") or "").strip():
        issues.append(f"{checkpoint_id}: transcript_ref required for {answer.get('source')}")
    if not _recorded_path_matches(run_dir, qref.get("path"), qpath):
        issues.append(f"{checkpoint_id}: question_ref.path mismatch")
    if qref.get("sha256") != _sha256_file(qpath):
        issues.append(f"{checkpoint_id}: question_ref.sha256 mismatch")
    if not question.get("created_at"):
        issues.append(f"{checkpoint_id}: question created_at missing")
    if qref.get("created_at") != question.get("created_at"):
        issues.append(f"{checkpoint_id}: question_ref.created_at mismatch")
    answered_at = _parse_iso_datetime(answer.get("answered_at"))
    created_at = _parse_iso_datetime(question.get("created_at"))
    if answered_at is None:
        issues.append(f"{checkpoint_id}: answered_at missing or invalid")
    if created_at is None:
        issues.append(f"{checkpoint_id}: question created_at missing or invalid")
    if answered_at and created_at and answered_at <= created_at:
        issues.append(f"{checkpoint_id}: answered_at must be after question created_at")
    return issues

def _checkpoint_batch_approval_issues(required, latest):
    normalized = []
    for checkpoint_id in required:
        answer = latest.get(checkpoint_id) or {}
        response = re.sub(r"\s+", " ", str(answer.get("user_response") or "").strip()).lower()
        answered_at = str(answer.get("answered_at") or "")
        if response:
            normalized.append((checkpoint_id, response, answered_at))
    if len(normalized) < 2:
        return []
    responses = {item[1] for item in normalized}
    timestamps = {item[2] for item in normalized}
    generic_plan_responses = {
        "implement the proposed plan.",
        "implement the proposed plan",
        "please implement this plan.",
        "please implement this plan",
    }
    if len(responses) == 1 and len(timestamps) == 1:
        return [
            "multiple checkpoint approvals share the same user_response and answered_at; "
            "record each checkpoint only after showing that checkpoint to the user"
        ]
    if responses and responses.issubset(generic_plan_responses):
        return [
            "checkpoint approval reused a Plan-mode implementation phrase; "
            "middle checkpoints require checkpoint-specific user answers"
        ]
    return []

def _checkpoint_artifact_order_issues(run_dir, required, latest):
    issues = []
    for checkpoint_id in required:
        answer = latest.get(checkpoint_id) or {}
        answered_at = _parse_iso_datetime(answer.get("answered_at"))
        if answered_at is None:
            continue
        for rel in CHECKPOINT_DOWNSTREAM_ARTIFACTS.get(checkpoint_id, []):
            artifact = run_dir / rel
            if not artifact.exists():
                continue
            artifact_at = datetime.fromtimestamp(artifact.stat().st_mtime, tz=answered_at.tzinfo)
            if artifact_at < answered_at:
                issues.append(
                    f"{checkpoint_id}: downstream artifact {rel} was generated before checkpoint approval "
                    f"({artifact_at.isoformat()} < {answered_at.isoformat()})"
                )
    return issues

def _review_predicate_required(run_dir, manifest):
    """spec §9 술어 — QA 자체 재계산. method_route.json의 review_predicate 필드나
    에이전트 기록 플래그는 신뢰하지 않는다 (stage_guard와 독립 구현, 같은 규칙)."""
    matched = []
    route_data = _read_json_if_exists(run_dir / "outputs" / "method_route.json") or {}
    if str(route_data.get("route") or "") in DEEP_REVIEW_ROUTES:
        matched.append("route_requires_review")
    if (
        (run_dir / "input" / "domain_intake.json").exists()
        or manifest.get("domain_mode") is True
        or (_read_json_if_exists(run_dir / "input" / "run_context.json") or {}).get("domain_mode") is True
    ):
        matched.append("domain_mode")
    intake = manifest.get("intake") if isinstance(manifest.get("intake"), dict) else {}
    report = intake.get("report") if isinstance(intake.get("report"), dict) else {}
    if report.get("depth") == "deep":
        matched.append("report_depth_deep")
    if intake.get("analysis_mode") in DECISION_ANALYSIS_MODES:
        matched.append("decision_analysis_mode")
    return bool(matched), matched

def _required_checkpoints_for(run_dir, manifest, post_communicate):
    """기본 필수 checkpoint에 조건부 analysis_result_review를 실행 순서 위치
    (analysis_strategy 뒤, dashboard_storyboard 앞)에 삽입한다.

    legacy 경계 (spec §15): QA의 analysis_result_review 요구는 method_route.json이
    존재하는 v1 routing run에만 적용한다. routing 도입 이전 run은 제외한다.
    런타임 가드(stage_guard·hook)는 술어를 무조건 적용하므로 신규 run은 우회 불가."""
    base = REQUIRED_POST_REPORT_CHECKPOINTS if post_communicate else REQUIRED_PRE_REPORT_CHECKPOINTS
    if not (run_dir / "outputs" / "method_route.json").exists():
        return base
    if not _review_predicate_required(run_dir, manifest)[0]:
        return base
    required = []
    for checkpoint_id in base:
        if checkpoint_id == "dashboard_storyboard":
            required.append("analysis_result_review")
        required.append(checkpoint_id)
    return tuple(required)

def checkpoint_lineage_checks(data_path, post_communicate=False):
    run_dir = _run_dir_for_data_path(data_path)
    run_manifest = _load_manifest(data_path)
    if not run_manifest:
        block("run lineage 검증 실패: manifest.json 없음 — 공식 pipeline/checkpoint 경로를 증명할 수 없음")
        return

    policy, policy_path = _load_checkpoint_policy(run_dir, run_manifest)
    if _checkpoint_policy_allows_skip(policy):
        return
    if policy and not _checkpoint_policy_allows_skip(policy):
        warn(f"checkpoint_policy가 있지만 명시적 자동 실행 예외가 아님({policy_path}) — human checkpoint 증거를 검사함")

    answers, answers_path = _load_checkpoint_answers(run_dir)
    if answers is None:
        block(
            "human checkpoint lineage 누락: checkpoint_answers.json 없음 — "
            "공식 wrapper를 거치지 않고 최종 산출물이 생성됐을 가능성"
        )
        return
    latest = _latest_checkpoint_answers(answers)
    required = _required_checkpoints_for(run_dir, run_manifest, post_communicate)
    missing_questions = []
    missing_or_invalid_answers = []
    provenance_issues = []
    for checkpoint_id in required:
        if not _checkpoint_question_exists(run_dir, checkpoint_id):
            missing_questions.append(checkpoint_id)
        answer = latest.get(checkpoint_id)
        if not _is_human_checkpoint_approval(answer):
            missing_or_invalid_answers.append(checkpoint_id)
        else:
            provenance_issues.extend(_checkpoint_answer_provenance_issues(run_dir, checkpoint_id, answer))
    if missing_questions:
        block(
            "human checkpoint question artifact 누락: "
            f"{', '.join(missing_questions)} — outputs/checkpoints/*_question.json|md 필요"
        )
    if missing_or_invalid_answers:
        block(
            "human checkpoint 승인 증거 누락/무효: "
            f"{', '.join(missing_or_invalid_answers)} — {answers_path}에 "
            "source=user_chat|ask_user_question|manual_cli, human_confirmed=true, user_response, continue_pipeline=true 필요"
        )
    if provenance_issues:
        block(
            "human checkpoint 승인 provenance 무효: "
            + "; ".join(provenance_issues)
            + " — scripts/apply_checkpoint_answer.py로 질문별 실제 답변을 다시 기록해야 함"
        )
    batch_issues = _checkpoint_batch_approval_issues(required, latest)
    if batch_issues:
        block("human checkpoint 일괄 승인 의심: " + "; ".join(batch_issues))
    artifact_order_issues = _checkpoint_artifact_order_issues(run_dir, required, latest)
    if artifact_order_issues:
        block(
            "human checkpoint 승인 순서 무효: "
            + "; ".join(artifact_order_issues)
            + " — checkpoint 승인 후 해당 단계 산출물을 다시 생성해야 함"
        )

def interview_loop_checks(data_path):
    """interview-loop-v2 §9 QA 확장: canonical/mirror 정합, 불변식 I1, 자유 질문
    예산·미니 결과 provenance, 라운드 파일 스윕(round3+ BLOCK·고아 R2 WARN),
    파생 domain_intake 무결성, 미니 결과 직접 인용 WARN(§7)."""
    run_dir = _run_dir_for_data_path(data_path)
    run_manifest = _load_manifest(data_path) or {}
    policy, _policy_path = _load_checkpoint_policy(run_dir, run_manifest)
    if _checkpoint_policy_allows_skip(policy):
        return

    canonical = run_dir / "checkpoint_answers.json"
    mirror = run_dir / "input" / "checkpoint_answers.json"
    if mirror.exists():
        if not canonical.exists():
            block("checkpoint 답변 mirror가 canonical 없이 존재 (fail-closed) — interview-loop-v2 §4.3")
        elif canonical.read_bytes() != mirror.read_bytes():
            block("checkpoint 답변 canonical/mirror 불일치 (fail-closed) — scripts/apply_checkpoint_answer.py로 재기록 필요")
    answers_doc = _read_json_if_exists(canonical) or {}
    records = [a for a in (answers_doc.get("answers") or []) if isinstance(a, dict)]
    known_ids = {str(a.get("answer_id")) for a in records if a.get("answer_id")}

    # 전달 순서(턴 분리) 감사: 팝업 답변은 핸드오프 출력 스탬프를 동반해야 한다.
    # 기록 시점 fail-closed가 1차 게이트 — 여기서는 수기 편집 우회를 WARN으로 표시
    # (스탬프 도입 전 legacy run 호환을 위해 BLOCK하지 않음).
    for a in records:
        if a.get("source") == "ask_user_question" and not a.get("handoff_printed_at"):
            warn(
                f"checkpoint '{a.get('checkpoint_id')}' 팝업 답변에 핸드오프 출력 스탬프 없음 "
                "(handoff_printed_at) — 근거 출력 선행 여부를 확인할 수 없음"
            )

    for a in records:
        if (a.get("companion_id") or a.get("loop_action")) and a.get("continue_pipeline") is True:
            block(
                "불변식 I1 위반: 탐색·수집 레코드가 continue_pipeline=true "
                f"({a.get('checkpoint_id')}/{a.get('answer_id')})"
            )

    free_counts = {}
    for a in records:
        if a.get("loop_action") == "free_question":
            key = (str(a.get("checkpoint_id")), int(a.get("interview_round") or 1))
            free_counts[key] = free_counts.get(key, 0) + 1
    for (cp, rnd), n in sorted(free_counts.items()):
        if n > 1:
            block(f"자유 질문이 라운드당 1개를 초과: {cp} round {rnd} ({n}개) — interview-loop-v2 D3")

    checkpoint_dir = run_dir / "outputs" / "checkpoints"
    if checkpoint_dir.is_dir():
        for checkpoint_id, base in CHECKPOINT_PREFIXES.items():
            r1 = checkpoint_dir / f"{base}.json"
            r2 = checkpoint_dir / f"{base}.round2.json"
            for stray in sorted(checkpoint_dir.glob(f"{base}.round*.json")):
                if stray.name != r2.name:
                    block(f"허용되지 않는 라운드 질문 파일: {stray.name} (추가 문답은 최대 2회)")
            if r2.exists():
                q2 = _read_json_if_exists(r2) or {}
                loop = q2.get("interview_loop") if isinstance(q2.get("interview_loop"), dict) else {}
                prior = loop.get("prior_round") if isinstance(loop.get("prior_round"), dict) else {}
                if not r1.exists() or str(prior.get("question_sha256") or "") != _sha256_file(r1):
                    warn(f"고아 라운드 2 질문 파일: {r2.name} — 현재 라운드 1과 연결되지 않음 (반려 재생성 흔적)")
                elif str(prior.get("answer_id") or "") not in known_ids:
                    block(f"라운드 1 답변 기록 없이 라운드 2 질문 존재 (위조 의심): {r2.name}")

    mini_rows = []
    exploration = run_dir / "outputs" / "exploration"
    if exploration.is_dir():
        for meta_path in sorted(exploration.glob("free_question_*.json")):
            meta = _read_json_if_exists(meta_path) or {}
            answer_id = str(meta.get("answer_id") or "")
            match = next((a for a in records if str(a.get("answer_id")) == answer_id), None)
            if match is None:
                block(f"미니 결과가 존재하지 않는 답변을 참조: {meta_path.name}")
                continue
            if match.get("loop_action") != "free_question":
                block(f"미니 결과가 자유 질문이 아닌 답변에 연결됨: {meta_path.name}")
            created = _parse_iso_datetime(meta.get("created_at"))
            answered = _parse_iso_datetime(match.get("answered_at"))
            if created and answered and created <= answered:
                block(f"미니 결과가 질문 기록보다 먼저 생성됨 (순서 위반): {meta_path.name}")
            md_path = meta_path.with_suffix(".md")
            if md_path.exists():
                for line in md_path.read_text(encoding="utf-8").splitlines():
                    stripped = line.strip()
                    if stripped.startswith("|") and not set(stripped) <= set("|-: "):
                        mini_rows.append(re.sub(r"\s+", "", stripped))

    if mini_rows:
        targets = []
        for name in ("summary_report.md", "deep_report.md"):
            report_path = run_dir / "outputs" / name
            if report_path.exists():
                targets.append((name, re.sub(r"\s+", "", report_path.read_text(encoding="utf-8"))))
        data_doc = _read_json_if_exists(pathlib.Path(data_path)) or {}
        targets.append(("dashboard_data.json", re.sub(r"\s+", "", json.dumps(data_doc, ensure_ascii=False))))
        for row in mini_rows:
            if len(row) < 8:
                continue
            for name, blob in targets:
                if row in blob:
                    warn(
                        f"미니 결과 표 행이 {name}에 직접 인용된 것으로 보임 — 공식 산출물은 "
                        "분석 경로에서 재계산해야 함 (interview-loop-v2 §7)"
                    )
                    break

    intake = _read_json_if_exists(run_dir / "input" / "domain_intake.json") or {}
    if intake.get("generated_by"):
        if intake.get("generated_by") != "scripts/build_domain_intake.py":
            block(f"파생 domain 확인 정보의 생성기 표기가 계약과 다름: {intake.get('generated_by')}")
        source_ids = intake.get("source_answer_ids") or []
        if not source_ids:
            block("파생 domain 확인 정보에 근거 답변 목록(source_answer_ids)이 없음")
        for sid in source_ids:
            match = next((a for a in records if str(a.get("answer_id")) == str(sid)), None)
            if match is None:
                block(f"파생 domain 확인 정보가 존재하지 않는 답변을 근거로 함: {sid}")
            elif not match.get("companion_id") or not (match.get("maps_to") or {}).get("domain_field"):
                block(f"파생 domain 확인 정보의 근거가 추가 확인 질문 답변이 아님: {sid}")


def _external_manifest_candidates(data_path, run_manifest):
    run_dir = _run_dir_for_data_path(data_path)
    candidates = []
    raw = run_manifest.get("external_denominators") if isinstance(run_manifest, dict) else None
    if isinstance(raw, str) and raw.strip():
        raw_path = pathlib.Path(raw).expanduser()
        if raw_path.is_absolute():
            candidates.append(raw_path)
        else:
            candidates.extend([pathlib.Path.cwd() / raw_path, run_dir / raw_path])
    candidates.extend([
        run_dir / "external_denominators.json",
        run_dir / "input" / "external_denominator_manifest.json",
    ])
    out, seen = [], set()
    for cand in candidates:
        key = str(cand)
        if key not in seen:
            seen.add(key)
            out.append(cand)
    return out

def _load_external_manifest(data_path, run_manifest):
    raw = run_manifest.get("external_denominators") if isinstance(run_manifest, dict) else None
    if isinstance(raw, dict):
        return raw, pathlib.Path("<manifest.external_denominators>")
    for cand in _external_manifest_candidates(data_path, run_manifest):
        if cand.exists():
            try:
                return json.loads(cand.read_text(encoding="utf-8")), cand
            except Exception as e:
                block(f"external context manifest 읽기 실패({cand}): {e}")
                return None, cand
    return None, None

def _external_adapter_plan_candidates(data_path):
    run_dir = _run_dir_for_data_path(data_path)
    return [
        run_dir / "input" / "external_adapter_plan.json",
        run_dir / "external_adapter_plan.json",
    ]

def _source_api_manifest_candidates(data_path):
    run_dir = _run_dir_for_data_path(data_path)
    return [
        run_dir / "input" / "source_api_manifest.json",
        run_dir / "source_api_manifest.json",
    ]

def _load_source_api_manifest(data_path):
    for cand in _source_api_manifest_candidates(data_path):
        if cand.exists():
            try:
                return json.loads(cand.read_text(encoding="utf-8")), cand
            except Exception as e:
                block(f"source_api_manifest 읽기 실패({cand}): {e}")
                return None, cand
    return None, None

def _load_external_adapter_plan(data_path):
    for cand in _external_adapter_plan_candidates(data_path):
        if cand.exists():
            try:
                return json.loads(cand.read_text(encoding="utf-8")), cand
            except Exception as e:
                block(f"external adapter plan 읽기 실패({cand}): {e}")
                return None, cand
    return None, None

def _manifest_source_ids(manifest):
    ids = set()
    for src in (manifest.get("sources") or []):
        if isinstance(src, dict) and src.get("id"):
            ids.add(str(src["id"]))
    return ids

def _metric_source_refs(data):
    refs = set()
    for kpi in data.get("kpis", []):
        metric = kpi.get("metric") or {}
        if metric.get("source_ref"):
            refs.add(str(metric["source_ref"]))
    for panel in data.get("panels", []):
        for chart in panel.get("charts", []):
            for series in ((chart.get("encoding") or {}).get("series") or []):
                metric = series.get("metric") or {}
                if metric.get("source_ref"):
                    refs.add(str(metric["source_ref"]))
    return refs

def external_adapter_plan_checks(data_path):
    plan, plan_path = _load_external_adapter_plan(data_path)
    if plan is None:
        return

    root = pathlib.Path(__file__).resolve().parent.parent
    schema_path = root / "schemas" / "external_adapter_plan.schema.json"
    try:
        import jsonschema
        schema = json.loads(schema_path.read_text(encoding="utf-8"))
        jsonschema.validate(plan, schema)
    except ImportError:
        warn("jsonschema 미설치 — external_adapter_plan 스키마 검증 건너뜀")
    except Exception as e:
        block(f"external_adapter_plan 스키마 검증 실패({plan_path}): {str(e).splitlines()[0]}")
        return

    selected = set(plan.get("selected_categories") or [])
    available = set(plan.get("available_categories") or [])
    unavailable = set(plan.get("unavailable_categories") or [])
    unknown = selected - available - unavailable
    if unknown:
        warn(f"external_adapter_plan selected category가 available/unavailable 어디에도 없음: {sorted(unknown)}")
    extra_available = available - selected
    if extra_available:
        warn(f"external_adapter_plan available category가 selected에 없음: {sorted(extra_available)}")

    run_manifest = _load_manifest(data_path)
    ext_manifest, _ = _load_external_manifest(data_path, run_manifest)
    manifest_categories = {
        str(adapter.get("category"))
        for adapter in ((ext_manifest or {}).get("adapters") or [])
        if isinstance(adapter, dict) and adapter.get("category")
    }
    if available and not manifest_categories:
        warn("external_adapter_plan에 available_categories가 있지만 external context manifest가 없음")
    missing_manifest = available - manifest_categories
    if missing_manifest:
        warn(f"external_adapter_plan available category가 external context manifest에 없음: {sorted(missing_manifest)}")

def source_api_manifest_checks(data_path, data):
    manifest, manifest_path = _load_source_api_manifest(data_path)
    if manifest is None:
        return

    root = pathlib.Path(__file__).resolve().parent.parent
    schema_path = root / "schemas" / "source_api_manifest.schema.json"
    try:
        import jsonschema
        schema = json.loads(schema_path.read_text(encoding="utf-8"))
        jsonschema.validate(manifest, schema)
    except ImportError:
        warn("jsonschema 미설치 — source_api_manifest 스키마 검증 건너뜀")
    except Exception as e:
        block(f"source_api_manifest 스키마 검증 실패({manifest_path}): {str(e).splitlines()[0]}")
        return

    status = manifest.get("status")
    source = manifest.get("source") or {}
    auth = manifest.get("auth") or {}
    acquisition = manifest.get("acquisition") or {}
    snapshot = manifest.get("snapshot") or {}
    source_ref = ((manifest.get("lineage") or {}).get("source_ref") or "").strip()

    if source.get("adapter") != "primary_api":
        block(f"source_api_manifest source.adapter가 primary_api가 아님: {source.get('adapter')}")
    if auth.get("secret_material_stored") is not False:
        block("source_api_manifest auth.secret_material_stored는 false여야 함 — API 키를 산출물에 저장하지 말 것")

    request_url = str(source.get("request_url") or "")
    endpoint_url = str(source.get("endpoint_url") or "")
    for label, url in (("request_url", request_url), ("endpoint_url", endpoint_url)):
        match = re.search(r"(serviceKey|apiKey|apikey|key)=([^&\\s]+)", url, flags=re.I)
        if match and match.group(2) not in {"${SERVICE_KEY}", "${PUBLIC_DATA_API_KEY}", "<redacted>", "REDACTED"}:
            block(f"source_api_manifest {label}에 API 키로 보이는 query 값이 노출됨")

    collected_statuses = {"collected", "available"}
    if status in {"planned", "smoke_tested"}:
        block(
            f"source_api_manifest status={status} — primary API 원천이 스냅샷으로 고정되기 전 산출물이 생성됨. "
            "connect 단계에서 smoke test, pagination, snapshot manifest 업데이트가 필요함"
        )
    if status == "blocked":
        blocker = manifest.get("blocker") or {}
        block(f"primary API source blocker: {blocker.get('type', 'unknown')} — {blocker.get('message', 'no message')}")

    if status in collected_statuses:
        if acquisition.get("pagination_checked") is not True:
            block("source_api_manifest collected/available 이지만 acquisition.pagination_checked가 true가 아님")
        row_count = snapshot.get("row_count")
        if not isinstance(row_count, int) or row_count <= 0:
            block("source_api_manifest collected/available 이지만 snapshot.row_count가 양수가 아님")
        if not snapshot.get("path"):
            block("source_api_manifest collected/available 이지만 snapshot.path가 비어 있음")
        else:
            snapshot_path = pathlib.Path(str(snapshot["path"]))
            root_candidates = [
                pathlib.Path.cwd(),
                pathlib.Path(__file__).resolve().parent.parent,
                _run_dir_for_data_path(data_path),
            ]
            exists = snapshot_path.exists() if snapshot_path.is_absolute() else any((root / snapshot_path).exists() for root in root_candidates)
            if not exists:
                warn(f"source_api_manifest snapshot.path 파일 존재 확인 실패: {snapshot['path']}")
        if not snapshot.get("columns"):
            warn("source_api_manifest snapshot.columns가 비어 있음")

    dashboard_source_ids = {str(s.get("id")) for s in data.get("sources", []) if s.get("id")}
    if source_ref and status in collected_statuses and source_ref not in dashboard_source_ids:
        warn(f"primary API source_ref '{source_ref}'가 dashboard_data.sources[]에 직접 연결되지 않음")

def _adapter_allowed_layers(category):
    return CATEGORY_ALLOWED_METRIC_LAYERS.get(category, CATEGORY_ALLOWED_METRIC_LAYERS.get("custom", set()))

def _adapter_is_coarse(adapter):
    spatial_grain = adapter.get("spatial_grain")
    grain_quality = adapter.get("grain_quality") or {}
    join_keys = adapter.get("join_keys") or []
    join_quality = {jk.get("quality") for jk in join_keys if isinstance(jk, dict)}
    return (
        spatial_grain in COARSE_GRAINS
        or bool(join_quality & COARSE_JOIN_QUALITIES)
        or grain_quality.get("coarse_aggregation") is True
        or grain_quality.get("denominator_aggregation_basis") in {"not_summed", "weighted"}
    )

def _contains_any(text, terms):
    hay = text or ""
    return any(term in hay for term in terms)

def _chart_text(chart, spec_by_chart_id):
    parts = [
        chart.get("id"),
        chart.get("title"),
        chart.get("subtitle"),
        ((chart.get("encoding") or {}).get("x") or {}).get("label"),
    ]
    parts.extend(series.get("label") for series in ((chart.get("encoding") or {}).get("series") or []))
    spec = spec_by_chart_id.get(chart.get("id"))
    if spec:
        parts.extend([
            spec.get("id"),
            spec.get("question"),
            spec.get("method"),
            (spec.get("calculation") or {}).get("metric_definition"),
        ])
    return " ".join(str(p) for p in parts if p)

def rank_overflow_checks(data, chart_spec=None):
    spec_by_chart_id = {}
    if chart_spec:
        for spec in chart_spec.get("charts", []):
            mapped = (spec.get("dashboard_mapping") or {}).get("chart_id") or spec.get("id")
            if mapped:
                spec_by_chart_id[str(mapped)] = spec
    for panel in data.get("panels", []):
        for chart in panel.get("charts", []):
            text = _chart_text(chart, spec_by_chart_id).lower()
            if not any(term.lower() in text for term in RANK_TERMS):
                continue
            values = []
            x_values = ((chart.get("encoding") or {}).get("x") or {}).get("values") or []
            values.extend(x_values)
            for series in ((chart.get("encoding") or {}).get("series") or []):
                values.extend(series.get("values") or [])
            suspicious = []
            for value in values:
                if isinstance(value, (int, float)) and math.isfinite(value) and abs(value) > RANK_OVERFLOW_ABS_LIMIT:
                    suspicious.append(value)
            if suspicious:
                block(
                    f"차트 '{chart.get('id')}' 순위 차이 값이 비정상적으로 큼({suspicious[:3]}) — "
                    "rank_delta unsigned overflow 의심"
                )

def _all_dashboard_charts(data):
    charts = []
    for panel in data.get("panels") or []:
        charts.extend(panel.get("charts") or [])
    return charts

def _chart_is_time_or_status(chart):
    encoding = chart.get("encoding") or {}
    x = encoding.get("x") or {}
    return chart.get("type") in TIME_STATUS_CHART_TYPES or x.get("type") == "time"

def profile_v4_contract_checks(data):
    """v4 E1 계약 (spec dashboard-profile-v4 §4.0~4.2): 델타/스파크 provenance는
    구조로 검증한다 — source_id는 sources[].id 대조, periods는 정렬·중복·길이,
    trend 마지막 point와 value는 Decimal 공식으로 정합 검사. 필드가 없는
    legacy 데이터는 전부 no-op."""
    from decimal import Decimal

    source_ids = {s.get("id") for s in (data.get("sources") or [])}

    def _check_provenance(label, prov, expected_len):
        if not isinstance(prov, dict):
            block(f"{label}: provenance 구조 누락 (source_id/time_field/periods)")
            return
        if prov.get("source_id") not in source_ids:
            block(f"{label}: provenance.source_id '{prov.get('source_id')}'가 sources에 없음")
        periods = prov.get("periods") or []
        if expected_len is not None and len(periods) != expected_len:
            block(f"{label}: provenance.periods 길이 {len(periods)} ≠ 기대 {expected_len}")
        if len(set(periods)) != len(periods):
            block(f"{label}: provenance.periods에 중복 기간 존재")
        elif sorted(periods) != list(periods):
            block(f"{label}: provenance.periods가 오름차순이 아님")

    for kpi in data.get("kpis") or []:
        kid = kpi.get("id")
        trend = kpi.get("trend")
        if isinstance(trend, dict):
            points = trend.get("points") or []
            if not all(
                isinstance(pt, (int, float)) and not isinstance(pt, bool) and math.isfinite(pt)
                for pt in points
            ):
                block(f"KPI '{kid}' trend.points에 숫자가 아니거나 비유한 값 존재")
                continue
            _check_provenance(f"KPI '{kid}' trend", trend.get("provenance"), len(points))
            value = kpi.get("value")
            precision = (kpi.get("format") or {}).get("precision")
            if not isinstance(value, (int, float)) or isinstance(value, bool):
                block(f"KPI '{kid}': trend가 있으면 value는 number여야 함 (문자열 KPI는 스파크 없이 플랫 강등)")
            elif not isinstance(precision, int) or isinstance(precision, bool):
                block(f"KPI '{kid}': trend가 있으면 format.precision(정수) 필수")
            elif points:
                tolerance = Decimal(5) / (Decimal(10) ** (precision + 1))
                if abs(Decimal(str(points[-1])) - Decimal(str(value))) > tolerance:
                    block(
                        f"KPI '{kid}': trend 마지막 point({points[-1]})와 value({value})가 "
                        f"precision {precision} 허용 오차(±{tolerance})를 벗어남"
                    )
        comparison = kpi.get("comparison")
        if isinstance(comparison, dict) and comparison.get("kind") == "period_delta":
            basis = comparison.get("basis")
            if not (isinstance(basis, str) and basis.strip()):
                block(f"KPI '{kid}' comparison(period_delta): basis 누락")
            delta = comparison.get("delta")
            direction = comparison.get("direction")
            if not isinstance(delta, (int, float)) or isinstance(delta, bool) or direction not in ("up", "down", "flat"):
                block(f"KPI '{kid}' comparison(period_delta): delta/direction 누락 또는 형식 오류")
            else:
                expected = "up" if delta > 0 else "down" if delta < 0 else "flat"
                if direction != expected:
                    block(
                        f"KPI '{kid}' comparison(period_delta): delta {delta} 부호와 "
                        f"direction '{direction}' 불일치"
                    )
            _check_provenance(f"KPI '{kid}' comparison", comparison.get("provenance"), 2)

    # E4: 스몰 멀티플 (spec §4.3) — panel 내부 한정, 2~9, type 제한, 축 일치
    allowed_types = {"line", "area", "bar"}
    group_to_panels: dict = {}
    all_chart_ids: list = []
    for p in data.get("panels") or []:
        pid = p.get("id")
        local_groups: dict = {}
        for ch in p.get("charts") or []:
            all_chart_ids.append(str(ch.get("id")))
            group = ch.get("small_multiple_group")
            if group:
                local_groups.setdefault(group, []).append(ch)
        for group, chs in local_groups.items():
            group_to_panels.setdefault(group, []).append(pid)
            if not (2 <= len(chs) <= 9):
                block(f"panel '{pid}' 스몰 멀티플 그룹 '{group}' 크기 {len(chs)} — 2~9만 허용")
            types = {ch.get("type") for ch in chs}
            if not types <= allowed_types:
                block(f"panel '{pid}' 그룹 '{group}'에 허용 밖 type {sorted(types - allowed_types)} — line/area/bar만")
            elif len(types) > 1:
                block(f"panel '{pid}' 그룹 '{group}' 내 chart type 불일치: {sorted(types)}")
            x_types = {((ch.get("encoding") or {}).get("x") or {}).get("type") for ch in chs}
            if len(x_types) > 1:
                block(f"panel '{pid}' 그룹 '{group}' 내 x축 유형 불일치: {sorted(str(t) for t in x_types)}")
            unit_sets = {
                tuple(sorted({str(se.get("unit")) for se in ((ch.get("encoding") or {}).get("series") or [])}))
                for ch in chs
            }
            if len(unit_sets) > 1:
                block(f"panel '{pid}' 그룹 '{group}' 내 series unit 불일치")
    for group, pids in group_to_panels.items():
        if len(pids) > 1:
            block(f"스몰 멀티플 그룹 '{group}'가 여러 panel에 걸침 {pids} — panel 내부 한정 (spec §4.3)")
    duplicated = sorted({cid for cid in all_chart_ids if all_chart_ids.count(cid) > 1})
    if duplicated:
        block(f"chart id 전역 중복: {duplicated} — 그룹 참조 안정성 훼손")

    # E5: cell_gradient (spec §4.4) — 인덱스 범위·number 열만
    for p in data.get("panels") or []:
        table = p.get("table")
        if not isinstance(table, dict):
            continue
        grad = table.get("cell_gradient")
        if not isinstance(grad, dict):
            continue
        columns = table.get("columns") or []
        for ci in grad.get("value_column_indices") or []:
            if not isinstance(ci, int) or ci < 0 or ci >= len(columns):
                block(f"panel '{p.get('id')}' cell_gradient 인덱스 {ci} — columns 범위 밖")
            elif (columns[ci] or {}).get("type") != "number":
                block(
                    f"panel '{p.get('id')}' cell_gradient 열 {ci}"
                    f"('{(columns[ci] or {}).get('name')}') type이 number가 아님"
                )

    # spec §7.2 WARN: v4 계약 선언의 이행·밀도 점검
    meta = data.get("meta") or {}
    if meta.get("dashboard_profile_contract") == "v4":
        panels = data.get("panels") or []
        kpis = data.get("kpis") or []
        has_e1 = any(
            isinstance(kpi.get("trend"), dict)
            or (isinstance(kpi.get("comparison"), dict) and kpi["comparison"].get("kind") == "period_delta")
            for kpi in kpis
        )
        has_group = any(ch.get("small_multiple_group") for p in panels for ch in (p.get("charts") or []))
        has_gradient = any(
            isinstance(p.get("table"), dict) and p["table"].get("cell_gradient") for p in panels
        )
        has_surface = any(p.get("surface") for p in panels)
        if not (has_e1 or has_group or has_gradient or has_surface):
            warn("v4 계약 선언인데 E1~E5 요소가 하나도 없음 — 계약 선언만 있고 이행 없음")
        if meta.get("dashboard_profile") == "analyst_workspace":
            primary = [p for p in panels if (p.get("surface") or "primary") == "primary"]
            first_screen = (
                (1 if kpis else 0)
                + sum(len(p.get("charts") or []) for p in primary)
                + sum(1 for p in primary if p.get("table"))
            )
            if first_screen >= 9:
                warn(
                    f"analyst v4 첫 화면 패널 수 {first_screen} — 목표 상한(8) 초과, "
                    "일부 패널의 surface=detail 강등 검토"
                )


def profile_v4_plan_alignment_checks(data, chart_spec):
    """v4 계획-이행 일치 (spec §4.5, Codex M10): 표현 결정은 chart_spec에 먼저
    기록되고 dashboard_data가 이행한다. 어긋나면 BLOCK, 필드가 없으면 no-op."""
    meta = data.get("meta") or {}
    design = chart_spec.get("dashboard_design") or {}
    plan_v4 = design.get("contract_version") == "v4"
    exec_v4 = meta.get("dashboard_profile_contract") == "v4"
    if plan_v4 != exec_v4:
        block(
            "v4 계약 선언 불일치: chart_spec dashboard_design.contract_version="
            f"{'v4' if plan_v4 else '없음'} vs dashboard_data meta.dashboard_profile_contract="
            f"{'v4' if exec_v4 else '없음'}"
        )

    data_chart_group = {}
    chart_panel = {}
    for p in data.get("panels") or []:
        for ch in p.get("charts") or []:
            data_chart_group[str(ch.get("id"))] = ch.get("small_multiple_group")
            chart_panel[str(ch.get("id"))] = p
    for spec in chart_spec.get("charts") or []:
        mapping = spec.get("dashboard_mapping") if isinstance(spec.get("dashboard_mapping"), dict) else {}
        cid = str(mapping.get("chart_id") or "")
        if cid not in data_chart_group:
            continue  # 미매핑 chart는 기존 missing_specs 검사가 담당
        plan_group = mapping.get("small_multiple_group")
        exec_group = data_chart_group[cid]
        if (plan_group or exec_group) and plan_group != exec_group:
            block(f"chart '{cid}' 스몰 멀티플 계획({plan_group}) ≠ 이행({exec_group}) — 표현 결정은 chart_spec 우선")
        plan_surface = mapping.get("surface")
        if plan_surface:
            panel = chart_panel[cid]
            exec_surface = panel.get("surface") or "primary"
            if plan_surface != exec_surface:
                block(
                    f"chart '{cid}' surface 계획({plan_surface}) ≠ "
                    f"panel '{panel.get('id')}' 이행({exec_surface})"
                )


def dashboard_profile_checks(data, chart_spec=None):
    profile = (data.get("meta") or {}).get("dashboard_profile", "executive_brief")
    if profile not in DASHBOARD_PROFILES:
        block(f"dashboard_data.meta.dashboard_profile '{profile}'는 허용 프로필이 아님")
        return

    panels = data.get("panels") or []
    first_panel = panels[0] if panels else {}
    first_charts = first_panel.get("charts") or []
    all_charts = _all_dashboard_charts(data)
    kpis = data.get("kpis") or []
    first_has_table = bool(first_panel.get("table"))
    has_table = any(panel.get("table") for panel in panels)

    if profile == "executive_brief":
        if not kpis:
            warn("executive_brief 프로필인데 KPI가 없음 — 첫 화면 요약력이 약할 수 있음")
        if not first_charts:
            warn("executive_brief 프로필인데 첫 패널에 핵심 차트가 없음")
        if len(first_charts) > 4 or len(all_charts) > 8 or (first_has_table and len(first_charts) > 2):
            warn("executive_brief 프로필치고 첫 화면/전체 차트가 많음 — 핵심 KPI와 1-2개 메인 차트 중심으로 축소 권장")

    if profile == "analyst_workspace":
        if len(all_charts) < 4 and not has_table:
            warn("analyst_workspace 프로필인데 차트/표가 적어 탐색형 화면으로 보기 어려움")
        if len(all_charts) >= 4 and not any(chart.get("type") in DIAGNOSTIC_CHART_TYPES for chart in all_charts):
            warn("analyst_workspace 프로필인데 heatmap/scatter/table/분포/예외 계열 진단 차트가 부족함")

    if profile == "operations_monitor":
        has_comparison = any(kpi.get("comparison") for kpi in kpis)
        has_time_or_status = any(_chart_is_time_or_status(chart) for chart in all_charts)
        if not has_comparison:
            warn("operations_monitor 프로필인데 KPI 전 기간 비교가 없음")
        if not has_time_or_status:
            warn("operations_monitor 프로필인데 시간/상태 변화 차트가 없음")
        if not (has_comparison or has_time_or_status):
            warn("operations_monitor 프로필은 반복 지표나 상태 변화가 있을 때 가장 적합함")

    if not chart_spec:
        return
    design = chart_spec.get("dashboard_design") or {}
    selected = design.get("selected_profile")
    if selected is None:
        warn("chart_spec.dashboard_design.selected_profile 누락 — storyboard에서 디자인 프로필 추천을 남기는 것을 권장")
        return
    if selected not in DASHBOARD_PROFILES:
        block(f"chart_spec.dashboard_design.selected_profile '{selected}'는 허용 프로필이 아님")
        return
    if selected != profile:
        block(
            "chart_spec.dashboard_design.selected_profile "
            f"'{selected}'와 dashboard_data.meta.dashboard_profile '{profile}'가 불일치"
        )

def template_static_checks(template_path):
    try:
        text = pathlib.Path(template_path).read_text(encoding="utf-8")
    except Exception as exc:
        warn(f"dashboard template 정적 검사 건너뜀: {exc}")
        return
    if "PROFILE_LABELS" in text:
        block("dashboard.html이 PROFILE_LABELS를 통해 내부 프로필 라벨을 노출할 수 있음")
    for term in PROFILE_LABEL_VISIBLE_TERMS:
        if term in text:
            block(f"dashboard.html에 내부 프로필 라벨 '{term}' 문자열이 남아 있음")
    if 'content:"DIK"' in text or "content:'DIK'" in text:
        warn("operations_monitor 레일에 내부 브랜드 텍스트가 노출될 수 있음")
    for fn in ("renderExecutivePanel", "renderAnalystPanel", "renderOperationsPanel"):
        if fn not in text:
            warn(f"dashboard.html에 프로필별 layout renderer '{fn}'가 없음")

def _assertive_forbidden_lines(text):
    lines = []
    for line in (text or "").splitlines():
        stripped = line.strip()
        if not stripped:
            continue
        for term in ASSERTIVE_FORBIDDEN_TERMS:
            if term in stripped and not any(safe in stripped for safe in SAFE_FORBIDDEN_CONTEXT_TERMS):
                lines.append((term, stripped))
                break
    return lines

def _forbidden_term_should_block(term, adapter_categories, has_external_manifest):
    if not has_external_manifest:
        return True
    if "확정" in term:
        return True
    return False

def _analysis_text_bundle(data_path, include_reports):
    outputs_dir = pathlib.Path(data_path).resolve().parent
    paths = [outputs_dir / "04_analysis.md"]
    if include_reports:
        paths.extend([outputs_dir / "summary_report.md", outputs_dir / "deep_report.md"])
    texts = []
    for path in paths:
        text = _read_optional_text(path)
        if text:
            texts.append((path.name, text))
    return texts

def terminology_guard_checks(data_path, data, has_external_manifest, adapter_categories, post_communicate=False):
    texts = _analysis_text_bundle(data_path, include_reports=post_communicate)
    dashboard_blob = json.dumps(data, ensure_ascii=False)
    texts.append(("dashboard_data.json", dashboard_blob))
    should_block = not has_external_manifest
    for name, text in texts:
        lines = _assertive_forbidden_lines(text)
        if not lines:
            continue
        sample = "; ".join(f"{term}: {line[:120]}" for term, line in lines[:2])
        if should_block or any(_forbidden_term_should_block(term, adapter_categories, has_external_manifest) for term, _ in lines):
            block(f"금지 해석 표현 감지({name}): {sample}")
        else:
            warn(f"외부 context 결론 표현 확인 필요({name}): {sample}")

def external_denominator_checks(data_path, data, chart_spec=None, post_communicate=False):
    run_manifest = _load_manifest(data_path)
    ext_manifest, ext_path = _load_external_manifest(data_path, run_manifest)
    adapter_categories = []

    if ext_manifest is None:
        terminology_guard_checks(data_path, data, False, adapter_categories, post_communicate=post_communicate)
        rank_overflow_checks(data, chart_spec=chart_spec)
        return

    root = pathlib.Path(__file__).resolve().parent.parent
    schema_path = root / "schemas" / "external_denominator_manifest.schema.json"
    try:
        import jsonschema
        schema = json.loads(schema_path.read_text(encoding="utf-8"))
        jsonschema.validate(ext_manifest, schema)
    except ImportError:
        warn("jsonschema 미설치 — external_denominator_manifest 스키마 검증 건너뜀")
    except Exception as e:
        block(f"external_denominator_manifest 스키마 검증 실패({ext_path}): {str(e).splitlines()[0]}")
        # 스키마가 깨져도 가능한 정적 검사는 계속한다.

    adapters = ext_manifest.get("adapters") or []
    status = ext_manifest.get("status")
    if status in {"available", "partial"} and not adapters:
        block("external_denominator_manifest status가 available/partial 이지만 adapters가 비어 있음")

    dashboard_source_ids = {str(s.get("id")) for s in data.get("sources", []) if s.get("id")}
    all_source_ids = dashboard_source_ids | _manifest_source_ids(run_manifest)
    metric_refs = _metric_source_refs(data)

    for adapter in adapters:
        adapter_id = adapter.get("id", "<unknown>")
        category = adapter.get("category")
        if category:
            adapter_categories.append(category)
        source_ref = adapter.get("source_ref")
        if source_ref and source_ref not in all_source_ids:
            block(f"external context '{adapter_id}' source_ref '{source_ref}'가 dashboard_data.sources[] 또는 manifest.sources[]에 없음")
        elif source_ref and source_ref not in metric_refs and source_ref not in dashboard_source_ids:
            warn(f"external context '{adapter_id}' source_ref '{source_ref}'가 KPI/차트 metric에서 직접 참조되지 않음")

        allowed_layers = _adapter_allowed_layers(category or "custom")
        for field in adapter.get("fields") or []:
            if not isinstance(field, dict):
                continue
            metric_layer = field.get("metric_layer")
            field_name = field.get("name", "<unknown>")
            if metric_layer not in allowed_layers:
                block(
                    f"external context '{adapter_id}' field '{field_name}' metric_layer '{metric_layer}'가 "
                    f"category '{category}' 허용 layer({sorted(allowed_layers)})와 불일치"
                )

        coverage = adapter.get("coverage") or {}
        grain_count = coverage.get("grain_count")
        matched_count = coverage.get("matched_count")
        match_rate = coverage.get("match_rate")
        null_rate = coverage.get("null_rate")
        if isinstance(grain_count, int) and isinstance(matched_count, int):
            if matched_count > grain_count:
                block(f"external context '{adapter_id}' matched_count({matched_count}) > grain_count({grain_count})")
            if grain_count > 0 and isinstance(match_rate, (int, float)):
                expected = matched_count / grain_count
                if abs(expected - float(match_rate)) > 0.02:
                    warn(f"external context '{adapter_id}' coverage.match_rate({match_rate})와 matched/grain({expected:.3f}) 불일치")
        if isinstance(match_rate, (int, float)):
            if match_rate < COVERAGE_BLOCK_MATCH_RATE:
                block(f"external context '{adapter_id}' match_rate {match_rate:.3f} < {COVERAGE_BLOCK_MATCH_RATE:.2f}")
            elif match_rate < COVERAGE_WARN_MATCH_RATE:
                warn(f"external context '{adapter_id}' match_rate {match_rate:.3f} < {COVERAGE_WARN_MATCH_RATE:.2f}")
        if isinstance(null_rate, (int, float)):
            if null_rate > COVERAGE_BLOCK_NULL_RATE:
                block(f"external context '{adapter_id}' null_rate {null_rate:.3f} > {COVERAGE_BLOCK_NULL_RATE:.2f}")
            elif null_rate > COVERAGE_WARN_NULL_RATE:
                warn(f"external context '{adapter_id}' null_rate {null_rate:.3f} > {COVERAGE_WARN_NULL_RATE:.2f}")

        source_type = adapter.get("source_type")
        acquisition = adapter.get("acquisition") or {}
        acquisition_method = acquisition.get("method")
        if source_type in {"api_snapshot", "remote_snapshot"} or acquisition_method in {"paged_api", "api_snapshot"}:
            if not acquisition:
                warn(f"external context '{adapter_id}' acquisition 메타 없음 — pagination/수집 행 수 확인 권장")
            else:
                if acquisition_method in {"paged_api", "api_snapshot"} and acquisition.get("pagination_checked") is not True:
                    warn(f"external context '{adapter_id}' pagination_checked가 true가 아님")
                if acquisition_method == "paged_api":
                    page_count = acquisition.get("page_count")
                    collected_row_count = acquisition.get("collected_row_count")
                    if not isinstance(page_count, int) or page_count <= 0:
                        warn(f"external context '{adapter_id}' paged_api인데 page_count가 양수가 아님")
                    if not isinstance(collected_row_count, int) or collected_row_count <= 0:
                        warn(f"external context '{adapter_id}' paged_api인데 collected_row_count가 양수가 아님")

        spatial_grain = adapter.get("spatial_grain")
        grain_quality = adapter.get("grain_quality") or {}
        if spatial_grain in ADMIN_GRAINS:
            if not grain_quality:
                warn(f"external context '{adapter_id}' 행정 grain 품질 메타 없음 — denominator 중복/상하위 혼재 점검 권장")
            else:
                if grain_quality.get("has_upper_lower_mix") is True and grain_quality.get("matched_grain_only") is not True:
                    block(f"external context '{adapter_id}' 상하위 행정구역 혼재가 있는데 matched_grain_only가 true가 아님")
                basis = grain_quality.get("denominator_aggregation_basis")
                if basis in {None, "unknown"}:
                    warn(f"external context '{adapter_id}' denominator_aggregation_basis 미확정")
                elif basis == "raw_source_total":
                    block(f"external context '{adapter_id}' denominator_aggregation_basis=raw_source_total — 중복 denominator 위험")
        if spatial_grain in COARSE_GRAINS:
            if not grain_quality:
                warn(f"external context '{adapter_id}' spatial_grain={spatial_grain}인데 grain_quality 메타 없음")
            else:
                basis = grain_quality.get("denominator_aggregation_basis")
                if basis in {None, "unknown"}:
                    warn(f"external context '{adapter_id}' coarse grain인데 denominator_aggregation_basis 미확정")
            if any((jk.get("quality") == "exact") for jk in (adapter.get("join_keys") or []) if isinstance(jk, dict)):
                warn(f"external context '{adapter_id}' spatial_grain={spatial_grain}에서 exact join 표현이 과신호일 수 있음")

        if post_communicate:
            deep_text = _read_optional_text(pathlib.Path(data_path).resolve().parent / "deep_report.md") or ""
            dashboard_text = json.dumps(data, ensure_ascii=False)
            lineage_missing = []
            if source_ref and source_ref not in deep_text:
                lineage_missing.append("source_ref")
            snapshot_at = adapter.get("snapshot_at")
            if snapshot_at and str(snapshot_at) not in deep_text:
                lineage_missing.append("기준일")
            join_keys = adapter.get("join_keys") or []
            join_terms = [str(v) for jk in join_keys for v in (jk.get("left"), jk.get("right")) if v]
            if join_terms and not any(term in deep_text for term in join_terms):
                lineage_missing.append("join key")
            grain_terms = [str(spatial_grain)] if spatial_grain else []
            if spatial_grain == "sigungu":
                grain_terms.append("시군구")
            if grain_terms and not any(term in deep_text for term in grain_terms):
                lineage_missing.append("spatial grain")
            if not any(term in deep_text for term in ("coverage", "match_rate", "결측", "null rate", "255/255")):
                lineage_missing.append("coverage/null_rate")
            if acquisition and not _contains_any(deep_text, ACQUISITION_DISCLOSURE_TERMS):
                lineage_missing.append("acquisition")
            if grain_quality and not _contains_any(deep_text, AGGREGATION_BASIS_TERMS):
                lineage_missing.append("denominator aggregation basis")
            if not any(term in deep_text for term in ("한계", "limitation", "금지 해석", "주의")):
                lineage_missing.append("limitations")
            if lineage_missing:
                block(f"deep_report.md external context lineage 누락({adapter_id}): {', '.join(lineage_missing)}")
            if _adapter_is_coarse(adapter):
                if not _contains_any(deep_text, COARSE_DISCLOSURE_TERMS):
                    block(f"deep_report.md coarse external context join/aggregation 설명 누락({adapter_id})")
                if not _contains_any(dashboard_text, COARSE_DISCLOSURE_TERMS):
                    warn(f"dashboard_data.json coarse external context join/aggregation 표시 약함({adapter_id})")

    terminology_guard_checks(data_path, data, True, adapter_categories, post_communicate=post_communicate)
    rank_overflow_checks(data, chart_spec=chart_spec)

def _playwright_browser_roots():
    roots = []
    env_path = os.environ.get("PLAYWRIGHT_BROWSERS_PATH")
    if env_path and env_path != "0":
        roots.extend(pathlib.Path(part).expanduser() for part in env_path.split(os.pathsep) if part)
    roots.extend([
        pathlib.Path.home() / "Library" / "Caches" / "ms-playwright",
        pathlib.Path.home() / ".cache" / "ms-playwright",
        pathlib.Path.home() / "AppData" / "Local" / "ms-playwright",
    ])
    out, seen = [], set()
    for root in roots:
        key = str(root)
        if key not in seen and root.exists():
            seen.add(key)
            out.append(root)
    return out

def _browser_cache_version(path):
    match = re.search(r"(?:chromium(?:_headless_shell)?)-(\d+)", str(path))
    return int(match.group(1)) if match else -1

def _browser_executable_candidates():
    candidates = []
    for env_name in ("DIK_PLAYWRIGHT_EXECUTABLE", "VK_PLAYWRIGHT_EXECUTABLE", "PLAYWRIGHT_CHROMIUM_EXECUTABLE"):
        env_value = os.environ.get(env_name)
        if env_value:
            candidates.append(pathlib.Path(env_value).expanduser())

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

    usable, seen = [], set()
    for path in candidates:
        path = path.expanduser()
        key = str(path)
        if key in seen or not path.is_file() or not os.access(path, os.X_OK):
            continue
        seen.add(key)
        usable.append(path)

    def sort_key(path):
        text = str(path)
        prefer_headless = 0 if ("headless_shell" in text or "chrome-headless-shell" in text) else 1
        return (-_browser_cache_version(path), prefer_headless, text)

    return sorted(usable, key=sort_key)

def _one_line_error(exc):
    text = str(exc).strip().splitlines()
    return text[0] if text else exc.__class__.__name__

def _launch_chromium_with_fallback(chromium):
    attempts = []
    try:
        return chromium.launch(), "playwright default"
    except Exception as exc:
        attempts.append(("playwright default", _one_line_error(exc)))

    for exe in _browser_executable_candidates():
        label = f"fallback executable {exe}"
        try:
            return chromium.launch(executable_path=str(exe)), label
        except Exception as exc:
            attempts.append((label, _one_line_error(exc)))

    details = "; ".join(f"{label}: {err}" for label, err in attempts[:5])
    raise RuntimeError(
        "Playwright 브라우저 실행 실패. dashboard_data 계약 실패와 분리된 로컬 렌더 환경 문제입니다. "
        f"시도한 실행 경로: {details}"
    )

def analysis_depth_checks(data_path, chart_spec=None, post_communicate=False):
    manifest = _load_manifest(data_path)
    report = _report_config(manifest)
    depth = report["depth"]
    evidence_scope = report["evidence_scope"]
    outputs_dir = pathlib.Path(data_path).resolve().parent
    analysis_path = outputs_dir / "04_analysis.md"
    analysis_text = _read_optional_text(analysis_path)

    if depth == "deep":
        if analysis_text is None:
            block("depth=deep 이지만 outputs/04_analysis.md 없음 — 심층 보고서 원재료 부족")
        else:
            compact = analysis_text.strip()
            if len(compact) < 2500:
                block(f"depth=deep 이지만 04_analysis.md가 너무 짧음({len(compact)}자) — 심층 분석 원재료 부족")
            missing = _missing_keywords(compact, ANALYSIS_DEEP_KEYWORDS)
            if missing:
                block(f"depth=deep 04_analysis.md 필수 요소 누락: {', '.join(missing)}")

        if chart_spec is not None:
            charts = chart_spec.get("charts") or []
            methods = {c.get("method") for c in charts if c.get("method")}
            chart_types = {((c.get("chart") or {}).get("type")) for c in charts if (c.get("chart") or {}).get("type")}
            chart_spec_quality_checks(chart_spec, deep=True)
            if len(charts) >= 4 and len(methods) < 3:
                warn(f"depth=deep chart_spec 방법론 다양성 낮음: {sorted(methods)}")
            if len(charts) >= 4 and len(chart_types) < 2:
                warn(f"depth=deep chart_spec 차트 유형 다양성 낮음: {sorted(chart_types)}")
    elif analysis_text is not None and len(analysis_text.strip()) < 1200:
        warn(f"04_analysis.md가 짧음({len(analysis_text.strip())}자) — 보고서 해석 깊이 확인 권장")

    if not post_communicate:
        return

    summary_path = outputs_dir / "summary_report.md"
    summary_text = None
    if not summary_path.exists():
        block("post-communicate 검증 실패: outputs/summary_report.md 없음")
    else:
        summary_text = _read_optional_text(summary_path)

    if evidence_scope == "web_context" and not (outputs_dir / "external_context.md").exists():
        block("evidence_scope=web_context 이지만 outputs/external_context.md 없음")

    reader_facing_report_checks(outputs_dir)

    if depth != "deep":
        return

    deep_path = outputs_dir / "deep_report.md"
    deep_text = _read_optional_text(deep_path)
    if deep_text is None:
        block("depth=deep 이지만 outputs/deep_report.md 없음")
        return

    compact = deep_text.strip()
    if len(compact) < 3500:
        block(f"depth=deep 이지만 deep_report.md가 너무 짧음({len(compact)}자) — 심층 보고서 기준 미달")

    missing_sections = _missing_heading_sections(compact, DEEP_REPORT_HEADINGS)
    if missing_sections:
        block(f"deep_report.md 필수 heading 누락: {', '.join(missing_sections)}")

    missing = _missing_keywords(compact, DEEP_REPORT_KEYWORDS)
    if missing:
        block(f"deep_report.md 필수 섹션/요소 누락: {', '.join(missing)}")

    if summary_text:
        summary_len = len(summary_text.strip())
        if summary_len > 2500 and summary_len > len(compact) * 0.75:
            warn(f"summary_report.md가 deep_report.md 대비 길어 역할 분리가 약할 수 있음(summary={summary_len}자, deep={len(compact)}자)")

    if chart_spec is not None:
        chart_ids = [str(c.get("id") or c.get("dashboard_mapping", {}).get("chart_id")) for c in chart_spec.get("charts", [])]
        chart_ids = [cid for cid in chart_ids if cid and cid != "None"]
        mentioned = [cid for cid in chart_ids if cid in compact]
        if chart_ids and not mentioned and "chart_spec" not in compact and "lineage" not in compact:
            warn("deep_report.md에서 chart_spec chart id 또는 lineage 신호가 거의 보이지 않음 — 근거 추적성 확인 권장")

    if analysis_text:
        a = _normalize_for_compare(analysis_text)
        d = _normalize_for_compare(deep_text)
        if a and d:
            similarity = difflib.SequenceMatcher(None, a[:12000], d[:12000]).ratio()
            if similarity > 0.92:
                block(f"deep_report.md가 04_analysis.md와 과도하게 유사함(similarity={similarity:.2f}) — 단순 복사 의심")

# ── expert-guided analysis routing v1 QA (spec §10.2) ──

def method_route_and_dependency_checks(data_path):
    """method_route.json schema/registry 검증 + dependency 승인·설치 provenance 검증."""
    run_dir = _run_dir_for_data_path(data_path)
    root = pathlib.Path(__file__).resolve().parent.parent
    registry = _read_json_if_exists(root / "methods" / "method_registry.json") or {}
    methods_by_id = {m.get("id"): m for m in registry.get("methods") or [] if isinstance(m, dict)}

    route_data = _read_json_if_exists(run_dir / "outputs" / "method_route.json")
    if route_data is None:
        # v1 routing 도입 전 legacy run 호환: wrapper가 신규 run에는 frame 필수
        # 산출물로 강제하므로 QA는 WARN까지만 (spec §15 legacy 경계).
        warn("method_route.json 없음 — v1 routing run이라면 frame 단계 산출물 누락")
    else:
        schema_ok = True
        try:
            import jsonschema
            schema = json.loads((root / "schemas" / "method_route.schema.json").read_text(encoding="utf-8"))
            jsonschema.validate(route_data, schema)
        except ImportError:
            warn("jsonschema 미설치 — method_route 스키마 검증 건너뜀")
        except Exception as e:
            block(f"method_route.json 스키마 검증 실패: {str(e).splitlines()[0]}")
            schema_ok = False
        if schema_ok:
            route = str(route_data.get("route") or "")
            if route not in ROUTE_RANK:
                block(f"method_route.route '{route}' 가 registry route가 아님")
            for method_id in route_data.get("selected_methods") or []:
                if str(method_id) not in methods_by_id:
                    block(f"method_route selected_method '{method_id}' 가 method registry에 없음")
            if route in V1_DOWNGRADE_ONLY_ROUTES and not route_data.get("downgraded_from"):
                warn(
                    f"route '{route}' 는 v1 registry에 전용 method가 없는 downgrade-only route — "
                    "강등 기록 없이 유지된 이유 확인 필요"
                )
            if route == "predictive" and not route_data.get("data_condition_evidence"):
                block("predictive route인데 data_condition_evidence 없음 — 타깃·검증 기간·누수 금지 기준 근거 필요")

    plan = _read_json_if_exists(run_dir / "input" / "dependency_plan.json")
    groups = (route_data or {}).get("dependency_groups") or []
    if groups and plan is None:
        block(f"method_route가 extra {groups} 를 요구하는데 dependency_plan.json 없음 — 승인 trail 부재")
    if plan is None:
        return

    allowlist = registry.get("dependency_allowlist") or {}
    for field in ("required_extras", "installed", "missing"):
        for extra in plan.get(field) or []:
            if str(extra) not in allowlist:
                block(f"dependency_plan.{field} 에 allowlist 밖 extra '{extra}' — 허용: {sorted(allowlist)}")
    install_result = plan.get("install_result") if isinstance(plan.get("install_result"), dict) else None
    if install_result:
        for extra in install_result.get("extras") or []:
            if str(extra) not in allowlist:
                block(f"install_result.extras 에 allowlist 밖 extra '{extra}' — 허용: {sorted(allowlist)}")
    approval = plan.get("approval") if isinstance(plan.get("approval"), dict) else None

    attempted_install = bool(install_result and install_result.get("status") in ("success", "failed"))
    if attempted_install and (not approval or approval.get("dependency_decision") != "install"):
        block("dependency 설치가 시도됐는데 install 승인 기록 없음 — analysis_strategy 명시 옵션 승인 필요")
    if approval:
        answers, _answers_path = _load_checkpoint_answers(run_dir)
        latest = _latest_checkpoint_answers(answers) if answers is not None else {}
        answer = latest.get("analysis_strategy")
        if not answer or answer.get("answer_id") != approval.get("answer_id"):
            block("dependency 승인 answer_id가 최신 analysis_strategy 답변과 연결되지 않음")
        else:
            issues = _checkpoint_answer_provenance_issues(run_dir, "analysis_strategy", answer)
            if issues:
                block("dependency 승인의 analysis_strategy 답변 provenance 무효: " + "; ".join(issues))
            maps_to = answer.get("maps_to") if isinstance(answer.get("maps_to"), dict) else {}
            if approval.get("dependency_decision") == "install" and maps_to.get("dependency_decision") != "install":
                block("install 승인인데 analysis_strategy 답변의 dependency_decision이 install이 아님 — free-text는 설치 승인이 아님")

def qa_dashboard_layout_lock_issues(run_dir, answer):
    """Independently verify the storyboard-approved v5 layout lock."""
    run_dir = pathlib.Path(run_dir)
    layout_path = run_dir / "outputs" / "dashboard_layout.json"
    if not isinstance(answer, dict):
        return (
            [
                "dashboard_storyboard: dashboard_layout.json이 있지만 승인 답변이 없음 — "
                "대시보드 구성 확인 단계 재승인 필요"
            ]
            if layout_path.exists()
            else []
        )

    qpath, _ = _resolve_answer_question_path(run_dir, "dashboard_storyboard", answer)
    question = _read_json_if_exists(qpath) if qpath and qpath.exists() else {}
    targets = question.get("approval_targets") if isinstance(question, dict) else None
    target = targets.get("dashboard_layout") if isinstance(targets, dict) else None
    if not isinstance(target, dict):
        return (
            [
                "dashboard_storyboard: dashboard_layout.json이 승인 질문에 잠기지 않음 — "
                "현재 레이아웃으로 재승인 필요"
            ]
            if layout_path.exists()
            else []
        )
    if not layout_path.exists():
        return [
            "dashboard_storyboard: 승인된 dashboard_layout.json이 현재 없음 — "
            "승인 대상 복구 또는 재승인 필요"
        ]

    issues = []
    if not _recorded_path_matches(run_dir, target.get("path"), layout_path):
        issues.append(
            "dashboard_storyboard: 승인된 dashboard_layout 경로와 현재 경로가 다름 — "
            "대시보드 구성 확인 단계 재승인 필요"
        )
    if str(target.get("sha256") or "") != _sha256_file(layout_path):
        issues.append(
            "dashboard_storyboard: dashboard_layout이 승인 이후 변경됨 — "
            "대시보드 구성 확인 단계 재승인 필요"
        )
    layout = _read_json_if_exists(layout_path) or {}
    if target.get("revision") != layout.get("revision"):
        issues.append(
            "dashboard_storyboard: dashboard_layout revision이 승인값과 다름 — "
            "대시보드 구성 확인 단계 재승인 필요"
        )
    return issues


def approval_target_lock_checks(data_path):
    """spec §7.2 승인 시점 잠금 — stage_guard.analysis_strategy_lock_issues와 같은
    규칙을 QA가 독립 재검증한다 (상향은 재승인, 강등은 사유 기록으로 허용)."""
    run_dir = _run_dir_for_data_path(data_path)
    answers, _path = _load_checkpoint_answers(run_dir)
    if answers is None:
        return  # lineage 검사가 별도로 BLOCK
    latest = _latest_checkpoint_answers(answers)
    for issue in qa_dashboard_layout_lock_issues(
        run_dir, latest.get("dashboard_storyboard")
    ):
        block(issue)
    if not latest.get("analysis_strategy"):
        return
    qpath = _checkpoint_question_json_path(run_dir, "analysis_strategy")
    if qpath is None or not qpath.exists():
        return
    question = _read_json_if_exists(qpath) or {}
    targets = question.get("approval_targets")
    if not isinstance(targets, dict) or not targets:
        return

    mr_locked = (targets.get("method_route") or {}).get("sha256")
    mr_path = run_dir / "outputs" / "method_route.json"
    if not mr_locked and mr_path.exists():
        route_data = _read_json_if_exists(mr_path) or {}
        if str(route_data.get("route") or "") in DEEP_REVIEW_ROUTES and not route_data.get("downgraded_from"):
            block(
                "analysis_strategy 승인 시점에 없던 method_route.json이 이후 심화 route로 생성됨 — "
                "분석 방향 확인 단계 재승인 필요"
            )
    if mr_locked and mr_path.exists() and _sha256_file(mr_path) != mr_locked:
        route_data = _read_json_if_exists(mr_path) or {}
        route = str(route_data.get("route") or "")
        downgraded_from = str(route_data.get("downgraded_from") or "")
        reason = str(route_data.get("downgrade_reason") or "").strip()
        from_rank = ROUTE_RANK.get(downgraded_from)
        if downgraded_from and from_rank is not None and from_rank >= ROUTE_RANK.get(route, 0):
            if not reason:
                block("method_route가 승인 후 강등됐는데 downgrade_reason 없음 — 강등 사유 기록 필요")
        else:
            block("method_route가 승인 시점 이후 상향(또는 미기록) 변경됨 — 분석 방향 확인 단계 재승인 필요")

    dp_locked = (targets.get("dependency_plan") or {}).get("sha256")
    dp_path = run_dir / "input" / "dependency_plan.json"
    if dp_locked and dp_path.exists() and _sha256_file(dp_path) != dp_locked:
        plan = _read_json_if_exists(dp_path) or {}
        approval = plan.get("approval") if isinstance(plan.get("approval"), dict) else {}
        if (plan.get("missing") or []) and approval.get("dependency_decision") != "install":
            block("dependency_plan이 승인 이후 확장됐는데 install 승인 없음 — 분석 방향 확인 단계 재승인 필요")

def _compute_domain_readiness(domain_intake):
    """spec §8.5 결정적 readiness — stage_guard.compute_domain_readiness와 동일 규칙."""
    def _empty(value):
        if value is None:
            return True
        if isinstance(value, (str, list, dict)):
            return len(value) == 0
        return False

    missing = [f for f in DOMAIN_REQUIRED_INTAKE_FIELDS if _empty(domain_intake.get(f))]
    if not missing:
        return "ready", []
    if len(missing) == len(DOMAIN_REQUIRED_INTAKE_FIELDS):
        return "insufficient", missing
    return "partial", missing

def _domain_scan_texts(data_path, data, post_communicate):
    texts = list(_dashboard_visible_texts(data))
    for name, text in _analysis_text_bundle(data_path, include_reports=post_communicate):
        texts.extend((f"{name}:line", line.strip()) for line in text.splitlines() if line.strip())
    return texts

def domain_readiness_checks(data_path, data, manifest, post_communicate=False):
    """domain mode 결론 게이트 (spec §10.2): intake 부재/불충분 시 확정 표현 BLOCK."""
    run_dir = _run_dir_for_data_path(data_path)
    intake_path = run_dir / "input" / "domain_intake.json"
    domain_mode = (
        intake_path.exists()
        or manifest.get("domain_mode") is True
        or (_read_json_if_exists(run_dir / "input" / "run_context.json") or {}).get("domain_mode") is True
    )
    if not domain_mode:
        return
    if not intake_path.exists():
        block("domain mode인데 domain_intake.json 없음 — 도메인 결론 근거 부재 (일반 구조 분석만 허용)")
        return
    domain_intake = _read_json_if_exists(intake_path) or {}
    status, missing = _compute_domain_readiness(domain_intake)
    recorded = (domain_intake.get("domain_readiness") or {}).get("status")
    if recorded and recorded != status:
        block(f"domain_readiness 기록값 '{recorded}' ≠ QA 재계산 '{status}' (누락: {missing}) — 결정적 계산 불일치")
    if status != "insufficient":
        return
    for where, text in _domain_scan_texts(data_path, data, post_communicate):
        if any(safe in text for safe in SAFE_FORBIDDEN_CONTEXT_TERMS):
            continue
        for term in DOMAIN_CONCLUSION_TERMS:
            if term in text:
                block(f"domain_readiness=insufficient 인데 확정 표현 '{term}' 감지({where}): {text[:120]}")
                break

def domain_forbidden_claims_checks(data_path, data, post_communicate=False):
    """domain_intake.forbidden_claims 명시 문구가 visible text에 나오면 BLOCK (spec §10.2)."""
    run_dir = _run_dir_for_data_path(data_path)
    domain_intake = _read_json_if_exists(run_dir / "input" / "domain_intake.json") or {}
    claims = [c for c in domain_intake.get("forbidden_claims") or [] if isinstance(c, dict) and c.get("phrase")]
    if not claims:
        return
    texts = _domain_scan_texts(data_path, data, post_communicate)
    for claim in claims:
        phrase = str(claim["phrase"])
        for where, text in texts:
            if phrase in text:
                allowed = claim.get("allowed_when")
                note = f" (허용 조건: {allowed} — 사람 검토 필요)" if allowed else ""
                block(f"domain 금지 문구 '{phrase}' 감지({where}): {text[:120]}{note}")
                break

def statistical_overclaim_checks(data_path, post_communicate=False):
    """p-value·상관계수만으로 원인·인과를 단정하는 표현 — WARN으로 시작 (spec §10.2).
    부정문('~로 단정할 수 없다')은 SAFE 문맥으로 건너뛴다. 대표 run 보정 후에만 BLOCK 승격."""
    for name, text in _analysis_text_bundle(data_path, include_reports=post_communicate):
        hits = []
        for line in text.splitlines():
            stripped = line.strip()
            if not stripped:
                continue
            if any(safe in stripped for safe in SAFE_FORBIDDEN_CONTEXT_TERMS):
                continue
            lowered = stripped.lower()
            if any(t in lowered for t in STAT_EVIDENCE_TERMS) and any(t in stripped for t in STAT_CONCLUSION_TERMS):
                hits.append(stripped)
        if hits:
            sample = "; ".join(h[:100] for h in hits[:2])
            warn(f"통계 수치만으로 단정 의심({name}): {sample}")

def static_checks(data, schema, chart_spec=None, chart_schema=None):
    # S1 스키마
    try:
        import jsonschema
        jsonschema.validate(data, schema)
    except ImportError:
        warn("jsonschema 미설치 — 스키마 검증 건너뜀")
    except Exception as e:
        block(f"스키마 검증 실패: {str(e).splitlines()[0]}")
        return  # 스키마가 깨지면 이하 검사 무의미

    reader_facing_dashboard_checks(data)
    profile_v4_contract_checks(data)

    # S2 sources[].id 유일성
    ids = [s["id"] for s in data["sources"]]
    if len(ids) != len(set(ids)):
        block(f"sources[].id 중복: {ids}")
    for s in data["sources"]:
        q = s.get("query")
        if q and ("..." in q or "SELECT ..." in q.upper()):
            warn(f"source '{s['id']}' query가 재현 불가능한 축약 표현임")

    # S3 metric.source_ref 실존 + S4 metric 시드(WARN)
    for k in data["kpis"]:
        m = k.get("metric")
        if not m:
            warn(f"KPI '{k['id']}' metric 누락 (v2 재현 시드 권장)")
        elif m["source_ref"] not in ids:
            block(f"KPI '{k['id']}' metric.source_ref '{m['source_ref']}' 가 sources에 없음")

    chart_ids = set()
    for p in data["panels"]:
        for ch in p["charts"]:
            chart_ids.add(ch["id"])
            enc = ch["encoding"]
            # S6 category 차트: x.values 길이 == series.values 길이
            if ch["type"] in ("line", "area", "bar", "stacked_bar"):
                xn = len(enc["x"]["values"])
                for se in enc["series"]:
                    if len(se["values"]) != xn:
                        block(f"차트 '{ch['id']}' series '{se['label']}' 길이 {len(se['values'])} ≠ x 길이 {xn}")
                    if (sr := se.get("metric")) and sr["source_ref"] not in ids:
                        block(f"차트 '{ch['id']}' series metric.source_ref '{sr['source_ref']}' 가 sources에 없음")
                # S7 stack 허용값
                if enc.get("stack") not in STACK_OK[ch["type"]]:
                    block(f"차트 '{ch['id']}' type={ch['type']} 에 stack='{enc.get('stack')}' 부적합 (허용: {STACK_OK[ch['type']]})")
        # S5 시뮬레이터: test_cases 필수 + 모델 계산 일치
        for sm in (p.get("simulators") or []):
            input_ids = {i["id"] for i in sm["inputs"]}
            model = sm["model"]
            if model["type"] in ("linear", "percentage"):
                for term in model["terms"]:
                    if term["input"] not in input_ids:
                        block(f"시뮬레이터 '{sm['id']}' model input '{term['input']}' 이 inputs에 없음")
            if model["type"] == "lookup":
                if model["input"] not in input_ids:
                    block(f"시뮬레이터 '{sm['id']}' lookup input '{model['input']}' 이 inputs에 없음")
                ins = [r["in"] for r in model["table"]]
                if ins != sorted(ins):
                    block(f"시뮬레이터 '{sm['id']}' lookup table.in 오름차순 아님")
            tcs = sm.get("test_cases")
            if not tcs:
                block(f"시뮬레이터 '{sm['id']}' test_cases 없음 — 죽은 시뮬레이터 방지 위해 최소 1개 필수")
                continue
            for tc in tcs:
                got = compute_model(sm["model"], sm["inputs"], tc["inputs"])
                if got is None or math.isnan(got) or abs(got - tc["expect"]) > 1e-6:
                    block(f"시뮬레이터 '{sm['id']}' test_case {tc['inputs']} → 계산 {got} ≠ expect {tc['expect']}")

    # S8 플레이스홀더 잔존
    blob = json.dumps(data, ensure_ascii=False)
    for ph in PLACEHOLDERS:
        if ph in blob:
            block(f"플레이스홀더 '{ph}' 가 데이터에 잔존")

    # S9 테이블 형태 검사
    for p in data["panels"]:
        t = p.get("table")
        if not t:
            continue
        width = len(t["columns"])
        for i, row in enumerate(t["rows"]):
            if len(row) != width:
                block(f"패널 '{p['id']}' table row {i} 길이 {len(row)} ≠ columns {width}")

    # sample_min 경고
    rc = data["meta"].get("row_count")
    for a in (data.get("assertions") or []):
        if a["rule"] == "sample_min" and rc is not None and rc < (a.get("min") or 0):
            warn(f"표본 작음: row_count {rc} < {a['min']} (target {a.get('target')})")

    # S10 chart_spec 중간 계약 검증(제공된 경우)
    if chart_spec is not None:
        if chart_schema is not None:
            try:
                import jsonschema
                jsonschema.validate(chart_spec, chart_schema)
            except ImportError:
                warn("jsonschema 미설치 — chart_spec 스키마 검증 건너뜀")
            except Exception as e:
                block(f"chart_spec 스키마 검증 실패: {str(e).splitlines()[0]}")
                return
        chart_spec_quality_checks(chart_spec, deep=False)
        dashboard_profile_checks(data, chart_spec)
        dashboard_story_alignment_checks(data, chart_spec)
        profile_v4_plan_alignment_checks(data, chart_spec)
        spec_ids = []
        for spec in chart_spec["charts"]:
            mapped = spec["dashboard_mapping"]["chart_id"]
            spec_ids.append(mapped)
            if spec["id"] != mapped:
                block(f"chart_spec '{spec['id']}' id와 dashboard_mapping.chart_id '{mapped}' 불일치")
            if mapped not in chart_ids:
                block(f"chart_spec chart_id '{mapped}' 가 dashboard_data charts에 없음")
            sql = spec["calculation"]["sql"]
            if any(ph in sql for ph in PLACEHOLDERS) or "..." in sql:
                block(f"chart_spec '{spec['id']}' calculation.sql에 placeholder/축약 표현 잔존")
            if ";" in sql.strip().rstrip(";"):
                block(f"chart_spec '{spec['id']}' calculation.sql 다중 문장 의심")
            if _is_selectish(sql):
                forbidden = re.search(r"\b(insert|update|delete|drop|create|alter|attach|copy|install|load|pragma|truncate|replace|merge|grant|revoke|vacuum|export|import)\b", sql, re.I)
                if forbidden:
                    block(f"chart_spec '{spec['id']}' calculation.sql 금지 키워드 감지: {forbidden.group(1)}")
        missing_specs = chart_ids - set(spec_ids)
        if missing_specs:
            warn(f"dashboard_data chart 중 chart_spec 매핑 없음: {sorted(missing_specs)}")


def render_checks(data, template_path, output_dir=None):
    try:
        from playwright.sync_api import sync_playwright
    except ImportError:
        warn("playwright 미설치 — 렌더 검사 건너뜀 (정적 검사만 수행). `pip install playwright && playwright install chromium`")
        return
    import tempfile
    tpl = pathlib.Path(template_path).read_text()
    rendered = tpl.replace("{PLACE_DASHBOARD_DATA_HERE}", json.dumps(data, ensure_ascii=False))
    # R5 주입 후 플레이스홀더 잔존
    if "{PLACE_DASHBOARD_DATA_HERE}" in rendered:
        block("렌더 후 데이터 주입 플레이스홀더 잔존 (주입 실패)")
        return
    tmp = pathlib.Path(tempfile.mkdtemp()) / "dashboard.html"
    tmp.write_text(rendered)
    errors, console = [], []
    try:
        with sync_playwright() as p:
            b, browser_label = _launch_chromium_with_fallback(p.chromium)
            if browser_label != "playwright default":
                warn(f"Playwright 기본 브라우저 실행 실패 후 fallback 사용: {browser_label}")
            pg = b.new_page()
            pg.on("console", lambda m: console.append((m.type, m.text)))
            pg.on("pageerror", lambda e: errors.append(str(e)))
            total_active_svgs = 0
            first_kpi_count = None
            meta = data.get("meta") or {}
            contract_v4 = meta.get("dashboard_profile_contract") == "v4"
            profile = meta.get("dashboard_profile", "executive_brief")
            v4_single_scroll = contract_v4 and profile == "analyst_workspace"
            v4_rail = contract_v4 and profile == "operations_monitor"
            switch_selector = ".v4-rail .rail-item" if v4_rail else ".tab"
            switch_label = "레일 항목" if v4_rail else "탭"
            viewports = [
                ("desktop", {"width": 1280, "height": 900}),
                ("mobile", {"width": 390, "height": 900}),
            ]
            for viewport_name, size in viewports:
                pg.set_viewport_size(size)
                pg.goto("file://" + str(tmp))
                pg.wait_for_timeout(500)
                # 눈검토용 스크린샷 산출물 (v4 smoke 발견: 기계 검사만 믿고
                # 화면을 보지 않으면 사각지대를 놓친다 — 오케스트레이터가
                # 정지점 전달 전 이 파일을 직접 확인해야 한다)
                if output_dir is not None:
                    try:
                        pg.screenshot(
                            path=str(pathlib.Path(output_dir) / f"qa_render_{viewport_name}.png"),
                            full_page=True,
                        )
                    except Exception as exc:
                        warn(f"렌더 스크린샷 저장 실패({viewport_name}): {exc}")
                if v4_single_scroll:
                    # v4 analyst: 탭 없이 primary 단일 스크롤 + detail/appendix 접힘 (spec §5.1)
                    tabs = pg.eval_on_selector_all(".tab", "els=>els.length")
                    if tabs:
                        block(f"v4 analyst 단일 스크롤인데 탭 {tabs}개 렌더 ({viewport_name})")
                    active_svgs = pg.eval_on_selector_all(".panel .chart-card svg", "els=>els.length")
                    total_active_svgs += active_svgs
                    expected_svgs = sum(len(panel["charts"]) for panel in data["panels"])
                    if active_svgs != expected_svgs:
                        block(f"v4 analyst 차트 SVG 렌더 수 {active_svgs} ≠ 전체 차트 수 {expected_svgs} ({viewport_name})")
                    for issue in pg.evaluate(LAYOUT_CHECK_JS):
                        block(f"렌더 레이아웃 오류({viewport_name}, single-scroll): {issue}")
                    if viewport_name == "desktop":
                        first_kpi_count = pg.eval_on_selector_all(".panel .kpi-v", "els=>els.length")
                    continue
                switches = pg.eval_on_selector_all(switch_selector, "els=>els.length")
                if switches != len(data["panels"]):
                    block(f"렌더 {switch_label} 수 {switches} ≠ 데이터 패널 {len(data['panels'])} ({viewport_name})")
                for idx, panel in enumerate(data["panels"]):
                    if switches:
                        pg.eval_on_selector_all(switch_selector, f"(els)=>els[{idx}].click()")
                        pg.wait_for_timeout(120)
                    # v4 E1: KPI 스파크 SVG와 구분하기 위해 차트 카드 selector만 센다
                    active_svgs = pg.eval_on_selector_all(".panel.active .chart-card svg", "els=>els.length")
                    total_active_svgs += active_svgs
                    expected_svgs = len(panel["charts"])
                    if active_svgs != expected_svgs:
                        block(f"패널 '{panel['id']}' 차트 SVG 렌더 수 {active_svgs} ≠ 차트 수 {expected_svgs} ({viewport_name})")
                    for issue in pg.evaluate(LAYOUT_CHECK_JS):
                        block(f"렌더 레이아웃 오류({viewport_name}, panel={panel['id']}): {issue}")
                    if viewport_name == "desktop" and idx == 0:
                        first_kpi_count = pg.eval_on_selector_all(".panel.active .kpi-v", "els=>els.length")
            # R4 시뮬레이터 실렌더 값-무결성: test_cases 를 실제 JS로 구동해 비교
            for panel in data["panels"]:
                for sm in (panel.get("simulators") or []):
                    for tc in sm["test_cases"]:
                        for iid, v in tc["inputs"].items():
                            sel = f'[data-sim="{sm["id"]}"][data-input="{iid}"]'
                            pg.eval_on_selector(sel, f"el=>{{el.value={v};el.dispatchEvent(new Event('input',{{bubbles:true}}));}}")
                        pg.wait_for_timeout(60)
                        txt = pg.eval_on_selector(f'#{sm["output"]["id"]}', "e=>e.textContent")
                        try:
                            if abs(float(txt) - tc["expect"]) > 1e-6:
                                block(f"렌더 시뮬레이터 '{sm['id']}' {tc['inputs']} → 화면값 {txt} ≠ expect {tc['expect']}")
                        except ValueError:
                            block(f"렌더 시뮬레이터 '{sm['id']}' 출력 '{txt}' 숫자 아님")
            b.close()
    except Exception as e:
        block(f"렌더 환경 오류: {e}")
        return
    if errors:
        block(f"페이지 에러: {errors}")
    cerr = [c for c in console if c[0] == "error"]
    if cerr:
        block(f"콘솔 에러: {cerr}")
    if total_active_svgs == 0:
        block("렌더 blank: SVG 0개")
    if first_kpi_count != len(data["kpis"]):
        block(f"KPI 렌더 수 {first_kpi_count} ≠ 데이터 {len(data['kpis'])}")


def dispatch_render_checks(
    data_path: pathlib.Path,
    data: dict,
    chart_spec: dict | None,
    layout: dict | None,
    legacy_template: pathlib.Path,
) -> None:
    """Select one renderer path; v5 errors never call legacy render_checks."""
    data_path = pathlib.Path(data_path).resolve()
    data_contract = (data.get("meta") or {}).get("dashboard_profile_contract")
    if chart_spec is None:
        if data_contract == "v5":
            block("v5 renderer requires chart_spec.json; legacy renderer fallback is forbidden")
            return
        render_checks(data, legacy_template, output_dir=data_path.parent)
        return

    try:
        renderer = select_renderer(chart_spec, data, layout)
    except ContractError as exc:
        block(str(exc))
        return
    if renderer != "v5":
        render_checks(data, legacy_template, output_dir=data_path.parent)
        return

    if layout is None:
        block("v5 renderer requires dashboard_layout.json")
        return
    issues = validate_layout(layout) + validate_v5_cross_contract(
        chart_spec, layout, data
    )
    if issues:
        for issue in issues:
            block(f"v5 contract: {issue}")
        return

    output_dir = data_path.parent
    chart_spec_path = output_dir / "chart_spec.json"
    layout_path = output_dir / "dashboard_layout.json"
    html_path = output_dir / "dashboard.html"
    manifest_path = output_dir / "dashboard_build_manifest.json"
    required = [chart_spec_path, layout_path, data_path, html_path, manifest_path]
    missing = [path.name for path in required if not path.exists()]
    if missing:
        block(f"v5 compiled artifact missing: {', '.join(missing)}")
        return

    try:
        recorded_manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
        expected_manifest = build_manifest(
            chart_spec_path,
            layout_path,
            data_path,
            KIT_ROOT,
            layout,
        )
    except (OSError, ValueError) as exc:
        block(f"v5 build manifest unreadable: {exc}")
        return
    if recorded_manifest != expected_manifest:
        block("v5 dashboard_build_manifest.json does not match current inputs/template/bundle")
        return

    browser_blocks, browser_warns = run_browser_qa(
        html_path, layout, data, output_dir
    )
    for issue in browser_blocks:
        block(issue)
    for issue in browser_warns:
        warn(issue)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("data", help="dashboard_data.json 경로")
    ap.add_argument("--chart-spec", default=None, help="chart_spec.json 경로")
    ap.add_argument("--layout", default=None, help="dashboard_layout.json 경로 (기본: data sibling)")
    ap.add_argument("--template", default=None, help="templates/dashboard.html 경로 (렌더 검사용)")
    ap.add_argument("--schema", default=None, help="dashboard_data.schema.json 경로")
    ap.add_argument("--chart-schema", default=None, help="chart_spec.schema.json 경로")
    ap.add_argument("--no-render", action="store_true")
    ap.add_argument("--post-communicate", action="store_true", help="communicate 이후 summary/deep/external 보고서까지 검증")
    args = ap.parse_args()

    root = pathlib.Path(__file__).resolve().parent.parent
    data_path = pathlib.Path(args.data)
    data = json.loads(data_path.read_text())
    schema_path = args.schema or (root / "schemas" / "dashboard_data.schema.json")
    schema = json.loads(pathlib.Path(schema_path).read_text())
    chart_spec = None
    chart_schema = None
    if args.chart_spec:
        chart_spec = json.loads(pathlib.Path(args.chart_spec).read_text())
        chart_schema_path = args.chart_schema or (root / "schemas" / "chart_spec.schema.json")
        chart_schema = json.loads(pathlib.Path(chart_schema_path).read_text())
    layout_path = pathlib.Path(args.layout) if args.layout else data_path.parent / "dashboard_layout.json"
    layout = json.loads(layout_path.read_text()) if layout_path.exists() else None
    template = args.template or (root / "templates" / "dashboard.html")

    template_static_checks(template)
    static_checks(data, schema, chart_spec=chart_spec, chart_schema=chart_schema)
    v5_series_scale_checks(data, layout)
    checkpoint_lineage_checks(data_path, post_communicate=args.post_communicate)
    interview_loop_checks(data_path)
    run_context_checks(data_path, data, chart_spec=chart_spec)
    source_api_manifest_checks(data_path, data)
    external_adapter_plan_checks(data_path)
    external_denominator_checks(data_path, data, chart_spec=chart_spec, post_communicate=args.post_communicate)
    analysis_depth_checks(data_path, chart_spec=chart_spec, post_communicate=args.post_communicate)
    # expert-guided analysis routing v1 (spec §10.2)
    routing_manifest = _load_manifest(data_path)
    method_route_and_dependency_checks(data_path)
    approval_target_lock_checks(data_path)
    domain_readiness_checks(data_path, data, routing_manifest, post_communicate=args.post_communicate)
    domain_forbidden_claims_checks(data_path, data, post_communicate=args.post_communicate)
    statistical_overclaim_checks(data_path, post_communicate=args.post_communicate)
    if not args.no_render:
        dispatch_render_checks(data_path, data, chart_spec, layout, template)

    print("=" * 56)
    print(f"data-insight-kit QA: {args.data}")
    print("=" * 56)
    for w in WARN:
        print(f"  WARN  {w}")
    for b in BLOCK:
        print(f"  BLOCK {b}")
    if not BLOCK and not WARN:
        print("  통과 — 경고·차단 없음")
    print("-" * 56)
    if BLOCK:
        print(f"❌ 출고 차단 — BLOCK {len(BLOCK)}건, WARN {len(WARN)}건")
        sys.exit(1)
    print(f"✅ 출고 가능 — BLOCK 0건, WARN {len(WARN)}건")
    sys.exit(0)


if __name__ == "__main__":
    main()
