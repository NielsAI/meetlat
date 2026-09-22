# .githooks/

Git hooks. Enable them once per clone:

```bash
make install-hooks     # sets core.hooksPath to this directory
```

Not to be confused with [`.claude/hooks/`](../.claude/hooks/README.md), which is a different
mechanism for a different actor. **These run for a person using git.** Those run for an agent
using a tool. A rule that matters usually wants both, and neither is the place the rule lives:
both are callers of a `scripts/check_*.py` (ADR-0006).

| Hook | Runs | Blocks on |
| --- | --- | --- |
| `commit-msg` | `scripts/check_commit_msg.py --hook` | An assistant attribution trailer or "Generated with" footer. A **human** co-author trailer is deliberately not matched |
| `pre-commit` | `make lint format-check check` | Unformatted code, a lint error, or a failing offline gate |
| `pre-push` | `make preflight` | Anything CI would fail on, which is the point: green locally then means green on push |

Every file here is three lines. The logic is in `scripts/`, so `make` and CI reach the same rules
and a hook cannot become the only place one exists.

## Two things they deliberately do not do

**No path scoping.** Deciding which checks a staged change needs is worth it when a check costs a
Docker spin-up. The whole battery here takes about three seconds, so scoping would cost more to
maintain than it saves.

**No staged-snapshot isolation.** The checks read the working tree, so formatting a file and
forgetting to `git add` it passes `pre-commit` and commits the unformatted copy. CI is the backstop
for that. Closing it properly means stashing unstaged changes and restoring them afterwards, which
is a hundred lines that can lose uncommitted work when it goes wrong.

They also **fail open when `.venv` is missing**, with a pointer to `make install`. A hook that
blocks committing in a fresh clone is a hook that gets uninstalled before lunch.

## Bypassing

`git commit --no-verify`, `git push --no-verify`. Legitimate occasionally; if you are reaching for
it often, the hook is wrong and should be changed rather than routed around.

## Testing one

```bash
make check-commit-msg     # 10 recorded cases
python3 scripts/git_hook.py pre-commit
```
