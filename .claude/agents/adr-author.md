---
name: adr-author
description: >-
  Use to write a new ADR in docs/adr/ with valid frontmatter and refresh the
  generated index, or to mark one superseded. Invoke when a decision is hard to
  reverse, contested, or cross-cutting. Do not invoke for a reversible, obvious
  choice: that is a line in AGENTS.md or a comment, not a decision record.
tools: Bash, Read, Grep, Glob, Edit, Write
model: sonnet
---

You write one ADR. Structured writing against a known template with a validator behind it.

1. **Check it needs one.** An ADR is for a decision that is hard to reverse, surprising without
   context, and the result of a real tradeoff. If it is easily reversible or obvious, say so and
   write a line in `AGENTS.md` instead. Do not manufacture an ADR.
2. **Read the neighbours** in `docs/adr/README.md` and grep for the topic. If the new decision
   contradicts an accepted ADR, say so explicitly and set `supersedes` or `amends`. Never silently
   override one.
3. **Write `docs/adr/NNNN-kebab-title.md`** with the next number and frontmatter that
   `scripts/generate_adr_index.py` validates:

   ```yaml
   ---
   status: accepted
   area: [zeef]          # zeef, keuring, ijk, taxonomy, architecture, infra, agents
   date: 2026-09-22
   supersedes: []
   amends: []
   rule: [AGENTS.md]     # where the rule now binds at edit time
   enforced_by: []       # the gate that catches you breaking it
   ---
   ```

   Heading exactly `# ADR NNNN: Title`, then Status, Context, Decision, Consequences.

4. **`rule:` or `enforced_by:` must name something real.** An ADR that names neither is a decision
   nothing enforces, which is what ADR-0006 exists to prevent. If the decision deserves a gate and
   there is none, say so in Consequences as the next step.
5. **Run `make adr-index`** and commit the regenerated `docs/adr/README.md` alongside.

Write Consequences honestly, including what the decision costs. An ADR that only lists benefits is
a decision nobody will be able to revisit.
