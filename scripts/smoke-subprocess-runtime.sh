#!/usr/bin/env bash
# Real-claude smoke test for the subprocess runtime.
#
# Exercises the full happy path: queue + spawn a trivial session,
# wait for the agent to finish, verify it created a file and made a
# commit. Requires `claude` + `tripwire` + `git` + `gh` on PATH.
#
# Usage:  bash scripts/smoke-subprocess-runtime.sh
# Env:    TW_SMOKE_TIMEOUT  seconds to wait for agent exit (default 240)

set -euo pipefail

TIMEOUT="${TW_SMOKE_TIMEOUT:-240}"
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

tmp_root="$(mktemp -d -t tripwire-smoke-XXXXXX)"
project_dir="$tmp_root/project"
clone_dir="$tmp_root/clone"
mkdir -p "$project_dir" "$clone_dir"

cleanup() {
  local exit_code=$?
  if [[ -n "${SESSION_ID:-}" ]]; then
    "$TRIPWIRE" session abandon "$SESSION_ID" \
      --project-dir "$project_dir" 2>/dev/null || true
  fi
  if (( exit_code != 0 )); then
    echo "--- FAIL (exit=$exit_code). Tree: $tmp_root" >&2
    if [[ -n "${LOG_PATH:-}" && -f "$LOG_PATH" ]]; then
      echo "--- Last 50 lines of $LOG_PATH ---" >&2
      tail -n 50 "$LOG_PATH" >&2 || true
    fi
  else
    rm -rf "$tmp_root"
  fi
}
trap cleanup EXIT

# 1. Seed the clone with an empty commit on main.
(
  cd "$clone_dir"
  git init -q -b main
  git -c user.name=smoke -c user.email=smoke@example.com \
    commit --allow-empty -q -m "smoke root"
)

# 2. Write tripwire project scaffolding.
cat > "$project_dir/project.yaml" <<YAML
name: smoke
key_prefix: SMK
next_issue_number: 1
next_session_number: 1
repos:
  SeidoAI/smoke-code:
    local: $clone_dir
YAML
mkdir -p "$project_dir"/{issues,nodes,sessions,docs,plans,agents,templates/artifacts}

# 3. Agent definition (no sub-agent tools, matches subprocess default).
cat > "$project_dir/agents/backend-coder.yaml" <<YAML
id: backend-coder
context:
  skills: []
YAML

# 4. Session + plan. Session + handoff yaml need frontmatter delimiters.
# spawn_config overrides the shipped prompt_template so the agent doesn't
# try to push / open a PR (no remote configured; local-only smoke).
SESSION_ID="smk-smoke-1"
mkdir -p "$project_dir/sessions/$SESSION_ID"
cat > "$project_dir/sessions/$SESSION_ID/session.yaml" <<YAML
---
id: $SESSION_ID
name: Smoke subprocess
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
    Do NOT push, do NOT open a PR — this is a local-only smoke test
    with no remote configured. Simply make the commit and stop.
---
YAML
cat > "$project_dir/sessions/$SESSION_ID/plan.md" <<'MD'
# Smoke plan

Create a file named `hello.txt` with the single-line contents `hi`
in the repo root. Commit it with the message `smoke: hello`. Do not
push and do not open a PR — this is a local-only smoke test. When
done, simply exit.
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

# 5. Queue + spawn.
"$TRIPWIRE" session queue "$SESSION_ID" --project-dir "$project_dir"
"$TRIPWIRE" session spawn "$SESSION_ID" --project-dir "$project_dir"

# Capture log path + pid (via json for reliable parsing).
_show_json() {
  "$TRIPWIRE" session show "$SESSION_ID" --project-dir "$project_dir" --format json 2>/dev/null
}
LOG_PATH="$(_show_json | python3 -c 'import json,sys; print(json.load(sys.stdin).get("runtime_state",{}).get("log_path") or "")')"
PID="$(_show_json | python3 -c 'import json,sys; print(json.load(sys.stdin).get("runtime_state",{}).get("pid") or "")')"

# 6. Poll until the claude subprocess exits (or timeout). tripwire
# doesn't auto-flip session.status when the child exits; we check the
# pid directly.
deadline=$(( $(date +%s) + TIMEOUT ))
while :; do
  if [[ -n "$PID" ]] && ! kill -0 "$PID" 2>/dev/null; then
    echo "smoke: claude subprocess (pid $PID) has exited"
    break
  fi
  if (( $(date +%s) > deadline )); then
    echo "FAIL: timed out after ${TIMEOUT}s (pid=$PID still alive)" >&2
    exit 1
  fi
  sleep 2
done

# 7. Assertions — worktree contains the expected artifact. Tripwire
# worktrees live at <clone>-wt-<session_id> (siblings of the clone),
# so we search under tmp_root.
worktree="$(find "$tmp_root" -maxdepth 6 -name "hello.txt" 2>/dev/null | head -n1)"

if [[ -z "$worktree" ]]; then
  echo "FAIL: hello.txt not created anywhere under $tmp_root" >&2
  exit 1
fi
if ! grep -q "^hi$" "$worktree"; then
  echo "FAIL: hello.txt does not contain 'hi': $(cat "$worktree")" >&2
  exit 1
fi

worktree_dir="$(dirname "$worktree")"
# `git log | grep -q` misbehaves under `set -o pipefail`: grep may
# close the pipe early (SIGPIPE), git log exits 141, pipefail
# propagates that to the pipeline. Capture first, then match.
git_log="$(git -C "$worktree_dir" log --oneline -n 5)"
if [[ "$git_log" != *"smoke: hello"* ]]; then
  echo "FAIL: no 'smoke: hello' commit in $worktree_dir" >&2
  echo "--- git log ---" >&2
  echo "$git_log" >&2
  exit 1
fi

# Summary is nice-to-have; failure here doesn't fail the smoke.
"$TRIPWIRE" session summary "$SESSION_ID" --project-dir "$project_dir" || true

echo "PASS: subprocess-runtime smoke"
