Feature: String Calculator
  As a developer
  I want to add numbers supplied as a delimited string
  So that I can sum an arbitrary list of numbers with one function

  Scenario: empty string returns zero
    Given the string ""
    When I add the numbers
    Then the result should be 0

  Scenario: single number returns itself
    Given the string "1"
    When I add the numbers
    Then the result should be 1

  Scenario: two comma separated numbers are summed
    Given the string "1,2"
    When I add the numbers
    Then the result should be 3

  Scenario: an unknown amount of numbers can be summed
    Given the string "1,2,3,4,5"
    When I add the numbers
    Then the result should be 15

  Scenario: newline can be used as a delimiter alongside commas
    Given the string "1\n2,3"
    When I add the numbers
    Then the result should be 6

  Scenario: negative numbers raise an error listing all of them
    Given the string "1,-2,3,-4"
    When I add the numbers
    Then it should raise an error containing "-2,-4"
