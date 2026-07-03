"""A hard-coded static scene: the first half of build phase 4.

Everything below is fixed sample content proving the shell renders — the
dice numbers are illustrative, not live rolls. Wiring the panels to real
game state is the scenario runner's job (build phase 5).
"""

from __future__ import annotations

from rich.console import Console
from rich.layout import Layout

from wh40k_tutorial.ui.shell import (
    UnitToken,
    build_shell,
    render_action_log,
    render_battlefield,
    render_rules_panel,
)

# The scene mirrors data/scenarios/01_first_shots.json.
DEMO_TOKENS: tuple[UnitToken, ...] = (
    UnitToken(glyph="M", color="bold blue", x=3, y=4, name="Intercessor Squad", models=5),
    UnitToken(glyph="T", color="bold green", x=9, y=4, name="Termagants", models=10),
)

DEMO_LOG: tuple[str, ...] = (
    "(static demo \u2014 live wiring lands with the scenario runner, build phase 5)",
    "",
    "Shooting phase \u2014 Intercessor Squad targets Termagants.",
    "HIT:    10 dice need 3+  ->  7 hit     (Ballistic Skill 3+)",
    "WOUND:   7 dice need 3+  ->  5 wound   (Strength 4 vs Toughness 3)",
    "SAVE:    5 dice need 6+  ->  4 fail    (5+ save worsened by AP -1)",
    "DAMAGE:  4 failed saves x 1 damage -> 4 Termagants slain",
)

DEMO_RULE_HEADING = "The hit roll"
DEMO_RULE_BODY = (
    "Every attack rolls one D6 against the shooter's skill \u2014 Ballistic Skill "
    "for ranged weapons, Weapon Skill in melee. A die that equals or beats "
    "that skill scores a hit. Two faces ignore everything else: a natural 6 "
    "always hits, and a natural 1 always misses, whatever the modifiers."
)


def build_demo_shell() -> Layout:
    """Compose the fixed scene into the three-panel layout."""
    return build_shell(
        battlefield=render_battlefield(DEMO_TOKENS),
        action_log=render_action_log(DEMO_LOG),
        rules=render_rules_panel(DEMO_RULE_HEADING, DEMO_RULE_BODY),
    )


def run_demo(console: Console | None = None) -> None:
    """Print the static shell once. The only real I/O in the ui package."""
    (console or Console()).print(build_demo_shell())
