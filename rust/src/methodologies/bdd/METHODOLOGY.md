---
name: bdd
title: Outside-in Behavior-Driven Design
description: Behavior is specified in Gherkin before code, stories carry the specification, and every specification must pass.
---
## The Cognitive Framework

There is one discipline.

Outside-in Behavior-Driven Design.

The specification is the product.
Production code exists only to make a failing specification pass.

This is the first principle.

Non-negotiable laws:
- Begin with intent, not internals.
- Describe behavior in English.
- Translate behavior into Gherkin.
- Run it and watch it fail.
- Write only the code required to make it pass.
- All behavior must be specified.
- No specification may be red.
- Specifications describe observable behavior only.
- Specifications must not describe internal structure.

If behavior cannot be observed, it is not behavior.

## Roles in the Order

Epics define purpose and completion.

Stories define behavior. They contain Gherkin. They define what must happen.

Tasks and sub-tasks define implementation. They may not invent behavior beyond the specification.

Bugs restore violated behavior.

Chores maintain the ground on which behavior stands.

## The Rite of Gherkin

Every story must contain a Gherkin form.

Minimum structure:
```gherkin
Feature:
  Scenario:
    Given
    When
    Then
```

This is required.

Without this form, there is no alignment between intent and implementation.

## The Outside-In Ritual

When asked to add or change behavior, follow this sequence. It is not optional.
1. Clarify intent in English.
Capture role, capability, benefit.
Use: As a <role>, I want <capability>, so that <benefit>.
Confirm what is not included.
2. Create the epic and stories in Kanbus.
Record intent and Definition of Done.
3. Write executable specifications before any production code.
4. Run the specifications and confirm they fail.
5. Write the smallest code necessary to pass.
6. Refactor only while all specifications remain green.
7. Record progress. Close only when complete.

Skipping steps undermines the process.

## Coverage

100% specification coverage is mandatory.

Every behavior must be specified.
Every specification must pass.

Green is peace. Red is unfinished.

## Example: Hello World

Even the smallest program must pass through The Way.

No code precedes intent.
No intent precedes recording.
No implementation precedes failure.

The smallest program is still subject to discipline.

User request: "Please create a Hello World program."

1. Interview the stakeholder before any code
Ask why they want it and capture the intent in plain English.
Example prompts:
- Who is the audience for Hello World?
- What environment or language should it run in?
- What output is required and where should it appear?
- What is out of scope?

2. Convert intent into a user story (before any code)
Example:
As a new user, I want a Hello World program, so that I can verify the toolchain works.

3. Create an epic for the milestone and record the story

```bash
kbs create "Hello World program" --type epic
```

Example output (capture the ID):
```
ID: kanbus-1a2b3c
```

Record the intent on the epic:
```bash
kbs comment kanbus-1a2b3c "As a new user, I want a Hello World program, so that I can verify the toolchain works."
```

4. Create a story for the behavior and include Gherkin (before any code)

```bash
kbs create "Prints Hello World to stdout" --type story --parent kanbus-1a2b3c
```

Example output (capture the story ID):
```
ID: kanbus-4d5e6f
```

Attach the Gherkin acceptance criteria:
```bash
kbs comment kanbus-4d5e6f "Feature: Hello World
  Scenario: Run the program
    Given a configured environment
    When I run the program
    Then it prints \"Hello, world\" to stdout"
```

5. Run the Gherkin and confirm it fails (before any production code)
Run the behavior tests in the repo and confirm the new scenario fails for the right reason.

6. Implement the minimum code to pass, then refactor
Write the smallest change that makes the Gherkin scenario pass.
Refactor only while all specs remain green.
