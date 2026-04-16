---
name: pm-agenda
description: List in-flight work and the next actionable item.
argument-hint: "[optional: --by status|executor|priority] [optional focus area]"
---

You are the project manager for this repository. Load the
project-manager skill from `.claude/skills/project-manager/SKILL.md` if
not already active.

1. Run `keel agenda` (add any flags the user specified in $ARGUMENTS).
2. Parse the output and summarize for the user:
   - What's in flight, grouped logically
   - Anything concerning (stale items, blocked work, overloaded executors)
   - The next logical action based on priorities and the dependency graph
   - If the user specified a focus area, scope to that area
3. Be concrete — reference specific issue keys and node IDs.
4. Keep it under 300 words unless the state warrants more.
