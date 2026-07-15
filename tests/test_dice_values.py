"""Tests for variable characteristics (`core.models.DiceValue`).

Damage may be a fixed integer or a small dice expression ("D3", "D6",
"D6+1"). Per CLAUDE.md, dice-affecting rules get distribution tests over
many rolls rather than single-outcome assertions.
"""

from __future__ import annotations

import random

import pytest

from wh40k_tutorial.core.models import DiceValue, FactionDataError, Weapon, load_faction


class TestParsing:
    @pytest.mark.parametrize(
        ("raw", "expected"),
        [
            (1, DiceValue(n_dice=0, die_sides=0, modifier=1)),
            (3, DiceValue(n_dice=0, die_sides=0, modifier=3)),
            ("D3", DiceValue(n_dice=1, die_sides=3, modifier=0)),
            ("D6", DiceValue(n_dice=1, die_sides=6, modifier=0)),
            ("d6", DiceValue(n_dice=1, die_sides=6, modifier=0)),
            ("D6+1", DiceValue(n_dice=1, die_sides=6, modifier=1)),
            ("2D6", DiceValue(n_dice=2, die_sides=6, modifier=0)),
            ("D6-1", DiceValue(n_dice=1, die_sides=6, modifier=-1)),
        ],
    )
    def test_coerce_accepts_ints_and_dice_strings(self, raw: object, expected: DiceValue) -> None:
        assert DiceValue.coerce(raw) == expected

    @pytest.mark.parametrize("raw", ["D4", "banana", "", "D", "6D", True, None, 1.5])
    def test_coerce_rejects_nonsense(self, raw: object) -> None:
        with pytest.raises(ValueError):
            DiceValue.coerce(raw)

    def test_coerce_is_idempotent(self) -> None:
        value = DiceValue.coerce("D3")
        assert DiceValue.coerce(value) is value

    @pytest.mark.parametrize(
        ("raw", "shown"),
        [(2, "2"), ("D3", "D3"), ("D6", "D6"), ("D6+2", "D6+2"), ("2D6", "2D6"), ("D6-1", "D6-1")],
    )
    def test_str_round_trips_the_notation(self, raw: object, shown: str) -> None:
        assert str(DiceValue.coerce(raw)) == shown


class TestStatistics:
    @pytest.mark.parametrize(
        ("raw", "average", "minimum", "maximum"),
        [
            (2, 2.0, 2, 2),
            ("D3", 2.0, 1, 3),
            ("D6", 3.5, 1, 6),
            ("D6+1", 4.5, 2, 7),
            ("2D6", 7.0, 2, 12),
        ],
    )
    def test_average_min_max(
        self, raw: object, average: float, minimum: int, maximum: int
    ) -> None:
        value = DiceValue.coerce(raw)
        assert value.average == pytest.approx(average)
        assert (value.minimum, value.maximum) == (minimum, maximum)

    def test_is_variable_distinguishes_dice_from_constants(self) -> None:
        assert DiceValue.coerce("D3").is_variable
        assert not DiceValue.coerce(3).is_variable

    @pytest.mark.parametrize("raw", ["D3", "D6", "D6+1"])
    def test_rolls_stay_in_range_and_average_out(self, raw: str) -> None:
        value = DiceValue.coerce(raw)
        rng = random.Random(4)
        rolls = [value.roll(rng) for _ in range(100_000)]
        assert min(rolls) == value.minimum
        assert max(rolls) == value.maximum
        assert sum(rolls) / len(rolls) == pytest.approx(value.average, abs=0.02)

    def test_d3_is_uniform_over_its_three_faces(self) -> None:
        rng = random.Random(9)
        rolls = [DiceValue.coerce("D3").roll(rng) for _ in range(60_000)]
        for face in (1, 2, 3):
            assert 0.32 < rolls.count(face) / len(rolls) < 0.35

    def test_fixed_values_never_touch_the_rng(self) -> None:
        # This is what keeps every pre-existing seeded scenario byte-identical
        # now that the damage step draws dice.
        untouched, control = random.Random(11), random.Random(11)
        fixed = DiceValue.fixed(2)
        assert [fixed.roll(untouched) for _ in range(5)] == [2] * 5
        assert untouched.random() == control.random()


class TestWeaponIntegration:
    def test_weapon_coerces_an_int_damage(self) -> None:
        weapon = Weapon("g", "G", "ranged", 24, 1, 4, 4, 0, 2)
        assert weapon.damage == DiceValue.fixed(2)

    def test_weapon_coerces_a_dice_string_damage(self) -> None:
        weapon = Weapon("g", "G", "ranged", 24, 1, 4, 4, 0, "D3")
        assert weapon.damage.is_variable
        assert str(weapon.damage) == "D3"


class TestLoaderValidation:
    def _faction(self, damage: object) -> str:
        return (
            '{"faction": "f", "display_name": "F", "units": {"u": {'
            '"display_name": "U", "profile": {"movement": 6, "toughness": 4, "save": 3,'
            ' "wounds": 1, "leadership": 6, "objective_control": 1},'
            '"unit_size": {"min": 1, "max": 1, "default": 1},'
            '"weapons": {"g": {"display_name": "G", "type": "ranged", "range": 24,'
            f' "attacks": 1, "skill": 4, "strength": 4, "ap": 0, "damage": {damage}}}}},'
            '"default_loadout": {"g": "all"}}}}'
        )

    def _load(self, tmp_path, damage: object):
        path = tmp_path / "f.json"
        path.write_text(self._faction(damage), encoding="utf-8")
        return load_faction(path)["u"].weapons[0].damage

    def test_loads_dice_damage(self, tmp_path) -> None:
        assert str(self._load(tmp_path, '"D3"')) == "D3"

    def test_loads_int_damage(self, tmp_path) -> None:
        assert str(self._load(tmp_path, "2")) == "2"

    @pytest.mark.parametrize("damage", ['"D4"', '"banana"', "0", "-1", '"D6-6"'])
    def test_rejects_bad_damage_naming_the_weapon(self, tmp_path, damage: str) -> None:
        with pytest.raises(FactionDataError, match="damage"):
            self._load(tmp_path, damage)
