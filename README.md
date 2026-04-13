# GTM Hub

Internal platform for Twilio Sales tools. Sign in with your `@twilio.com` Google account.

**Live at:** https://gtm-hub.duckdns.org

---

## What's here

```
backend/                        Flask API (auth + app registry)
├── app.py                      Platform: Google OAuth, /api/me, /api/apps
├── salesforce.py               Shared Salesforce client (all apps can use this)
└── apps/
    ├── _template/              Copy this to start a new app
    ├── scorecard/              Original SE Scorecard (CSV upload)
    └── se_scorecard_v2/        SE Scorecard V2 (live Salesforce data)
        ├── manifest.json
        ├── routes.py           API routes + team config + caching
        └── sf_analysis.py      Metric computation, flags, ranking, roasts

frontend/
└── src/
    ├── lib/
    │   ├── api.ts              Typed API helpers
    │   ├── stores.ts           Svelte stores (user, theme, team/period selection)
    │   └── colors.ts           Tier/flag color tokens (P5 + Twilio themes)
    └── routes/
        ├── (launcher)/         Login page + app grid
        ├── (scorecard)/        Original SE Scorecard pages
        └── (se-scorecard-v2)/  SE Scorecard V2 pages
            └── se-scorecard-v2/
                ├── +page.svelte        Team/period selector + summary
                ├── me/                 Individual SE stats + flags + opp tables
                ├── report/             Full team report
                └── rankings/           Power rankings leaderboard

deploy.sh                       One-command deploy to EC2
deploy.env                      Secrets + config (gitignored)
```

---

## SE Scorecard V2

Live Salesforce data for all SE teams. No CSV uploads — data is queried directly and cached per team per period.

### Teams supported

| Key | Label | Motion | Subteams |
|---|---|---|---|
| `digital_sales` | Digital Sales | DSR (Activate / Expansion) | — |
| `dorg` | DORG | AE (New Business / Strategic) | — |
| `namer` | NAMER | AE | Retail, NB, ISV, HighTech, RegVerts, MarTech |
| `emea` | EMEA | AE | North, DACH, South |
| `apj` | APJ | AE | — |
| `latam` | LATAM | AE | Brazil, ROL |

### Periods

Current-year quarters + last 3 full years. Current quarter refreshes every 10 minutes; historical periods cache for 1 week.

### Caching

Cache files live in `backend/outputs/`. Delete them to force a fresh Salesforce fetch. File naming: `sf_se_data_<team>[_<subteam>]_<period>[_min<icav>].json`.

### Salesforce queries (parallel)

All 4 queries fire simultaneously via `ThreadPoolExecutor`:
1. **Closed Won opps** — TW and non-TW, used for all SE metrics
2. **Win rate** — Closed Won + Closed Lost counts per SE
3. **Pipeline opps** — Open opps beyond period end (for email motion classification)
4. **Email tasks** — SE email activity linked to opportunities

