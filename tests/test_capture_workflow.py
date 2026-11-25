import os
import subprocess
import tempfile
import textwrap
import unittest
from pathlib import Path


WORKFLOW = Path(__file__).resolve().parents[1] / ".github/workflows/capture-feeds.yml"


class CaptureWorkflowTests(unittest.TestCase):
    def run_commit_step(self, *, changed=True, push_failures=0, commit_fails=False):
        workflow = WORKFLOW.read_text(encoding="utf-8")
        script = textwrap.dedent(workflow.split(
            "      - name: Commit newly captured stories\n        run: |\n", 1
        )[1])
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            git = root / "git"
            git.write_text(
                "#!/bin/bash\n"
                "echo \"$1\" >> \"$CALLS\"\n"
                "case \"$1\" in\n"
                "  diff) if [ \"$2\" = --staged ] && [ \"$CHANGED\" = 1 ]; then exit 1; fi ;;\n"
                "  commit) if [ \"$COMMIT_FAILS\" = 1 ]; then exit 1; fi ;;\n"
                "  push) n=$(grep -c '^push$' \"$CALLS\"); "
                "if [ \"$n\" -le \"$PUSH_FAILURES\" ]; then exit 1; fi ;;\n"
                "esac\n",
                encoding="utf-8",
            )
            git.chmod(0o755)
            sleep = root / "sleep"
            sleep.write_text('#!/bin/bash\necho "sleep $1" >> "$CALLS"\n', encoding="utf-8")
            sleep.chmod(0o755)
            env = dict(os.environ, PATH=f"{root}:{os.environ['PATH']}",
                       CALLS=str(root / "calls"), CHANGED=str(int(changed)),
                       PUSH_FAILURES=str(push_failures), COMMIT_FAILS=str(int(commit_fails)))
            result = subprocess.run(["bash", "-e", "-c", script], cwd=root,
                                    env=env, capture_output=True, text=True)
            calls = (root / "calls").read_text(encoding="utf-8").splitlines()
        return result, calls

    def test_retries_transient_push_failures(self):
        result, calls = self.run_commit_step(push_failures=2)
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(calls.count("commit"), 1)
        self.assertEqual(calls.count("push"), 3)
        self.assertEqual([call for call in calls if call.startswith("sleep")],
                         ["sleep 10", "sleep 20"])

    def test_persistent_push_failure_fails_the_step(self):
        result, calls = self.run_commit_step(push_failures=3)
        self.assertNotEqual(result.returncode, 0)
        self.assertEqual(calls.count("push"), 3)
        self.assertIn("Push failed after 3 attempts.", result.stdout)

    def test_no_changes_does_not_commit_or_push(self):
        result, calls = self.run_commit_step(changed=False)
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertNotIn("commit", calls)
        self.assertNotIn("push", calls)

    def test_failed_commit_is_not_pushed(self):
        result, calls = self.run_commit_step(commit_fails=True)
        self.assertNotEqual(result.returncode, 0)
        self.assertNotIn("push", calls)


if __name__ == "__main__":
    unittest.main()
