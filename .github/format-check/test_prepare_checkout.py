"""Exercise the format check's Git base selection with real commits."""

import os
import subprocess
import tempfile
import unittest
from pathlib import Path


SCRIPT = Path(__file__).with_name("prepare_checkout.sh")


class PrepareCheckoutTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.repo = Path(self.temp.name)
        self.git("init", "-q", "-b", "main")
        self.git("config", "user.name", "Test")
        self.git("config", "user.email", "test@example.com")
        self.write("MAINTAINERS", "maintainer\n")
        self.git("add", ".")
        self.git("commit", "-qm", "initial")
        self.original_base = self.git("rev-parse", "HEAD")
        self.git("checkout", "-qb", "contributor")
        self.write("community/new/SKILL.md", "skill\n")
        self.git("add", ".")
        self.git("commit", "-qm", "skill")
        self.head = self.git("rev-parse", "HEAD")
        self.git("checkout", "-q", "main")
        self.write("MAINTAINERS", "maintainer\nnew-reviewer\n")
        self.write(".github/workflows/other.yml", "name: trusted\n")
        self.git("add", ".")
        self.git("commit", "-qm", "main advances")
        self.current_base = self.git("rev-parse", "HEAD")
        self.git("update-ref", "refs/remotes/origin/main", self.current_base)
        self.git("update-ref", "refs/pull/73/head", self.head)

    def tearDown(self):
        self.temp.cleanup()

    def git(self, *args):
        return subprocess.check_output(["git", *args], cwd=self.repo, text=True).strip()

    def write(self, name, content):
        path = self.repo / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(content)

    def prepare(self, event="pull_request_target", head=None, pr="73"):
        return subprocess.run(
            ["bash", str(SCRIPT), event, head or self.head, pr], cwd=self.repo,
            capture_output=True, text=True, env={**os.environ, "GIT_CONFIG_GLOBAL": os.devnull},
        )

    def test_pr_uses_current_main_and_not_stale_event_base(self):
        result = self.prepare()

        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(result.stdout.strip(), self.current_base)
        self.assertEqual(self.git("diff", "--name-only", f"{result.stdout.strip()}...HEAD"),
                         "community/new/SKILL.md")
        self.assertEqual(self.git("show", f"{result.stdout.strip()}:MAINTAINERS"),
                         "maintainer\nnew-reviewer")

    def test_pr_rejects_wrong_head_even_if_merge_is_possible(self):
        result = self.prepare(head=self.original_base)

        self.assertNotEqual(result.returncode, 0)

    def test_pr_rejects_untrusted_checkout_base(self):
        self.git("checkout", "-qb", "untrusted", self.original_base)
        result = self.prepare()

        self.assertNotEqual(result.returncode, 0)

    def test_pr_uses_trusted_checker_even_when_contributor_changes_it(self):
        self.git("checkout", "-q", "contributor")
        self.write(".github/format-check/format_check.py", "print('bypass')\n")
        self.git("add", ".")
        self.git("commit", "-qm", "replace checker")
        head = self.git("rev-parse", "HEAD")
        self.git("checkout", "-q", "main")
        self.git("reset", "-q", "--hard", "HEAD")
        self.git("update-ref", "refs/pull/73/head", head)
        result = self.prepare(head=head)

        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertFalse((self.repo / ".github/format-check/format_check.py").exists())
        self.assertIn(".github/format-check/format_check.py",
                      self.git("diff", "--name-only", f"{self.current_base}...HEAD"))

    def test_dispatch_builds_checked_merge_on_current_main(self):
        result = self.prepare(event="workflow_dispatch")

        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(result.stdout.strip(), self.current_base)
        self.assertEqual(self.git("rev-parse", "HEAD^2"), self.head)
        self.assertEqual(self.git("diff", "--name-only", f"{result.stdout.strip()}...HEAD"),
                         "community/new/SKILL.md")

    def test_dispatch_uses_trusted_checker_even_when_contributor_changes_it(self):
        self.git("checkout", "-q", "contributor")
        self.write(".github/format-check/format_check.py", "print('bypass')\n")
        self.git("add", ".")
        self.git("commit", "-qm", "replace checker")
        head = self.git("rev-parse", "HEAD")
        self.git("update-ref", "refs/pull/73/head", head)
        self.git("checkout", "-q", "main")
        self.git("reset", "-q", "--hard", "HEAD")

        result = self.prepare(event="workflow_dispatch", head=head)

        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertFalse((self.repo / ".github/format-check/format_check.py").exists())
        self.assertIn(".github/format-check/format_check.py",
                      self.git("diff", "--name-only", f"{self.current_base}...HEAD"))

    def test_dispatch_rejects_branch_that_is_not_pr_head(self):
        result = self.prepare(event="workflow_dispatch", head=self.original_base)

        self.assertNotEqual(result.returncode, 0)

    def test_dispatch_rejects_conflicts_instead_of_scanning_partial_merge(self):
        self.git("checkout", "-q", "contributor")
        self.write("MAINTAINERS", "attacker\n")
        self.git("add", ".")
        self.git("commit", "-qm", "conflict with main")
        head = self.git("rev-parse", "HEAD")
        self.git("update-ref", "refs/pull/73/head", head)
        self.git("checkout", "-q", "main")
        result = self.prepare(event="workflow_dispatch", head=head)

        self.assertNotEqual(result.returncode, 0)
        self.assertEqual(self.git("rev-parse", "HEAD"), self.current_base)

    def test_pr_head_is_verified_against_fetched_ref(self):
        self.git("update-ref", "refs/pull/73/head", self.head)
        result = self.prepare(head=self.original_base)

        self.assertNotEqual(result.returncode, 0)


if __name__ == "__main__":
    unittest.main()
