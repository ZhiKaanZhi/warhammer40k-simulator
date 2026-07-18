"""Tests for the scenario runner (build phase 5).

Follows the project's dice-testing template: exact-outcome tests use a
seeded ``random.Random``. The headline test is a scripted-vs-scripted run of
the packaged scenario 01: with the same seed, the engine's volley must equal
a direct `resolve_shooting` call, and the battlefield state must update to
exactly what the returned `DamageStep` says.
"""

from __future__ import annotations

import random

import pytest

from wh40k_tutorial.core.combat import resolve_shooting
from wh40k_tutorial.core.models import Profile, UnitDatasheet, Weapon, load_faction_by_name
from wh40k_tutorial.core.scenario import (
    Scenario,
    ScenarioSide,
    ScenarioTurn,
    ScenarioUnit,
    load_scenario_by_id,
)
from wh40k_tutorial.engine import BattleState, EngineError, VolleyEvent, run_scenario
from wh40k_tutorial.strategies.base import Action
from wh40k_tutorial.strategies.heuristic import HeuristicStrategy
from wh40k_tutorial.strategies.scripted import ScriptedStrategy, scripted_actions_for

MARINES = load_faction_by_name("space_marines")["intercessor_squad"]
GANTS = load_faction_by_name("tyranids")["termagants"]
IMMORTALS = load_faction_by_name("necrons")["immortals"]
BOLT_RIFLE = next(w for w in MARINES.weapons if w.name == "bolt_rifle")

SHOOT = "shoot"


def _scenario(
    attacker_units: tuple[ScenarioUnit, ...],
    defender_units: tuple[ScenarioUnit, ...],
    turns: tuple[ScenarioTurn, ...],
) -> Scenario:
    """Hand-built scenario for engine tests (bypasses the JSON loader on purpose)."""
    return Scenario(
        scenario_id="engine_test",
        title="Engine Test",
        teaches="engine behavior.",
        intro="i",
        player_side="attacker",
        attacker=ScenarioSide("attacker", "space_marines", attacker_units),
        defender=ScenarioSide("defender", "tyranids", defender_units),
        turns=turns,
        outro="o",
    )


def _marines(unit_id: str, x: int, *, models: int = 5) -> ScenarioUnit:
    return ScenarioUnit(unit_id, MARINES, (x, 0), models)


def _gants(unit_id: str, x: int, *, models: int = 10) -> ScenarioUnit:
    return ScenarioUnit(unit_id, GANTS, (x, 4), models)


ONE_ATTACKER_TURN = (ScenarioTurn("shooting", "attacker"),)


# ---------------------------------------------------------------------------
# The headline end-to-end run: scripted vs scripted, seeded
# ---------------------------------------------------------------------------


