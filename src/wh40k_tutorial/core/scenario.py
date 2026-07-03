"""Scenario model: the pre-positioned battles that teach one concept each.

`load_scenario` / `load_scenario_by_id` deserialize `data/scenarios/*.json`
into frozen value types, validating eagerly in the same name-the-culprit
style as the faction loader: referenced factions are loaded, referenced
datasheets must exist, model counts must fit the datasheet's unit size,
positions must be on the battlefield grid and not collide, and any scripted
actions must be legal for the units on the board. Bad data fails at load
time, never mid-battle. Schema reference: `.claude/skills/add-scenario/SKILL.md`.
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from importlib import resources
from pathlib import Path

from wh40k_tutorial.core.models import FactionDataError, UnitDatasheet, load_faction_by_name

# The battlefield the scenarios position their units on. The Rich UI draws
# this same grid (ui/shell.py defaults to these dimensions).
BATTLEFIELD_WIDTH = 12
BATTLEFIELD_HEIGHT = 8

SIDES = ("attacker", "defender")

# v1 models the shooting phase only (see "Scope discipline" in CLAUDE.md).
_SUPPORTED_PHASES = ("shooting",)


class ScenarioDataError(ValueError):
    """A scenario JSON file doesn't match the schema in the add-scenario skill."""


@dataclass(frozen=True)
class ScenarioUnit:
    """One unit as placed by the scenario, with its datasheet already resolved."""

    unit_id: str
    datasheet: UnitDatasheet
    position: tuple[int, int]  # (x, y) on the battlefield grid
    models: int


@dataclass(frozen=True)
class ScenarioSide:
    """Everything one side brings to the battle."""

    name: str  # "attacker" or "defender"
    faction: str
    units: tuple[ScenarioUnit, ...]


@dataclass(frozen=True)
class ScenarioAction:
    """One scripted shooting action inside a turn entry.

    This is the *data-file* shape; `strategies.scripted` converts it into the
    protocol's `Action` at runtime (core stays free of the strategies layer).
    """

    attacker_unit_id: str
    weapon: str  # weapon key on the attacker's datasheet; must be ranged
    target_unit_id: str


@dataclass(frozen=True)
class ScenarioTurn:
    """One phase of one game turn.

    ``actions`` is the optional script for this turn: when the active side is
    played by ``ScriptedStrategy``, these are the shots it replays, in order.
    Turns the *player* acts in normally leave it empty — the human decides.
    """

    phase: str  # v1: "shooting" only
    active_side: str
    narrate_before: str = ""
    actions: tuple[ScenarioAction, ...] = ()


@dataclass(frozen=True)
class Scenario:
    """A whole tutorial scenario, loaded and cross-checked."""

    scenario_id: str
    title: str
    teaches: str
    intro: str
    player_side: str
    attacker: ScenarioSide
    defender: ScenarioSide
    turns: tuple[ScenarioTurn, ...]
    outro: str

    def side(self, name: str) -> ScenarioSide:
        if name == "attacker":
            return self.attacker
        if name == "defender":
            return self.defender
        raise KeyError(f"no side named {name!r}; sides are {SIDES}")

    @property
    def all_units(self) -> tuple[ScenarioUnit, ...]:
        return self.attacker.units + self.defender.units


def opposing_side(side: str) -> str:
    """The other side: attacker <-> defender."""
    if side == "attacker":
        return "defender"
    if side == "defender":
        return "attacker"
    raise KeyError(f"no side named {side!r}; sides are {SIDES}")


# ---------------------------------------------------------------------------
# Parsing helpers (same conventions as core/models.py)
# ---------------------------------------------------------------------------


def _get(mapping: dict, key: str, ctx: str) -> object:
    """Fetch a required field, failing with a message that names where it was missing."""
    try:
        return mapping[key]
    except (KeyError, TypeError):
        raise ScenarioDataError(f"missing required field {key!r} in {ctx}") from None


def _str_field(mapping: dict, key: str, ctx: str) -> str:
    value = _get(mapping, key, ctx)
    if not isinstance(value, str) or not value.strip():
        raise ScenarioDataError(f"{ctx}: field {key!r} must be a non-empty string, got {value!r}")
    return value


def _parse_position(raw: object, ctx: str) -> tuple[int, int]:
    if (
        not isinstance(raw, list)
        or len(raw) != 2
        or any(isinstance(v, bool) or not isinstance(v, int) for v in raw)
    ):
        raise ScenarioDataError(f"{ctx}: 'position' must be a two-integer [x, y], got {raw!r}")
    x, y = raw
    if not (0 <= x < BATTLEFIELD_WIDTH and 0 <= y < BATTLEFIELD_HEIGHT):
        raise ScenarioDataError(
            f"{ctx}: position ({x}, {y}) is off the "
            f"{BATTLEFIELD_WIDTH}x{BATTLEFIELD_HEIGHT} battlefield grid"
        )
    return (x, y)


