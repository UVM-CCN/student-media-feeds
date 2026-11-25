import os
import subprocess
import tempfile
import textwrap
import unittest
from pathlib import Path


WORKFLOW = Path(__file__).resolve().parents[1] / ".github/workflows/capture-feeds.yml"


class CapturePushTests(unittest.TestCase):
    def run_commit_step(self, push_failures=0, changed=True, commit_fails=False):
        workflow = WORKFLOW.read_text(encoding="utf-8")
        step = workflow.split("      - name: Commit newly captured stories\n        run: |\n", 1)[1]
        script = textwrap.dedent(step)

        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            git = root / "git"
            git.write_text(textwrap.dedent("""\
                #!/bin/bash
                echo "$1" >> "$CALLS"
                case "$1" in
                  diff) [ "$CHANGED" = 0 ] ;;
                  commit) [ "$COMMIT_FAILS" = 0 ] ;;
                  push)
                    count=$(grep -c '^push$' "$CALLS")
                    [ "$count" -gt "$PUSH_FAILURES" ]
                    ;;
                esac
            """), encoding="utf-8")
            git.chmod(0o755)
            sleep = root / "sleep"
            sleep.write_text('#!/bin/bash\necho "sleep $1" >> "$CALLS"\n', encoding="utf-8")
            sleep.chmod(0o755)
            calls = root / "calls"
            env = dict(os.environ, PATH=f"{root}:{os.environ['PATH']}", CALLS=str(calls),
                       CHANGED=str(int(changed)), COMMIT_FAILS=str(int(commit_fails)),
                       PUSH_FAILURES=str(push_failures))
            result = subprocess.run(["bash", "-e", "-c", script], env=env,
                                    capture_output=True, text=True)
            return result, calls.read_text(encoding="utf-8").splitlines()

    def test_no_changes_does_not_commit_or_push(self):
        result, calls = self.run_commit_step(changed=False)
        self.assertEqual(result.returncode, 0)
        self.assertNotIn("commit", calls)
        self.assertNotIn("push", calls)

    def test_successful_push_is_not_retried(self):
        result, calls = self.run_commit_step()
        self.assertEqual(result.returncode, 0)
        self.assertEqual(calls.count("commit"), 1)
        self.assertEqual(calls.count("push"), 1)
        self.assertFalse(any(call.startswith("sleep ") for call in calls))

    def test_transient_push_failures_retry_same_commit(self):
        result, calls = self.run_commit_step(push_failures=2)
        self.assertEqual(result.returncode, 0)
        self.assertEqual(calls.count("commit"), 1)
        self.assertEqual(calls.count("push"), 3)
        self.assertEqual([call for call in calls if call.startswith("sleep ")],
                         ["sleep 10", "sleep 20"])

    def test_persistent_push_failure_fails_after_four_attempts(self):
        result, calls = self.run_commit_step(push_failures=4)
        self.assertNotEqual(result.returncode, 0)
        self.assertEqual(calls.count("push"), 4)
        self.assertEqual([call for call in calls if call.startswith("sleep ")],
                         ["sleep 10", "sleep 20", "sleep 40"])

    def test_commit_failure_does_not_push(self):
        result, calls = self.run_commit_step(commit_fails=True)
        self.assertNotEqual(result.returncode, 0)
        self.assertNotIn("push", calls)


if __name__ == "__main__":
    unittest.main()
