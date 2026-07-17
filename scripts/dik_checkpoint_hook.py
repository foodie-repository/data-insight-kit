#!/usr/bin/env python3
"""PreToolUse gate for the Claude Code AND Codex CLI adapters.

The Codex CLI wrapper (run_codex_pipeline.sh) enforces mid-pipeline user
checkpoints with a deterministic outer loop (stage_guard.py + checkpoint_gate.py,
exit code 3). But when the model orchestrates the stages itself — Claude Code
plugin, or Codex Desktop driven in natural language — there is no such outer
loop, so the same guards are only advisory prose and get bypassed under
"execute the approved plan" pressure.

This hook restores a deterministic gate for BOTH runtimes. Claude Code and Codex
share the same PreToolUse deny contract, so one script serves both; only the
file-edit tool differs (Claude: Write/Edit with file_path; Codex: apply_patch
with a patch body). It runs before every Write / Edit / Bash / apply_patch call
and DENIES the call when it would produce a downstream stage artifact whose
required user checkpoint has not been approved with valid v3 provenance. It also
blocks internal terminology from leaking into reader-facing checkpoint/intake
question files.

Registered by hooks/hooks.json (Claude Code plugin) and .codex/hooks.json
(Codex project hooks).

It reuses the exact approval-validation logic from stage_guard.py so the hook,
the wrapper, and qa/validate.py all agree on what counts as a real approval.

Safety: this hook is packaged in a plugin and therefore fires for every tool
call in the user's session, including work unrelated to data-insight-kit. It is
deliberately fail-open — any unexpected error or any target outside a
data-insight-kit run results in exit 0 (no decision, normal permission flow).
Only a positively identified gated write inside a kit run is ever denied.
"""
from __future__ import annotations

import json
import os
import re
import sys
import tempfile
from pathlib import Path

# stage_guard.py and validate_user_facing_text.py live next to this file.
sys.path.insert(0, str(Path(__file__).resolve().parent))
import stage_guard  # noqa: E402
import validate_user_facing_text as ufv  # noqa: E402

# Downstream artifact -> the stage that produces it. stage_guard.STAGE_REQUIREMENTS
# then maps the stage to the checkpoints that must be approved first.
ARTIFACT_STAGE = {
    "03_frame.md": "frame",
    "method_route.json": "frame",
    "04_analysis.md": "analyze",
    "chart_spec.json": "analyze",
    "dashboard_layout.json": "analyze",
    "dashboard_data.json": "visualize",
    "dashboard.html": "visualize",
    "summary_report.md": "communicate",
    "deep_report.md": "communicate",
    "external_context.md": "communicate",
}

CHECKPOINT_LABEL = {
    "data_profile": "데이터 확인 단계",
    "analysis_strategy": "분석 방향 확인 단계",
    "dashboard_storyboard": "대시보드 구성안 확인 단계",
    "report_outline": "보고서 구성안 확인 단계",
}

# Reader-facing question/intake files whose content must stay free of internal terms.
# 라운드 2 질문 파일(.round2 접미사)도 동일하게 배포용 언어 게이트 대상이다
# (interview-loop-v2 §9 — 접미사가 끼면 `_question.json` endswith 매칭이 빠진다).
USER_FACING_SUFFIXES = (
    "_question.json",
    "_question.md",
    "_question.round2.json",
    "_question.round2.md",
    "intake_questions.json",
    "intake_questions.md",
)

# Run-local builder scripts (under runs/<id>/) are the observed bypass vector:
# the model writes a script that generates dashboard/report outputs wholesale.
BUILDER_HINT = re.compile(r"(build|dashboard|report|generate|render|make)", re.IGNORECASE)


def find_kit_run(target: Path) -> Path | None:
    """Return the runs/<id> dir if `target` is inside a data-insight-kit run."""
    parts = target.parts
    for i in range(len(parts) - 1, -1, -1):
        if parts[i] == "runs" and i + 1 < len(parts):
            kit_root = Path(*parts[:i]) if i > 0 else Path(target.anchor or ".")
            run_dir = Path(*parts[: i + 2])
            marker = kit_root / "scripts" / "stage_guard.py"
            contract = kit_root / "docs" / "pipeline-contract.md"
            if marker.exists() or contract.exists():
                return run_dir
    return None


