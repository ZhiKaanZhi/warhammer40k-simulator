"""Tests for the Strategy layer (build phase 5).

Covers the fleshed-out `GameState` snapshot (eligibility rules the engine and
strategies share), `ScriptedStrategy` replay semantics, and `HumanStrategy`
driven through Click's `CliRunner` with fed input.
"""

from __future__ import annotations

import click
import pytest
from click.testing import CliRunner

from wh40k_tutorial.core.models import Profile, UnitDatasheet, Weapon, load_faction_by_name
from wh40k_tutorial.core.scenario import (
    Scenario,
    ScenarioSide,
    ScenarioTurn,
    ScenarioUnit,
)
from wh40k_tutorial.core.scenario import (
    ScenarioAction as SA,
)
from wh40k_tutorial.strategies.base import Action, GameState, UnitSnapshot
from wh40k_tutorial.strategies.human import HumanStrategy
from wh40k_tutorial.strategies.scripted import (
    ScriptedStrategy,
    ScriptExhaustedError,
    scripted_actions_for,
)

MARINES = load_faction_by_name("space_marines")["intercessor_squad"]
GANTS = load_faction_by_name("tyranids")["termagants"]


def _weapon(name: str, *, type_: str = "ranged", range_: int | None = None) -> Weapon:
    return Weapon(
        name=name,
        display_name=name.replace("_", " ").title(),
        type=type_,
        range=(0 if type_ == "melee" else 12) if range_ is None else range_,
        attacks=1,
        skill=4,
        strength=4,
        ap=0,
        damage=1,
    )


def _sheet(key: str, *weapons: Weapon, loadout: tuple[str, ...] = ()) -> UnitDatasheet:
    return UnitDatasheet(
        key=key,
        display_name=key.replace("_", " ").title(),
        faction="test",
        profile=Profile(
            movement=6, toughness=4, save=4, wounds=1, leadership=6, objective_control=2
        ),
        weapons=weapons,
        default_model_count=5,
        default_loadout=loadout,
    )


def _snap(
    unit_id: str,
    side: str,
    sheet: UnitDatasheet,
    *,
    models: int | None = None,
    position: tuple[int, int] | None = None,
    has_shot: bool = False,
    has_fought: bool = False,
    loadout: tuple[str, ...] = (),
) -> UnitSnapshot:
    resolved_models = sheet.default_model_count if models is None else models
    # Distances matter now (ADR 0007): unless a test places a unit itself,
    # attackers stand at (2, 4) and defenders at (7, 4) — 5 squares = 10"
    # apart, inside the fixture's 12" weapons' range and safely unengaged.
    if position is None:
        position = (2, 4) if side == "attacker" else (7, 4)
    return UnitSnapshot(
        unit_id=unit_id,
        side=side,
        datasheet=sheet,
        position=position,
        models=resolved_models,
        wounds_on_lead=sheet.profile.wounds if resolved_models > 0 else 0,
        has_shot=has_shot,
        has_fought=has_fought,
        loadout=loadout,
    )


def _state(
    *units: UnitSnapshot, active_side: str = "attacker", phase: str = "shooting"
) -> GameState:
    return GameState(turn=1, phase=phase, active_side=active_side, units=units)


# ---------------------------------------------------------------------------
# GameState: the shared eligibility rules
# ---------------------------------------------------------------------------


