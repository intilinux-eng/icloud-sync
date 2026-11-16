# SPDX-License-Identifier: MIT
"""Unit tests: no network, no rclone."""
import os
import sys
import tempfile
import time
import unittest
from pathlib import Path

_SANDBOX = tempfile.mkdtemp(prefix="ics-unit-")
os.environ["XDG_CONFIG_HOME"] = f"{_SANDBOX}/config"
os.environ["XDG_STATE_HOME"] = f"{_SANDBOX}/state"
os.environ["XDG_CACHE_HOME"] = f"{_SANDBOX}/cache"

sys.path.insert(0, str(Path(__file__).resolve().parent))
from support import ROOT, load_program  # noqa: E402

ics = load_program()


class ConfigTests(unittest.TestCase):
    def test_written_config_reads_back_identical(self):
        ics.write_config(dict(ics.DEFAULTS))
        self.assertEqual(ics.load_config(), ics.DEFAULTS)

    def test_every_option_is_documented(self):
        self.assertEqual(set(ics.DEFAULTS), set(ics.CONFIG_HELP))

    def test_filters_cover_excludes_and_escape_skipped_paths(self):
        text = ics.filters_text([".DS_Store", ".Trash-*/"], {"Shared [1]/": "x", "Keynote/a*.key": "y"})
        self.assertIn("- .DS_Store\n", text)
        self.assertIn("- .Trash-*/**\n", text)
        self.assertIn("- /Shared \\[1\\]/**\n", text)
        self.assertIn("- /Keynote/a\\*.key\n", text)

    def test_exclude_matcher_works_on_names(self):
        excluded = ics.exclude_matcher(ics.DEFAULTS["exclude"])
        for name in (".DS_Store", ".~lock.report.odt#", "movie.mp4.part", "x.3f9a1c22.partial", ".Trash-1000"):
            self.assertTrue(excluded(name), name)
        for name in ("report.odt", "RCLONE_TEST", "partial.txt"):
            self.assertFalse(excluded(name), name)


class RcloneConfTests(unittest.TestCase):
    def test_section_is_updated_in_place_and_others_are_untouched(self):
        conf = Path(_SANDBOX) / "rclone.conf"
        conf.write_text("[gdrive]\ntype = drive\ntoken = abc\n\n[icloud]\ntype = iclouddrive\napple_id = old\n"
                        "cookies = zzz\ntrust_token = ttt\n\n[other]\ntype = s3\n")
        ics.rclone_conf_set(conf, "icloud", {"apple_id": "new@example.com", "password": "OBS",
                                             "cookies": None, "trust_token": None})
        ics.rclone_conf_set(conf, "fresh", {"type": "iclouddrive", "apple_id": "a@example.com"})
        text = conf.read_text()
        self.assertIn("[gdrive]\ntype = drive\ntoken = abc\n", text)
        self.assertIn("[icloud]\ntype = iclouddrive\napple_id = new@example.com\npassword = OBS\n", text)
        self.assertNotIn("cookies", text)
        self.assertNotIn("trust_token", text)
        self.assertIn("[other]\ntype = s3\n", text)
        self.assertIn("[fresh]\ntype = iclouddrive\napple_id = a@example.com\n", text)
        self.assertEqual(conf.stat().st_mode & 0o777, 0o600)

    def test_encrypted_config_is_refused(self):
        conf = Path(_SANDBOX) / "encrypted.conf"
        conf.write_text("# Encrypted rclone configuration File\n\nRCLONE_ENCRYPT_V0:\nabc\n")
        with self.assertRaises(RuntimeError):
            ics.rclone_conf_set(conf, "icloud", {"type": "iclouddrive"})