def _parse_unit(
    raw: object, side_name: str, sheets: dict[str, UnitDatasheet], ctx: str
) -> ScenarioUnit:
    if not isinstance(raw, dict):
        raise ScenarioDataError(f"{ctx}: each unit must be an object, got {raw!r}")
    unit_id = _str_field(raw, "id", ctx)
    ctx = f"{ctx} (id {unit_id!r})"
    datasheet_key = _str_field(raw, "datasheet", ctx)
    sheet = sheets.get(datasheet_key)
    if sheet is None:
        raise ScenarioDataError(
            f"{ctx}: datasheet {datasheet_key!r} does not exist in the "
            f"{side_name} side's faction; available: {', '.join(sorted(sheets))}"
        )
    models = _get(raw, "models", ctx)
    if isinstance(models, bool) or not isinstance(models, int):
        raise ScenarioDataError(f"{ctx}: 'models' must be an integer, got {models!r}")
    hi = sheet.max_model_count
    if models < sheet.min_model_count or (hi is not None and models > hi):
        raise ScenarioDataError(
            f"{ctx}: {models} models does not fit {sheet.display_name}'s unit size "
            f"({sheet.min_model_count}..{hi})"
        )
    return ScenarioUnit(
        unit_id=unit_id,
        datasheet=sheet,
        position=_parse_position(_get(raw, "position", ctx), ctx),
        models=models,
    )


def _parse_side(data: dict, name: str, source: str) -> ScenarioSide:
    ctx = f"{source}.sides.{name}"
    raw = _get(data, name, f"{source}.sides")
    if not isinstance(raw, dict):
        raise ScenarioDataError(f"{ctx}: must be an object with 'faction' and 'units'")
    faction = _str_field(raw, "faction", ctx)
    try:
        sheets = load_faction_by_name(faction)
    except FactionDataError as exc:
        raise ScenarioDataError(f"{ctx}: cannot load faction {faction!r} — {exc}") from exc
    units_raw = _get(raw, "units", ctx)
    if not isinstance(units_raw, list) or not units_raw:
        raise ScenarioDataError(f"{ctx}: 'units' must be a non-empty list")
    units = tuple(
        _parse_unit(u, name, sheets, f"{ctx}.units[{i}]") for i, u in enumerate(units_raw)
    )
    return ScenarioSide(name=name, faction=faction, units=units)


def _cross_check_placement(scenario_units: tuple[ScenarioUnit, ...], source: str) -> None:
    seen_ids: dict[str, str] = {}
    seen_positions: dict[tuple[int, int], str] = {}
    for unit in scenario_units:
        if unit.unit_id in seen_ids:
            raise ScenarioDataError(
                f"{source}: unit id {unit.unit_id!r} is used more than once — "
                f"ids must be unique across both sides"
            )
        seen_ids[unit.unit_id] = unit.unit_id
        if unit.position in seen_positions:
            raise ScenarioDataError(
                f"{source}: units {seen_positions[unit.position]!r} and {unit.unit_id!r} "
                f"share position {unit.position} — one grid square holds one unit"
            )
        seen_positions[unit.position] = unit.unit_id


def _parse_action(
    raw: object,
    active: ScenarioSide,
    enemies: ScenarioSide,
    ctx: str,
) -> ScenarioAction:
    if not isinstance(raw, dict):
        raise ScenarioDataError(f"{ctx}: each action must be an object, got {raw!r}")
    attacker_id = _str_field(raw, "attacker", ctx)
    weapon_key = _str_field(raw, "weapon", ctx)
    target_id = _str_field(raw, "target", ctx)
    shooter = next((u for u in active.units if u.unit_id == attacker_id), None)
    if shooter is None:
        raise ScenarioDataError(
            f"{ctx}: attacker {attacker_id!r} is not a unit on the active "
            f"({active.name}) side"
        )
    weapon = next((w for w in shooter.datasheet.weapons if w.name == weapon_key), None)
    if weapon is None:
        raise ScenarioDataError(
            f"{ctx}: {shooter.datasheet.display_name} has no weapon {weapon_key!r}"
        )
    if weapon.type != "ranged":
        raise ScenarioDataError(
            f"{ctx}: {weapon.display_name} is a melee weapon — scripted shooting "
            f"actions need a ranged weapon"
        )
    if all(u.unit_id != target_id for u in enemies.units):
        raise ScenarioDataError(
            f"{ctx}: target {target_id!r} is not a unit on the {enemies.name} side"
        )
    return ScenarioAction(
        attacker_unit_id=attacker_id, weapon=weapon_key, target_unit_id=target_id
    )


