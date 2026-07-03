"""Click-based CLI entry point.

Commands:

    wh40k                       # overview + pointer to --help
    wh40k list                  # list available scenarios
    wh40k play <scenario-id>    # run a tutorial scenario
    wh40k demo                  # static preview of the three-panel UI
    wh40k version               # print the package version

`play` runs the phase-5 scenario runner: the player's side is driven by
`HumanStrategy` prompts, the opponent by `ScriptedStrategy`, and every volley
is reported step by step straight from the `ShootingResult` record. Rule
*explanations* (the contextual rules panel content and "why?" expansion)
arrive with the narrator, build phase 6.
"""

from __future__ import annotations

import random

import click
from rich.console import Console

from wh40k_tutorial import __version__
from wh40k_tutorial.core.scenario import (
    SIDES,
    ScenarioDataError,
    ScenarioTurn,
    available_scenarios,
    load_scenario_by_id,
    opposing_side,
)
from wh40k_tutorial.engine import BattleState, EngineError, VolleyEvent, run_scenario
from wh40k_tutorial.strategies.base import Strategy
from wh40k_tutorial.strategies.human import HumanStrategy
from wh40k_tutorial.strategies.scripted import (
    ScriptedStrategy,
    ScriptExhaustedError,
    scripted_actions_for,
)
from wh40k_tutorial.ui.demo import run_demo
from wh40k_tutorial.ui.live import render_live_shell, volley_report_lines

# Explicit render height for the shell so the battlefield (16 rows minimum)
# and one full volley report always fit without the layout cropping the log.
_SHELL_HEIGHT = 32


@click.group(invoke_without_command=True)
@click.pass_context
def main(ctx: click.Context) -> None:
    """Warhammer 40,000 interactive tutorial."""
    if ctx.invoked_subcommand is None:
        click.echo("warhammer40k-tutorial — an interactive 40k tutorial.")
        click.echo("Run `wh40k list` to see scenarios, `wh40k play <id>` to play one.")
        click.echo("Run `wh40k --help` for all commands.")


@main.command()
def version() -> None:
    """Print the package version."""
    click.echo(__version__)


@main.command()
def demo() -> None:
    """Show a static preview of the three-panel tutorial interface."""
    run_demo()


@main.command(name="list")
def list_scenarios() -> None:
    """List available tutorial scenarios."""
    try:
        scenarios = available_scenarios()
    except ScenarioDataError as exc:
        raise click.ClickException(str(exc)) from exc
    for scenario in scenarios:
        click.echo(f"{scenario.scenario_id}  —  {scenario.title} "
                   f"(teaches {scenario.teaches.rstrip('.')})")


@main.command()
@click.argument("scenario_id")
@click.option("--seed", type=int, default=None,
              help="Seed the dice for a reproducible battle.")
def play(scenario_id: str, seed: int | None) -> None:
    """Run a tutorial scenario end to end."""
    try:
        scenario = load_scenario_by_id(scenario_id)
    except ScenarioDataError as exc:
        raise click.ClickException(str(exc)) from exc

    console = Console()
    opponent = opposing_side(scenario.player_side)
    strategies: dict[str, Strategy] = {
        scenario.player_side: HumanStrategy(),
        opponent: ScriptedStrategy(scripted_actions_for(scenario, opponent)),
    }

    click.echo(f"\n=== {scenario.title} ===")
    click.echo(f"This scenario teaches {scenario.teaches.rstrip('.')}.")
    click.echo(f"You play the {scenario.player_side}.\n")
    click.echo(scenario.intro + "\n")
    console.print(render_live_shell(
        BattleState.from_scenario(scenario).snapshot().units,
        ("The battle is about to begin.",),
    ), height=_SHELL_HEIGHT)

    last_volley: list[str] = []

    def announce_turn(number: int, turn: ScenarioTurn) -> None:
        click.echo(f"\n— Turn {number}: {turn.phase} phase, the {turn.active_side} acts —")
        if turn.narrate_before:
            click.echo(turn.narrate_before + "\n")

    def show_volley(event: VolleyEvent) -> None:
        last_volley[:] = volley_report_lines(event.result, turn=event.turn)
        for line in last_volley:
            click.echo(line)
        click.echo("")

    try:
        final = run_scenario(
            scenario,
            strategies,
            rng=random.Random(seed),
            on_turn_start=announce_turn,
            on_volley=show_volley,
        )
    except (EngineError, ScriptExhaustedError) as exc:
        raise click.ClickException(str(exc)) from exc

    console.print(render_live_shell(
        final.snapshot().units,
        last_volley or ("No shots were fired.",),
    ), height=_SHELL_HEIGHT)
    for side in SIDES:
        if final.side_wiped(side):
            click.echo(f"The {side}'s force has been wiped out.")
    click.echo("\n" + scenario.outro)


if __name__ == "__main__":
    main()
