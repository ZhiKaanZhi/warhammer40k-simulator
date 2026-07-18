"""HumanStrategy: the player picks each shot and each fight through Click prompts.

The player IS the strategy — this class only translates battlefield snapshots
into numbered menus and the player's picks into an ``Action``. It offers only
legal choices (eligible shooters or fighters, weapons of the phase's type,
and — in melee — only engaged targets), so the engine's own legality
validation should never fire on a human decision. When
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
    """Prompts the player for one action per activation — a shot, or a fight."""

    def choose_action(self, state: GameState) -> Action:
        if state.phase == "fight":
            return self._choose_fight(state)
        return self._choose_shot(state)

    def _choose_shot(self, state: GameState) -> Action:
        shooter = _pick("unit to shoot with", state.eligible_shooters(), _describe_unit)
        weapon = _pick("weapon", shooter.ranged_weapons, _describe_weapon)
        target = _pick("target", state.surviving_enemies(), _describe_unit)
        return Action(
            kind="shoot",
            attacker_unit_id=shooter.unit_id,
            weapon_key=weapon.name,
            target_unit_id=target.unit_id,
        )

    def _choose_fight(self, state: GameState) -> Action:
        def describe_fighter(unit: UnitSnapshot) -> str:
            # Two mobs of "Boyz (10 models)" are indistinguishable on a menu;
            # naming each unit's opponent is what makes the ordering decision
            # legible — WHICH fight, not just which unit.
            enemies = " and ".join(
                e.datasheet.display_name for e in state.engaged_enemies(unit)
            )
            return f"{_describe_unit(unit)} — fighting {enemies}"

        fighter = _pick(
            "unit to fight with",
            state.eligible_fighters(state.active_side),
            describe_fighter,
        )
        weapon = _pick("melee weapon", fighter.melee_weapons, _describe_weapon)
        target = _pick("target", state.engaged_enemies(fighter), _describe_unit)
        return Action(
            kind="fight",
            attacker_unit_id=fighter.unit_id,
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