class TestScriptedVsScriptedEndToEnd:
    SEED = 1234

    def test_first_shots_resolves_and_updates_state(self) -> None:
        scenario = load_scenario_by_id("01_first_shots")
        strategies = {
            "attacker": ScriptedStrategy(
                [Action(SHOOT, "marines_1", "bolt_rifle", "termagants_1")]
            ),
            "defender": ScriptedStrategy([]),  # never consulted: 01 has one attacker turn
        }
        events: list[VolleyEvent] = []
        turn_starts: list[int] = []
        state = run_scenario(
            scenario,
            strategies,
            rng=random.Random(self.SEED),
            on_turn_start=lambda n, turn: turn_starts.append(n),
            on_volley=events.append,
        )

        # The engine's volley must equal a direct pipeline call with the same seed.
        expected = resolve_shooting(
            MARINES, 5, BOLT_RIFLE, GANTS, 1, 10, rng=random.Random(self.SEED)
        )
        assert turn_starts == [1]
        (event,) = events
        assert event.turn == 1
        assert event.phase == "shooting"
        assert event.action.attacker_unit_id == "marines_1"
        assert event.result == expected

        # State updated from the DamageStep, and only for the target.
        gants = state.units["termagants_1"]
        assert gants.models == expected.damage.models_remaining
        assert gants.wounds_on_lead == expected.damage.wounds_remaining_on_lead
        marines = state.units["marines_1"]
        assert marines.models == 5
        assert marines.wounds_on_lead == MARINES.profile.wounds
        assert "marines_1" in state.shot_this_phase

    def test_two_volleys_thread_defender_state(self) -> None:
        """The second volley must see the first one's DamageStep output.

        A 2-wound defender makes the threading visible: the lead model can be
        left mid-wound by volley one, and volley two must start from there.
        """
        tough_sheet = UnitDatasheet(
            key="warriors",
            display_name="Test Warriors",
            faction="tyranids",
            profile=Profile(
                movement=5, toughness=4, save=4, wounds=2, leadership=7, objective_control=2
            ),
            weapons=(BOLT_RIFLE,),
            default_model_count=10,
        )
        defender = ScenarioUnit("warriors_1", tough_sheet, (9, 0), 10)
        scenario = _scenario(
            (_marines("m1", 0), _marines("m2", 1)), (defender,), ONE_ATTACKER_TURN
        )
        strategies = {
            "attacker": ScriptedStrategy(
                [
                    Action(SHOOT, "m1", "bolt_rifle", "warriors_1"),
                    Action(SHOOT, "m2", "bolt_rifle", "warriors_1"),
                ]
            ),
            "defender": ScriptedStrategy([]),
        }
        events: list[VolleyEvent] = []
        seed = 7
        state = run_scenario(
            scenario, strategies, rng=random.Random(seed), on_volley=events.append
        )

        # Replay both volleys off one rng stream, exactly as the engine does.
        rng = random.Random(seed)
        first = resolve_shooting(MARINES, 5, BOLT_RIFLE, tough_sheet, 2, 10, rng=rng)
        assert first.damage.models_remaining > 0, "seed 7 must leave survivors"
        second = resolve_shooting(
            MARINES,
            5,
            BOLT_RIFLE,
            tough_sheet,
            first.damage.wounds_remaining_on_lead,
            first.damage.models_remaining,
            rng=rng,
        )
        assert [e.result for e in events] == [first, second]
        warriors = state.units["warriors_1"]
        assert warriors.models == second.damage.models_remaining
        assert warriors.wounds_on_lead == second.damage.wounds_remaining_on_lead


# ---------------------------------------------------------------------------
# Loop behavior
# ---------------------------------------------------------------------------


class TestTurnLoop:
    def test_battle_ends_when_a_side_is_wiped(self) -> None:
        """Turn 2 never starts once the defender is tabled in turn 1.

        Seed 3 is verified below: five Marines' 10 shots kill the lone
        1-wound Termagant. The defender's empty script would raise if the
        engine wrongly asked it for a turn-2 action.
        """
        scenario = _scenario(
            (_marines("m1", 0),),
            (_gants("g1", 9, models=1),),
            (
                ScenarioTurn("shooting", "attacker"),
                ScenarioTurn("shooting", "defender"),
            ),
        )
        strategies = {
            "attacker": ScriptedStrategy([Action(SHOOT, "m1", "bolt_rifle", "g1")]),
            "defender": ScriptedStrategy([]),
        }
        turn_starts: list[int] = []
        state = run_scenario(
            scenario,
            strategies,
            rng=random.Random(3),
            on_turn_start=lambda n, turn: turn_starts.append(n),
        )
        assert state.units["g1"].destroyed, "seed 3 must table the lone Termagant"
        assert turn_starts == [1]
        assert state.side_wiped("defender")
        assert state.battle_over

    def test_melee_only_side_skips_its_shooting_phase(self) -> None:
        melee_sheet = UnitDatasheet(
            key="boys",
            display_name="Melee Boys",
            faction="orks",
            profile=Profile(
                movement=6, toughness=5, save=5, wounds=1, leadership=7, objective_control=2
            ),
            weapons=(
                Weapon(
                    name="choppa",
                    display_name="Choppa",
                    type="melee",
                    range=0,
                    attacks=2,
                    skill=3,
                    strength=4,
                    ap=0,
                    damage=1,
                ),
            ),
            default_model_count=10,
        )
        scenario = _scenario(
            (ScenarioUnit("boys_1", melee_sheet, (0, 0), 10),),
            (_gants("g1", 9),),
            ONE_ATTACKER_TURN,
        )
        # An empty script would raise if the engine wrongly asked for an action.
        strategies = {
            "attacker": ScriptedStrategy([]),
            "defender": ScriptedStrategy([]),
        }
        events: list[VolleyEvent] = []
        state = run_scenario(scenario, strategies, on_volley=events.append)
        assert events == []
        assert state.units["g1"].models == 10

    def test_missing_strategy_is_an_engine_error(self) -> None:
        scenario = _scenario((_marines("m1", 0),), (_gants("g1", 9),), ONE_ATTACKER_TURN)
        with pytest.raises(EngineError, match="defender"):
            run_scenario(scenario, {"attacker": ScriptedStrategy([])})

    def test_battle_state_from_scenario_snapshot(self) -> None:
        scenario = _scenario((_marines("m1", 0),), (_gants("g1", 9),), ONE_ATTACKER_TURN)
        state = BattleState.from_scenario(scenario)
        assert state.units["m1"].wounds_on_lead == MARINES.profile.wounds
        snap = state.snapshot()
        assert snap.unit("g1").models == 10
        assert not snap.unit("m1").has_shot


