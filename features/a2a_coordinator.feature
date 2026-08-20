Feature: A2A Protocol Integration with Coding Engineer Harness
  As a developer tackling complex coding problems
  I want a coordinator agent that delegates to multiple Coding Engineer harnesses via A2A
  So that problems too large for a single agent can be decomposed and solved

  Background:
    Given a Coding Engineer harness is available
    And an A2A server is created for the Coding Engineer harness

  Scenario: A2A server exposes Agent Card at the well-known discovery endpoint
    When a GET request is made to "/.well-known/agent.json"
    Then the response status should be 200
    And the response body should be valid JSON
    And the agent card "name" field should be a non-empty string
    And the agent card "description" field should be a non-empty string
    And the agent card "url" field should be a non-empty string
    And the agent card "version" field should be a non-empty string
    And the agent card "capabilities" field should be present

  Scenario: A2A server accepts and processes a task via JSON-RPC
    Given a JSON-RPC request with method "tasks/send" and message "Implement a function that adds two numbers"
    When the request is sent to the A2A server
    Then the response status should be 200
    And the response should contain a result key
    And the result should contain a task "id"
    And the result should contain a task "state"

  Scenario: Coordinator agent is a compiled LangGraph graph
    Given the coordinator module is imported
    Then the coordinator graph should be a compiled LangGraph instance
    And the coordinator graph should have an "invoke" method

  Scenario: Coordinator delegates a task to a Coding Engineer harness via A2A
    Given the coordinator module is imported
    And the coordinator is configured with the A2A endpoint URL
    And a delegation instruction "Write a Python function that returns the factorial of n"
    When the coordinator processes the instruction
    Then the coordinator should return a non-empty result
    And the result should contain evidence of task delegation to the harness

  Scenario: End-to-end delegation test script exists and runs successfully
    Given a test or script file exists for coordinator-to-harness delegation
    When the test or script is executed
    Then the execution should complete without errors
    And the output should contain evidence of successful task delegation
    And the output should contain evidence of result retrieval from the harness