def approval_issues(run_dir: Path, checkpoints: tuple[str, ...]) -> list[str]:
    """Reuse stage_guard's validation; empty list means all approved."""
    if stage_guard.checkpoint_policy_allows_skip(run_dir):
        return []
    latest = stage_guard.latest_answers(run_dir)
    issues: list[str] = []
    for checkpoint_id in checkpoints:
        answer = latest.get(checkpoint_id)
        if not answer:
            issues.append(f"{checkpoint_id}: approved answer missing")
            continue
        issues.extend(stage_guard.validate_answer(run_dir, checkpoint_id, answer))
    if "analysis_strategy" in checkpoints:
        issues.extend(
            stage_guard.analysis_strategy_lock_issues(
                run_dir, latest.get("analysis_strategy")
            )
        )
    if "dashboard_storyboard" in checkpoints:
        issues.extend(
            stage_guard.dashboard_layout_lock_issues(
                run_dir, latest.get("dashboard_storyboard")
            )
        )
    return issues


def gated_checkpoints_for(target: Path, is_builder: bool, run_dir: Path) -> tuple[str, ...]:
    """Which checkpoints this write requires, or () if it is not gated."""
    if is_builder:
        # A run-local builder produces official outputs wholesale, so it must
        # clear every checkpoint. The contract forbids run-local builders from
        # making official outputs without approval.
        return tuple(CHECKPOINT_LABEL)
    stage = ARTIFACT_STAGE.get(target.name)
    if stage is None:
        return ()
    # Only gate the canonical outputs/ artifact, not same-named files elsewhere.
    if target.parent.name != "outputs":
        return ()
    # effective_stage_requirements adds the conditional analysis_result_review
    # gate per this run's own predicate, so hook and stage_guard never drift.
    return stage_guard.effective_stage_requirements(run_dir, stage)


def pending_checkpoint_without_handoff(cwd: Path) -> str | None:
    """전달 순서(턴 분리) 게이트: 답변 대기 중인 checkpoint 질문의 핸드오프
    원문이 아직 한 번도 출력되지 않았다면 AskUserQuestion 팝업을 막는다
    (v4 smoke 발견 — 근거를 보여주기 전에 선택을 요구하는 경로 차단)."""
    import hashlib

    for runs_root in (cwd / "runs", cwd / "data-insight-kit" / "runs"):
        if not runs_root.is_dir():
            continue
        for run_dir in sorted(runs_root.iterdir()):
            checkpoints = run_dir / "outputs" / "checkpoints"
            if not checkpoints.is_dir():
                continue
            answered_shas: set[str] = set()
            try:
                store = json.loads((run_dir / "checkpoint_answers.json").read_text(encoding="utf-8"))
                answers = store.get("answers") if isinstance(store, dict) else None
                for ans in answers or []:
                    ref = ans.get("question_ref") if isinstance(ans, dict) else None
                    if isinstance(ref, dict) and ref.get("sha256"):
                        answered_shas.add(str(ref["sha256"]))
            except (OSError, json.JSONDecodeError):
                pass
            printed_shas: set[str] = set()
            log_path = checkpoints / "handoff_log.json"
            try:
                for entry in json.loads(log_path.read_text(encoding="utf-8")):
                    if isinstance(entry, dict) and entry.get("question_sha256"):
                        printed_shas.add(str(entry["question_sha256"]))
            except (OSError, json.JSONDecodeError):
                pass
            for qfile in sorted(checkpoints.glob("*_question*.json")):
                sha = hashlib.sha256(qfile.read_bytes()).hexdigest()
                if sha in answered_shas or sha in printed_shas:
                    continue
                return (
                    "⛔ 전달 순서(턴 분리) 게이트: 답변 대기 중인 checkpoint 질문의 근거 원문이 "
                    f"아직 출력되지 않았습니다 ({qfile}).\n"
                    "팝업을 띄우기 전에 먼저 다음을 하세요:\n"
                    f"1) python3 scripts/checkpoint_gate.py {run_dir.name} <checkpoint-id> --print-existing 결과를 "
                    "채팅 본문에 그대로 출력하고 턴을 끝내 사용자가 근거를 읽게 하세요.\n"
                    "2) 그 다음 턴에서 선택을 받으세요 (팝업 또는 채팅 답변)."
                )
    return None


