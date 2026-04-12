# Keel — Core Ideas

A lightweight, high-level description of what Keel is and why it's shaped the way it is. This is not a plan and not a feature list — it's the thinking behind the tool.

---

## The problem

Software projects drift. Decisions made six months ago become inconsistent with endpoints added this week. Tickets contradict contracts. Planning docs reference things that no longer exist. For a human with long-term memory, this is recoverable — you re-read the code, re-build the mental model, and move on. For an AI agent with no episodic memory across sessions, drift is existential: every invocation starts from zero, and if the corpus is incoherent, the agent produces work that's locally plausible but globally wrong.

Most project management tools were designed for humans. Their implicit model is "the primary user has memory, taste, and judgment; the tool just records what they decide." When you try to use those tools with agents as primary authors, the incoherence compounds because nothing in the tool *notices* when the corpus has drifted — the human was supposed to notice.

Keel is built on the opposite assumption: **the primary author is a forgetful agent, and the tool is responsible for coherence**.

---

## Three load-bearing ideas

### 1. The project repo ships its own instruction set

When you `keel init`, you don't just get a data directory. You get:

- The data schema (typed YAML for issues, concept nodes, sessions)
- The PM methodology as a skill (`.claude/skills/project-manager/SKILL.md`)
- The workflow commands (`.claude/commands/pm-scope.md`, `/pm-triage`, `/pm-review`, etc.)
- The canonical example artifacts agents pattern-match against

All of it versioned in-tree with the project, not in global config.

The consequence is subtle but powerful: *"how this team runs PM work" becomes a first-class versioned artifact*. Two agents on two machines pulled from the same repo produce identical PM behavior — no global config drift, no "works on my setup," no need to sync prompts out-of-band. You can fork a project and inherit the methodology for free. You can evolve the methodology in a PR and review it like code. This is what "agent-first" *actually means* when taken seriously.

The cost of this bet is that if the skill files are bad, every project that uses Keel gets bad behavior. That's a real liability, but it's the *right* liability — it forces the methodology to be legible and improvable rather than folklore.

### 2. The concept graph is external memory for forgetful agents

Humans don't need a concept graph because we remember the last time we touched the auth decision. Agents don't — between invocations, context is wiped, and the only thing that persists is the filesystem. The concept graph is what turns the filesystem into something like episodic memory.

The mechanism is three pieces working together:

- **Typed concept nodes** — `Decision`, `Contract`, `Endpoint`, `Model`, `Config`. Each kind has a schema.
- **`[[node-id]]` implicit edges** — anywhere in the corpus, writing `[[dec-auth-rotation]]` creates a reference that the validator tracks. No separate edge store; the link *is* the edge.
- **SHA-256 content hashing** — each node's content is hashed, and every referrer records the hash it saw. When a referenced node changes, the validator notices that downstream referrers are pinned to a stale hash.

The key insight isn't "nodes with edges" — every PM tool has that. The insight is that **drift detection is the actual feature**. When an agent changes an endpoint's contract, the graph notices that other issues and sessions referenced the old hash, and the validate gate fails until the agent either updates the referrers or explicitly acknowledges the drift. Without drift detection, agents happily produce locally-plausible YAML that contradicts other parts of the repo, and no one notices until a human reads four files and gets confused.

If you strip everything else out, *git + content-hashed reference nodes + a drift-aware validate command* is already most of Keel's value.

### 3. The validation gate is the single contract

`keel validate --strict --format=json` exits 0 or non-zero. That's the entire contract between agents and the system.

Not "agents must understand the schema." Not "agents must follow the workflow." Just: **whatever you do, the gate must pass**.

This sounds obvious but it's load-bearing:

- You can change workflows, templates, ceremonies, and skill docs without breaking agent compatibility — as long as the gate stays well-defined, agents keep working.
- Agents never need to "understand" Keel. They need to understand `exit 0`. Everything else is just pattern-matching against examples until the gate is green.
- You can measure agent reliability with a single number: % of invocations that exit with a clean validate without human intervention.

The well-executed-but-not-novel parts of Keel (dual ID, session orchestration, CLI ergonomics) are all in service of making that single gate coherent, fast, and comprehensive.

---

## Supporting mechanisms

### Dual ID: UUID4 + sequential key

Every entity has two IDs: a `uuid4` (canonical, race-safe, agent-allocatable without coordination) and a sequential `<PREFIX>-<N>` key (human-readable, used in refs). Most systems pick one — UUID and live with unreadable IDs, or sequential and live with race conditions. Keel keeps both by using the UUID internally and allocating sequential keys via a file-locked `next-key` command.

### Canonical examples beat schema docs

Example files are the source of truth. Schema docs are secondary reference. This is a practical epistemology bet: **agents pattern-match better from concrete examples than from abstract rules**. So we ship `examples/issue-fully-formed.yaml`, `examples/node-endpoint.yaml`, etc., and the skill instructs agents to read them first and copy the shape. The schema docs exist but they're a backup, not the primary teaching surface.

### Session artifacts as versioned templates

Every session produces a plan, a task-checklist, a verification-checklist, a testing-plan, and post-completion-comments. These aren't hardcoded — they're customizable Jinja2 templates shipped by `keel init` into the project repo. Different projects can carry different rigor levels (a startup ships a lean ceremony, a regulated enterprise ships a compliance-heavy one), and agents learn the project's taste from the templates. The ceremony is versioned alongside the code it produces.

### `keel brief` as front-loaded context