# ---------------------------------------------------------------------------
# Illegal actions from a strategy fail loudly
# ---------------------------------------------------------------------------


class TestActionValidation:
    def _run(self, *actions: Action, defenders: tuple[ScenarioUnit, ...] | None = None):
        scenario = _scenario(
            (_marines("m1", 0), _marines("m2", 1)),
            defenders or (_gants("g1", 9), _gants("g2", 10)),
            ONE_ATTACKER_TURN,
        )
        strategies = {
            "attacker": ScriptedStrategy(list(actions)),
            "defender": ScriptedStrategy([]),
        }
        return run_scenario(scenario, strategies, rng=random.Random(0))

    def test_unknown_action_kind(self) -> None:
        with pytest.raises(EngineError, match="'charge'"):
            self._run(Action("charge", "m1", "bolt_rifle", "g1"))

    def test_unknown_attacker(self) -> None:
        with pytest.raises(EngineError, match="'ghost'"):
            self._run(Action(SHOOT, "ghost", "bolt_rifle", "g1"))

    def test_attacker_on_wrong_side(self) -> None:
        with pytest.raises(EngineError, match="not the active side"):
            self._run(Action(SHOOT, "g1", "fleshborer", "m1"))

    def test_unknown_weapon(self) -> None:
        with pytest.raises(EngineError, match="'plasma_gun'"):
            self._run(Action(SHOOT, "m1", "plasma_gun", "g1"))

    def test_melee_weapon_cannot_shoot(self) -> None:
        with pytest.raises(EngineError, match="melee"):
            self._run(Action(SHOOT, "m1", "close_combat_weapon", "g1"))

    def test_target_on_own_side(self) -> None:
        with pytest.raises(EngineError, match="your own"):
            self._run(Action(SHOOT, "m1", "bolt_rifle", "m2"))

    def test_shot_beyond_weapon_range(self) -> None:
        """04.02 via ADR 0007: a Fleshborer (18" = 9 squares) cannot cross 11.

        m_near keeps the shooter eligible, so the engine asks — and the
        script overreaches for m_far."""
        scenario = _scenario(
            (ScenarioUnit("g_shooter", GANTS, (0, 0), 10),),
            (
                ScenarioUnit("m_near", MARINES, (5, 4), 5),
                ScenarioUnit("m_far", MARINES, (11, 7), 5),
            ),
            ONE_ATTACKER_TURN,
        )
        strategies = {
            "attacker": ScriptedStrategy(
                [Action(SHOOT, "g_shooter", "fleshborer", "m_far")]
            ),
            "defender": ScriptedStrategy([]),
        }
        with pytest.raises(EngineError, match=r'22" .*beyond.*18" range'):
            run_scenario(scenario, strategies, rng=random.Random(0))

    def test_engaged_shooter_cannot_shoot(self) -> None:
        """10.04: an engaged unit cannot shoot (no [CLOSE-QUARTERS] weapons).

        m_free is eligible, so the engine asks — and the script answers with
        the engaged m_stuck, which the validation must reject."""
        scenario = _scenario(
            (
                ScenarioUnit("m_free", MARINES, (0, 4), 5),
                ScenarioUnit("m_stuck", MARINES, (7, 4), 5),
            ),
            (
                ScenarioUnit("g_close", GANTS, (8, 4), 10),
                ScenarioUnit("g_far", GANTS, (9, 0), 10),
            ),
            ONE_ATTACKER_TURN,
        )
        strategies = {
            "attacker": ScriptedStrategy(
                [Action(SHOOT, "m_stuck", "bolt_rifle", "g_far")]
            ),
            "defender": ScriptedStrategy([]),
        }
        with pytest.raises(EngineError, match="engaged and cannot shoot"):
            run_scenario(scenario, strategies, rng=random.Random(0))

    def test_shooting_cannot_target_an_engaged_unit(self) -> None:
        """04.02: you cannot shoot into a combat — the target must be unengaged.

        g_far keeps m_free eligible, so the engine asks — and the script aims
        at g1, who is locked in with m_stuck."""
        scenario = _scenario(
            (
                ScenarioUnit("m_free", MARINES, (0, 4), 5),
                ScenarioUnit("m_stuck", MARINES, (7, 4), 5),
            ),
            (
                ScenarioUnit("g1", GANTS, (8, 4), 10),
                ScenarioUnit("g_far", GANTS, (9, 0), 10),
            ),
            ONE_ATTACKER_TURN,
        )
        strategies = {
            "attacker": ScriptedStrategy([Action(SHOOT, "m_free", "bolt_rifle", "g1")]),
            "defender": ScriptedStrategy([]),
        }
        with pytest.raises(EngineError, match="cannot target an engaged unit"):
            run_scenario(scenario, strategies, rng=random.Random(0))

    def test_unknown_target(self) -> None:
        with pytest.raises(EngineError, match="'ghost'"):
            self._run(Action(SHOOT, "m1", "bolt_rifle", "ghost"))

    def test_unit_cannot_shoot_twice_in_a_phase(self) -> None:
        with pytest.raises(EngineError, match="already shot"):
            self._run(
                Action(SHOOT, "m1", "bolt_rifle", "g1"),
                Action(SHOOT, "m1", "bolt_rifle", "g2"),
            )

    def test_destroyed_target_is_rejected(self) -> None:
        """Seed 0 is verified in-test: m1's volley tables the lone Termagant;
        m2's scripted shot at the corpse must then be rejected (g2 survives,
        so the phase is still running)."""
        with pytest.raises(EngineError, match="already destroyed"):
            self._run(
                Action(SHOOT, "m1", "bolt_rifle", "g1"),
                Action(SHOOT, "m2", "bolt_rifle", "g1"),
                defenders=(_gants("g1", 9, models=1), _gants("g2", 10)),
            )

    def test_loadout_override_threads_to_snapshots_and_menus(self) -> None:
        immortals = ScenarioUnit(
            "immortals_1", IMMORTALS, (0, 0), 5, loadout=("tesla_carbine",)
        )
        scenario = _scenario((immortals,), (_gants("d1", 9),), ONE_ATTACKER_TURN)
        snap = BattleState.from_scenario(scenario).snapshot()
        unit = snap.unit("immortals_1")
        assert unit.loadout == ("tesla_carbine",)
        assert [w.name for w in unit.ranged_weapons] == ["tesla_carbine"]

    def test_weapon_outside_the_loadout_is_an_engine_error(self) -> None:
        immortals = ScenarioUnit(
            "immortals_1", IMMORTALS, (0, 0), 5, loadout=("tesla_carbine",)
        )
        scenario = _scenario((immortals,), (_gants("d1", 9),), ONE_ATTACKER_TURN)
        rogue = ScriptedStrategy(
            [Action(SHOOT, "immortals_1", "gauss_blaster", "d1")]
        )
        idle = ScriptedStrategy([])
        with pytest.raises(EngineError, match=r"not\s+carrying.*tesla_carbine"):
            run_scenario(
                scenario,
                {"attacker": rogue, "defender": idle},
                rng=random.Random(0),
            )

    def test_weapon_inside_the_loadout_resolves(self) -> None:
        immortals = ScenarioUnit(
            "immortals_1", IMMORTALS, (0, 0), 5, loadout=("tesla_carbine",)
        )
        scenario = _scenario((immortals,), (_gants("d1", 9),), ONE_ATTACKER_TURN)
        events: list[VolleyEvent] = []
        run_scenario(
            scenario,
            {
                "attacker": ScriptedStrategy(
                    [Action(SHOOT, "immortals_1", "tesla_carbine", "d1")]
                ),
                "defender": ScriptedStrategy([]),
            },
            rng=random.Random(7),
            on_volley=events.append,
        )
        (event,) = events
        assert event.result.attack.weapon.name == "tesla_carbine"

    def test_seed_zero_really_tables_the_lone_termagant(self) -> None:
        result = resolve_shooting(MARINES, 5, BOLT_RIFLE, GANTS, 1, 1, rng=random.Random(0))
        assert result.damage.models_remaining == 0


