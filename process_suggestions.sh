#!/usr/bin/env bash
# process_suggestions.sh
# Reads suggestions from Firestore, deduplicates/filters them with Claude,
# then clones gtm-hub and runs "claude -p" to implement each one
# on its own branch.
#
# Usage: ./process_suggestions.sh
# Must be run from the repo root (same dir as deploy.env).
#
# Prerequisites:
#   - deploy.env with FIRESTORE_PROJECT + FIRESTORE_CREDENTIALS_B64
#   - google-cloud-firestore pip package installed (pip3 install google-cloud-firestore)
#   - git + gh CLI authenticated
#   - claude CLI in PATH (claude -p)
#   - python3 in PATH

set -euo pipefail

export CLAUDE_CODE_MAX_OUTPUT_TOKENS=32000

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

FIRESTORE_COLLECTION="se-scorecard-v2-suggestions"
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
# 1. Download suggestions from Firestore
###############################################################################

echo ""
echo "--- Step 1: Downloading suggestions from Firestore ---"

python3 - "$FIRESTORE_PROJECT" "$FIRESTORE_CREDENTIALS_B64" "$FIRESTORE_COLLECTION" "$SUGGESTIONS_RAW" <<'PYEOF'
import base64, json, sys
from google.cloud import firestore
from google.oauth2 import service_account

project    = sys.argv[1]
creds_b64  = sys.argv[2]
collection = sys.argv[3]
out_file   = sys.argv[4]

info  = json.loads(base64.b64decode(creds_b64).decode())
creds = service_account.Credentials.from_service_account_info(
    info, scopes=["https://www.googleapis.com/auth/datastore"])
db   = firestore.Client(project=project, credentials=creds)
docs = db.collection(collection).order_by("created_at").stream()
items = []
for doc in docs:
    d = doc.to_dict()
    d["id"] = doc.id
    items.append(d)
with open(out_file, "w") as f:
    json.dump(items, f, indent=2)
print(len(items))
PYEOF

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

python3 - "$SUGGESTIONS_FILTERED" "$REPO_DIR" "$FIRESTORE_PROJECT" "$FIRESTORE_CREDENTIALS_B64" "$FIRESTORE_COLLECTION" <<'PYEOF'
import base64, json, os, subprocess, sys, re, textwrap, datetime
from google.cloud import firestore
from google.oauth2 import service_account

suggestions_file = sys.argv[1]
repo_dir         = sys.argv[2]
fs_project       = sys.argv[3]
fs_creds_b64     = sys.argv[4]
fs_collection    = sys.argv[5]

# Initialise Firestore client
_fs_info  = json.loads(base64.b64decode(fs_creds_b64).decode())
_fs_creds = service_account.Credentials.from_service_account_info(
    _fs_info, scopes=["https://www.googleapis.com/auth/datastore"])
db = firestore.Client(project=fs_project, credentials=_fs_creds)

# Single source of truth — loaded once, individual docs updated in Firestore after each suggestion
suggestions = json.load(open(suggestions_file))

def run(cmd, cwd=None, check=True, capture=False):
    kwargs = dict(cwd=cwd, check=check)
    if capture:
        kwargs["capture_output"] = True
        kwargs["text"] = True
    return subprocess.run(cmd, **kwargs)

DELETE_STATUSES = {"done", "security_blocked"}

