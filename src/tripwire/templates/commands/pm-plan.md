---
name: pm-plan
description: DEPRECATED — run `tripwire plan` directly.
argument-hint: "[optional: --name project-name]"
---

`/pm-plan` is deprecated as of v0.6a and will be removed in v0.7.

Run `tripwire plan $ARGUMENTS` directly. The one-shot preview before
`tripwire init` doesn't benefit from a slash command wrapper, and the
name conflicts with `plan.md` artifact vocabulary.
