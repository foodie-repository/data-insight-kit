#!/usr/bin/env python3
"""
Refuse to enter downstream stages unless required human checkpoints are approved.

This guard is intentionally separate from qa/validate.py. QA catches bad final
artifacts, but stage entry should fail before a later stage writes official
outputs when the run is still waiting for user input.
"""
from __future__ import annotations

import argparse
import hashlib
import json
from datetime import datetime
from pathlib import Path
from typing import Any

HUMAN_CONFIRMATION_SOURCES = {"ask_user_question", "user_chat", "manual_cli"}
RECORDER_ID = "scripts/apply_checkpoint_answer.py"
CHECKPOINT_PREFIXES = {
    "data_profile": "01_data_profile_question",
    "analysis_strategy": "02_analysis_strategy_question",
    "dashboard_storyboard": "03_dashboard_storyboard_question",
    "report_outline": "04_report_outline_question",
    # Conditional H2.5 gate. Fixed prefix 05_ regardless of pipeline order
    # (analyze -> [05_ conditional] -> 03_dashboard_storyboard). spec §15.
    "analysis_result_review": "05_analysis_result_review_question",
}
STAGE_REQUIREMENTS = {
    "intake": (),
    "connect": (),
    "explore": (),
    "frame": ("data_profile",),
    "analyze": ("data_profile", "analysis_strategy"),
    "visualize": ("data_profile", "analysis_strategy", "dashboard_storyboard"),
    "qa": ("data_profile", "analysis_strategy", "dashboard_storyboard"),
    "communicate": ("data_profile", "analysis_strategy", "dashboard_storyboard", "report_outline"),
}

# spec §9 predicate inputs. Recomputed here (and in qa/validate.py) — never trusted
# from method_route.json's own review_predicate field.
DEEP_REVIEW_ROUTES = {"statistical", "ml_exploratory", "predictive", "causal_experiment"}
DECISION_ANALYSIS_MODES = {"candidate_prioritization", "risk_screening"}

# spec §8.5 common required domain-intake fields (route-specific extras come from
# the method registry, checked separately at analyze entry).
DOMAIN_REQUIRED_FIELDS = (
    "row_meaning",
    "entity_grain",
    "column_semantics",
    "exclusion_rules",
    "objective",
    "forbidden_claims",
)

# Implementation default (spec §15): route rank for detecting upward changes.
ROUTE_RANK = {
    "descriptive": 0,
    "diagnostic": 0,
    "statistical": 1,
    "ml_exploratory": 1,
    "predictive": 2,
    "causal_experiment": 2,
}


def read_json(path: Path) -> dict[str, Any]:
    if not path.exists():
        return {}
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        raise SystemExit(f"invalid JSON in {path}: {exc}")
    return data if isinstance(data, dict) else {}


