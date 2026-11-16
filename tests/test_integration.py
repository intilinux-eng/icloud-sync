"""Integration tests: the real program driving a real rclone between two local folders.

"cloud" stands in for iCloud Drive. The iCloud-specific fast lane (folder etags) cannot run
here because the local backend has no folder IDs; everything else is the production code path.
"""
import os
import signal
import subprocess
import sys
import tempfile
import time
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from support import SCRIPT, find_rclone  # noqa: E402

RCLONE = find_rclone()


@unittest.skipUnless(RCLONE, "rclone >= 1.69 not found (run: ./icloud-sync install-rclone)")
class SyncTestCase(unittest.TestCase):
    extra_config = ""

    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp(prefix="ics"))
        if len(str(self.tmp)) > 90:
            self.skipTest("temporary path too long for rclone bisync listing names; set TMPDIR to a short path")
        self.pc, self.cloud = self.tmp / "pc", self.tmp / "cloud"
        for d in (self.pc, self.cloud, self.tmp / "config" / "icloud-sync"):
            d.mkdir(parents=True)
        (self.tmp / "rclone.conf").touch()
        self.env = dict(os.environ, XDG_CONFIG_HOME=str(self.tmp / "config"), XDG_STATE_HOME=str(self.tmp / "state"),
                        XDG_CACHE_HOME=str(self.tmp / "cache"), RCLONE_CONFIG=str(self.tmp / "rclone.conf"),
                        PYTHONDONTWRITEBYTECODE="1")
        self.write_config()

    def write_config(self, **overrides):
        values = {"remote": str(self.cloud), "local": str(self.pc), "rclone_path": RCLONE, "connectivity_host": ""}
        values.update(overrides)
        lines = [f'{k} = "{v}"' for k, v in values.items()]
        lines += ["notifications = false", "remote_check_interval = 1", "poll_interval = 600", "debounce = 1"]
        (self.tmp / "config" / "icloud-sync" / "config.toml").write_text("\n".join(lines) + "\n" + self.extra_config)

    def ics(self, *args):
        return subprocess.run([sys.executable, str(SCRIPT), *args], env=self.env, capture_output=True, text=True, timeout=120)

    def sync(self, *args):
        result = self.ics("sync", *args)
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        return result

    def names(self, root):
        return sorted(str(p.relative_to(root)) for p in root.rglob("*"))

    def assert_in_sync(self):
        self.assertEqual(self.names(self.pc), self.names(self.cloud))