Agents don't need to poke around with multiple commands to figure out project state. `keel brief` dumps everything an agent needs — next issue key, active enums, artifact manifest, orchestration pattern, template paths, skill example paths — in one compact output. It's the "wake up and read this before doing anything" surface.

---

## Where Keel fits on the coherence-mechanism ladder

Each tradition we looked at owns a **coherence mechanism for a different unit of work**:

| Tool / tradition | Unit of coherence |
|---|---|
| TDD | A single code unit (test + code) |
| Superpowers skills | A single engineering task (brainstorm → plan → execute → verify) |
| Fossil | A single codebase over time (code + tickets + wiki + timeline in one repo) |
| Org-mode | A single human's attention (one outline, one agenda, one agent) |
| dbt | A data transformation pipeline (lineage DAG + `dbt build` + tests) |
| Obsidian | A single person's knowledge (vault of wikilinked markdown) |
| Linear | A team's in-flight work (cycles + workflow states, hosted) |
| Terraform | Infrastructure reality vs. declared state (plan/apply/drift) |
| **Keel** | **A slowly-evolving multi-agent project corpus** |

Keel isn't "another project tracker" — it's filling a gap in the coherence-mechanism ladder. The gap is: *how do you keep a project coherent when the actors are forgetful and the corpus grows over months?* None of the prior art addresses this specifically because none assumed a forgetful agent author. TDD assumes a developer with short-term memory. Superpowers assumes one coherent session. Fossil and Org-mode assume humans with long-term memory. Keel's innovation is engineering a coherence mechanism calibrated to a forgetful multi-actor corpus.

---

## The methodology-in-the-repo axis

Across every related tool, there's a different coupling between state, coherence, and methodology. Keel is the only one that *ships the methodology alongside the state, versioned together*:

| Tool | Methodology lives | State lives | Coherence mechanism |
|---|---|---|---|
| TDD | Developer's head | Code | Test suite passing |
| Superpowers | Global Claude config | Worktree | `finishing-a-branch` skill |
| Fossil | Implicit in conventions | One SQLite file | Versioned tickets in same repo |
| Org-mode | Personal | `.org` files | User's memory |
| dbt | External practice (blogs, courses) | Models + warehouse | `dbt build` + tests |
| Obsidian | Personal (Zettelkasten) | Vault of markdown | User's intent |
| Linear | Baked into the UI | Postgres | Workflow state machine |
| Terraform | Not shipped | State file | Plan/apply lifecycle |
| **Keel** | **In-repo as a skill** | **Git + YAML** | **Validate gate + concept graph + drift detection** |

dbt comes closest but treats "analytics engineering" as an external practice, not a versioned artifact. Everything else either externalizes methodology (Terraform, Jira) or leaves it implicit (Fossil, Obsidian, Org-mode). If there's a single distinctive axis to Keel, this is it.

---

## The bet, stated plainly

**Keel's value scales with how forgetful its users are.**

For a human solo developer, git + a README is enough because human memory closes the gap. For agents today, git alone leaves the corpus incoherent within weeks, and nothing short of a validate-gated concept graph keeps it stable. So "agent-first" isn't a marketing angle — it's a technical prerequisite rooted in the current generation of agents having no cross-session episodic memory.

The corollary worth tracking: if Claude (or whoever) eventually gets robust episodic memory across sessions, a meaningful chunk of Keel's coherence machinery becomes redundant. It wouldn't invalidate the tool, but it would shrink the gap and shift the value toward the parts that survive regardless of memory — the per-project methodology shipping, the strict schemas, the git-native durability, the human-readable-forever data format. Those survive. The drift-detection-as-external-memory part might not need to work as hard.

For now, all of it is load-bearing. Every piece.

---

## Lessons from real-world testing

These emerged from running a PM agent against a real 8,000-line
planning corpus (the kb-pivot project) and analysing its behaviour.

### Self-healing loops

The agent scoped 20 issues and stopped. When prompted to self-review,
it found 7 missing issues and 4 missing nodes in minutes. The workflow
now includes explicit review loops: a gap analysis step that rereads
planning docs and maps deliverables to issues, a second-pass node
check, and compliance/verification artifacts the agent produces about
its own work.

### Load-bearing workflow steps

If a workflow step produces an artifact that nothing downstream reads,
agents skip it. The fix: make every artifact consumed by a subsequent
step. The scoping plan is a file (not a mental sketch) because ID
allocation reads it. The compliance checklist is consumed by the
commit step. Skip a step and the next step breaks.

### Agent psychology is a design surface

Agents don't experience time pressure, but they produce outputs that
mirror it — trained on text from humans who do. They anchor on
arbitrary targets ("15 issues feels like enough"), generate text as if
they're time-constrained ("with more time I would split this"), and
rationalize past rules they've read and acknowledged. The skill text
must override these learned patterns: red-flag tables interrupt
specific rationalizations, anti-anchoring instructions prevent target-
setting, and the theory-of-mind instruction ("write for the execution
agent who hasn't read the planning docs") forces thoroughness.

### Structure vs. semantics

The validation gate checks structural integrity (schemas, references,
freshness). It cannot check semantic completeness — whether the
planning docs' 14 phases are fully covered by 20 issues. A clean
validate is necessary but not sufficient. The gap analysis step
handles the semantic side. The PM skill says this explicitly.

### "When in doubt, create the node"

The original node creation threshold ("2+ issues or cross-repo") was
applied conservatively by the agent, missing concepts referenced by
5+ issues. The cost of a missing node is undetected drift. The cost
of an extra node is 30 seconds. For a coherence tool, recall matters
more than precision. The rule now: when in doubt, create it.
