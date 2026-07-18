"""교차검증(Codex)에서 발견된 체크포인트 게이트 우회 2건에 대한 회귀 테스트.

기존 테스트는 정상 경로만 검증해 이 우회를 놓쳤다. 이 파일은 '비정상 경로'
—승인 없이 게이트를 통과시키려는 시도— 가 실제로 차단되는지 검증한다.

H1: manifest.json에 self-signed checkpoint_policy(mode=auto)를 넣어 모든 checkpoint를
    통째로 skip하려는 시도. 정책 정본은 wrapper가 쓰는 input/checkpoint_policy.json
    하나뿐이므로 manifest 자기서명은 무력이어야 한다(stage_guard·qa/validate 공유).
H2: checkpoint_answers.json / input/checkpoint_policy.json 을 직접 write해서 승인·skip을
    위조하려는 시도. dik_checkpoint_hook write-gate가 deny하고, 정상 생산자
    (apply_checkpoint_answer.py, run_codex_pipeline.sh)는 통과해야 한다.
"""
from __future__ import annotations

import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

KIT_ROOT = Path(__file__).resolve().parents[1]
STAGE_GUARD = KIT_ROOT / "scripts" / "stage_guard.py"
HOOK = KIT_ROOT / "scripts" / "dik_checkpoint_hook.py"


class ManifestPolicyFallbackRegression(unittest.TestCase):
    """H1: self-signed checkpoint_policy는 정책 소스로 인정되면 안 된다."""

    def _run_stage_guard(self, root: Path, run_id: str, stage: str):
        return subprocess.run(
            [sys.executable, str(STAGE_GUARD), run_id, stage],
            cwd=root, text=True, capture_output=True, check=False,
        )

    def test_manifest_self_signed_policy_does_not_skip_checkpoints(self):
        with tempfile.TemporaryDirectory() as t:
            root = Path(t)
            run = root / "runs" / "h1-run"
            (run / "input").mkdir(parents=True)
            (run / "outputs" / "checkpoints").mkdir(parents=True)
            # 승인·질문·답변 전무. manifest에만 self-signed auto policy를 주입.
            (run / "manifest.json").write_text(json.dumps(
                {"run_id": "h1-run",
                 "checkpoint_policy": {"mode": "auto", "explicit_skip": True}}))
            result = self._run_stage_guard(root, "h1-run", "frame")
            # 폴백 제거 후에는 승인 부재로 BLOCK(exit 3)이어야 한다(과거엔 exit 0으로 우회).
            self.assertEqual(result.returncode, 3, result.stdout + result.stderr)
            self.assertIn("approved answer missing", result.stdout)

    def test_legit_auto_policy_file_still_skips(self):
        # 정상 --auto 경로(input/checkpoint_policy.json)는 계속 skip해야 한다(과잉 차단 방지).
        with tempfile.TemporaryDirectory() as t:
            root = Path(t)
            run = root / "runs" / "h1-auto"
            (run / "input").mkdir(parents=True)
            (run / "outputs" / "checkpoints").mkdir(parents=True)
            (run / "input" / "checkpoint_policy.json").write_text(json.dumps(
                {"mode": "auto", "explicit_skip": True}))
            result = self._run_stage_guard(root, "h1-auto", "frame")
            # 정책 skip 경로는 exit 0을 조용히 반환한다(성공 메시지는 비-skip 경로 전용).
            self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
            self.assertNotIn("stage guard blocked", result.stdout)

    def test_policy_predicate_ignores_manifest_and_agrees_across_layers(self):
        # 단일 술어(stage_guard.policy_allows_skip)를 qa/validate가 그대로 재사용하는지.
        sys.path.insert(0, str(KIT_ROOT / "scripts"))
        sys.path.insert(0, str(KIT_ROOT))
        import stage_guard  # noqa: PLC0415
        from qa import validate  # noqa: PLC0415

        self.assertIs(validate.policy_allows_skip, stage_guard.policy_allows_skip)
        allow = {"mode": "auto", "explicit_skip": True}
        self.assertTrue(stage_guard.policy_allows_skip(allow))
        # no_checkpoints 관용/None/부분필드는 skip을 허용하지 않는다.
        self.assertFalse(stage_guard.policy_allows_skip({"mode": "no_checkpoints", "explicit_skip": True}))
        self.assertFalse(stage_guard.policy_allows_skip({"mode": "auto"}))
        self.assertFalse(stage_guard.policy_allows_skip(None))
        with tempfile.TemporaryDirectory() as t:
            run = Path(t) / "runs" / "h1-unit"
            run.mkdir(parents=True)
            (run / "manifest.json").write_text(json.dumps(
                {"checkpoint_policy": {"mode": "auto", "explicit_skip": True}}))
            # input/checkpoint_policy.json 없음 → manifest 자기서명만으로는 skip 불가.
            self.assertFalse(stage_guard.checkpoint_policy_allows_skip(run))