class OneShotTests(SyncTestCase):
    def test_first_sync_merges_both_sides_and_honours_excludes(self):
        (self.pc / "mine.txt").write_text("from the pc")
        (self.pc / ".DS_Store").write_text("junk")
        (self.cloud / "Docs").mkdir()
        (self.cloud / "Docs" / "theirs.txt").write_text("from the cloud")
        (self.cloud / "Empty").mkdir()
        self.sync()
        self.assertEqual((self.pc / "Docs" / "theirs.txt").read_text(), "from the cloud")
        self.assertEqual((self.cloud / "mine.txt").read_text(), "from the pc")
        self.assertTrue((self.pc / "Empty").is_dir(), "empty folders are synced")
        self.assertFalse((self.cloud / ".DS_Store").exists(), "excluded files stay local")
        self.assertTrue((self.pc / "RCLONE_TEST").exists() and (self.cloud / "RCLONE_TEST").exists())
        self.assertEqual(self.ics("status").returncode, 0)

    def test_changes_travel_in_both_directions(self):
        (self.pc / "keep.txt").write_text("1")
        (self.pc / "gone.txt").write_text("1")
        self.sync()
        (self.pc / "new-local.txt").write_text("new")
        (self.cloud / "keep.txt").write_text("changed remotely")
        (self.cloud / "gone.txt").unlink()
        self.sync()
        self.assertEqual((self.pc / "keep.txt").read_text(), "changed remotely")
        self.assertFalse((self.pc / "gone.txt").exists())
        self.assertTrue((self.cloud / "new-local.txt").exists())
        self.assert_in_sync()

    def test_conflict_keeps_both_versions_and_newer_wins_the_name(self):
        (self.pc / "doc.txt").write_text("v0")
        self.sync()
        now = time.time()
        (self.pc / "doc.txt").write_text("pc version")
        os.utime(self.pc / "doc.txt", (now - 60, now - 60))
        (self.cloud / "doc.txt").write_text("cloud version, newer")
        os.utime(self.cloud / "doc.txt", (now, now))
        out = self.sync().stdout
        self.assertIn("conflitt", out)
        self.assertEqual((self.pc / "doc.txt").read_text(), "cloud version, newer")
        losers = [p for p in self.pc.iterdir() if "conflict" in p.name]
        self.assertEqual([p.read_text() for p in losers], ["pc version"])
        self.assert_in_sync()

    def test_mass_deletion_is_blocked_until_forced(self):
        (self.pc / "Docs").mkdir()
        for i in range(12):
            (self.pc / "Docs" / f"f{i}.txt").write_text(str(i))
        self.sync()
        for f in (self.cloud / "Docs").iterdir():
            f.unlink()
        blocked = self.ics("sync")
        self.assertEqual(blocked.returncode, 1)
        self.assertIn("--force", blocked.stdout)
        self.assertEqual(len(list((self.pc / "Docs").iterdir())), 12, "nothing may be deleted while blocked")
        self.sync("--force")
        self.assertEqual(list((self.pc / "Docs").iterdir()), [])

    def test_a_few_deletions_are_never_blocked(self):
        for name in ("a.txt", "b.txt"):
            (self.pc / name).write_text("1")
        self.sync()
        (self.pc / "b.txt").unlink()  # 1 file out of 3 is above the 25% limit, but it is ordinary use
        self.sync()
        self.assertFalse((self.cloud / "b.txt").exists())

    def test_a_side_that_looks_empty_is_never_propagated(self):
        (self.pc / "a.txt").write_text("1")
        self.sync()
        for f in self.cloud.iterdir():
            f.unlink()
        blocked = self.ics("sync")
        self.assertEqual(blocked.returncode, 1)
        self.assertIn("vuoto", blocked.stdout)
        self.assertTrue((self.pc / "a.txt").exists())

    def test_missing_check_file_blocks_the_sync(self):
        (self.pc / "a.txt").write_text("1")
        self.sync()
        (self.pc / "b.txt").write_text("2")
        self.sync()
        (self.cloud / "RCLONE_TEST").rename(self.tmp / "hidden")
        (self.cloud / "a.txt").unlink()
        blocked = self.ics("sync")
        self.assertEqual(blocked.returncode, 1)
        self.assertIn("RCLONE_TEST", blocked.stdout)
        self.assertTrue((self.pc / "a.txt").exists(), "a remote that looks wrong must not delete local files")
        (self.tmp / "hidden").rename(self.cloud / "RCLONE_TEST")
        self.sync()

    def test_lost_bisync_state_is_rebuilt_without_deleting(self):
        (self.pc / "a.txt").write_text("1")
        self.sync()
        for listing in (self.tmp / "cache" / "rclone" / "bisync").glob("*.lst*"):
            listing.unlink()
        (self.cloud / "extra.txt").write_text("2")
        self.sync()
        self.assertTrue((self.pc / "extra.txt").exists() and (self.pc / "a.txt").exists())

    def test_missing_local_folder_is_reported_not_propagated(self):
        (self.pc / "a.txt").write_text("1")
        self.sync()
        self.pc.rename(self.tmp / "unmounted")
        self.assertEqual(self.ics("sync").returncode, 1)
        self.assertTrue((self.cloud / "a.txt").exists())

    def test_dry_run_changes_nothing(self):
        self.sync()
        (self.pc / "preview.txt").write_text("1")
        out = self.sync("--dry-run").stdout
        self.assertIn("preview.txt", out)
        self.assertFalse((self.cloud / "preview.txt").exists())

    def test_changed_excludes_trigger_a_safe_realignment(self):
        (self.pc / "a.txt").write_text("1")
        self.sync()
        self.extra_config = 'exclude = ["*.log"]\n'
        self.write_config()
        (self.pc / "debug.log").write_text("x")
        (self.pc / "b.txt").write_text("2")
        self.sync()
        self.assertTrue((self.cloud / "b.txt").exists())
        self.assertFalse((self.cloud / "debug.log").exists())