def deny(reason: str) -> None:
    print(
        json.dumps(
            {
                "hookSpecificOutput": {
                    "hookEventName": "PreToolUse",
                    "permissionDecision": "deny",
                    "permissionDecisionReason": reason,
                }
            }
        )
    )
    sys.exit(0)


def build_checkpoint_reason(target_desc: str, run_dir: Path, missing: tuple[str, ...]) -> str:
    labels = " / ".join(CHECKPOINT_LABEL.get(cp, cp) for cp in missing)
    next_cp = missing[-1]
    prefix = stage_guard.CHECKPOINT_PREFIXES.get(next_cp, next_cp)
    q_md = f"{run_dir}/outputs/checkpoints/{prefix}.md"
    return (
        f"⛔ data-insight-kit 확인 단계 게이트: '{target_desc}'를 만들기 전에 "
        f"'{labels}'에 대한 실제 사용자 확인이 필요합니다.\n"
        "지금은 다음 단계로 넘어가지 말고 다음을 하세요:\n"
        f"1) {q_md} 의 chat_prompt(현재 이해 / 확인할 내용 / 막힌 결정 / 추천 답안 / 질문)를 "
        "AskUserQuestion으로 사용자에게 그대로 보여주고 답을 받으세요. "
        "질문 파일이 없으면 먼저 scripts/checkpoint_gate.py 로 만드세요.\n"
        "2) 사용자의 실제 답변만 scripts/apply_checkpoint_answer.py 로 기록하세요 "
        "(--source user_chat --user-response \"<사용자 답변>\" --transcript-ref \"<메시지 id>\").\n"
        "3) 승인이 기록된 뒤에 다시 시도하세요.\n"
        "플랜 승인 문구(\"Implement the proposed plan\" 등)를 여러 확인 단계 답변으로 "
        "재사용하지 마세요. 그건 승인으로 인정되지 않습니다."
    )


def check_terminology(target: Path, content: str) -> None:
    """Block internal terms in reader-facing question/intake file content."""
    name = target.name
    if not any(name.endswith(suffix) for suffix in USER_FACING_SUFFIXES):
        return
    suffix = ".json" if name.endswith(".json") else ".md"
    tmp = None
    try:
        with tempfile.NamedTemporaryFile(
            "w", suffix=suffix, delete=False, encoding="utf-8"
        ) as fh:
            fh.write(content)
            tmp = Path(fh.name)
        issues = ufv.validate_path(tmp)
    finally:
        if tmp is not None:
            tmp.unlink(missing_ok=True)
    # A checkpoint/intake JSON that simply has no user brief yet is not a leak.
    issues = [i for i in issues if "no user_analysis_brief" not in i]
    if issues:
        detail = "\n".join(f"- {i}" for i in issues)
        deny(
            f"⛔ data-insight-kit 배포 언어 게이트: '{target.name}'의 사용자용 문구에 "
            f"내부 용어가 노출됩니다. 사용자에게 보이는 부분은 쉬운 말로 바꾸고 "
            f"내부 용어는 기술 부록/tooltip으로 옮기세요.\n{detail}"
        )


def apply_patch_targets(patch_text: str) -> list[tuple[str, str]]:
    """Extract (path, added_content) for each Add/Update File in a Codex patch."""
    added: dict[str, list[str]] = {}
    current: str | None = None
    for line in patch_text.splitlines():
        marker = re.match(r"\*\*\*\s+(Add|Update|Delete) File:\s*(.+?)\s*$", line)
        if marker:
            action, path = marker.group(1), marker.group(2).strip()
            current = path if action in {"Add", "Update"} else None
            if current is not None:
                added.setdefault(current, [])
            continue
        if current is not None and line.startswith("+") and not line.startswith("+++"):
            added[current].append(line[1:])
    return [(path, "\n".join(lines)) for path, lines in added.items()]


