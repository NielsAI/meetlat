# CLAUDE.md

Claude Code's entry point. The canonical, cross-tool orientation lives in `AGENTS.md` and is
imported below so the two never drift.

@AGENTS.md

## Claude Code specifics

- **Subagents** (`.claude/agents/`): delegate rather than doing these by hand.
  `calibration-reviewer` (review anything that would publish a number: judge cards, prompts, hand
  labels, the agreement maths), `check-author` (add a layer 1 check with its fixture and clean
  corpus entries), `adr-author` (write an ADR with valid frontmatter and refresh the index),
  `licence-auditor` (check that what this repository redistributes it may redistribute, and that
  what it claims in prose is what the code and the labels hold). Their
  `model:` routing and the reason for each is `.claude/agents/rules/model-routing.md`; changing a
  row changes that table first.
- **Skills** (`.claude/skills/`): `/calibrate-judge` is the ADR-0004 protocol as a sequence you
  execute, and the thing to read before touching anything under `judges/` or `gold/`.
  `/add-zeef-check` is the layer 1 procedure.
- **Hooks** (`.claude/settings.json`, contract in `.claude/hooks/README.md`, ADR-0006): one
  fail-closed guard on writes to `gold/` (`scripts/check_gold_write.py`), a `PostToolUse` reminder
  naming the gate an edit just put out of date, and a `SessionStart` line with the branch, the
  dirty tree, and how much is actually calibrated. All fail open on unreadable input and none
  mutates a file.
- **Git hooks** are a separate mechanism in `.githooks/`, for a person using git rather than an
  agent using a tool, enabled with `make install-hooks`. Notably `commit-msg` rejects an assistant
  attribution trailer, which is the enforcement behind the rule that a commit records what changed
  and why rather than who typed it. Do not add one and then reach for `--no-verify`.
- **Preflight**: `make preflight` runs the full CI battery locally. Use it to self-verify green
  instead of pushing and waiting.

## The one thing to be careful about

`gold/` holds hand labels. Two people, reconciled by hand, and every number this project publishes
is measured against them. They are the only artifact here that is neither reproducible nor
recoverable, and an agent that helpfully regenerates one destroys the instrument without anything
downstream being able to tell. Reading is free; a write is refused by a hook, and that hook is
correct. If labels need to change, that is a person's job, and saying so is the right answer.