def writeback(status, suggestion, branch=None, pr_url=None):
    """Update or delete the Firestore document for this suggestion.
    Deletes on done (PR created) or security_blocked — no point keeping them."""
    doc_ref = db.collection(fs_collection).document(suggestion["id"])
    if status in DELETE_STATUSES:
        try:
            doc_ref.delete()
            print(f"  Firestore deleted: [{suggestion['id']}] ({status})")
        except Exception as e:
            print(f"  WARN: Firestore delete failed: {e}")
        return
    # For transient statuses (failed, push_failed, no_changes) just update
    suggestion["status"]       = status
    suggestion["completed_at"] = datetime.datetime.now(datetime.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    update = {"status": status, "completed_at": suggestion["completed_at"]}
    if branch:
        suggestion["branch"] = branch
        update["branch"]     = branch
    if pr_url:
        suggestion["pr_url"] = pr_url
        update["pr_url"]     = pr_url
    try:
        doc_ref.update(update)
        print(f"  Firestore writeback: [{suggestion['id']}] → {status}")
    except Exception as e:
        print(f"  WARN: Firestore writeback failed: {e}")

def sanitize_branch(owner, created_at):
    # For email, use the local part; for phone or anything else, use as-is
    username = owner.split('@')[0] if '@' in owner else owner
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



def implement_suggestion(suggestion, repo_map):
    text   = suggestion["text"]
    owner  = suggestion.get("email") or suggestion.get("phone", "anonymous")
    sid    = suggestion["id"]
    branch = f"suggestion-{sanitize_branch(owner, suggestion.get('created_at', ''))}"

    print(f"\n  Suggestion [{sid}]")
    print(f"  Owner : {owner}")
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
        git_add_cmd  = "git add " + " ".join(f'"{f}"' for f in target_files)
        files_list   = "\n".join(f"  - {f}" for f in target_files)
        context_note = f"Focus your changes on these files (read them with the Read tool first):\n{files_list}"
    else:
        git_add_cmd  = "git add -A"
        context_note = f"The se-scorecard-v2 file tree is:\n{repo_map}\nRead whatever files you need."

    TOKEN_ERRORS = ["prompt is too long", "token limit", "context length", "max_tokens",
                    "rate_limit", "exceeded the 8192"]
    MAX_CONTINUATIONS = 10

    def run_claude_with_continuation(initial_prompt):
        """
        Start a claude -p session and, if it hits the output token limit,
        resume with --continue until the task is complete or we give up.
        Session is saved (no --no-session-persistence) so --continue works.
        Returns (success: bool, last_output: str).
        """
        # ── Initial call ──────────────────────────────────────────────────
        print("  Step B: starting ...", flush=True)
        proc = subprocess.Popen(
            ["claude", "-p", initial_prompt,
             "--model", "sonnet",
             "--dangerously-skip-permissions"],
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
            return True, output

        if not any(e in output.lower() for e in TOKEN_ERRORS):
            print(f"  claude failed (rc={proc.returncode}):")
            print(output[-1000:])
            return False, output

        # ── Continue until done ───────────────────────────────────────────
        for cont in range(1, MAX_CONTINUATIONS + 1):
            print(f"  Step B: continuing (pass {cont}/{MAX_CONTINUATIONS}) ...", flush=True)
            proc = subprocess.Popen(
                ["claude", "--continue", "-p", "continue",
                 "--model", "sonnet",
                 "--dangerously-skip-permissions"],
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
                return True, output

            if not any(e in output.lower() for e in TOKEN_ERRORS):
                print(f"  claude failed on continuation {cont} (rc={proc.returncode}):")
                print(output[-1000:])
                return False, output

        print(f"  Exhausted {MAX_CONTINUATIONS} continuations.")
        return False, ""

    # ── Step B: single claude session with continuation support ───────────
    prompt = textwrap.dedent(f"""\
        Implement this suggestion in gtm-hub (se-scorecard-v2 app only): "{text}"

        The se-scorecard-v2 app lives in:
          - backend:  backend/apps/se_scorecard_v2/
          - frontend: frontend/src/routes/se-scorecard-v2/  (and related components)

        {context_note}

        Do not modify any other app. After making all changes, you MUST:
        1. Stage changed files: {git_add_cmd}
        2. Commit: git commit -m "suggestion: {text[:80]}"

        The task is NOT complete until git commit has run successfully.
    """)

    ok, _ = run_claude_with_continuation(prompt)
    if not ok:
        writeback("failed", suggestion)
        return False

    # ── Catch any uncommitted changes claude left behind ───────────────────
    diff_uncommitted = run(["git", "diff"],             cwd=repo_dir, capture=True).stdout
    diff_staged      = run(["git", "diff", "--cached"], cwd=repo_dir, capture=True).stdout
    if diff_uncommitted.strip() or diff_staged.strip():
        print("  Staging and committing leftover changes ...")
        add_args = target_files if target_files else ["-A"]
        run(["git", "add"] + add_args, cwd=repo_dir)
        run(["git", "commit", "-m", f"suggestion: {text[:80]}"], cwd=repo_dir, check=False)

    diff_text = run(["git", "diff", "main...HEAD"], cwd=repo_dir, capture=True).stdout
    if not diff_text.strip():
        print("  No changes detected after implementation, skipping push.")
        writeback("no_changes", suggestion)
        return False

    # ── Security review (Haiku — classify only the diff lines) ───────────
    # Feed ONLY the raw diff — no surrounding context — to avoid hallucination
    # about code that appears elsewhere in the conversation.
    sec_prompt = (
        "You are a security reviewer. Read the git diff below and reply with ONLY:\n"
        "  SAFE   — if there are no significant security issues in the changed lines\n"
        "  UNSAFE <reason> — if the changed lines introduce a real security risk\n\n"
        "Rules:\n"
        "- Judge ONLY the lines prefixed with + or - in the diff.\n"
        "- Do NOT comment on code that is not in the diff.\n"
        "- Hardcoded reference data (e.g. revenue figures, thresholds) is NOT a risk.\n"
        "- Minor style issues are NOT security issues.\n\n"
        "Diff:\n"
        + diff_text[:6000]
    )

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

    # ── Open a pull request ────────────────────────────────────────────────
    pr_result = subprocess.run(
        ["gh", "pr", "create",
         "--title", f"Suggestion: {text[:72]}",
         "--body", f"**Submitted by:** {owner}\n\n**Suggestion:**\n{text}\n\n---\n*Auto-implemented by process_suggestions.sh*",
         "--head", branch,
         "--base", "main"],
        cwd=repo_dir, capture_output=True, text=True,
    )
    if pr_result.returncode == 0:
        pr_url = pr_result.stdout.strip()
        print(f"  PR created: {pr_url}")
        writeback("done", suggestion, branch=branch, pr_url=pr_url)
    else:
        print(f"  WARN: PR creation failed: {pr_result.stderr.strip()[:200]}")
        writeback("done", suggestion, branch=branch)
    return True


# ── Build repo map once, reuse for every suggestion ───────────────────────
print("  Building repo map ...")
repo_map = build_repo_map(repo_dir)
print(repo_map)

# ── Main loop ─────────────────────────────────────────────────────────────
ok_count = fail_count = 0

for i, suggestion in enumerate(suggestions, 1):
    status = suggestion.get("status")
    branch = suggestion.get("branch")

    if status in ("done", "security_blocked"):
        # These should have been deleted from Firestore — if still present, skip
        print(f"\n[{i}/{len(suggestions)}] Skipping (already {status}): {suggestion['text'][:80]}")
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
