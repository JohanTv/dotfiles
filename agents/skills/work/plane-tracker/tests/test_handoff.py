import io
import os
import subprocess
import sys
import tempfile
import unittest
from contextlib import redirect_stderr

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "scripts"))
import plane  # noqa: E402
from plane_cli import worklog  # noqa: E402

ENV = dict(os.environ, GIT_AUTHOR_NAME="t", GIT_AUTHOR_EMAIL="t@t", GIT_COMMITTER_NAME="t", GIT_COMMITTER_EMAIL="t@t",
           GIT_CONFIG_GLOBAL="/dev/null", GIT_CONFIG_SYSTEM="/dev/null")


def git(cwd, *args):
    return subprocess.run(["git", *args], cwd=cwd, env=ENV, capture_output=True, text=True, check=True).stdout.strip()


class Sanitize(unittest.TestCase):
    def test_remotes(self):
        self.assertEqual(plane.sanitize_remote("git@github.com:Org/repo.git"), "Org/repo")
        self.assertEqual(plane.sanitize_remote("https://github.com/Org/repo.git"), "Org/repo")
        self.assertEqual(plane.sanitize_remote("https://user:tok3n@github.com/Org/repo"), "Org/repo")
        self.assertIsNone(plane.sanitize_remote("https://gitlab.example.com/Org/repo.git"))
        self.assertIsNone(plane.sanitize_remote("no-es-una-url"))


class HandoffRepo(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        root = self.tmp.name
        self.remote = os.path.join(root, "remote.git")
        self.work = os.path.join(root, "work")
        git(root, "init", "-q", "--bare", "-b", "main", self.remote)
        git(root, "clone", "-q", self.remote, self.work)
        git(self.work, "checkout", "-q", "-b", "dev")
        self._commit("a")
        git(self.work, "push", "-q", "-u", "origin", "dev")
        git(self.work, "checkout", "-q", "-b", "feat/OMNIFY-1-x")
        self._commit("b")
        self._cwd = os.getcwd()
        os.chdir(self.work)
        self._env = {k: os.environ.get(k) for k in ENV}
        os.environ.update(ENV)

    def tearDown(self):
        os.chdir(self._cwd)
        for k, v in self._env.items():
            if v is None:
                os.environ.pop(k, None)
            else:
                os.environ[k] = v
        self.tmp.cleanup()

    def _commit(self, name):
        with open(os.path.join(self.work, name), "w") as f:
            f.write(name)
        git(self.work, "add", name)
        git(self.work, "commit", "-q", "-m", name)

    def test_unpushed_commits_block_the_handoff(self):
        with self.assertRaises(plane.HandoffError) as ctx:
            plane.handoff_facts()
        self.assertIn("sin pushear", str(ctx.exception))

    def test_pushed_branch_with_base_and_clean_tree(self):
        git(self.work, "push", "-q", "-u", "origin", "feat/OMNIFY-1-x")
        facts = plane.handoff_facts(base="dev")
        self.assertEqual((facts["branch"], facts["where"], facts["dirty"]), ("feat/OMNIFY-1-x", "origin/feat/OMNIFY-1-x", 0))
        self.assertEqual((facts["base"], facts["ahead_of_base"]), ("dev", 1))
        self.assertEqual(len(facts["sha"]), 40)
        text = plane.format_handoff(facts)
        self.assertEqual(text.count(worklog.PLACEHOLDER), 3)
        self.assertIn("working tree limpio", text)
        self.assertNotIn(self.work, text)  # nunca rutas absolutas

    def test_dirty_tree_is_reported(self):
        git(self.work, "push", "-q", "-u", "origin", "feat/OMNIFY-1-x")
        with open(os.path.join(self.work, "nuevo"), "w") as f:
            f.write("x")
        self.assertEqual(plane.handoff_facts()["dirty"], 1)

    def test_detached_head_and_missing_base(self):
        git(self.work, "push", "-q", "-u", "origin", "feat/OMNIFY-1-x")
        with self.assertRaises(plane.HandoffError) as ctx:
            plane.handoff_facts(base="no-existe")
        self.assertIn("origin/no-existe", str(ctx.exception))
        with self.assertRaises(plane.HandoffError):
            plane.handoff_facts(base="--evil")
        git(self.work, "checkout", "-q", "--detach")
        with self.assertRaises(plane.HandoffError) as ctx:
            plane.handoff_facts()
        self.assertIn("desacoplado", str(ctx.exception))

    def test_no_remote(self):
        git(self.work, "remote", "remove", "origin")
        with self.assertRaises(plane.HandoffError) as ctx:
            plane.handoff_facts()
        self.assertIn("no tiene remoto", str(ctx.exception))


class Placeholders(unittest.TestCase):
    def test_visible_placeholder_is_rejected_hidden_block_is_not(self):
        with redirect_stderr(io.StringIO()), self.assertRaises(SystemExit):
            worklog.reject_placeholders("- **Avance realizado:** [COMPLETAR]")
        worklog.reject_placeholders("Todo listo <!-- PLANE_WORKLOG_METADATA {\"notes\": \"[COMPLETAR]\"} -->")


class Check(unittest.TestCase):
    ROW = {"ticket_id": "OMNIFY-1", "plane_comment_id": "c1", "date": "2026-10-29", "start_time": "09:00", "end_time": "10:00",
           "duration_minutes": 60, "track": "main", "capacity_bucket": "deep_work", "worker_type": "human"}
    META = {"date": "2026-10-29", "start_time": "09:00", "end_time": "10:00", "duration_minutes": 60, "track": "main",
            "capacity_bucket": "deep_work", "worker_type": "human"}

    def run_check(self, rows, comments):
        return worklog.check_worklogs(rows, comments, "2026-10-29", "2026-10-29")

    def test_consistent(self):
        self.assertEqual(self.run_check([self.ROW], {"c1": {"has_block": True, "meta": self.META}}), [])

    def test_mismatch_orphan_duplicate_no_block_missing(self):
        mismatch = self.run_check([dict(self.ROW, duration_minutes=45)], {"c1": {"has_block": True, "meta": self.META}})
        self.assertEqual(mismatch[0]["code"], "mismatch")
        self.assertIn("duration_minutes", mismatch[0]["detail"])
        self.assertEqual(self.run_check([self.ROW], {})[0]["code"], "orphan")
        dup = self.run_check([self.ROW, dict(self.ROW, start_time="09:05")], {"c1": {"has_block": True, "meta": self.META}})
        self.assertIn("duplicate", [i["code"] for i in dup])
        self.assertEqual(self.run_check([self.ROW], {"c1": {"has_block": False, "meta": None}})[0]["code"], "no_block")
        missing = self.run_check([], {"c9": {"has_block": True, "meta": self.META}})
        self.assertEqual(missing[0]["code"], "missing_local")
        self.assertEqual(self.run_check([dict(self.ROW, plane_comment_id=None)], {})[0]["code"], "unlinked")

    def test_missing_local_ignores_other_periods(self):
        old = dict(self.META, date="2026-09-01")
        self.assertEqual(self.run_check([], {"c9": {"has_block": True, "meta": old}}), [])


if __name__ == "__main__":
    unittest.main()