class UnsyncableTests(SyncTestCase):
    """Items iCloud lists but will not serve must be excluded instead of failing every run."""

    def test_permanent_download_errors_are_skipped_and_reported(self):
        fake = self.tmp / "fake-rclone"
        fake.write_text(f"""#!/bin/sh
# Real rclone, plus the two permanent iCloud errors until the skip rules show up in the filters file.
if [ "$1" = bisync ]; then
  filters=; log=; prev=
  for a in "$@"; do
    [ "$prev" = --filters-file ] && filters=$a
    [ "$prev" = --log-file ] && log=$a
    prev=$a
  done
  if ! grep -q '^- /Shared/\\*\\*' "$filters" || ! grep -q '^- /Keynote/Deck.key' "$filters"; then
    "{RCLONE}" "$@"
    echo "2026/01/01 10:00:00 ERROR : Shared/a.pdf: Failed to copy: failed to open source object: RootURL not set" >> "$log"
    echo "2026/01/01 10:00:01 ERROR : Keynote/Deck.key.ee0ce831.partial: corrupted on transfer: sizes differ src() 9 vs dst(x) 7" >> "$log"
    echo "2026/01/01 10:00:02 ERROR : Bisync aborted. Must run --resync to recover." >> "$log"
    exit 7
  fi
fi
exec "{RCLONE}" "$@"
""")
        fake.chmod(0o755)
        self.write_config(rclone_path=str(fake))
        (self.cloud / "ok.txt").write_text("fine")
        self.sync()
        listed = self.ics("skipped").stdout
        self.assertIn("Shared/", listed)
        self.assertIn("Keynote/Deck.key", listed)
        self.assertIn("2 elementi", self.ics("status").stdout)
        (self.pc / "later.txt").write_text("1")
        self.sync()
        self.assertTrue((self.cloud / "later.txt").exists())


class DaemonTests(SyncTestCase):
    def wait_for(self, condition, timeout=30):
        deadline = time.time() + timeout
        while time.time() < deadline:
            if condition():
                return True
            time.sleep(0.2)
        return False

    def test_daemon_reacts_to_both_sides_and_stops_cleanly(self):
        (self.cloud / "start.txt").write_text("1")
        daemon = subprocess.Popen([sys.executable, str(SCRIPT), "watch"], env=self.env,
                                  stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True)
        try:
            self.assertTrue(self.wait_for((self.pc / "start.txt").exists), "initial sync")
            (self.pc / "local.txt").write_text("typed on the pc")
            self.assertTrue(self.wait_for((self.cloud / "local.txt").exists), "inotify-triggered upload")
            (self.pc / ".~lock.local.odt#").write_text("temp")
            (self.cloud / "phone.jpg").write_text("photo")
            self.assertTrue(self.wait_for((self.pc / "phone.jpg").exists), "remote change found by the light check")
            (self.cloud / "phone.jpg").unlink()
            self.assertTrue(self.wait_for(lambda: not (self.pc / "phone.jpg").exists()), "remote deletion")
            self.assertFalse((self.cloud / ".~lock.local.odt#").exists(), "temporary files are never uploaded")
        finally:
            daemon.send_signal(signal.SIGTERM)
            out, _ = daemon.communicate(timeout=120)
        self.assertEqual(daemon.returncode, 0, out)
        self.assertIn("Arrestato", out)
        self.assertFalse((self.tmp / "state" / "icloud-sync" / "activity").exists())


if __name__ == "__main__":
    unittest.main()
