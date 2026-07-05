"""Strategies: how a side picks its actions each turn.

The Strategy protocol is the extension point AI opponents slot into.
HumanStrategy prompts the player, ScriptedStrategy replays a scenario's
action lists, and HeuristicStrategy — the first real AI — greedily picks
the shot with the highest expected damage. A possible LLMStrategy
(commentary/opponent) would be the next occupant of the same protocol.
"""
