"""Tests for the faction JSON loader (build phase 2).

Two layers:

- the real packaged data files must load and round-trip exact values
- malformed data must fail loudly at load time, with a message naming the
  offending unit/weapon — bad data should never reach the combat pipeline
"""

from __future__ import annotations

import json
from importlib import resources
from pathlib import Path

import pytest

from wh40k_tutorial.core.models import (
    FactionDataError,
    UnitDatasheet,
    load_faction,
    load_faction_by_name,
)

# ---------------------------------------------------------------------------
# Helpers for building malformed fixtures
# ---------------------------------------------------------------------------


def _minimal_faction() -> dict:
    """A smallest-possible valid faction dict; tests mutate it to break one thing."""
    return {
        "faction": "test_faction",
        "display_name": "Test Faction",
        "units": {
            "test_unit": {
                "display_name": "Test Unit",
                "profile": {
                    "movement": 6,
                    "toughness": 4,
                    "save": 3,
                    "wounds": 2,
                    "leadership": 6,
                    "objective_control": 2,
                },
                "unit_size": {"min": 1, "max": 5, "default": 3},
                "weapons": {
                    "test_gun": {
                        "display_name": "Test Gun",
                        "type": "ranged",
                        "range": 12,
                        "attacks": 1,
                        "skill": 4,
                        "strength": 4,
                        "ap": 0,
                        "damage": 1,
                        "keywords": [],
                    }
                },
                "default_loadout": {"test_gun": "all"},
                "abilities": [],
                "notes": "",
            }
        },
    }


def _load(tmp_path: Path, data: dict) -> dict[str, UnitDatasheet]:
    file = tmp_path / "test_faction.json"
    file.write_text(json.dumps(data), encoding="utf-8")
    return load_faction(file)


# ---------------------------------------------------------------------------
# The packaged data files
# ---------------------------------------------------------------------------


class TestPackagedFactions:
    def test_minimal_fixture_is_valid(self, tmp_path: Path) -> None:
        # Guards the test helpers themselves: every malformed test below
        # relies on this baseline actually loading.
        units = _load(tmp_path, _minimal_faction())
        assert set(units) == {"test_unit"}

    def test_intercessors_round_trip_exactly(self) -> None:
        units = load_faction_by_name("space_marines")
        squad = units["intercessor_squad"]
        assert squad.display_name == "Intercessor Squad"
        assert squad.faction == "space_marines"
        p = squad.profile
        assert (p.movement, p.toughness, p.save, p.wounds) == (6, 4, 3, 2)
        assert p.invulnerable_save is None
        rifle = {w.name: w for w in squad.weapons}["bolt_rifle"]
        assert rifle.display_name == "Bolt Rifle"
        assert (rifle.range, rifle.attacks, rifle.skill) == (24, 2, 3)
        assert (rifle.strength, rifle.ap, rifle.damage) == (4, 1, 1)
        assert rifle.keywords == ("assault",)
        assert squad.default_model_count == 5
        assert squad.default_loadout == ("bolt_rifle",)

    def test_termagants_round_trip_exactly(self) -> None:
        units = load_faction_by_name("tyranids")
        swarm = units["termagants"]
        p = swarm.profile
        assert (p.toughness, p.save, p.wounds) == (3, 5, 1)
        borer = {w.name: w for w in swarm.weapons}["fleshborer"]
        assert (borer.range, borer.attacks, borer.skill) == (18, 1, 4)
        assert (borer.strength, borer.ap, borer.damage) == (4, 0, 1)
        assert swarm.default_model_count == 10
        melee = {w.name: w for w in swarm.weapons}["claws_and_teeth"]
        assert melee.type == "melee"
        assert melee.range == 0

    def test_unknown_faction_lists_what_exists(self) -> None:
        with pytest.raises(FactionDataError, match="space_marines"):
            load_faction_by_name("squats")


