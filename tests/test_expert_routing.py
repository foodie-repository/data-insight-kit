"""Coverage for expert-guided analysis routing v1 stage-2 additions (commits 5-7):
stage_guard.py §9 predicate/domain readiness/approval lock, dik_checkpoint_hook.py
install-command and domain-pack write gates, dependency_preflight.py downgrade/apply-approval,
and qa/validate.py routing/dependency/domain QA. See docs/specs/expert-guided-analysis-routing.md.
"""
from __future__ import annotations

import hashlib
import importlib.util
import json
import shutil
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace

KIT_ROOT = Path(__file__).resolve().parents[1]


def load_module(name: str, relative_path: str):
    path = KIT_ROOT / relative_path
    spec = importlib.util.spec_from_file_location(name, path)
    if spec is None or spec.loader is None:
        raise RuntimeError(f"cannot load module: {path}")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


stage_guard = load_module("dik_stage_guard_routing", "scripts/stage_guard.py")
hook = load_module("dik_checkpoint_hook_routing", "scripts/dik_checkpoint_hook.py")
preflight = load_module("dik_dependency_preflight_routing", "scripts/dependency_preflight.py")
qa = load_module("dik_qa_validate_routing", "qa/validate.py")


# ── shared fixture helpers ──────────────────────────────────────────────

def _write_json(path: Path, data) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")


def _make_run(tmp: Path, run_id: str) -> Path:
    run = tmp / "runs" / run_id
    (run / "input").mkdir(parents=True)
    (run / "outputs" / "checkpoints").mkdir(parents=True)
    return run


def _data_path(run: Path) -> Path:
    return run / "outputs" / "dashboard_data.json"


def _write_method_route(run: Path, route: str, selected_methods: list[str], **extra) -> Path:
    path = run / "outputs" / "method_route.json"
    data = {
        "schema_version": "data-insight-kit.method_route.v1",
        "run_id": run.name,
        "created_at": "2026-07-10T00:00:00Z",
        "route": route,
        "selected_methods": list(selected_methods),
    }
    data.update(extra)
    _write_json(path, data)
    return path


def _write_dependency_plan(run: Path, **fields) -> Path:
    path = run / "input" / "dependency_plan.json"
    data = {
        "schema_version": "data-insight-kit.dependency_plan.v1",
        "run_id": run.name,
        "created_at": "2026-07-10T00:05:00Z",
        "environment": {"kit_root": "kit", "venv_path": "kit/.venv", "basis": "kit_local_venv"},
        "required_extras": [],
        "installed": [],
        "missing": [],
        "approval": None,
        "install_result": None,
    }
    data.update(fields)
    _write_json(path, data)
    return path


def _write_domain_intake(run: Path, **fields) -> Path:
    path = run / "input" / "domain_intake.json"
    data = {
        "schema_version": "data-insight-kit.domain_intake.v1",
        "run_id": run.name,
        "created_at": "2026-07-10T00:00:00Z",
        "domain_scope": None,
        "objective": None,
        "row_meaning": None,
        "entity_grain": None,
        "column_semantics": [],
        "exclusion_rules": [],
        "kpi_definitions": [],
        "forbidden_claims": [],
        "evidence_boundaries": {"can_say": [], "cannot_say": []},
        "open_questions": [],
        "domain_readiness": {
            "status": "insufficient",
            "computed_at": "2026-07-10T00:00:00Z",
            "rule": "deterministic-v1",
            "missing_required": [],
        },
    }
    data.update(fields)
    _write_json(path, data)
    return path


def _write_analysis_strategy_question(run: Path, approval_targets: dict) -> Path:
    path = run / "outputs" / "checkpoints" / "02_analysis_strategy_question.json"
    _write_json(path, {"approval_targets": approval_targets})
    return path


# ── stage_guard.py: §9 predicate ────────────────────────────────────────