Queries 1+2 are required; 3+4 are best-effort (failures skip email activity, don't block the response).

### Adding a new team

Edit `TEAMS` in `backend/apps/se_scorecard_v2/routes.py`:

```python
"my_team": {
    "label":              "My Team",
    "description":        "Short description shown in the UI.",
    "motion":             "ae",   # "ae" = New Business/Strategic, "dsr" = Activate/Expansion
    "soql_filter":        "Technical_Lead__r.UserRole.Name = 'SE - My Team'",
    "email_owner_filter": "Owner.UserRole.Name = 'SE - My Team'",
    "criteria": [
        {"label": "SE Tagged", "detail": "Technical Lead UserRole = 'SE - My Team'"},
    ],
    # Optional: subteams override soql_filter + email_owner_filter
    "subteams": [
        {"key": "my_team_sub", "label": "Sub", "soql_filter": "...", "email_owner_filter": "..."},
    ],
    # Optional: use a different SOQL filter for prior-year historical data
    "historical_soql_filter": "...",
},
```

No other files need to change.

---

## Adding a new app

You need **3 files**. Platform files don't change.

### 1. `backend/apps/<yourapp>/manifest.json`

```json
{
  "id": "myapp",
  "name": "My App",
  "description": "One sentence about what it does.",
  "icon": "🚀",
  "path": "/myapp",
  "status": "live"
}
```

Set `"status": "coming_soon"` to show the card as disabled. Prefix the directory with `_` to hide it from the launcher entirely.

### 2. `backend/apps/<yourapp>/routes.py`

Auth is automatic — every `/api/*` route is already protected.

```python
from __future__ import annotations
from flask import Blueprint, jsonify, session

bp = Blueprint("myapp", __name__)

@bp.route("/api/myapp/data")
def get_data():
    email = session.get("user_email")  # always present
    return jsonify({"user": email, "data": []})
```

> **Note:** Always include `from __future__ import annotations` at the top. The server runs Python 3.9 (AL2023) and `X | Y` union type syntax requires 3.10+. This import makes annotations lazy and safe on 3.9+.

### 3. `frontend/src/routes/(<yourapp>)/<yourapp>/+page.svelte`

The route group `(<yourapp>)` doesn't affect the URL — it's just for layout grouping. Add a `+layout.svelte` in the group folder for custom chrome.

```svelte
<script lang="ts">
  import { user } from '$lib/stores';
  let data = $state(null);
  $effect(async () => {
    const r = await fetch('/api/myapp/data');
    data = await r.json();
  });
</script>

<div>Hello {$user?.email}</div>
```

Copy the full starter from `backend/apps/_template/` and `frontend/src/routes/(template)/`.

---

## Using Salesforce

```python
from salesforce import sf

# SOQL query — returns all records, handles pagination automatically
opps = sf.query("SELECT Id, Name, CloseDate FROM Opportunity WHERE StageName = 'Closed Won'")

# Raw REST API call
record = sf.get("/services/data/v59.0/sobjects/Account/001XXXXXXXXXXXXXXX")
```

Token refresh is automatic. Salesforce credentials come from `deploy.env` and are injected as environment variables on the server.

---

## Running locally

```bash
# Backend — source deploy.env but override FRONTEND_URL to point at local Vite
cd backend
set -a && source ../deploy.env && set +a
LOCAL_DEV=1 FRONTEND_URL="http://localhost:5173" python3 app.py
```

```bash
# Frontend
cd frontend
npm install
npm run dev
```

Frontend: `http://localhost:5173` — Backend: `http://localhost:5001`. Vite proxies `/api/*` to Flask automatically.

> **After modifying backend code**, restart Flask — blueprints are only discovered at startup.

> **To reset cached Salesforce data**, delete files in `backend/outputs/sf_se_data_*.json`.

---

## Deploying

```bash
bash deploy.sh
```

1. Builds SvelteKit frontend (`npm run build`)
2. Tarballs backend + frontend, uploads to S3
3. Terminates any existing tagged EC2 instance
4. Launches fresh AL2023 t3.micro, runs userdata bootstrap:
   - Installs Python 3, nginx, certbot
   - Downloads + extracts app files from S3
   - Installs Python dependencies
   - Creates and starts `app.service` (gunicorn on `127.0.0.1:5000`)
   - Configures nginx to proxy `/api/*` to Flask, serve frontend static files
   - Issues Let's Encrypt SSL cert for the domain
5. Associates Elastic IP
6. Total time: ~7 minutes

Requires `deploy.env` with all secrets set. The domain and frontend URL are configured there.

---

## Platform conventions

| Thing | Convention |
|---|---|
| API routes | Prefix with `/api/<appname>/` |
| Blueprint | Any name, auto-registered from `apps/<name>/routes.py` |
| Hidden apps | Prefix directory with `_` (skipped from launcher + manifests) |
| Manifest | `backend/apps/<name>/manifest.json` |
| Frontend group | `frontend/src/routes/(<name>)/` |
| Salesforce | `from salesforce import sf` |
| Auth | Free — never implement it yourself |
| `/api/me` enrichment | Expose `enrich_me(email) -> dict` in `routes.py` |
| Python compat | Always add `from __future__ import annotations` (server is Python 3.9) |
