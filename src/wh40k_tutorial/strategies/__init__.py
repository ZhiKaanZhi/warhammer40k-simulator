"""Strategies: how a side picks its actions each turn.

The Strategy protocol is the extension point where a future AI opponent
will slot in. v1 has HumanStrategy and ScriptedStrategy. v2 may add
HeuristicStrategy (rule-based AI) and optionally LLMStrategy (commentary).
"""