class TestScenarioReferencesResolve:
    def test_first_shots_datasheets_exist(self) -> None:
        scenario_file = (
            resources.files("wh40k_tutorial") / "data" / "scenarios" / "01_first_shots.json"
        )
        scenario = json.loads(scenario_file.read_text(encoding="utf-8"))
        for side in scenario["sides"].values():
            units = load_faction_by_name(side["faction"])
            for entry in side["units"]:
                assert entry["datasheet"] in units, (
                    f"scenario references {entry['datasheet']!r}, "
                    f"missing from {side['faction']}"
                )
                assert entry["models"] >= 1


# ---------------------------------------------------------------------------
# Malformed data fails loudly, naming the culprit
# ---------------------------------------------------------------------------


class TestMalformedData:
    def test_negative_ap(self, tmp_path: Path) -> None:
        data = _minimal_faction()
        data["units"]["test_unit"]["weapons"]["test_gun"]["ap"] = -1
        with pytest.raises(FactionDataError, match=r"'ap'.*test_gun|test_gun.*'ap'"):
            _load(tmp_path, data)

    def test_unknown_keyword_is_rejected_as_typo(self, tmp_path: Path) -> None:
        data = _minimal_faction()
        # "sustained_hits" without its number is exactly the typo we guard against
        data["units"]["test_unit"]["weapons"]["test_gun"]["keywords"] = ["sustained_hits"]
        with pytest.raises(FactionDataError, match="unknown weapon keyword"):
            _load(tmp_path, data)

    def test_known_keywords_pass_even_if_engine_ignores_them(self, tmp_path: Path) -> None:
        data = _minimal_faction()
        data["units"]["test_unit"]["weapons"]["test_gun"]["keywords"] = [
            "assault",
            "sustained_hits_2",
            "anti_infantry_4",
        ]
        units = _load(tmp_path, data)
        gun = units["test_unit"].weapons[0]
        assert gun.keywords == ("assault", "sustained_hits_2", "anti_infantry_4")

    def test_bad_weapon_type(self, tmp_path: Path) -> None:
        data = _minimal_faction()
        data["units"]["test_unit"]["weapons"]["test_gun"]["type"] = "psychic"
        with pytest.raises(FactionDataError, match="'type'"):
            _load(tmp_path, data)

    def test_variable_attacks_not_supported_yet(self, tmp_path: Path) -> None:
        data = _minimal_faction()
        data["units"]["test_unit"]["weapons"]["test_gun"]["attacks"] = "D6"
        with pytest.raises(FactionDataError, match="variable Attacks"):
            _load(tmp_path, data)

    def test_missing_required_field(self, tmp_path: Path) -> None:
        data = _minimal_faction()
        del data["units"]["test_unit"]["weapons"]["test_gun"]["strength"]
        with pytest.raises(FactionDataError, match="missing required field 'strength'"):
            _load(tmp_path, data)

    def test_loadout_referencing_unknown_weapon(self, tmp_path: Path) -> None:
        data = _minimal_faction()
        data["units"]["test_unit"]["default_loadout"] = {"plasma_gun": "all"}
        with pytest.raises(FactionDataError, match="default_loadout"):
            _load(tmp_path, data)

    def test_unit_size_default_out_of_range(self, tmp_path: Path) -> None:
        data = _minimal_faction()
        data["units"]["test_unit"]["unit_size"]["default"] = 99
        with pytest.raises(FactionDataError, match="min <= default <= max"):
            _load(tmp_path, data)

    def test_melee_weapon_with_nonzero_range(self, tmp_path: Path) -> None:
        data = _minimal_faction()
        gun = data["units"]["test_unit"]["weapons"]["test_gun"]
        gun["type"] = "melee"
        gun["range"] = 12
        with pytest.raises(FactionDataError, match="melee weapons must have range 0"):
            _load(tmp_path, data)

    def test_bool_is_not_an_integer(self, tmp_path: Path) -> None:
        data = _minimal_faction()
        data["units"]["test_unit"]["weapons"]["test_gun"]["attacks"] = True
        with pytest.raises(FactionDataError, match="must be an integer"):
            _load(tmp_path, data)

    def test_invalid_json_names_the_file(self, tmp_path: Path) -> None:
        file = tmp_path / "broken.json"
        file.write_text("{not json", encoding="utf-8")
        with pytest.raises(FactionDataError, match=r"broken\.json"):
            load_faction(file)
