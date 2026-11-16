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
        for name in ("report.odt", ".icloud-sync-check", "partial.txt"):
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
        self.buttons = []
        self.real_notify, ics.notify = ics.notify, self.fake_notify
        self.engine = ics.Engine.__new__(ics.Engine)
        self.engine.cfg, self.engine.new_skips = {}, 0
        self.state, self.prev = {}, "ok"

    def fake_notify(self, cfg, title, body, urgent=False, actions=None):
        self.sent.append(title)
        self.buttons.append(actions)

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
        self.assertEqual(self.buttons[-1][0][1], "login", "the sign-in alert offers a button that opens the sign-in window")
        self.assertEqual(self.run_sync("auth"), 1)
        self.assertEqual(self.run_sync("ok"), 2)


FAKE_GDBUS = """#!/bin/sh
# Stands in for gdbus + the desktop's notification server.
here=$(dirname "$0")
case "$1" in
  monitor)
    echo "Monitoring signals on object /org/freedesktop/Notifications owned by :1.42"
    while [ ! -f "$here/sent" ]; do sleep 0.05; done
    echo "/org/freedesktop/Notifications: org.freedesktop.Notifications.ActionInvoked (uint32 6, '0')"
    echo "/org/freedesktop/Notifications: org.freedesktop.Notifications.__REPLY__"
    sleep 30 ;;
  call)
    printf '%s\\n' "$@" > "$here/args"
    echo "(uint32 7,)"
    touch "$here/sent" ;;
esac
"""


class NotificationButtonTests(unittest.TestCase):
    """The helper process shows the notification, waits for a click and runs the matching action."""

    def run_helper(self, reply):
        import argparse
        import json
        bindir = Path(tempfile.mkdtemp(prefix="ics-bin-"))
        (bindir / "gdbus").write_text(FAKE_GDBUS.replace("__REPLY__", reply))
        (bindir / "gdbus").chmod(0o755)
        spec = {"title": "It's here", "body": "line one\nline two", "urgent": False,
                "actions": [["Renew", "login", ""], ["Show", "show", "/tmp/x"]]}
        done = []
        real, ics.run_action = ics.run_action, lambda verb, arg: done.append((verb, arg))
        path, os.environ["PATH"] = os.environ["PATH"], f"{bindir}:{os.environ['PATH']}"
        try:
            started = time.time()
            self.assertEqual(ics.cmd_notify_helper(None, argparse.Namespace(spec=json.dumps(spec))), 0)
            self.assertLess(time.time() - started, 10, "the helper must stop waiting once the notification is answered")
        finally:
            ics.run_action, os.environ["PATH"] = real, path
        return done, (bindir / "args").read_text()

    def test_clicked_button_runs_its_action(self):
        done, _ = self.run_helper("ActionInvoked (uint32 7, '1')")
        self.assertEqual(done, [("show", "/tmp/x")])

    def test_buttons_and_text_reach_the_notification_server(self):
        _, sent = self.run_helper("NotificationClosed (uint32 7, uint32 2)")
        self.assertIn("['0', 'Renew', '1', 'Show']", sent)
        self.assertIn("'It\\'s here'", sent)
        self.assertIn("'line one\\nline two'", sent)

    def test_dismissed_notification_runs_nothing(self):
        done, _ = self.run_helper("NotificationClosed (uint32 7, uint32 2)")
        self.assertEqual(done, [])

    def test_gvariant_quoting(self):
        self.assertEqual(ics.gvariant("a'b\\c\nd"), "'a\\'b\\\\c\\nd'")


class FolderIconTests(unittest.TestCase):
    def test_marker_is_written_and_removed_only_if_ours(self):
        folder = Path(tempfile.mkdtemp(prefix="ics-icon-"))
        ics.mark_folder(folder, True)
        self.assertIn("Icon=folder-cloud", (folder / ".directory").read_text())
        ics.mark_folder(folder, False)
        self.assertFalse((folder / ".directory").exists())
        (folder / ".directory").write_text("[Desktop Entry]\nIcon=my-own-icon\n")
        ics.mark_folder(folder, True)
        ics.mark_folder(folder, False)
        self.assertIn("my-own-icon", (folder / ".directory").read_text(), "a user's own .directory is never touched")

    def test_marker_is_never_synced(self):
        self.assertTrue(ics.exclude_matcher(ics.DEFAULTS["exclude"])(".directory"))


