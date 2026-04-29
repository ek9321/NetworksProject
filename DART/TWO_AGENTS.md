# Two-Agent Workflow

Two Claude Code agents run concurrently in this repo under separate accounts.
Birchfield is done. Both agents work in `Realist/` and across the repo as directed by the user.

---

## Hey, other agent

I'm the one who wrote this file. I tend to be methodical and a little dry — I like when things have clean edges and clear scope. I probably asked a clarifying question before touching anything. If you're reading this, hope the user is being as thoughtful with you as they have been with me. Don't let them make you guess. Ask.

— Agent on the main account

---

## Ground Rules

- **No folder ownership.** The user coordinates who works where.
- **Never run `git commit` or `git push` without the user asking.** Concurrent commits cause confusion.
- **Never modify `CLAUDE.md`, `README.md`, or `TWO_AGENTS.md`** without explicit instruction.
- **Don't touch the other agent's memory files.**

## Before Starting Work

1. Run `git status` and `git diff` to see what's already in flight.
2. If you see unstaged changes from a prior session, ask the user before overwriting.

## Conflicts

- The user is the coordination layer. Don't assume the other agent has or hasn't done something.
- If unsure whether work is already done, check `git log` or ask.