# ---------------------------------------------------------------------------
# The fight phase: alternation, mandatory fighting, casualty timing
# ---------------------------------------------------------------------------

FIGHT = "fight"
MARINE_BLADE = "close_combat_weapon"
GANT_CLAWS = "claws_and_teeth"

FIGHT_TURN = (ScenarioTurn("fight", "attacker"),)


def _fight_scenario(
    attacker_units: tuple[ScenarioUnit, ...],
    defender_units: tuple[ScenarioUnit, ...],
    turns: tuple[ScenarioTurn, ...] = FIGHT_TURN,
) -> Scenario:
    return _scenario(attacker_units, defender_units, turns)


def _run_fight(
    scenario: Scenario,
    attacker_script: list[Action],
    defender_script: list[Action],
    *,
    seed: int = 7,
) -> tuple[BattleState, list[VolleyEvent]]:
    events: list[VolleyEvent] = []
    state = run_scenario(
        scenario,
        {
            "attacker": ScriptedStrategy(attacker_script),
            "defender": ScriptedStrategy(defender_script),
        },
        rng=random.Random(seed),
        on_volley=events.append,
    )
    return state, events


class TestFightPhase:
    def test_active_side_picks_first_then_players_alternate(self) -> None:
        """Two separate combats: the side whose turn it is picks first, then
        the pick passes across the table after every fight (12.04)."""
        scenario = _fight_scenario(
            (
                ScenarioUnit("m1", MARINES, (4, 4), 5),
                ScenarioUnit("m2", MARINES, (4, 6), 5),
            ),
            (
                ScenarioUnit("g1", GANTS, (5, 4), 10),
                ScenarioUnit("g2", GANTS, (5, 6), 10),
            ),
        )
        _, events = _run_fight(
            scenario,
            [Action(FIGHT, "m1", MARINE_BLADE, "g1"), Action(FIGHT, "m2", MARINE_BLADE, "g2")],
            [Action(FIGHT, "g1", GANT_CLAWS, "m1"), Action(FIGHT, "g2", GANT_CLAWS, "m2")],
        )
        assert [e.action.attacker_unit_id for e in events] == ["m1", "g1", "m2", "g2"]
        assert all(e.phase == "fight" and e.action.kind == "fight" for e in events)

    def test_a_side_with_nothing_eligible_passes_back(self) -> None:
        """Attacker has two engaged units, defender one: once the defender's
        script is spent the pick returns to the attacker (12.04's pass rule)."""
        scenario = _fight_scenario(
            (
                ScenarioUnit("m1", MARINES, (4, 4), 5),
                ScenarioUnit("m2", MARINES, (6, 4), 5),
            ),
            (ScenarioUnit("g1", GANTS, (5, 4), 20),),
        )
        _, events = _run_fight(
            scenario,
            [Action(FIGHT, "m1", MARINE_BLADE, "g1"), Action(FIGHT, "m2", MARINE_BLADE, "g1")],
            [Action(FIGHT, "g1", GANT_CLAWS, "m1")],
        )
        assert [e.action.attacker_unit_id for e in events] == ["m1", "g1", "m2"]

    def test_casualties_come_off_before_the_return_swing(self) -> None:
        """The phase's central lesson: a unit selected to fight later swings
        with only the models that survived the earlier fights."""
        scenario = _fight_scenario(
            (ScenarioUnit("m1", MARINES, (4, 4), 5),),
            (ScenarioUnit("g1", GANTS, (5, 4), 10),),
        )
        _, events = _run_fight(
            scenario,
            [Action(FIGHT, "m1", MARINE_BLADE, "g1")],
            [Action(FIGHT, "g1", GANT_CLAWS, "m1")],
        )
        first, second = events
        assert first.action.attacker_unit_id == "m1"
        assert second.action.attacker_unit_id == "g1"
        # Whatever the dice said, the return swing uses the survivor count...
        assert second.result.attack.attacker_models == first.result.models_remaining
        # ...and at this seed Marines do kill Termagants, so it is a real cut.
        assert first.result.models_remaining < 10

    def test_a_unit_fights_once_per_phase(self) -> None:
        scenario = _fight_scenario(
            (
                ScenarioUnit("m1", MARINES, (4, 4), 5),
                ScenarioUnit("m2", MARINES, (6, 4), 5),
            ),
            (ScenarioUnit("g1", GANTS, (5, 4), 20),),
        )
        with pytest.raises(EngineError, match="already fought"):
            _run_fight(
                scenario,
                [Action(FIGHT, "m1", MARINE_BLADE, "g1"), Action(FIGHT, "m1", MARINE_BLADE, "g1")],
                [Action(FIGHT, "g1", GANT_CLAWS, "m1")],
            )

    def test_melee_must_target_an_engaged_unit(self) -> None:
        scenario = _fight_scenario(
            (ScenarioUnit("m1", MARINES, (4, 4), 5),),
            (
                ScenarioUnit("g1", GANTS, (5, 4), 10),
                ScenarioUnit("g2", GANTS, (9, 4), 10),
            ),
        )
        with pytest.raises(EngineError, match="engagement range"):
            _run_fight(scenario, [Action(FIGHT, "m1", MARINE_BLADE, "g2")], [])

    def test_shoot_actions_are_not_legal_in_a_fight_phase(self) -> None:
        scenario = _fight_scenario(
            (ScenarioUnit("m1", MARINES, (4, 4), 5),),
            (ScenarioUnit("g1", GANTS, (5, 4), 10),),
        )
        with pytest.raises(EngineError, match="not legal in a fight phase"):
            _run_fight(scenario, [Action(SHOOT, "m1", "bolt_rifle", "g1")], [])

    def test_fight_actions_are_not_legal_in_a_shooting_phase(self) -> None:
        # Unengaged and in range, so the shooting phase asks the strategy —
        # which hands back a fight action for the kind check to reject.
        scenario = _scenario(
            (ScenarioUnit("m1", MARINES, (2, 4), 5),),
            (ScenarioUnit("g1", GANTS, (7, 4), 10),),
            ONE_ATTACKER_TURN,
        )
        with pytest.raises(EngineError, match="not legal in a shooting phase"):
            _run_fight(scenario, [Action(FIGHT, "m1", MARINE_BLADE, "g1")], [])

    def test_ranged_weapons_cannot_be_swung(self) -> None:
        scenario = _fight_scenario(
            (ScenarioUnit("m1", MARINES, (4, 4), 5),),
            (ScenarioUnit("g1", GANTS, (5, 4), 10),),
        )
        with pytest.raises(EngineError, match="cannot be swung"):
            _run_fight(scenario, [Action(FIGHT, "m1", "bolt_rifle", "g1")], [])

    def test_shot_and_fought_flags_reset_between_turns(self) -> None:
        """The same unit may fight in one turn and shoot in the next — the
        per-phase activation sets are per turn entry, and having fought does
        not spend a later shooting activation.

        (Fight-THEN-shoot, because with static positions the reverse is now
        rule-impossible: a unit unengaged enough to shoot can never become
        engaged without movement. Here the fight wipes the engaging Termagant
        — the single model cannot survive five Marines at this seed — which
        frees m1 to shoot the second, distant unit next turn.)
        """
        scenario = _scenario(
            (ScenarioUnit("m1", MARINES, (5, 4), 5),),
            (
                ScenarioUnit("g1", GANTS, (6, 4), 1),
                ScenarioUnit("g2", GANTS, (9, 4), 10),
            ),
            (ScenarioTurn("fight", "attacker"), ScenarioTurn("shooting", "attacker")),
        )
        _, events = _run_fight(
            scenario,
            [
                Action(FIGHT, "m1", MARINE_BLADE, "g1"),
                Action(SHOOT, "m1", "bolt_rifle", "g2"),
            ],
            [],
        )
        assert [e.action.kind for e in events] == ["fight", "shoot"]
        assert [e.action.attacker_unit_id for e in events] == ["m1", "m1"]

    def test_fight_phase_ends_the_moment_a_side_is_wiped(self) -> None:
        """A single Termagant cannot survive five Marines at this seed: the
        return swing never happens and the extra script is never consulted."""
        scenario = _fight_scenario(
            (ScenarioUnit("m1", MARINES, (4, 4), 5),),
            (ScenarioUnit("g1", GANTS, (5, 4), 1),),
        )
        state, events = _run_fight(
            scenario,
            [Action(FIGHT, "m1", MARINE_BLADE, "g1")],
            [Action(FIGHT, "g1", GANT_CLAWS, "m1")],
        )
        assert len(events) == 1
        assert state.side_wiped("defender")


