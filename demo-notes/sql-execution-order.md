---
description: Logical execution order of SQL SELECT queries, with examples
---

# SQL Query Logical Execution Order

SQL is *written* in one order but *executed* in another. Knowing the logical
execution order explains why aliases and filters behave the way they do.

## The order

1. **FROM** (and JOINs) — build the working row set
2. **WHERE** — filter rows (no access to SELECT aliases yet)
3. **GROUP BY** — collapse rows into groups
4. **HAVING** — filter groups (aggregates allowed here)
5. **SELECT** — compute expressions and aliases
6. **DISTINCT** — remove duplicate result rows
7. **ORDER BY** — sort (SELECT aliases ARE visible here)
8. **LIMIT / OFFSET** — trim the final result set

## Why it matters

- A column alias defined in SELECT cannot be used in WHERE, because WHERE
  runs before SELECT. It can be used in ORDER BY, which runs after.
- HAVING exists because WHERE cannot see aggregate results: WHERE runs
  before GROUP BY, HAVING runs after.
- LIMIT without ORDER BY returns an *arbitrary* subset — the sort must be
  applied before the trim to be deterministic.

## Example

```sql
SELECT department, AVG(salary) AS avg_pay   -- 5
FROM employees                              -- 1
WHERE hired_on >= '2024-01-01'              -- 2
GROUP BY department                         -- 3
HAVING AVG(salary) > 50000                  -- 4
ORDER BY avg_pay DESC                       -- 7
LIMIT 5;                                    -- 8
```