class LogParsingTests(unittest.TestCase):
    def classify(self, rc, text):
        return ics.Engine.classify(ics.Engine.__new__(ics.Engine), rc, text)

    def test_counts(self):
        counts = ics.parse_counts("INFO  : a.txt: Copied (new)\nINFO  : b: Copied (replaced existing)\n"
                                  "INFO  : c.txt: Deleted\n")
        self.assertEqual((counts["copied"], counts["deleted"]), (2, 1))

    def test_apple_login_errors_are_recognised(self):
        for text in ("ERROR : Failed to create file system: trust token expired, please reauth",
                     "ERROR : x: HTTP error 423 (423 Locked) Missing PCS cookies from the request"):
            self.assertEqual(self.classify(1, text).status, "auth", text)

    def test_other_failures(self):
        self.assertEqual(self.classify(0, "").status, "ok")
        self.assertEqual(self.classify(1, "ERROR : Safety abort: too many deletes (>25%)").status, "deletes")
        self.assertEqual(self.classify(7, "ERROR : Bisync aborted. Must run --resync to recover.").status, "resync-needed")
        self.assertEqual(self.classify(7, "ERROR : Bisync critical error: cannot find prior Path1 or Path2 listings").status,
                         "resync-needed")
        self.assertEqual(self.classify(7, "ERROR : Empty current Path2 listing. Cannot sync to an empty directory").status,
                         "empty")
        self.assertEqual(self.classify(7, "ERROR : Bisync aborted. Error is retryable without --resync").status, "error")
        self.assertEqual(self.classify(1, "ERROR : disk full").status, "error")

    def test_unsyncable_items(self):
        log = ("2026/11/12 18:08:30 ERROR : Keynote/Deck.key.ee0ce831.partial: corrupted on transfer: sizes differ "
               "src() 449701 vs dst(Local file system at /x) 368814\n"
               "2026/11/12 18:09:30 ERROR : Shared/Sub/a.pdf: Failed to copy: failed to open source object: RootURL not set\n"
               "2026/11/12 18:09:30 ERROR : top.pdf: Failed to copy: failed to open source object: RootURL not set\n")
        self.assertEqual(set(ics.find_unsyncable(log)), {"Keynote/Deck.key", "Shared/Sub/", "top.pdf"})

    def test_remote_helpers(self):
        self.assertEqual(ics.remote_join("icloud:", "f"), "icloud:f")
        self.assertEqual(ics.remote_join("icloud:Docs", "f"), "icloud:Docs/f")
        self.assertEqual(ics.remote_name("icloud:Docs"), "icloud")
        self.assertIsNone(ics.remote_name("/tmp/x"))


@unittest.skipUnless(sys.platform.startswith("linux"), "inotify is Linux-only")
class WatcherTests(unittest.TestCase):
    def test_recursive_watch_follows_new_and_moved_folders(self):
        root = Path(tempfile.mkdtemp(prefix="ics-watch-"))
        (root / "sub").mkdir()
        w = ics.Watcher(root, ics.exclude_matcher(ics.DEFAULTS["exclude"]))
        self.assertFalse(w.poll())
        (root / "a.txt").write_text("x")
        self.assertTrue(w.poll(), "file creation")
        (root / ".~lock.a.odt#").write_text("x")
        (root / "x.tmp").write_text("x")
        self.assertFalse(w.poll(), "excluded names must not trigger a sync")
        (root / "sub/new/deep").mkdir(parents=True)
        self.assertTrue(w.poll())
        (root / "sub/new/deep/f").write_text("1")
        self.assertTrue(w.poll(), "folder created after start is watched")
        os.rename(root / "sub/new", root / "moved")
        self.assertTrue(w.poll())
        (root / "moved/deep/g").write_text("1")
        self.assertTrue(w.poll(), "moved folder is still watched")
        os.remove(root / "a.txt")
        self.assertTrue(w.poll(), "deletion")


