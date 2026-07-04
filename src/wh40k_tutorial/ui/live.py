"""Presenters that feed live game state into the phase-4 shell builders.

Two jobs, both pure formatting:

- turn `UnitSnapshot`s into battlefield `UnitToken`s;
- turn a `ShootingResult` into the plain, step-by-step account of one volley,
  straight from the record's facts (ADR 0001).

The volley account states *what* happened at each step and the numbers that
drove it. The rules *behind* those numbers come from `narrator.py` (build
phase 6): the CLI interleaves its inline explanations with the fact lines and
feeds them to the rules panel here via ``render_live_shell``.
"""

from __future__ import annotations

from collections.abc import Sequence

from rich.layout import Layout

from wh40k_tutorial.core.combat import SaveStep, ShootingResult
from wh40k_tutorial.core.dice import RollResult
from wh40k_tutorial.strategies.base import UnitSnapshot
from wh40k_tutorial.ui.shell import (
    UnitToken,
    build_shell,
    render_action_log,
    render_battlefield,
    render_rules_panel,
)

SIDE_STYLES = {"attacker": "bold blue", "defender": "bold green"}

RULES_PLACEHOLDER_HEADING = "Rules panel"
RULES_PLACEHOLDER_BODY = (
    "The action log records the plain facts of every roll; the rule behind "
    "each one appears here as the dice fall. After a volley you can also ask "
    "for the deeper rule behind any step."
)


def tokens_from_units(units: Sequence[UnitSnapshot]) -> tuple[UnitToken, ...]:
    """Battlefield tokens for every surviving unit; destroyed units leave the table."""
    return tuple(
        UnitToken(
            glyph=unit.datasheet.display_name[0].upper(),
            color=SIDE_STYLES.get(unit.side, "bold white"),
            x=unit.position[0],
            y=unit.position[1],
            name=unit.datasheet.display_name,
            models=unit.models,
        )
        for unit in units
        if not unit.destroyed
    )


def render_live_shell(
    units: Sequence[UnitSnapshot],
    log_lines: Sequence[str],
    *,
    rules_heading: str = RULES_PLACEHOLDER_HEADING,
    rules_body: str = RULES_PLACEHOLDER_BODY,
) -> Layout:
    """The three-panel shell, driven by live state instead of the demo scene.

    ``rules_heading``/``rules_body`` let the caller fill the rules panel with
    the narrator's explanations for the latest volley; the defaults show the
    pre-battle placeholder.
    """
    return build_shell(
        battlefield=render_battlefield(tokens_from_units(units)),
        action_log=render_action_log(log_lines),
        rules=render_rules_panel(rules_heading, rules_body),
    )


def volley_report_lines(result: ShootingResult, *, turn: int) -> list[str]:
    """One volley as plain step-by-step facts, read straight off the record."""
    attack, hit, wound = result.attack, result.hit, result.wound
    save = result.save
    weapon = attack.weapon

    lines = [
        f"Turn {turn} — {result.attacker.display_name} fires "
        f"{weapon.display_name} at {result.defender.display_name}.",
        f"ATTACKS: {attack.attacker_models} models x {attack.attacks_per_model} attacks "
        f"= {attack.total_attacks} dice",
        f"HIT:     need {hit.roll.target}+ — rolled {_faces(hit.roll)} -> {hit.hits} hit",
        f"WOUND:   need {wound.roll.target}+ (S{wound.strength} vs T{wound.toughness}) "
        f"— rolled {_faces(wound.roll)} -> {wound.wounds} wound",
        _save_line(save),
        _damage_line(result),
    ]
    return lines


def _faces(roll: RollResult) -> str:
    return " ".join(str(face) for face in roll.raw_rolls) if roll.raw_rolls else "no dice"


def _save_desc(save: SaveStep) -> str:
    parts = [f"armour {save.armor_save}+"]
    if save.ap:
        parts.append(f"AP -{save.ap}")
    if save.invulnerable_save is not None:
        parts.append(f"invulnerable {save.invulnerable_save}++")
    return ", ".join(parts)


def _save_line(save: SaveStep) -> str:
    if not save.save_possible:
        return (
            f"SAVE:    no save possible ({_save_desc(save)} -> needs "
            f"{save.modified_target}+) — all {save.failed_saves} wounds fail"
        )
    return (
        f"SAVE:    need {save.modified_target}+ ({_save_desc(save)}) — rolled "
        f"{_faces(save.roll)} -> {save.failed_saves} failed"
    )


def _damage_line(result: ShootingResult) -> str:
    damage = result.damage
    started_with = damage.models_remaining + damage.models_slain
    line = (
        f"DAMAGE:  {result.save.failed_saves} failed saves x "
        f"{damage.damage_per_failed_save} damage -> {damage.models_slain} models slain; "
        f"{damage.models_remaining} of {started_with} remain"
    )
    wounds_per_model = result.defender.profile.wounds
    if damage.models_remaining > 0 and damage.wounds_remaining_on_lead != wounds_per_model:
        line += (
            f" (lead model on {damage.wounds_remaining_on_lead} of "
            f"{wounds_per_model} wounds)"
        )
    if damage.wasted_damage:
        line += f", {damage.wasted_damage} damage wasted (overkill)"
    return line
