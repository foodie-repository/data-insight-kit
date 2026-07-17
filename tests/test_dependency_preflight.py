from __future__ import annotations

import importlib.util
import json
import shutil
import tempfile
import unittest
from pathlib import Path

KIT_ROOT = Path(__file__).resolve().parents[1]


def load_module(name: str, relative_path: str):
    path = KIT_ROOT / relative_path
    spec = importlib.util.spec_from_file_location(name, path)
    if spec is None or spec.loader is None:
        raise RuntimeError(f"cannot load module: {path}")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


preflight = load_module("dependency_preflight", "scripts/dependency_preflight.py")

SPEC_V1_METHODS = {
    # core (spec §6)
    "ranking": [],
    "distribution": [],
    "composition": [],
    "trend": [],
    "quality": [],
    # stats
    "group_difference_candidate": ["stats"],
    "correlation_candidate": ["stats"],
    "simple_regression_candidate": ["stats"],
    "confidence_interval_candidate": ["stats"],
    # ml
    "clustering_candidate": ["ml"],
    "anomaly_candidate": ["ml"],
    "dimensionality_reduction_candidate": ["ml"],
}
VALID_ROUTES = {
    "descriptive",
    "diagnostic",
    "statistical",
    "ml_exploratory",
    "predictive",
    "causal_experiment",
}


class MethodRegistryContractTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.registry = json.loads(
            (KIT_ROOT / "methods" / "method_registry.json").read_text(encoding="utf-8")
        )

    def test_registry_covers_spec_v1_methods_with_expected_groups(self):
        methods = {m["id"]: m for m in self.registry["methods"]}
        self.assertEqual(set(methods), set(SPEC_V1_METHODS))
        for method_id, expected_groups in SPEC_V1_METHODS.items():
            self.assertEqual(
                methods[method_id].get("dependency_groups"), expected_groups, method_id
            )

    def test_method_ids_unique_and_routes_valid(self):
        ids = [m["id"] for m in self.registry["methods"]]
        self.assertEqual(len(ids), len(set(ids)))
        for method in self.registry["methods"]:
            self.assertIn(method["route"], VALID_ROUTES, method["id"])
            for group in method.get("dependency_groups") or []:
                self.assertIn(group, self.registry["dependency_allowlist"], method["id"])

    def test_every_method_has_guard_fields(self):
        for method in self.registry["methods"]:
            with self.subTest(method_id=method["id"]):
                self.assertTrue(method.get("label"))
                self.assertTrue(method.get("allowed_questions"))
                self.assertTrue(method.get("blocked_claims"))
                self.assertTrue(method.get("recommended_charts"))
                self.assertIn("data_conditions", method.get("requires", {}))
                self.assertIn("domain_conditions", method.get("requires", {}))

    def test_downgrade_only_routes_have_no_dedicated_methods(self):
        downgrade_only = set(self.registry["route_policy"]["v1_downgrade_only_routes"])
        self.assertEqual(downgrade_only, {"predictive", "causal_experiment"})
        for method in self.registry["methods"]:
            self.assertNotIn(method["route"], downgrade_only, method["id"])


