<!-- The `model:` frontmatter of the agents beside this file. -->
# Reviewer model routing

Model routing is the one lever where cost and quality trade off directly, so it gets a table with
reasons rather than whatever the frontmatter happened to default to.

**`inherit` is a real answer, not an absence.** It means "this agent should think as hard as
whatever is driving it", which is right when the work is judgement whose depth scales with the
change. It is wrong when the work is mechanical, where inheriting the strongest model pays more
for the same answer.

| Agent | `model:` | Why |
| --- | --- | --- |
| `calibration-reviewer` | `inherit` | The most expensive miss in this repository is a number that looks measured and is not, and it is the one failure nothing downstream can detect. The work is judgement against a protocol whose decidable half already runs in `make check-judges`, so only the part that needs thinking reaches the agent |
| `check-author` | `sonnet` | Mechanical against a fixed contract with a gate behind it. `make check-zeef` decides when the work is correct; the model only has to get there |
| `adr-author` | `sonnet` | Structured writing against a known template with a validator behind it (`make adr-index` catches a malformed landing contract) |
| `licence-auditor` | `inherit` | Judgement about the world outside the repository: whether a source grants what an entry says it grants, and whether a sentence is supported by what is actually built. The mechanical half already runs in `make check-zeef`, so what reaches the agent is the reading, and how much reading a change needs is exactly what the driving model already knows |

## Rules

- **An agent declares `model:` explicitly.** Omitting it is how a routing table becomes accidental.
- **Changing a row changes this table first**, with the reason. A `model:` edit whose rationale
  lives only in a commit message is back where this started.
- **The reason names the work, not the model.** "Judgement against a protocol" survives a model
  rename; "use the big one" does not.
