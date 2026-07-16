"""End-to-end CLI tests for `wh40k list` and `wh40k play` (build phase 5).

`play` is exercised through Click's `CliRunner`. Scenario 01 offers exactly
one shooter, one weapon, and one target, so `HumanStrategy` announces each
choice instead of prompting — the run needs no stdin. The seeded run's
casualty numbers are checked against the engine itself (same seed), so the
test asserts real behavior without hard-coding platform-independent dice.
"""

from __future__ import annotations

import random

from click.testing import CliRunner

from wh40k_tutorial import __version__
from wh40k_tutorial.cli import main
from wh40k_tutorial.core.scenario import load_scenario_by_id
from wh40k_tutorial.engine import run_scenario
from wh40k_tutorial.strategies.base import Action
from wh40k_tutorial.strategies.scripted import ScriptedStrategy

SEED = 42


class TestList:
    def test_lists_first_shots(self) -> None:
        result = CliRunner().invoke(main, ["list"])
        assert result.exit_code == 0, result.output
        assert "01_first_shots" in result.output
        assert "First Shots" in result.output
        assert "teaches the four-step combat sequence" in result.output


class TestPlay:
    def _expected_survivors(self) -> int:
        scenario = load_scenario_by_id("01_first_shots")
        strategies = {
            "attacker": ScriptedStrategy(
                [Action("shoot", "marines_1", "bolt_rifle", "termagants_1")]
            ),
            "defender": ScriptedStrategy([]),
        }
        state = run_scenario(scenario, strategies, rng=random.Random(SEED))
        return state.units["termagants_1"].models

    def test_plays_first_shots_end_to_end(self) -> None:
        result = CliRunner().invoke(main, ["play", "01_first_shots", "--seed", str(SEED)])
        assert result.exit_code == 0, result.output
        out = result.output

        # Framing: title, teaches, intro, outro.
        assert "=== First Shots ===" in out
        assert "You play the attacker." in out
        assert "swarm of Tyranid Termagants" in out
        assert "Every shooting attack in 40k follows this exact sequence." in out

        # The shell rendered from live state, and the choices were announced.
        assert "Battlefield" in out
        assert "Action Log" in out
        assert "Unit to shoot with: Intercessor Squad (5 models)" in out
        assert "Weapon: Bolt Rifle" in out
        assert "Target: Termagants (10 models)" in out

        # The volley account, step by step, with the seed-determined outcome.
        assert "Turn 1 — Intercessor Squad fires Bolt Rifle at Termagants." in out
        assert "ATTACKS: 5 models x 2 attacks = 10 dice" in out
        assert "HIT:     need 3+" in out
        assert "WOUND:   need 3+ (S4 vs T3)" in out
        assert "SAVE:    need 6+ (armour 5+, AP -1)" in out
        survivors = self._expected_survivors()
        assert f"{survivors} of 10 remain" in out
        assert f"Termagants — {survivors} models" in out  # final battlefield legend

    def test_unknown_scenario_names_the_available_ones(self) -> None:
        result = CliRunner().invoke(main, ["play", "99_nope"])
        assert result.exit_code != 0
        assert "no scenario named '99_nope'" in result.output
        assert "01_first_shots" in result.output

    # ------------------------------------------------------------------
    # Phase 6: the narrator in the play loop
    # ------------------------------------------------------------------

    def test_every_fact_line_carries_its_rule(self) -> None:
        result = CliRunner().invoke(
            main, ["play", "01_first_shots", "--seed", str(SEED)], input="\n"
        )
        assert result.exit_code == 0, result.output
        out = result.output

        # One inline rule per pipeline step, arrowed under its fact line.
        assert out.count("↳") == 5
        assert "the pool is 5 x 2 = 10 dice" in out
        assert "Ballistic Skill, printed on the weapon profile" in out
        assert "Strength 4 beats the target's Toughness 3" in out
        assert "AP -1 is armour-piercing and worsens it to 6+" in out
        assert "single wound apiece" in out

        # The offer of a deeper rule, and the final rules panel filled in.
        assert "Deeper rule?" in out
        assert "The rules behind" in out  # panel heading (wraps in the column)

    def test_why_prints_the_full_rule_and_bad_input_reprompts(self) -> None:
        result = CliRunner().invoke(
            main,
            ["play", "01_first_shots", "--seed", str(SEED)],
            input="banana\nwhy save?\n\n",
        )
        assert result.exit_code == 0, result.output
        out = result.output
        assert "Pick one of: attacks/hit/wound/save/damage" in out
        assert "SAVE — the full rule:" in out
        assert "invulnerable save" in out
        assert "no lucky-six rule" in out

    def test_play_survives_end_of_input_at_the_why_prompt(self) -> None:
        # No input at all: the why prompt hits end-of-input and the battle
        # must still run to the outro instead of aborting.
        result = CliRunner().invoke(main, ["play", "01_first_shots", "--seed", str(SEED)])
        assert result.exit_code == 0, result.output
        assert "Every shooting attack in 40k follows this exact sequence." in result.output


