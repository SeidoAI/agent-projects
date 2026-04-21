# Keel v0.1 end-to-end test — kb-pivot

You are testing Keel, a project management tool. Follow these steps one at a time.

## Step 1: Initialize

```bash
tripwire init . --name kb-pivot --key-prefix KBP --no-git --force
```

Verify it worked:
```bash
ls project.yaml .claude/skills/project-manager/SKILL.md
```

## Step 2: Scope the project

The planning documents are in `raw_planning/`. Use the PM scoping slash command:

```
/pm-scope Transform kb-pivot from a single-purpose business onboarding tool into a general-purpose multi-KB platform. Planning docs are in ./raw_planning/.
```

Follow whatever the PM skill and its workflow instruct you to do. Do not cut corners on scope.

## Step 3: Exercise the CLI

After scoping is complete and `tripwire validate --strict` passes, run each of these and report what you see:

```bash
tripwire agenda --by status
tripwire agenda --by executor --format json
tripwire status
tripwire status --format json
tripwire graph --type concept --format json
tripwire refs list --format json
tripwire refresh
```

Then pick an issue ID and a node ID from your output and run:
```bash
tripwire graph --type concept --upstream <issue-id> --format json
tripwire graph --type concept --downstream <node-id> --format json
tripwire validate --strict --format=json --select <issue-id>+
tripwire refs reverse <node-id>
```

Then:
```bash
tripwire view --port 7777
```
Let it run briefly, then Ctrl+C.

## Step 4: Incremental update

Pick one issue and change its status from `backlog` to `todo`. Edit the file, then:
```bash
tripwire validate --strict --format=json
tripwire agenda --by status
```

## Step 5: Report

Write a summary:
1. **What worked** — features that performed as expected
2. **What broke** — commands that errored or produced wrong output
3. **Quality of your own output** — are the issues, nodes, sessions, and plans you created good? What would you do differently?
4. **Skill quality** — did SKILL.md and the workflow docs give you enough guidance? Where were they unclear, wrong, or missing information?
5. **Workflow friction** — any step that felt clunky
6. **Missing features** — anything you wished existed

Be honest. Reference specific files and error messages.