class ConfigProtocolTests(unittest.TestCase):
    """rclone's non-interactive configuration replies, as observed with rclone 1.76."""

    def test_question(self):
        reply = ('{"State": "2fa_do", "Option": {"Name": "config_2fa", "Help": "Two-factor code", '
                 '"IsPassword": false}, "Error": "", "Result": ""}')
        question, problem = ics.parse_config_reply(0, reply, "")
        self.assertEqual((question["state"], question["name"], question["secret"], problem), ("2fa_do", "config_2fa", False, ""))

    def test_finished(self):
        self.assertEqual(ics.parse_config_reply(0, '{"State": "", "Option": null, "Error": "", "Result": ""}', ""), (None, ""))

    def test_fatal_error_is_reported_without_log_noise(self):
        question, problem = ics.parse_config_reply(2, "", '2026/11/16 23:10:54 NOTICE: Fatal error: unknown state "x"\n')
        self.assertIsNone(question)
        self.assertEqual(problem, 'unknown state "x"')

    def test_days_left(self):
        self.assertIsNone(ics.login_days_left({}))
        self.assertEqual(ics.login_days_left({"last_login": time.time() - 5 * 86400}), 24)


FAKE_RCLONE = """#!/bin/sh
# Stands in for rclone + Apple: code 123456 is right, "sms" asks again, anything else is wrong.
echo "$@" >> "$FAKE_RCLONE_LOG"
case "$1 $2" in
  "obscure -") cat > /dev/null; echo OBSCURED-PASSWORD ;;
  "config file") echo "Configuration file is stored at:"; echo "$RCLONE_CONFIG" ;;
  "config update")
    state=; result=; prev=
    for a in "$@"; do
      [ "$prev" = --state ] && state=$a
      [ "$prev" = --result ] && result=$a
      prev=$a
    done
    if [ -z "$state" ] || [ "$result" = sms ]; then
      echo '{"State": "2fa_do", "Option": {"Name": "config_2fa", "Help": "Two-factor authentication", "IsPassword": false}, "Error": "", "Result": ""}'
    elif [ "$result" = 123456 ]; then
      echo '{"State": "", "Option": null, "Error": "", "Result": ""}'
    else
      echo "2026/01/01 10:00:00 NOTICE: Fatal error: failed to validate 2FA code: incorrect code" >&2
      exit 1
    fi ;;
  "lsf "*) echo Documents/; echo a.txt ;;
esac
"""


class QtTestCase(unittest.TestCase):
    def setUp(self):
        try:
            from PyQt6 import QtCore, QtGui, QtWidgets
        except ImportError:
            self.skipTest("PyQt6 not installed")
        os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
        self.QtCore, self.QtGui, self.QtWidgets = QtCore, QtGui, QtWidgets
        self.app = QtWidgets.QApplication.instance() or QtWidgets.QApplication(["test"])
        ics.STATE_DIR.mkdir(parents=True, exist_ok=True)
        for f in (ics.STATE_FILE, ics.PID_FILE, ics.ACTIVITY_FILE, ics.PAUSE_FILE):
            f.unlink(missing_ok=True)

    def wait_for(self, condition, what, timeout=15):
        deadline = time.time() + timeout
        while time.time() < deadline:
            self.app.processEvents()
            if condition():
                return
            time.sleep(0.01)
        self.fail(f"timed out waiting for: {what}")