class TestOtherCommands:
    def test_version(self) -> None:
        result = CliRunner().invoke(main, ["version"])
        assert result.exit_code == 0
        assert __version__ in result.output

    def test_demo_still_renders(self) -> None:
        result = CliRunner().invoke(main, ["demo"])
        assert result.exit_code == 0, result.output
        assert "Battlefield" in result.output


class TestAbilityScenarioEndToEnd:
    """Scenario 04 through the real CLI: the ability must be visible in the
    dice lines and narrated, at the pinned demo seed."""

    def test_lethal_hits_shows_up_in_the_volley_and_the_teaching(self) -> None:
        result = CliRunner().invoke(
            main, ["play", "04_lethal_hits", "--seed", "5"], input="\n\n"
        )
        assert result.exit_code == 0, result.output
        out = result.output
        assert "auto from lethal crits" in out          # the fact line annotation
        assert "Lethal Hits let" in out                  # the narrator's sentence
        assert "still gets saves" in out                 # ...and its saves caveat
        assert "auto-wound is not an auto-kill" in out   # the outro's core lesson

    def test_devastating_wounds_shows_mortals_and_the_one_model_cap(self) -> None:
        result = CliRunner().invoke(
            main, ["play", "07_devastating_wounds", "--seed", "6"], input="\n\n"
        )
        assert result.exit_code == 0, result.output
        out = result.output
        # The override armed the arc rifle (galvanic rifle absent).
        assert "Weapon: Arc Rifle" in out
        assert "Galvanic Rifle" not in out
        # Variable damage is rolled and shown, not assumed.
        assert "D3 rolled" in out
        # Turn 1 (seed 6): a critical wound bypasses the save and wastes its
        # overkill on a 2-wound Marine — the rulebook's own example, live.
        assert "critical diverted to mortal wounds" in out
        assert "wasted (one model per critical)" in out
        assert "no armour or invulnerable save can stop" in out
        assert "Each critical wound strikes just one model." in out
        assert "a scalpel, not an avalanche" in out   # the outro's core lesson

    def test_first_blood_shows_the_fight_phase_and_the_reduced_return_swing(self) -> None:
        result = CliRunner().invoke(
            main, ["play", "08_first_blood", "--seed", "20"], input="\n\n"
        )
        assert result.exit_code == 0, result.output
        out = result.output
        # The fight-turn banner: both sides act, the player picks first.
        assert "both sides fight; the attacker picks first" in out
        # Melee wording end to end: menu, header, WS narration.
        assert "Unit to fight with: Boyz" in out
        assert "with Choppa in melee" in out
        assert "Weapon Skill" in out
        # The lesson in the dice: 10 Boyz swing 30, the survivors answer with 9.
        assert "10 models x 3 attacks = 30 dice" in out
        assert "3 models x 3 attacks = 9 dice" in out
        assert "2 models slain; 3 of 5 remain" in out
        # The outro's core sentence.
        assert "a dead model makes no attacks" in out

    def test_return_fire_ai_targets_the_softer_unit(self) -> None:
        result = CliRunner().invoke(
            main,
            ["play", "06_return_fire", "--seed", "11"],
            input="1\n\n\n\n1\n\n\n\n",
        )
        assert result.exit_code == 0, result.output
        out = result.output
        assert "the defender acts" in out                # the enemy took a turn
        assert "Strike Team fires Pulse Rifle at Necron Warriors" in out
        assert "Strike Team fires Pulse Rifle at Immortals" not in out
        assert "the Warriors drew the fire" in out       # the outro's core lesson

    def test_sustained_hits_override_arms_the_tesla_and_teaches(self) -> None:
        result = CliRunner().invoke(
            main, ["play", "05_sustained_hits", "--seed", "5"], input="\n\n"
        )
        assert result.exit_code == 0, result.output
        out = result.output
        # The override visibly swapped the gun: tesla offered, gauss absent.
        assert "Weapon: Tesla Carbine" in out
        assert "Gauss Blaster" not in out
        # The fact line does the sustained arithmetic in the open (seed 5, turn 1).
        assert "24 hit (14 rolled + 10 sustained from 5 crits)" in out
        assert "Sustained Hits kicked in" in out         # the narrator's sentence
        assert "not automatic wounds" in out             # the outro's core lesson
