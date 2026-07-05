"""Tests for the scenario loader (build phase 5).

Same philosophy as the faction-loader tests: a valid file round-trips into
frozen value types with datasheets resolved, and malformed data fails loudly
at load time with a message naming the culprit — never mid-battle.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from wh40k_tutorial.core.scenario import (
    BATTLEFIELD_HEIGHT,
    BATTLEFIELD_WIDTH,
    Scenario,
    ScenarioDataError,
    available_scenarios,
    load_scenario,
    load_scenario_by_id,
    opposing_side,
)

# ---------------------------------------------------------------------------
# Fixture helpers
# ---------------------------------------------------------------------------


def _base() -> dict:
    """A minimal valid scenario against the packaged factions."""
    return {
        "id": "test_scenario",
        "title": "Test Scenario",
        "teaches": "testing the loader.",
        "intro": "An intro.",
        "player_side": "attacker",
        "sides": {
            "attacker": {
                "faction": "space_marines",
                "units": [
                    {
                        "id": "marines_1",
                        "datasheet": "intercessor_squad",
                        "position": [3, 4],
                        "models": 5,
                    }
                ],
            },
            "defender": {
                "faction": "tyranids",
                "units": [
                    {
                        "id": "termagants_1",
                        "datasheet": "termagants",
                        "position": [9, 4],
                        "models": 10,
                    }
                ],
            },
        },
        "turns": [
            {"phase": "shooting", "active_side": "attacker", "narrate_before": "Fire."}
        ],
        "outro": "An outro.",
    }


def _load(tmp_path: Path, data: dict, filename: str | None = None) -> Scenario:
    name = filename or f"{data.get('id', 'broken')}.json"
    file = tmp_path / name
    file.write_text(json.dumps(data), encoding="utf-8")
    return load_scenario(file)


# ---------------------------------------------------------------------------
# Valid data round-trips
# ---------------------------------------------------------------------------


class TestValidScenario:
    def test_base_fixture_is_valid(self, tmp_path: Path) -> None:
        scenario = _load(tmp_path, _base())
        assert scenario.scenario_id == "test_scenario"
        assert scenario.title == "Test Scenario"
        assert scenario.player_side == "attacker"
        assert scenario.attacker.faction == "space_marines"
        assert scenario.defender.faction == "tyranids"

    def test_datasheets_are_resolved(self, tmp_path: Path) -> None:
        scenario = _load(tmp_path, _base())
        marines = scenario.attacker.units[0]
        gants = scenario.defender.units[0]
        assert marines.datasheet.display_name == "Intercessor Squad"
        assert marines.position == (3, 4)
        assert marines.models == 5
        assert gants.datasheet.display_name == "Termagants"
        assert gants.models == 10

    def test_turns_parse(self, tmp_path: Path) -> None:
        scenario = _load(tmp_path, _base())
        (turn,) = scenario.turns
        assert turn.phase == "shooting"
        assert turn.active_side == "attacker"
        assert turn.narrate_before == "Fire."
        assert turn.actions == ()

    def test_scripted_actions_parse_and_validate(self, tmp_path: Path) -> None:
        data = _base()
        data["turns"].append(
            {
                "phase": "shooting",
                "active_side": "defender",
                "actions": [
                    {"attacker": "termagants_1", "weapon": "fleshborer", "target": "marines_1"}
                ],
            }
        )
        scenario = _load(tmp_path, data)
        (action,) = scenario.turns[1].actions
        assert action.attacker_unit_id == "termagants_1"
        assert action.weapon == "fleshborer"
        assert action.target_unit_id == "marines_1"

    def test_side_lookup_and_opposing(self, tmp_path: Path) -> None:
        scenario = _load(tmp_path, _base())
        assert scenario.side("defender").faction == "tyranids"
        assert opposing_side("attacker") == "defender"
        assert opposing_side("defender") == "attacker"
        with pytest.raises(KeyError):
            scenario.side("bystander")
        with pytest.raises(KeyError):
            opposing_side("bystander")


class TestPackagedScenarios:
    def test_all_five_scenarios_are_listed(self) -> None:
        assert [s.scenario_id for s in available_scenarios()] == [
            "01_first_shots",
            "02_tougher_targets",
            "03_piercing_armour",
            "04_lethal_hits",
            "05_sustained_hits",
        ]

    def test_tougher_targets_offers_two_toughness_values(self) -> None:
        scenario = load_scenario_by_id("02_tougher_targets")
        defenders = scenario.defender.units
        toughness = sorted(u.datasheet.profile.toughness for u in defenders)
        assert toughness == [4, 5]  # the whole lesson is this contrast
        assert len(scenario.turns) == 2

    def test_piercing_armour_defender_has_the_invulnerable(self) -> None:
        scenario = load_scenario_by_id("03_piercing_armour")
        rangers = scenario.defender.units[0].datasheet
        assert rangers.profile.invulnerable_save == 5
        assert scenario.player_side == "attacker"

    def test_lethal_hits_attacker_carries_the_keyword(self) -> None:
        scenario = load_scenario_by_id("04_lethal_hits")
        flayer = scenario.attacker.units[0].datasheet.weapons[0]
        assert "lethal_hits" in flayer.keywords

    def test_sustained_hits_equips_the_tesla_override(self) -> None:
        scenario = load_scenario_by_id("05_sustained_hits")
        immortals = scenario.attacker.units[0]
        assert immortals.loadout == ("tesla_carbine",)
        tesla = next(w for w in immortals.datasheet.weapons if w.name == "tesla_carbine")
        assert "sustained_hits_2" in tesla.keywords
        assert scenario.player_side == "attacker"
        assert len(scenario.turns) == 2

    def test_first_shots_loads_by_id(self) -> None:
        scenario = load_scenario_by_id("01_first_shots")
        assert scenario.title == "First Shots"
        assert scenario.player_side == "attacker"
        assert scenario.attacker.units[0].datasheet.display_name == "Intercessor Squad"
        assert scenario.defender.units[0].models == 10
        assert scenario.turns[0].phase == "shooting"

    def test_unknown_id_names_the_available_ones(self) -> None:
        with pytest.raises(ScenarioDataError, match="01_first_shots"):
            load_scenario_by_id("99_does_not_exist")

    def test_available_scenarios_includes_first_shots(self) -> None:
        ids = [s.scenario_id for s in available_scenarios()]
        assert "01_first_shots" in ids
        assert ids == sorted(ids)  # file-name order = intended play order


# ---------------------------------------------------------------------------
# Malformed data fails loudly, naming the culprit
# ---------------------------------------------------------------------------


class TestMalformedScenario:
    def test_invalid_json(self, tmp_path: Path) -> None:
        file = tmp_path / "broken.json"
        file.write_text("{not json", encoding="utf-8")
        with pytest.raises(ScenarioDataError, match="not valid JSON"):
            load_scenario(file)

    def test_missing_required_field(self, tmp_path: Path) -> None:
        data = _base()
        del data["title"]
        with pytest.raises(ScenarioDataError, match="'title'"):
            _load(tmp_path, data)

    def test_id_must_match_filename(self, tmp_path: Path) -> None:
        with pytest.raises(ScenarioDataError, match="must match the file name"):
            _load(tmp_path, _base(), filename="something_else.json")

    def test_bad_player_side(self, tmp_path: Path) -> None:
        data = _base()
        data["player_side"] = "spectator"
        with pytest.raises(ScenarioDataError, match="player_side"):
            _load(tmp_path, data)

    def test_missing_side(self, tmp_path: Path) -> None:
        data = _base()
        del data["sides"]["defender"]
        with pytest.raises(ScenarioDataError, match="defender"):
            _load(tmp_path, data)

    def test_unknown_faction(self, tmp_path: Path) -> None:
        data = _base()
        data["sides"]["defender"]["faction"] = "squats"
        with pytest.raises(ScenarioDataError, match="squats"):
            _load(tmp_path, data)

    def test_unknown_datasheet_names_available(self, tmp_path: Path) -> None:
        data = _base()
        data["sides"]["attacker"]["units"][0]["datasheet"] = "terminator_squad"
        with pytest.raises(ScenarioDataError, match=r"terminator_squad.*intercessor_squad"):
            _load(tmp_path, data)

    @pytest.mark.parametrize("models", [4, 11])  # Intercessors are 5..10
    def test_models_outside_unit_size(self, tmp_path: Path, models: int) -> None:
        data = _base()
        data["sides"]["attacker"]["units"][0]["models"] = models
        with pytest.raises(ScenarioDataError, match="unit size"):
            _load(tmp_path, data)

    def test_position_off_grid(self, tmp_path: Path) -> None:
        data = _base()
        data["sides"]["attacker"]["units"][0]["position"] = [BATTLEFIELD_WIDTH, 4]
        with pytest.raises(
            ScenarioDataError, match=f"{BATTLEFIELD_WIDTH}x{BATTLEFIELD_HEIGHT}"
        ):
            _load(tmp_path, data)

    def test_position_malformed(self, tmp_path: Path) -> None:
        data = _base()
        data["sides"]["attacker"]["units"][0]["position"] = [3]
        with pytest.raises(ScenarioDataError, match="two-integer"):
            _load(tmp_path, data)

    def test_duplicate_unit_id_across_sides(self, tmp_path: Path) -> None:
        data = _base()
        data["sides"]["defender"]["units"][0]["id"] = "marines_1"
        with pytest.raises(ScenarioDataError, match="more than once"):
            _load(tmp_path, data)

    def test_duplicate_position(self, tmp_path: Path) -> None:
        data = _base()
        data["sides"]["defender"]["units"][0]["position"] = [3, 4]
        with pytest.raises(ScenarioDataError, match="share position"):
            _load(tmp_path, data)

    def test_empty_turns(self, tmp_path: Path) -> None:
        data = _base()
        data["turns"] = []
        with pytest.raises(ScenarioDataError, match="turns"):
            _load(tmp_path, data)

    def test_unsupported_phase_mentions_v1_scope(self, tmp_path: Path) -> None:
        data = _base()
        data["turns"][0]["phase"] = "movement"
        with pytest.raises(ScenarioDataError, match=r"movement.*v1"):
            _load(tmp_path, data)

    def test_bad_active_side(self, tmp_path: Path) -> None:
        data = _base()
        data["turns"][0]["active_side"] = "everyone"
        with pytest.raises(ScenarioDataError, match="active_side"):
            _load(tmp_path, data)


class TestMalformedScriptedActions:
    def _with_action(self, action: dict) -> dict:
        data = _base()
        data["turns"][0]["actions"] = [action]
        return data

    def test_attacker_not_on_active_side(self, tmp_path: Path) -> None:
        action = {"attacker": "termagants_1", "weapon": "fleshborer", "target": "marines_1"}
        with pytest.raises(ScenarioDataError, match="not a unit on the active"):
            _load(tmp_path, self._with_action(action))

    def test_unknown_weapon(self, tmp_path: Path) -> None:
        action = {"attacker": "marines_1", "weapon": "plasma_gun", "target": "termagants_1"}
        with pytest.raises(ScenarioDataError, match="plasma_gun"):
            _load(tmp_path, self._with_action(action))

    def test_melee_weapon_rejected(self, tmp_path: Path) -> None:
        action = {
            "attacker": "marines_1",
            "weapon": "close_combat_weapon",
            "target": "termagants_1",
        }
        with pytest.raises(ScenarioDataError, match="melee"):
            _load(tmp_path, self._with_action(action))

    def test_unknown_target(self, tmp_path: Path) -> None:
        action = {"attacker": "marines_1", "weapon": "bolt_rifle", "target": "hive_tyrant_1"}
        with pytest.raises(ScenarioDataError, match="hive_tyrant_1"):
            _load(tmp_path, self._with_action(action))


# ---------------------------------------------------------------------------
# Per-scenario loadout overrides
# ---------------------------------------------------------------------------


def _with_necron_attacker(data: dict) -> dict:
    """Swap the attacker for Immortals, who carry two ranged guns."""
    data["sides"]["attacker"] = {
        "faction": "necrons",
        "units": [
            {"id": "immortals_1", "datasheet": "immortals", "position": [3, 4], "models": 5}
        ],
    }
    return data


class TestLoadoutOverride:
    def test_no_override_leaves_loadout_empty(self, tmp_path: Path) -> None:
        scenario = _load(tmp_path, _base())
        assert scenario.attacker.units[0].loadout == ()

    def test_valid_override_round_trips(self, tmp_path: Path) -> None:
        data = _with_necron_attacker(_base())
        data["sides"]["attacker"]["units"][0]["loadout"] = {"tesla_carbine": "all"}
        scenario = _load(tmp_path, data)
        assert scenario.attacker.units[0].loadout == ("tesla_carbine",)

    def test_unknown_weapon_names_the_available_ones(self, tmp_path: Path) -> None:
        data = _with_necron_attacker(_base())
        data["sides"]["attacker"]["units"][0]["loadout"] = {"doomsday_cannon": "all"}
        with pytest.raises(ScenarioDataError, match=r"doomsday_cannon.*tesla_carbine"):
            _load(tmp_path, data)

    def test_partial_coverage_rejected_in_v1(self, tmp_path: Path) -> None:
        data = _with_necron_attacker(_base())
        data["sides"]["attacker"]["units"][0]["loadout"] = {"tesla_carbine": "half"}
        with pytest.raises(ScenarioDataError, match="only 'all'"):
            _load(tmp_path, data)

    def test_empty_override_rejected(self, tmp_path: Path) -> None:
        data = _with_necron_attacker(_base())
        data["sides"]["attacker"]["units"][0]["loadout"] = {}
        with pytest.raises(ScenarioDataError, match="non-empty"):
            _load(tmp_path, data)

    def test_melee_only_override_rejected(self, tmp_path: Path) -> None:
        data = _with_necron_attacker(_base())
        data["sides"]["attacker"]["units"][0]["loadout"] = {"close_combat_weapon": "all"}
        with pytest.raises(ScenarioDataError, match="at least one ranged"):
            _load(tmp_path, data)

    def test_scripted_action_outside_the_override_rejected(self, tmp_path: Path) -> None:
        data = _with_necron_attacker(_base())
        data["sides"]["attacker"]["units"][0]["loadout"] = {"tesla_carbine": "all"}
        data["turns"][0]["actions"] = [
            {"attacker": "immortals_1", "weapon": "gauss_blaster", "target": "termagants_1"}
        ]
        with pytest.raises(ScenarioDataError, match=r"not\s+carrying.*tesla_carbine"):
            _load(tmp_path, data)

    def test_scripted_action_outside_the_default_loadout_rejected(
        self, tmp_path: Path
    ) -> None:
        # No override: Immortals default to the gauss blaster, so a script
        # firing the tesla carbine is an authoring inconsistency.
        data = _with_necron_attacker(_base())
        data["turns"][0]["actions"] = [
            {"attacker": "immortals_1", "weapon": "tesla_carbine", "target": "termagants_1"}
        ]
        with pytest.raises(ScenarioDataError, match=r"not\s+carrying.*gauss_blaster"):
            _load(tmp_path, data)

    def test_scripted_action_inside_the_override_accepted(self, tmp_path: Path) -> None:
        data = _with_necron_attacker(_base())
        data["sides"]["attacker"]["units"][0]["loadout"] = {"tesla_carbine": "all"}
        data["turns"][0]["actions"] = [
            {"attacker": "immortals_1", "weapon": "tesla_carbine", "target": "termagants_1"}
        ]
        (action,) = _load(tmp_path, data).turns[0].actions
        assert action.weapon == "tesla_carbine"
