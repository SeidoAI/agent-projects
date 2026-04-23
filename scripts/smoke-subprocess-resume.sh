#!/usr/bin/env bash
# Real-claude smoke test for the subprocess resume flow.
#
# Forces a stop-and-ask (plan.md asks an unanswerable question),
# then adds a "## PM follow-up" section and re-spawns with --resume.
# Asserts the agent picks up prior context after resume.
#
# Usage: bash scripts/smoke-subprocess-resume.sh
# Env:   TW_SMOKE_TIMEOUT  seconds to wait for each spawn (default 180)

set -euo pipefail

TIMEOUT="${TW_SMOKE_TIMEOUT:-180}"
TRIPWIRE="${TRIPWIRE:-tripwire}"

if ! command -v "$TRIPWIRE" >/dev/null; then
  echo "FAIL: tripwire not found. Set TRIPWIRE=/path/to/tripwire" >&2
  exit 1
fi
for bin in claude git; do
  if ! command -v "$bin" >/dev/null; then
    echo "FAIL: $bin not on PATH" >&2
    exit 1
  fi
done

tmp_root="$(mktemp -d -t tripwire-smoke-resume-XXXXXX)"
project_dir="$tmp_root/project"
clone_dir="$tmp_root/clone"
mkdir -p "$project_dir" "$clone_dir"

SESSION_ID="smk-resume-1"
cleanup() {
  local exit_code=$?
  "$TRIPWIRE" session abandon "$SESSION_ID" \
    --project-dir "$project_dir" 2>/dev/null || true
  if (( exit_code != 0 )); then
    echo "--- FAIL (exit=$exit_code). Tree: $tmp_root" >&2
    "$TRIPWIRE" session logs "$SESSION_ID" \
      --project-dir "$project_dir" --tail 80 2>/dev/null || true
  else
    rm -rf "$tmp_root"
  fi
}
trap cleanup EXIT

# Seed clone.
(
  cd "$clone_dir"
  git init -q -b main
  git -c user.name=smoke -c user.email=smoke@example.com \
    commit --allow-empty -q -m "smoke root"
)

# Project scaffold.
cat > "$project_dir/project.yaml" <<YAML
name: smoke-resume
key_prefix: SMK
next_issue_number: 1
next_session_number: 1
repos:
  SeidoAI/smoke-code:
    local: $clone_dir
YAML
mkdir -p "$project_dir"/{issues,nodes,sessions,docs,plans,agents,templates/artifacts}
cat > "$project_dir/agents/backend-coder.yaml" <<YAML
id: backend-coder
context:
  skills: []
YAML

# Session with an ambiguous plan that forces stop-and-ask.
# spawn_config overrides prompt_template so the agent doesn't attempt
# the push+PR exit protocol against a local-only repo.
mkdir -p "$project_dir/sessions/$SESSION_ID"
cat > "$project_dir/sessions/$SESSION_ID/session.yaml" <<YAML
---
id: $SESSION_ID
name: Smoke resume
agent: backend-coder
issues: []
status: planned
repos:
  - repo: SeidoAI/smoke-code
    base_branch: main
spawn_config:
  config:
    max_turns: 20
  prompt_template: |
    {plan}

    You are running headless (claude -p). Execute the plan and exit.
    Do NOT push, do NOT open a PR — this is a local-only smoke test.
    If you need clarification, write your question as plain text in
    your final response and stop. The PM will update the plan and
    respawn you with --resume.
---
YAML
cat > "$project_dir/sessions/$SESSION_ID/plan.md" <<'MD'
# Resume smoke plan

Your task has two phases.

**Phase 1 (now):** Decide the magic password. The password must
meet a policy that isn't specified here. If you can't work it out
from context, **stop and ask in plain text** — do NOT invent one.
This is intentional.

**Phase 2 (on resume):** Once the PM supplies the password in a
`## PM follow-up` section, create `password.txt` containing
exactly the password string. Commit with message `smoke: password`.
MD
handoff_uuid="$(uuidgen | tr '[:upper:]' '[:lower:]')"
handoff_at="$(date -u +%Y-%m-%dT%H:%M:%SZ)"
cat > "$project_dir/sessions/$SESSION_ID/handoff.yaml" <<YAML
---
uuid: $handoff_uuid
session_id: $SESSION_ID
handoff_at: $handoff_at
handed_off_by: pm
branch: feat/$SESSION_ID
---
YAML

_show_json() {
  "$TRIPWIRE" session show "$SESSION_ID" --project-dir "$project_dir" --format json 2>/dev/null
}
_get_pid() {
  _show_json | python3 -c 'import json,sys; print(json.load(sys.stdin).get("runtime_state",{}).get("pid") or "")'
}
_get_status() {
  _show_json | python3 -c 'import json,sys; print(json.load(sys.stdin).get("status",""))'
}

_wait_for_exit() {
  local phase="$1" pid="$2" deadline=$(( $(date +%s) + TIMEOUT ))
  while :; do
    if [[ -n "$pid" ]] && ! kill -0 "$pid" 2>/dev/null; then
      echo "$phase: claude subprocess (pid $pid) has exited"
      return 0
    fi
    if (( $(date +%s) > deadline )); then
      echo "FAIL: $phase timed out after ${TIMEOUT}s (pid=$pid still alive)" >&2
      return 1
    fi
    sleep 2
  done
}

# Phase 1: queue + spawn; expect the agent to stop-and-ask.
"$TRIPWIRE" session queue "$SESSION_ID" --project-dir "$project_dir"
"$TRIPWIRE" session spawn "$SESSION_ID" --project-dir "$project_dir"

PHASE1_PID="$(_get_pid)"
_wait_for_exit "phase 1" "$PHASE1_PID" || exit 1

# Phase 1 should have stopped-to-ask: the summary heuristic flags this.
if ! "$TRIPWIRE" session summary "$SESSION_ID" --project-dir "$project_dir" \
  | grep -qi "stopped to ask"; then
  echo "WARN: phase 1 did not obviously stop-to-ask — continuing anyway" >&2
fi

# Phase 2: supply the follow-up answer + pause→paused before --resume.
cat >> "$project_dir/sessions/$SESSION_ID/plan.md" <<'MD'

## PM follow-up

The magic password is `hunter2`. Proceed with Phase 2.
MD

# --resume requires status 'paused' or 'failed'. tripwire doesn't
# auto-flip status when the subprocess exits, so phase 1 leaves it
# as 'executing' with a dead pid. `session pause` sees the dead pid
# and transitions to 'failed', which --resume accepts.
status="$(_get_status)"
if [[ "$status" == "executing" ]]; then
  "$TRIPWIRE" session pause "$SESSION_ID" --project-dir "$project_dir" || true
fi

"$TRIPWIRE" session spawn "$SESSION_ID" --project-dir "$project_dir" --resume

PHASE2_PID="$(_get_pid)"
_wait_for_exit "phase 2" "$PHASE2_PID" || exit 1

# Phase 2 assertion: password.txt exists with 'hunter2'.
password_file="$(
  find "$tmp_root" -maxdepth 6 -name "password.txt" 2>/dev/null | head -n1
)"
if [[ -z "$password_file" ]]; then
  echo "FAIL: password.txt was not created on resume" >&2
  exit 1
fi
if ! grep -q "^hunter2$" "$password_file"; then
  echo "FAIL: password.txt does not contain 'hunter2': $(cat "$password_file")" >&2
  exit 1
fi

"$TRIPWIRE" session summary "$SESSION_ID" --project-dir "$project_dir" || true

echo "PASS: subprocess-resume smoke"