def _is_gated_output(token: str) -> bool:
    return token.rsplit("/", 1)[-1] in ARTIFACT_STAGE and "runs" in token.split("/")


def bash_write_destinations(command: str) -> list[Path]:
    """Every destination-looking path from redirects/cp/mv/tee/install/rsync/dd,
    WITHOUT the `_is_gated_output` runs/-artifact filter that `bash_targets()`
    applies. Used only for the domain-pack write gate, which is intentionally
    NOT scoped to runs/ (spec §13 forbids domains/<name>/ auto-edits everywhere,
    not just mid-run). Reuses the exact same extraction regexes as
    `bash_targets()` so both stay in lockstep; `bash_targets()` itself is left
    untouched since its narrow runs/-artifact scoping is intentional and other
    tests depend on it.
    """
    destinations: list[Path] = []
    seen: set[str] = set()

    def add(raw: str) -> None:
        if raw not in seen:
            seen.add(raw)
            destinations.append(Path(raw))

    for match in re.finditer(r">>?\s*[\"']?([\w./\-]+)", command):
        add(match.group(1))

    for match in re.finditer(r"\b(?:tee|cp|mv|install|rsync|dd)\b([^\n|;&]*)", command):
        for token in re.findall(r"[\w./\-]+", match.group(1)):
            add(token.split("=", 1)[-1])

    return destinations


def bash_targets(command: str) -> list[tuple[Path, bool]]:
    """Extract *write-intent* targets from a Bash command.

    Only gate commands that actually WRITE a gated artifact — redirections
    (``>``/``>>``/``tee``) and copy/move destinations (``cp``/``mv``/``install``/
    ``rsync``/``dd``) — plus execution of a run-local builder script. A command
    that merely mentions a gated path (``cat``/``grep``/``head``/a path inside a
    string) is NOT a write and must not be blocked.
    """
    targets: list[tuple[Path, bool]] = []
    seen: set[tuple[str, bool]] = set()

    def add(raw: str, is_builder: bool) -> None:
        key = (raw, is_builder)
        if key not in seen:
            seen.add(key)
            targets.append((Path(raw), is_builder))

    # Redirections into a gated output: `> path`, `>> path`.
    for match in re.finditer(r">>?\s*[\"']?([\w./\-]+)", command):
        if _is_gated_output(match.group(1)):
            add(match.group(1), False)

    # Write commands whose argument list contains a gated output (destination):
    # tee / cp / mv / install / rsync / dd of=...
    for match in re.finditer(r"\b(?:tee|cp|mv|install|rsync|dd)\b([^\n|;&]*)", command):
        for token in re.findall(r"[\w./\-]+", match.group(1)):
            if _is_gated_output(token.split("=", 1)[-1]):
                add(token.split("=", 1)[-1], False)

    # Execution of a run-local builder script (writes outputs wholesale).
    for token in re.findall(r"[\w./\-]+\.(?:py|sh)", command):
        base = token.rsplit("/", 1)[-1]
        if "runs" in token.split("/") and BUILDER_HINT.search(base):
            add(token, True)

    return targets


def _safe_json(path: Path) -> dict:
    """Local fail-open reader — never raises, unlike stage_guard.read_json."""
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
        return data if isinstance(data, dict) else {}
    except Exception:
        return {}


def _normalize_pkg(name: str) -> str:
    """Mirror dependency_preflight.normalize() so allowlist comparison agrees."""
    return re.sub(r"[-_.]+", "_", name).lower()


