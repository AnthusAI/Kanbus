---
name: crap
title: CRAP Reduction
description: Keep change risk low by reducing complexity and covering the code that remains complex.
tools:
  - name: report
    command: tools/crap-report
    purpose: Report the CRAP score of every Python function in files changed since the base branch, worst first.
---
## CRAP Reduction

CRAP (Change Risk Anti-Patterns) scores a function by its cyclomatic complexity and how little of it the tests exercise: `complexity^2 * (1 - coverage)^3 + complexity`. A fully covered function scores its complexity. An untested function scores roughly its complexity squared.

When you change code, leave the functions you touched with a lower CRAP score than you found them.

- Run the report before and after your change. It reads `coverage.xml` from the repository root, so refresh that file first when the tests have changed.
- Treat any score above 30 as a function to simplify, cover, or both.
- Reduce complexity first: extract a branch into a well-named function, replace nested conditionals with early returns, and delete dead paths.
- Then cover what remains with a specification that describes the behavior, following the rest of this document's process.
- Never lower a CRAP score by deleting a test or excluding code from coverage.
