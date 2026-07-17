from __future__ import annotations

import hashlib
import importlib.util
import json
import os
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

from tests.v5_fixtures import minimal_chart_spec_v5, minimal_layout_v5

KIT_ROOT = Path(__file__).resolve().parents[1]


def load_module(name: str, relative_path: str):
    path = KIT_ROOT / relative_path
    spec = importlib.util.spec_from_file_location(name, path)
    if spec is None or spec.loader is None:
        raise RuntimeError(f"cannot load module: {path}")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


checkpoint_gate = load_module("checkpoint_gate_routing", "scripts/checkpoint_gate.py")
ufv = load_module("ufv_routing", "scripts/validate_user_facing_text.py")

QUESTION_SCHEMA = json.loads(
    (KIT_ROOT / "schemas" / "checkpoint_question.schema.json").read_text(encoding="utf-8")
)

DEFAULT_STRATEGY_OPTION_IDS = [
    "approve_strategy",
    "revise_questions_kpis",
    "choose_analysis_direction",
    "simplify_strategy",
]


def sha256_file(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


class GateRoutingTestCase(unittest.TestCase):
    def make_run(self, root: Path, run_id: str) -> Path:
        run = root / "runs" / run_id
        (run / "input").mkdir(parents=True)
        (run / "outputs").mkdir(parents=True)
        (run / "outputs" / "03_frame.md").write_text("# Frame\n핵심 질문과 지표 정의\n", encoding="utf-8")
        (run / "outputs" / "04_analysis.md").write_text("# Analysis\n1차 발견 요약\n", encoding="utf-8")
        (run / "outputs" / "chart_spec.json").write_text(
            json.dumps({"charts": []}, ensure_ascii=False), encoding="utf-8"
        )
        return run

    def write_method_route(self, run: Path, route: str = "statistical") -> Path:
        path = run / "outputs" / "method_route.json"
        path.write_text(
            json.dumps(
                {
                    "schema_version": "data-insight-kit.method_route.v1",
                    "run_id": run.name,
                    "created_at": "2026-07-10T01:00:00Z",
                    "route": route,
                    "selected_methods": ["group_difference_candidate"],
                    "dependency_groups": ["stats"],
                }
            ),
            encoding="utf-8",
        )
        return path

    def write_dependency_plan(self, run: Path, missing: list[str], installed: list[str]) -> Path:
        path = run / "input" / "dependency_plan.json"
        path.write_text(
            json.dumps(
                {
                    "schema_version": "data-insight-kit.dependency_plan.v1",
                    "run_id": run.name,
                    "created_at": "2026-07-10T01:05:00Z",
                    "environment": {
                        "kit_root": str(KIT_ROOT),
                        "venv_path": str(KIT_ROOT / ".venv"),
                        "basis": "kit_local_venv",
                    },
                    "required_extras": sorted(set(missing) | set(installed)),
                    "installed": installed,
                    "missing": missing,
                    "approval": None,
                    "install_result": None,
                }
            ),
            encoding="utf-8",
        )
        return path

    def create_question(self, root: Path, run_id: str, checkpoint_id: str):
        previous = Path.cwd()
        os.chdir(root)
        try:
            return checkpoint_gate.create_question(run_id, checkpoint_id)
        finally:
            os.chdir(previous)

    def assert_schema_valid(self, question: dict) -> None:
        import jsonschema

        jsonschema.validate(question, QUESTION_SCHEMA)

    def assert_user_facing_clean(self, *paths: Path) -> None:
        for path in paths:
            issues = ufv.validate_path(path)
            self.assertEqual(issues, [], f"user-facing text issues in {path}")


class DashboardLayoutHandoffTests(GateRoutingTestCase):
    def test_layout_summary_names_aligned_stacked_series_panels(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "dashboard_layout.json"
            layout = minimal_layout_v5()
            layout["components"][2]["render_options"]["series_layout"] = "stacked_panels"
            path.write_text(json.dumps(layout), encoding="utf-8")

            summary = checkpoint_gate.dashboard_layout_summary(path)

            self.assertIn("표현 방식", summary)
            self.assertIn("같은 시간축의 위아래 패널", summary)

    def test_storyboard_question_rejects_invalid_stateful_layout(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            run = self.make_run(root, "unit-run")
            layout = minimal_layout_v5()
            chart = next(item for item in layout["components"] if item["kind"] == "chart")
            chart["interactions"] = ["tooltip", "data_zoom"]
            (run / "outputs" / "dashboard_layout.json").write_text(
                json.dumps(layout), encoding="utf-8"
            )

            with self.assertRaisesRegex(SystemExit, "visible state/reset"):
                self.create_question(root, "unit-run", "dashboard_storyboard")

    def test_storyboard_chat_handoff_lists_layout_original_path_and_revision(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            run = self.make_run(root, "unit-run")
            (run / "outputs" / "chart_spec.json").write_text(
                json.dumps(minimal_chart_spec_v5()), encoding="utf-8"
            )
            (run / "outputs" / "dashboard_layout.json").write_text(
                json.dumps(minimal_layout_v5()), encoding="utf-8"
            )
            previous = Path.cwd()
            os.chdir(root)
            try:
                question, question_json, question_md = checkpoint_gate.create_question(
                    "unit-run", "dashboard_storyboard"
                )
                handoff = checkpoint_gate.render_question_for_chat(
                    question, question_json, question_md
                )
            finally:
                os.chdir(previous)
            self.assertIn("dashboard_layout.json", handoff)
            self.assertIn("revision 1", handoff)
            self.assertIn("hero-chart", handoff)


class AnalysisResultReviewTests(GateRoutingTestCase):
    def test_config_uses_fixed_05_prefix_and_existing_ids_unchanged(self):
        config = checkpoint_gate.CHECKPOINTS["analysis_result_review"]
        self.assertEqual(config["order"], "05")
        self.assertEqual(config["kind"], "result_review")
        for checkpoint_id, order in (
            ("data_profile", "01"),
            ("analysis_strategy", "02"),
            ("dashboard_storyboard", "03"),
            ("report_outline", "04"),
        ):
            self.assertEqual(checkpoint_gate.CHECKPOINTS[checkpoint_id]["order"], order)

    def test_question_created_at_05_prefix_and_schema_valid(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            run = self.make_run(root, "review-run")
            self.write_method_route(run)
            question, question_json, question_md = self.create_question(
                root, "review-run", "analysis_result_review"
            )
            self.assertTrue(question_json.name.startswith("05_analysis_result_review_question"))
            self.assertTrue((root / question_json).exists() or question_json.exists())
            self.assert_schema_valid(question)
            self.assertIn("분석 깊이 요약", question["current_understanding"])
            self.assert_user_facing_clean(root / question_json, root / question_md)


class AnalysisStrategyLockAndDependencyTests(GateRoutingTestCase):
    def test_embeds_approval_targets_and_dependency_options_when_missing(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            run = self.make_run(root, "deep-run")
            route_path = self.write_method_route(run)
            plan_path = self.write_dependency_plan(run, missing=["stats"], installed=[])
            question, question_json, question_md = self.create_question(
                root, "deep-run", "analysis_strategy"
            )
            self.assert_schema_valid(question)

            targets = question.get("approval_targets") or {}
            self.assertEqual(set(targets), {"method_route", "dependency_plan"})
            self.assertEqual(targets["method_route"]["sha256"], sha256_file(route_path))
            self.assertEqual(targets["dependency_plan"]["sha256"], sha256_file(plan_path))

            option_ids = [option["id"] for option in question["options"]]
            self.assertIn("install_and_deepen", option_ids)
            self.assertIn("proceed_without_install", option_ids)
            self.assertLessEqual(len(option_ids), 4)
            self.assertEqual(question["recommended_option_id"], "install_and_deepen")

            by_id = {option["id"]: option for option in question["options"]}
            self.assertEqual(by_id["install_and_deepen"]["maps_to"]["dependency_decision"], "install")
            self.assertTrue(by_id["install_and_deepen"]["continue_pipeline"])
            self.assertEqual(
                by_id["proceed_without_install"]["maps_to"]["dependency_decision"], "skip_install"
            )
            self.assertEqual(by_id["revise_questions_kpis"]["maps_to"]["dependency_decision"], "adjust")
            self.assert_user_facing_clean(root / question_json, root / question_md)

    def test_default_options_without_dependency_plan(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            self.make_run(root, "plain-run")
            question, _, _ = self.create_question(root, "plain-run", "analysis_strategy")
            self.assert_schema_valid(question)
            self.assertNotIn("approval_targets", question)
            self.assertEqual(
                [option["id"] for option in question["options"]], DEFAULT_STRATEGY_OPTION_IDS
            )
            self.assertEqual(question["recommended_option_id"], "approve_strategy")

    def test_default_options_when_extras_already_installed(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            run = self.make_run(root, "ready-run")
            self.write_method_route(run)
            self.write_dependency_plan(run, missing=[], installed=["stats"])
            question, _, _ = self.create_question(root, "ready-run", "analysis_strategy")
            self.assert_schema_valid(question)
            # 설치 결정이 필요 없으므로 기존 옵션을 유지하되, 승인 잠금은 남긴다.
            self.assertEqual(
                [option["id"] for option in question["options"]], DEFAULT_STRATEGY_OPTION_IDS
            )
            self.assertIn("dependency_plan", question.get("approval_targets") or {})
            self.assertIn("이미 준비된 기능", question["current_understanding"])


class DataPreviewSourceTests(unittest.TestCase):
    """data_profile 샘플 미리보기가 kit 메타데이터가 아닌 실제 데이터를 뽑는지 (버그 회귀)."""

    def _make_input(self, root: Path, names: list[str]) -> Path:
        run = root / "runs" / "preview-run"
        (run / "input").mkdir(parents=True)
        for name in names:
            path = run / "input" / name
            if name.endswith(".csv"):
                path.write_text("col_a,col_b\n1,2\n3,4\n", encoding="utf-8")
            else:
                path.write_text('{"mode": "meta"}\n', encoding="utf-8")
        return run

    def test_source_files_excludes_kit_internal_metadata(self):
        with tempfile.TemporaryDirectory() as tmp:
            run = self._make_input(
                Path(tmp),
                ["checkpoint_policy.json", "run_context.json", "dependency_plan.json", "real_data.csv"],
            )
            names = [p.name for p in checkpoint_gate.source_files(run)]
            self.assertEqual(names, ["real_data.csv"])

    def test_source_files_prefers_tabular_over_user_json(self):
        # 사용자 데이터 JSON은 허용하되, 알파벳이 빨라도 표 형식이 먼저 와야 한다.
        with tempfile.TemporaryDirectory() as tmp:
            run = self._make_input(Path(tmp), ["aaa_user_data.json", "zzz_data.csv"])
            names = [p.name for p in checkpoint_gate.source_files(run)]
            self.assertEqual(names, ["zzz_data.csv", "aaa_user_data.json"])

    def test_build_data_preview_samples_real_data_not_policy(self):
        with tempfile.TemporaryDirectory() as tmp:
            run = self._make_input(
                Path(tmp), ["checkpoint_policy.json", "police_data.csv", "run_context.json"]
            )
            checkpoint_dir = run / "outputs" / "checkpoints"
            checkpoint_dir.mkdir(parents=True)
            notes: list[str] = []
            cwd = os.getcwd()
            os.chdir(tmp)
            try:
                preview = checkpoint_gate.build_data_preview(run, checkpoint_dir, notes)
            finally:
                os.chdir(cwd)
            self.assertIsNotNone(preview)
            assert preview is not None
            self.assertTrue(preview.endswith("data_preview.csv"))
            self.assertIn("police_data.csv", notes[0])
            self.assertNotIn("checkpoint_policy", " ".join(notes))
            content = (checkpoint_dir / "data_preview.csv").read_text(encoding="utf-8")
            self.assertIn("col_a", content)

    def test_build_data_preview_prefers_connect_stage_limited_preview(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            run = root / "runs" / "preview-run"
            (run / "input").mkdir(parents=True)
            (run / "outputs").mkdir(parents=True)
            (run / "input" / "stores.csv").write_text(
                "bizesNm,rdnmAdr,adongNm,indsLclsNm\n민감상호,상세주소,역삼1동,음식\n",
                encoding="utf-8",
            )
            (run / "outputs" / "data_preview.csv").write_text(
                "admin_dong_name,industry_large_name\n역삼1동,음식\n",
                encoding="utf-8",
            )
            checkpoint_dir = run / "outputs" / "checkpoints"
            notes: list[str] = []
            cwd = os.getcwd()
            os.chdir(tmp)
            try:
                preview = checkpoint_gate.build_data_preview(run, checkpoint_dir, notes)
            finally:
                os.chdir(cwd)
            self.assertIsNotNone(preview)
            content = (checkpoint_dir / "data_preview.csv").read_text(encoding="utf-8")
            self.assertIn("admin_dong_name", content)
            self.assertNotIn("민감상호", content)
            self.assertNotIn("상세주소", content)
            self.assertIn("connect 단계", notes[0])

    def test_write_csv_preview_removes_identifying_columns_from_raw_source(self):
        with tempfile.TemporaryDirectory() as tmp:
            source = Path(tmp) / "stores.csv"
            source.write_text(
                "bizesId,bizesNm,rdnmAdr,lon,lat,adongNm,indsLclsNm\n"
                "S1,민감상호,서울시 상세주소,127.1,37.5,역삼1동,음식\n",
                encoding="utf-8",
            )
            target = Path(tmp) / "data_preview.csv"
            self.assertTrue(checkpoint_gate.write_csv_preview(source, target))
            content = target.read_text(encoding="utf-8")
            self.assertEqual(
                content,
                "adongNm,indsLclsNm\n역삼1동,음식\n",
            )

    def test_write_csv_preview_reencodes_cp949_to_utf8(self):
        # cp949 원본이 errors="replace"로 U+FFFD가 된 채 실리던 회귀 (v2.1)
        with tempfile.TemporaryDirectory() as tmp:
            source = Path(tmp) / "cp949_data.csv"
            source.write_bytes("업종명,행정동\n한식음식점,역삼동\n".encode("cp949"))
            target = Path(tmp) / "data_preview.csv"
            self.assertTrue(checkpoint_gate.write_csv_preview(source, target))
            content = target.read_text(encoding="utf-8")
            self.assertIn("한식음식점", content)
            self.assertNotIn("�", content)

    def test_write_csv_preview_keeps_utf8_source_intact(self):
        with tempfile.TemporaryDirectory() as tmp:
            source = Path(tmp) / "utf8_data.csv"
            source.write_text("업종명,행정동\n카페,논현동\n", encoding="utf-8")
            target = Path(tmp) / "data_preview.csv"
            self.assertTrue(checkpoint_gate.write_csv_preview(source, target))
            self.assertIn("카페", target.read_text(encoding="utf-8"))


EXPLORATION_SCHEMA = json.loads(
    (KIT_ROOT / "schemas" / "exploration_candidates.schema.json").read_text(encoding="utf-8")
)


def make_min_question(schema_version: str = "data-insight-kit.checkpoint_question.v1") -> dict:
    """checkpoint_question 스키마의 required만 채운 최소 유효 payload."""
    return {
        "schema_version": schema_version,
        "run_id": "r1",
        "created_at": "2026-07-11T00:00:00+00:00",
        "status": "blocked_for_user_checkpoint",
        "checkpoint_id": "data_profile",
        "checkpoint_kind": "data_review",
        "header": "데이터 탐색 확인",
        "interview_style": "deep_interview_checkpoint",
        "user_review_brief": {
            "plain_title": "데이터 확인",
            "why_this_checkpoint_matters": "범위와 품질 확인",
            "what_user_should_review": ["표본과 기간"],
            "what_will_happen_next": ["분석 방향 확인 단계"],
            "what_this_does_not_decide": ["차트 구성"],
            "approval_question": "진행할까요?",
        },
        "current_understanding": "탐색 요약",
        "blocked_decision": "진행 여부",
        "recommended_answer": "진행",
        "recommended_option_id": "go",
        "question": "진행할까요?",
        "chat_prompt": "현재 이해 / 막힌 결정 / 추천 답안 / 질문",
        "options": [
            {"id": "go", "label": "진행", "description": "그대로 진행", "continue_pipeline": True},
            {"id": "stop", "label": "수정", "description": "수정 후 재확인", "continue_pipeline": False},
        ],
        "allow_free_text": True,
        "response_instructions": {
            "write_to": "checkpoint_answers.json",
            "apply_command": "python3 scripts/apply_checkpoint_answer.py r1 data_profile ...",
            "resume_command": "bash scripts/run_codex_pipeline.sh r1",
        },
    }


LOOP_R1 = {
    "round": 1,
    "max_rounds": 2,
    "free_question_used_this_round": False,
    "max_free_questions_per_round": 1,
    "finalization_rule": "조기 종료 선택 또는 라운드 상한 도달 시 누적 답변으로 확정",
}

PRIOR_ROUND = {
    "question_path": "runs/r1/outputs/checkpoints/01_data_profile_question.json",
    "question_sha256": "a" * 64,
    "answer_id": "chkans_prior",
    "trigger": "explore_direction",
}


def make_candidates(n: int = 2) -> dict:
    return {
        "schema_version": "data-insight-kit.exploration_candidates.v1",
        "run_id": "r1",
        "created_at": "2026-07-11T00:00:00+00:00",
        "candidates": [
            {
                "id": f"dir_{i}",
                "label": f"방향 {i}",
                "why_interesting": "상위 구간 집중이 두드러짐",
                "mini_result": {
                    "summary": "상위 3개 구가 전체의 41%",
                    "table_path": f"outputs/exploration/candidate_dir_{i}.md",
                    "computation": "지역 컬럼 groupby 건수 집계, 결측 제외",
                    "source_columns": ["sido", "sigungu"],
                    "row_count_used": 64231,
                },
                "maps_to": {"frame_focus": f"dir_{i}"},
            }
            for i in range(n)
        ],
    }


class InterviewLoopSchemaTests(unittest.TestCase):
    """interview-loop-v2 spec §4.2 조건부 스키마 계약 (커밋 3)."""

    def validate(self, payload: dict, schema: dict) -> None:
        import jsonschema

        jsonschema.validate(payload, schema)

    def assert_invalid(self, payload: dict, schema: dict) -> None:
        import jsonschema

        with self.assertRaises(jsonschema.ValidationError):
            jsonschema.validate(payload, schema)

    def test_legacy_v1_question_still_validates(self):
        self.validate(make_min_question(), QUESTION_SCHEMA)

    def test_v2_requires_interview_loop(self):
        q = make_min_question("data-insight-kit.checkpoint_question.v2")
        with self.subTest(case="v2 without interview_loop is invalid"):
            self.assert_invalid(q, QUESTION_SCHEMA)
        with self.subTest(case="v2 with round-1 loop is valid"):
            q["interview_loop"] = dict(LOOP_R1)
            self.validate(q, QUESTION_SCHEMA)

    def test_v2_round2_requires_prior_round(self):
        q = make_min_question("data-insight-kit.checkpoint_question.v2")
        q["interview_loop"] = {**LOOP_R1, "round": 2}
        with self.subTest(case="round 2 without prior_round is invalid"):
            self.assert_invalid(q, QUESTION_SCHEMA)
        with self.subTest(case="round 2 with prior_round is valid"):
            q["interview_loop"]["prior_round"] = dict(PRIOR_ROUND)
            self.validate(q, QUESTION_SCHEMA)
        with self.subTest(case="prior_round trigger outside enum is invalid"):
            q["interview_loop"]["prior_round"] = {**PRIOR_ROUND, "trigger": "agent_whim"}
            self.assert_invalid(q, QUESTION_SCHEMA)

    def test_loop_action_option_cannot_continue_pipeline(self):
        # 불변식 I1의 스키마 층: maps_to.loop_action 옵션은 continue_pipeline=false.
        q = make_min_question("data-insight-kit.checkpoint_question.v2")
        q["interview_loop"] = dict(LOOP_R1)
        direction = {
            "id": "dir_a",
            "label": "지역별로 좁히기",
            "description": "상위 3개 구가 전체의 41%",
            "continue_pipeline": False,
            "maps_to": {"loop_action": "explore_direction", "frame_focus": "dir_a"},
        }
        with self.subTest(case="loop_action with continue_pipeline=false is valid"):
            q["options"] = [q["options"][0], direction]
            self.validate(q, QUESTION_SCHEMA)
        with self.subTest(case="loop_action with continue_pipeline=true is invalid"):
            q["options"] = [q["options"][0], {**direction, "continue_pipeline": True}]
            self.assert_invalid(q, QUESTION_SCHEMA)

    def test_companion_questions_capped_and_gate_free(self):
        q = make_min_question("data-insight-kit.checkpoint_question.v2")
        q["interview_loop"] = dict(LOOP_R1)
        companion = {
            "id": "row_meaning",
            "question": "행 1개는 어떤 업무 단위인가요?",
            "header": "행의 의미",
            "allow_free_text": True,
            "maps_to": {"domain_field": "row_meaning"},
        }
        with self.subTest(case="two companions are valid"):
            q["companion_questions"] = [companion, {**companion, "id": "grain"}]
            self.validate(q, QUESTION_SCHEMA)
        with self.subTest(case="three companions exceed the budget"):
            q["companion_questions"] = [
                companion,
                {**companion, "id": "grain"},
                {**companion, "id": "exclusions"},
            ]
            self.assert_invalid(q, QUESTION_SCHEMA)
        with self.subTest(case="companion option cannot even carry continue_pipeline"):
            q["companion_questions"] = [
                {
                    **companion,
                    "options": [
                        {"id": "o1", "label": "주문 1건", "description": "주문 단위", "continue_pipeline": True},
                        {"id": "o2", "label": "고객 1명", "description": "고객 단위"},
                    ],
                }
            ]
            self.assert_invalid(q, QUESTION_SCHEMA)

    def test_exploration_block_shape(self):
        q = make_min_question("data-insight-kit.checkpoint_question.v2")
        q["interview_loop"] = dict(LOOP_R1)
        with self.subTest(case="exploration with both fields is valid"):
            q["exploration"] = {
                "candidates_ref": "outputs/exploration_candidates.json",
                "free_question_slot": True,
            }
            self.validate(q, QUESTION_SCHEMA)
        with self.subTest(case="exploration missing candidates_ref is invalid"):
            q["exploration"] = {"free_question_slot": True}
            self.assert_invalid(q, QUESTION_SCHEMA)

    def test_exploration_candidates_schema(self):
        with self.subTest(case="two candidates with full mini_result are valid"):
            self.validate(make_candidates(2), EXPLORATION_SCHEMA)
        with self.subTest(case="four candidates exceed the cap"):
            self.assert_invalid(make_candidates(4), EXPLORATION_SCHEMA)
        with self.subTest(case="single candidate is below the minimum"):
            self.assert_invalid(make_candidates(1), EXPLORATION_SCHEMA)
        with self.subTest(case="missing mini_result.summary is invalid"):
            payload = make_candidates(2)
            del payload["candidates"][0]["mini_result"]["summary"]
            self.assert_invalid(payload, EXPLORATION_SCHEMA)
        with self.subTest(case="missing maps_to.frame_focus is invalid"):
            payload = make_candidates(2)
            payload["candidates"][0]["maps_to"] = {}
            self.assert_invalid(payload, EXPLORATION_SCHEMA)


class InterviewLoopHarness(unittest.TestCase):
    """인터뷰 루프 테스트 공용 스캐폴딩 (subprocess로 실제 스크립트 구동)."""

    GATE = KIT_ROOT / "scripts" / "checkpoint_gate.py"
    APPLY = KIT_ROOT / "scripts" / "apply_checkpoint_answer.py"
    STAGE_GUARD = KIT_ROOT / "scripts" / "stage_guard.py"
    UFV = KIT_ROOT / "scripts" / "validate_user_facing_text.py"

    def scaffold(self, root: Path, run_id: str = "loop-run") -> Path:
        run = root / "runs" / run_id
        (run / "input").mkdir(parents=True)
        (run / "outputs").mkdir(parents=True)
        return run

    def run_gate(self, root: Path, run_id: str, checkpoint: str) -> subprocess.CompletedProcess:
        return subprocess.run(
            [sys.executable, str(self.GATE), run_id, checkpoint, "--quiet"],
            cwd=root,
            text=True,
            capture_output=True,
        )

    def run_apply(self, root: Path, run_id: str, checkpoint: str, *extra: str) -> subprocess.CompletedProcess:
        return subprocess.run(
            [sys.executable, str(self.APPLY), run_id, checkpoint, *extra],
            cwd=root,
            text=True,
            capture_output=True,
        )

    def read_answers(self, run: Path) -> list[dict]:
        data = json.loads((run / "checkpoint_answers.json").read_text(encoding="utf-8"))
        return data["answers"]

    def run_stage_guard(self, root: Path, run_id: str, stage: str) -> subprocess.CompletedProcess:
        return subprocess.run(
            [sys.executable, str(self.STAGE_GUARD), run_id, stage],
            cwd=root,
            text=True,
            capture_output=True,
        )

    def approve_round2_flow(self, root: Path) -> Path:
        """R1 생성 → 자유 질문 → R2 생성 → R2 승인까지 진행하고 run 경로 반환."""
        run = self.scaffold(root)
        self.assertEqual(self.run_gate(root, "loop-run", "data_profile").returncode, 3)
        applied = self.run_apply(
            root, "loop-run", "data_profile",
            "--free-question", "구별로 나눠서 보여줘",
            "--source", "user_chat",
            "--user-response", "구별로 나눠서 보여줘",
            "--transcript-ref", "thread:guard-1",
        )
        self.assertEqual(applied.returncode, 0, applied.stderr)
        self.assertEqual(self.run_gate(root, "loop-run", "data_profile").returncode, 3)
        confirm = self.run_apply(
            root, "loop-run", "data_profile",
            "--option", "confirm_and_continue",
            "--source", "user_chat",
            "--user-response", "확인했어요, 진행해주세요",
            "--transcript-ref", "thread:guard-2",
        )
        self.assertEqual(confirm.returncode, 0, confirm.stderr)
        return run


class InterviewLoopRuntimeTests(InterviewLoopHarness):
    """interview-loop-v2 §4 런타임 (커밋 4): 라운드 생성·결정 레코드·I1·fail-closed."""

    def test_round1_v2_then_free_question_creates_round2(self):
        import jsonschema

        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            run = self.scaffold(root)
            r1 = self.run_gate(root, "loop-run", "data_profile")
            self.assertEqual(r1.returncode, 3, r1.stderr)
            q1_path = run / "outputs" / "checkpoints" / "01_data_profile_question.json"
            self.assertTrue(q1_path.exists())
            q1 = json.loads(q1_path.read_text(encoding="utf-8"))
            jsonschema.validate(q1, QUESTION_SCHEMA)
            self.assertEqual(q1["schema_version"], "data-insight-kit.checkpoint_question.v2")
            self.assertEqual(q1["interview_loop"]["round"], 1)
            self.assertFalse(q1["interview_loop"]["free_question_used_this_round"])

            applied = self.run_apply(
                root, "loop-run", "data_profile",
                "--free-question", "구별로 나눠서 보여줘",
                "--source", "user_chat",
                "--user-response", "구별로 나눠서 보여줘",
                "--transcript-ref", "thread:loop-1",
            )
            self.assertEqual(applied.returncode, 0, applied.stderr)
            record = self.read_answers(run)[-1]
            self.assertEqual(record["loop_action"], "free_question")
            self.assertFalse(record["continue_pipeline"])
            self.assertEqual(record["interview_round"], 1)

            r2 = self.run_gate(root, "loop-run", "data_profile")
            self.assertEqual(r2.returncode, 3, r2.stderr)
            q2_path = run / "outputs" / "checkpoints" / "01_data_profile_question.round2.json"
            self.assertTrue(q2_path.exists())
            q2 = json.loads(q2_path.read_text(encoding="utf-8"))
            jsonschema.validate(q2, QUESTION_SCHEMA)
            self.assertEqual(q2["interview_loop"]["round"], 2)
            prior = q2["interview_loop"]["prior_round"]
            self.assertEqual(prior["trigger"], "free_question")
            self.assertEqual(prior["answer_id"], record["answer_id"])
            self.assertEqual(prior["question_sha256"], sha256_file(q1_path))
            option_ids = [option["id"] for option in q2["options"]]
            self.assertIn("confirm_and_continue", option_ids)

    def test_approved_storyboard_layout_revision_creates_immutable_round2(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            run = self.scaffold(root)
            (run / "outputs" / "04_analysis.md").write_text(
                "# Analysis\n화면 구조 확인\n", encoding="utf-8"
            )
            (run / "outputs" / "chart_spec.json").write_text(
                json.dumps(minimal_chart_spec_v5()), encoding="utf-8"
            )
            layout_path = run / "outputs" / "dashboard_layout.json"
            layout_path.write_text(json.dumps(minimal_layout_v5()), encoding="utf-8")

            self.assertEqual(
                self.run_gate(root, "loop-run", "dashboard_storyboard").returncode, 3
            )
            approved = self.run_apply(
                root,
                "loop-run",
                "dashboard_storyboard",
                "--option",
                "approve_analyst_workspace",
                "--source",
                "user_chat",
                "--user-response",
                "탐색형 화면으로 승인",
                "--transcript-ref",
                "thread:layout-r1",
            )
            self.assertEqual(approved.returncode, 0, approved.stderr)

            revised = minimal_layout_v5()
            revised["revision"] = 2
            revised["generated_at"] = "2026-07-18T00:00:00Z"
            layout_path.write_text(json.dumps(revised), encoding="utf-8")

            gate = self.run_gate(root, "loop-run", "dashboard_storyboard")
            self.assertEqual(gate.returncode, 3, gate.stderr)
            q2_path = (
                run
                / "outputs"
                / "checkpoints"
                / "03_dashboard_storyboard_question.round2.json"
            )
            q2 = json.loads(q2_path.read_text(encoding="utf-8"))
            self.assertEqual(
                q2["interview_loop"]["prior_round"]["trigger"], "artifact_revision"
            )
            self.assertEqual(
                q2["approval_targets"]["dashboard_layout"]["sha256"],
                sha256_file(layout_path),
            )
            self.assertEqual(
                q2["approval_targets"]["dashboard_layout"]["revision"], 2
            )
            first_q2_hash = sha256_file(q2_path)

            repeated = self.run_gate(root, "loop-run", "dashboard_storyboard")
            self.assertEqual(repeated.returncode, 3, repeated.stderr)
            self.assertEqual(sha256_file(q2_path), first_q2_hash)

    def test_free_question_budget_and_flag_exclusivity(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            run = self.scaffold(root)
            self.assertEqual(self.run_gate(root, "loop-run", "data_profile").returncode, 3)
            base = [
                "--source", "user_chat",
                "--user-response", "질문",
                "--transcript-ref", "thread:loop-2",
            ]
            with self.subTest(case="free question + continue-pipeline rejected (I1)"):
                bad = self.run_apply(
                    root, "loop-run", "data_profile",
                    "--free-question", "질문", "--continue-pipeline", *base,
                )
                self.assertNotEqual(bad.returncode, 0)
                self.assertIn("상호 배타", bad.stderr)
            with self.subTest(case="second free question in the same round rejected (D3)"):
                first = self.run_apply(
                    root, "loop-run", "data_profile", "--free-question", "첫 질문", *base
                )
                self.assertEqual(first.returncode, 0, first.stderr)
                second = self.run_apply(
                    root, "loop-run", "data_profile", "--free-question", "둘째 질문", *base
                )
                self.assertNotEqual(second.returncode, 0)
                self.assertIn("라운드당 1개", second.stderr)
            self.assertTrue((run / "checkpoint_answers.json").exists())

    def test_question_file_outside_allowed_set_rejected(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            self.scaffold(root)
            rogue = root / "rogue_question.json"
            rogue.write_text("{}", encoding="utf-8")
            result = self.run_apply(
                root, "loop-run", "data_profile",
                "--question-file", str(rogue),
                "--answer", "임의 승인", "--continue-pipeline",
                "--source", "user_chat", "--user-response", "임의 승인",
                "--transcript-ref", "thread:loop-3",
            )
            self.assertNotEqual(result.returncode, 0)
            self.assertIn("outputs", result.stderr)

    def test_mirror_mismatch_fails_closed(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            run = self.scaffold(root)
            (run / "checkpoint_answers.json").write_text(
                json.dumps({"answers": []}, ensure_ascii=False), encoding="utf-8"
            )
            (run / "input" / "checkpoint_answers.json").write_text(
                json.dumps({"answers": [{"checkpoint_id": "data_profile", "continue_pipeline": True}]}, ensure_ascii=False),
                encoding="utf-8",
            )
            result = self.run_gate(root, "loop-run", "data_profile")
            self.assertNotIn(result.returncode, (0, 3, 4))
            self.assertIn("불일치", result.stderr)

    def test_companion_answer_does_not_flip_approval(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            run = self.scaffold(root)
            question_dir = run / "outputs" / "checkpoints"
            question_dir.mkdir(parents=True)
            question = {
                "run_id": "loop-run",
                "checkpoint_id": "data_profile",
                "checkpoint_kind": "data_review",
                "created_at": "2026-07-10T00:00:00+00:00",
                "question": "진행할까요?",
                "recommended_option_id": "go",
                "interview_loop": {"round": 1},
                "options": [
                    {"id": "go", "label": "진행", "description": "그대로 진행", "continue_pipeline": True},
                ],
                "companion_questions": [
                    {
                        "id": "row_meaning",
                        "question": "행 1개는 어떤 업무 단위인가요?",
                        "header": "행의 의미",
                        "allow_free_text": True,
                        "maps_to": {"domain_field": "row_meaning"},
                    }
                ],
            }
            (question_dir / "01_data_profile_question.json").write_text(
                json.dumps(question, ensure_ascii=False), encoding="utf-8"
            )
            approve = self.run_apply(
                root, "loop-run", "data_profile",
                "--option", "go", "--source", "user_chat",
                "--user-response", "네 진행해주세요", "--transcript-ref", "thread:loop-4",
            )
            self.assertEqual(approve.returncode, 0, approve.stderr)
            with self.subTest(case="companion + continue-pipeline rejected (I1)"):
                bad = self.run_apply(
                    root, "loop-run", "data_profile",
                    "--companion", "row_meaning", "--answer", "주문 1건",
                    "--continue-pipeline",
                    "--source", "user_chat", "--user-response", "주문 1건",
                    "--transcript-ref", "thread:loop-5",
                )
                self.assertNotEqual(bad.returncode, 0)
            companion = self.run_apply(
                root, "loop-run", "data_profile",
                "--companion", "row_meaning", "--answer", "주문 1건",
                "--source", "user_chat", "--user-response", "주문 1건",
                "--transcript-ref", "thread:loop-6",
            )
            self.assertEqual(companion.returncode, 0, companion.stderr)
            record = self.read_answers(run)[-1]
            self.assertEqual(record["companion_id"], "row_meaning")
            self.assertFalse(record["continue_pipeline"])
            self.assertEqual(record["maps_to"], {"domain_field": "row_meaning"})
            gate = self.run_gate(root, "loop-run", "data_profile")
            self.assertEqual(gate.returncode, 0, gate.stdout + gate.stderr)
            self.assertIn("approved", gate.stdout)


class InterviewLoopGuardTests(InterviewLoopHarness):
    """interview-loop-v2 §4.6/§9 가드·round-aware lineage (커밋 5) — 커밋 7 smoke의 전제."""

    def test_round2_approval_passes_gate_guard_and_qa_lineage(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            run = self.approve_round2_flow(root)
            with self.subTest(step="gate approves the round-2 answer"):
                gate = self.run_gate(root, "loop-run", "data_profile")
                self.assertEqual(gate.returncode, 0, gate.stdout + gate.stderr)
            with self.subTest(step="stage_guard allows frame entry"):
                guard = subprocess.run(
                    [sys.executable, str(self.STAGE_GUARD), "loop-run", "frame"],
                    cwd=root, text=True, capture_output=True,
                )
                self.assertEqual(guard.returncode, 0, guard.stdout + guard.stderr)
            with self.subTest(step="qa provenance resolves the round-2 question"):
                qa = load_module("qa_validate_loop", "qa/validate.py")
                answers = json.loads((run / "checkpoint_answers.json").read_text(encoding="utf-8"))
                latest = qa._latest_checkpoint_answers(answers)
                issues = qa._checkpoint_answer_provenance_issues(run, "data_profile", latest["data_profile"])
                self.assertEqual(issues, [])
            with self.subTest(step="generated round questions pass the language gate"):
                files = sorted(
                    str(p) for p in (run / "outputs" / "checkpoints").glob("01_data_profile_question*")
                )
                ufv = subprocess.run(
                    [sys.executable, str(self.UFV), *files],
                    cwd=root, text=True, capture_output=True,
                )
                self.assertEqual(ufv.returncode, 0, ufv.stdout + ufv.stderr)

    def test_orphan_round2_blocks_guard_and_gate(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            run = self.approve_round2_flow(root)
            q1 = run / "outputs" / "checkpoints" / "01_data_profile_question.json"
            q1.write_text(q1.read_text(encoding="utf-8") + "\n", encoding="utf-8")
            guard = subprocess.run(
                [sys.executable, str(self.STAGE_GUARD), "loop-run", "frame"],
                cwd=root, text=True, capture_output=True,
            )
            self.assertEqual(guard.returncode, 3, guard.stdout)
            self.assertIn("고아", guard.stdout)
            gate = self.run_gate(root, "loop-run", "data_profile")
            self.assertEqual(gate.returncode, 3, gate.stdout)

    def test_round3_file_and_forged_loop_action_block(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            run = self.approve_round2_flow(root)
            with self.subTest(case="stray round3 file blocks stage entry"):
                stray = run / "outputs" / "checkpoints" / "01_data_profile_question.round3.json"
                stray.write_text("{}", encoding="utf-8")
                guard = subprocess.run(
                    [sys.executable, str(self.STAGE_GUARD), "loop-run", "frame"],
                    cwd=root, text=True, capture_output=True,
                )
                self.assertEqual(guard.returncode, 3, guard.stdout)
                self.assertIn("허용되지 않는 라운드", guard.stdout)
                stray.unlink()
            with self.subTest(case="forged loop_action approval is rejected (I1)"):
                for target in (run / "checkpoint_answers.json", run / "input" / "checkpoint_answers.json"):
                    data = json.loads(target.read_text(encoding="utf-8"))
                    record = data["answers"][-1]
                    record["loop_action"] = "explore_direction"
                    record["continue_pipeline"] = True
                    target.write_text(
                        json.dumps(data, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
                    )
                guard = subprocess.run(
                    [sys.executable, str(self.STAGE_GUARD), "loop-run", "frame"],
                    cwd=root, text=True, capture_output=True,
                )
                self.assertEqual(guard.returncode, 3, guard.stdout)
                self.assertIn("I1", guard.stdout)

    def test_qa_latest_answers_skip_companion_records(self):
        qa = load_module("qa_validate_loop_units", "qa/validate.py")
        approve = {"checkpoint_id": "data_profile", "continue_pipeline": True, "answer_id": "a1"}
        companion = {
            "checkpoint_id": "data_profile",
            "continue_pipeline": False,
            "companion_id": "row_meaning",
            "answer_id": "a2",
        }
        latest = qa._latest_checkpoint_answers({"answers": [approve, companion]})
        self.assertEqual(latest["data_profile"]["answer_id"], "a1")


class InterviewLoopExplorationTests(InterviewLoopHarness):
    """interview-loop-v2 §5.1/§6 data_profile 탐색 문답 (커밋 6)."""

    def write_candidates(self, run: Path, count: int = 2) -> dict:
        exploration_dir = run / "outputs" / "exploration"
        exploration_dir.mkdir(parents=True, exist_ok=True)
        specs = [
            ("by_region", "지역별로 나눠 보기", "상위 3개 구가 전체의 41%"),
            ("by_period", "기간 변화로 보기", "최근 3개월 증가폭이 가장 큼"),
            ("by_type", "유형 구성으로 보기", "두 유형이 전체의 70%"),
        ][:count]
        candidates = []
        for cid, label, summary in specs:
            table = exploration_dir / f"candidate_{cid}.md"
            table.write_text("| 구분 | 값 |\n|---|---|\n| 예시 | 1 |\n", encoding="utf-8")
            candidates.append(
                {
                    "id": cid,
                    "label": label,
                    "why_interesting": "탐색에서 두드러진 축",
                    "mini_result": {
                        "summary": summary,
                        "table_path": f"outputs/exploration/candidate_{cid}.md",
                        "computation": "컬럼 기준 건수 집계, 결측 제외",
                        "source_columns": ["sido"],
                        "row_count_used": 1000,
                    },
                    "maps_to": {"frame_focus": cid},
                }
            )
        data = {
            "schema_version": "data-insight-kit.exploration_candidates.v1",
            "run_id": run.name,
            "created_at": "2026-07-10T00:00:00+00:00",
            "candidates": candidates,
        }
        (run / "outputs" / "exploration_candidates.json").write_text(
            json.dumps(data, ensure_ascii=False), encoding="utf-8"
        )
        return data

    def test_round1_renders_direction_options_from_candidates(self):
        import jsonschema

        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            run = self.scaffold(root)
            self.write_candidates(run)
            self.assertEqual(self.run_gate(root, "loop-run", "data_profile").returncode, 3)
            q1 = json.loads(
                (run / "outputs" / "checkpoints" / "01_data_profile_question.json").read_text(encoding="utf-8")
            )
            jsonschema.validate(q1, QUESTION_SCHEMA)
            option_ids = [opt["id"] for opt in q1["options"]]
            self.assertEqual(option_ids[0], "continue_with_current_data")
            self.assertIn("explore_by_region", option_ids)
            self.assertIn("explore_by_period", option_ids)
            for opt in q1["options"][1:]:
                self.assertFalse(opt["continue_pipeline"])  # 불변식 I1
                self.assertEqual(opt["maps_to"]["loop_action"], "explore_direction")
            self.assertTrue(q1["exploration"]["free_question_slot"])
            artifact_paths = " ".join(a["path"] for a in q1.get("artifacts", []))
            self.assertIn("candidate_by_region.md", artifact_paths)
            with self.subTest(step="question md embeds candidate evidence"):
                md_text = (run / "outputs" / "checkpoints" / "01_data_profile_question.md").read_text(
                    encoding="utf-8"
                )
                self.assertIn("## 근거 (미리 본 결과 원문)", md_text)
                self.assertIn("| 예시 | 1 |", md_text)
            with self.subTest(step="language gate passes"):
                files = sorted(
                    str(p) for p in (run / "outputs" / "checkpoints").glob("01_data_profile_question*")
                )
                ufv = subprocess.run(
                    [sys.executable, str(self.UFV), *files], cwd=root, text=True, capture_output=True
                )
                self.assertEqual(ufv.returncode, 0, ufv.stdout)

    def test_direction_pick_creates_round2_with_frame_focus_and_approves(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            run = self.scaffold(root)
            self.write_candidates(run)
            self.assertEqual(self.run_gate(root, "loop-run", "data_profile").returncode, 3)
            picked = self.run_apply(
                root, "loop-run", "data_profile",
                "--option", "explore_by_region",
                "--source", "user_chat",
                "--user-response", "지역별로 먼저 보고 싶어요",
                "--transcript-ref", "thread:exp-1",
            )
            self.assertEqual(picked.returncode, 0, picked.stderr)
            self.assertEqual(self.run_gate(root, "loop-run", "data_profile").returncode, 3)
            q2 = json.loads(
                (run / "outputs" / "checkpoints" / "01_data_profile_question.round2.json").read_text(
                    encoding="utf-8"
                )
            )
            self.assertIn("지역별로 나눠 보기", q2["question"])
            confirm = next(opt for opt in q2["options"] if opt["id"] == "confirm_direction")
            self.assertEqual(confirm["maps_to"]["frame_focus"], "by_region")
            self.assertIn("미리 본 결과", q2["current_understanding"])
            self.assertEqual(q2["interview_loop"]["prior_round"]["trigger"], "explore_direction")
            approved = self.run_apply(
                root, "loop-run", "data_profile",
                "--option", "confirm_direction",
                "--source", "user_chat",
                "--user-response", "이 방향으로 확정해주세요",
                "--transcript-ref", "thread:exp-2",
            )
            self.assertEqual(approved.returncode, 0, approved.stderr)
            gate = self.run_gate(root, "loop-run", "data_profile")
            self.assertEqual(gate.returncode, 0, gate.stdout + gate.stderr)
            record = self.read_answers(run)[-1]
            self.assertEqual(record["maps_to"]["frame_focus"], "by_region")
            guard = self.run_stage_guard(root, "loop-run", "frame")
            self.assertEqual(guard.returncode, 0, guard.stdout + guard.stderr)

    def test_print_existing_embeds_mini_result_evidence(self):
        # smoke 발견 수정: chat_prompt 650자 압축으로 근거 표가 탈락 — 핸드오프가
        # 미리 본 결과 '내용'을 직접 내장해야 사용자가 보고 선택할 수 있다.
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            run = self.scaffold(root)
            self.write_candidates(run)
            self.assertEqual(self.run_gate(root, "loop-run", "data_profile").returncode, 3)
            picked = self.run_apply(
                root, "loop-run", "data_profile",
                "--option", "explore_by_region",
                "--source", "user_chat",
                "--user-response", "지역별로 먼저 보고 싶어요",
                "--transcript-ref", "thread:ev-1",
            )
            self.assertEqual(picked.returncode, 0, picked.stderr)
            self.assertEqual(self.run_gate(root, "loop-run", "data_profile").returncode, 3)
            shown = subprocess.run(
                [sys.executable, str(self.GATE), "loop-run", "data_profile", "--print-existing"],
                cwd=root, text=True, capture_output=True,
            )
            self.assertEqual(shown.returncode, 0)
            self.assertIn("근거", shown.stdout)
            self.assertIn("| 예시 | 1 |", shown.stdout)

    def test_invalid_candidates_degrade_to_default_question(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            run = self.scaffold(root)
            self.write_candidates(run, count=1)
            self.assertEqual(self.run_gate(root, "loop-run", "data_profile").returncode, 3)
            q1 = json.loads(
                (run / "outputs" / "checkpoints" / "01_data_profile_question.json").read_text(encoding="utf-8")
            )
            option_ids = [opt["id"] for opt in q1["options"]]
            self.assertIn("revise_scope", option_ids)
            self.assertNotIn("exploration", q1)
            self.assertIn("기본 질문으로 진행", q1["current_understanding"])


class InterviewLoopRemainingStopsTests(InterviewLoopHarness):
    """interview-loop-v2 §5.2~5.5·§7 나머지 정지점 부착 (커밋 8)."""

    RECORD = KIT_ROOT / "scripts" / "record_free_question_result.py"

    def scaffold_full(self, root: Path, run_id: str = "loop-run") -> Path:
        run = self.scaffold(root, run_id)
        (run / "outputs" / "03_frame.md").write_text("# Frame\n핵심 질문과 지표 정의\n", encoding="utf-8")
        (run / "outputs" / "04_analysis.md").write_text("# Analysis\n핵심 발견: 서울 1위\n", encoding="utf-8")
        (run / "outputs" / "chart_spec.json").write_text(
            json.dumps({"charts": []}, ensure_ascii=False), encoding="utf-8"
        )
        return run

    def ask_free_question(self, root: Path, run_id: str, checkpoint: str, ref: str) -> subprocess.CompletedProcess:
        return self.run_apply(
            root, run_id, checkpoint,
            "--free-question", "상위 5개만 다시 보여줘",
            "--source", "user_chat",
            "--user-response", "상위 5개만 다시 보여줘",
            "--transcript-ref", ref,
        )

    def test_free_question_round2_works_at_every_checkpoint(self):
        checkpoints = [
            "analysis_strategy",
            "analysis_result_review",
            "dashboard_storyboard",
            "report_outline",
        ]
        for checkpoint in checkpoints:
            with self.subTest(checkpoint=checkpoint):
                with tempfile.TemporaryDirectory() as tmp:
                    root = Path(tmp)
                    run = self.scaffold_full(root)
                    r1 = self.run_gate(root, "loop-run", checkpoint)
                    self.assertEqual(r1.returncode, 3, r1.stderr)
                    asked = self.ask_free_question(root, "loop-run", checkpoint, f"thread:rs-{checkpoint}")
                    self.assertEqual(asked.returncode, 0, asked.stderr)
                    r2 = self.run_gate(root, "loop-run", checkpoint)
                    self.assertEqual(r2.returncode, 3, r2.stderr)
                    round2 = list((run / "outputs" / "checkpoints").glob(f"*_{checkpoint}_question.round2.json"))
                    self.assertEqual(len(round2), 1)
                    q2 = json.loads(round2[0].read_text(encoding="utf-8"))
                    self.assertEqual(q2["interview_loop"]["prior_round"]["trigger"], "free_question")

    def test_strategy_round2_recomputes_approval_targets(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            run = self.scaffold_full(root)
            route_path = run / "outputs" / "method_route.json"
            route_path.write_text(
                json.dumps({"schema_version": "data-insight-kit.method_route.v1", "run_id": "loop-run",
                            "created_at": "2026-07-10T00:00:00+00:00", "route": "descriptive",
                            "selected_methods": ["ranking"]}, ensure_ascii=False),
                encoding="utf-8",
            )
            self.assertEqual(self.run_gate(root, "loop-run", "analysis_strategy").returncode, 3)
            q1 = json.loads(
                (run / "outputs" / "checkpoints" / "02_analysis_strategy_question.json").read_text(encoding="utf-8")
            )
            old_sha = q1["approval_targets"]["method_route"]["sha256"]
            self.assertEqual(self.ask_free_question(root, "loop-run", "analysis_strategy", "thread:rs-t").returncode, 0)
            route_path.write_text(
                json.dumps({"schema_version": "data-insight-kit.method_route.v1", "run_id": "loop-run",
                            "created_at": "2026-07-10T00:10:00+00:00", "route": "descriptive",
                            "selected_methods": ["ranking", "distribution"]}, ensure_ascii=False),
                encoding="utf-8",
            )
            self.assertEqual(self.run_gate(root, "loop-run", "analysis_strategy").returncode, 3)
            q2 = json.loads(
                (run / "outputs" / "checkpoints" / "02_analysis_strategy_question.round2.json").read_text(
                    encoding="utf-8"
                )
            )
            new_sha = q2["approval_targets"]["method_route"]["sha256"]
            self.assertNotEqual(new_sha, old_sha)
            self.assertEqual(new_sha, hashlib.sha256(route_path.read_bytes()).hexdigest())

    def test_storyboard_summary_only_for_simple_runs(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            run = self.scaffold_full(root)
            with self.subTest(case="simple run includes first-result summary"):
                self.assertEqual(self.run_gate(root, "loop-run", "dashboard_storyboard").returncode, 3)
                q1 = json.loads(
                    (run / "outputs" / "checkpoints" / "03_dashboard_storyboard_question.json").read_text(
                        encoding="utf-8"
                    )
                )
                self.assertIn("1차 분석 결과 검토를 겸합니다", q1["current_understanding"])
                self.assertIn("핵심 발견: 서울 1위", q1["current_understanding"])
            with self.subTest(case="deep-route run does not claim to substitute the review stop"):
                (run / "outputs" / "method_route.json").write_text(
                    json.dumps({"schema_version": "data-insight-kit.method_route.v1", "run_id": "loop-run",
                                "created_at": "2026-07-10T00:00:00+00:00", "route": "statistical",
                                "selected_methods": ["group_difference_candidate"]}, ensure_ascii=False),
                    encoding="utf-8",
                )
                self.assertEqual(self.run_gate(root, "loop-run", "dashboard_storyboard").returncode, 3)
                q1 = json.loads(
                    (run / "outputs" / "checkpoints" / "03_dashboard_storyboard_question.json").read_text(
                        encoding="utf-8"
                    )
                )
                self.assertNotIn("검토를 겸합니다", q1["current_understanding"])

    def test_record_free_question_result_contract(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            run = self.scaffold_full(root)
            self.assertEqual(self.run_gate(root, "loop-run", "data_profile").returncode, 3)
            self.assertEqual(self.ask_free_question(root, "loop-run", "data_profile", "thread:rs-r").returncode, 0)
            answer_id = self.read_answers(run)[-1]["answer_id"]
            table = root / "mini_table.md"
            table.write_text("| 지역 | 건수 |\n|---|---|\n| 서울 | 10 |\n| 부산 | 7 |\n", encoding="utf-8")

            def record(*extra: str) -> subprocess.CompletedProcess:
                return subprocess.run(
                    [sys.executable, str(self.RECORD), "loop-run", "data_profile", *extra],
                    cwd=root, text=True, capture_output=True,
                )

            with self.subTest(case="unknown answer_id rejected"):
                bad = record("--answer-id", "chkans_none", "--method", "m", "--limits", "l",
                             "--table-md", str(table))
                self.assertNotEqual(bad.returncode, 0)
            with self.subTest(case="happy path writes linked md+json"):
                ok = record("--answer-id", answer_id, "--method", "sido 기준 건수 집계",
                            "--limits", "표본 작음", "--table-md", str(table))
                self.assertEqual(ok.returncode, 0, ok.stderr)
                meta = json.loads(
                    (run / "outputs" / "exploration" / "free_question_data_profile_1.json").read_text(
                        encoding="utf-8"
                    )
                )
                self.assertEqual(meta["answer_id"], answer_id)
                self.assertEqual(meta["table_rows"], 2)
                md_text = (run / "outputs" / "exploration" / "free_question_data_profile_1.md").read_text(
                    encoding="utf-8"
                )
                self.assertIn("상위 5개만 다시 보여줘", md_text)
            with self.subTest(case="duplicate result for the same answer rejected"):
                dup = record("--answer-id", answer_id, "--method", "m", "--limits", "l",
                             "--table-md", str(table))
                self.assertNotEqual(dup.returncode, 0)
            with self.subTest(case="round-2 question links the recorded mini result"):
                self.assertEqual(self.run_gate(root, "loop-run", "data_profile").returncode, 3)
                q2 = json.loads(
                    (run / "outputs" / "checkpoints" / "01_data_profile_question.round2.json").read_text(
                        encoding="utf-8"
                    )
                )
                minis = " ".join(q2["interview_loop"]["prior_round"].get("mini_result_paths", []))
                self.assertIn("free_question_data_profile_1", minis)
            with self.subTest(case="approval record cannot take a mini result"):
                confirm = self.run_apply(
                    root, "loop-run", "data_profile",
                    "--option", "confirm_and_continue", "--source", "user_chat",
                    "--user-response", "확인했습니다", "--transcript-ref", "thread:rs-ok",
                )
                self.assertEqual(confirm.returncode, 0, confirm.stderr)
                approve_id = self.read_answers(run)[-1]["answer_id"]
                bad = record("--answer-id", approve_id, "--method", "m", "--limits", "l",
                             "--table-md", str(table))
                self.assertNotEqual(bad.returncode, 0)

    def test_chat_handoff_advertises_free_question(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            self.scaffold_full(root)
            self.assertEqual(self.run_gate(root, "loop-run", "report_outline").returncode, 3)
            shown = subprocess.run(
                [sys.executable, str(self.GATE), "loop-run", "report_outline", "--print-existing"],
                cwd=root, text=True, capture_output=True,
            )
            self.assertEqual(shown.returncode, 0)
            self.assertIn("직접 질문", shown.stdout)


class InterviewLoopDomainTests(InterviewLoopHarness):
    """interview-loop-v2 §8 도메인 인터뷰 런타임 (커밋 9)."""

    BUILD = KIT_ROOT / "scripts" / "build_domain_intake.py"

    def scaffold_domain(self, root: Path, run_id: str = "loop-run") -> Path:
        run = self.scaffold(root, run_id)
        (run / "manifest.json").write_text(
            json.dumps({"run_id": run_id, "domain_mode": True}, ensure_ascii=False), encoding="utf-8"
        )
        return run

    def answer_companion(self, root: Path, run_id: str, checkpoint: str, companion: str,
                         text: str, ref: str) -> subprocess.CompletedProcess:
        return self.run_apply(
            root, run_id, checkpoint,
            "--companion", companion, "--answer", text,
            "--source", "user_chat", "--user-response", text, "--transcript-ref", ref,
        )

    def test_domain_mode_renders_priority_companions(self):
        import jsonschema

        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            run = self.scaffold_domain(root)
            self.assertEqual(self.run_gate(root, "loop-run", "data_profile").returncode, 3)
            q1 = json.loads(
                (run / "outputs" / "checkpoints" / "01_data_profile_question.json").read_text(encoding="utf-8")
            )
            jsonschema.validate(q1, QUESTION_SCHEMA)
            companions = q1.get("companion_questions") or []
            self.assertEqual([c["id"] for c in companions], ["row_meaning", "entity_grain"])
            self.assertEqual(companions[0]["maps_to"]["domain_field"], "row_meaning")
            with self.subTest(case="non-domain run has no companions"):
                run2 = self.scaffold(root, "plain-run")
                self.assertEqual(self.run_gate(root, "plain-run", "data_profile").returncode, 3)
                q_plain = json.loads(
                    (run2 / "outputs" / "checkpoints" / "01_data_profile_question.json").read_text(
                        encoding="utf-8"
                    )
                )
                self.assertNotIn("companion_questions", q_plain)
            with self.subTest(case="chat handoff shows companions"):
                shown = subprocess.run(
                    [sys.executable, str(self.GATE), "loop-run", "data_profile", "--print-existing"],
                    cwd=root, text=True, capture_output=True,
                )
                self.assertIn("행의 의미", shown.stdout)
            with self.subTest(case="question md carries companions and free-question guide"):
                md_text = (run / "outputs" / "checkpoints" / "01_data_profile_question.md").read_text(
                    encoding="utf-8"
                )
                self.assertIn("## 추가 확인 질문 (선택)", md_text)
                self.assertIn("행 1개는 어떤 업무 단위", md_text)
                self.assertIn("--companion row_meaning", md_text)
                self.assertIn("직접 질문(단계당 1회)", md_text)
            with self.subTest(case="companion md passes the language gate (커밋 12d 회귀)"):
                # 기록 명령의 checkpoint_id(내부 용어)가 사용자 구역에 노출되면
                # 언어 게이트가 자기 질문 파일을 차단한다 — domain smoke 발견.
                files = sorted(
                    str(p) for p in (run / "outputs" / "checkpoints").glob("01_data_profile_question*")
                )
                ufv = subprocess.run(
                    [sys.executable, str(self.UFV), *files], cwd=root, text=True, capture_output=True
                )
                self.assertEqual(ufv.returncode, 0, ufv.stdout)

    def test_readiness_gap_triggers_round2_and_build_derives_intake(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            run = self.scaffold_domain(root)
            self.assertEqual(self.run_gate(root, "loop-run", "data_profile").returncode, 3)
            self.assertEqual(
                self.answer_companion(root, "loop-run", "data_profile", "row_meaning",
                                      "가맹점 1곳의 월간 실적", "thread:dm-1").returncode, 0)
            self.assertEqual(
                self.answer_companion(root, "loop-run", "data_profile", "entity_grain",
                                      "가맹점 단위, 월 집계", "thread:dm-2").returncode, 0)
            with self.subTest(step="trigger (b) creates a reconfirmation round 2"):
                r2 = self.run_gate(root, "loop-run", "data_profile")
                self.assertEqual(r2.returncode, 3, r2.stderr)
                q2 = json.loads(
                    (run / "outputs" / "checkpoints" / "01_data_profile_question.round2.json").read_text(
                        encoding="utf-8"
                    )
                )
                self.assertEqual(q2["interview_loop"]["prior_round"]["trigger"], "domain_readiness_gap")
                self.assertIn("아직 확인되지 않은 업무 기준", q2["current_understanding"])
                remaining = [c["id"] for c in q2.get("companion_questions") or []]
                self.assertEqual(remaining, ["column_semantics", "exclusion_rules"])
            with self.subTest(step="round-2 approval closes the checkpoint"):
                confirm = self.run_apply(
                    root, "loop-run", "data_profile",
                    "--option", "confirm_and_continue", "--source", "user_chat",
                    "--user-response", "확인된 기준까지 반영해 진행해주세요",
                    "--transcript-ref", "thread:dm-3",
                )
                self.assertEqual(confirm.returncode, 0, confirm.stderr)
                self.assertEqual(self.run_gate(root, "loop-run", "data_profile").returncode, 0)
            with self.subTest(step="build_domain_intake derives file with readiness"):
                built = subprocess.run(
                    [sys.executable, str(self.BUILD), "loop-run"],
                    cwd=root, text=True, capture_output=True,
                )
                self.assertEqual(built.returncode, 0, built.stderr)
                intake = json.loads((run / "input" / "domain_intake.json").read_text(encoding="utf-8"))
                self.assertEqual(intake["row_meaning"], "가맹점 1곳의 월간 실적")
                self.assertEqual(intake["generated_by"], "scripts/build_domain_intake.py")
                self.assertEqual(len(intake["source_answer_ids"]), 2)
                self.assertEqual(intake["domain_readiness"]["status"], "partial")
                self.assertEqual(intake["domain_readiness"]["rule"], "deterministic-v1")
                self.assertIn("column_semantics", intake["domain_readiness"]["missing_required"])
            with self.subTest(step="derived file matches schema"):
                import jsonschema

                schema = json.loads(
                    (KIT_ROOT / "schemas" / "domain_intake.schema.json").read_text(encoding="utf-8")
                )
                intake = json.loads((run / "input" / "domain_intake.json").read_text(encoding="utf-8"))
                jsonschema.validate(intake, schema)

    def test_manual_intake_file_wins_and_gets_open_question_notes(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            run = self.scaffold_domain(root)
            manual = {
                "schema_version": "data-insight-kit.domain_intake.v1",
                "run_id": "loop-run",
                "created_at": "2026-07-10T00:00:00+00:00",
                "domain_scope": "가맹 유통",
                "objective": "지점 정리 판단",
                "row_meaning": "지점 1곳의 월 실적",
                "entity_grain": "지점",
                "column_semantics": [{"column": "grade", "meaning": "지점 등급"}],
                "exclusion_rules": ["테스트 지점 제외"],
                "kpi_definitions": [{"name": "월 매출", "formula": "sum(amount)"}],
                "forbidden_claims": [{"phrase": "폐점 확정"}],
                "evidence_boundaries": {"can_say": ["매출 비교"], "cannot_say": ["폐점 원인"]},
                "open_questions": [],
            }
            (run / "input" / "domain_intake.json").write_text(
                json.dumps(manual, ensure_ascii=False), encoding="utf-8"
            )
            self.assertEqual(self.run_gate(root, "loop-run", "data_profile").returncode, 3)
            self.assertEqual(
                self.answer_companion(root, "loop-run", "data_profile", "row_meaning",
                                      "사실은 주 단위 실적도 섞여 있어요", "thread:dm-4").returncode, 0)
            built = subprocess.run(
                [sys.executable, str(self.BUILD), "loop-run"], cwd=root, text=True, capture_output=True
            )
            self.assertEqual(built.returncode, 0, built.stderr)
            intake = json.loads((run / "input" / "domain_intake.json").read_text(encoding="utf-8"))
            self.assertEqual(intake["row_meaning"], "지점 1곳의 월 실적")  # 주입 우선
            self.assertNotIn("generated_by", intake)
            self.assertTrue(any("행의 의미" in note for note in intake["open_questions"]))


class DomainPackWriteTargetTests(unittest.TestCase):
    """커밋 11 오탐 수정: domains/ 루트 문서는 pack 콘텐츠가 아니다."""

    hook = load_module("dik_hook_pack_target", "scripts/dik_checkpoint_hook.py")

    def test_domains_root_doc_is_not_a_pack_write(self):
        target = KIT_ROOT / "domains" / "README.md"
        self.assertIsNone(self.hook.domain_pack_write_target(target))

    def test_pack_content_and_template_behave_as_before(self):
        with self.subTest(case="pack 내부 파일은 여전히 차단 대상"):
            target = KIT_ROOT / "domains" / "retail" / "kpi-rules.md"
            self.assertEqual(self.hook.domain_pack_write_target(target), "retail")
        with self.subTest(case="template은 여전히 예외"):
            target = KIT_ROOT / "domains" / "template" / "kpi-rules.md"
            self.assertIsNone(self.hook.domain_pack_write_target(target))


class InterviewLoopQaTests(InterviewLoopHarness):
    """interview-loop-v2 §9 QA 확장 (커밋 10) — interview_loop_checks."""

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.qa = load_module("qa_validate_interview", "qa/validate.py")

    def run_checks(self, run: Path) -> tuple[list[str], list[str]]:
        data_path = run / "outputs" / "dashboard_data.json"
        if not data_path.exists():
            data_path.write_text(json.dumps({"meta": {}}, ensure_ascii=False), encoding="utf-8")
        if not (run / "manifest.json").exists():
            (run / "manifest.json").write_text(
                json.dumps({"run_id": run.name}, ensure_ascii=False), encoding="utf-8"
            )
        self.qa.BLOCK.clear()
        self.qa.WARN.clear()
        self.qa.interview_loop_checks(data_path)
        return list(self.qa.BLOCK), list(self.qa.WARN)

    def append_record(self, run: Path, record: dict) -> None:
        for target in (run / "checkpoint_answers.json", run / "input" / "checkpoint_answers.json"):
            data = json.loads(target.read_text(encoding="utf-8")) if target.exists() else {"answers": []}
            data.setdefault("answers", []).append(record)
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_text(json.dumps(data, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")

    def test_clean_round2_run_produces_no_interview_blocks(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            run = self.approve_round2_flow(root)
            blocks, warns = self.run_checks(run)
            self.assertEqual(blocks, [])
            self.assertEqual(warns, [])

    def test_i1_violation_and_free_question_budget_block(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            run = self.approve_round2_flow(root)
            self.append_record(run, {
                "checkpoint_id": "data_profile", "answer_id": "forged-1",
                "loop_action": "explore_direction", "continue_pipeline": True,
                "interview_round": 1,
            })
            self.append_record(run, {
                "checkpoint_id": "data_profile", "answer_id": "extra-fq",
                "loop_action": "free_question", "continue_pipeline": False,
                "interview_round": 1,
            })
            blocks, _ = self.run_checks(run)
            self.assertTrue(any("I1" in b for b in blocks), blocks)
            self.assertTrue(any("라운드당 1개를 초과" in b for b in blocks), blocks)

    def test_round_file_sweep_blocks_and_warns(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            run = self.approve_round2_flow(root)
            checkpoints = run / "outputs" / "checkpoints"
            (checkpoints / "01_data_profile_question.round3.json").write_text("{}", encoding="utf-8")
            q1 = checkpoints / "01_data_profile_question.json"
            q1.write_text(q1.read_text(encoding="utf-8") + "\n", encoding="utf-8")  # R2 고아화
            blocks, warns = self.run_checks(run)
            self.assertTrue(any("허용되지 않는 라운드" in b for b in blocks), blocks)
            self.assertTrue(any("고아 라운드 2" in w for w in warns), warns)

    def test_mini_result_provenance_and_direct_quote(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            run = self.approve_round2_flow(root)
            exploration = run / "outputs" / "exploration"
            exploration.mkdir(parents=True, exist_ok=True)
            with self.subTest(case="unknown answer_id blocks"):
                (exploration / "free_question_data_profile_9.json").write_text(
                    json.dumps({"answer_id": "ghost", "created_at": "2026-07-11T00:00:00+00:00"}),
                    encoding="utf-8",
                )
                blocks, _ = self.run_checks(run)
                self.assertTrue(any("존재하지 않는 답변" in b for b in blocks), blocks)
                (exploration / "free_question_data_profile_9.json").unlink()
            free_answer = next(
                a for a in json.loads((run / "checkpoint_answers.json").read_text(encoding="utf-8"))["answers"]
                if a.get("loop_action") == "free_question"
            )
            with self.subTest(case="result created before the question blocks"):
                (exploration / "free_question_data_profile_1.json").write_text(
                    json.dumps({"answer_id": free_answer["answer_id"],
                                "created_at": "2020-01-01T00:00:00+00:00"}),
                    encoding="utf-8",
                )
                blocks, _ = self.run_checks(run)
                self.assertTrue(any("먼저 생성됨" in b for b in blocks), blocks)
            with self.subTest(case="direct quote in report warns"):
                (exploration / "free_question_data_profile_1.json").write_text(
                    json.dumps({"answer_id": free_answer["answer_id"],
                                "created_at": "2026-12-31T00:00:00+00:00"}),
                    encoding="utf-8",
                )
                (exploration / "free_question_data_profile_1.md").write_text(
                    "# 직접 질문 확인 결과\n결과:\n| 지역 | 건수 |\n|---|---|\n| 서울특별시 | 12345 |\n",
                    encoding="utf-8",
                )
                (run / "outputs" / "summary_report.md").write_text(
                    "# 보고서\n| 서울특별시 | 12345 |\n", encoding="utf-8"
                )
                blocks, warns = self.run_checks(run)
                self.assertEqual([b for b in blocks if "먼저 생성됨" in b], [])
                self.assertTrue(any("직접 인용" in w for w in warns), warns)

    def test_derived_domain_intake_integrity(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            run = self.approve_round2_flow(root)
            (run / "input" / "domain_intake.json").write_text(
                json.dumps({
                    "generated_by": "scripts/build_domain_intake.py",
                    "source_answer_ids": ["ghost-answer"],
                }, ensure_ascii=False),
                encoding="utf-8",
            )
            blocks, _ = self.run_checks(run)
            self.assertTrue(any("존재하지 않는 답변을 근거" in b for b in blocks), blocks)


class HandoffOrderEnforcementTests(InterviewLoopHarness):
    """전달 순서(턴 분리) 강제 — v4 smoke 발견: 팝업(ask_user_question) 답변은
    같은 질문 sha의 핸드오프 출력 스탬프가 선행해야 기록된다."""

    HOOK = KIT_ROOT / "scripts" / "dik_checkpoint_hook.py"

    def print_existing(self, root: Path, run_id: str, checkpoint: str) -> subprocess.CompletedProcess:
        return subprocess.run(
            [sys.executable, str(self.GATE), run_id, checkpoint, "--print-existing"],
            cwd=root, text=True, capture_output=True,
        )

    def test_popup_answer_without_handoff_print_is_rejected(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            self.scaffold(root)
            # run_gate는 --quiet 생성이라 핸드오프 스탬프가 없다
            self.assertEqual(self.run_gate(root, "loop-run", "data_profile").returncode, 3)
            denied = self.run_apply(
                root, "loop-run", "data_profile",
                "--option", "continue_with_current_data",
                "--source", "ask_user_question",
                "--user-response", "현재 데이터로 진행",
                "--transcript-ref", "popup:1",
            )
            self.assertNotEqual(denied.returncode, 0)
            self.assertIn("핸드오프 원문 출력이 선행", denied.stderr)

    def test_popup_answer_after_print_existing_carries_audit_fields(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            run = self.scaffold(root)
            self.assertEqual(self.run_gate(root, "loop-run", "data_profile").returncode, 3)
            printed = self.print_existing(root, "loop-run", "data_profile")
            self.assertEqual(printed.returncode, 0, printed.stderr)
            log = json.loads(
                (run / "outputs" / "checkpoints" / "handoff_log.json").read_text(encoding="utf-8")
            )
            self.assertEqual(len(log), 1)
            accepted = self.run_apply(
                root, "loop-run", "data_profile",
                "--option", "continue_with_current_data",
                "--source", "ask_user_question",
                "--user-response", "현재 데이터로 진행",
                "--transcript-ref", "popup:2",
            )
            self.assertEqual(accepted.returncode, 0, accepted.stderr)
            record = self.read_answers(run)[-1]
            self.assertTrue(record.get("handoff_printed_at"))
            self.assertGreaterEqual(record.get("handoff_to_answer_seconds", -1), 0)

    def test_user_chat_answer_without_stamp_is_still_accepted(self):
        # 채팅 답변은 본문에 원문이 남는 경로 — 완화 (스탬프 없이 허용)
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            run = self.scaffold(root)
            self.assertEqual(self.run_gate(root, "loop-run", "data_profile").returncode, 3)
            accepted = self.run_apply(
                root, "loop-run", "data_profile",
                "--option", "continue_with_current_data",
                "--source", "user_chat",
                "--user-response", "현재 데이터로 진행",
                "--transcript-ref", "chat:1",
            )
            self.assertEqual(accepted.returncode, 0, accepted.stderr)
            self.assertNotIn("handoff_printed_at", self.read_answers(run)[-1])

    def _hook_result(self, root: Path) -> str:
        payload = json.dumps(
            {"tool_name": "AskUserQuestion", "tool_input": {}, "cwd": str(root)}
        )
        proc = subprocess.run(
            [sys.executable, str(self.HOOK)],
            input=payload, cwd=root, text=True, capture_output=True,
        )
        self.assertEqual(proc.returncode, 0, proc.stderr)
        return proc.stdout

    def test_hook_gates_popup_until_handoff_is_printed(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            self.scaffold(root)
            self.assertEqual(self.run_gate(root, "loop-run", "data_profile").returncode, 3)
            with self.subTest(state="pending question without stamp -> deny"):
                decision = json.loads(self._hook_result(root))["hookSpecificOutput"]
                self.assertEqual(decision["permissionDecision"], "deny")
                self.assertIn("전달 순서", decision["permissionDecisionReason"])
            with self.subTest(state="after print-existing -> allow"):
                self.assertEqual(self.print_existing(root, "loop-run", "data_profile").returncode, 0)
                self.assertNotIn("deny", self._hook_result(root))

    def test_qa_warns_on_popup_answer_missing_stamp(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            run = self.scaffold(root)
            (run / "checkpoint_answers.json").write_text(
                json.dumps({
                    "answers": [{
                        "answer_id": "a1", "checkpoint_id": "data_profile",
                        "source": "ask_user_question", "human_confirmed": True,
                        "continue_pipeline": True,
                    }]
                }, ensure_ascii=False),
                encoding="utf-8",
            )
            qa = load_module("qa_validate_handoff", "qa/validate.py")
            qa.BLOCK.clear()
            qa.WARN.clear()
            previous = os.getcwd()
            os.chdir(root)
            try:
                qa.interview_loop_checks(str(run / "outputs" / "dashboard_data.json"))
            finally:
                os.chdir(previous)
            self.assertTrue(any("핸드오프 출력 스탬프 없음" in w for w in qa.WARN), qa.WARN)


if __name__ == "__main__":
    unittest.main()