def _parse_turn(
    raw: object, attacker: ScenarioSide, defender: ScenarioSide, ctx: str
) -> ScenarioTurn:
    if not isinstance(raw, dict):
        raise ScenarioDataError(f"{ctx}: each turn must be an object, got {raw!r}")
    phase = _str_field(raw, "phase", ctx)
    if phase not in _SUPPORTED_PHASES:
        raise ScenarioDataError(
            f"{ctx}: phase {phase!r} is not supported — v1 models only "
            f"{', '.join(_SUPPORTED_PHASES)} (see 'Scope discipline' in CLAUDE.md)"
        )
    active_side = _str_field(raw, "active_side", ctx)
    if active_side not in SIDES:
        raise ScenarioDataError(f"{ctx}: 'active_side' must be one of {SIDES}, got {active_side!r}")
    narrate = raw.get("narrate_before", "")
    if not isinstance(narrate, str):
        raise ScenarioDataError(f"{ctx}: 'narrate_before' must be a string, got {narrate!r}")
    actions_raw = raw.get("actions", [])
    if not isinstance(actions_raw, list):
        raise ScenarioDataError(f"{ctx}: 'actions' must be a list, got {actions_raw!r}")
    active = attacker if active_side == "attacker" else defender
    enemies = defender if active_side == "attacker" else attacker
    actions = tuple(
        _parse_action(a, active, enemies, f"{ctx}.actions[{i}]")
        for i, a in enumerate(actions_raw)
    )
    return ScenarioTurn(
        phase=phase, active_side=active_side, narrate_before=narrate, actions=actions
    )


def _parse_scenario(data: object, source: str) -> Scenario:
    if not isinstance(data, dict):
        raise ScenarioDataError(f"{source}: top level must be a JSON object")
    scenario_id = _str_field(data, "id", source)
    player_side = _str_field(data, "player_side", source)
    if player_side not in SIDES:
        raise ScenarioDataError(
            f"{source}: 'player_side' must be one of {SIDES}, got {player_side!r}"
        )
    sides = _get(data, "sides", source)
    if not isinstance(sides, dict):
        raise ScenarioDataError(f"{source}: 'sides' must be an object with attacker and defender")
    attacker = _parse_side(sides, "attacker", source)
    defender = _parse_side(sides, "defender", source)
    _cross_check_placement(attacker.units + defender.units, source)
    turns_raw = _get(data, "turns", source)
    if not isinstance(turns_raw, list) or not turns_raw:
        raise ScenarioDataError(f"{source}: 'turns' must be a non-empty list")
    turns = tuple(
        _parse_turn(t, attacker, defender, f"{source}.turns[{i}]")
        for i, t in enumerate(turns_raw)
    )
    return Scenario(
        scenario_id=scenario_id,
        title=_str_field(data, "title", source),
        teaches=_str_field(data, "teaches", source),
        intro=_str_field(data, "intro", source),
        player_side=player_side,
        attacker=attacker,
        defender=defender,
        turns=turns,
        outro=_str_field(data, "outro", source),
    )


# ---------------------------------------------------------------------------
# Loading
# ---------------------------------------------------------------------------


def load_scenario(path: str | Path) -> Scenario:
    """Load one scenario JSON file, validating it eagerly.

    Raises `ScenarioDataError` (a `ValueError`) naming the field, unit, or
    action at fault. The file's stem must match the scenario's ``id`` so
    ``wh40k play <id>`` always finds what ``wh40k list`` showed.
    """
    file = Path(path)
    try:
        data = json.loads(file.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        raise ScenarioDataError(f"{file.name}: not valid JSON ({exc})") from exc
    scenario = _parse_scenario(data, source=file.name)
    if scenario.scenario_id != file.stem:
        raise ScenarioDataError(
            f"{file.name}: 'id' is {scenario.scenario_id!r} but must match the "
            f"file name ({file.stem!r})"
        )
    return scenario


def _packaged_scenarios_dir():
    return resources.files("wh40k_tutorial") / "data" / "scenarios"


def load_scenario_by_id(scenario_id: str) -> Scenario:
    """Load a packaged scenario by id, e.g. ``load_scenario_by_id("01_first_shots")``."""
    scenarios_dir = _packaged_scenarios_dir()
    candidate = scenarios_dir / f"{scenario_id}.json"
    if not candidate.is_file():
        available = sorted(
            p.name.removesuffix(".json")
            for p in scenarios_dir.iterdir()
            if p.name.endswith(".json")
        )
        raise ScenarioDataError(
            f"no scenario named {scenario_id!r}; available: {', '.join(available)}"
        )
    scenario = _parse_scenario(
        json.loads(candidate.read_text(encoding="utf-8")), source=f"{scenario_id}.json"
    )
    if scenario.scenario_id != scenario_id:
        raise ScenarioDataError(
            f"{scenario_id}.json: 'id' is {scenario.scenario_id!r} but must match the "
            f"file name ({scenario_id!r})"
        )
    return scenario


def available_scenarios() -> list[Scenario]:
    """Load every packaged scenario, in file-name (intended play) order.

    Packaged data is curated, so a malformed file fails loudly here rather
    than being silently skipped — `wh40k list` surfaces the loader's message.
    """
    scenarios_dir = _packaged_scenarios_dir()
    names = sorted(p.name for p in scenarios_dir.iterdir() if p.name.endswith(".json"))
    return [load_scenario_by_id(name.removesuffix(".json")) for name in names]
