#!/usr/bin/env bash
# process_suggestions.sh
# Reads suggestions from S3, deduplicates/filters them with Claude,
# then clones gtm-hub and runs "claude -p" to implement each one
# on its own branch.
#
# Usage: ./process_suggestions.sh
# Must be run from the repo root (same dir as deploy.env).
#
# Prerequisites:
#   - AWS CLI configured (uses PROFILE from deploy.env)
#   - git + gh CLI authenticated
#   - claude CLI in PATH (claude -p)
#   - python3 in PATH

set -euo pipefail

###############################################################################
# 0. Config
###############################################################################

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
ENV_FILE="$SCRIPT_DIR/deploy.env"

if [[ ! -f "$ENV_FILE" ]]; then
  echo "ERROR: deploy.env not found at $SCRIPT_DIR/deploy.env" >&2
  exit 1
fi

# shellcheck source=/dev/null
source "$ENV_FILE"

SUGGESTIONS_S3_KEY="suggestions/se-scorecard-v2.json"
REPO_URL="https://github.com/kali-twilio/gtm-hub"
WORK_DIR="$(mktemp -d)"
SUGGESTIONS_RAW="$WORK_DIR/suggestions_raw.json"
SUGGESTIONS_FILTERED="$WORK_DIR/suggestions_filtered.json"
LOG_FILE="$SCRIPT_DIR/process_suggestions.log"

echo "Work dir: $WORK_DIR"
echo "Log: $LOG_FILE"

# Redirect a copy of all output to the log file
exec > >(tee -a "$LOG_FILE") 2>&1

echo ""
echo "========================================================"
echo "process_suggestions.sh  $(date -u '+%Y-%m-%dT%H:%M:%SZ')"
echo "========================================================"

###############################################################################
# 1. Download suggestions JSON from S3
###############################################################################

echo ""
echo "--- Step 1: Downloading suggestions from S3 ---"

aws s3 cp "s3://$BUCKET/$SUGGESTIONS_S3_KEY" "$SUGGESTIONS_RAW" \
  --profile "$PROFILE" \
  --region  "$REGION"

TOTAL=$(python3 -c "import json; d=json.load(open('$SUGGESTIONS_RAW')); print(len(d))")
echo "Downloaded $TOTAL suggestions."

###############################################################################
# 2. Deduplicate / filter with Claude
###############################################################################

echo ""
echo "--- Step 2: Filtering suggestions with Claude ---"

RAW_JSON=$(cat "$SUGGESTIONS_RAW")

FILTER_PROMPT=$(cat <<'PROMPT'
You are a suggestion quality filter for an internal sales engineering scorecard app.

Given the JSON array of suggestion objects below, return a cleaned JSON array following these rules:

REMOVAL rules (remove the entry entirely):
1. Duplicates — if two suggestions have the same or very similar intent, keep only the first one.
2. Security risks — anything asking to expose credentials, bypass auth, dump data, etc.
3. Jokes / memes / nonsense — clearly non-serious entries.
4. Test messages — "test", "asdf", placeholder text, etc.

KEEP rules:
- Genuine feature requests, UX improvements, data/metric changes, etc.
- Minor wording differences count as duplicates only if the underlying intent is identical.
- Any item that already has a "status" field (e.g. "done", "security_blocked") — always preserve
  these exactly as-is, they have already been processed.

Return ONLY valid JSON — the filtered array with the same object shape as the input.
No explanation, no markdown fences, just the raw JSON array.

INPUT:
PROMPT
)

FILTERED=$(echo "$FILTER_PROMPT"$'\n'"$RAW_JSON" | claude -p \
  --model haiku \
  --output-format text \
  --no-session-persistence \
  2>&1)

# Strip markdown fences if present, then validate JSON.
# Falls back to raw suggestions if Claude prefixes conversational text.
python3 -c "
import json, sys, re