class HookForgeryWriteGateRegression(unittest.TestCase):
    """H2: 체크포인트 상태 파일 직접 위조는 hook write-gate가 deny해야 한다."""

    def _make_kit(self, tmp: Path) -> Path:
        (tmp / "scripts").mkdir()
        (tmp / "docs").mkdir()
        (tmp / "scripts" / "stage_guard.py").write_text("x", encoding="utf-8")
        (tmp / "docs" / "pipeline-contract.md").write_text("x", encoding="utf-8")
        run = tmp / "runs" / "hook-run"
        (run / "outputs" / "checkpoints").mkdir(parents=True)
        (run / "input").mkdir(parents=True)
        return run

    def _decision(self, payload: dict) -> str:
        result = subprocess.run(
            [sys.executable, str(HOOK)],
            input=json.dumps(payload), text=True, capture_output=True, check=False,
        )
        self.assertEqual(result.returncode, 0, result.stderr)
        if not result.stdout.strip():
            return "allow"
        return json.loads(result.stdout)["hookSpecificOutput"]["permissionDecision"]

    def _write(self, tmp: Path, rel_path: str, content: str = "{}") -> str:
        return self._decision(
            {"tool_name": "Write", "cwd": str(tmp),
             "tool_input": {"file_path": rel_path, "content": content}})

    def _edit(self, tmp: Path, rel_path: str) -> str:
        return self._decision(
            {"tool_name": "Edit", "cwd": str(tmp), "tool_input": {"file_path": rel_path}})

    def _bash(self, tmp: Path, command: str) -> str:
        return self._decision(
            {"tool_name": "Bash", "cwd": str(tmp), "tool_input": {"command": command}})

    def test_direct_write_checkpoint_answers_denied(self):
        with tempfile.TemporaryDirectory() as t:
            tmp = Path(t)
            self._make_kit(tmp)
            self.assertEqual(self._write(tmp, "runs/hook-run/checkpoint_answers.json"), "deny")
            self.assertEqual(self._write(tmp, "runs/hook-run/input/checkpoint_answers.json"), "deny")

    def test_direct_write_checkpoint_policy_denied(self):
        with tempfile.TemporaryDirectory() as t:
            tmp = Path(t)
            self._make_kit(tmp)
            self.assertEqual(self._write(tmp, "runs/hook-run/input/checkpoint_policy.json"), "deny")

    def test_edit_checkpoint_answers_denied(self):
        with tempfile.TemporaryDirectory() as t:
            tmp = Path(t)
            self._make_kit(tmp)
            self.assertEqual(self._edit(tmp, "runs/hook-run/checkpoint_answers.json"), "deny")

    def test_bash_redirect_into_state_file_denied(self):
        with tempfile.TemporaryDirectory() as t:
            tmp = Path(t)
            self._make_kit(tmp)
            self.assertEqual(
                self._bash(tmp, "echo x > runs/hook-run/checkpoint_answers.json"), "deny")
            self.assertEqual(
                self._bash(tmp, "cp /tmp/a runs/hook-run/input/checkpoint_policy.json"), "deny")

    def test_sanctioned_producers_allowed(self):
        # 정상 생산자는 in-process python write라 리다이렉트로 안 잡혀 통과해야 한다.
        with tempfile.TemporaryDirectory() as t:
            tmp = Path(t)
            self._make_kit(tmp)
            self.assertEqual(
                self._bash(tmp, "python3 scripts/apply_checkpoint_answer.py hook-run "
                                "--source user_chat --user-response yes"), "allow")
            self.assertEqual(
                self._bash(tmp, "bash scripts/run_codex_pipeline.sh hook-run --auto"), "allow")

    def test_unrelated_writes_not_over_blocked(self):
        with tempfile.TemporaryDirectory() as t:
            tmp = Path(t)
            self._make_kit(tmp)
            # 같은 basename이라도 kit run 밖이면 무관.
            self.assertEqual(self._write(tmp, "/tmp/checkpoint_answers.json"), "allow")
            # run 안이라도 보호 대상이 아닌 일반 파일은 통과.
            self.assertEqual(self._write(tmp, "runs/hook-run/input/data.csv"), "allow")


if __name__ == "__main__":
    unittest.main()
