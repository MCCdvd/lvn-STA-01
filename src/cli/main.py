from __future__ import annotations

import click

from src.cli import commands
from src.cli.decorators import cli_error_handler


@click.group()
def cli() -> None:
    """LVN trading strategy command line interface."""


for command in [
    commands.backtest,
    commands.optimize,
    commands.walk_forward,
    commands.visualize,
    commands.report,
    commands.validate,
]:
    cli.add_command(command)


@cli_error_handler
def main() -> None:
    cli(standalone_mode=False)


if __name__ == "__main__":
    main()