def sha256_file(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def parse_dt(value: Any) -> datetime | None:
    if not value:
        return None
    text = str(value)
    if text.endswith("Z"):
        text = text[:-1] + "+00:00"
    try:
        return datetime.fromisoformat(text)
    except ValueError:
        return None


def recorded_path_matches(run: Path, recorded: Any, actual_path: Path) -> bool:
    if not recorded:
        return False
    candidate = Path(str(recorded))
    candidates = [candidate]
    if not candidate.is_absolute():
        candidates.append(run.parent.parent / candidate)
    actual = actual_path.resolve()
    return any(path.resolve() == actual for path in candidates)


def policy_allows_skip(policy: dict[str, Any] | None) -> bool:
    """정식 자동 실행 술어 — 3계층(stage_guard·dik_checkpoint_hook·qa/validate)이
    공유하는 단일 정의. wrapper가 --auto/--no-checkpoints에서
    input/checkpoint_policy.json에 남긴 정책만 인정한다(mode=auto+explicit_skip).
    manifest.json 등 다른 위치의 self-signed 정책은 인정하지 않는다(교차검증 H1)."""
    if not isinstance(policy, dict):
        return False
    return policy.get("mode") == "auto" and policy.get("explicit_skip") is True


def checkpoint_policy_allows_skip(run: Path) -> bool:
    # 정본은 wrapper가 쓰는 input/checkpoint_policy.json 하나뿐이다. manifest.json
    # 폴백은 정당한 생산자가 없어 self-signed 우회 통로였으므로 제거했다(교차검증 H1).
    return policy_allows_skip(read_json(run / "input" / "checkpoint_policy.json"))


def answer_candidates(run: Path) -> list[Path]:
    return [run / "checkpoint_answers.json", run / "input" / "checkpoint_answers.json"]


def answer_store_issues(run: Path) -> list[str]:
    """interview-loop-v2 §4.3 canonical 단일화 (Codex H2): input/ mirror는 판정에
    쓰지 않고 정합만 검사한다. 어긋나면 fail-closed 사유를 돌려준다."""
    canonical = run / "checkpoint_answers.json"
    mirror = run / "input" / "checkpoint_answers.json"
    if mirror.exists():
        if not canonical.exists():
            return ["checkpoint_answers: mirror가 canonical 없이 존재합니다 (fail-closed)"]
        if canonical.read_bytes() != mirror.read_bytes():
            return [
                "checkpoint_answers: canonical/mirror 불일치 (fail-closed) — "
                "scripts/apply_checkpoint_answer.py로 답변을 다시 기록해 동기화하세요"
            ]
    return []


def latest_answers(run: Path) -> dict[str, dict[str, Any]]:
    """canonical checkpoint_answers.json만 판정 입력으로 쓴다 (spec §4.3 —
    과거에는 mirror를 이어 읽어 파일 순서상 mirror가 이겼다). companion
    레코드는 결정에서 제외한다 (M1). 자유 질문 레코드는 I1로 승인이 될 수
    없으므로 결정 레코드로 남아도 안전하다."""
    latest: dict[str, dict[str, Any]] = {}
    data = read_json(run / "checkpoint_answers.json")
    for item in data.get("answers") or []:
        if not isinstance(item, dict) or not item.get("checkpoint_id"):
            continue
        if item.get("companion_id"):
            continue
        latest[str(item["checkpoint_id"])] = item
    return latest


def question_path(run: Path, checkpoint_id: str) -> Path:
    prefix = CHECKPOINT_PREFIXES[checkpoint_id]
    return run / "outputs" / "checkpoints" / f"{prefix}.json"


def resolve_answer_question(run: Path, checkpoint_id: str, answer: dict[str, Any]) -> tuple[Path, list[str]]:
    """interview-loop-v2 §4.6 질문 파일 resolver: 허용 집합은 {라운드 1 canonical,
    같은 prefix `.round2`} ∩ 해당 run의 outputs/checkpoints 뿐이다. 라운드 2는
    유효 R2 체인(§4.1 — prior_round.question_sha256이 현재 R1을 가리킴)이어야
    한다. round3 이상 파일은 존재 자체가 차단 사유다."""
    prefix = CHECKPOINT_PREFIXES[checkpoint_id]
    checkpoints_dir = run / "outputs" / "checkpoints"
    r1 = checkpoints_dir / f"{prefix}.json"
    r2 = checkpoints_dir / f"{prefix}.round2.json"
    issues: list[str] = []
    for stray in sorted(checkpoints_dir.glob(f"{prefix}.round*.json")):
        if stray.name != r2.name:
            issues.append(
                f"{checkpoint_id}: 허용되지 않는 라운드 질문 파일 {stray.name} (추가 문답은 최대 2회)"
            )
    qref = answer.get("question_ref") if isinstance(answer.get("question_ref"), dict) else {}
    ref_name = Path(str(qref.get("path") or "")).name
    if ref_name and ref_name not in {r1.name, r2.name}:
        issues.append(f"{checkpoint_id}: 답변이 허용 집합 밖 질문 파일을 참조합니다 ({ref_name})")
        return r1, issues
    if ref_name != r2.name:
        return r1, issues
    if not r2.exists():
        issues.append(f"{checkpoint_id}: 답변이 참조한 라운드 2 질문 파일이 없습니다")
        return r1, issues
    question2 = read_json(r2)
    loop = question2.get("interview_loop") if isinstance(question2.get("interview_loop"), dict) else {}
    prior = loop.get("prior_round") if isinstance(loop.get("prior_round"), dict) else {}
    if not r1.exists():
        issues.append(f"{checkpoint_id}: 라운드 2가 있는데 라운드 1 질문 파일이 없습니다")
    elif str(prior.get("question_sha256") or "") != sha256_file(r1):
        issues.append(f"{checkpoint_id}: 라운드 2가 현재 라운드 1 질문을 가리키지 않습니다 (고아 라운드 2)")
    prior_answer_id = str(prior.get("answer_id") or "")
    known_ids = {
        str(item.get("answer_id"))
        for item in (read_json(run / "checkpoint_answers.json").get("answers") or [])
        if isinstance(item, dict)
    }
    if not prior_answer_id or prior_answer_id not in known_ids:
        issues.append(f"{checkpoint_id}: 라운드 1 답변 기록 없이 라운드 2 질문이 존재합니다 (위조 의심)")
    if r1.exists():
        r1_created = parse_dt(read_json(r1).get("created_at"))
        r2_created = parse_dt(question2.get("created_at"))
        if r1_created and r2_created and r2_created <= r1_created:
            issues.append(f"{checkpoint_id}: 라운드 2 생성 시각이 라운드 1보다 빠릅니다")
    return r2, issues


def domain_mode_active(run: Path) -> bool:
    """domain_intake.json 존재 OR manifest.domain_mode OR run_context.domain_mode (spec §9)."""
    if (run / "input" / "domain_intake.json").exists():
        return True
    manifest = read_json(run / "manifest.json")
    if manifest.get("domain_mode") is True:
        return True
    run_context = read_json(run / "input" / "run_context.json")
    return run_context.get("domain_mode") is True


def review_predicate_required(run: Path) -> tuple[bool, list[str]]:
    """spec §9 predicate — recomputed here and in qa/validate.py independently; never trust method_route.json's own review_predicate field as ground truth."""
    matched: list[str] = []
    route_data = read_json(run / "outputs" / "method_route.json")
    if str(route_data.get("route") or "") in DEEP_REVIEW_ROUTES:
        matched.append("route_requires_review")
    if domain_mode_active(run):
        matched.append("domain_mode")
    manifest = read_json(run / "manifest.json")
    intake = manifest.get("intake") if isinstance(manifest.get("intake"), dict) else {}
    report = intake.get("report") if isinstance(intake.get("report"), dict) else {}
    if report.get("depth") == "deep":
        matched.append("report_depth_deep")
    if intake.get("analysis_mode") in DECISION_ANALYSIS_MODES:
        matched.append("decision_analysis_mode")
    return bool(matched), matched


def compute_domain_readiness(domain_intake: dict[str, Any]) -> tuple[str, list[str]]:
    """spec §8.5 deterministic readiness. Pure function (plain dict in, primitives
    out) so qa/validate.py can mirror the exact same rule."""
    def _empty(value: Any) -> bool:
        if value is None:
            return True
        if isinstance(value, (str, list, dict)):
            return len(value) == 0
        return False

    missing = [field for field in DOMAIN_REQUIRED_FIELDS if _empty(domain_intake.get(field))]
    if not missing:
        return "ready", []
    if len(missing) == len(DOMAIN_REQUIRED_FIELDS):
        return "insufficient", missing
    return "partial", missing


def method_registry(run: Path) -> dict[str, Any]:
    """Load methods/method_registry.json from the run's kit root (best-effort)."""
    for base in (run.parent.parent, Path(__file__).resolve().parents[1]):
        path = base / "methods" / "method_registry.json"
        if path.exists():
            return read_json(path)
    return {}


def effective_stage_requirements(run: Path, stage: str) -> tuple[str, ...]:
    """Static STAGE_REQUIREMENTS plus the conditional analysis_result_review gate
    (spec §9). Inserted in pipeline order — after analysis_strategy, before
    dashboard_storyboard — for stages downstream of the H2.5 gate. Reused by
    dik_checkpoint_hook.py so hook and guard never drift."""
    base = STAGE_REQUIREMENTS.get(stage)
    if base is None:
        return ()
    if stage in ("visualize", "qa", "communicate") and review_predicate_required(run)[0]:
        effective: list[str] = []
        for checkpoint_id in base:
            if checkpoint_id == "dashboard_storyboard":
                effective.append("analysis_result_review")
            effective.append(checkpoint_id)
        return tuple(effective)
    return base


def analysis_strategy_lock_issues(run: Path, answer: dict[str, Any] | None) -> list[str]:
    """spec §7.2 approval-time lock: compare the analysis_strategy question's
    approval_targets sha256 against current method_route/dependency_plan. Upward
    change (route escalation, added extras) requires re-approval; a recorded
    downgrade is allowed with a reason."""
    if not isinstance(answer, dict):
        return []
    # 라운드 2 승인이면 라운드 2 질문의 approval_targets가 기준이다 (spec §5.2).
    # 체인 위반 사유는 validate_answer가 이미 보고하므로 여기서는 경로만 쓴다.
    qpath, _ = resolve_answer_question(run, "analysis_strategy", answer)
    if not qpath.exists():
        return []
    question = read_json(qpath)
    targets = question.get("approval_targets")
    if not isinstance(targets, dict) or not targets:
        return []
    issues: list[str] = []

    mr_locked = (targets.get("method_route") or {}).get("sha256")
    mr_path = run / "outputs" / "method_route.json"
    if not mr_locked and mr_path.exists():
        # method_route.json did not exist yet when analysis_strategy was approved
        # (approval_targets.method_route was never recorded). If it now exists
        # with a route that needs analysis_result_review and no recorded
        # downgrade, that is an unreviewed upward change -> re-approval required.
        route_data = read_json(mr_path)
        route = str(route_data.get("route") or "")
        if route in DEEP_REVIEW_ROUTES and not route_data.get("downgraded_from"):
            issues.append(
                "analysis_strategy: 승인 시점에는 method_route.json이 없었는데 이후 심화 route로 "
                "생성됐습니다. 분석 방향 확인 단계 질문을 다시 만들어 재승인을 받으세요."
            )
    if mr_locked and mr_path.exists() and sha256_file(mr_path) != mr_locked:
        route_data = read_json(mr_path)
        route = str(route_data.get("route") or "")
        downgraded_from = str(route_data.get("downgraded_from") or "")
        reason = str(route_data.get("downgrade_reason") or "").strip()
        current_rank = ROUTE_RANK.get(route, 0)
        from_rank = ROUTE_RANK.get(downgraded_from)
        if downgraded_from and from_rank is not None and from_rank >= current_rank:
            if not reason:
                issues.append(
                    "analysis_strategy: method_route가 승인 후 강등됐으나 downgrade_reason이 "
                    "비어 있습니다. 강등 사유를 기록해야 진행할 수 있습니다."
                )
            # recorded downgrade with reason -> allowed
        else:
            issues.append(
                "analysis_strategy: method_route가 승인 시점 이후 상향(또는 미기록) 변경됐습니다. "
                "분석 방향 확인 단계 질문을 다시 만들어 재승인을 받으세요."
            )

    dp_locked = (targets.get("dependency_plan") or {}).get("sha256")
    dp_path = run / "input" / "dependency_plan.json"
    if dp_locked and dp_path.exists() and sha256_file(dp_path) != dp_locked:
        plan = read_json(dp_path)
        approval = plan.get("approval") if isinstance(plan.get("approval"), dict) else {}
        missing = plan.get("missing") or []
        if missing and approval.get("dependency_decision") != "install":
            issues.append(
                "analysis_strategy: 추가 분석 기능 준비 계획이 승인 이후 확장됐는데 설치 승인이 "
                "없습니다. 분석 방향 확인 단계에서 다시 승인을 받으세요."
            )
    return issues


def dashboard_layout_lock_issues(
    run: Path, answer: dict[str, Any] | None
) -> list[str]:
    """Lock the v5 dashboard layout to the approved storyboard question.

    Legacy/v4 runs have neither dashboard_layout.json nor a layout approval
    target and remain unaffected. Once either exists, both must agree on path,
    hash, and revision before visualize or later stages may run.
    """
    layout_path = run / "outputs" / "dashboard_layout.json"
    if not isinstance(answer, dict):
        return (
            [
                "dashboard_storyboard: dashboard_layout.json이 있지만 승인 답변이 없습니다. "
                "대시보드 구성 확인 단계 재승인이 필요합니다."
            ]
            if layout_path.exists()
            else []
        )

    qpath, _ = resolve_answer_question(run, "dashboard_storyboard", answer)
    question = read_json(qpath) if qpath.exists() else {}
    targets = question.get("approval_targets")
    target = targets.get("dashboard_layout") if isinstance(targets, dict) else None
    if not isinstance(target, dict):
        return (
            [
                "dashboard_storyboard: dashboard_layout.json이 승인 질문에 잠기지 않았습니다. "
                "현재 레이아웃으로 질문을 다시 만들어 재승인을 받으세요."
            ]
            if layout_path.exists()
            else []
        )
    if not layout_path.exists():
        return [
            "dashboard_storyboard: 승인된 dashboard_layout.json이 현재 없습니다. "
            "승인 대상 레이아웃을 복구하거나 재승인을 받으세요."
        ]

    issues: list[str] = []
    if not recorded_path_matches(run, target.get("path"), layout_path):
        issues.append(
            "dashboard_storyboard: 승인된 dashboard_layout 경로와 현재 경로가 다릅니다. "
            "대시보드 구성 확인 단계 재승인이 필요합니다."
        )
    if str(target.get("sha256") or "") != sha256_file(layout_path):
        issues.append(
            "dashboard_storyboard: dashboard_layout이 승인 이후 변경됐습니다. "
            "대시보드 구성 확인 단계 재승인이 필요합니다."
        )
    layout = read_json(layout_path)
    if target.get("revision") != layout.get("revision"):
        issues.append(
            "dashboard_storyboard: dashboard_layout revision이 승인값과 다릅니다. "
            "대시보드 구성 확인 단계 재승인이 필요합니다."
        )
    return issues


def analyze_domain_entry_issues(run: Path) -> list[str]:
    """analyze 진입 차단 (spec §8, §10): domain mode인데 intake가 없거나, intake가
    insufficient인데 도메인 조건이 필요한 method가 선택된 경우."""
    if not domain_mode_active(run):
        return []
    intake_path = run / "input" / "domain_intake.json"
    if not intake_path.exists():
        return [
            "analyze: domain mode인데 domain_intake.json이 없습니다. 도메인 전문가 확인 정보를 "
            "먼저 기록해야 도메인 인식 분석을 진행할 수 있습니다."
        ]
    status, _missing = compute_domain_readiness(read_json(intake_path))
    if status != "insufficient":
        return []
    route_path = run / "outputs" / "method_route.json"
    if not route_path.exists():
        return []
    selected = read_json(route_path).get("selected_methods") or []
    if not selected:
        return []
    registry = method_registry(run)
    methods_by_id = {m.get("id"): m for m in registry.get("methods") or [] if isinstance(m, dict)}
    for method_id in selected:
        method = methods_by_id.get(str(method_id))
        if method and (method.get("requires") or {}).get("domain_conditions"):
            return [
                "analyze: 도메인 기준 확인 상태가 부족한데(insufficient) 도메인 조건이 필요한 분석 "
                "방법이 선택됐습니다. 도메인 전문가 확인 정보를 보강한 뒤 진행하세요."
            ]
    return []


def validate_answer(run: Path, checkpoint_id: str, answer: dict[str, Any]) -> list[str]:
    issues: list[str] = []
    issues.extend(answer_store_issues(run))
    if answer.get("companion_id") or answer.get("loop_action"):
        issues.append(
            f"{checkpoint_id}: 탐색·수집 레코드(companion·자유 질문·방향 선택)는 승인이 될 수 없습니다 (불변식 I1)"
        )
    qpath, round_issues = resolve_answer_question(run, checkpoint_id, answer)
    issues.extend(round_issues)
    if not qpath.exists():
        issues.append(f"{checkpoint_id}: question artifact missing ({qpath})")
        return issues
    question = read_json(qpath)
    qref = answer.get("question_ref") if isinstance(answer.get("question_ref"), dict) else {}

    if answer.get("continue_pipeline") is not True:
        issues.append(f"{checkpoint_id}: latest answer does not allow continuation")
    if answer.get("source") not in HUMAN_CONFIRMATION_SOURCES:
        issues.append(f"{checkpoint_id}: source is not a human confirmation source")
    if answer.get("source") in {"user_chat", "ask_user_question"} and not str(answer.get("transcript_ref") or "").strip():
        issues.append(f"{checkpoint_id}: transcript_ref is required for {answer.get('source')} approvals")
    if answer.get("human_confirmed") is not True:
        issues.append(f"{checkpoint_id}: human_confirmed is not true")
    if not str(answer.get("user_response") or "").strip():
        issues.append(f"{checkpoint_id}: user_response is empty")
    if answer.get("approval_contract_version") != "checkpoint-answer.v3":
        issues.append(f"{checkpoint_id}: approval_contract_version must be checkpoint-answer.v3")
    if answer.get("recorded_by") != RECORDER_ID:
        issues.append(f"{checkpoint_id}: recorded_by must be {RECORDER_ID}")
    if not answer.get("answer_id"):
        issues.append(f"{checkpoint_id}: answer_id missing")
    if not recorded_path_matches(run, qref.get("path"), qpath):
        issues.append(f"{checkpoint_id}: question_ref.path does not match current question artifact")
    if qref.get("sha256") != sha256_file(qpath):
        issues.append(f"{checkpoint_id}: question_ref.sha256 does not match current question artifact")
    if not question.get("created_at"):
        issues.append(f"{checkpoint_id}: question created_at missing")
    if qref.get("created_at") != question.get("created_at"):
        issues.append(f"{checkpoint_id}: question_ref.created_at does not match question created_at")

    answered_at = parse_dt(answer.get("answered_at"))
    created_at = parse_dt(question.get("created_at"))
    if not answered_at:
        issues.append(f"{checkpoint_id}: answered_at invalid or missing")
    if not created_at:
        issues.append(f"{checkpoint_id}: question created_at invalid or missing")
    if answered_at and created_at and answered_at <= created_at:
        issues.append(f"{checkpoint_id}: answered_at must be after question created_at")
    return issues


def assert_can_run(run_id: str, stage: str) -> int:
    if stage not in STAGE_REQUIREMENTS:
        raise SystemExit(f"unknown stage: {stage}. valid stages: {', '.join(sorted(STAGE_REQUIREMENTS))}")
    run = Path("runs") / run_id
    requirements = effective_stage_requirements(run, stage)
    needs_domain_check = stage == "analyze"
    if not requirements and not needs_domain_check:
        return 0
    if checkpoint_policy_allows_skip(run):
        return 0
    latest = latest_answers(run)
    issues: list[str] = []
    for checkpoint_id in requirements:
        answer = latest.get(checkpoint_id)
        if not answer:
            issues.append(f"{checkpoint_id}: approved answer missing")
            continue
        issues.extend(validate_answer(run, checkpoint_id, answer))
    if "analysis_strategy" in requirements:
        issues.extend(analysis_strategy_lock_issues(run, latest.get("analysis_strategy")))
    if "dashboard_storyboard" in requirements:
        issues.extend(dashboard_layout_lock_issues(run, latest.get("dashboard_storyboard")))
    if needs_domain_check:
        issues.extend(analyze_domain_entry_issues(run))
    if issues:
        print(f"✋ stage guard blocked: {stage}")
        print("사용자 checkpoint 승인 증거가 부족하거나 위조 가능성이 있어 다음 단계로 진행하지 않습니다.")
        for issue in issues:
            print(f"- {issue}")
        print("")
        print("다음 조치:")
        print("- 질문 파일을 사용자에게 보여준 뒤 실제 답변을 받으세요.")
        print("- 답변은 scripts/apply_checkpoint_answer.py 로만 기록하세요.")
        return 3
    print(f"✅ stage guard passed: {stage}")
    return 0


def main() -> int:
    parser = argparse.ArgumentParser(description="Guard data-insight-kit stage entry with checkpoint approvals.")
    parser.add_argument("run_id")
    parser.add_argument("stage", choices=sorted(STAGE_REQUIREMENTS))
    args = parser.parse_args()
    return assert_can_run(args.run_id, args.stage)


if __name__ == "__main__":
    raise SystemExit(main())
