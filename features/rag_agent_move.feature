Feature: Move rag_research_chatbot into rag_agent package
  As a developer maintaining the codebase
  I want rag_research_chatbot.py moved into a rag_agent/ subfolder
  So that the code is properly organized as a package

  Scenario: rag_agent directory exists
    Given the worktree has been refactored
    Then a directory named "rag_agent" exists in the worktree root

  Scenario: rag_research_chatbot.py exists inside rag_agent
    Given the worktree has been refactored
    Then a file named "rag_agent/rag_research_chatbot.py" exists in the worktree

  Scenario: Original rag_research_chatbot.py is removed from root
    Given the worktree has been refactored
    Then a file named "rag_research_chatbot.py" does not exist in the worktree root

  Scenario: __init__.py exists in rag_agent
    Given the worktree has been refactored
    Then a file named "rag_agent/__init__.py" exists in the worktree

  Scenario: Class is preserved in the new location
    Given the worktree has been refactored
    Then the file "rag_agent/rag_research_chatbot.py" defines at least one class
    And the class is importable from "rag_agent.rag_research_chatbot"

  Scenario: No bare imports of rag_research_chatbot remain outside the package
    Given the worktree has been refactored
    Then no Python file outside "rag_agent" contains an import of "rag_research_chatbot" without the "rag_agent" prefix

  Scenario: Module can be imported without errors
    Given the worktree has been refactored
    Then importing "rag_agent.rag_research_chatbot" completes without ImportError or ModuleNotFoundError

  Scenario: Test command completes without import errors
    Given the worktree has been refactored
    Then running "python -m pytest --collect-only -q" in the worktree root does not produce ImportError or ModuleNotFoundError