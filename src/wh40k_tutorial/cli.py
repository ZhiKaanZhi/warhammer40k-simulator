"""Click-based CLI entry point.

Currently a stub. The intended commands:

    wh40k                       # interactive menu: pick a scenario, play it
    wh40k list                  # list available scenarios
    wh40k play <scenario-id>    # run a specific scenario
    wh40k version               # print version

TODO: implement once the engine and scenario runner exist (phase 5).
"""

from __future__ import annotations

import click

from wh40k_tutorial import __version__


@click.group(invoke_without_command=True)
@click.pass_context
def main(ctx: click.Context) -> None:
    """Warhammer 40,000 interactive tutorial."""
    if ctx.invoked_subcommand is None:
        click.echo("warhammer40k-tutorial — scaffold in progress.")
        click.echo("Run `wh40k --help` to see commands.")
        click.echo("See CLAUDE.md for the build plan.")


@main.command()
def version() -> None:
    """Print the package version."""
    click.echo(__version__)


@main.command(name="list")
def list_scenarios() -> None:
    """List available tutorial scenarios."""
    # TODO: scan data/scenarios/, print id + title + teaches
    click.echo("TODO: scenario listing not yet implemented (build phase 5).")


@main.command()
@click.argument("scenario_id")
def play(scenario_id: str) -> None:
    """Run a specific tutorial scenario."""
    # TODO: load scenario, instantiate strategies, hand to scenario runner.
    click.echo(f"TODO: scenario runner not yet implemented. Asked for: {scenario_id}")


if __name__ == "__main__":
    main()
