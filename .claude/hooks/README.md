# .claude/hooks/

Hooks are how a rule in this repository becomes something that happens rather than something an
agent is asked to remember. Wired in [`../settings.json`](../settings.json); the contract below is
the rule for adding one (ADR-0006).

## The contract

1. **Fail open unless the rule is a safety rule.** A parse or IO error exits 0 with no output. One
   guard fails closed on its decision, `check_gold_write.py`, because hand labels are the one
   thing here that is neither reproducible nor recoverable. Even that one fails *open* on
   unreadable input: a guard that blocks every call the moment its own payload is malformed gets
   deleted within a day, and a deleted guard protects nothing.
2. **Never mutate a file.** Regeneration is slow and side-effecting, and running it under an agent
   mid-task is how a diff grows things nobody asked for. A hook points; `make` or CI does the
   work. `regeneration_reminder.py` is the worked example.
3. **Deduplicate per session** where the message is advisory, keyed by `session_id` under
   `TMPDIR`. A hook that says the same thing on every edit is a hook people learn to skim.
4. **The hook is a caller, never the logic.** Anything with real rules lives in a stdlib
   `scripts/check_*.py` that `make`, CI and any other tool can invoke identically. A rule that
   exists only inside a hook binds one tool on one machine, which is most of what ADR-0006 is
   about.
5. **Emit the documented JSON.** `hookSpecificOutput` with `hookEventName`, plus
   `permissionDecision` / `permissionDecisionReason` for `PreToolUse`, or `additionalContext` for
   the advisory events.

## What is wired

| Event | Runs | Posture |
| --- | --- | --- |
| `PreToolUse` on `Write\|Edit\|NotebookEdit\|Bash` | `scripts/check_gold_write.py --hook` | **Fail closed.** No writing to `gold/*.jsonl`; reading, and `gold/README.md`, are untouched (ADR-0004) |
| `PostToolUse` on `Write\|Edit` | `regeneration_reminder.py` | Advisory: names the gate the edit just put out of date |
| `SessionStart` | `session_start_context.py` | Read-only: branch, dirty tree, and how much is actually calibrated |

## Deliberately not wired

- **`UserPromptSubmit`**: no rule here needs to inspect a prompt, and exiting 2 on that event can
  erase what the user typed.
- **A version-control guard.** This is a single-author repository where commits are the author's
  own call, and the assistant's own instructions already cover it. If that changes, it is a
  `scripts/check_*.py` like everything else, not a hook with the rules inside it.

## Testing a hook

Pipe it a payload; that is the whole interface.

```bash
echo '{"tool_name":"Write","tool_input":{"file_path":"gold/x.jsonl"}}' \
  | python3 scripts/check_gold_write.py --hook

python3 scripts/check_gold_write.py --selftest   # 16 recorded cases
make test ARGS="-k gold_guard"
```
