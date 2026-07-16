"""Domain model: units, weapons, profiles, the things data files describe.

These are frozen dataclasses — pure value types. Runtime state (current
wounds remaining, model count after casualties, etc.) lives in the engine,
not here.

`load_faction` / `load_faction_by_name` deserialize `data/factions/*.json`
into these types, validating eagerly so bad data fails at load time with a
message naming the faction/unit/weapon — never at resolution time deep in
the combat pipeline. Schema reference: `.claude/skills/add-unit/SKILL.md`.
"""

from __future__ import annotations

import json
import random
import re
from dataclasses import dataclass
from importlib import resources
from pathlib import Path


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
class WeaponKeyword:
    """A weapon keyword as the hook framework consumes it (ADR 0002).

    JSON stores canonical lowercase strings ("sustained_hits_1"); this is the
    structured form — a name plus an optional numeric parameter — so one hook
    can serve every value of a parametric ability.
    """

    name: str  # e.g. "sustained_hits", "lethal_hits"
    value: int | None = None  # e.g. 1 for "sustained_hits_1"; None if bare


def parse_weapon_keyword(raw: str) -> WeaponKeyword:
    """Split a canonical keyword string into name + optional trailing number."""
    head, _, tail = raw.rpartition("_")
    if head and tail.isdigit():
        return WeaponKeyword(name=head, value=int(tail))
    return WeaponKeyword(name=raw)


_DICE_RE = re.compile(r"^(\d*)[dD](\d+)([+-]\d+)?$")


@dataclass(frozen=True)
class DiceValue:
    """A characteristic that is either a fixed number or a simple dice roll.

    Covers the forms weapons use for Damage: a fixed integer, a single die
    ('D3', 'D6'), or a die with a flat modifier ('D6+2'). ``roll`` draws one
    sample — a fixed value never touches the rng, so introducing variable
    damage doesn't disturb any existing seeded outcome — and ``average`` is
    the mean the expected-damage estimator reads. (v1 uses a single die;
    the shape allows a count for later.)
    """

    n_dice: int      # 0 for a fixed value; else the number of dice (v1: 1)
    die_sides: int   # 3 or 6 when n_dice > 0; 0 for a fixed value
    modifier: int    # the constant when fixed; the flat "+X" on a die otherwise

    @classmethod
    def fixed(cls, value: int) -> DiceValue:
        return cls(n_dice=0, die_sides=0, modifier=value)

    @classmethod
    def coerce(cls, value: object) -> DiceValue:
        """Best-effort conversion from an int or a dice string; raises ValueError.

        Convenience for hand-built ``Weapon``s; the JSON loader uses
        ``_parse_damage`` instead for messages that name the offending field.
        """
        if isinstance(value, DiceValue):
            return value
        if isinstance(value, bool):
            raise ValueError(f"cannot interpret {value!r} as a damage value")
        if isinstance(value, int):
            return cls.fixed(value)
        if isinstance(value, str):
            match = _DICE_RE.match(value.strip())
            if match:
                n = int(match.group(1)) if match.group(1) else 1
                sides = int(match.group(2))
                mod = int(match.group(3)) if match.group(3) else 0
                if sides in (3, 6) and n >= 1:
                    return cls(n_dice=n, die_sides=sides, modifier=mod)
        raise ValueError(f"cannot interpret {value!r} as a damage value")

    @property
    def is_variable(self) -> bool:
        return self.n_dice > 0

    @property
    def average(self) -> float:
        """Mean of the roll — (sides+1)/2 per die, plus the modifier."""
        return self.n_dice * (self.die_sides + 1) / 2 + self.modifier

    @property
    def minimum(self) -> int:
        return self.n_dice + self.modifier  # each die shows at least 1

    @property
    def maximum(self) -> int:
        return self.n_dice * self.die_sides + self.modifier

    def roll(self, rng: random.Random) -> int:
        """One sample. A fixed value draws no dice, leaving the rng untouched."""
        return sum(rng.randint(1, self.die_sides) for _ in range(self.n_dice)) + self.modifier

    def __str__(self) -> str:
        if not self.is_variable:
            return str(self.modifier)
        core = f"{self.n_dice if self.n_dice > 1 else ''}D{self.die_sides}"
        if self.modifier > 0:
            core += f"+{self.modifier}"
        elif self.modifier < 0:
            core += str(self.modifier)
        return core