class TestGameState:
    def test_eligible_shooters_excludes_dead_shot_and_unarmed(self) -> None:
        melee_only = _sheet("choppa_boys", _weapon("choppa", type_="melee"))
        state = _state(
            _snap("a1", "attacker", MARINES),
            _snap("a2", "attacker", MARINES, has_shot=True),
            _snap("a3", "attacker", MARINES, models=0),
            _snap("a4", "attacker", melee_only),
            _snap("d1", "defender", GANTS),
        )
        assert [u.unit_id for u in state.eligible_shooters()] == ["a1"]

    def test_eligible_shooters_excludes_the_engaged(self) -> None:
        """10.04: an engaged unit cannot shoot — it never reaches the menu."""
        state = _state(
            _snap("a_free", "attacker", MARINES, position=(2, 4)),
            _snap("a_stuck", "attacker", MARINES, position=(6, 4)),
            _snap("d_close", "defender", GANTS, position=(7, 4)),   # engages a_stuck
            _snap("d_open", "defender", GANTS, position=(2, 0)),    # a_free's target
        )
        assert [u.unit_id for u in state.eligible_shooters()] == ["a_free"]

    def test_eligible_shooters_need_a_target_in_range(self) -> None:
        """A shooter with nothing legal to shoot is skipped, not deadlocked."""
        gunners = _sheet("gunners", _weapon("test_gun"))  # 12" = 6 squares
        state = _state(
            _snap("a1", "attacker", gunners, position=(0, 0)),
            _snap("d1", "defender", GANTS, position=(7, 4)),  # 7 squares = 14" > 12"
        )
        assert state.eligible_shooters() == ()

    def test_shootable_targets_filter_range_and_engagement(self) -> None:
        """04.02: within the weapon's range and unengaged — nothing else."""
        gunners = _sheet("gunners", _weapon("test_gun"))  # 12" = 6 squares
        state = _state(
            _snap("a1", "attacker", gunners, position=(2, 4)),
            _snap("a2", "attacker", MARINES, position=(6, 1)),
            _snap("d_near", "defender", GANTS, position=(6, 4)),     # 4 squares: legal
            _snap("d_far", "defender", GANTS, position=(11, 4)),     # 9 squares = 18" > 12"
            _snap("d_stuck", "defender", GANTS, position=(6, 0)),    # engaged with a2
            _snap("d_dead", "defender", GANTS, position=(4, 0), models=0),
        )
        shooter = state.unit("a1")
        weapon = shooter.ranged_weapons[0]
        assert [u.unit_id for u in state.shootable_targets(shooter, weapon)] == ["d_near"]

    def test_surviving_enemies_excludes_destroyed(self) -> None:
        state = _state(
            _snap("a1", "attacker", MARINES),
            _snap("d1", "defender", GANTS),
            _snap("d2", "defender", GANTS, models=0),
        )
        assert [u.unit_id for u in state.surviving_enemies()] == ["d1"]

    def test_unit_lookup(self) -> None:
        state = _state(_snap("a1", "attacker", MARINES))
        assert state.unit("a1").datasheet is MARINES
        with pytest.raises(KeyError, match="ghost"):
            state.unit("ghost")

    def test_ranged_weapons_follow_loadout_order(self) -> None:
        pistol, rifle, sword = _weapon("pistol"), _weapon("rifle"), _weapon("sword", type_="melee")
        sheet = _sheet("kitted_squad", sword, rifle, pistol, loadout=("rifle", "sword", "pistol"))
        snap = _snap("a1", "attacker", sheet)
        assert [w.name for w in snap.ranged_weapons] == ["rifle", "pistol"]

    def test_ranged_weapons_honor_a_scenario_override(self) -> None:
        pistol, rifle = _weapon("pistol"), _weapon("rifle")
        sheet = _sheet("kitted_squad", rifle, pistol, loadout=("rifle",))
        snap = _snap("a1", "attacker", sheet, loadout=("pistol",))
        assert [w.name for w in snap.ranged_weapons] == ["pistol"]

    def test_ranged_weapons_fall_back_to_all_ranged_without_loadout(self) -> None:
        pistol, sword = _weapon("pistol"), _weapon("sword", type_="melee")
        snap = _snap("a1", "attacker", _sheet("plain_squad", sword, pistol))
        assert [w.name for w in snap.ranged_weapons] == ["pistol"]


# ---------------------------------------------------------------------------
# ScriptedStrategy
# ---------------------------------------------------------------------------


class TestScriptedStrategy:
    def test_replays_actions_in_order(self) -> None:
        first = Action("shoot", "a1", "bolt_rifle", "d1")
        second = Action("shoot", "a2", "bolt_rifle", "d1")
        strategy = ScriptedStrategy([first, second])
        state = _state(_snap("a1", "attacker", MARINES), _snap("d1", "defender", GANTS))
        assert strategy.choose_action(state) is first
        assert strategy.choose_action(state) is second

    def test_exhausted_script_fails_loudly(self) -> None:
        strategy = ScriptedStrategy([])
        state = _state(_snap("a1", "attacker", MARINES), _snap("d1", "defender", GANTS))
        with pytest.raises(ScriptExhaustedError, match=r"attacker.*turn 1"):
            strategy.choose_action(state)

    def test_scripted_actions_for_flattens_one_side_in_play_order(self) -> None:
        marines_unit = ScenarioUnit("m1", MARINES, (0, 0), 5)
        gants_unit = ScenarioUnit("g1", GANTS, (5, 5), 10)
        scenario = Scenario(
            scenario_id="s",
            title="t",
            teaches="x",
            intro="i",
            player_side="attacker",
            attacker=ScenarioSide("attacker", "space_marines", (marines_unit,)),
            defender=ScenarioSide("defender", "tyranids", (gants_unit,)),
            turns=(
                ScenarioTurn("shooting", "attacker", actions=(SA("m1", "bolt_rifle", "g1"),)),
                ScenarioTurn("shooting", "defender", actions=(SA("g1", "fleshborer", "m1"),)),
                ScenarioTurn("shooting", "defender", actions=(SA("g1", "fleshborer", "m1"),)),
            ),
            outro="o",
        )
        actions = scripted_actions_for(scenario, "defender")
        assert len(actions) == 2
        assert all(a.kind == "shoot" for a in actions)
        assert all(a.attacker_unit_id == "g1" for a in actions)
        assert all(a.weapon_key == "fleshborer" for a in actions)
        assert scripted_actions_for(scenario, "attacker") == (
            Action("shoot", "m1", "bolt_rifle", "g1"),
        )


