from __future__ import annotations

import os
import re
from typing import Optional


_WINDOWS_DRIVE_PATH_RE = re.compile(r"^[a-zA-Z]:[\\/]")
_WINDOWS_UNC_PATH_RE = re.compile(r"^(?:\\\\|//)[^\\/]+[\\/][^\\/]+")
_WINDOWS_ENV_VAR_RE = re.compile(r"%([A-Za-z_][A-Za-z0-9_]*)%")


class PathValidationError(ValueError):
    """Raised when a CLI path option is invalid."""


def _expand_windows_env_vars(path_value: str) -> str:
    def _replace(match: re.Match[str]) -> str:
        variable_name = match.group(1)
        return os.environ.get(variable_name, match.group(0))

    return _WINDOWS_ENV_VAR_RE.sub(_replace, path_value)


def _is_windows_absolute_path(path_value: str) -> bool:
    return bool(_WINDOWS_DRIVE_PATH_RE.match(path_value) or _WINDOWS_UNC_PATH_RE.match(path_value))


def resolve_path(raw_path: str) -> str:
    if raw_path is None:
        raise PathValidationError("Path value is required.")
    value = str(raw_path).strip()
    if not value:
        raise PathValidationError("Path value cannot be empty.")

    expanded = _expand_windows_env_vars(os.path.expandvars(os.path.expanduser(value)))
    if os.path.isabs(expanded) or _is_windows_absolute_path(expanded):
        return os.path.normpath(expanded)
    return os.path.abspath(os.path.normpath(expanded))


def resolve_directory(raw_path: str, option_name: str, must_exist: bool = False, create: bool = False) -> str:
    resolved = resolve_path(raw_path)
    if os.path.exists(resolved) and not os.path.isdir(resolved):
        raise PathValidationError(
            f"{option_name} must point to a directory, but got file path: '{raw_path}' -> '{resolved}'."
        )

    if must_exist and not os.path.isdir(resolved):
        raise PathValidationError(
            f"{option_name} directory does not exist: '{raw_path}' -> '{resolved}'. "
            f"Provide a valid directory path (absolute or relative), for example '.' or '~/data'."
        )

    if create:
        try:
            os.makedirs(resolved, exist_ok=True)
        except OSError as exc:
            raise PathValidationError(
                f"Unable to create {option_name} directory '{resolved}'. "
                "Check path permissions and parent directory."
            ) from exc
    return resolved
