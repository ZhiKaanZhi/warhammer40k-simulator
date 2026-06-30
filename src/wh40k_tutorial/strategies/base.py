"""The Strategy protocol — the extension point for player input and AI opponents.

A Strategy is anything that, given the current game state, returns the next
action for a side. Three implementations are planned:

- HumanStrategy:     prompts the player via the CLI. The player IS the strategy.
- ScriptedStrategy:  replays a fixed sequence from the scenario file.
                     Used for the AI side in v1 tutorials.
- HeuristicStrategy: (v2) picks the highest-EV action using the same combat
                     math the engine uses for dice resolution.

The engine ONLY interacts with strategies through this protocol. Player input
logic does not leak into combat code. AI logic does not need to know how
the player decides things. This separation is what keeps the engine clean.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol


@dataclass(frozen=True)
class GameState:
    """Snapshot of the battlefield at decision time.

    TODO: flesh out as we build phase 2. For now this is a placeholder so
    the Strategy protocol's signature is stable.
    """

    turn: int
    phase: str
    active_side: str  # "attacker" or "defender"
    # TODO: units on the board, positions, wounds remaining, etc.


@dataclass(frozen=True)
class Action:
    """An action a strategy can take.

    v1 only models the shooting phase, so for now an Action is "this attacker
    shoots that target with that weapon". Future phases (movement, charge,
    fight) will add Action subclasses or a discriminated union.

    TODO: replace with a proper discriminated union once we have more actions.
    """

    kind: str  # "shoot" for v1
    attacker_unit_id: str
    weapon_key: str
    target_unit_id: str


class Strategy(Protocol):
    """Anything that can choose actions for a side."""

    def choose_action(self, state: GameState) -> Action:
        """Return the next action for the active side, given the current state."""
        ...