def try_extract(text):
    text = re.sub(r'^\s*\`\`\`[a-z]*\s*', '', text.strip())
    text = re.sub(r'\s*\`\`\`\s*$', '', text)
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        pass
    # Handle leading prose before the array
    m = re.search(r'(\[.*\])', text, re.DOTALL)
    if m:
        try:
            return json.loads(m.group(1))
        except json.JSONDecodeError:
            pass
    return None

raw = sys.stdin.read()
d = try_extract(raw)
if d is None:
    print('ERROR: could not parse filtered JSON', file=sys.stderr)
    sys.exit(1)
print(json.dumps(d, indent=2))
" <<< "$FILTERED" > "$SUGGESTIONS_FILTERED" || {
    echo "WARN: filter step JSON parse failed — using unfiltered suggestions."
    cp "$SUGGESTIONS_RAW" "$SUGGESTIONS_FILTERED"
}

KEPT=$(python3 -c "import json; d=json.load(open('$SUGGESTIONS_FILTERED')); print(len(d))")
echo "Kept $KEPT / $TOTAL suggestions after filtering."

###############################################################################
# 3. Clone the repo into the work dir
###############################################################################

echo ""
echo "--- Step 3: Cloning $REPO_URL ---"

REPO_DIR="$WORK_DIR/gtm-hub"
GH_TOKEN=$(gh auth token)
GH_USER=$(gh api user --jq .login)

git clone "$REPO_URL" "$REPO_DIR"
# Set token-authenticated remote so headless pushes work without keychain
git -C "$REPO_DIR" remote set-url origin \
  "https://${GH_USER}:${GH_TOKEN}@github.com/kali-twilio/gtm-hub.git"
# Set git identity for commits made inside the temp clone
git -C "$REPO_DIR" config user.email "$(gh api user --jq .email 2>/dev/null || echo "${GH_USER}@users.noreply.github.com")"
git -C "$REPO_DIR" config user.name  "$GH_USER"
echo "Cloned to $REPO_DIR (authenticated as $GH_USER)"

###############################################################################
# 4. Process each suggestion
###############################################################################

echo ""
echo "--- Step 4: Implementing suggestions ---"

python3 - "$SUGGESTIONS_FILTERED" "$REPO_DIR" "$ENV_FILE" "$BUCKET" "$PROFILE" "$REGION" "$SUGGESTIONS_S3_KEY" <<'PYEOF'
import json, os, subprocess, sys, re, textwrap, datetime

suggestions_file = sys.argv[1]
repo_dir         = sys.argv[2]
env_file         = sys.argv[3]
s3_bucket        = sys.argv[4]
aws_profile      = sys.argv[5]
aws_region       = sys.argv[6]
s3_key           = sys.argv[7]

# Single source of truth — loaded once, mutated in place, written back to S3 after each suggestion
suggestions = json.load(open(suggestions_file))

def run(cmd, cwd=None, check=True, capture=False):
    kwargs = dict(cwd=cwd, check=check)
    if capture:
        kwargs["capture_output"] = True
        kwargs["text"] = True
    return subprocess.run(cmd, **kwargs)