# Install verbs matched so a standalone verb word matches but 'pip install-x-as-word'
# does not — the (?![\w-]) lookahead rejects a trailing hyphen/word char (spec §10.2).
_PIP_INSTALL_RE = re.compile(r"\b(?:pip|pip3)\s+install(?![\w-])")
_PIP_MODULE_INSTALL_RE = re.compile(r"\bpython3?\s+-m\s+pip\s+install(?![\w-])")
_UV_ADD_RE = re.compile(r"\buv\s+add(?![\w-])")
_UV_SYNC_RE = re.compile(r"\buv\s+sync(?![\w-])")
_EXTRA_RE = re.compile(r"--extra[=\s]+([\w.\-]+)")
# Blanket extra-pulling flags: uv sync --all-extras (or a bare --extras / -E) pulls
# in every optional group, so it cannot be checked against a specific approved
# extra and must be rejected outright rather than enumerated (spec §10.2).
_UV_SYNC_BLANKET_RE = re.compile(r"--all-extras\b|--extras\b")
_UV_SYNC_DASH_E_RE = re.compile(r"(?:^|\s)-E(?:\s|$)")

# A compound/chained command (`pip install ok && pip install evil`, `a; b`, `a | b`)
# must have EVERY segment inspected independently — checking only the first
# segment would let a later install ride along unchecked (spec §10.2).
_SEGMENT_SPLIT_RE = re.compile(r"&&|\|\||[;|]")


def _split_segments(command: str) -> list[str]:
    return [seg.strip() for seg in _SEGMENT_SPLIT_RE.split(command) if seg.strip()]


def _has_blanket_extra_flag(segment: str) -> bool:
    return bool(_UV_SYNC_BLANKET_RE.search(segment) or _UV_SYNC_DASH_E_RE.search(segment))


def _install_pkg_tokens(segment: str, verb: str) -> list[str]:
    """Package tokens after the install verb, stripped of flags and version specs.
    `segment` is expected to already be a single shell-separator-free command."""
    match = re.search(rf"\b{verb}(?![\w-])(.*)", segment)
    tail = match.group(1) if match else ""
    tokens: list[str] = []
    for raw in tail.split():
        if raw.startswith("-"):
            continue  # flags: -U, --upgrade, --dev, --extra handled elsewhere, ...
        name = re.split(r"[<>=!~\[]", raw)[0].strip()  # strip version + extras marker
        if name:
            tokens.append(name)
    return tokens


def _install_provenance_issues(run_dir: Path) -> list[str]:
    """Valid dependency install approval provenance (spec §7.3, §10.2)."""
    plan = _safe_json(run_dir / "input" / "dependency_plan.json")
    approval = plan.get("approval") if isinstance(plan.get("approval"), dict) else None
    if not approval:
        return ["dependency_plan.json에 설치 승인이 없습니다 (approval=null)."]
    if approval.get("dependency_decision") != "install":
        return ["설치 승인 결정이 install이 아닙니다."]
    answer_id = approval.get("answer_id")
    if not answer_id:
        return ["설치 승인에 answer_id가 없습니다."]
    answer = stage_guard.latest_answers(run_dir).get("analysis_strategy")
    if not isinstance(answer, dict) or answer.get("answer_id") != answer_id:
        return ["설치 승인 answer_id가 analysis_strategy 답변과 일치하지 않습니다."]
    if stage_guard.validate_answer(run_dir, "analysis_strategy", answer):
        return ["설치 승인의 analysis_strategy 답변이 유효한 승인 provenance를 통과하지 못합니다."]
    maps_to = answer.get("maps_to") if isinstance(answer.get("maps_to"), dict) else {}
    if maps_to.get("dependency_decision") != "install":
        return ["analysis_strategy 답변의 dependency_decision이 install이 아닙니다."]
    return []