@dataclass(frozen=True)
class Weapon:
    """A weapon profile.

    `name` is the stable key from the faction JSON (e.g. "bolt_rifle"), used by
    loadouts and engine lookups; `display_name` is what the narrator shows.
    `skill` is BS for ranged weapons and WS for melee — both are the to-hit target.
    `ap` is stored as a *positive* integer representing the magnitude of the modifier.
    A rulebook "AP -2" weapon has `ap=2` here.
    """

    name: str
    display_name: str
    type: str  # "ranged" or "melee"
    range: int  # in inches; 0 for melee
    attacks: int
    skill: int
    strength: int
    ap: int  # positive integer magnitude
    damage: DiceValue  # a fixed int or dice string may be passed; coerced to DiceValue
    keywords: tuple[str, ...] = ()

    def __post_init__(self) -> None:
        # Accept a plain int or a dice string ("D3") for ergonomics; the
        # canonical stored form is always a DiceValue.
        if not isinstance(self.damage, DiceValue):
            object.__setattr__(self, "damage", DiceValue.coerce(self.damage))

    @property
    def parsed_keywords(self) -> tuple[WeaponKeyword, ...]:
        """The keywords in structured name+value form, for the hook framework."""
        return tuple(parse_weapon_keyword(raw) for raw in self.keywords)


@dataclass(frozen=True)
class UnitDatasheet:
    """A unit's datasheet — the static description, not a battlefield instance."""

    key: str  # e.g. "intercessor_squad"
    display_name: str
    faction: str
    profile: Profile
    weapons: tuple[Weapon, ...]
    default_model_count: int
    min_model_count: int = 1
    # None = uncapped (hand-built test sheets); the JSON loader always sets it.
    max_model_count: int | None = None
    default_loadout: tuple[str, ...] = ()  # weapon keys every model fires by default
    abilities: tuple[str, ...] = ()  # v1: just names. v2: structured ability objects.
    notes: str = ""


def shootable_weapons(
    datasheet: UnitDatasheet, loadout_override: tuple[str, ...] = ()
) -> tuple[Weapon, ...]:
    """The ranged weapons a unit may fire, honoring an optional loadout override.

    This is the single definition of "what can this unit shoot": the scenario
    loader, the engine's action validation, and the strategies'
    ``UnitSnapshot.ranged_weapons`` all defer to it, so menus, scripts, and
    legality checks can never disagree.

    Selection: the scenario's ``loadout_override`` if one was given, otherwise
    the datasheet's ``default_loadout``; the result is that selection's ranged
    entries, in selection order. A datasheet that declares no loadout at all
    falls back to every ranged weapon it carries. (The scenario loader
    guarantees any override it accepts contains at least one ranged weapon,
    so an override never falls through to that last resort.)
    """
    by_key = {w.name: w for w in datasheet.weapons}
    selected = loadout_override or datasheet.default_loadout
    chosen = tuple(by_key[key] for key in selected if by_key[key].type == "ranged")
    if chosen:
        return chosen
    return tuple(w for w in datasheet.weapons if w.type == "ranged")


def melee_weapons(
    datasheet: UnitDatasheet, loadout_override: tuple[str, ...] = ()
) -> tuple[Weapon, ...]:
    """The melee weapons a unit may fight with, honoring an optional loadout override.

    The Fight-phase mirror of `shootable_weapons`, and like it the single
    definition of "what can this unit swing": scenario loader, engine
    validation, and ``UnitSnapshot.melee_weapons`` all defer here.

    Selection: the melee entries of the scenario's ``loadout_override`` (or
    the datasheet's ``default_loadout``) when it names any; otherwise every
    melee weapon on the sheet. The fallback is the common case on purpose —
    loadouts swap *guns*, but a model always keeps its close-combat weapon
    (the 11th-edition rule is that each model picks one melee weapon it has
    when fighting, 04.01), so an override that only names rifles must not
    disarm the unit in melee.
    """
    by_key = {w.name: w for w in datasheet.weapons}
    selected = loadout_override or datasheet.default_loadout
    chosen = tuple(by_key[key] for key in selected if by_key[key].type == "melee")
    if chosen:
        return chosen
    return tuple(w for w in datasheet.weapons if w.type == "melee")


class FactionDataError(ValueError):
    """A faction JSON file doesn't match the schema in the add-unit skill."""


# Canonical weapon keywords (see `.claude/skills/add-unit/SKILL.md`).
# The loader accepts any keyword listed here even if the engine doesn't
# implement it yet — unimplemented keywords are inert until the phase-7
# hook framework lands. Unknown spellings are rejected as probable typos.
_EXACT_KEYWORDS = frozenset(
    {"assault", "heavy", "lethal_hits", "devastating_wounds", "twin_linked", "blast", "torrent"}
)
_PARAMETRIC_KEYWORDS = (
    re.compile(r"^(?:rapid_fire|sustained_hits)_[1-9]\d*$"),
    re.compile(r"^anti_(?:infantry|vehicle|monster|character|fly|psyker)_[2-6]$"),
)