class StageGuardReviewPredicateTests(unittest.TestCase):
    def test_false_for_descriptive_route_and_standard_depth(self):
        with tempfile.TemporaryDirectory() as tmp:
            run = _make_run(Path(tmp), "pred-false")
            _write_method_route(run, route="descriptive", selected_methods=["ranking"])
            _write_json(run / "manifest.json", {"intake": {"report": {"depth": "standard"}}})
            required, matched = stage_guard.review_predicate_required(run)
            self.assertFalse(required)
            self.assertEqual(matched, [])

    def test_true_for_each_condition_independently(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            with self.subTest(condition="route_requires_review"):
                run = _make_run(root, "pred-route")
                _write_method_route(run, route="statistical", selected_methods=["group_difference_candidate"])
                required, matched = stage_guard.review_predicate_required(run)
                self.assertTrue(required)
                self.assertIn("route_requires_review", matched)
            with self.subTest(condition="domain_mode_via_intake_file"):
                run = _make_run(root, "pred-domain-file")
                _write_domain_intake(run)
                required, matched = stage_guard.review_predicate_required(run)
                self.assertTrue(required)
                self.assertIn("domain_mode", matched)
            with self.subTest(condition="domain_mode_via_manifest_flag"):
                run = _make_run(root, "pred-domain-manifest")
                _write_json(run / "manifest.json", {"domain_mode": True})
                required, matched = stage_guard.review_predicate_required(run)
                self.assertTrue(required)
                self.assertIn("domain_mode", matched)
            with self.subTest(condition="domain_mode_via_run_context_stamp"):
                run = _make_run(root, "pred-domain-run-context")
                _write_json(run / "input" / "run_context.json", {"domain_mode": True})
                required, matched = stage_guard.review_predicate_required(run)
                self.assertTrue(required)
                self.assertIn("domain_mode", matched)
            with self.subTest(condition="domain_mode_run_context_false_is_inactive"):
                run = _make_run(root, "pred-domain-run-context-false")
                _write_json(run / "input" / "run_context.json", {"domain_mode": False})
                self.assertFalse(stage_guard.domain_mode_active(run))
            with self.subTest(condition="report_depth_deep"):
                run = _make_run(root, "pred-deep")
                _write_json(run / "manifest.json", {"intake": {"report": {"depth": "deep"}}})
                required, matched = stage_guard.review_predicate_required(run)
                self.assertTrue(required)
                self.assertIn("report_depth_deep", matched)
            with self.subTest(condition="decision_analysis_mode"):
                run = _make_run(root, "pred-decision")
                _write_json(run / "manifest.json", {"intake": {"analysis_mode": "candidate_prioritization"}})
                required, matched = stage_guard.review_predicate_required(run)
                self.assertTrue(required)
                self.assertIn("decision_analysis_mode", matched)


# ── stage_guard.py: §8.5 domain readiness ───────────────────────────────

class StageGuardDomainReadinessTests(unittest.TestCase):
    def test_ready_and_insufficient_status_and_missing_fields(self):
        with self.subTest(case="all fields filled -> ready"):
            intake = {
                "row_meaning": "1행=1거래",
                "entity_grain": "거래",
                "column_semantics": [{"column": "amt", "meaning": "금액"}],
                "exclusion_rules": ["테스트 제외"],
                "objective": "이상 거래 탐지",
                "forbidden_claims": [{"phrase": "사기다"}],
            }
            status, missing = stage_guard.compute_domain_readiness(intake)
            self.assertEqual(status, "ready")
            self.assertEqual(missing, [])
        with self.subTest(case="all fields empty -> insufficient"):
            status, missing = stage_guard.compute_domain_readiness({})
            self.assertEqual(status, "insufficient")
            self.assertEqual(set(missing), set(stage_guard.DOMAIN_REQUIRED_FIELDS))
            self.assertEqual(len(missing), 6)

    def test_partial_fill_and_empty_list_counts_as_missing(self):
        intake = {
            "row_meaning": "1행=1거래",
            "entity_grain": "거래",
            "column_semantics": [],  # empty list must count as missing, not "filled"
            "exclusion_rules": ["테스트 제외"],
            "objective": "이상 거래 탐지",
            "forbidden_claims": [{"phrase": "사기다"}],
        }
        status, missing = stage_guard.compute_domain_readiness(intake)
        self.assertEqual(status, "partial")
        self.assertEqual(missing, ["column_semantics"])


# ── stage_guard.py: effective_stage_requirements ────────────────────────

class StageGuardEffectiveRequirementsTests(unittest.TestCase):
    def test_inserts_review_before_storyboard_for_statistical_route(self):
        with tempfile.TemporaryDirectory() as tmp:
            run = _make_run(Path(tmp), "eff-a")
            _write_method_route(run, route="statistical", selected_methods=["group_difference_candidate"])
            expected = {
                "visualize": ("data_profile", "analysis_strategy", "analysis_result_review", "dashboard_storyboard"),
                "qa": ("data_profile", "analysis_strategy", "analysis_result_review", "dashboard_storyboard"),
                "communicate": (
                    "data_profile", "analysis_strategy", "analysis_result_review",
                    "dashboard_storyboard", "report_outline",
                ),
            }
            for stage, expected_tuple in expected.items():
                with self.subTest(stage=stage):
                    self.assertEqual(stage_guard.effective_stage_requirements(run, stage), expected_tuple)

    def test_unaffected_for_frame_and_analyze_even_with_deep_review_route(self):
        with tempfile.TemporaryDirectory() as tmp:
            run = _make_run(Path(tmp), "eff-b")
            _write_method_route(run, route="statistical", selected_methods=["group_difference_candidate"])
            self.assertEqual(
                stage_guard.effective_stage_requirements(run, "frame"),
                stage_guard.STAGE_REQUIREMENTS["frame"],
            )
            self.assertEqual(
                stage_guard.effective_stage_requirements(run, "analyze"),
                stage_guard.STAGE_REQUIREMENTS["analyze"],
            )

    def test_descriptive_route_matches_static_table_for_all_stages(self):
        with tempfile.TemporaryDirectory() as tmp:
            run = _make_run(Path(tmp), "eff-c")
            _write_method_route(run, route="descriptive", selected_methods=["ranking"])
            for stage in stage_guard.STAGE_REQUIREMENTS:
                with self.subTest(stage=stage):
                    self.assertEqual(
                        stage_guard.effective_stage_requirements(run, stage),
                        stage_guard.STAGE_REQUIREMENTS[stage],
                    )


# ── stage_guard.py: §7.2 analysis_strategy_lock_issues ──────────────────

class StageGuardAnalysisStrategyLockTests(unittest.TestCase):
    def test_matching_hashes_produce_no_issues(self):
        with tempfile.TemporaryDirectory() as tmp:
            run = _make_run(Path(tmp), "lock-a")
            mr_path = _write_method_route(run, route="descriptive", selected_methods=["ranking"])
            dp_path = _write_dependency_plan(run)
            _write_analysis_strategy_question(run, {
                "method_route": {"sha256": stage_guard.sha256_file(mr_path)},
                "dependency_plan": {"sha256": stage_guard.sha256_file(dp_path)},
            })
            issues = stage_guard.analysis_strategy_lock_issues(run, {})
            self.assertEqual(issues, [])

    def test_route_changed_upward_without_downgraded_from_requires_reapproval(self):
        with tempfile.TemporaryDirectory() as tmp:
            run = _make_run(Path(tmp), "lock-b")
            mr_path = _write_method_route(run, route="statistical", selected_methods=["group_difference_candidate"])
            _write_analysis_strategy_question(run, {"method_route": {"sha256": stage_guard.sha256_file(mr_path)}})
            _write_method_route(run, route="predictive", selected_methods=["ranking"])
            issues = stage_guard.analysis_strategy_lock_issues(run, {})
            self.assertTrue(any("재승인" in i for i in issues))
            self.assertTrue(any("상향" in i for i in issues))

    def test_recorded_downgrade_requires_reason_but_is_allowed_once_recorded(self):
        with tempfile.TemporaryDirectory() as tmp:
            run = _make_run(Path(tmp), "lock-c")
            mr_path = _write_method_route(run, route="statistical", selected_methods=["group_difference_candidate"])
            _write_analysis_strategy_question(run, {"method_route": {"sha256": stage_guard.sha256_file(mr_path)}})

            _write_method_route(
                run, route="descriptive", selected_methods=["ranking"],
                downgraded_from="statistical", downgrade_reason="",
            )
            issues_no_reason = stage_guard.analysis_strategy_lock_issues(run, {})
            self.assertTrue(any("downgrade_reason" in i for i in issues_no_reason))

            _write_method_route(
                run, route="descriptive", selected_methods=["ranking"],
                downgraded_from="statistical", downgrade_reason="표본 수 부족",
            )
            issues_with_reason = stage_guard.analysis_strategy_lock_issues(run, {})
            self.assertEqual(issues_with_reason, [])

    def test_route_created_after_approval_with_deep_route_and_no_downgrade_requires_reapproval(self):
        with tempfile.TemporaryDirectory() as tmp:
            run = _make_run(Path(tmp), "lock-d")
            # approval_targets recorded before method_route.json existed: no "method_route" key.
            _write_analysis_strategy_question(run, {"dependency_plan": {"sha256": "0" * 64}})
            _write_method_route(run, route="ml_exploratory", selected_methods=["clustering_candidate"])
            issues = stage_guard.analysis_strategy_lock_issues(run, {})
            self.assertTrue(any("심화 route로" in i for i in issues))

    def test_dependency_plan_expansion_requires_install_approval_unless_missing_is_empty(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            run1 = _make_run(root, "lock-e1")
            dp_path = _write_dependency_plan(run1, required_extras=["stats"], missing=[])
            _write_analysis_strategy_question(run1, {"dependency_plan": {"sha256": stage_guard.sha256_file(dp_path)}})
            _write_dependency_plan(run1, required_extras=["stats"], missing=["stats"])
            issues = stage_guard.analysis_strategy_lock_issues(run1, {})
            self.assertTrue(any("설치 승인이" in i for i in issues))

            run2 = _make_run(root, "lock-e2")
            dp_path2 = _write_dependency_plan(run2, required_extras=[], missing=[])
            _write_analysis_strategy_question(run2, {"dependency_plan": {"sha256": stage_guard.sha256_file(dp_path2)}})
            _write_dependency_plan(run2, required_extras=["ml"], installed=["ml"], missing=[])
            issues2 = stage_guard.analysis_strategy_lock_issues(run2, {})
            self.assertEqual(issues2, [])


# ── stage_guard.py: analyze_domain_entry_issues ─────────────────────────

class StageGuardDomainEntryTests(unittest.TestCase):
    def test_blocks_missing_intake_and_domain_conditioned_method_selection(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            with self.subTest(case="domain mode active but no domain_intake.json"):
                run = _make_run(root, "domain-a")
                _write_json(run / "manifest.json", {"domain_mode": True})
                issues = stage_guard.analyze_domain_entry_issues(run)
                self.assertTrue(any("domain_intake.json이 없습니다" in i for i in issues))
            with self.subTest(case="insufficient intake + domain-conditioned method selected"):
                run = _make_run(root, "domain-b")
                _write_domain_intake(run)  # all empty -> insufficient
                _write_method_route(run, route="statistical", selected_methods=["group_difference_candidate"])
                issues = stage_guard.analyze_domain_entry_issues(run)
                self.assertTrue(any("도메인 조건이 필요한" in i for i in issues))

    def test_allows_core_only_selection_and_non_domain_mode_runs(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            with self.subTest(case="insufficient intake but only core method selected"):
                run = _make_run(root, "domain-c")
                _write_domain_intake(run)
                _write_method_route(run, route="descriptive", selected_methods=["ranking"])
                self.assertEqual(stage_guard.analyze_domain_entry_issues(run), [])
            with self.subTest(case="not domain mode"):
                run = _make_run(root, "domain-d")
                self.assertEqual(stage_guard.analyze_domain_entry_issues(run), [])


# ── dik_checkpoint_hook.py: install command gate ────────────────────────

class HookInstallCommandTests(unittest.TestCase):
    def _make_kit(self, tmp: Path) -> Path:
        kit = tmp / "kit"
        (kit / "scripts").mkdir(parents=True)
        (kit / "docs").mkdir(parents=True)
        (kit / "methods").mkdir(parents=True)
        (kit / "scripts" / "stage_guard.py").write_text("x", encoding="utf-8")
        (kit / "docs" / "pipeline-contract.md").write_text("x", encoding="utf-8")
        shutil.copy(KIT_ROOT / "methods" / "method_registry.json", kit / "methods" / "method_registry.json")
        return kit

    def _make_valid_run(self, kit: Path, run_id: str, dependency_decision: str = "install") -> Path:
        run = _make_run(kit, run_id)
        created = "2026-07-10T00:00:00+00:00"
        qpath = run / "outputs" / "checkpoints" / "02_analysis_strategy_question.json"
        qpath.write_text(
            json.dumps({"checkpoint_id": "analysis_strategy", "created_at": created}, ensure_ascii=False),
            encoding="utf-8",
        )
        rel = f"runs/{run.name}/outputs/checkpoints/02_analysis_strategy_question.json"
        answer = {
            "answer_id": "a-install-1",
            "checkpoint_id": "analysis_strategy",
            "recorded_by": "scripts/apply_checkpoint_answer.py",
            "source": "user_chat",
            "transcript_ref": "thread:install",
            "user_response": "네, 설치하고 진행하세요.",
            "human_confirmed": True,
            "approval_contract_version": "checkpoint-answer.v3",
            "continue_pipeline": True,
            "answered_at": "2026-07-10T00:05:00+00:00",
            "question_ref": {
                "path": rel,
                "sha256": hashlib.sha256(qpath.read_bytes()).hexdigest(),
                "created_at": created,
                "checkpoint_id": "analysis_strategy",
            },
            "maps_to": {"dependency_decision": dependency_decision},
        }
        _write_json(run / "checkpoint_answers.json", {"answers": [answer]})
        _write_json(run / "input" / "dependency_plan.json", {
            "approval": {"answer_id": answer["answer_id"], "dependency_decision": dependency_decision},
        })
        return run

    def test_allowed_single_install_with_valid_provenance_has_no_issues(self):
        with tempfile.TemporaryDirectory() as tmp:
            kit = self._make_kit(Path(tmp))
            run = self._make_valid_run(kit, "install-ok")
            issues = hook.install_command_issues(run, "pip install scipy")
            self.assertEqual(issues, [])

    def test_disallowed_package_and_chained_command_report_the_offending_package(self):
        with tempfile.TemporaryDirectory() as tmp:
            kit = self._make_kit(Path(tmp))
            run = self._make_valid_run(kit, "install-bad-pkg")
            with self.subTest(command="single disallowed package"):
                issues = hook.install_command_issues(run, "pip install evil-pkg")
                self.assertTrue(any("evil-pkg" in i for i in issues))
            with self.subTest(command="chained command hides a second install"):
                issues = hook.install_command_issues(run, "pip install scipy && pip install evil-pkg")
                self.assertTrue(any("evil-pkg" in i for i in issues))

    def test_blanket_and_unapproved_extra_flags_are_rejected(self):
        with tempfile.TemporaryDirectory() as tmp:
            kit = self._make_kit(Path(tmp))
            run = self._make_valid_run(kit, "install-extra-flags")
            with self.subTest(flag="--all-extras"):
                issues = hook.install_command_issues(run, "uv sync --all-extras")
                self.assertTrue(any("전체 extra" in i for i in issues))
            with self.subTest(flag="--extra bogus"):
                issues = hook.install_command_issues(run, "uv sync --extra bogus")
                self.assertTrue(any("bogus" in i for i in issues))

    def test_hyphenated_lookalike_word_is_not_detected_as_install(self):
        with tempfile.TemporaryDirectory() as tmp:
            kit = self._make_kit(Path(tmp))
            run = self._make_valid_run(kit, "install-hyphen")
            issues = hook.install_command_issues(run, "pip install-something-else")
            self.assertEqual(issues, [])

    def test_missing_approval_produces_provenance_issue(self):
        with tempfile.TemporaryDirectory() as tmp:
            kit = self._make_kit(Path(tmp))
            run = _make_run(kit, "install-no-approval")
            _write_json(run / "input" / "dependency_plan.json", {"approval": None})
            issues = hook.install_command_issues(run, "pip install scipy")
            self.assertTrue(any("approval=null" in i for i in issues))

    def test_uv_add_is_denied_even_with_valid_provenance(self):
        # interview-loop-v2 spec §9 (v1 발견 3): uv add는 pyproject.toml을 바꾸므로
        # allowlist 패키지 + 유효 승인이어도 전면 deny.
        with tempfile.TemporaryDirectory() as tmp:
            kit = self._make_kit(Path(tmp))
            run = self._make_valid_run(kit, "install-uv-add")
            with self.subTest(command="allowlisted package with approval"):
                issues = hook.install_command_issues(run, "uv add scipy")
                self.assertTrue(any("uv add" in i for i in issues))
                self.assertTrue(any("uv sync --extra" in i for i in issues))
            with self.subTest(command="chained behind an approved sync"):
                issues = hook.install_command_issues(run, "uv sync --extra stats && uv add scipy")
                self.assertTrue(any("uv add" in i for i in issues))

    def test_uv_sync_allowed_extra_with_valid_provenance_has_no_issues(self):
        with tempfile.TemporaryDirectory() as tmp:
            kit = self._make_kit(Path(tmp))
            run = self._make_valid_run(kit, "install-uv-sync-ok")
            issues = hook.install_command_issues(run, "uv sync --extra stats")
            self.assertEqual(issues, [])


# ── dik_checkpoint_hook.py: domain-pack write gate + bash destinations ──

class HookDomainPackAndBashWriteTests(unittest.TestCase):
    def _make_kit(self, tmp: Path) -> Path:
        kit = tmp / "kit"
        (kit / "scripts").mkdir(parents=True)
        (kit / "docs").mkdir(parents=True)
        (kit / "scripts" / "stage_guard.py").write_text("x", encoding="utf-8")
        (kit / "docs" / "pipeline-contract.md").write_text("x", encoding="utf-8")
        return kit

    def test_domain_pack_write_target_named_pack_vs_template_vs_no_markers(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            kit = self._make_kit(root)
            with self.subTest(case="named pack under kit with markers"):
                target = kit / "domains" / "real" / "kpi-rules.md"
                self.assertEqual(hook.domain_pack_write_target(target), "real")
            with self.subTest(case="template pack is exempt"):
                target = kit / "domains" / "template" / "x.md"
                self.assertIsNone(hook.domain_pack_write_target(target))
            with self.subTest(case="domains/ path with no kit markers in any ancestor"):
                stray = root / "not-a-kit" / "domains" / "real" / "y.md"
                self.assertIsNone(hook.domain_pack_write_target(stray))

    def test_bash_write_destinations_extracts_redirect_and_copy_targets_without_runs_filter(self):
        destinations = hook.bash_write_destinations(
            "cat a.txt > outside/file.txt && tee -a runs/hook-run/outputs/log.txt "
            "&& cp x.md domains/real/kpi-rules.md"
        )
        as_str = [str(p) for p in destinations]
        self.assertIn("outside/file.txt", as_str)
        self.assertIn("domains/real/kpi-rules.md", as_str)
        self.assertIn("runs/hook-run/outputs/log.txt", as_str)


# ── dependency_preflight.py: downgrade_method_route ─────────────────────

class DependencyPreflightDowngradeTests(unittest.TestCase):
    def _registry(self) -> dict:
        return json.loads((KIT_ROOT / "methods" / "method_registry.json").read_text(encoding="utf-8"))

    def _make_run_with_route(self, tmp: Path, run_id: str, route: str, selected_methods: list[str]) -> Path:
        run = tmp / "runs" / run_id
        (run / "outputs").mkdir(parents=True)
        _write_method_route(run, route=route, selected_methods=selected_methods)
        return run

    def test_downgrades_to_descriptive_when_core_has_no_diagnostic_method(self):
        with tempfile.TemporaryDirectory() as tmp:
            run = self._make_run_with_route(
                Path(tmp), "dg-desc", "statistical", ["group_difference_candidate", "ranking"]
            )
            new_route = preflight.downgrade_method_route(run, self._registry(), "표본 부족")
            self.assertEqual(new_route, "descriptive")
            data = json.loads((run / "outputs" / "method_route.json").read_text())
            self.assertEqual(data["route"], "descriptive")
            self.assertEqual(data["selected_methods"], ["ranking"])
            self.assertEqual(data["downgraded_from"], "statistical")
            self.assertEqual(data["downgrade_reason"], "표본 부족")
            self.assertEqual(data["dependency_groups"], [])

    def test_downgrades_to_diagnostic_when_core_has_a_diagnostic_method(self):
        with tempfile.TemporaryDirectory() as tmp:
            run = self._make_run_with_route(
                Path(tmp), "dg-diag", "statistical", ["quality", "group_difference_candidate"]
            )
            new_route = preflight.downgrade_method_route(run, self._registry(), "설치 미승인")
            self.assertEqual(new_route, "diagnostic")
            data = json.loads((run / "outputs" / "method_route.json").read_text())
            self.assertEqual(data["selected_methods"], ["quality"])

    def test_downgraded_from_is_preserved_across_repeated_downgrades_but_reason_updates(self):
        with tempfile.TemporaryDirectory() as tmp:
            run = self._make_run_with_route(
                Path(tmp), "dg-repeat", "statistical", ["group_difference_candidate", "ranking"]
            )
            registry = self._registry()
            preflight.downgrade_method_route(run, registry, "1차 사유")
            first = json.loads((run / "outputs" / "method_route.json").read_text())
            self.assertEqual(first["downgraded_from"], "statistical")

            preflight.downgrade_method_route(run, registry, "2차 사유")
            second = json.loads((run / "outputs" / "method_route.json").read_text())
            self.assertEqual(second["downgraded_from"], "statistical")  # preserved, not overwritten
            self.assertEqual(second["downgrade_reason"], "2차 사유")  # reason still updates


# ── dependency_preflight.py: apply_approval ──────────────────────────────

class DependencyPreflightApplyApprovalTests(unittest.TestCase):
    def _registry(self) -> dict:
        return json.loads((KIT_ROOT / "methods" / "method_registry.json").read_text(encoding="utf-8"))

    def _make_run(self, tmp: Path, run_id: str) -> Path:
        run = _make_run(tmp, run_id)
        _write_method_route(
            run, route="statistical", selected_methods=["group_difference_candidate", "ranking"],
            dependency_groups=["stats"],
        )
        return run

    def _valid_answer(self, run: Path, dependency_decision: str) -> dict:
        created = "2026-07-10T00:00:00+00:00"
        qpath = run / "outputs" / "checkpoints" / "02_analysis_strategy_question.json"
        qpath.write_text(
            json.dumps({"checkpoint_id": "analysis_strategy", "created_at": created}, ensure_ascii=False),
            encoding="utf-8",
        )
        rel = f"runs/{run.name}/outputs/checkpoints/02_analysis_strategy_question.json"
        answer = {
            "answer_id": "a-apply-1",
            "checkpoint_id": "analysis_strategy",
            "recorded_by": "scripts/apply_checkpoint_answer.py",
            "source": "user_chat",
            "transcript_ref": "thread:apply",
            "user_response": "네, 진행하세요.",
            "human_confirmed": True,
            "approval_contract_version": "checkpoint-answer.v3",
            "continue_pipeline": True,
            "answered_at": "2026-07-10T00:05:00+00:00",
            "question_ref": {
                "path": rel,
                "sha256": hashlib.sha256(qpath.read_bytes()).hexdigest(),
                "created_at": created,
                "checkpoint_id": "analysis_strategy",
            },
            "maps_to": {"dependency_decision": dependency_decision},
        }
        _write_json(run / "checkpoint_answers.json", {"answers": [answer]})
        return answer

    def _plan(self, run: Path, missing: list[str]) -> dict:
        return {
            "schema_version": "data-insight-kit.dependency_plan.v1",
            "run_id": run.name,
            "created_at": "2026-07-10T00:00:00Z",
            "environment": {
                "kit_root": str(KIT_ROOT), "venv_path": str(KIT_ROOT / ".venv"), "basis": "kit_local_venv",
            },
            "required_extras": missing,
            "installed": [],
            "missing": missing,
            "approval": None,
            "install_result": None,
        }

    def test_skip_install_downgrades_route_and_clears_missing(self):
        with tempfile.TemporaryDirectory() as tmp:
            run = self._make_run(Path(tmp), "apply-skip")
            self._valid_answer(run, "skip_install")
            plan = self._plan(run, ["stats"])
            rc = preflight.apply_approval(run, KIT_ROOT, self._registry(), plan)
            self.assertEqual(rc, 0)
            self.assertEqual(plan["approval"]["dependency_decision"], "skip_install")
            self.assertIsNone(plan["install_result"])
            self.assertEqual(plan["missing"], [])
            route_data = json.loads((run / "outputs" / "method_route.json").read_text())
            self.assertEqual(route_data["route"], "descriptive")
            self.assertEqual(route_data["downgraded_from"], "statistical")

    def test_no_missing_extras_returns_zero_without_touching_approval_or_writing_plan(self):
        with tempfile.TemporaryDirectory() as tmp:
            run = self._make_run(Path(tmp), "apply-nomiss")
            self._valid_answer(run, "install")
            plan = self._plan(run, [])
            rc = preflight.apply_approval(run, KIT_ROOT, self._registry(), plan)
            self.assertEqual(rc, 0)
            self.assertIsNone(plan["approval"])
            self.assertFalse((run / "input" / "dependency_plan.json").exists())

    def test_install_success_stub_records_installed_extras(self):
        with tempfile.TemporaryDirectory() as tmp:
            run = self._make_run(Path(tmp), "apply-install-ok")
            self._valid_answer(run, "install")
            plan = self._plan(run, ["stats"])
            original_run = preflight.subprocess.run
            preflight.subprocess.run = lambda cmd, capture_output, text: SimpleNamespace(
                returncode=0, stdout="", stderr=""
            )
            try:
                rc = preflight.apply_approval(run, KIT_ROOT, self._registry(), plan)
            finally:
                preflight.subprocess.run = original_run
            self.assertEqual(rc, 0)
            self.assertEqual(plan["install_result"]["status"], "success")
            self.assertEqual(plan["missing"], [])
            self.assertIn("stats", plan["installed"])

    def test_install_failure_stub_downgrades_route_but_keeps_approval_recorded(self):
        with tempfile.TemporaryDirectory() as tmp:
            run = self._make_run(Path(tmp), "apply-install-fail")
            self._valid_answer(run, "install")
            plan = self._plan(run, ["stats"])
            original_run = preflight.subprocess.run
            preflight.subprocess.run = lambda cmd, capture_output, text: SimpleNamespace(
                returncode=1, stdout="", stderr="network unreachable"
            )
            try:
                rc = preflight.apply_approval(run, KIT_ROOT, self._registry(), plan)
            finally:
                preflight.subprocess.run = original_run
            self.assertEqual(rc, 0)
            self.assertEqual(plan["install_result"]["status"], "failed")
            self.assertIsNotNone(plan["install_result"]["fallback_route"])
            self.assertEqual(plan["approval"]["dependency_decision"], "install")


# ── qa/validate.py ────────────────────────────────────────────────────

class QaBaseTestCase(unittest.TestCase):
    def setUp(self):
        qa.BLOCK.clear()
        qa.WARN.clear()


class QaRequiredCheckpointsTests(QaBaseTestCase):
    def test_legacy_and_descriptive_runs_keep_base_checkpoint_tuple(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            with self.subTest(case="legacy run without method_route.json, depth=deep"):
                run = _make_run(root, "qa-legacy")
                manifest = {"intake": {"report": {"depth": "deep"}}}
                result = qa._required_checkpoints_for(run, manifest, post_communicate=False)
                self.assertEqual(result, qa.REQUIRED_PRE_REPORT_CHECKPOINTS)
            with self.subTest(case="routing run, descriptive + standard depth"):
                run = _make_run(root, "qa-routing-plain")
                _write_json(run / "outputs" / "method_route.json", {"route": "descriptive"})
                result = qa._required_checkpoints_for(run, {}, post_communicate=False)
                self.assertEqual(result, qa.REQUIRED_PRE_REPORT_CHECKPOINTS)

    def test_routing_run_with_deep_review_route_inserts_review_before_storyboard(self):
        with tempfile.TemporaryDirectory() as tmp:
            run = _make_run(Path(tmp), "qa-routing-deep")
            _write_json(run / "outputs" / "method_route.json", {"route": "statistical"})
            result = qa._required_checkpoints_for(run, {}, post_communicate=False)
            self.assertEqual(
                result,
                ("data_profile", "analysis_strategy", "analysis_result_review", "dashboard_storyboard"),
            )


class QaMethodRouteDependencyChecksTests(QaBaseTestCase):
    def test_missing_method_route_warns_only(self):
        with tempfile.TemporaryDirectory() as tmp:
            run = _make_run(Path(tmp), "mrd-missing")
            qa.method_route_and_dependency_checks(_data_path(run))
            self.assertEqual(qa.BLOCK, [])
            self.assertTrue(any("method_route.json 없음" in w for w in qa.WARN))

    def test_unknown_selected_method_blocks(self):
        with tempfile.TemporaryDirectory() as tmp:
            run = _make_run(Path(tmp), "mrd-unknown-method")
            _write_method_route(run, route="descriptive", selected_methods=["ghost_method"])
            qa.method_route_and_dependency_checks(_data_path(run))
            self.assertTrue(any("ghost_method" in b and "method registry에 없음" in b for b in qa.BLOCK))

    def test_predictive_route_without_data_condition_evidence_blocks(self):
        with tempfile.TemporaryDirectory() as tmp:
            run = _make_run(Path(tmp), "mrd-predictive")
            _write_method_route(run, route="predictive", selected_methods=["ranking"])
            qa.method_route_and_dependency_checks(_data_path(run))
            self.assertTrue(any("data_condition_evidence" in b for b in qa.BLOCK))

    def test_dependency_groups_without_plan_blocks(self):
        with tempfile.TemporaryDirectory() as tmp:
            run = _make_run(Path(tmp), "mrd-no-plan")
            _write_method_route(
                run, route="statistical", selected_methods=["group_difference_candidate"],
                dependency_groups=["stats"],
            )
            qa.method_route_and_dependency_checks(_data_path(run))
            self.assertTrue(any("dependency_plan.json 없음" in b for b in qa.BLOCK))

    def test_dependency_plan_extra_outside_allowlist_blocks(self):
        with tempfile.TemporaryDirectory() as tmp:
            run = _make_run(Path(tmp), "mrd-bad-extra")
            _write_dependency_plan(run, required_extras=["viz"], installed=[], missing=[])
            qa.method_route_and_dependency_checks(_data_path(run))
            self.assertTrue(any("allowlist 밖 extra 'viz'" in b for b in qa.BLOCK))

    def test_install_result_success_without_approval_blocks(self):
        with tempfile.TemporaryDirectory() as tmp:
            run = _make_run(Path(tmp), "mrd-no-approval")
            _write_dependency_plan(
                run, install_result={"status": "success", "extras": ["stats"]}, approval=None
            )
            qa.method_route_and_dependency_checks(_data_path(run))
            self.assertTrue(any("install 승인 기록 없음" in b for b in qa.BLOCK))


class QaApprovalTargetLockTests(QaBaseTestCase):
    def test_matching_hashes_produce_no_block(self):
        with tempfile.TemporaryDirectory() as tmp:
            run = _make_run(Path(tmp), "lock-qa-a")
            mr_path = _write_method_route(run, route="descriptive", selected_methods=["ranking"])
            _write_analysis_strategy_question(run, {"method_route": {"sha256": qa._sha256_file(mr_path)}})
            _write_json(run / "checkpoint_answers.json", {"answers": [{"checkpoint_id": "analysis_strategy"}]})
            qa.approval_target_lock_checks(_data_path(run))
            self.assertEqual(qa.BLOCK, [])

    def test_upward_change_blocks_and_recorded_downgrade_with_reason_does_not(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            with self.subTest(case="upward change"):
                run = _make_run(root, "lock-qa-b")
                mr_path = _write_method_route(run, route="statistical", selected_methods=["group_difference_candidate"])
                _write_analysis_strategy_question(run, {"method_route": {"sha256": qa._sha256_file(mr_path)}})
                _write_json(run / "checkpoint_answers.json", {"answers": [{"checkpoint_id": "analysis_strategy"}]})
                _write_method_route(run, route="predictive", selected_methods=["ranking"])
                qa.approval_target_lock_checks(_data_path(run))
                self.assertTrue(any("재승인 필요" in b for b in qa.BLOCK))
            qa.BLOCK.clear()
            with self.subTest(case="recorded downgrade with reason"):
                run = _make_run(root, "lock-qa-c")
                mr_path = _write_method_route(run, route="statistical", selected_methods=["group_difference_candidate"])
                _write_analysis_strategy_question(run, {"method_route": {"sha256": qa._sha256_file(mr_path)}})
                _write_json(run / "checkpoint_answers.json", {"answers": [{"checkpoint_id": "analysis_strategy"}]})
                _write_method_route(
                    run, route="descriptive", selected_methods=["ranking"],
                    downgraded_from="statistical", downgrade_reason="표본 부족",
                )
                qa.approval_target_lock_checks(_data_path(run))
                self.assertEqual(qa.BLOCK, [])


class QaDomainReadinessMirrorTests(QaBaseTestCase):
    def test_compute_domain_readiness_matches_expected_status_and_missing(self):
        with self.subTest(case="ready"):
            intake = {
                "row_meaning": "1행=1거래", "entity_grain": "거래",
                "column_semantics": [{"column": "amt", "meaning": "금액"}],
                "exclusion_rules": ["테스트 제외"], "objective": "이상 거래 탐지",
                "forbidden_claims": [{"phrase": "사기다"}],
            }
            status, missing = qa._compute_domain_readiness(intake)
            self.assertEqual(status, "ready")
            self.assertEqual(missing, [])
        with self.subTest(case="insufficient"):
            status, missing = qa._compute_domain_readiness({})
            self.assertEqual(status, "insufficient")
            self.assertEqual(sorted(missing), sorted(qa.DOMAIN_REQUIRED_INTAKE_FIELDS))

    def test_cross_implementation_agreement_with_stage_guard(self):
        """The most valuable test in this file: stage_guard.compute_domain_readiness
        and qa._compute_domain_readiness are independent re-implementations of the
        same spec §8.5 rule. If they ever drift, guard and QA would disagree on
        whether a run is allowed to state domain conclusions."""
        samples = [
            {},
            {
                "row_meaning": "1행=1거래", "entity_grain": "거래",
                "column_semantics": [{"column": "amt", "meaning": "금액"}],
                "exclusion_rules": ["테스트 제외"], "objective": "이상 거래 탐지",
                "forbidden_claims": [{"phrase": "사기다"}],
            },
            {
                "row_meaning": "1행=1거래", "entity_grain": "거래",
                "column_semantics": [],
                "exclusion_rules": ["테스트 제외"], "objective": "이상 거래 탐지",
                "forbidden_claims": [{"phrase": "사기다"}],
            },
            {"row_meaning": "1행=1거래"},
        ]
        for intake in samples:
            with self.subTest(intake=intake):
                self.assertEqual(
                    stage_guard.compute_domain_readiness(intake),
                    qa._compute_domain_readiness(intake),
                )


class QaDomainReadinessChecksTests(QaBaseTestCase):
    def test_insufficient_intake_blocks_confident_conclusion_but_allows_safe_context(self):
        with tempfile.TemporaryDirectory() as tmp:
            run = _make_run(Path(tmp), "domain-readiness-a")
            _write_domain_intake(run)  # all empty -> insufficient, recorded status matches
            data_blocking = {
                "meta": {"title": "분석"}, "kpis": [],
                "panels": [{"charts": [{"id": "c1", "title": "이 매장을 추천합니다", "desc": "요약"}]}],
            }
            qa.domain_readiness_checks(_data_path(run), data_blocking, {}, post_communicate=False)
            self.assertTrue(any("추천합니다" in b for b in qa.BLOCK))

            qa.BLOCK.clear()
            data_safe = {
                "meta": {"title": "분석"}, "kpis": [],
                "panels": [{"charts": [{"id": "c1", "title": "데이터 한계 내에서 추천합니다", "desc": "요약"}]}],
            }
            qa.domain_readiness_checks(_data_path(run), data_safe, {}, post_communicate=False)
            self.assertEqual(qa.BLOCK, [])

    def test_recorded_ready_status_mismatched_with_recomputed_insufficient_blocks(self):
        with tempfile.TemporaryDirectory() as tmp:
            run = _make_run(Path(tmp), "domain-readiness-b")
            _write_domain_intake(run, domain_readiness={"status": "ready"})
            qa.domain_readiness_checks(
                _data_path(run), {"meta": {}, "kpis": [], "panels": []}, {}, post_communicate=False
            )
            self.assertTrue(any("QA 재계산" in b for b in qa.BLOCK))

    def test_run_context_stamp_activates_domain_mode_in_qa(self):
        with tempfile.TemporaryDirectory() as tmp:
            run = _make_run(Path(tmp), "domain-readiness-run-context")
            _write_json(run / "input" / "run_context.json", {"domain_mode": True})
            required, matched = qa._review_predicate_required(run, {})
            self.assertTrue(required)
            self.assertIn("domain_mode", matched)
            qa.domain_readiness_checks(
                _data_path(run), {"meta": {}, "kpis": [], "panels": []}, {}, post_communicate=False
            )
            self.assertTrue(any("domain_intake.json 없음" in b for b in qa.BLOCK))


class QaDomainForbiddenClaimsAndOverclaimTests(QaBaseTestCase):
    def test_forbidden_phrase_in_chart_title_blocks_when_present_and_passes_when_absent(self):
        with tempfile.TemporaryDirectory() as tmp:
            run = _make_run(Path(tmp), "forbidden-claims")
            _write_domain_intake(run, forbidden_claims=[{"phrase": "원인이다"}])

            data_hit = {"meta": {}, "kpis": [], "panels": [{"charts": [{"id": "c1", "title": "재고 부족이 원인이다"}]}]}
            qa.domain_forbidden_claims_checks(_data_path(run), data_hit, post_communicate=False)
            self.assertTrue(any("원인이다" in b for b in qa.BLOCK))

            qa.BLOCK.clear()
            data_clean = {"meta": {}, "kpis": [], "panels": [{"charts": [{"id": "c1", "title": "재고 추세"}]}]}
            qa.domain_forbidden_claims_checks(_data_path(run), data_clean, post_communicate=False)
            self.assertEqual(qa.BLOCK, [])

    def test_statistical_overclaim_warns_on_assertion_and_skips_negation(self):
        with tempfile.TemporaryDirectory() as tmp:
            run = _make_run(Path(tmp), "overclaim")
            analysis_path = run / "outputs" / "04_analysis.md"
            analysis_path.write_text("p-value 0.03으로 인과관계를 입증한다\n", encoding="utf-8")
            qa.statistical_overclaim_checks(_data_path(run), post_communicate=False)
            self.assertTrue(any("단정 의심" in w for w in qa.WARN))

            qa.WARN.clear()
            analysis_path.write_text("상관계수만으로 인과관계를 단정할 수 없다\n", encoding="utf-8")
            qa.statistical_overclaim_checks(_data_path(run), post_communicate=False)
            self.assertEqual(qa.WARN, [])


# ── dashboard-profile-v4: 스키마 확장 + E1 계약 QA (spec §4.0~4.2) ──────

DASHBOARD_SCHEMA = json.loads(
    (KIT_ROOT / "schemas" / "dashboard_data.schema.json").read_text(encoding="utf-8")
)
CHART_SPEC_SCHEMA = json.loads(
    (KIT_ROOT / "schemas" / "chart_spec.schema.json").read_text(encoding="utf-8")
)


def _v4_provenance(periods):
    return {"source_id": "src1", "time_field": "ym", "periods": list(periods)}


def _v4_dashboard_data(kpi_extra=None):
    kpi = {
        "id": "k1", "label": "월 거래는 늘었는가?", "value": 123, "unit": "건",
        "kind": "absolute", "status": "good",
    }
    kpi.update(kpi_extra or {})
    return {
        "meta": {
            "title": "테스트", "domain": "테스트", "audience": "mixed",
            "mode": "directed", "generated_at": "2026-07-13T00:00:00Z", "language": "ko",
        },
        "sources": [{
            "id": "src1", "type": "file", "ref": "input/a.parquet",
            "snapshot_at": "2026-07-13T00:00:00Z",
            "sample_policy": {"sampled": False, "n": 10},
        }],
        "kpis": [kpi],
        "panels": [{
            "id": "p1", "title": "패널",
            "charts": [{
                "id": "c1", "type": "bar", "title": "차트",
                "encoding": {
                    "x": {"type": "category", "label": "구", "values": ["강남", "서초"]},
                    "series": [{"label": "건수", "unit": "건", "values": [10, 20]}],
                    "stack": "none",
                },
            }],
        }],
    }


def _schema_ok(data):
    import jsonschema

    try:
        jsonschema.validate(data, DASHBOARD_SCHEMA)
        return True
    except jsonschema.ValidationError:
        return False


class ProfileV4SchemaTests(unittest.TestCase):
    def test_legacy_kpi_without_v4_fields_still_validates(self):
        self.assertTrue(_schema_ok(_v4_dashboard_data()))

    def test_legacy_comparison_without_kind_still_validates(self):
        data = _v4_dashboard_data({
            "comparison": {"basis": "수도권 평균 대비", "delta": 1.2, "direction": "up"}
        })
        self.assertTrue(_schema_ok(data))

    def test_valid_trend_kpi_validates(self):
        data = _v4_dashboard_data({
            "format": {"precision": 0},
            "trend": {
                "points": [98, 104, 111, 123],
                "period_label": "최근 4개월",
                "provenance": _v4_provenance(["2026-02", "2026-03", "2026-04", "2026-05"]),
            },
        })
        self.assertTrue(_schema_ok(data))

    def test_trend_with_string_value_fails(self):
        data = _v4_dashboard_data({
            "value": "5.66~7.49",
            "format": {"precision": 0},
            "trend": {
                "points": [1, 2, 3, 4],
                "provenance": _v4_provenance(["a", "b", "c", "d"]),
            },
        })
        self.assertFalse(_schema_ok(data))

    def test_trend_without_provenance_fails(self):
        data = _v4_dashboard_data({
            "format": {"precision": 0},
            "trend": {"points": [1, 2, 3, 4]},
        })
        self.assertFalse(_schema_ok(data))

    def test_trend_without_precision_fails(self):
        data = _v4_dashboard_data({
            "trend": {
                "points": [1, 2, 3, 4],
                "provenance": _v4_provenance(["a", "b", "c", "d"]),
            },
        })
        self.assertFalse(_schema_ok(data))

    def test_period_delta_without_basis_or_provenance_fails(self):
        for extra in (
            {"comparison": {"kind": "period_delta", "delta": 1.0, "direction": "up",
                            "provenance": _v4_provenance(["2026-04", "2026-05"])}},
            {"comparison": {"kind": "period_delta", "basis": "전월 대비",
                            "delta": 1.0, "direction": "up"}},
        ):
            with self.subTest(extra=extra):
                self.assertFalse(_schema_ok(_v4_dashboard_data(extra)))

    def test_valid_period_delta_validates(self):
        data = _v4_dashboard_data({
            "comparison": {
                "kind": "period_delta", "basis": "전월 대비", "delta": 6.5,
                "direction": "up",
                "provenance": _v4_provenance(["2026-04", "2026-05"]),
            }
        })
        self.assertTrue(_schema_ok(data))

    def test_new_optional_fields_validate(self):
        data = _v4_dashboard_data()
        data["meta"]["dashboard_profile_contract"] = "v4"
        data["panels"][0]["surface"] = "primary"
        data["panels"][0]["charts"][0]["small_multiple_group"] = "g1"
        data["panels"][0]["table"] = {
            "granularity": "aggregated", "row_limit": 10,
            "columns": [{"name": "구", "type": "string"}, {"name": "건수", "type": "number"}],
            "rows": [["강남", 10]],
            "cell_gradient": {"value_column_indices": [1], "scale": "column"},
        }
        self.assertTrue(_schema_ok(data))

    def test_chart_spec_schema_gains_v4_plan_fields(self):
        design = CHART_SPEC_SCHEMA["properties"]["dashboard_design"]["properties"]
        self.assertIn("contract_version", design)
        item = CHART_SPEC_SCHEMA["properties"]["charts"]["items"]
        if "$ref" in item:
            item = CHART_SPEC_SCHEMA["$defs"][item["$ref"].split("/")[-1]]
        mapping = item["properties"]["dashboard_mapping"]["properties"]
        for field in ("surface", "small_multiple_group", "table_treatment"):
            self.assertIn(field, mapping)


class ProfileV4ContractQaTests(QaBaseTestCase):
    def _trend_kpi(self, points, value, precision=0, provenance=None):
        return {
            "value": value,
            "format": {"precision": precision},
            "trend": {
                "points": points,
                "provenance": provenance
                or _v4_provenance([f"2026-{i:02d}" for i in range(1, len(points) + 1)]),
            },
        }

    def test_valid_trend_passes_with_no_blocks(self):
        qa.profile_v4_contract_checks(_v4_dashboard_data(self._trend_kpi([98, 104, 111, 123], 123)))
        self.assertEqual(qa.BLOCK, [])

    def test_provenance_source_id_mismatch_blocks(self):
        prov = {"source_id": "ghost", "time_field": "ym",
                "periods": ["2026-01", "2026-02", "2026-03", "2026-04"]}
        qa.profile_v4_contract_checks(
            _v4_dashboard_data(self._trend_kpi([1, 2, 3, 4], 4, provenance=prov))
        )
        self.assertTrue(any("sources에 없음" in b for b in qa.BLOCK))

    def test_unsorted_and_mismatched_periods_block(self):
        prov = _v4_provenance(["2026-03", "2026-01", "2026-02", "2026-04"])
        qa.profile_v4_contract_checks(
            _v4_dashboard_data(self._trend_kpi([1, 2, 3, 4], 4, provenance=prov))
        )
        self.assertTrue(any("오름차순" in b for b in qa.BLOCK))

        qa.BLOCK.clear()
        prov = _v4_provenance(["2026-01", "2026-02", "2026-03"])
        qa.profile_v4_contract_checks(
            _v4_dashboard_data(self._trend_kpi([1, 2, 3, 4], 4, provenance=prov))
        )
        self.assertTrue(any("길이" in b for b in qa.BLOCK))

    def test_last_point_value_decimal_mismatch_blocks(self):
        qa.profile_v4_contract_checks(_v4_dashboard_data(self._trend_kpi([98, 104, 111, 120], 123)))
        self.assertTrue(any("허용 오차" in b for b in qa.BLOCK))

        qa.BLOCK.clear()
        # precision 1 → ±0.05: 122.98 vs 123.0은 오차 안
        qa.profile_v4_contract_checks(
            _v4_dashboard_data(self._trend_kpi([98, 104, 111, 122.98], 123.0, precision=1))
        )
        self.assertEqual(qa.BLOCK, [])

    def test_delta_sign_direction_mismatch_blocks(self):
        data = _v4_dashboard_data({
            "comparison": {
                "kind": "period_delta", "basis": "전월 대비", "delta": -3.0,
                "direction": "up",
                "provenance": _v4_provenance(["2026-04", "2026-05"]),
            }
        })
        qa.profile_v4_contract_checks(data)
        self.assertTrue(any("불일치" in b for b in qa.BLOCK))

    def test_benchmark_comparison_is_untouched(self):
        data = _v4_dashboard_data({
            "comparison": {"basis": "수도권 평균 대비", "delta": 1.2, "direction": "up"}
        })
        qa.profile_v4_contract_checks(data)
        self.assertEqual(qa.BLOCK, [])

    def test_v4_contract_without_elements_warns(self):
        data = _v4_dashboard_data()
        data["meta"]["dashboard_profile_contract"] = "v4"
        qa.profile_v4_contract_checks(data)
        self.assertTrue(any("이행 없음" in w for w in qa.WARN))

    def test_small_multiple_group_rules_block(self):
        base = _v4_dashboard_data()
        chart = base["panels"][0]["charts"][0]

        with self.subTest(rule="group_size_1"):
            data = _v4_dashboard_data()
            data["panels"][0]["charts"] = [dict(chart, id="c1", small_multiple_group="g")]
            qa.profile_v4_contract_checks(data)
            self.assertTrue(any("2~9만 허용" in b for b in qa.BLOCK))

        qa.BLOCK.clear()
        with self.subTest(rule="cross_panel_span"):
            data = _v4_dashboard_data()
            data["panels"].append(dict(data["panels"][0], id="p2",
                                       charts=[dict(chart, id="c9", small_multiple_group="g"),
                                               dict(chart, id="c10", small_multiple_group="g")]))
            data["panels"][0]["charts"] = [dict(chart, id="c1", small_multiple_group="g"),
                                           dict(chart, id="c2", small_multiple_group="g")]
            qa.profile_v4_contract_checks(data)
            self.assertTrue(any("여러 panel에 걸침" in b for b in qa.BLOCK))

        qa.BLOCK.clear()
        with self.subTest(rule="disallowed_type"):
            data = _v4_dashboard_data()
            data["panels"][0]["charts"] = [
                dict(chart, id="c1", type="heatmap", small_multiple_group="g"),
                dict(chart, id="c2", type="heatmap", small_multiple_group="g"),
            ]
            qa.profile_v4_contract_checks(data)
            self.assertTrue(any("line/area/bar만" in b for b in qa.BLOCK))

        qa.BLOCK.clear()
        with self.subTest(rule="duplicate_chart_id"):
            data = _v4_dashboard_data()
            data["panels"][0]["charts"] = [dict(chart, id="dup"), dict(chart, id="dup")]
            qa.profile_v4_contract_checks(data)
            self.assertTrue(any("chart id 전역 중복" in b for b in qa.BLOCK))

        qa.BLOCK.clear()
        with self.subTest(rule="valid_group_passes"):
            data = _v4_dashboard_data()
            data["panels"][0]["charts"] = [dict(chart, id="c1", small_multiple_group="g"),
                                           dict(chart, id="c2", small_multiple_group="g")]
            qa.profile_v4_contract_checks(data)
            self.assertEqual(qa.BLOCK, [])

    def test_cell_gradient_rules_block(self):
        def table(**grad):
            return {
                "granularity": "aggregated", "row_limit": 5,
                "columns": [{"name": "구", "type": "string"}, {"name": "건수", "type": "number"}],
                "rows": [["강남", 10], ["서초", 20]],
                "cell_gradient": grad or None,
            }

        with self.subTest(rule="index_out_of_range"):
            data = _v4_dashboard_data()
            data["panels"][0]["table"] = table(value_column_indices=[5], scale="column")
            qa.profile_v4_contract_checks(data)
            self.assertTrue(any("columns 범위 밖" in b for b in qa.BLOCK))

        qa.BLOCK.clear()
        with self.subTest(rule="non_number_column"):
            data = _v4_dashboard_data()
            data["panels"][0]["table"] = table(value_column_indices=[0], scale="column")
            qa.profile_v4_contract_checks(data)
            self.assertTrue(any("number가 아님" in b for b in qa.BLOCK))

        qa.BLOCK.clear()
        with self.subTest(rule="valid_gradient_passes"):
            data = _v4_dashboard_data()
            data["panels"][0]["table"] = table(value_column_indices=[1], scale="column")
            qa.profile_v4_contract_checks(data)
            self.assertEqual(qa.BLOCK, [])

    def test_plan_alignment_checks(self):
        def spec(contract=None, group=None, surface=None):
            mapping = {"panel_id": "p1", "chart_id": "c1", "priority": 1}
            if group:
                mapping["small_multiple_group"] = group
            if surface:
                mapping["surface"] = surface
            design = {"selected_profile": "analyst_workspace"}
            if contract:
                design["contract_version"] = contract
            return {"dashboard_design": design,
                    "charts": [{"dashboard_mapping": mapping}]}

        with self.subTest(rule="contract_mismatch"):
            data = _v4_dashboard_data()
            data["meta"]["dashboard_profile_contract"] = "v4"
            qa.profile_v4_plan_alignment_checks(data, spec(contract=None))
            self.assertTrue(any("계약 선언 불일치" in b for b in qa.BLOCK))

        qa.BLOCK.clear()
        with self.subTest(rule="group_mismatch"):
            data = _v4_dashboard_data()
            data["panels"][0]["charts"][0]["small_multiple_group"] = "g"
            qa.profile_v4_plan_alignment_checks(data, spec())
            self.assertTrue(any("스몰 멀티플 계획" in b for b in qa.BLOCK))

        qa.BLOCK.clear()
        with self.subTest(rule="surface_mismatch"):
            data = _v4_dashboard_data()
            qa.profile_v4_plan_alignment_checks(data, spec(surface="detail"))
            self.assertTrue(any("surface 계획" in b for b in qa.BLOCK))

        qa.BLOCK.clear()
        with self.subTest(rule="aligned_passes"):
            data = _v4_dashboard_data()
            data["meta"]["dashboard_profile_contract"] = "v4"
            data["panels"][0]["surface"] = "detail"
            data["panels"][0]["charts"][0]["small_multiple_group"] = "g"
            qa.profile_v4_plan_alignment_checks(
                data, spec(contract="v4", group="g", surface="detail")
            )
            self.assertEqual(qa.BLOCK, [])

    def test_language_gate_collects_basis_and_period_label(self):
        data = _v4_dashboard_data({
            "format": {"precision": 0},
            "comparison": {"kind": "period_delta", "basis": "전월 대비", "delta": 1.0,
                           "direction": "up", "provenance": _v4_provenance(["a", "b"])},
            "trend": {"points": [1, 2, 3, 4], "period_label": "최근 4개월",
                      "provenance": _v4_provenance(["a", "b", "c", "d"])},
        })
        keys = {key for key, _ in qa._dashboard_visible_texts(data)}
        self.assertIn("kpis[0].comparison.basis", keys)
        self.assertIn("kpis[0].trend.period_label", keys)

    def test_analyst_v4_first_screen_density_warns_at_nine(self):
        data = _v4_dashboard_data()
        data["meta"]["dashboard_profile_contract"] = "v4"
        data["meta"]["dashboard_profile"] = "analyst_workspace"
        base_chart = data["panels"][0]["charts"][0]
        # KPI 블록(1) + primary 차트 8 = 첫 화면 패널 수 9 → WARN
        data["panels"][0]["charts"] = [dict(base_chart, id=f"c{i}") for i in range(8)]
        data["panels"][0]["surface"] = "primary"
        qa.profile_v4_contract_checks(data)
        self.assertTrue(any("첫 화면 패널 수 9" in w for w in qa.WARN))
        self.assertEqual(qa.BLOCK, [])


if __name__ == "__main__":
    unittest.main()