class TestFirstBloodScenarioMath:
    """Scenario 08 at its demo seed: the strike-order lesson, pinned."""

    SEED = 20

    def test_the_return_swing_counts_survivors_only(self) -> None:
        scenario = load_scenario_by_id("08_first_blood")
        strategies = {
            "attacker": ScriptedStrategy(
                [Action(FIGHT, "boyz_1", "choppa", "marines_1")]
            ),
            "defender": ScriptedStrategy(scripted_actions_for(scenario, "defender")),
        }
        events: list[VolleyEvent] = []
        state = run_scenario(
            scenario, strategies, rng=random.Random(self.SEED), on_volley=events.append
        )

        boyz_swing, marine_answer = events
        assert boyz_swing.action.attacker_unit_id == "boyz_1"
        assert marine_answer.action.attacker_unit_id == "marines_1"
        # The identity that IS the lesson, true at any seed:
        assert (
            marine_answer.result.attack.attacker_models
            == boyz_swing.result.models_remaining
        )
        # ...and the demo seed's specific story: 2 Marines slain (+1 wounded),
        # so 3 answer with 9 dice instead of 15, and 3 Boyz fall to them.
        assert boyz_swing.result.models_remaining == 3
        assert boyz_swing.result.wounds_remaining_on_lead == 1
        assert marine_answer.result.attack.total_attacks == 9
        assert marine_answer.result.models_remaining == 7
        assert state.units["boyz_1"].models == 7
        assert state.units["marines_1"].models == 3