# ---------------------------------------------------------------------------
# HumanStrategy (driven through Click's CliRunner)
# ---------------------------------------------------------------------------


def _choose(state: GameState, input_text: str) -> tuple[Action, str]:
    """Run HumanStrategy.choose_action inside a Click context with fed stdin."""
    captured: dict[str, Action] = {}

    @click.command()
    def cmd() -> None:
        captured["action"] = HumanStrategy().choose_action(state)

    result = CliRunner().invoke(cmd, input=input_text)
    assert result.exit_code == 0, result.output
    return captured["action"], result.output


class TestHumanStrategy:
    def test_single_options_are_announced_not_prompted(self) -> None:
        state = _state(_snap("a1", "attacker", MARINES), _snap("d1", "defender", GANTS))
        action, output = _choose(state, input_text="")
        assert action == Action("shoot", "a1", "bolt_rifle", "d1")
        assert "Unit to shoot with: Intercessor Squad" in output
        assert "Weapon: Bolt Rifle" in output
        assert "Target: Termagants" in output
        assert "Your choice" not in output  # nothing was prompted

    def test_multiple_options_are_prompted_by_number(self) -> None:
        rifle, pistol = _weapon("rifle"), _weapon("pistol")
        squad = _sheet("kitted_squad", rifle, pistol, loadout=("rifle", "pistol"))
        state = _state(
            _snap("a1", "attacker", MARINES),
            _snap("a2", "attacker", squad),
            _snap("d1", "defender", GANTS),
            _snap("d2", "defender", GANTS),
        )
        # Pick the 2nd shooter, its 2nd weapon, the 1st target.
        action, output = _choose(state, input_text="2\n2\n1\n")
        assert action == Action("shoot", "a2", "pistol", "d1")
        assert "Pick a unit to shoot with:" in output
        assert "2. Kitted Squad (5 models)" in output
        assert "Pick a weapon:" in output
        assert "Pick a target:" in output

    def test_weapon_menu_drops_weapons_with_no_legal_target(self) -> None:
        """A gun whose every target is out of reach is not offered (04.02):
        the 4" pistol cannot touch the target 5 squares (10") away, so only
        the 12" rifle appears — announced, not prompted."""
        rifle, pistol = _weapon("rifle"), _weapon("pistol", range_=4)
        squad = _sheet("kitted_squad", rifle, pistol, loadout=("rifle", "pistol"))
        state = _state(
            _snap("a1", "attacker", squad, position=(2, 4)),
            _snap("d1", "defender", GANTS, position=(7, 4)),
        )
        action, output = _choose(state, input_text="")
        assert action == Action("shoot", "a1", "rifle", "d1")
        assert "Weapon: Rifle" in output
        assert "Pistol" not in output

    def test_out_of_range_pick_is_reprompted(self) -> None:
        state = _state(
            _snap("a1", "attacker", MARINES),
            _snap("a2", "attacker", MARINES),
            _snap("d1", "defender", GANTS),
        )
        action, output = _choose(state, input_text="9\n1\n")
        assert action.attacker_unit_id == "a1"
        assert output.count("Your choice") >= 2  # rejected, asked again


# ---------------------------------------------------------------------------
# Fight-phase eligibility and menus
# ---------------------------------------------------------------------------


