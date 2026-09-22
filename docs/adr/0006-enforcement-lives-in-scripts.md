---
status: accepted
area: [infra, agents]
date: 2026-09-22
supersedes: []
amends: []
rule: [AGENTS.md, .claude/hooks/README.md]
enforced_by: [Makefile, .github/workflows/ci.yml]
---

# ADR 0006: A rule worth having is a script with three callers

## Status

Accepted (2026-09-22). Adopted from the author's Hub repository, where the same decision is
ADR-0354.

## Context

This repository's entire argument is that an unenforced claim is not a measurement. It would be
absurd for its own rules to be prose that an agent is asked to remember.

Prose rules fail in a particular way. They are read once at the start of a session, they bind
exactly one tool, and they are silently dropped the moment a task gets long. The rules that matter
most here, no false positives in layer 1, no judge reporting an uncertified number, are exactly
the ones that a tired evening breaks by accident.

## Decision

**A rule worth enforcing becomes a `scripts/check_*.py` with three callers**: a `make` target for
a person before pushing, a CI job so a push is measured against the same gate, and, where the
feedback is worth having instantly, a Claude Code hook.

**The hook is a caller, never the logic.** Anything with real rules lives in the script, so the
rule is one a person can run, CI can enforce, and any agent-facing tool can obey. A rule that
exists only inside a hook binds one tool on one machine.

**The script exposes an `audit(root)` function**, not just a `main()`. That is what lets
`tests/test_judge_gate.py` build a valid judge in a temp directory and break it one way at a time.
A gate nobody tests is a gate that rots.

**A hook fails open unless it is a safety rule, and never mutates a file.** Generation under an
agent mid-task is how a diff grows things nobody asked for. A hook points; `make` does the work.

## Consequences

`make preflight` runs the same targets CI runs, so green locally means green on push. The one rule
with a fail-closed hook is the gold set guard: hand labels are the instrument the whole system is
calibrated against, and an agent that helpfully regenerates them destroys the only ground truth
there is, silently and irreversibly.
