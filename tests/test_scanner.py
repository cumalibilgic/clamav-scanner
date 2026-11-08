import os
import sys
import tempfile
import threading
import time
import unittest
from pathlib import Path
from unittest import mock

import scanner


def _python(code: str) -> list[str]:
    return [sys.executable, "-c", code]


class FindProgramTests(unittest.TestCase):
    def test_finds_program_in_absolute_path_entry(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            program = Path(tmp) / "clamscan.exe"
            program.write_text("")
            env = {"PATH": os.pathsep.join(["", tmp])}
            self.assertEqual(scanner.find_program("clamscan.exe", env), str(program))

    def test_ignores_relative_path_entries_and_current_directory(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            (Path(tmp) / "clamscan.exe").write_text("")
            previous = os.getcwd()
            os.chdir(tmp)
            try:
                env = {"PATH": os.pathsep.join([".", "bin"])}
                self.assertEqual(scanner.find_program("clamscan.exe", env), "")
            finally:
                os.chdir(previous)

    def test_falls_back_to_program_files(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            clamav_dir = Path(tmp) / "ClamAV"
            clamav_dir.mkdir()
            program = clamav_dir / "freshclam.exe"
            program.write_text("")
            env = {"PATH": "", "ProgramFiles": tmp}
            self.assertEqual(scanner.find_program("freshclam.exe", env), str(program))

    def test_returns_empty_string_when_missing(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            env = {"PATH": tmp, "ProgramFiles": tmp, "ProgramFiles(x86)": tmp}
            self.assertEqual(scanner.find_program("clamscan.exe", env), "")


class CommandBuilderTests(unittest.TestCase):
    def test_scan_command_without_quarantine(self) -> None:
        args = scanner.build_scan_command("clamscan.exe", "C:/data")
        self.assertEqual(args, ["clamscan.exe", "--recursive", "--infected", "--no-summary", "C:/data"])

    def test_scan_command_with_quarantine_puts_target_last(self) -> None:
        args = scanner.build_scan_command("clamscan.exe", "C:/data", "C:/quarantine")
        self.assertEqual(
            args,
            ["clamscan.exe", "--recursive", "--infected", "--no-summary", "--move=C:/quarantine", "C:/data"],
        )

    def test_update_command(self) -> None:
        self.assertEqual(scanner.build_update_command("freshclam.exe"), ["freshclam.exe"])


class ButtonStateTests(unittest.TestCase):
    def test_scan_is_blocked_while_busy_even_with_a_path(self) -> None:
        # Gerileme testi: tarama sürerken yeni konum seçmek ikinci taramayı açmamalı.
        self.assertFalse(scanner.can_start_scan(has_path=True, busy=True))

    def test_scan_needs_a_path(self) -> None:
        self.assertFalse(scanner.can_start_scan(has_path=False, busy=False))

    def test_scan_allowed_when_idle_with_path(self) -> None:
        self.assertTrue(scanner.can_start_scan(has_path=True, busy=False))


class SummaryTests(unittest.TestCase):
    def test_scan_codes(self) -> None:
        self.assertIn("tehdit olmadı", scanner.summarize_exit_code(scanner.ACTION_SCAN, 0))
        self.assertIn("en az bir tehdit", scanner.summarize_exit_code(scanner.ACTION_SCAN, 1))
        self.assertIn("kod 2", scanner.summarize_exit_code(scanner.ACTION_SCAN, 2))

    def test_update_codes(self) -> None:
        self.assertIn("tamamlandı", scanner.summarize_exit_code(scanner.ACTION_UPDATE, 0))
        self.assertIn("kod 1", scanner.summarize_exit_code(scanner.ACTION_UPDATE, 1))

    def test_cancelled_overrides_exit_code(self) -> None:
        self.assertIn("iptal", scanner.summarize_exit_code(scanner.ACTION_SCAN, 1, cancelled=True))
        self.assertIn("iptal", scanner.summarize_exit_code(scanner.ACTION_UPDATE, 1, cancelled=True))


class DecodeTests(unittest.TestCase):
    def test_utf8(self) -> None:
        self.assertEqual(scanner.decode_output("şğüöç\n".encode("utf-8")), "şğüöç\n")

    def test_falls_back_to_system_encoding(self) -> None:
        with mock.patch.object(scanner.locale, "getpreferredencoding", return_value="cp1254"):
            self.assertEqual(scanner.decode_output(b"\xfe"), "ş")

    def test_never_raises_on_undecodable_bytes(self) -> None:
        with mock.patch.object(scanner.locale, "getpreferredencoding", return_value="utf-8"):
            self.assertIsInstance(scanner.decode_output(b"\xff\xfe\xfa"), str)

    def test_unknown_system_encoding_does_not_raise(self) -> None:
        with mock.patch.object(scanner.locale, "getpreferredencoding", return_value="no-such-codec"):
            self.assertIsInstance(scanner.decode_output(b"\xff"), str)


class CommandRunnerTests(unittest.TestCase):
    def test_streams_lines_and_returns_exit_code(self) -> None:
        lines: list[str] = []
        result = scanner.CommandRunner().run(_python("print('a'); print('b')"), lines.append)
        self.assertEqual("".join(lines).split(), ["a", "b"])
        self.assertEqual(result, scanner.CommandResult(returncode=0, cancelled=False))

    def test_returns_nonzero_exit_code(self) -> None:
        result = scanner.CommandRunner().run(_python("import sys; sys.exit(1)"), lambda _line: None)
        self.assertEqual(result.returncode, 1)
        self.assertFalse(result.cancelled)

    def test_stderr_is_merged_into_output(self) -> None:
        lines: list[str] = []
        scanner.CommandRunner().run(_python("import sys; sys.stderr.write('oops\\n')"), lines.append)
        self.assertIn("oops", "".join(lines))

    def test_missing_program_raises_oserror_and_runner_stays_usable(self) -> None:
        runner = scanner.CommandRunner()
        with self.assertRaises(OSError):
            runner.run(["this-program-does-not-exist-12345"], lambda _line: None)
        result = runner.run(_python("pass"), lambda _line: None)
        self.assertEqual(result.returncode, 0)
        self.assertFalse(result.cancelled)

    def test_cancel_stops_a_running_command(self) -> None:
        runner = scanner.CommandRunner()
        started = threading.Event()
        results: list[scanner.CommandResult] = []

        def on_line(_line: str) -> None:
            started.set()

        code = "import time; print('start', flush=True); time.sleep(60)"
        worker = threading.Thread(target=lambda: results.append(runner.run(_python(code), on_line)))
        begin = time.monotonic()
        worker.start()
        self.assertTrue(started.wait(timeout=20), "komut başlamadı")
        runner.cancel()
        worker.join(timeout=20)
        self.assertFalse(worker.is_alive(), "iptal sonrası komut durmadı")
        self.assertLess(time.monotonic() - begin, 40)
        self.assertEqual(len(results), 1)
        self.assertTrue(results[0].cancelled)

    def test_cancel_flag_does_not_leak_into_next_run(self) -> None:
        runner = scanner.CommandRunner()
        started = threading.Event()
        worker = threading.Thread(
            target=lambda: runner.run(
                _python("import time; print('x', flush=True); time.sleep(60)"), lambda _l: started.set()
            )
        )
        worker.start()
        self.assertTrue(started.wait(timeout=20))
        runner.cancel()
        worker.join(timeout=20)
        result = runner.run(_python("pass"), lambda _line: None)
        self.assertFalse(result.cancelled)


if __name__ == "__main__":
    unittest.main()