_WEAPON_TYPES = ("ranged", "melee")


def _get(mapping: dict, key: str, ctx: str) -> object:
    """Fetch a required field, failing with a message that names where it was missing."""
    try:
        return mapping[key]
    except (KeyError, TypeError):
        raise FactionDataError(f"missing required field {key!r} in {ctx}") from None


def _int_field(mapping: dict, key: str, ctx: str, *, lo: int, hi: int | None = None) -> int:
    """Fetch a required integer field and range-check it (bools are rejected)."""
    value = _get(mapping, key, ctx)
    if isinstance(value, bool) or not isinstance(value, int):
        raise FactionDataError(f"{ctx}: field {key!r} must be an integer, got {value!r}")
    if value < lo or (hi is not None and value > hi):
        bounds = f"in {lo}..{hi}" if hi is not None else f">= {lo}"
        raise FactionDataError(f"{ctx}: field {key!r} must be {bounds}, got {value}")
    return value


def _validate_keyword(keyword: object, ctx: str) -> str:
    if isinstance(keyword, str) and (
        keyword in _EXACT_KEYWORDS or any(p.match(keyword) for p in _PARAMETRIC_KEYWORDS)
    ):
        return keyword
    raise FactionDataError(
        f"{ctx}: unknown weapon keyword {keyword!r}. Canonical names live in "
        f".claude/skills/add-unit/SKILL.md — add new keywords there first. "
        f"(Keywords the engine hasn't implemented yet are accepted but inert.)"
    )


def _parse_damage(data: dict, ctx: str) -> DiceValue:
    """Parse a weapon's Damage: a positive integer, or a dice value 'D3'/'D6'/'D6+1'."""
    raw = _get(data, "damage", ctx)
    if isinstance(raw, bool):
        raise FactionDataError(f"{ctx}: 'damage' must be an integer or dice value, got {raw!r}")
    if isinstance(raw, int):
        if raw < 1:
            raise FactionDataError(f"{ctx}: 'damage' must be >= 1, got {raw}")
        return DiceValue.fixed(raw)
    if isinstance(raw, str):
        match = _DICE_RE.match(raw.strip())
        if match is None:
            raise FactionDataError(
                f"{ctx}: 'damage' must be an integer or a dice value like 'D3', 'D6', "
                f"or 'D6+1', got {raw!r}"
            )
        n = int(match.group(1)) if match.group(1) else 1
        sides = int(match.group(2))
        mod = int(match.group(3)) if match.group(3) else 0
        if sides not in (3, 6):
            raise FactionDataError(f"{ctx}: dice damage supports only D3 or D6, got 'D{sides}'")
        if n < 1:
            raise FactionDataError(f"{ctx}: dice count must be >= 1 in {raw!r}")
        if n + mod < 1:
            raise FactionDataError(f"{ctx}: 'damage' {raw!r} can roll below 1")
        return DiceValue(n_dice=n, die_sides=sides, modifier=mod)
    raise FactionDataError(f"{ctx}: 'damage' must be an integer or dice value, got {raw!r}")


def _parse_weapon(key: str, data: dict, ctx: str) -> Weapon:
    weapon_type = _get(data, "type", ctx)
    if weapon_type not in _WEAPON_TYPES:
        raise FactionDataError(f"{ctx}: 'type' must be one of {_WEAPON_TYPES}, got {weapon_type!r}")
    attacks_raw = _get(data, "attacks", ctx)
    if isinstance(attacks_raw, str):
        raise FactionDataError(
            f"{ctx}: variable Attacks ({attacks_raw!r}) aren't supported yet — planned "
            f"alongside the shooting pipeline (see docs/design/shooting-pipeline.md)"
        )
    weapon_range = _int_field(data, "range", ctx, lo=0)
    if weapon_type == "melee" and weapon_range != 0:
        raise FactionDataError(f"{ctx}: melee weapons must have range 0, got {weapon_range}")
    return Weapon(
        name=key,
        display_name=str(_get(data, "display_name", ctx)),
        type=weapon_type,
        range=weapon_range,
        attacks=_int_field(data, "attacks", ctx, lo=1),
        skill=_int_field(data, "skill", ctx, lo=2, hi=6),
        strength=_int_field(data, "strength", ctx, lo=1),
        ap=_int_field(data, "ap", ctx, lo=0),
        damage=_parse_damage(data, ctx),
        keywords=tuple(_validate_keyword(kw, ctx) for kw in data.get("keywords", [])),
    )


