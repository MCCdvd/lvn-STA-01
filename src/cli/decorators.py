from __future__ import annotations

import functools
import traceback

import click


def cli_error_handler(func):
    @functools.wraps(func)
    def wrapper(*args, **kwargs):
        try:
            return func(*args, **kwargs)
        except Exception as exc:  # noqa: BLE001
            raise click.ClickException(f"{exc}\n{traceback.format_exc()}") from exc

    return wrapper
