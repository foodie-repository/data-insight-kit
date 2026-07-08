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
  python qa/validate.py <dashboard_data.json> [--chart-spec outputs/chart_spec.json] [--template templates/dashboard.html] [--no-render] [--post-communicate]
종료코드: 0 = 출고 가능(BLOCK 없음) / 1 = 차단(BLOCK 있음) / 2 = 사용 오류.
"""
import sys, json, argparse, pathlib, math, re, difflib, os

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
        x = vals[model["input"]]; tb = model["table"]
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
PUBLIC_AUDIENCE_CODES = {"executive", "analyst", "operator", "mixed"}
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

    audience = str(meta.get("audience") or "")
    if audience in PUBLIC_AUDIENCE_CODES:
        warn(
            f"meta.audience='{audience}'는 내부 코드값임 — 렌더러가 그대로 표시하면 "
            "사용자용 라벨(예: 검토용/운영용/요약용)로 치환 필요"
        )

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
        dashboard_story_alignment_checks(data, chart_spec)
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


def render_checks(data, template_path):
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
            viewports = [
                ("desktop", {"width": 1280, "height": 900}),
                ("mobile", {"width": 390, "height": 900}),
            ]
            for viewport_name, size in viewports:
                pg.set_viewport_size(size)
                pg.goto("file://" + str(tmp)); pg.wait_for_timeout(500)
                tabs = pg.eval_on_selector_all(".tab", "els=>els.length")
                if tabs != len(data["panels"]):
                    block(f"렌더 탭 수 {tabs} ≠ 데이터 패널 {len(data['panels'])} ({viewport_name})")
                for idx, panel in enumerate(data["panels"]):
                    if tabs:
                        pg.eval_on_selector_all(".tab", f"(els)=>els[{idx}].click()")
                        pg.wait_for_timeout(120)
                    active_svgs = pg.eval_on_selector_all(".panel.active svg", "els=>els.length")
                    total_active_svgs += active_svgs
                    expected_svgs = len(panel["charts"])
                    if active_svgs != expected_svgs:
                        block(f"패널 '{panel['id']}' SVG 렌더 수 {active_svgs} ≠ 차트 수 {expected_svgs} ({viewport_name})")
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
    if errors: block(f"페이지 에러: {errors}")
    cerr = [c for c in console if c[0] == "error"]
    if cerr: block(f"콘솔 에러: {cerr}")
    if total_active_svgs == 0: block("렌더 blank: SVG 0개")
    if first_kpi_count != len(data["kpis"]): block(f"KPI 렌더 수 {first_kpi_count} ≠ 데이터 {len(data['kpis'])}")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("data", help="dashboard_data.json 경로")
    ap.add_argument("--chart-spec", default=None, help="chart_spec.json 경로")
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
    template = args.template or (root / "templates" / "dashboard.html")

    static_checks(data, schema, chart_spec=chart_spec, chart_schema=chart_schema)
    source_api_manifest_checks(data_path, data)
    external_adapter_plan_checks(data_path)
    external_denominator_checks(data_path, data, chart_spec=chart_spec, post_communicate=args.post_communicate)
    analysis_depth_checks(data_path, chart_spec=chart_spec, post_communicate=args.post_communicate)
    if not args.no_render:
        render_checks(data, template)

    print("=" * 56)
    print(f"data-insight-kit QA: {args.data}")
    print("=" * 56)
    for w in WARN: print(f"  WARN  {w}")
    for b in BLOCK: print(f"  BLOCK {b}")
    if not BLOCK and not WARN: print("  통과 — 경고·차단 없음")
    print("-" * 56)
    if BLOCK:
        print(f"❌ 출고 차단 — BLOCK {len(BLOCK)}건, WARN {len(WARN)}건")
        sys.exit(1)
    print(f"✅ 출고 가능 — BLOCK 0건, WARN {len(WARN)}건")
    sys.exit(0)


if __name__ == "__main__":
    main()
