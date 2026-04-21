# Subagent delegation protocol (NOT YET ENABLED)

**DO NOT USE SUBAGENTS for writing files.** This document captures
learnings from v0.2 testing for future implementation. The active
instruction is in SKILL.md: "DO NOT USE SUBAGENTS for writing
project entities."

## v0.2 findings

A PM agent was tested against a 6,700-line planning corpus. It
delegated to 9 subagents and produced 92 issues, 53 nodes, and 20
sessions. Results:

1. **The PM agent never read a single file its subagents produced.**
   When asked to describe a random issue from memory, it guessed from
   the prompt it sent the subagent, not from the actual file contents.
   It had "high structural confidence, low semantic confidence."

2. **The first subagent batch had zero `[[node-id]]` references**
   because the subagent wasn't given the node ID list. The PM agent
   had to patch all 16 files post-hoc.

3. **The worst subagent invented dangling references** (`[[kb-pivot-spec]]`)
   to nodes that don't exist, because it wasn't given the list of valid
   node IDs.

4. **Self-review became meaningless.** The gap analysis and compliance
   steps require the PM agent to review its own output. If it didn't
   write the output, it can't meaningfully review it.

5. **Key allocation split across contexts.** The PM agent pre-allocated
   76 keys but the epic subagent allocated its own 16, causing the
   sequence to jump from 76 to 93 while KBP-1 through KBP-76 were
   still empty.

## Protocol (for future implementation)

When subagent delegation is re-enabled, the following protocol must be
followed:

### Context requirements per subagent

Each subagent MUST receive:
- The canonical example file for the entity type
- The complete list of valid concept node IDs
- The pre-allocated keys and UUIDs for that batch
- The body section requirements (all 9 for concrete, 3 for epics)
- The `related:` cross-reference expectations

### Mandatory read-back

After each subagent returns, the PM agent MUST:
- Read at least 3 random files from the batch
- Run `tripwire validate --strict --select <batch-range>+` on the batch
- Verify that `[[node-id]]` references are semantically correct (not
  just syntactically present)
- Be able to describe any file's contents from memory

### Quality verification

If the PM agent cannot describe a random file's contents when asked,
the delegation failed and the batch must be rewritten.

### Reconciliation

After all subagent batches are complete:
- Run full validation
- Check cross-batch consistency (do issues from batch A correctly
  reference nodes from batch B?)
- Run `tripwire refs summary` to verify node coverage