class NotificationTests(unittest.TestCase):
    """A passing error must not alarm the user; a persistent one must, exactly once."""

    def setUp(self):
        self.sent = []
        self.real_notify, ics.notify = ics.notify, lambda cfg, title, body, urgent=False: self.sent.append(title)
        self.engine = ics.Engine.__new__(ics.Engine)
        self.engine.cfg, self.engine.new_skips = {}, 0
        self.state, self.prev = {}, "ok"

    def tearDown(self):
        ics.notify = self.real_notify

    def run_sync(self, status):
        self.engine.announce(self.prev, ics.Result(status, "details"), self.state)
        self.prev = status
        return len(self.sent)

    def test_single_error_then_recovery_is_silent(self):
        self.assertEqual(self.run_sync("error"), 0)
        self.assertEqual(self.run_sync("ok"), 0)

    def test_repeated_error_alerts_once_and_recovery_is_announced(self):
        self.assertEqual(self.run_sync("error"), 0)
        self.assertEqual(self.run_sync("error"), 1)
        self.assertEqual(self.run_sync("error"), 1)
        self.assertEqual(self.run_sync("ok"), 2)
        self.assertIn("iCloud Drive", self.sent[-1])

    def test_problems_that_need_the_user_alert_immediately(self):
        self.assertEqual(self.run_sync("auth"), 1)
        self.assertEqual(self.run_sync("auth"), 1)
        self.assertEqual(self.run_sync("ok"), 2)


class PackagingTests(unittest.TestCase):
    def test_packaged_unit_matches_the_generated_one(self):
        expected = ics.UNIT_TEMPLATE.format(homepage=ics.HOMEPAGE, exec="/usr/bin/icloud-sync")
        self.assertEqual((ROOT / "data/icloud-sync.service").read_text(), expected)

    def test_changelog_documents_the_current_version(self):
        self.assertIn(f"## {ics.VERSION}", (ROOT / "CHANGELOG.md").read_text())


class TrayTests(unittest.TestCase):
    def setUp(self):
        ics.STATE_DIR.mkdir(parents=True, exist_ok=True)
        for f in (ics.STATE_FILE, ics.PID_FILE, ics.ACTIVITY_FILE):
            f.unlink(missing_ok=True)

    def test_state_without_daemon_is_stopped(self):
        ics.save_state({"status": "ok", "last_success": time.time()})
        self.assertEqual(ics.tray_state()[0], "stopped")

    def test_state_follows_daemon_status_and_activity(self):
        ics.PID_FILE.write_text(str(os.getpid()))
        saved, ics.APP = ics.APP, "python"  # our own cmdline stands in for the daemon's
        try:
            ics.save_state({"status": "ok", "last_success": time.time()})
            self.assertEqual(ics.tray_state()[0], "ok")
            ics.save_state({"status": "error", "error_streak": 1})
            self.assertEqual(ics.tray_state()[0], "offline", "a first, probably passing error is not shown in red")
            ics.save_state({"status": "error", "error_streak": 2})
            self.assertEqual(ics.tray_state()[0], "error")
            ics.save_state({"status": "auth", "message": "trust token expired"})
            kind, _text, hint = ics.tray_state()
            self.assertEqual(kind, "error")
            self.assertIn("login", hint)
            with ics.activity():
                self.assertEqual(ics.tray_state()[0], "sync")
            self.assertEqual(ics.tray_state()[0], "error")
        finally:
            ics.APP = saved

    def test_icons_render_for_every_state(self):
        try:
            from PyQt6 import QtCore, QtGui, QtWidgets
        except ImportError:
            self.skipTest("PyQt6 not installed")
        os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
        app = QtWidgets.QApplication.instance() or QtWidgets.QApplication(["test"])
        self.assertIsNotNone(app)  # a QApplication must exist before any pixmap is created
        images = {}
        for kind in ("ok", "sync", "error", "offline", "stopped", "unknown"):
            pm = ics.tray_pixmap(QtCore, QtGui, kind, 32)
            self.assertEqual((pm.width(), pm.height()), (32, 32))
            image = pm.toImage()
            images[kind] = bytes(image.constBits().asarray(image.sizeInBytes()))
        self.assertEqual(len(set(images.values())), len(images), "every state must look different")


if __name__ == "__main__":
    unittest.main()