def _parse_profile(data: dict, ctx: str) -> Profile:
    invuln = data.get("invulnerable_save")
    if invuln is not None and (
        isinstance(invuln, bool) or not isinstance(invuln, int) or not 2 <= invuln <= 6
    ):
        raise FactionDataError(f"{ctx}: 'invulnerable_save' must be an int in 2..6, got {invuln!r}")
    return Profile(
        movement=_int_field(data, "movement", ctx, lo=0),
        toughness=_int_field(data, "toughness", ctx, lo=1),
        # A save of 7 means "no meaningful armour save" — ADR 0003's no-save branch handles it.
        save=_int_field(data, "save", ctx, lo=2, hi=7),
        wounds=_int_field(data, "wounds", ctx, lo=1),
        leadership=_int_field(data, "leadership", ctx, lo=1),
        objective_control=_int_field(data, "objective_control", ctx, lo=0),
        invulnerable_save=invuln,
    )


def _parse_loadout(data: dict, weapon_keys: set[str], ctx: str) -> tuple[str, ...]:
    loadout = data.get("default_loadout", {})
    for weapon_key, coverage in loadout.items():
        if weapon_key not in weapon_keys:
            raise FactionDataError(
                f"{ctx}.default_loadout: references unknown weapon {weapon_key!r}"
            )
        if coverage != "all":
            raise FactionDataError(
                f"{ctx}.default_loadout: only 'all' is supported in v1, got {coverage!r}"
            )
    return tuple(loadout)


def _parse_unit(faction_key: str, unit_key: str, data: dict) -> UnitDatasheet:
    ctx = f"{faction_key}.units.{unit_key}"
    weapons_data = _get(data, "weapons", ctx)
    if not isinstance(weapons_data, dict) or not weapons_data:
        raise FactionDataError(f"{ctx}: 'weapons' must be a non-empty object")
    size_ctx = f"{ctx}.unit_size"
    size = _get(data, "unit_size", ctx)
    lo = _int_field(size, "min", size_ctx, lo=1)
    hi = _int_field(size, "max", size_ctx, lo=1)
    default = _int_field(size, "default", size_ctx, lo=1)
    if not lo <= default <= hi:
        raise FactionDataError(f"{size_ctx}: need min <= default <= max, got {lo}/{default}/{hi}")
    return UnitDatasheet(
        key=unit_key,
        display_name=str(_get(data, "display_name", ctx)),
        faction=faction_key,
        profile=_parse_profile(_get(data, "profile", ctx), f"{ctx}.profile"),
        weapons=tuple(
            _parse_weapon(w_key, w_data, f"{ctx}.weapons.{w_key}")
            for w_key, w_data in weapons_data.items()
        ),
        default_model_count=default,
        min_model_count=lo,
        max_model_count=hi,
        default_loadout=_parse_loadout(data, set(weapons_data), ctx),
        abilities=tuple(str(a) for a in data.get("abilities", [])),
        notes=str(data.get("notes", "")),
    )


def _parse_faction(data: dict, source: str) -> dict[str, UnitDatasheet]:
    faction_key = str(_get(data, "faction", source))
    units = _get(data, "units", source)
    if not isinstance(units, dict) or not units:
        raise FactionDataError(f"{source}: 'units' must be a non-empty object")
    return {
        unit_key: _parse_unit(faction_key, unit_key, unit_data)
        for unit_key, unit_data in units.items()
    }


def load_faction(path: str | Path) -> dict[str, UnitDatasheet]:
    """Load a faction JSON file and return a dict of unit_key -> UnitDatasheet.

    Schema: `.claude/skills/add-unit/SKILL.md`. Raises `FactionDataError` (a
    `ValueError`) naming the faction/unit/weapon on any schema violation.
    Keywords are checked against the canonical list purely as a typo guard;
    the engine is NOT required to implement them — unimplemented keywords are
    inert until the phase-7 hook framework lands.
    """
    file = Path(path)
    try:
        data = json.loads(file.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        raise FactionDataError(f"{file.name}: not valid JSON ({exc})") from exc
    return _parse_faction(data, source=file.name)


def load_faction_by_name(name: str) -> dict[str, UnitDatasheet]:
    """Load a faction that ships inside the package, e.g. ``load_faction_by_name("tyranids")``."""
    factions_dir = resources.files("wh40k_tutorial") / "data" / "factions"
    candidate = factions_dir / f"{name}.json"
    if not candidate.is_file():
        available = sorted(
            p.name.removesuffix(".json")
            for p in factions_dir.iterdir()
            if p.name.endswith(".json")
        )
        raise FactionDataError(f"no faction named {name!r}; available: {', '.join(available)}")
    return _parse_faction(
        json.loads(candidate.read_text(encoding="utf-8")), source=f"{name}.json"
    )
