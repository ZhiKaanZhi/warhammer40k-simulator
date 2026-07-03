"""HumanStrategy: the player picks each shot through Click prompts.

The player IS the strategy — this class only translates battlefield snapshots
into numbered menus and the player's picks into an ``Action``. It offers only
legal choices (eligible shooters, ranged weapons, surviving targets), so the
engine's own legality validation should never fire on a human decision. When
a menu has exactly one option it is announced and auto-picked: scenario 01
has one unit, one gun, and one target, and asking three one-option questions
would teach nothing.
"""

from __future__ import annotations

from collections.abc import Callable, Sequence
from typing import TypeVar

import click

from wh40k_tutorial.core.models import Weapon
from wh40k_tutorial.strategies.base import Action, GameState, UnitSnapshot

T = TypeVar("T")


def _describe_unit(unit: UnitSnapshot) -> str:
    return f"{unit.datasheet.display_name} ({unit.models} models)"


def _describe_weapon(weapon: Weapon) -> str:
    return (
        f"{weapon.display_name} — {weapon.attacks} attacks, {weapon.skill}+ to hit, "
        f"S{weapon.strength}, AP -{weapon.ap}, {weapon.damage} damage"
    )


class HumanStrategy:
    """Prompts the player for one shooting action per activation."""

    def choose_action(self, state: GameState) -> Action:
        shooter = _pick("unit to shoot with", state.eligible_shooters(), _describe_unit)
        weapon = _pick("weapon", shooter.ranged_weapons, _describe_weapon)
        target = _pick("target", state.surviving_enemies(), _describe_unit)
        return Action(
            kind="shoot",
            attacker_unit_id=shooter.unit_id,
            weapon_key=weapon.name,
            target_unit_id=target.unit_id,
        )


def _pick(what: str, options: Sequence[T], describe: Callable[[T], str]) -> T:
    """Announce a single option, or show a numbered menu and prompt for a pick."""
    if not options:
        raise RuntimeError(
            f"no {what} available — the engine should not have asked for an action"
        )
    if len(options) == 1:
        click.echo(f"{what.capitalize()}: {describe(options[0])}")
        return options[0]
    click.echo(f"Pick a {what}:")
    for i, option in enumerate(options, start=1):
        click.echo(f"  {i}. {describe(option)}")
    index = click.prompt("Your choice", type=click.IntRange(1, len(options)))
    return options[index - 1]
