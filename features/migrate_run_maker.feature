Feature: Migrate _run_maker from AgentExecutor to create_agent
  The legacy AgentExecutor API in coding_agent/llm_boundaries.py must be
  replaced with the modern create_agent API while preserving behaviour.

  Scenario: create_agent is imported from langchain.agents
    Given the source file coding_agent/llm_boundaries.py
    Then it should contain the import "from langchain.agents import create_agent"

  Scenario: create_agent is actually called inside _run_maker
    Given the source file coding_agent/llm_boundaries.py
    Then "create_agent" should be called within the "_run_maker" function

  Scenario: AgentExecutor is no longer referenced
    Given the source file coding_agent/llm_boundaries.py
    Then it should not contain the string "AgentExecutor"

  Scenario: create_tool_calling_agent is no longer referenced
    Given the source file coding_agent/llm_boundaries.py
    Then it should not contain the string "create_tool_calling_agent"

  Scenario: The 20-iteration cap on the maker's tool loop is preserved
    Given the source file coding_agent/llm_boundaries.py
    Then it should contain a configuration that limits iterations to 20

  Scenario: Tool error handling is preserved
    Given the source file coding_agent/llm_boundaries.py
    Then it should contain a configuration that handles tool errors

  Scenario: _run_maker keeps its signature
    Given the source file coding_agent/llm_boundaries.py
    Then the function "_run_maker" should have the signature parameters "llm, jail, state"

  Scenario: _run_maker return value is compatible with nodes.py
    Given the source file coding_agent/llm_boundaries.py
    And the source file coding_agent/nodes.py
    Then the return value of "_run_maker" should be compatible with its usage in nodes.py