"""Domain model: units, weapons, profiles, the things data files describe.

These are frozen dataclasses — pure value types. Runtime state (current
wounds remaining, model count after casualties, etc.) lives in the engine,
not here.

TODO: implement load_faction() to deserialize data/factions/*.json into these.
"""

from __future__ import annotations

from dataclasses import dataclass, field


@dataclass(frozen=True)
class Profile:
    """The unit-level statline."""

    movement: int           # M in inches
    toughness: int          # T
    save: int               # armor save target (3 means "3+")
    wounds: int             # W per model
    leadership: int         # Ld target
    objective_control: int  # OC
    invulnerable_save: int | None = None  # e.g. 4 means "4++" — None if no invuln


@dataclass(frozen=True)
class Weapon:
    """A weapon profile.

    `skill` is BS for ranged weapons and WS for melee — both are the to-hit target.
    `ap` is stored as a *positive* integer representing the magnitude of the modifier.
    A rulebook "AP -2" weapon has `ap=2` here.
    """

    name: str
    type: str  # "ranged" or "melee"
    range: int  # in inches; 0 for melee
    attacks: int
    skill: int
    strength: int
    ap: int  # positive integer magnitude
    damage: int
    keywords: tuple[str, ...] = ()


@dataclass(frozen=True)
class UnitDatasheet:
    """A unit's datasheet — the static description, not a battlefield instance."""

    key: str  # e.g. "intercessor_squad"
    display_name: str
    faction: str
    profile: Profile
    weapons: tuple[Weapon, ...]
    default_model_count: int
    abilities: tuple[str, ...] = ()  # v1: just names. v2: structured ability objects.
    notes: str = ""


# TODO: implement
def load_faction(path: str) -> dict[str, UnitDatasheet]:
    """Load a faction JSON file and return a dict of unit_key -> UnitDatasheet.

    See `.claude/skills/add-unit/SKILL.md` for the schema this expects.
    Raise a clear error if a unit references a keyword the engine doesn't support yet.
    """
    raise NotImplementedError("TODO: implement JSON loader for faction data")
