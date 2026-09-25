from __future__ import annotations

import os
import tempfile
import unittest

from validators import PathValidationError, resolve_directory, resolve_path


class PathValidationTests(unittest.TestCase):
    def test_resolve_path_makes_relative_absolute(self) -> None:
        resolved = resolve_path(".")
        self.assertTrue(os.path.isabs(resolved))

    def test_resolve_path_expands_home_and_env_vars(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            os.environ["LVN_TEST_DIR"] = tmp_dir
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


if __name__ == "__main__":
    unittest.main()
