"""Jailed, allowlisted execution primitives for the Coding Engineer agent.

Nothing in the rest of `coding_agent` should touch the filesystem or spawn a
subprocess except through `code_exec` and `worktree`. See
CODING_ENGINEER.md §4 (Safety rails).
"""
