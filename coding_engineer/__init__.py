"""Coding Engineer harness — A2A-compatible wrapper around the coding_agent.

This package exposes the existing Coding Engineer LangGraph graph (in
``coding_agent``) under the ``coding_engineer`` name so that A2A tooling
and the coordinator can import it as a harness module.
"""
from coding_agent.engine import (  # noqa: F401
    CodingEngineer,
    build_graph,
    run_cli,
    stream_run,
)

__all__ = ["CodingEngineer", "build_graph", "run_cli", "stream_run"]