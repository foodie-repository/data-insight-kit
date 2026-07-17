from __future__ import annotations

import importlib.util
import hashlib
import json
import os
import shutil
import subprocess
import sys
import tempfile
import unittest
from datetime import datetime, timedelta, timezone
from pathlib import Path

import jsonschema

from tests.v5_fixtures import (
    minimal_chart_spec_v5,
    minimal_dashboard_data_v5,
    minimal_layout_v5,
)


KIT_ROOT = Path(__file__).resolve().parents[1]


def load_module(name: str, relative_path: str):
    path = KIT_ROOT / relative_path
    spec = importlib.util.spec_from_file_location(name, path)
    if spec is None or spec.loader is None:
        raise RuntimeError(f"cannot load module: {path}")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


class CheckpointGateTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.checkpoint_gate = load_module("checkpoint_gate", "scripts/checkpoint_gate.py")

    def test_all_checkpoints_have_human_review_contract(self):
        for checkpoint_id, config in self.checkpoint_gate.CHECKPOINTS.items():
            with self.subTest(checkpoint_id=checkpoint_id):
                brief = self.checkpoint_gate.USER_REVIEW_BRIEFS.get(checkpoint_id)
                self.assertIsInstance(brief, dict)
                self.assertTrue(brief.get("plain_title"))
                self.assertGreaterEqual(len(brief.get("what_user_should_review") or []), 3)
                self.assertTrue(brief.get("approval_question"))

                options = config.get("options") or []
                self.assertTrue(any(option.get("continue_pipeline") for option in options))
                self.assertTrue(any(not option.get("continue_pipeline") for option in options))
                self.assertIn(config.get("recommended_option_id"), {option.get("id") for option in options})

    def test_create_question_blocks_and_includes_data_preview(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            run = root / "runs" / "unit-run"
            (run / "input").mkdir(parents=True)
            (run / "outputs").mkdir(parents=True)
            (run / "input" / "sample.csv").write_text(
                "region,segment,value\nA,x,10\nB,y,20\n",
                encoding="utf-8",
            )
            (run / "outputs" / "01_profile.md").write_text("# Profile\n2 rows, 3 columns\n", encoding="utf-8")
            (run / "outputs" / "02_eda.md").write_text("# EDA\nregion and segment preview\n", encoding="utf-8")

            previous = Path.cwd()
            os.chdir(root)
            try:
                question, question_json, question_md = self.checkpoint_gate.create_question(
                    "unit-run",
                    "data_profile",
                )
            finally:
                os.chdir(previous)

            self.assertEqual(question["status"], "blocked_for_user_checkpoint")
            self.assertEqual(question["interview_style"], "deep_interview_checkpoint")
            self.assertTrue(question["response_instructions"]["human_response_required"])
            self.assertIn("사용자 실제 답변", question["response_instructions"]["apply_command"])
            self.assertIn("--transcript-ref", question["response_instructions"]["apply_command"])
            self.assertIn("추천 답안", question["chat_prompt"])
            self.assertIn("질문:", question["chat_prompt"])

            preview_path = root / question["data_snapshot"]["sample_preview_path"]
            self.assertTrue(preview_path.exists())
            self.assertTrue((root / question_json).exists())
            self.assertTrue((root / question_md).exists())

            manifest = json.loads((run / "manifest.json").read_text(encoding="utf-8"))
            checkpoint_stage = next(
                stage for stage in manifest["stages"] if stage["name"] == "checkpoint:data_profile"
            )
            self.assertEqual(checkpoint_stage["status"], "blocked_for_user_checkpoint")

    def test_checkpoint_chat_handoff_puts_question_before_files(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            run = root / "runs" / "unit-run"
            (run / "input").mkdir(parents=True)
            (run / "outputs").mkdir(parents=True)
            (run / "input" / "sample.csv").write_text(
                "region,segment,value\nA,x,10\nB,y,20\n",
                encoding="utf-8",
            )
            (run / "outputs" / "01_profile.md").write_text("# Profile\n2 rows, 3 columns\n", encoding="utf-8")
            (run / "outputs" / "02_eda.md").write_text("# EDA\nregion and segment preview\n", encoding="utf-8")

            previous = Path.cwd()
            os.chdir(root)
            try:
                question, question_json, question_md = self.checkpoint_gate.create_question(
                    "unit-run",
                    "data_profile",
                )
                handoff = self.checkpoint_gate.render_question_for_chat(question, question_json, question_md)
            finally:
                os.chdir(previous)

            self.assertLess(handoff.index("현재 이해:"), handoff.index("기술 정보:"))
            self.assertLess(handoff.index("질문:"), handoff.index("질문 파일:"))
            self.assertIn("추천 답안:", handoff)
            self.assertIn("채팅창에는 선택지 이름이나 원하는 수정 방향", handoff)
            self.assertIn("--user-response", handoff)
            self.assertIn("--transcript-ref", handoff)

    def test_dashboard_storyboard_question_exposes_design_profiles(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            run = root / "runs" / "unit-run"
            (run / "outputs").mkdir(parents=True)
            (run / "outputs" / "04_analysis.md").write_text(
                "# 대시보드 구성안\n추천안은 요약형, 대안은 분석가형입니다.\n",
                encoding="utf-8",
            )
            (run / "outputs" / "chart_spec.json").write_text(
                json.dumps(
                    {
                        "dashboard_story": {
                            "headline": "핵심 흐름",
                            "decision": "요약형 화면으로 공유한다",
                            "caveat": "원천 한계가 있다",
                        },
                        "dashboard_design": {
                            "selected_profile": "executive_brief",
                            "density": "standard",
                            "navigation": "tabs",
                            "rationale": "공유용 요약이 목적이다.",
                        },
                        "charts": [],
                    },
                    ensure_ascii=False,
                ),
                encoding="utf-8",
            )

            previous = Path.cwd()
            os.chdir(root)
            try:
                question, question_json, question_md = self.checkpoint_gate.create_question(
                    "unit-run",
                    "dashboard_storyboard",
                )
            finally:
                os.chdir(previous)

            option_ids = {option["id"] for option in question["options"]}
            self.assertIn("approve_storyboard", option_ids)
            self.assertIn("approve_analyst_workspace", option_ids)
            self.assertIn("approve_operations_monitor", option_ids)
            self.assertIn("dashboard_design_profiles", question)
            self.assertEqual(
                set(question["dashboard_design_profiles"]),
                {"executive_brief", "analyst_workspace", "operations_monitor"},
            )
            self.assertIn("화면 스타일 선택지", question["chat_prompt"])
            markdown = (root / question_md).read_text(encoding="utf-8")
            self.assertIn("대시보드 스타일 선택지", markdown)
            self.assertTrue((root / question_json).exists())

    def test_dashboard_storyboard_question_follows_selected_profile_and_schema(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            run = root / "runs" / "unit-run"
            (run / "outputs").mkdir(parents=True)
            (run / "outputs" / "04_analysis.md").write_text(
                "# 분석 결과\n탐색형 화면에서 세그먼트와 예외를 비교합니다.\n",
                encoding="utf-8",
            )
            (run / "outputs" / "chart_spec.json").write_text(
                json.dumps(
                    {
                        "dashboard_story": {
                            "headline": "세그먼트 집중도를 탐색한다",
                            "decision": "예외 조합을 비교한다",
                            "caveat": "시계열 컬럼이 없다",
                        },
                        "dashboard_design": {
                            "selected_profile": "analyst_workspace",
                            "density": "compact",
                            "navigation": "tabs",
                            "rationale": "세그먼트와 예외 비교가 핵심이다.",
                        },
                        "charts": [],
                    },
                    ensure_ascii=False,
                ),
                encoding="utf-8",
            )

            previous = Path.cwd()
            os.chdir(root)
            try:
                question, _, _ = self.checkpoint_gate.create_question(
                    "unit-run",
                    "dashboard_storyboard",
                )
            finally:
                os.chdir(previous)

            schema = json.loads(
                (KIT_ROOT / "schemas" / "checkpoint_question.schema.json").read_text(
                    encoding="utf-8"
                )
            )
            jsonschema.Draft202012Validator(schema).validate(question)
            self.assertLessEqual(len(question["options"]), 4)
            self.assertEqual(question["recommended_option_id"], "approve_analyst_workspace")
            recommended = [option for option in question["options"] if option.get("recommended")]
            self.assertEqual([option["id"] for option in recommended], ["approve_analyst_workspace"])
            self.assertIn("탐색형 화면", question["recommended_answer"])
            self.assertIn("탐색형 화면", question["chat_prompt"])
            self.assertNotIn("요약형 화면으로 승인한다", question["recommended_answer"])


class CheckpointAnswerCliTests(unittest.TestCase):
    def test_wrapper_reprints_checkpoint_question_after_user_text_validation(self):
        wrapper = (KIT_ROOT / "scripts" / "run_codex_pipeline.sh").read_text(encoding="utf-8")
        self.assertIn('checkpoint_gate.py "$RUN_ID" "$checkpoint" --quiet', wrapper)
        self.assertIn('checkpoint_gate.py "$RUN_ID" "$checkpoint" --print-existing', wrapper)
        self.assertLess(
            wrapper.index('validate_user_facing_text.py "${files[@]}"'),
            wrapper.index('checkpoint_gate.py "$RUN_ID" "$checkpoint" --print-existing'),
        )

    def test_checkpoint_print_existing_cli_uses_chat_first_handoff(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            question_dir = root / "runs" / "unit-run" / "outputs" / "checkpoints"
            question_dir.mkdir(parents=True)
            (question_dir / "01_data_profile_question.json").write_text(
                json.dumps(
                    {
                        "run_id": "unit-run",
                        "checkpoint_id": "data_profile",
                        "header": "데이터 탐색 확인",
                        "chat_prompt": "현재 이해: 데이터 확인 단계입니다.\n막힌 결정: 범위를 승인해야 합니다.\n추천 답안: 현재 데이터로 진행\n질문: 계속 진행할까요?",
                        "recommended_option_id": "continue",
                        "options": [
                            {
                                "id": "continue",
                                "label": "현재 데이터로 진행",
                                "description": "이 범위로 다음 단계로 갑니다.",
                                "continue_pipeline": True,
                            }
                        ],
                        "response_instructions": {
                            "apply_command": "python3 scripts/apply_checkpoint_answer.py unit-run data_profile --option continue --source user_chat --user-response \"네\" --transcript-ref \"thread:unit-turn\"",
                            "resume_command": "bash scripts/run_codex_pipeline.sh unit-run --guided",
                        },
                    },
                    ensure_ascii=False,
                ),
                encoding="utf-8",
            )
            script = KIT_ROOT / "scripts" / "checkpoint_gate.py"
            result = subprocess.run(
                [sys.executable, str(script), "unit-run", "data_profile", "--print-existing"],
                cwd=root,
                text=True,
                capture_output=True,
                check=False,
            )
            self.assertEqual(result.returncode, 0, result.stderr + result.stdout)
            self.assertLess(result.stdout.index("현재 이해:"), result.stdout.index("기술 정보:"))
            self.assertLess(result.stdout.index("질문:"), result.stdout.index("질문 파일:"))

    def test_checkpoint_answer_requires_real_user_confirmation_to_continue(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            question_dir = root / "runs" / "unit-run" / "outputs" / "checkpoints"
            question_dir.mkdir(parents=True)
            (question_dir / "01_data_profile_question.json").write_text(
                json.dumps(
                    {
                        "run_id": "unit-run",
                        "created_at": "2026-07-09T00:00:00+00:00",
                        "checkpoint_id": "data_profile",
                        "checkpoint_kind": "data_review",
                        "question": "진행할까요?",
                        "blocked_decision": "사용자 확인 필요",
                        "recommended_answer": "진행",
                        "chat_prompt": "데이터를 보고 진행 여부를 알려주세요.",
                        "options": [
                            {
                                "id": "continue",
                                "label": "진행",
                                "continue_pipeline": True,
                                "maps_to": {"checkpoint_decision": "approved"},
                            }
                        ],
                    },
                    ensure_ascii=False,
                )
                + "\n",
                encoding="utf-8",
            )
            script = KIT_ROOT / "scripts" / "apply_checkpoint_answer.py"

            rejected = subprocess.run(
                [
                    sys.executable,
                    str(script),
                    "unit-run",
                    "data_profile",
                    "--option",
                    "continue",
                    "--source",
                    "agent_assumption",
                    "--user-response",
                    "사용자가 승인했다고 가정",
                ],
                cwd=root,
                text=True,
                capture_output=True,
                check=False,
            )
            self.assertNotEqual(rejected.returncode, 0)
            self.assertIn("not human-confirmed", rejected.stderr + rejected.stdout)
            self.assertFalse((root / "runs" / "unit-run" / "checkpoint_answers.json").exists())

            missing_transcript = subprocess.run(
                [
                    sys.executable,
                    str(script),
                    "unit-run",
                    "data_profile",
                    "--option",
                    "continue",
                    "--source",
                    "user_chat",
                    "--user-response",
                    "네, 현재 데이터로 진행하세요.",
                ],
                cwd=root,
                text=True,
                capture_output=True,
                check=False,
            )
            self.assertNotEqual(missing_transcript.returncode, 0)
            self.assertIn("require --transcript-ref", missing_transcript.stderr + missing_transcript.stdout)
            self.assertFalse((root / "runs" / "unit-run" / "checkpoint_answers.json").exists())

            accepted = subprocess.run(
                [
                    sys.executable,
                    str(script),
                    "unit-run",
                    "data_profile",
                    "--option",
                    "continue",
                    "--source",
                    "user_chat",
                    "--user-response",
                    "네, 현재 데이터로 진행하세요.",
                    "--transcript-ref",
                    "thread:unit-turn-1",
                ],
                cwd=root,
                text=True,
                capture_output=True,
                check=False,
            )
            self.assertEqual(accepted.returncode, 0, accepted.stderr + accepted.stdout)
            answers = json.loads((root / "runs" / "unit-run" / "checkpoint_answers.json").read_text())
            answer = answers["answers"][0]
            self.assertTrue(answer["continue_pipeline"])
            self.assertTrue(answer["human_confirmed"])
            self.assertEqual(answer["source"], "user_chat")
            self.assertEqual(answer["transcript_ref"], "thread:unit-turn-1")
            self.assertEqual(answer["approval_contract_version"], "checkpoint-answer.v3")
            self.assertEqual(answer["recorded_by"], "scripts/apply_checkpoint_answer.py")
            self.assertTrue(answer["answer_id"])
            self.assertEqual(answer["question_ref"]["checkpoint_id"], "data_profile")
            self.assertTrue(answer["question_ref"]["sha256"])
            self.assertTrue((root / "runs" / "unit-run" / "input" / "checkpoint_answers.json").exists())

    def test_checkpoint_answer_rejects_legacy_question_without_created_at(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            question_dir = root / "runs" / "unit-run" / "outputs" / "checkpoints"
            question_dir.mkdir(parents=True)
            (question_dir / "01_data_profile_question.json").write_text(
                json.dumps(
                    {
                        "run_id": "unit-run",
                        "checkpoint_id": "data_profile",
                        "checkpoint_kind": "data_review",
                        "question": "진행할까요?",
                        "options": [
                            {
                                "id": "continue",
                                "label": "진행",
                                "continue_pipeline": True,
                            }
                        ],
                    },
                    ensure_ascii=False,
                ),
                encoding="utf-8",
            )
            script = KIT_ROOT / "scripts" / "apply_checkpoint_answer.py"
            result = subprocess.run(
                [
                    sys.executable,
                    str(script),
                    "unit-run",
                    "data_profile",
                    "--option",
                    "continue",
                    "--source",
                    "user_chat",
                    "--user-response",
                    "네, 진행하세요.",
                    "--transcript-ref",
                    "thread:legacy-test-turn",
                ],
                cwd=root,
                text=True,
                capture_output=True,
                check=False,
            )
            self.assertNotEqual(result.returncode, 0)
            self.assertIn("missing created_at", result.stderr + result.stdout)


class CheckpointGateProvenanceTests(unittest.TestCase):
    """The wrapper's stop/go gate must require the same v3 provenance as stage_guard."""

    SCRIPT = KIT_ROOT / "scripts" / "checkpoint_gate.py"

    def _gate(self, root: Path) -> subprocess.CompletedProcess:
        return subprocess.run(
            [sys.executable, str(self.SCRIPT), "cx", "data_profile", "--quiet"],
            cwd=root,
            text=True,
            capture_output=True,
            check=False,
        )

    def test_gate_rejects_answer_without_v3_provenance(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            run = root / "runs" / "cx"
            (run / "outputs" / "checkpoints").mkdir(parents=True)
            (run / "outputs" / "checkpoints" / "01_data_profile_question.json").write_text(
                json.dumps({"run_id": "cx", "checkpoint_id": "data_profile", "created_at": "2026-07-09T00:00:00+00:00"}),
                encoding="utf-8",
            )
            # source/human_confirmed/user_response present, but no recorded_by /
            # answer_id / approval_contract_version / question_ref -> must reject.
            (run / "checkpoint_answers.json").write_text(
                json.dumps(
                    {
                        "answers": [
                            {
                                "checkpoint_id": "data_profile",
                                "continue_pipeline": True,
                                "source": "user_chat",
                                "human_confirmed": True,
                                "user_response": "Implement the proposed plan.",
                                "answered_at": "2026-07-09T00:00:00+00:00",
                            }
                        ]
                    }
                ),
                encoding="utf-8",
            )
            result = self._gate(root)
            self.assertEqual(result.returncode, 3, result.stdout)
            self.assertIn("rejected", result.stdout)

    def test_gate_accepts_v3_answer_recorded_by_helper(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            run = root / "runs" / "cx"
            (run / "outputs" / "checkpoints").mkdir(parents=True)
            (run / "outputs" / "checkpoints" / "01_data_profile_question.json").write_text(
                json.dumps(
                    {
                        "run_id": "cx",
                        "created_at": "2026-07-09T00:00:00+00:00",
                        "checkpoint_id": "data_profile",
                        "options": [{"id": "continue", "label": "진행", "continue_pipeline": True}],
                    },
                    ensure_ascii=False,
                )
                + "\n",
                encoding="utf-8",
            )
            recorded = subprocess.run(
                [
                    sys.executable,
                    str(KIT_ROOT / "scripts" / "apply_checkpoint_answer.py"),
                    "cx",
                    "data_profile",
                    "--option",
                    "continue",
                    "--source",
                    "user_chat",
                    "--user-response",
                    "네, 진행하세요.",
                    "--transcript-ref",
                    "thread:cx-1",
                ],
                cwd=root,
                text=True,
                capture_output=True,
                check=False,
            )
            self.assertEqual(recorded.returncode, 0, recorded.stderr)
            result = self._gate(root)
            self.assertEqual(result.returncode, 0, result.stdout)
            self.assertIn("approved", result.stdout)


class StageGuardTests(unittest.TestCase):
    def test_stage_guard_blocks_frame_without_data_profile_answer(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / "runs" / "unit-run" / "outputs" / "checkpoints").mkdir(parents=True)
            script = KIT_ROOT / "scripts" / "stage_guard.py"
            result = subprocess.run(
                [sys.executable, str(script), "unit-run", "frame"],
                cwd=root,
                text=True,
                capture_output=True,
                check=False,
            )
            self.assertEqual(result.returncode, 3)
            self.assertIn("approved answer missing", result.stdout)

    def test_stage_guard_accepts_v3_checkpoint_answer(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            run = root / "runs" / "unit-run"
            checkpoints = run / "outputs" / "checkpoints"
            checkpoints.mkdir(parents=True)
            qpath = checkpoints / "01_data_profile_question.json"
            created_at = "2026-07-09T00:00:00+00:00"
            qpath.write_text(
                json.dumps({"checkpoint_id": "data_profile", "created_at": created_at}, ensure_ascii=False),
                encoding="utf-8",
            )
            rel_qpath = Path("runs") / "unit-run" / "outputs" / "checkpoints" / "01_data_profile_question.json"
            (run / "checkpoint_answers.json").write_text(
                json.dumps(
                    {
                        "answers": [
                            {
                                "answer_id": "answer-data-profile",
                                "checkpoint_id": "data_profile",
                                "recorded_by": "scripts/apply_checkpoint_answer.py",
                                "source": "user_chat",
                                "transcript_ref": "thread:unit-turn-1",
                                "user_response": "네, 데이터 확인 후 진행합니다.",
                                "human_confirmed": True,
                                "approval_contract_version": "checkpoint-answer.v3",
                                "continue_pipeline": True,
                                "answered_at": "2026-07-09T00:01:00+00:00",
                                "question_ref": {
                                    "path": str(rel_qpath),
                                    "sha256": hashlib.sha256(qpath.read_bytes()).hexdigest(),
                                    "created_at": created_at,
                                    "checkpoint_id": "data_profile",
                                },
                            }
                        ]
                    },
                    ensure_ascii=False,
                ),
                encoding="utf-8",
            )
            script = KIT_ROOT / "scripts" / "stage_guard.py"
            result = subprocess.run(
                [sys.executable, str(script), "unit-run", "frame"],
                cwd=root,
                text=True,
                capture_output=True,
                check=False,
            )
            self.assertEqual(result.returncode, 0, result.stderr + result.stdout)
            self.assertIn("stage guard passed", result.stdout)


class IntakeAnswerCliTests(unittest.TestCase):
    def test_intake_answer_persists_report_and_adapter_policy(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            output_dir = root / "runs" / "unit-run" / "outputs"
            output_dir.mkdir(parents=True)
            (output_dir / "intake_questions.json").write_text(
                json.dumps(
                    {
                        "run_id": "unit-run",
                        "question_id": "external_adapter_policy",
                        "question_kind": "external_adapter_policy",
                        "question": "외부 보정 데이터를 얼마나 붙일까요?",
                        "recommended_option_id": "location_context",
                        "options": [
                            {
                                "id": "location_context",
                                "label": "입지 판단 보강",
                                "maps_to": {
                                    "report_contract": {
                                        "depth": "deep",
                                        "audience": "mixed",
                                        "evidence_scope": "data_only",
                                    },
                                    "external_adapters": {
                                        "mode": "ask_user_selected",
                                        "selected_categories": ["population", "rent"],
                                        "unavailable_categories": ["sales"],
                                        "interpretation_guards": ["layer_separation_required"],
                                    },
                                },
                            }
                        ],
                        "response_instructions": {"write_to": "runs/unit-run/input/intake_draft.yaml"},
                        "interview_state": {"remaining_decisions": ["external_adapter_policy"]},
                    },
                    ensure_ascii=False,
                )
                + "\n",
                encoding="utf-8",
            )
            script = KIT_ROOT / "scripts" / "apply_intake_answer.py"
            result = subprocess.run(
                [
                    sys.executable,
                    str(script),
                    "unit-run",
                    "--option",
                    "location_context",
                    "--source",
                    "ask_user_question",
                ],
                cwd=root,
                text=True,
                capture_output=True,
                check=False,
            )
            self.assertEqual(result.returncode, 0, result.stderr + result.stdout)
            draft = json.loads((root / "runs" / "unit-run" / "input" / "intake_draft.yaml").read_text())
            self.assertEqual(draft["draft_status"], "ready_for_final_intake")
            self.assertEqual(draft["report"]["depth"], "deep")
            self.assertEqual(draft["external_adapters"]["selected_categories"], ["population", "rent"])
            self.assertEqual(draft["interview"]["style"], "ask_user_question + deep_interview")


class UserFacingTextTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.validator = load_module("validate_user_facing_text", "scripts/validate_user_facing_text.py")

    def test_internal_terms_are_blocked_only_in_user_facing_markdown_section(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "plan.md"
            path.write_text(
                "# 사용자용 분석 기획안\nchart_spec로 진행합니다.\n\n## 기술 부록\nchart_spec.json\n",
                encoding="utf-8",
            )
            issues = self.validator.validate_path(path)
            self.assertEqual(len(issues), 1)
            self.assertIn("chart_spec", issues[0])

            path.write_text(
                "# 사용자용 분석 기획안\n차트 구성안으로 진행합니다.\n\n## 기술 부록\nchart_spec.json\n",
                encoding="utf-8",
            )
            self.assertEqual(self.validator.validate_path(path), [])

    def test_user_review_brief_json_blocks_internal_terms(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "question.json"
            path.write_text(
                json.dumps({"user_review_brief": {"plain_title": "chart_spec 확인"}}, ensure_ascii=False),
                encoding="utf-8",
            )
            issues = self.validator.validate_path(path)
            self.assertTrue(any("chart_spec" in issue for issue in issues))

    def test_plan_mode_output_blocks_technical_template_before_user_brief(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "plan.md"
            path.write_text(
                "\n".join(
                    [
                        "# 경찰청 범죄 지역별 통계 data-insight-kit 분석 계획",
                        "",
                        "## Summary",
                        "- 새 run id는 `police-crime-region-2024-counts-20260709-v3`로 둔다.",
                        "",
                        "## Key Changes",
                        "- input과 outputs를 만든다.",
                        "",
                        "## Test Plan",
                        "- qa/validate.py를 실행한다.",
                    ]
                ),
                encoding="utf-8",
            )
            issues = self.validator.validate_path(path)
            self.assertTrue(any("technical plan heading" in issue for issue in issues))

    def test_plan_mode_output_allows_technical_template_in_appendix(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "plan.md"
            path.write_text(
                "\n".join(
                    [
                        "# 이번 분석은 이렇게 진행합니다",
                        "",
                        "## 한 줄 목적",
                        "선택한 데이터에서 범죄 발생 건수의 분포와 지역 차이를 확인합니다.",
                        "",
                        "## 답할 질문",
                        "- 어떤 범죄 유형과 지역의 발생 건수가 큰가요?",
                        "- 현재 데이터만으로 판단하기 어려운 것은 무엇인가요?",
                        "",
                        "## 질문",
                        "이 범위로 먼저 데이터 확인 단계부터 시작할까요?",
                        "",
                        "## 기술 부록",
                        "",
                        "## Summary",
                        "- run id와 QA 절차를 정리한다.",
                        "",
                        "## Test Plan",
                        "- qa/validate.py를 실행한다.",
                    ]
                ),
                encoding="utf-8",
            )
            self.assertEqual(self.validator.validate_path(path), [])

    def test_plan_mode_output_blocks_preapproval_selected_direction_and_risk_label(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "plan.md"
            path.write_text(
                "\n".join(
                    [
                        "# 이번 분석은 이렇게 진행합니다",
                        "",
                        "## 한 줄 목적",
                        "선택한 데이터에서 발생 건수의 분포와 지역 차이를 확인합니다.",
                        "",
                        "선택된 방향:",
                        "- 현황·리스크 진단",
                        "- 위험 점검",
                        "",
                        "## 질문",
                        "이 범위로 먼저 데이터 확인 단계부터 시작할까요?",
                    ]
                ),
                encoding="utf-8",
            )
            issues = self.validator.validate_path(path)
            self.assertTrue(any("선택된 방향" in issue for issue in issues))
            self.assertTrue(any("현황·리스크 진단" in issue for issue in issues))
            self.assertTrue(any("위험 점검" in issue for issue in issues))

    def test_reader_text_blocks_relative_period_placeholders_and_unresolved_units(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "storyboard.md"
            path.write_text(
                "2026-06 가격은 시작월보다 높다.\n가격 단위 미확인으로 표시한다.\n",
                encoding="utf-8",
            )

            issues = self.validator.validate_path(path)

            self.assertTrue(any("시작월" in issue for issue in issues))
            self.assertTrue(any("가격 단위 미확인" in issue for issue in issues))


class QaQualityGuardTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.qa = load_module("dik_qa_validate", "qa/validate.py")

    def setUp(self):
        self.qa.BLOCK.clear()
        self.qa.WARN.clear()

    def test_deep_chart_spec_blocks_shallow_or_repetitive_design(self):
        self.qa.chart_spec_quality_checks({"dashboard_story": {}, "charts": []}, deep=True)
        self.assertTrue(any("dashboard_story" in item for item in self.qa.BLOCK))
        self.assertTrue(any("차트 수 부족" in item for item in self.qa.BLOCK))

        self.qa.BLOCK.clear()
        repetitive = {
            "dashboard_story": {
                "headline": "질문별 비교",
                "decision": "비교 기준을 확인한다",
                "caveat": "표본 한계가 있다",
            },
            "charts": [
                {
                    "id": f"chart_{idx}",
                    "question": f"세그먼트 {idx}의 순위는 무엇인가?",
                    "method": "ranking",
                    "chart": {"type": "bar"},
                    "insight": {
                        "finding": f"세그먼트 {idx}는 상위권과 하위권 차이가 있다.",
                        "evidence": f"상위 값은 {idx + 10}, 하위 값은 {idx}로 차이가 있다.",
                        "limit": "순위는 원인이나 성과를 직접 설명하지 않는다.",
                    },
                }
                for idx in range(4)
            ],
        }
        self.qa.chart_spec_quality_checks(repetitive, deep=True)
        self.assertTrue(any("방법론 다양성 부족" in item for item in self.qa.BLOCK))
        self.assertTrue(any("차트 유형 다양성 부족" in item for item in self.qa.BLOCK))

    def test_reader_facing_guards_block_internal_terms_and_raw_columns(self):
        self.qa.reader_facing_dashboard_checks(
            {
                "meta": {"title": "fresh snapshot data_only"},
                "kpis": [],
                "panels": [],
            }
        )
        self.assertTrue(any("meta.title" in item for item in self.qa.BLOCK))

        self.qa.BLOCK.clear()
        with tempfile.TemporaryDirectory() as tmp:
            outputs = Path(tmp)
            (outputs / "summary_report.md").write_text(
                "# 업무지구 분석\nTOT_WRC_POPLTN_CO 기준으로 설명합니다.\n",
                encoding="utf-8",
            )
            self.qa.reader_facing_report_checks(outputs)
        self.assertTrue(any("원천 컬럼명" in item for item in self.qa.BLOCK))

    def test_reader_facing_guards_block_relative_period_placeholders_and_unresolved_units(self):
        self.qa.reader_facing_dashboard_checks(
            {
                "meta": {"title": "서울 아파트 매매 변화"},
                "kpis": [
                    {
                        "label": "현재 가격은 시작월보다 높다",
                        "value": 97250,
                        "unit": "가격 단위 미확인",
                        "kind": "absolute",
                        "status": "neutral",
                    }
                ],
                "panels": [],
            }
        )

        self.assertTrue(any("시작월" in item for item in self.qa.BLOCK))
        self.assertTrue(any("가격 단위 미확인" in item for item in self.qa.BLOCK))

    def test_v5_series_scale_guard_requires_stacked_panels_when_one_line_is_flattened(self):
        data = {
            "meta": {"dashboard_profile_contract": "v5"},
            "panels": [
                {
                    "charts": [
                        {
                            "id": "trend",
                            "type": "line",
                            "encoding": {
                                "series": [
                                    {"label": "가격", "values": [90, 100, 110]},
                                    {"label": "거래량", "values": [50, 1200, 80]},
                                ]
                            },
                        }
                    ]
                }
            ],
        }
        layout = {
            "components": [
                {
                    "kind": "chart",
                    "data_refs": ["trend"],
                    "render_options": {"series_layout": "overlay"},
                }
            ]
        }

        self.qa.v5_series_scale_checks(data, layout)
        self.assertTrue(any("관측 범위" in item for item in self.qa.BLOCK))

        self.qa.BLOCK.clear()
        layout["components"][0]["render_options"]["series_layout"] = "stacked_panels"
        self.qa.v5_series_scale_checks(data, layout)
        self.assertEqual(self.qa.BLOCK, [])

    def test_dashboard_profile_mismatch_blocks(self):
        data = {"meta": {"dashboard_profile": "analyst_workspace"}}
        chart_spec = {"dashboard_design": {"selected_profile": "executive_brief"}}
        self.qa.dashboard_profile_checks(data, chart_spec)
        self.assertTrue(any("dashboard_profile" in item for item in self.qa.BLOCK))

        self.qa.BLOCK.clear()
        self.qa.WARN.clear()
        data["meta"]["dashboard_profile"] = "operations_monitor"
        chart_spec["dashboard_design"]["selected_profile"] = "operations_monitor"
        self.qa.dashboard_profile_checks(data, chart_spec)
        self.assertEqual(self.qa.BLOCK, [])

    def test_dashboard_template_supports_design_profiles(self):
        template = (KIT_ROOT / "templates" / "dashboard.html").read_text(encoding="utf-8")
        self.assertIn("DASHBOARD_PROFILES", template)
        self.assertIn("profile-executive_brief", template)
        self.assertIn("profile-analyst_workspace", template)
        self.assertIn("profile-operations_monitor", template)
        self.assertIn("renderExecutivePanel", template)
        self.assertIn("renderAnalystPanel", template)
        self.assertIn("renderOperationsPanel", template)
        self.assertNotIn("요약 보고서형", template)
        self.assertNotIn("분석가 작업형", template)
        self.assertNotIn("운영 모니터링형", template)

    def test_dashboard_profile_layout_sanity_warns(self):
        self.qa.WARN.clear()
        self.qa.BLOCK.clear()
        sparse = {
            "meta": {"dashboard_profile": "analyst_workspace"},
            "kpis": [],
            "panels": [{"id": "p1", "charts": [{"id": "c1", "type": "bar", "encoding": {}}]}],
        }
        self.qa.dashboard_profile_checks(sparse, {"dashboard_design": {"selected_profile": "analyst_workspace"}})
        self.assertTrue(any("analyst_workspace" in item for item in self.qa.WARN))

        self.qa.WARN.clear()
        ops = {
            "meta": {"dashboard_profile": "operations_monitor"},
            "kpis": [{"id": "k1", "label": "현재값"}],
            "panels": [{"id": "p1", "charts": [{"id": "c1", "type": "bar", "encoding": {}}]}],
        }
        self.qa.dashboard_profile_checks(ops, {"dashboard_design": {"selected_profile": "operations_monitor"}})
        self.assertTrue(any("operations_monitor" in item for item in self.qa.WARN))

    def test_render_qa_counts_only_chart_card_svgs(self):
        # v4 커밋 3 (Codex H5): KPI 스파크 SVG가 추가돼도 차트 수 검사가
        # 깨지지 않도록 selector를 분리한다.
        template = (KIT_ROOT / "templates" / "dashboard.html").read_text(encoding="utf-8")
        self.assertIn('class="card chart-card', template)
        qa_text = (KIT_ROOT / "qa" / "validate.py").read_text(encoding="utf-8")
        self.assertIn('".panel.active .chart-card svg"', qa_text)
        self.assertNotIn('".panel.active svg"', qa_text)

    def test_validate_does_not_fallback_when_v5_layout_is_missing(self):
        calls = []
        original = self.qa.render_checks
        self.qa.render_checks = lambda *args, **kwargs: calls.append("legacy")
        try:
            self.qa.dispatch_render_checks(
                Path("runs/unit/outputs/dashboard_data.json"),
                minimal_dashboard_data_v5(),
                minimal_chart_spec_v5(),
                None,
                KIT_ROOT / "templates" / "dashboard.html",
            )
        finally:
            self.qa.render_checks = original
        self.assertEqual(calls, [])
        self.assertTrue(any("dashboard_layout" in issue for issue in self.qa.BLOCK))

    def test_validate_dispatches_valid_v5_to_browser_qa_only(self):
        from dashboard_v5.compiler import compile_dashboard

        with tempfile.TemporaryDirectory() as tmp:
            outputs = Path(tmp)
            chart_spec_path = outputs / "chart_spec.json"
            layout_path = outputs / "dashboard_layout.json"
            data_path = outputs / "dashboard_data.json"
            chart_spec = minimal_chart_spec_v5()
            layout = minimal_layout_v5()
            data = minimal_dashboard_data_v5()
            chart_spec_path.write_text(json.dumps(chart_spec), encoding="utf-8")
            layout_path.write_text(json.dumps(layout), encoding="utf-8")
            data_path.write_text(json.dumps(data), encoding="utf-8")
            compile_dashboard(
                chart_spec_path,
                layout_path,
                data_path,
                output_path=outputs / "dashboard.html",
                kit_root=KIT_ROOT,
            )

            legacy_calls = []
            browser_calls = []
            original_render = self.qa.render_checks
            original_browser = self.qa.run_browser_qa
            self.qa.render_checks = lambda *args, **kwargs: legacy_calls.append(True)
            self.qa.run_browser_qa = lambda *args, **kwargs: (
                browser_calls.append(True) or ([], ["browser warning"])
            )
            try:
                self.qa.dispatch_render_checks(
                    data_path,
                    data,
                    chart_spec,
                    layout,
                    KIT_ROOT / "templates" / "dashboard.html",
                )
            finally:
                self.qa.render_checks = original_render
                self.qa.run_browser_qa = original_browser
            self.assertEqual(legacy_calls, [])
            self.assertEqual(browser_calls, [True])
            self.assertIn("browser warning", self.qa.WARN)

    def test_template_static_checks_blocks_profile_label_leak(self):
        self.qa.WARN.clear()
        self.qa.BLOCK.clear()
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "dashboard.html"
            path.write_text("const PROFILE_LABELS = {'executive_brief':'요약 보고서형'};", encoding="utf-8")
            self.qa.template_static_checks(path)
        self.assertTrue(any("PROFILE_LABELS" in item for item in self.qa.BLOCK))

    def test_checkpoint_lineage_blocks_manual_builder_bypass(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            run = root / "runs" / "manual-bypass"
            outputs = run / "outputs"
            outputs.mkdir(parents=True)
            data_path = outputs / "dashboard_data.json"
            data_path.write_text("{}", encoding="utf-8")
            (run / "manifest.json").write_text(
                json.dumps(
                    {
                        "run_id": "manual-bypass",
                        "intake": {
                            "finalization": {"finalized_by": "guided_intake"},
                        },
                        "stages": [
                            {"name": "intake", "status": "complete"},
                            {"name": "connect", "status": "complete"},
                            {"name": "explore", "status": "complete"},
                            {"name": "frame", "status": "complete"},
                            {"name": "analyze", "status": "complete"},
                            {"name": "visualize", "status": "complete"},
                        ],
                    },
                    ensure_ascii=False,
                ),
                encoding="utf-8",
            )
            self.qa.checkpoint_lineage_checks(data_path)
        self.assertTrue(any("checkpoint_answers.json 없음" in item for item in self.qa.BLOCK))

    def test_checkpoint_lineage_allows_explicit_auto_policy(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            run = root / "runs" / "auto-run"
            outputs = run / "outputs"
            input_dir = run / "input"
            outputs.mkdir(parents=True)
            input_dir.mkdir(parents=True)
            data_path = outputs / "dashboard_data.json"
            data_path.write_text("{}", encoding="utf-8")
            (run / "manifest.json").write_text(
                json.dumps({"run_id": "auto-run", "stages": []}, ensure_ascii=False),
                encoding="utf-8",
            )
            (input_dir / "checkpoint_policy.json").write_text(
                json.dumps(
                    {
                        "schema_version": "data-insight-kit.checkpoint_policy.v1",
                        "run_id": "auto-run",
                        "mode": "auto",
                        "explicit_skip": True,
                        "skip_reason": "wrapper invoked with --auto or --no-checkpoints",
                    },
                    ensure_ascii=False,
                ),
                encoding="utf-8",
            )
            self.qa.checkpoint_lineage_checks(data_path)
        self.assertEqual(self.qa.BLOCK, [])

    def test_checkpoint_lineage_accepts_human_confirmed_answers(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            run = root / "runs" / "guided-run"
            outputs = run / "outputs"
            checkpoints = outputs / "checkpoints"
            outputs.mkdir(parents=True)
            checkpoints.mkdir(parents=True)
            data_path = outputs / "dashboard_data.json"
            data_path.write_text("{}", encoding="utf-8")
            (run / "manifest.json").write_text(
                json.dumps({"run_id": "guided-run", "stages": []}, ensure_ascii=False),
                encoding="utf-8",
            )
            answers = []
            question_created = datetime(2026, 7, 9, 0, 0, tzinfo=timezone.utc)
            for idx, (checkpoint_id, prefix) in enumerate(self.qa.CHECKPOINT_PREFIXES.items(), start=1):
                answered_at = question_created + timedelta(minutes=idx)
                question_path = checkpoints / f"{prefix}.json"
                question_payload = {
                    "checkpoint_id": checkpoint_id,
                    "created_at": question_created.isoformat(),
                }
                question_path.write_text(json.dumps(question_payload, ensure_ascii=False), encoding="utf-8")
                (checkpoints / f"{prefix}.md").write_text(
                    f"# {checkpoint_id}\n",
                    encoding="utf-8",
                )
                answers.append(
                    {
                        "answer_id": f"answer-{checkpoint_id}",
                        "checkpoint_id": checkpoint_id,
                        "recorded_by": "scripts/apply_checkpoint_answer.py",
                        "source": "user_chat",
                        "transcript_ref": f"thread:guided-turn-{idx}",
                        "user_response": f"네, {checkpoint_id} 확인 후 진행하세요.",
                        "human_confirmed": True,
                        "approval_contract_version": "checkpoint-answer.v3",
                        "continue_pipeline": True,
                        "answered_at": answered_at.isoformat(),
                        "question_ref": {
                            "path": str(question_path),
                            "sha256": hashlib.sha256(question_path.read_bytes()).hexdigest(),
                            "created_at": question_created.isoformat(),
                            "checkpoint_id": checkpoint_id,
                        },
                    }
                )
            (run / "checkpoint_answers.json").write_text(
                json.dumps({"answers": answers}, ensure_ascii=False),
                encoding="utf-8",
            )
            self.qa.checkpoint_lineage_checks(data_path, post_communicate=True)
        self.assertEqual(self.qa.BLOCK, [])

    def test_checkpoint_lineage_blocks_artifacts_generated_before_approval(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            run = root / "runs" / "order-bypass-run"
            outputs = run / "outputs"
            checkpoints = outputs / "checkpoints"
            outputs.mkdir(parents=True)
            checkpoints.mkdir(parents=True)
            data_path = outputs / "dashboard_data.json"
            data_path.write_text("{}", encoding="utf-8")
            (run / "manifest.json").write_text(
                json.dumps({"run_id": "order-bypass-run", "stages": []}, ensure_ascii=False),
                encoding="utf-8",
            )
            answers = []
            question_created = datetime(2026, 7, 9, 0, 0, tzinfo=timezone.utc)
            for idx, (checkpoint_id, prefix) in enumerate(self.qa.CHECKPOINT_PREFIXES.items(), start=1):
                answered_at = question_created + timedelta(minutes=idx)
                question_path = checkpoints / f"{prefix}.json"
                question_payload = {
                    "checkpoint_id": checkpoint_id,
                    "created_at": question_created.isoformat(),
                }
                question_path.write_text(json.dumps(question_payload, ensure_ascii=False), encoding="utf-8")
                (checkpoints / f"{prefix}.md").write_text(f"# {checkpoint_id}\n", encoding="utf-8")
                answers.append(
                    {
                        "answer_id": f"answer-{checkpoint_id}",
                        "checkpoint_id": checkpoint_id,
                        "recorded_by": "scripts/apply_checkpoint_answer.py",
                        "source": "user_chat",
                        "transcript_ref": f"thread:order-turn-{idx}",
                        "user_response": f"네, {checkpoint_id} 확인 후 진행하세요.",
                        "human_confirmed": True,
                        "approval_contract_version": "checkpoint-answer.v3",
                        "continue_pipeline": True,
                        "answered_at": answered_at.isoformat(),
                        "question_ref": {
                            "path": str(question_path),
                            "sha256": hashlib.sha256(question_path.read_bytes()).hexdigest(),
                            "created_at": question_created.isoformat(),
                            "checkpoint_id": checkpoint_id,
                        },
                    }
                )
            early_ts = (question_created + timedelta(seconds=30)).timestamp()
            os.utime(data_path, (early_ts, early_ts))
            (run / "checkpoint_answers.json").write_text(
                json.dumps({"answers": answers}, ensure_ascii=False),
                encoding="utf-8",
            )
            self.qa.checkpoint_lineage_checks(data_path, post_communicate=True)
        self.assertTrue(any("승인 순서 무효" in item for item in self.qa.BLOCK))
        self.assertTrue(any("generated before checkpoint approval" in item for item in self.qa.BLOCK))

    def test_checkpoint_lineage_blocks_forged_batch_answers(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            run = root / "runs" / "forged-run"
            outputs = run / "outputs"
            checkpoints = outputs / "checkpoints"
            outputs.mkdir(parents=True)
            checkpoints.mkdir(parents=True)
            data_path = outputs / "dashboard_data.json"
            data_path.write_text("{}", encoding="utf-8")
            (run / "manifest.json").write_text(
                json.dumps({"run_id": "forged-run", "stages": []}, ensure_ascii=False),
                encoding="utf-8",
            )
            answers = []
            for checkpoint_id, prefix in self.qa.CHECKPOINT_PREFIXES.items():
                (checkpoints / f"{prefix}.json").write_text(
                    json.dumps(
                        {
                            "checkpoint_id": checkpoint_id,
                            "created_at": "2026-07-09T00:00:00+00:00",
                        },
                        ensure_ascii=False,
                    ),
                    encoding="utf-8",
                )
                (checkpoints / f"{prefix}.md").write_text(f"# {checkpoint_id}\n", encoding="utf-8")
                answers.append(
                    {
                        "checkpoint_id": checkpoint_id,
                        "selected_option_id": "approve",
                        "continue_pipeline": True,
                        "source": "user_chat",
                        "human_confirmed": True,
                        "user_response": "Implement the proposed plan.",
                        "answered_at": "2026-07-09T00:00:00+00:00",
                    }
                )
            (run / "checkpoint_answers.json").write_text(
                json.dumps({"schema_version": "data-insight-kit.checkpoint_answers.v1", "answers": answers}, ensure_ascii=False),
                encoding="utf-8",
            )
            self.qa.checkpoint_lineage_checks(data_path, post_communicate=True)
        self.assertTrue(any("provenance" in item for item in self.qa.BLOCK))
        self.assertTrue(any("일괄 승인" in item for item in self.qa.BLOCK))

    def test_run_context_blocks_prior_run_reference_in_fresh_analysis(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            run = root / "runs" / "fresh-run"
            outputs = run / "outputs"
            input_dir = run / "input"
            outputs.mkdir(parents=True)
            input_dir.mkdir(parents=True)
            data_path = outputs / "dashboard_data.json"
            data = {
                "meta": {"title": "fresh"},
                "sources": [
                    {
                        "id": "old",
                        "type": "file",
                        "ref": "runs/old-run/outputs/dashboard_data.json",
                    }
                ],
            }
            data_path.write_text(json.dumps(data, ensure_ascii=False), encoding="utf-8")
            (run / "manifest.json").write_text(
                json.dumps({"run_id": "fresh-run", "stages": []}, ensure_ascii=False),
                encoding="utf-8",
            )
            (input_dir / "run_context.json").write_text(
                json.dumps(
                    {
                        "schema_version": "data-insight-kit.run_context.v1",
                        "run_id": "fresh-run",
                        "created_at": "2026-07-09T00:00:00+00:00",
                        "mode": "fresh_analysis",
                        "allow_prior_run_reference": False,
                        "reference_runs": [],
                    },
                    ensure_ascii=False,
                ),
                encoding="utf-8",
            )
            self.qa.run_context_checks(data_path, data, chart_spec=None)
        self.assertTrue(any("기존 run 산출물 참조 감지" in item for item in self.qa.BLOCK))

    def test_run_context_allows_declared_prior_reference(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            run = root / "runs" / "compare-run"
            outputs = run / "outputs"
            input_dir = run / "input"
            outputs.mkdir(parents=True)
            input_dir.mkdir(parents=True)
            data_path = outputs / "dashboard_data.json"
            data = {
                "meta": {"title": "compare"},
                "sources": [
                    {
                        "id": "old",
                        "type": "file",
                        "ref": "runs/old-run/outputs/dashboard_data.json",
                    }
                ],
            }
            data_path.write_text(json.dumps(data, ensure_ascii=False), encoding="utf-8")
            (run / "manifest.json").write_text(
                json.dumps({"run_id": "compare-run", "stages": []}, ensure_ascii=False),
                encoding="utf-8",
            )
            (input_dir / "run_context.json").write_text(
                json.dumps(
                    {
                        "schema_version": "data-insight-kit.run_context.v1",
                        "run_id": "compare-run",
                        "created_at": "2026-07-09T00:00:00+00:00",
                        "mode": "compare_with_previous",
                        "allow_prior_run_reference": True,
                        "reference_runs": ["runs/old-run"],
                    },
                    ensure_ascii=False,
                ),
                encoding="utf-8",
            )
            self.qa.run_context_checks(data_path, data, chart_spec=None)
        self.assertEqual(self.qa.BLOCK, [])


class CheckpointHookTests(unittest.TestCase):
    """PreToolUse gate for the Claude Code adapter (scripts/dik_checkpoint_hook.py)."""

    HOOK = KIT_ROOT / "scripts" / "dik_checkpoint_hook.py"

    def _make_kit(self, tmp: Path) -> Path:
        (tmp / "scripts").mkdir()
        (tmp / "docs").mkdir()
        (tmp / "scripts" / "stage_guard.py").write_text("x", encoding="utf-8")
        (tmp / "docs" / "pipeline-contract.md").write_text("x", encoding="utf-8")
        run = tmp / "runs" / "hook-run"
        (run / "outputs" / "checkpoints").mkdir(parents=True)
        return run

    def _valid_answer(self, run: Path, checkpoint_id: str, prefix: str, minute: int) -> dict:
        created = "2026-07-09T00:00:00+00:00"
        qpath = run / "outputs" / "checkpoints" / f"{prefix}.json"
        qpath.write_text(
            json.dumps({"checkpoint_id": checkpoint_id, "created_at": created}, ensure_ascii=False),
            encoding="utf-8",
        )
        rel = f"runs/{run.name}/outputs/checkpoints/{prefix}.json"
        return {
            "answer_id": f"a-{checkpoint_id}",
            "checkpoint_id": checkpoint_id,
            "recorded_by": "scripts/apply_checkpoint_answer.py",
            "source": "user_chat",
            "transcript_ref": f"thread:{checkpoint_id}",
            "user_response": "네, 진행하세요.",
            "human_confirmed": True,
            "approval_contract_version": "checkpoint-answer.v3",
            "continue_pipeline": True,
            "answered_at": f"2026-07-09T00:0{minute}:00+00:00",
            "question_ref": {
                "path": rel,
                "sha256": hashlib.sha256(qpath.read_bytes()).hexdigest(),
                "created_at": created,
                "checkpoint_id": checkpoint_id,
            },
        }

    def _decision(self, payload: dict) -> str:
        result = subprocess.run(
            [sys.executable, str(self.HOOK)],
            input=json.dumps(payload),
            text=True,
            capture_output=True,
            check=False,
        )
        self.assertEqual(result.returncode, 0, result.stderr)
        if not result.stdout.strip():
            return "allow"
        return json.loads(result.stdout)["hookSpecificOutput"]["permissionDecision"]

    def _write(self, tmp: Path, rel_path: str, content: str = "x") -> str:
        return self._decision(
            {"tool_name": "Write", "cwd": str(tmp), "tool_input": {"file_path": rel_path, "content": content}}
        )

    def _bash(self, tmp: Path, command: str) -> str:
        return self._decision(
            {"tool_name": "Bash", "cwd": str(tmp), "tool_input": {"command": command}}
        )

    def test_denies_downstream_artifact_without_checkpoint_approval(self):
        with tempfile.TemporaryDirectory() as t:
            tmp = Path(t)
            self._make_kit(tmp)
            self.assertEqual(self._write(tmp, "runs/hook-run/outputs/04_analysis.md"), "deny")
            self.assertEqual(self._write(tmp, "runs/hook-run/outputs/dashboard_data.json"), "deny")
            self.assertEqual(self._write(tmp, "runs/hook-run/outputs/summary_report.md"), "deny")

    def test_allows_pre_checkpoint_artifacts(self):
        with tempfile.TemporaryDirectory() as t:
            tmp = Path(t)
            self._make_kit(tmp)
            self.assertEqual(self._write(tmp, "runs/hook-run/outputs/01_profile.md"), "allow")
            self.assertEqual(self._write(tmp, "runs/hook-run/outputs/02_eda.md"), "allow")

    def test_allows_downstream_artifact_with_valid_v3_approval(self):
        with tempfile.TemporaryDirectory() as t:
            tmp = Path(t)
            run = self._make_kit(tmp)
            answers = [
                self._valid_answer(run, "data_profile", "01_data_profile_question", 1),
                self._valid_answer(run, "analysis_strategy", "02_analysis_strategy_question", 2),
            ]
            (run / "checkpoint_answers.json").write_text(
                json.dumps({"answers": answers}, ensure_ascii=False), encoding="utf-8"
            )
            self.assertEqual(self._write(tmp, "runs/hook-run/outputs/04_analysis.md"), "allow")

    def test_denies_downstream_when_only_earlier_checkpoint_approved(self):
        with tempfile.TemporaryDirectory() as t:
            tmp = Path(t)
            run = self._make_kit(tmp)
            answers = [self._valid_answer(run, "data_profile", "01_data_profile_question", 1)]
            (run / "checkpoint_answers.json").write_text(
                json.dumps({"answers": answers}, ensure_ascii=False), encoding="utf-8"
            )
            # 03_frame only needs data_profile -> allowed.
            self.assertEqual(self._write(tmp, "runs/hook-run/outputs/03_frame.md"), "allow")
            # 04_analysis also needs analysis_strategy -> denied.
            self.assertEqual(self._write(tmp, "runs/hook-run/outputs/04_analysis.md"), "deny")

    def test_hook_allows_layout_write_only_after_analysis_strategy_approval(self):
        with tempfile.TemporaryDirectory() as t:
            tmp = Path(t)
            run = self._make_kit(tmp)
            target = "runs/hook-run/outputs/dashboard_layout.json"
            self.assertEqual(
                self._write(tmp, target, json.dumps(minimal_layout_v5())), "deny"
            )
            answers = [
                self._valid_answer(run, "data_profile", "01_data_profile_question", 1),
                self._valid_answer(
                    run, "analysis_strategy", "02_analysis_strategy_question", 2
                ),
            ]
            (run / "checkpoint_answers.json").write_text(
                json.dumps({"answers": answers}), encoding="utf-8"
            )
            self.assertEqual(
                self._write(tmp, target, json.dumps(minimal_layout_v5())), "allow"
            )

    def test_hook_denies_v5_dashboard_data_before_storyboard_layout_approval(self):
        with tempfile.TemporaryDirectory() as t:
            tmp = Path(t)
            run = self._make_kit(tmp)
            answers = [
                self._valid_answer(run, "data_profile", "01_data_profile_question", 1),
                self._valid_answer(
                    run, "analysis_strategy", "02_analysis_strategy_question", 2
                ),
            ]
            (run / "checkpoint_answers.json").write_text(
                json.dumps({"answers": answers}), encoding="utf-8"
            )
            self.assertEqual(
                self._write(
                    tmp, "runs/hook-run/outputs/dashboard_data.json", "{}"
                ),
                "deny",
            )

    def test_hook_requires_storyboard_answer_to_lock_current_layout_hash(self):
        with tempfile.TemporaryDirectory() as t:
            tmp = Path(t)
            run = self._make_kit(tmp)
            layout_path = run / "outputs" / "dashboard_layout.json"
            layout_path.write_text(
                json.dumps(minimal_layout_v5()), encoding="utf-8"
            )
            answers = [
                self._valid_answer(run, "data_profile", "01_data_profile_question", 1),
                self._valid_answer(
                    run, "analysis_strategy", "02_analysis_strategy_question", 2
                ),
                self._valid_answer(
                    run, "dashboard_storyboard", "03_dashboard_storyboard_question", 3
                ),
            ]
            answer_path = run / "checkpoint_answers.json"
            answer_path.write_text(
                json.dumps({"answers": answers}), encoding="utf-8"
            )
            target = "runs/hook-run/outputs/dashboard_data.json"
            self.assertEqual(self._write(tmp, target, "{}"), "deny")

            question_path = (
                run
                / "outputs"
                / "checkpoints"
                / "03_dashboard_storyboard_question.json"
            )
            question = json.loads(question_path.read_text())
            question["approval_targets"] = {
                "dashboard_layout": {
                    "path": str(layout_path),
                    "sha256": hashlib.sha256(layout_path.read_bytes()).hexdigest(),
                    "revision": 1,
                    "created_at": "2026-07-14T00:00:00Z",
                }
            }
            question_path.write_text(json.dumps(question), encoding="utf-8")
            answers[-1]["question_ref"]["sha256"] = hashlib.sha256(
                question_path.read_bytes()
            ).hexdigest()
            answer_path.write_text(
                json.dumps({"answers": answers}), encoding="utf-8"
            )
            self.assertEqual(self._write(tmp, target, "{}"), "allow")

    def test_wrapper_contains_v5_compiler_and_layout_qa_arguments(self):
        script = (KIT_ROOT / "scripts" / "run_codex_pipeline.sh").read_text(
            encoding="utf-8"
        )
        self.assertIn("scripts/render_dashboard_v5.py", script)
        self.assertIn('--layout "$RUN/outputs/dashboard_layout.json"', script)
        self.assertIn('--data "$RUN/outputs/dashboard_data.json"', script)

    def test_denies_batch_fabricated_v1_answers(self):
        with tempfile.TemporaryDirectory() as t:
            tmp = Path(t)
            run = self._make_kit(tmp)
            for cp, prefix in (
                ("data_profile", "01_data_profile_question"),
                ("analysis_strategy", "02_analysis_strategy_question"),
            ):
                (run / "outputs" / "checkpoints" / f"{prefix}.json").write_text(
                    json.dumps({"checkpoint_id": cp, "created_at": "2026-07-09T00:00:00+00:00"}),
                    encoding="utf-8",
                )
            # Single Plan approval fanned across checkpoints, no v3 provenance.
            answers = [
                {
                    "checkpoint_id": cp,
                    "selected_option_id": "approve",
                    "continue_pipeline": True,
                    "source": "user_chat",
                    "human_confirmed": True,
                    "user_response": "Implement the proposed plan.",
                    "answered_at": "2026-07-09T00:00:00+00:00",
                }
                for cp in ("data_profile", "analysis_strategy")
            ]
            (run / "checkpoint_answers.json").write_text(
                json.dumps({"schema_version": "data-insight-kit.checkpoint_answers.v1", "answers": answers}),
                encoding="utf-8",
            )
            self.assertEqual(self._write(tmp, "runs/hook-run/outputs/04_analysis.md"), "deny")

    def test_allows_when_explicit_auto_policy(self):
        with tempfile.TemporaryDirectory() as t:
            tmp = Path(t)
            run = self._make_kit(tmp)
            (run / "input").mkdir()
            (run / "input" / "checkpoint_policy.json").write_text(
                json.dumps({"mode": "auto", "explicit_skip": True}), encoding="utf-8"
            )
            self.assertEqual(self._write(tmp, "runs/hook-run/outputs/dashboard_data.json"), "allow")

    def test_denies_run_local_builder_and_output_redirect_in_bash(self):
        with tempfile.TemporaryDirectory() as t:
            tmp = Path(t)
            self._make_kit(tmp)
            self.assertEqual(
                self._bash(tmp, "python3 runs/hook-run/scripts/build_dashboard.py"), "deny"
            )
            self.assertEqual(
                self._bash(tmp, "cat foo > runs/hook-run/outputs/dashboard_data.json"), "deny"
            )

    def test_allows_unrelated_bash(self):
        with tempfile.TemporaryDirectory() as t:
            tmp = Path(t)
            self._make_kit(tmp)
            self.assertEqual(self._bash(tmp, "ls -la && git status"), "allow")
            self.assertEqual(self._bash(tmp, "python3 runs/hook-run/scripts/load_input.py"), "allow")

    def test_allows_read_only_mention_of_gated_path(self):
        # Reading/inspecting a gated artifact is not a write and must not block.
        with tempfile.TemporaryDirectory() as t:
            tmp = Path(t)
            self._make_kit(tmp)
            self.assertEqual(self._bash(tmp, "cat runs/hook-run/outputs/04_analysis.md"), "allow")
            self.assertEqual(self._bash(tmp, "grep foo runs/hook-run/outputs/dashboard_data.json"), "allow")
            self.assertEqual(
                self._bash(tmp, "echo '{\"file_path\":\"runs/hook-run/outputs/04_analysis.md\"}'"),
                "allow",
            )

    def test_denies_internal_terms_in_reader_facing_question_file(self):
        with tempfile.TemporaryDirectory() as t:
            tmp = Path(t)
            self._make_kit(tmp)
            leak = json.dumps({"user_review_brief": {"plain_title": "chart_spec 확인"}}, ensure_ascii=False)
            self.assertEqual(
                self._write(tmp, "runs/hook-run/outputs/checkpoints/01_data_profile_question.json", leak),
                "deny",
            )

    def test_allows_clean_reader_facing_question_file(self):
        with tempfile.TemporaryDirectory() as t:
            tmp = Path(t)
            self._make_kit(tmp)
            clean = json.dumps(
                {
                    "user_review_brief": {
                        "plain_title": "데이터 확인 단계입니다",
                        "what_user_should_review": ["범위와 기간"],
                        "approval_question": "이 범위로 진행할까요?",
                    }
                },
                ensure_ascii=False,
            )
            self.assertEqual(
                self._write(tmp, "runs/hook-run/outputs/checkpoints/01_data_profile_question.json", clean),
                "allow",
            )

    def test_allows_writes_outside_a_kit_run(self):
        with tempfile.TemporaryDirectory() as t:
            tmp = Path(t)
            # No kit markers -> not a kit run.
            (tmp / "runs" / "x" / "outputs").mkdir(parents=True)
            self.assertEqual(self._write(tmp, "runs/x/outputs/04_analysis.md"), "allow")

    def test_fails_open_on_malformed_input(self):
        result = subprocess.run(
            [sys.executable, str(self.HOOK)],
            input="not json",
            text=True,
            capture_output=True,
            check=False,
        )
        self.assertEqual(result.returncode, 0)
        self.assertEqual(result.stdout.strip(), "")

    def _apply_patch(self, tmp: Path, patch: str) -> str:
        return self._decision(
            {"tool_name": "apply_patch", "cwd": str(tmp), "tool_input": {"command": patch}}
        )

    def test_codex_apply_patch_denies_gated_output_without_approval(self):
        with tempfile.TemporaryDirectory() as t:
            tmp = Path(t)
            self._make_kit(tmp)
            patch = (
                "*** Begin Patch\n*** Update File: runs/hook-run/outputs/04_analysis.md\n"
                "@@\n+분석 내용\n*** End Patch"
            )
            self.assertEqual(self._apply_patch(tmp, patch), "deny")

    def test_codex_apply_patch_allows_pre_checkpoint_file(self):
        with tempfile.TemporaryDirectory() as t:
            tmp = Path(t)
            self._make_kit(tmp)
            patch = (
                "*** Begin Patch\n*** Add File: runs/hook-run/outputs/01_profile.md\n"
                "+프로파일\n*** End Patch"
            )
            self.assertEqual(self._apply_patch(tmp, patch), "allow")

    def test_codex_apply_patch_denies_internal_terms_in_question_file(self):
        with tempfile.TemporaryDirectory() as t:
            tmp = Path(t)
            self._make_kit(tmp)
            patch = (
                "*** Begin Patch\n"
                "*** Add File: runs/hook-run/outputs/checkpoints/01_data_profile_question.json\n"
                '+{"user_review_brief": {"plain_title": "chart_spec 확인"}}\n'
                "*** End Patch"
            )
            self.assertEqual(self._apply_patch(tmp, patch), "deny")


class ExternalAdapterUtilsTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.utils = load_module("external_adapter_utils", "scripts/external_adapter_utils.py")

    def test_coverage_audit_and_metric_layer_contracts(self):
        coverage = self.utils.coverage_audit(grain_count=10, matched_count=8, null_count=2)
        self.assertEqual(coverage["match_rate"], 0.8)
        self.assertEqual(coverage["null_rate"], 0.2)

        with self.assertRaises(ValueError):
            self.utils.coverage_audit(grain_count=3, matched_count=4)

        errors = self.utils.validate_adapter_metric_layers(
            {
                "id": "rent_test",
                "category": "rent",
                "fields": [{"name": "sales_like", "metric_layer": "performance"}],
            }
        )
        self.assertEqual(len(errors), 1)
        self.assertIn("category=rent", errors[0])


class WrapperDomainModeFlagTests(unittest.TestCase):
    """--domain-mode 스탬프 통합 검증. guided-intake preflight가 exit 3으로
    멈추므로 codex CLI 없이 write_run_context_policy까지 실행된다."""

    def _run_wrapper(self, run_id: str, *flags: str) -> subprocess.CompletedProcess:
        return subprocess.run(
            ["bash", "scripts/run_codex_pipeline.sh", run_id, "--guided-intake", *flags],
            cwd=KIT_ROOT,
            capture_output=True,
            text=True,
            timeout=120,
        )

    def _read_context(self, run_dir) -> dict:
        return json.loads((run_dir / "input" / "run_context.json").read_text(encoding="utf-8"))

    def test_domain_mode_flag_stamps_run_context_and_survives_resume_without_flag(self):
        run_id = f"unittest-domain-mode-{os.getpid()}"
        run_dir = KIT_ROOT / "runs" / run_id
        self.addCleanup(lambda: shutil.rmtree(run_dir, ignore_errors=True))
        (run_dir / "input").mkdir(parents=True, exist_ok=True)
        (run_dir / "input" / "tiny.csv").write_text("a,b\n1,2\n", encoding="utf-8")

        first = self._run_wrapper(run_id, "--domain-mode")
        self.assertEqual(first.returncode, 3, msg=first.stdout + first.stderr)
        self.assertIs(self._read_context(run_dir).get("domain_mode"), True)

        resumed = self._run_wrapper(run_id)  # 플래그 생략 — sticky 유지 확인
        self.assertEqual(resumed.returncode, 3, msg=resumed.stdout + resumed.stderr)
        self.assertIs(self._read_context(run_dir).get("domain_mode"), True)

    def test_run_without_flag_records_domain_mode_false(self):
        run_id = f"unittest-no-domain-mode-{os.getpid()}"
        run_dir = KIT_ROOT / "runs" / run_id
        self.addCleanup(lambda: shutil.rmtree(run_dir, ignore_errors=True))
        (run_dir / "input").mkdir(parents=True, exist_ok=True)
        (run_dir / "input" / "tiny.csv").write_text("a,b\n1,2\n", encoding="utf-8")

        result = self._run_wrapper(run_id)
        self.assertEqual(result.returncode, 3, msg=result.stdout + result.stderr)
        context = self._read_context(run_dir)
        self.assertIs(context.get("domain_mode"), False)
        schema = json.loads(
            (KIT_ROOT / "schemas" / "run_context.schema.json").read_text(encoding="utf-8")
        )
        jsonschema.Draft202012Validator(schema).validate(context)

    def test_negated_prior_reference_request_stays_fresh(self):
        run_id = f"unittest-fresh-negation-{os.getpid()}"
        run_dir = KIT_ROOT / "runs" / run_id
        self.addCleanup(lambda: shutil.rmtree(run_dir, ignore_errors=True))
        (run_dir / "input").mkdir(parents=True, exist_ok=True)
        (run_dir / "input" / "tiny.csv").write_text("a,b\n1,2\n", encoding="utf-8")
        (run_dir / "user_request.txt").write_text(
            "이전 run의 분석과 보고서는 참조하지 않고 이번 입력부터 새로 분석한다.",
            encoding="utf-8",
        )

        result = self._run_wrapper(run_id)

        self.assertEqual(result.returncode, 3, msg=result.stdout + result.stderr)
        context = self._read_context(run_dir)
        self.assertEqual(context["mode"], "fresh_analysis")
        self.assertIs(context["allow_prior_run_reference"], False)
        self.assertIs(context["user_request_indicates_prior_reference"], False)


if __name__ == "__main__":
    unittest.main()