class TestFightEligibility:
    def test_eligible_fighters_require_engagement_life_arms_and_a_free_turn(self) -> None:
        state = _state(
            _snap("engaged", "attacker", MARINES, position=(4, 4)),
            _snap("fought", "attacker", MARINES, position=(4, 5), has_fought=True),
            _snap("far", "attacker", MARINES, position=(0, 0)),
            _snap("dead", "attacker", MARINES, position=(4, 3), models=0),
            _snap("g1", "defender", GANTS, position=(5, 4)),
            phase="fight",
        )
        assert [u.unit_id for u in state.eligible_fighters("attacker")] == ["engaged"]
        # ...and eligibility is per side, not per active_side:
        assert [u.unit_id for u in state.eligible_fighters("defender")] == ["g1"]

    def test_engaged_enemies_filters_by_adjacency_and_life(self) -> None:
        state = _state(
            _snap("m1", "attacker", MARINES, position=(4, 4)),
            _snap("near", "defender", GANTS, position=(5, 5)),
            _snap("far", "defender", GANTS, position=(8, 4)),
            _snap("dead", "defender", GANTS, position=(4, 5), models=0),
            phase="fight",
        )
        m1 = state.unit("m1")
        assert [u.unit_id for u in state.engaged_enemies(m1)] == ["near"]

    def test_melee_weapons_survive_a_guns_only_loadout_override(self) -> None:
        """A scenario override that swaps rifles must not disarm the unit in
        melee — models always keep their close-combat weapon (04.01)."""
        snap = _snap("m1", "attacker", MARINES, loadout=("bolt_rifle",))
        assert [w.name for w in snap.melee_weapons] == ["close_combat_weapon"]

    def test_melee_weapons_honor_a_melee_entry_in_the_override(self) -> None:
        blade, claw = _weapon("blade", type_="melee"), _weapon("claw", type_="melee")
        sheet = _sheet("brawlers", blade, claw, loadout=("blade", "claw"))
        snap = _snap("b1", "attacker", sheet, loadout=("claw",))
        assert [w.name for w in snap.melee_weapons] == ["claw"]


class TestScriptedFightActions:
    def test_fight_turn_actions_carry_the_fight_kind_and_their_own_side(self) -> None:
        """scripted_actions_for attributes a fight-turn action by its acting
        unit's side, because both sides act in a fight turn."""
        scenario = Scenario(
            scenario_id="s",
            title="t",
            teaches="x.",
            intro="i",
            player_side="attacker",
            attacker=ScenarioSide(
                "attacker", "space_marines", (ScenarioUnit("m1", MARINES, (4, 4), 5),)
            ),
            defender=ScenarioSide(
                "defender", "tyranids", (ScenarioUnit("g1", GANTS, (5, 4), 10),)
            ),
            turns=(
                ScenarioTurn(
                    "fight",
                    "attacker",
                    actions=(SA("g1", "claws_and_teeth", "m1"),),
                ),
            ),
            outro="o",
        )
        assert scripted_actions_for(scenario, "defender") == (
            Action("fight", "g1", "claws_and_teeth", "m1"),
        )
        assert scripted_actions_for(scenario, "attacker") == ()


class TestHumanStrategyFights:
    def test_single_option_fight_is_announced_not_prompted(self) -> None:
        state = _state(
            _snap("m1", "attacker", MARINES, position=(4, 4)),
            _snap("g1", "defender", GANTS, position=(5, 4)),
            phase="fight",
        )
        action, output = _choose(state, input_text="")
        assert action == Action("fight", "m1", "close_combat_weapon", "g1")
        assert "Unit to fight with: Intercessor Squad (5 models) — fighting Termagants" in output
        assert "Melee weapon: Close Combat Weapon" in output
        assert "Target: Termagants" in output
        assert "Your choice" not in output

    def test_only_engaged_enemies_are_offered_as_targets(self) -> None:
        state = _state(
            _snap("m1", "attacker", MARINES, position=(4, 4)),
            _snap("near_a", "defender", GANTS, position=(5, 4)),
            _snap("near_b", "defender", GANTS, position=(5, 5)),
            _snap("far", "defender", GANTS, position=(9, 4)),
            phase="fight",
        )
        action, output = _choose(state, input_text="2\n")
        assert action == Action("fight", "m1", "close_combat_weapon", "near_b")
        assert "Pick a target:" in output
        # The target menu offers the two engaged units, not the far one; the
        # fighter announce line also names both, hence four mentions total.
        assert output.count("Termagants") == 4

    def test_fight_menu_names_each_units_opponent(self) -> None:
        """Two identical mobs are only tellable apart by WHO they are fighting."""
        state = _state(
            _snap("left", "attacker", MARINES, position=(2, 2)),
            _snap("right", "attacker", MARINES, position=(6, 6)),
            _snap("g_left", "defender", GANTS, position=(2, 3)),
            _snap("g_right", "defender", GANTS, position=(6, 7)),
            phase="fight",
        )
        action, output = _choose(state, input_text="2\n")
        assert action.attacker_unit_id == "right"
        assert "— fighting Termagants" in output