def writeback(status, suggestion, branch=None):
    """Stamp status on the suggestion object and push the full JSON back to S3."""
    suggestion["status"]       = status
    suggestion["completed_at"] = datetime.datetime.now(datetime.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    if branch:
        suggestion["branch"] = branch
    tmp = "/tmp/se-scorecard-v2-writeback.json"
    with open(tmp, "w") as f:
        json.dump(suggestions, f, indent=2)
    result = subprocess.run(
        ["aws", "s3", "cp", tmp, f"s3://{s3_bucket}/{s3_key}",
         "--profile", aws_profile, "--region", aws_region],
        capture_output=True, text=True,
    )
    if result.returncode == 0:
        print(f"  S3 writeback: [{suggestion['id']}] → {status}")
    else:
        print(f"  WARN: S3 writeback failed: {result.stderr.strip()}")

def sanitize_branch(email, created_at):
    username = email.split('@')[0]
    safe = re.sub(r'[^a-zA-Z0-9._-]', '-', username).strip('-')
    # Use unix timestamp so branches sort chronologically for the same person
    try:
        ts = int(datetime.datetime.fromisoformat(created_at.replace("Z", "+00:00")).timestamp())
    except Exception:
        ts = int(datetime.datetime.now(datetime.timezone.utc).timestamp())
    return f"{safe[:40]}-{ts}"

def strip_fences(text):
    """Remove markdown code fences from a Claude response."""
    text = re.sub(r'^\s*```[a-z]*\s*', '', text.strip())
    text = re.sub(r'\s*```\s*$', '', text)
    return text.strip()

def build_repo_map(repo_dir):
    """
    Walk the se-scorecard-v2 app dirs and return a compact tree string.
    Discovers route dirs dynamically so renamed paths don't silently break.
    Skips __pycache__, node_modules, .svelte-kit, build, dist.
    """
    SKIP_DIRS = {"__pycache__", "node_modules", ".svelte-kit", "build", ".git", "dist"}

    # Discover frontend routes dir dynamically — find any dir whose name contains
    # "se-scorecard" or "se_scorecard" under frontend/src/routes/
    routes_base = os.path.join(repo_dir, "frontend", "src", "routes")
    scorecard_route = None
    if os.path.isdir(routes_base):
        for entry in os.listdir(routes_base):
            if "scorecard" in entry.lower() and "v2" in entry.lower():
                scorecard_route = os.path.join(routes_base, entry)
                break

    ROOTS = [
        os.path.join(repo_dir, "backend", "apps", "se_scorecard_v2"),
        scorecard_route,
        os.path.join(repo_dir, "frontend", "src", "lib"),
    ]

    lines = []
    for root_path in ROOTS:
        if not root_path or not os.path.isdir(root_path):
            continue
        rel_root = os.path.relpath(root_path, repo_dir)
        lines.append(f"{rel_root}/")
        for dirpath, dirnames, filenames in os.walk(root_path):
            dirnames[:] = [d for d in sorted(dirnames) if d not in SKIP_DIRS]
            depth = dirpath.replace(root_path, "").count(os.sep)
            indent = "  " * (depth + 1)
            for fname in sorted(filenames):
                rel = os.path.relpath(os.path.join(dirpath, fname), repo_dir)
                lines.append(f"{indent}{rel}")
    return "\n".join(lines)

def identify_files(suggestion_text, repo_map):
    """
    Step A — Haiku: given the suggestion and the repo map, return the list of
    file paths (relative to repo root) that need to change.
    Returns a list of strings, or [] on failure.
    """
    prompt = textwrap.dedent(f"""\
        You are a code planner for a SvelteKit + Flask web app called gtm-hub.

        Given the suggestion below and the file tree of the se-scorecard-v2 app,
        return a JSON array of file paths (relative to the repo root) that will
        need to be created or modified to implement the suggestion.

        Rules:
        - Only include files within the se-scorecard-v2 app.
        - Be precise — only files that definitely need changing.
        - Return ONLY a raw JSON array of strings, no explanation, no fences.

        Suggestion: "{suggestion_text}"

        File tree:
        {repo_map}
    """)

    result = subprocess.run(
        ["claude", "-p", prompt,
         "--model", "haiku",
         "--no-session-persistence"],
        capture_output=True, text=True,
    )
    raw = strip_fences((result.stdout + result.stderr).strip())
    try:
        files = json.loads(raw)
        if isinstance(files, list):
            # Resolve to absolute paths that actually exist
            valid = []
            for f in files:
                abs_path = os.path.join(repo_dir, f)
                if os.path.isfile(abs_path):
                    valid.append(f)
                else:
                    print(f"  WARN: identified file not found, skipping: {f}")
            print(f"  Step A identified {len(valid)} file(s): {valid}")
            return valid
    except Exception as e:
        print(f"  WARN: could not parse file list from haiku ({e}), falling back to full context")
    return []

def build_file_context(file_paths):
    """Read each identified file and return them as a single inline context block."""
    blocks = []
    for rel_path in file_paths:
        abs_path = os.path.join(repo_dir, rel_path)
        try:
            content = open(abs_path).read()
            blocks.append(f"### {rel_path}\n```\n{content}\n```")
        except Exception as e:
            print(f"  WARN: could not read {rel_path}: {e}")
    return "\n\n".join(blocks)

SYSTEM_PROMPT = textwrap.dedent("""\
    You are working on gtm-hub, an internal Twilio sales engineering dashboard.
    Tech stack:
      - Frontend: SvelteKit (TypeScript), Tailwind CSS, component files are .svelte
      - Backend: Python Flask, one Blueprint per app under backend/apps/
      - The se-scorecard-v2 app specifically: backend/apps/se_scorecard_v2/ (routes.py,
        sf_analysis.py) + a SvelteKit route under frontend/src/routes/se-scorecard-v2/
      - Shared frontend utilities live in frontend/src/lib/
    Always follow the existing code style. Do not touch any other app.
""")

def implement_suggestion(suggestion, repo_map):
    text   = suggestion["text"]
    email  = suggestion["email"]
    sid    = suggestion["id"]
    branch = f"suggestion-{sanitize_branch(email, suggestion['created_at'])}"

    print(f"\n  Suggestion [{sid}]")
    print(f"  Email : {email}")
    print(f"  Branch: {branch}")
    print(f"  Text  : {text}")

    # Reset to clean main
    run(["git", "checkout", "main"],  cwd=repo_dir)
    run(["git", "pull", "--ff-only"], cwd=repo_dir, check=False)
    result = run(["git", "checkout", "-B", branch], cwd=repo_dir, check=False)
    if result.returncode != 0:
        print("  WARN: could not create branch, skipping.")
        writeback("failed", suggestion)
        return False

    # ── Step A: identify which files need changing (Haiku) ────────────────
    print("  Step A: identifying files to change ...")
    target_files = identify_files(text, repo_map)

    if target_files:
        file_context = build_file_context(target_files)
        files_list   = "\n".join(f"  - {f}" for f in target_files)
        # Stage only the identified files to limit blast radius
        git_add_cmd  = "git add " + " ".join(f'"{f}"' for f in target_files)
        context_note = textwrap.dedent(f"""\
            Focus your changes on these files (already read for you below):
            {files_list}

            Current file contents:
            {file_context}
        """)
    else:
        # Fallback: give Claude the repo map and let it find files itself
        git_add_cmd  = "git add -A"
        context_note = textwrap.dedent(f"""\
            The se-scorecard-v2 file tree is:
            {repo_map}
        """)

    # ── Step B: implement (Sonnet) ─────────────────────────────────────────
    prompt = textwrap.dedent(f"""\
        Implement this suggestion: "{text}" in gtm-hub but only for the se-scorecard-v2 app.

        The se-scorecard-v2 app lives in:
          - backend:  backend/apps/se_scorecard_v2/
          - frontend: frontend/src/routes/se-scorecard-v2/  (and related components)

        {context_note}

        Do not modify any other app. After making all changes, you MUST:
        1. Stage changed files with: {git_add_cmd}
        2. Commit with a descriptive message: git commit -m "suggestion: {text}"

        The task is NOT complete until you have run git commit successfully.
        Verify with: git log --oneline -1
    """)

    TOKEN_ERRORS = ["prompt is too long", "token limit", "context length", "max_tokens", "rate_limit"]
    MAX_ATTEMPTS = 5

    for attempt in range(1, MAX_ATTEMPTS + 1):
        print(f"  Step B: claude attempt {attempt}/{MAX_ATTEMPTS} ...", flush=True)

        # Stream output live so progress is visible in the log, while also
        # collecting it for error detection
        proc = subprocess.Popen(
            ["claude", "-p", prompt,
             "--model", "sonnet",
             "--dangerously-skip-permissions",
             "--no-session-persistence",
             "--append-system-prompt", SYSTEM_PROMPT],
            cwd=repo_dir,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            text=True,
        )
        output_lines = []
        for line in proc.stdout:
            print(f"    {line}", end="", flush=True)
            output_lines.append(line)
        proc.wait()
        output = "".join(output_lines)

        if proc.returncode == 0:
            print("  claude succeeded.")
            break

        if any(e in output.lower() for e in TOKEN_ERRORS):
            print(f"  Hit token/rate limit on attempt {attempt}, retrying...")
            continue

        print(f"  claude failed (rc={proc.returncode}):")
        print(output[-2000:])
        writeback("failed", suggestion)
        return False
    else:
        print(f"  Exhausted {MAX_ATTEMPTS} attempts, skipping.")
        writeback("failed", suggestion)
        return False

    # ── Catch any uncommitted changes claude left behind ───────────────────
    diff_uncommitted = run(["git", "diff"],             cwd=repo_dir, capture=True).stdout
    diff_staged      = run(["git", "diff", "--cached"], cwd=repo_dir, capture=True).stdout
    if diff_uncommitted.strip() or diff_staged.strip():
        print("  Staging and committing leftover changes ...")
        add_args = target_files if target_files else ["-A"]
        run(["git", "add"] + add_args, cwd=repo_dir)
        run(["git", "commit", "-m", f"suggestion: {text}"], cwd=repo_dir, check=False)

    diff_text = run(["git", "diff", "main...HEAD"], cwd=repo_dir, capture=True).stdout
    if not diff_text.strip():
        print("  No changes detected after implementation, skipping push.")
        writeback("no_changes", suggestion)
        return False

    # ── Security review (Haiku — diff is a classification task) ───────────
    sec_prompt = textwrap.dedent(f"""\
        Review the following git diff for security issues.
        Focus on: SQL/shell/XSS injection, exposed secrets or credentials,
        broken authentication, insecure direct object references, path traversal,
        and any other OWASP Top-10 risks.

        Reply with ONLY one of:
          SAFE   — no significant security issues
          UNSAFE — followed by a brief description of the issue(s)

        Diff:
        {diff_text[:8000]}
    """)

    sec_result = subprocess.run(
        ["claude", "-p", sec_prompt,
         "--model", "haiku",
         "--no-session-persistence"],
        capture_output=True, text=True,
    )
    sec_output = (sec_result.stdout + sec_result.stderr).strip()
    print(f"  Security review: {sec_output[:300]}")

    if sec_output.upper().startswith("UNSAFE"):
        print("  SECURITY ISSUE detected — skipping push.")
        run(["git", "checkout", "main"], cwd=repo_dir)
        writeback("security_blocked", suggestion)
        return False

    # ── Push ───────────────────────────────────────────────────────────────
    print("  Pushing branch ...")
    push_result = run(
        ["git", "push", "--force-with-lease", "origin", branch],
        cwd=repo_dir, check=False,
    )
    if push_result.returncode != 0:
        print("  WARN: push failed.")
        writeback("push_failed", suggestion)
        return False

    print(f"  Done — branch '{branch}' pushed.")
    writeback("done", suggestion, branch=branch)
    return True

# ── Build repo map once, reuse for every suggestion ───────────────────────
print("  Building repo map ...")
repo_map = build_repo_map(repo_dir)
print(repo_map)

# ── Main loop ─────────────────────────────────────────────────────────────
ok_count = fail_count = 0

for i, suggestion in enumerate(suggestions, 1):
    if suggestion.get("status") in ("done", "security_blocked"):
        print(f"\n[{i}/{len(suggestions)}] Skipping (already {suggestion['status']}): {suggestion['text']}")
        continue

    print(f"\n[{i}/{len(suggestions)}] Processing suggestion ...")
    try:
        if implement_suggestion(suggestion, repo_map):
            ok_count += 1
        else:
            fail_count += 1
    except Exception as exc:
        print(f"  ERROR: {exc}")
        writeback("failed", suggestion)
        fail_count += 1

print(f"\n=== Done: {ok_count} succeeded, {fail_count} failed ===")
PYEOF

###############################################################################
# 5. Cleanup
###############################################################################

echo ""
echo "--- Step 5: Cleaning up temp dir ---"
rm -rf "$WORK_DIR"
echo "Removed $WORK_DIR"
echo ""
echo "All done. Full log at: $LOG_FILE"
