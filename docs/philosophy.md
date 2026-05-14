# Philosophy

This document anchors the framework's design decisions. When a future
PM or UX choice is on the table, the question is: *which of these
principles speaks to it, and what does that suggest?*

It exists because v0.8 forced a reframing of the dashboard around
attention rather than inventory, and the same reframing applies
across the rest of the surface. Without an anchor doc, every new
screen risks rediscovering the same lesson — or worse, missing it.

---

## 1. Comparative advantage

Tripwire is a project management framework designed to be *driven*
by AI agents and *audited* by humans. The two parties have very
different capabilities. The framework should play to the strengths
of each rather than treating them as interchangeable.

**Agents are good at:**

- Mechanical execution (writing code, running tests, opening PRs)
- Structural validation (schema checks, reference resolution,
  freshness propagation)
- Parallelism (many sessions, many issues, many checks at once)
- Self-review against explicit rubrics
- Operating tirelessly across long sessions

**Agents are bad at:**

- Taste (is this scope right? is this artifact good enough?)
- Strategic priority (what should we build next, given limited
  budget?)
- Stopping decisions (when is something "done enough"?)
- Catching divergence between intent and result
- Resolving genuine ambiguity that the spec doesn't cover

**Humans are good at:**

- The bad-at-list above
- Weighing tradeoffs across dimensions agents can't quantify
- Drawing on context that lives outside the project (politics,
  customer feedback, prior art the agent hasn't seen)
- Recognising "this feels off" without articulating why yet

**Humans are bad at:**

- Anything mechanical, especially repeated mechanical work
- Sustaining attention across long, low-stakes streams
- Holding the entire project graph in working memory

**Implication:** the framework should let agents do as much as
possible, surface the smallest possible slice for the human, and
make that slice exactly the work where human judgement earns its
keep. Every UI surface should be evaluable against this filter.

---

## 2. The leverage question

> *"Where does the human user's attention deliver most leverage to
> the project?"*

This is the central design question for every human-facing surface
in tripwire. It has a sharp form: "what slice of the project state,
if I look at it, lets me move things forward in a way agents
couldn't?"

Concretely, the answers are:

1. **Decisions agents can't make alone** — scope, taste, priority,
   stopping, approvals over thresholds
2. **Stuck/blocked work** — agent waiting on external input,
   merge conflicts, failing CI
3. **Surprises** — tripwires fired, validator errors, unexpected
   re-engagement loops, cost spikes
4. **Drift** — project sprawl, sessions ahead of issues, long-stale
   blocked items
5. **Critical-path leverage** — the one unblock that moves the most
   downstream work

Things explicitly *not* on that list:

- "How many sessions are in each stage" — useful as ambient
  context, but doesn't drive action
- "What fired three days ago" — historical, belongs on a log
  screen
- "Every dependency edge in the project" — overload, see
  [§4](#4-critical-path-as-the-primary-dependency-frame)

The dashboard's left column ([[inbox-attention-queue]]) and
critical-path spine ([[critical-path-spine]]) are direct answers
to this question. Everything else on the dashboard supports them.

See [[dec-attention-leverage-frame]] for the formal decision.

---

## 3. Tripwires are agent-facing

Tripwires are part of the agent control loop. They fire when:

1. **An agent deviated** from the defined workflow (e.g. tries to
   merge without a self-review artifact). The tripwire's job is to
   nudge the agent back on path.
2. **The agent needs context just-in-time** that we deliberately
   hide from baseline prompts to keep them lean. The tripwire
   surfaces complex acceptance rules only when the agent
   approaches the relevant code — progressive disclosure.

In both cases the **agent** is the consumer. Humans don't act on
tripwires directly.

**Implication:** tripwires don't go in the dashboard's attention
queue. They live on a dedicated process-quality screen (S6) where
the human can review *patterns* — fires per session, top firing
rules, fires-per-kind over time — to refine the workflow itself.
The tripwire log is for retrospective process improvement, not
real-time alerting.

When a tripwire firing genuinely implies the human should act
(e.g. session is hopelessly stuck after N re-engagements), the
PM agent escalates by writing an inbox entry. The chain:

```
agent deviates → tripwire fires → process metric on S6
                                ↓
                  PM agent decides this needs human eyes
                                ↓
                  PM writes inbox/<id>.md → dashboard left col
```

See [[dec-tripwires-are-agent-facing]].

---

## 4. Critical path as the primary dependency frame

Every PM tool wants to show dependencies. Most fail by showing
the full DAG — every issue, every blocker edge, every session.
Beyond ~20 nodes the visualisation is overload; the human spends
time decoding the graph instead of acting on it.

The Elon-method framing solves this: at any moment, there is *one*
sub-process determining wall-clock time. The work of management is
to identify that sub-process and act on it. Repeat.

Translated into tripwire's vocabulary:

- The **critical path** is the longest in-flight dependency chain,
  weighted by transitive downstream fan-out at each node.
- The dashboard renders **only** that chain, as a single
  horizontal spine.
- The full DAG belongs on a separate screen (Concepts/Workflow
  Map) for occasional drill-down.

The "longest with most fan-out" rule answers a sharper question
than just "longest chain": *if I unblock one thing right now,
which one moves the most subsequent work?*

When chains tie, the spine notes it (`ties exist` footnote) and
the human can investigate further on the dedicated graph view.
When all in-flight sessions are independent, the spine collapses
to "no critical path — N independent sessions" — informative
absence.

See [[dec-critical-path-elon-method]] and [[compute-critical-path]].

---

## 5. The two-bucket attention model

Most PM tools have a single "notifications" or "activity" feed.
That shape conflates two cognitive modes:

| Mode          | Cognitive load            | Treatment                |
|---------------|---------------------------|--------------------------|
| Interruptive  | Stop, look, decide        | Always-visible, urgent   |
| Digest        | Skim when convenient      | Collapsible, batchable   |

Mixing them dilutes both. Urgent items get lost in the digest.
Digest items steal attention they didn't need to.

The inbox solves this with exactly two buckets:

- **`bucket: blocked`** — interruptive. Something is paused or
  about to drift without a human decision. Empty state is a
  feature: "nothing blocking you right now" = active reassurance.
- **`bucket: fyi`** — digest. A decision was made or work
  completed; the human should know in case they disagree.
  Collapsible, default-expanded, easy to roll up after a skim.

Why not three buckets, or five? Triage cost grows non-linearly
with bucket count. If a finer distinction matters,
`escalation_reason` is a queryable string field — encode the
distinction there, not in another panel. (And mine the field
later for meta-learning on what gets resolved fast vs ignored.)

Why not zero (just one feed)? Because the cognitive treatment
*has* to differ. Render BLOCKED in alert chrome, FYI in muted
chrome — the visual encoding tells the human which cognitive
mode to engage *before* they read the title.

See [[dec-two-bucket-attention-model]] and [[inbox-attention-queue]].

---

## 6. The PM agent as attention curator

The inbox's value comes from one source: a single curator with
strong taste decides what crosses the threshold.

**Open-escalation channels degrade.** Slack `@channel`
notifications, JIRA notification streams, GitHub PR review
queues — all started open and degraded into "delete-without-
reading" because the signal-to-noise ratio collapsed under the
weight of many uncoordinated writers.

**Curated channels stay valuable** because someone whose name is
on the signal cares that it's worth reading. Tripwire codifies
this by making the PM agent the **only** writer:

- Validators don't auto-create inbox entries from lint failures
- Coding agents don't escalate via inbox; their channels are
  PR descriptions, session artifacts, and (cross-container) the
  messaging layer
- Scripts/cron/CI don't write inbox entries
- The route layer has no POST-create endpoint — the PM agent's
  authoring surface is the filesystem, matching the existing
  "agents create entities by writing files" rule for issues,
  sessions, and nodes

The PM agent is taught (via PM-skill) when to write `blocked`
vs `fyi` vs *not write at all*. The third one is the most
important — most deviations are not inbox-worthy.

If a future agent class (e.g. QA agents) earns inbox write
access, it does so only after demonstrating that its proposed
signals would survive the same authoring rules. Coding agents
never qualify — their outputs are PR-shaped, not curation-shaped.

See [[dec-pm-only-inbox-authoring]] and the PM-skill SKILL.md
for the full authoring rules.

---

## 7. Filesystem-native, file-watcher transport

Tripwire is git-native: every entity is a file, every change is
a commit, every audit is `git log` or `git blame`. This shapes
the runtime architecture too.

When the PM agent writes an inbox entry, the transport is:

```
PM agent       writes inbox/<id>.md  via Write tool
                                    │
                                    ▼
file-watcher   observes write       →  FileChangedEvent
                                    │
                                    ▼
WebSocket      broadcasts event     →  frontend invalidate
                                    │
                                    ▼
TanStack Query refetches list       →  dashboard re-renders
```

No messaging layer. No queue. No delivery confirmation. The file
write IS the event. This is intentional — it keeps audit direct
(`git diff inbox/`), keeps the convention consistent with issues
and sessions, and avoids tying lifecycle semantics to message-
queue assumptions that don't fit.

Messaging stays in the codebase for cases the file system can't
reach: container-isolated coding agents, cross-project signals,
future external notification channels (push, email). Within the
PM project repo where writer + reader share a filesystem,
messaging is unnecessary overhead.

See [[dec-no-messaging-for-inbox]].

---

## 8. Quick preview, full edit

Markdown-bearing entities (inbox entries, sessions, issues) all
need a "show me the rendered body" surface. The right answer
isn't one shape — it's two:

- **Side drawer for preview** — slides from the right edge,
  ~520px wide, doesn't navigate away from the dashboard. Renders
  the markdown body, references chip strip, and the entity-
  specific primary action (resolve for inbox, edit-link for
  issue, etc.). Triggered from any entity row on the dashboard.
- **Dedicated screen for full edit** — `/p/<pid>/issues/<key>`,
  `/p/<pid>/sessions/<id>` — handles deep editing, comment
  threads, full artifact lists. Linked from the drawer's
  "open full →" affordance.

The drawer pattern is shared across entity types so visual
treatment stays consistent. The dedicated screens are where
extended interaction happens.

Why not always navigate? Loss of context, slower triage,
dashboard becomes "a list of links" rather than a workspace.
Why not always modal? Modal centres focus; drawer keeps the
dashboard visible behind. The PM is more often previewing in
context than fully focusing on one item.

See [[dec-shared-preview-drawer]] and [[inbox-preview-drawer]].

---

## 9. Specs declare, validate enforces, agents execute, CLI codifies

The framework's load-bearing surfaces have a clear separation of
concerns:

1. **`workflow.yaml` declares structure.** State machines, routes,
   invariants per status and per transition, instance shapes, required
   fields. Pure data. No imperative code. No conditional predicates.
2. **`tripwire validate` enforces invariants.** Always available. Reads
   every instance file, runs every declared validator, produces
   findings. Single accountability surface across every workflow.
3. **Agents execute via CLI.** Skill markdown documents *what to do
   and why*. CLI commands are the *how*. The agent calls CLI;
   tripwire's validators catch deviation.
4. **CLI codifies repetitive procedure.** Layer 1 wraps individual
   external operations (git, gh, fs, process) with our defaults.
   Layer 2 chains common combos. Layer 3 (skill markdown) selects,
   sequences, and recovers from failure.

### Why this separation

Agents are unreliable but obedient. Validators are reliable but
passive. Agents drive the work; validators trip them when they
deviate. Validators don't try to prevent the deviation — they catch
it after. That asymmetry is the point. Tripwire only fires on
deviation.

### What this rules out

- No imperative side-effects in `workflow.yaml`. YAML does not
  orchestrate. Side-effects that happen on transitions belong in CLI
  commands the agent calls *before* transitioning.
- No conditional logic in workflow declarations. "If X then Y"
  becomes a validator finding + a CLI command that does Y.
- No per-workflow Python class scaffolding. Adding a workflow is
  declaring it in YAML. Side-effects only when a repetitive external
  operation needs codifying.

### What this enables

- Agents extend tripwire by editing YAML. No Python knowledge
  needed.
- `tripwire validate` accountability scales linearly with workflow
  count.
- New skills (slash commands) wrap CLI; new workflows declare YAML;
  new invariants are validators. Three orthogonal extension points.

See [[WORKFLOW_ACTIONS.md]] for the canonical enumeration of every
workflow, status, transition, and CLI command this principle
produces.

---

## 10. Anti-patterns

Concrete patterns this philosophy rules out. If a proposed
change matches one of these, push back.

**Don't:**

- Add "everything that exists" sections to the dashboard. They
  belong on dedicated inventory screens.
- Render full dependency graphs anywhere except the
  Concepts/Workflow Map screen. Overload defeats leverage.
- Mix alerts with status in a single feed. Cognitive modes
  differ; visual treatment must too.
- Open the inbox to multiple writer classes. Curation collapses
  under multiple authors.
- Auto-create inbox entries from validator failures. The
  validator surfaces structural issues; the PM agent decides
  what's worth a human's attention.
- Build a unified "now feed" combining sessions, tripwires,
  validator output, and PRs. Each has a different consumer
  and a different cognitive treatment.
- Show notifications for routine state transitions. The
  dashboard is for "what needs you?", not "what just changed?"
- Add a third inbox bucket. If a finer distinction matters,
  put it in `escalation_reason` and mine it later.
- Surface tripwires as human alerts. They're agent
  instrumentation; their human surface is a process-quality
  chart on S6.

**Do:**

- Justify every dashboard section against the leverage question
- Trust the PM agent's curation; codify rules when the
  curation drifts
- Treat empty states as features when their absence is
  informative
- Prefer fewer, more meaningful surfaces over many chatty ones
- Make agents do as much as they can; surface the minimum
  meaningful slice to the human

---

## Where to read next

- [[dec-attention-leverage-frame]] — the formal decision
  behind §1, §2
- [[dec-tripwires-are-agent-facing]] — §3
- [[dec-critical-path-elon-method]] — §4
- [[dec-two-bucket-attention-model]] — §5
- [[dec-pm-only-inbox-authoring]] — §6
- [[dec-no-messaging-for-inbox]] — §7
- [[dec-shared-preview-drawer]] — §8
- [[WORKFLOW_ACTIONS.md]] — §9, the canonical enumeration
- [[project-dashboard-view]] — the composition this philosophy
  produced
- [[inbox-entry-schema]] — the artifact shape that carries
  curated escalations

For the implementation surfaces, follow the references in those
nodes to [[session-stage-row]], [[critical-path-spine]],
[[inbox-attention-queue]], [[inbox-preview-drawer]], and the
backend services that support them.
