"""Isolated LLM invocation wrappers for the Coding Engineer loop.

Extracted from ``coding_agent/engine.py`` during the single-responsibility
refactor.  Every LLM call in the loop goes through one of these boundary
functions so tests can monkeypatch just the model call and exercise the real
graph, worktree, gates, and report writer around it.
"""

from __future__ import annotations

from typing import Any

from langchain.agents import AgentExecutor, create_tool_calling_agent
from langchain_core.messages import HumanMessage
from langchain_core.prompts import ChatPromptTemplate, MessagesPlaceholder

from coding_agent.gates import _read_step_defs
from coding_agent.maker_tools import _build_maker_tools, _maker_task_text
from coding_agent.prompts import (
    AUTHOR_BDD_PROMPT,
    DIAGNOSE_PROMPT,
    INTAKE_PROMPT,
    MAKER_SYSTEM_PROMPT,
    PLAN_JUDGE_PROMPT,
    PLAN_PROPOSE_PROMPT,
    REVIEW_PROMPT,
)
from coding_agent.schemas import (
    BddAuthorResult,
    DiagnosisResult,
    PlanJudgement,
    PlanProposal,
    ReviewVerdict,
    TargetSpec,
)
from coding_agent.state import CodingLoopState
from coding_agent.structured import invoke_structured
from coding_agent.tools.code_exec import Jail


def _llm_parse_target_spec(llm, goal: str, target_dir: str) -> TargetSpec:
    prompt = INTAKE_PROMPT.format(goal=goal, target_dir=target_dir)
    return invoke_structured(llm, TargetSpec, prompt)


def _llm_author_bdd(llm, state: CodingLoopState) -> BddAuthorResult:
    criteria = (state.get("spec") or {}).get("acceptance_criteria", [])
    prompt = AUTHOR_BDD_PROMPT.format(
        goal=state["goal"],
        acceptance_criteria="\n".join(f"- {c}" for c in criteria) or "(none extracted)",
    )
    return invoke_structured(llm, BddAuthorResult, prompt)


def _llm_diagnose(llm, state: CodingLoopState, phase: str, failure_detail: str) -> DiagnosisResult:
    lessons = state.get("lessons") or []
    lesson_lines = (
        "\n".join(f"- attempt {ls.get('attempt')}: {ls.get('insight')}" for ls in lessons[-5:])
        or "(none yet)"
    )
    prompt = DIAGNOSE_PROMPT.format(
        goal=state["goal"], phase=phase, failure_detail=failure_detail, lessons=lesson_lines
    )
    return invoke_structured(llm, DiagnosisResult, prompt)


##### 6c. Context Engineering (ACE Playbook): Itemized, incremental failure lessons merged by deterministic code
def _lessons_block(state: CodingLoopState) -> str:
    """Aggregated lessons for the ToT re-planning prompt (the GoT step) -- empty
    on the first planning pass, populated once plans start dying."""
    lessons = state.get("lessons") or []
    if not lessons:
        return ""
    body = "\n".join(f"- ({ls.get('category')}) {ls.get('insight')}" for ls in lessons[-8:])
    return f"\nLessons from earlier failed attempts (avoid repeating these):\n{body}\n"


def _criteria_text(state: CodingLoopState) -> str:
    criteria = (state.get("spec") or {}).get("acceptance_criteria", [])
    return "\n".join(f"- {c}" for c in criteria) or "(none extracted)"


##### 6a. ToT Candidate Proposal: Primary model proposes 3 distinct plans (temp 0.8)
def _llm_propose_plans(llm, state: CodingLoopState, k: int) -> PlanProposal:
    prompt = PLAN_PROPOSE_PROMPT.format(
        k=k, goal=state["goal"], acceptance_criteria=_criteria_text(state), lessons_block=_lessons_block(state)
    )
    return invoke_structured(llm, PlanProposal, prompt)


##### 6b. Cold Evaluation Scoring: Secondary judge model scores candidate plans against lessons (temp 0.0)
def _llm_judge_plans(llm, state: CodingLoopState, plans: list[dict]) -> PlanJudgement:
    plans_block = "\n".join(
        f"[{i}] {p.get('rationale', '')}\n" + "\n".join(f"    - {s}" for s in p.get("steps", []))
        for i, p in enumerate(plans)
    )
    prompt = PLAN_JUDGE_PROMPT.format(
        goal=state["goal"],
        acceptance_criteria=_criteria_text(state),
        lessons_block=_lessons_block(state),
        plans_block=plans_block,
    )
    return invoke_structured(llm, PlanJudgement, prompt)


##### 12b. Adversarial Review Prompt: Blinded to maker reasoning (sees spec, diff, step defs, test output only)
def _llm_review(llm, state: CodingLoopState) -> ReviewVerdict:
    bdd = state.get("bdd_report") or {}
    step_defs = _read_step_defs(state)
    prompt = REVIEW_PROMPT.format(
        goal=state["goal"],
        acceptance_criteria=_criteria_text(state),
        diff=(state.get("last_diff") or "(no diff)")[:6000],
        step_defs=step_defs[:6000],
        test_output=(bdd.get("stdout") or "(no output)")[:2000],
    )
    return invoke_structured(llm, ReviewVerdict, prompt)


# TODO (Future Refactor / Self-Improvement Task):
#https://docs.langchain.com/oss/python/langchain/agents
# Migrate _run_maker from legacy AgentExecutor (langchain classic) to modern create_agent:
#
# Target Architecture:
#   Replace `create_tool_calling_agent` + `AgentExecutor` with `from langchain.agents import create_agent`
#   (or `from langgraph.prebuilt import create_react_agent`).
#
# Key Steps for the Coding Agent Self-Improvement Goal:
#   1. Import `create_agent` from `langchain.agents`.
#   2. Instantiate the agent using `create_agent(model=llm, tools=tools, system_prompt=MAKER_SYSTEM_PROMPT)`.
#   3. Remove `AgentExecutor` instantiation and invoke the compiled LangGraph agent graph directly.
#   4. Ensure the iteration limit (max_iterations=20) and tool error handling are preserved.
#   5. Run `pytest coding_agent/tests/` to verify 100% test suite compatibility.
def _run_maker(llm, jail: Jail, state: CodingLoopState) -> dict[str, Any]:
    tools = _build_maker_tools(jail, state["budgets"])
    prompt = ChatPromptTemplate.from_messages(
        [
            ("system", MAKER_SYSTEM_PROMPT),
            MessagesPlaceholder(variable_name="messages"),
            MessagesPlaceholder(variable_name="agent_scratchpad"),
        ]
    )
    # https://reference.langchain.com/python/langchain-classic/agents/tool_calling_agent/base/create_tool_calling_agent
    agent = create_tool_calling_agent(llm, tools, prompt)
    # max_iterations=8 was too tight for a real multi-file change: the first
    # live self-hosted run ("Agent stopped due to max iterations" on all 4
    # attempts) needed read+write on rag_research_chatbot.py, a new
    # rag_agent/__init__.py, delete of the old file, an app.py import edit,
    # and a run_pytest check -- more tool calls than a genuine refactor-shaped
    # goal can fit in 8. Raised to a more realistic budget for multi-file work.
    # https://reference.langchain.com/python/langchain-classic/agents/agent/AgentExecutor
    executor = AgentExecutor(agent=agent, tools=tools, max_iterations=20)
    task_message = HumanMessage(content=_maker_task_text(state))
    return executor.invoke({"messages": [task_message]})
