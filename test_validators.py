from __future__ import annotations

import os
import tempfile
import unittest
from unittest import mock

from validators import PathValidationError, resolve_directory, resolve_path


class PathValidationTests(unittest.TestCase):
    def test_resolve_path_makes_relative_absolute(self) -> None:
        resolved = resolve_path(".")
        self.assertTrue(os.path.isabs(resolved))

    def test_resolve_path_expands_home_and_env_vars(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            with mock.patch.dict(os.environ, {"LVN_TEST_DIR": tmp_dir}, clear=False):
                env_path = resolve_path("$LVN_TEST_DIR")
                windows_env_path = resolve_path("%LVN_TEST_DIR%")
                self.assertEqual(env_path, os.path.normpath(tmp_dir))
                self.assertEqual(windows_env_path, os.path.normpath(tmp_dir))
            self.assertEqual(resolve_path("~"), os.path.normpath(os.path.expanduser("~")))

    def test_resolve_directory_reports_helpful_error(self) -> None:
        bad_dir = "path_that_does_not_exist_12345"
        with self.assertRaises(PathValidationError) as ctx:
            resolve_directory(bad_dir, "--data-dir", must_exist=True)
        message = str(ctx.exception)
        self.assertIn("--data-dir directory does not exist", message)
        self.assertIn(bad_dir, message)

    def test_resolve_directory_rejects_file_paths(self) -> None:
        with tempfile.NamedTemporaryFile() as tmp_file:
            with self.assertRaises(PathValidationError) as ctx:
                resolve_directory(tmp_file.name, "--data-dir")
            self.assertIn("must point to a directory", str(ctx.exception))

    def test_resolve_path_keeps_windows_absolute_forms(self) -> None:
        drive_path = r"C:\Users\tester\data"
        unc_backslash = r"\\server\share\data"
        unc_forward = "//server/share/data"
        if os.name == "nt":
            self.assertEqual(resolve_path(drive_path), os.path.normpath(drive_path))
            self.assertEqual(resolve_path(unc_backslash), os.path.normpath(unc_backslash))
        else:
            self.assertEqual(resolve_path(drive_path), os.path.abspath(os.path.normpath(drive_path)))
            self.assertEqual(resolve_path(unc_backslash), os.path.abspath(os.path.normpath(unc_backslash)))
        self.assertEqual(resolve_path(unc_forward), os.path.normpath(unc_forward))

    def test_resolve_directory_windows_absolute_must_exist_validation(self) -> None:
        drive_path = r"C:\Users\tester\data"
        normalized = os.path.normpath(drive_path)
        with mock.patch("validators.os.name", "nt"):
            with mock.patch("os.path.exists", return_value=True), mock.patch("os.path.isdir", return_value=True):
                self.assertEqual(resolve_directory(drive_path, "--data-dir", must_exist=True), normalized)

            with mock.patch("os.path.exists", return_value=False), mock.patch("os.path.isdir", return_value=False):
                with self.assertRaises(PathValidationError):
                    resolve_directory(drive_path, "--data-dir", must_exist=True)

    def test_resolve_directory_rejects_conflicting_flags(self) -> None:
        with self.assertRaises(PathValidationError):
            resolve_directory(".", "--data-dir", must_exist=True, create=True)


if __name__ == "__main__":
    unittest.main()