def install_command_issues(run_dir: Path, command: str) -> list[str]:
    """Detect install invocations across every shell segment of `command` and
    return issues if any segment's target is outside the registry allowlist or
    lacks valid install-approval provenance (spec §10.2). The command is split
    on &&/||/;/| first so a chained/compound command cannot smuggle a second
    install past the first segment's check, and each segment is inspected
    independently for pip/uv-add/uv-sync-extra invocations. `uv add` is denied
    unconditionally — it rewrites the kit pyproject.toml, so approval cannot
    make it safe (interview-loop-v2 spec §9, v1 CHANGELOG 발견 3)."""
    segments = _split_segments(command)
    if not segments:
        return []

    kit_root = run_dir.parent.parent
    allowlist = _safe_json(kit_root / "methods" / "method_registry.json").get("dependency_allowlist") or {}
    allowed_pkgs = {_normalize_pkg(pkg) for pkgs in allowlist.values() for pkg in pkgs}

    issues: list[str] = []
    any_install = False
    for segment in segments:
        is_pip = bool(_PIP_INSTALL_RE.search(segment) or _PIP_MODULE_INSTALL_RE.search(segment))
        is_uv_add = bool(_UV_ADD_RE.search(segment))
        is_uv_sync = bool(_UV_SYNC_RE.search(segment))
        blanket = is_uv_sync and _has_blanket_extra_flag(segment)
        pinned_extra = is_uv_sync and not blanket and bool(_EXTRA_RE.search(segment))
        if not (is_pip or is_uv_add or blanket or pinned_extra):
            continue
        any_install = True

        if is_uv_add:
            issues.append(
                "`uv add`는 kit pyproject.toml을 변경하므로 승인 여부와 무관하게 허용되지 않습니다. "
                "승인된 extra는 `uv sync --extra <group>`으로 설치하세요."
            )
        elif blanket:
            issues.append(
                "전체 extra(--all-extras) 설치는 허용되지 않습니다. 승인된 extra만 개별로 설치하세요."
            )
        elif pinned_extra:
            for extra in _EXTRA_RE.findall(segment):
                if extra not in allowlist:
                    allowed = ", ".join(sorted(allowlist)) or "없음"
                    issues.append(f"허용되지 않은 extra 설치 시도: {extra} (허용 extra: {allowed})")
        else:
            for token in _install_pkg_tokens(segment, "install"):
                if _normalize_pkg(token) not in allowed_pkgs:
                    issues.append(f"허용되지 않은 패키지 설치 시도: {token}")

    if any_install:
        issues.extend(_install_provenance_issues(run_dir))
    return issues


def build_install_deny_reason(run_dir: Path, issues: list[str]) -> str:
    detail = "\n".join(f"- {issue}" for issue in issues)
    return (
        "⛔ data-insight-kit 설치 승인 게이트: 이 설치 명령을 실행할 수 없습니다.\n"
        f"{detail}\n"
        "추가 분석 기능 설치는 '분석 방향 확인 단계'에서 사용자가 install_and_deepen 옵션을 "
        "명시적으로 선택해 승인한 뒤에만, registry allowlist(stats/ml) 안에서 진행할 수 있습니다.\n"
        f"승인 기록: {run_dir}/input/dependency_plan.json 의 approval.answer_id ↔ "
        "checkpoint_answers.json(analysis_strategy)."
    )


def domain_pack_write_target(path: Path) -> str | None:
    """Return the domain name if `path` is a non-template <kit_root>/domains/<name>/
    write, else None. Not gated behind runs/ — domain pack edits are a permanent
    non-goal (spec §13)."""
    parts = path.parts
    for i in range(len(parts) - 1):
        if parts[i] != "domains":
            continue
        name = parts[i + 1]
        if i + 2 >= len(parts):
            # domains/ 바로 아래 파일(README.md 등)은 pack 콘텐츠가 아니라 문서다 —
            # pack 쓰기는 domains/<name>/ '안쪽' 경로여야 한다 (v2 커밋 11 오탐 수정).
            continue
        if name == "template":
            continue
        kit_root = Path(*parts[:i]) if i > 0 else Path(path.anchor or ".")
        marker = kit_root / "scripts" / "stage_guard.py"
        contract = kit_root / "docs" / "pipeline-contract.md"
        if marker.exists() or contract.exists():
            return name
    return None