class DependencyPreflightTests(unittest.TestCase):
    def make_kit(self, tmp: Path) -> Path:
        """실제 registry/schema를 복사한 임시 kit root (venv 없음)."""
        kit = tmp / "kit"
        (kit / "methods").mkdir(parents=True)
        (kit / "schemas").mkdir(parents=True)
        shutil.copy(KIT_ROOT / "methods" / "method_registry.json", kit / "methods")
        shutil.copy(KIT_ROOT / "schemas" / "dependency_plan.schema.json", kit / "schemas")
        return kit

    def make_run(self, kit: Path, run_id: str, selected_methods: list[str]) -> Path:
        run = kit / "runs" / run_id
        (run / "input").mkdir(parents=True)
        (run / "outputs").mkdir(parents=True)
        (run / "outputs" / "method_route.json").write_text(
            json.dumps(
                {
                    "schema_version": "data-insight-kit.method_route.v1",
                    "run_id": run_id,
                    "created_at": "2026-07-10T00:00:00Z",
                    "route": "statistical",
                    "selected_methods": selected_methods,
                }
            ),
            encoding="utf-8",
        )
        return run

    def fake_install(self, kit: Path, packages: list[str]) -> None:
        sp = kit / ".venv" / "lib" / "python3.11" / "site-packages"
        sp.mkdir(parents=True, exist_ok=True)
        for name in packages:
            (sp / f"{name.replace('-', '_')}-1.0.0.dist-info").mkdir()

    def test_core_only_route_requires_no_extras(self):
        with tempfile.TemporaryDirectory() as tmp:
            kit = self.make_kit(Path(tmp))
            run = self.make_run(kit, "r-core", ["ranking", "trend"])
            registry = preflight.load_registry(kit)
            plan, issues = preflight.build_plan("r-core", run, kit, registry)
            self.assertEqual(issues, [])
            self.assertEqual(plan["required_extras"], [])
            self.assertEqual(plan["missing"], [])
            self.assertIsNone(preflight.install_command(kit, plan["missing"]))

    def test_stats_route_missing_without_kit_venv(self):
        with tempfile.TemporaryDirectory() as tmp:
            kit = self.make_kit(Path(tmp))
            run = self.make_run(kit, "r-stats", ["group_difference_candidate", "ranking"])
            registry = preflight.load_registry(kit)
            plan, issues = preflight.build_plan("r-stats", run, kit, registry)
            self.assertEqual(issues, [])
            self.assertEqual(plan["required_extras"], ["stats"])
            self.assertEqual(plan["installed"], [])
            self.assertEqual(plan["missing"], ["stats"])
            self.assertEqual(plan["environment"]["basis"], "kit_local_venv")
            cmd = preflight.install_command(kit, plan["missing"])
            self.assertIn("uv sync", cmd)
            self.assertIn("--extra stats", cmd)

    def test_installed_detection_uses_kit_venv_dist_info(self):
        with tempfile.TemporaryDirectory() as tmp:
            kit = self.make_kit(Path(tmp))
            run = self.make_run(
                kit, "r-mix", ["group_difference_candidate", "clustering_candidate"]
            )
            self.fake_install(kit, ["scipy", "statsmodels", "matplotlib", "seaborn"])
            registry = preflight.load_registry(kit)
            plan, _ = preflight.build_plan("r-mix", run, kit, registry)
            self.assertEqual(plan["required_extras"], ["ml", "stats"])
            self.assertEqual(plan["installed"], ["stats"])
            self.assertEqual(plan["missing"], ["ml"])
            scikit = [p for p in plan["packages"] if p["name"] == "scikit-learn"]
            self.assertEqual(len(scikit), 1)
            self.assertFalse(scikit[0]["installed"])

    def test_plan_validates_against_schema(self):
        import jsonschema

        schema = json.loads(
            (KIT_ROOT / "schemas" / "dependency_plan.schema.json").read_text(encoding="utf-8")
        )
        with tempfile.TemporaryDirectory() as tmp:
            kit = self.make_kit(Path(tmp))
            run = self.make_run(kit, "r-schema", ["correlation_candidate"])
            registry = preflight.load_registry(kit)
            plan, _ = preflight.build_plan("r-schema", run, kit, registry)
            jsonschema.validate(plan, schema)

    def test_rerun_preserves_approval_only_when_extras_unchanged(self):
        with tempfile.TemporaryDirectory() as tmp:
            kit = self.make_kit(Path(tmp))
            run = self.make_run(kit, "r-approve", ["group_difference_candidate"])
            registry = preflight.load_registry(kit)
            plan, _ = preflight.build_plan("r-approve", run, kit, registry)
            plan["approval"] = {
                "answer_id": "a-1",
                "checkpoint_id": "analysis_strategy",
                "dependency_decision": "install",
                "approved_at": "2026-07-10T00:10:00Z",
            }
            (run / "input" / "dependency_plan.json").write_text(
                json.dumps(plan), encoding="utf-8"
            )

            same, _ = preflight.build_plan("r-approve", run, kit, registry)
            self.assertEqual(same["approval"], plan["approval"])

            # route가 ml로 확장되면 이전 승인은 무효 (승인 시점 잠금과 일관)
            (run / "outputs" / "method_route.json").write_text(
                json.dumps(
                    {
                        "schema_version": "data-insight-kit.method_route.v1",
                        "run_id": "r-approve",
                        "created_at": "2026-07-10T00:20:00Z",
                        "route": "ml_exploratory",
                        "selected_methods": ["clustering_candidate"],
                    }
                ),
                encoding="utf-8",
            )
            changed, _ = preflight.build_plan("r-approve", run, kit, registry)
            self.assertIsNone(changed["approval"])

    def test_unknown_method_is_reported_as_issue(self):
        with tempfile.TemporaryDirectory() as tmp:
            kit = self.make_kit(Path(tmp))
            run = self.make_run(kit, "r-bad", ["made_up_method"])
            registry = preflight.load_registry(kit)
            plan, issues = preflight.build_plan("r-bad", run, kit, registry)
            self.assertEqual(plan["required_extras"], [])
            self.assertTrue(any("made_up_method" in issue for issue in issues))

    def test_default_preflight_never_invokes_installers(self):
        # 기본(플래그 없는) preflight 경로는 설치하지 않는다. 실제 설치(uv sync)는
        # --apply-approval 승인 경로에서만 허용되며, 그마저 raw shell/blocking
        # helper가 아니라 단일 subprocess.run(uv sync ...)로만 수행한다.
        source = (KIT_ROOT / "scripts" / "dependency_preflight.py").read_text(encoding="utf-8")
        for forbidden in ("os.system", "popen", "check_call", "check_output"):
            self.assertNotIn(forbidden, source)
        # subprocess 사용은 apply_approval(승인 경로) 안에서만, 정확히 한 번.
        self.assertEqual(source.count("subprocess.run("), 1)
        apply_body = source.split("def apply_approval", 1)[1].split("\ndef ", 1)[0]
        self.assertIn("subprocess.run(", apply_body)
        # main에서 apply_approval 호출은 --apply-approval 플래그로 게이트된다.
        self.assertIn("if args.apply_approval:", source)


if __name__ == "__main__":
    unittest.main()