class LoginDialogTests(QtTestCase):
    def setUp(self):
        super().setUp()
        self.tmp = Path(tempfile.mkdtemp(prefix="ics-login-"))
        self.rclone = self.tmp / "rclone"
        self.rclone.write_text(FAKE_RCLONE)
        self.rclone.chmod(0o755)
        os.environ["FAKE_RCLONE_LOG"] = str(self.tmp / "calls.log")
        os.environ["RCLONE_CONFIG"] = str(self.tmp / "rclone.conf")
        (self.tmp / "rclone.conf").write_text("[icloud]\ntype = iclouddrive\napple_id = me@example.com\npassword = OLD\n")
        self.cfg = dict(ics.DEFAULTS, remote="icloud:")

    def dialog(self, ask_credentials=False):
        dlg = ics.login_dialog(self.QtCore, self.QtWidgets, self.cfg, str(self.rclone), ask_credentials)
        self.addCleanup(dlg.reject)
        if not ask_credentials:
            self.assertEqual(dlg.st["step"], "confirm")
            self.assertFalse((self.tmp / "calls.log").exists(), "Apple must not be contacted before the user confirms")
            dlg.widgets["go"].click()
        return dlg

    def step(self, dlg, name):
        self.wait_for(lambda: dlg.st["step"] == name, f"step {name!r} (now {dlg.st['step']!r})")

    def test_renewal_with_the_right_code(self):
        dlg = self.dialog()
        self.step(dlg, "question")
        self.assertIn("6 cifre", dlg.widgets["info"].text())
        dlg.widgets["answer"].setText(" 123456 ")
        dlg.widgets["go"].click()
        self.step(dlg, "done")
        self.assertTrue(dlg.st["ok"])
        self.assertAlmostEqual(ics.load_state()["last_login"], time.time(), delta=30)
        calls = (self.tmp / "calls.log").read_text()
        self.assertIn("--continue --state 2fa_do --result 123456", calls)
        self.assertIn("lsf icloud:", calls)

    def test_wrong_code_can_be_retried(self):
        dlg = self.dialog()
        self.step(dlg, "question")
        dlg.widgets["answer"].setText("000000")
        dlg.widgets["go"].click()
        self.step(dlg, "failed")
        self.assertIn("incorrect code", dlg.widgets["error"].text())
        self.assertFalse(dlg.st["ok"])
        dlg.widgets["go"].click()  # "Riprova": Apple sends a new code
        self.step(dlg, "question")
        dlg.widgets["answer"].setText("123456")
        dlg.widgets["go"].click()
        self.step(dlg, "done")

    def test_sms_request_asks_for_the_code_again(self):
        dlg = self.dialog()
        self.step(dlg, "question")
        dlg.widgets["answer"].setText("sms")
        dlg.widgets["go"].click()
        self.wait_for(lambda: "--result sms" in (self.tmp / "calls.log").read_text() and dlg.st["step"] == "question",
                      "second question after sms")
        dlg.widgets["answer"].setText("123456")
        dlg.widgets["go"].click()
        self.step(dlg, "done")

    def test_first_login_stores_obscured_credentials_never_on_a_command_line(self):
        dlg = self.dialog(ask_credentials=True)
        self.assertEqual(dlg.st["step"], "credentials")
        dlg.widgets["go"].click()
        self.assertIn("Apple ID", dlg.widgets["error"].text())
        dlg.widgets["apple_id"].setText("new@example.com")
        dlg.widgets["password"].setText("s3cret-pass")
        dlg.widgets["go"].click()
        self.step(dlg, "question")
        conf = (self.tmp / "rclone.conf").read_text()
        self.assertIn("apple_id = new@example.com", conf)
        self.assertIn("password = OBSCURED-PASSWORD", conf)
        self.assertNotIn("s3cret-pass", conf)
        self.assertNotIn("s3cret-pass", (self.tmp / "calls.log").read_text())
        self.assertEqual(dlg.widgets["password"].text(), "")

    def test_missing_rclone_is_reported(self):
        dlg = ics.login_dialog(self.QtCore, self.QtWidgets, self.cfg, str(self.tmp / "no-such-rclone"), False)
        self.addCleanup(dlg.reject)
        dlg.widgets["go"].click()
        self.step(dlg, "failed")


class TrayMenuTests(QtTestCase):
    def setUp(self):
        super().setUp()
        self.menu, self.refresh, _open = ics.build_tray_menu(self.QtCore, self.QtGui, self.QtWidgets,
                                                             dict(ics.DEFAULTS), lambda: None)

    def test_pause_entry_toggles_the_pause_flag(self):
        self.refresh()
        self.assertEqual(self.menu.items["pause"].text(), "Metti in pausa")
        self.menu.items["pause"].trigger()
        self.assertTrue(ics.PAUSE_FILE.exists())
        self.assertIn("Riprendi", self.menu.items["pause"].text())
        self.assertFalse(self.menu.items["sync"].isEnabled())
        self.menu.items["pause"].trigger()
        self.assertFalse(ics.PAUSE_FILE.exists())

    def test_entries_follow_the_state(self):
        ics.save_state({"status": "ok", "last_success": time.time()})
        self.refresh()
        self.assertFalse(self.menu.items["skipped"].isVisible())
        self.assertEqual(self.menu.items["login"].text(), "Rinnova accesso Apple…")
        ics.save_state({"status": "ok", "skipped": {"Shared/": "x", "a.key": "y"}, "last_login": time.time() - 86400 * 3})
        self.refresh()
        self.assertIn("(2)", self.menu.items["skipped"].text())
        self.assertIn("26 giorni", self.menu.items["login"].text())

    def test_windows_show_log_and_skipped_items(self):
        ics.LOG_FILE.write_text("2026-11-16 10:00:00 OK in 3s: 1 copiati\n")
        win = ics.text_window(self.QtWidgets, "log", lambda: ics.log_text(300))
        self.addCleanup(win.close)
        self.assertIn("1 copiati", win.findChild(self.QtWidgets.QPlainTextEdit).toPlainText())
        ics.save_state({"skipped": {"Shared/": "cartella condivisa"}})
        self.assertIn("Shared/", ics.skipped_text())
        self.assertEqual(ics.retry_skipped(), 1)
        self.assertEqual(ics.load_state()["skipped"], {})


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

    def test_paused_daemon_is_shown_as_paused(self):
        ics.PID_FILE.write_text(str(os.getpid()))
        saved, ics.APP = ics.APP, "python"
        try:
            ics.save_state({"status": "ok", "last_success": time.time()})
            ics.PAUSE_FILE.touch()
            self.assertEqual(ics.tray_state()[:2], ("stopped", "In pausa"))
        finally:
            ics.APP = saved
            ics.PAUSE_FILE.unlink(missing_ok=True)

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