def build_domain_pack_deny_reason(name: str, target: Path) -> str:
    return (
        f"⛔ data-insight-kit domain pack 게이트: 'domains/{name}/' 자동 수정은 금지입니다 "
        f"(대상: {target.name}).\n"
        "domain pack 변경은 이번 run의 outputs/domain_pack_update_candidates.md에 후보로 남기고 "
        "사람 검토를 거쳐야 하며, 에이전트가 직접 편집할 수 없습니다."
    )


def main() -> int:
    try:
        payload = json.load(sys.stdin)
    except Exception:
        return 0  # fail-open

    tool_name = payload.get("tool_name")
    tool_input = payload.get("tool_input") or {}
    cwd = payload.get("cwd") or os.getcwd()

    if tool_name == "AskUserQuestion":
        issue = pending_checkpoint_without_handoff(Path(cwd))
        if issue:
            deny(issue)
        return 0

    if tool_name not in {"Write", "Edit", "Bash", "apply_patch"}:
        return 0

    def resolve(raw: str) -> Path:
        p = Path(raw)
        if not p.is_absolute():
            p = Path(cwd) / p
        return Path(os.path.normpath(str(p)))

    candidates: list[tuple[Path, bool, str]] = []  # (path, is_builder, content)
    if tool_name in {"Write", "Edit"}:  # Claude Code file edits
        fp = tool_input.get("file_path")
        if fp:
            content = tool_input.get("content", "") if tool_name == "Write" else ""
            candidates.append((resolve(fp), False, content))
    elif tool_name == "apply_patch":  # Codex file edits (patch body)
        patch = (
            tool_input.get("command")
            or tool_input.get("patch")
            or tool_input.get("input")
            or tool_input.get("content")
            or ""
        )
        for path, content in apply_patch_targets(patch):
            candidates.append((resolve(path), False, content))
    else:  # Bash (both runtimes)
        command = tool_input.get("command", "") or ""
        for path, is_builder in bash_targets(command):
            candidates.append((resolve(str(path)), is_builder, ""))

    try:
        # Install-command gate (spec §10.2): about the COMMAND TEXT, not a write
        # target, so it is a separate path from bash_targets() extraction.
        if tool_name == "Bash":
            command = tool_input.get("command", "") or ""
            cwd_run = find_kit_run(Path(os.path.normpath(str(Path(cwd)))))
            if cwd_run is not None:
                install_issues = install_command_issues(cwd_run, command)
                if install_issues:
                    deny(build_install_deny_reason(cwd_run, install_issues))

            # Domain-pack write gate for Bash redirects/cp/mv/tee/install/rsync/dd
            # (spec §13). bash_targets()/candidates only extract runs/-scoped gated
            # artifacts, so a plain `cp x domains/<name>/y` never reaches the
            # candidates loop below — check every destination-looking token here,
            # independent of and additive to that existing extraction.
            for raw in bash_write_destinations(command):
                resolved = resolve(str(raw))
                domain_name = domain_pack_write_target(resolved)
                if domain_name is not None:
                    deny(build_domain_pack_deny_reason(domain_name, resolved))

        for target, is_builder, content in candidates:
            # Domain pack write gate (spec §13): permanent non-goal, not gated on runs/.
            domain_name = domain_pack_write_target(target)
            if domain_name is not None:
                deny(build_domain_pack_deny_reason(domain_name, target))
            run_dir = find_kit_run(target)
            if run_dir is None:
                continue
            # Terminology gate (Write of reader-facing question/intake files).
            if content:
                check_terminology(target, content)
            # Checkpoint gate.
            checkpoints = gated_checkpoints_for(target, is_builder, run_dir)
            if not checkpoints:
                continue
            issues = approval_issues(run_dir, checkpoints)
            if issues:
                missing = tuple(
                    cp for cp in checkpoints if any(i.startswith(f"{cp}:") for i in issues)
                ) or checkpoints
                target_desc = (
                    f"run-local builder {target.name}" if is_builder else target.name
                )
                deny(build_checkpoint_reason(target_desc, run_dir, missing))
    except SystemExit:
        raise
    except Exception:
        return 0  # fail-open on any unexpected error

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