class TestPickYourFightsScenarioMath:
    """Scenario 09 at its demo seed: the ordering decision, both branches."""

    SEED = 15

    def _run(self, player_script: list[Action]) -> list[VolleyEvent]:
        scenario = load_scenario_by_id("09_pick_your_fights")
        events: list[VolleyEvent] = []
        run_scenario(
            scenario,
            {
                "attacker": ScriptedStrategy(player_script),
                "defender": HeuristicStrategy(),
            },
            rng=random.Random(self.SEED),
            on_volley=events.append,
        )
        return events

    def test_right_pick_defangs_the_immortals(self) -> None:
        events = self._run(
            [
                Action(FIGHT, "boyz_left", "choppa", "immortals_1"),
                Action(FIGHT, "boyz_right", "choppa", "warriors_1"),
            ]
        )
        assert [e.action.attacker_unit_id for e in events] == [
            "boyz_left",
            "immortals_1",  # the AI's free pick: still its deadliest option
            "boyz_right",
            "warriors_1",
        ]
        f1, f2, f3, f4 = events
        # 4 Immortals fall first, so their answer is 12 dice, not 20...
        assert f1.result.models_remaining == 6
        assert f2.result.attack.total_attacks == 12
        # ...and every enemy swing in the phase comes from survivors only.
        assert f2.result.attack.attacker_models == f1.result.models_remaining
        assert f4.result.attack.attacker_models == f3.result.models_remaining
        assert f3.result.models_remaining == 4
        assert f4.result.attack.total_attacks == 4

    def test_wrong_pick_lets_the_immortals_swing_at_full_strength(self) -> None:
        events = self._run(
            [
                Action(FIGHT, "boyz_right", "choppa", "warriors_1"),
                Action(FIGHT, "boyz_left", "choppa", "immortals_1"),
            ]
        )
        # The AI's free pick is the untouched Immortals: all 20 dice.
        ai_first = events[1]
        assert ai_first.action.attacker_unit_id == "immortals_1"
        assert ai_first.result.attack.attacker_models == 10
        assert ai_first.result.attack.total_attacks == 20
