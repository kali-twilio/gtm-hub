# GTM Hub

Internal platform for Twilio Sales tools. Sign in with your `@twilio.com` Google account.

**Live at:** https://se-scorecard.duckdns.org

---

## What's here

```
backend/                  Flask API (auth + app registry)
├── app.py                Platform: Google OAuth, /api/me, /api/apps
├── salesforce.py         Shared Salesforce client (all apps can use this)
└── apps/
    ├── _template/        Copy this to start a new app
    └── scorecard/        SE Scorecard app

frontend/                 SvelteKit frontend
└── src/routes/
    ├── (launcher)/       Login page + app grid
    └── (scorecard)/      SE Scorecard pages
```

---

## Adding a new app

You need **3 files**. Platform files don't change.

### 1. Backend — `backend/apps/<yourapp>/manifest.json`

Controls how your app appears in the launcher.

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

Set `"status": "coming_soon"` to show the card as disabled while you build.

---

### 2. Backend — `backend/apps/<yourapp>/routes.py`

Your API routes. Auth is **automatic** — every route here is already protected by the platform. Users have a valid `@twilio.com` session before they can reach your endpoints.

```python
from flask import Blueprint, jsonify, session

bp = Blueprint("myapp", __name__)

@bp.route("/api/myapp/data")
def get_data():
    email = session.get("user_email")  # always present, auth is guaranteed
    return jsonify({"user": email, "data": []})
```

Rules:
- Blueprint can be named anything
- Prefix your routes with `/api/<yourapp>/` to avoid collisions
- No auth code needed — the platform handles it

---

### 3. Frontend — `frontend/src/routes/(<yourapp>)/<yourapp>/+page.svelte`

Your UI. The user is guaranteed to be logged in.

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

If you want custom chrome (nav bar, theme), add a `+layout.svelte` in `frontend/src/routes/(<yourapp>)/`.

Copy the full template from `backend/apps/_template/` and `frontend/src/routes/(template)/`.

---

## Using Salesforce

A shared Salesforce client is available to all apps. Import it and query away — token refresh is handled automatically.

```python
from salesforce import sf

# Run any SOQL query — returns all records, handles pagination
accounts = sf.query("SELECT Id, Name, AnnualRevenue FROM Account WHERE Type = 'Customer'")

# Raw REST API call
record = sf.get("/services/data/v59.0/sobjects/Account/001XXXXXXXXXXXXXXX")
```

The client retries automatically if the access token has expired. You never deal with OAuth.

Salesforce credentials live in `deploy.env` (gitignored) and are injected as environment variables on the server. You don't need to configure anything — it just works once the platform is deployed.

---

## Running locally

**Backend:**
```bash
cd backend
LOCAL_DEV=1 \
  GOOGLE_CLIENT_ID=<from deploy.env> \
  GOOGLE_CLIENT_SECRET=<from deploy.env> \
  python3 app.py
```

**Frontend:**
```bash
cd frontend
npm install
npm run dev
```

Frontend runs on `http://localhost:5174`, backend on `http://localhost:5001`. The Vite dev server proxies `/api/*` to Flask automatically.

> **After adding or modifying a backend app**, restart Flask — it only discovers blueprints at startup. New routes won't exist until you do.

---

## Deploying

```bash
bash deploy.sh
```

Builds the frontend, tarballs backend + frontend, uploads to S3, spins up a fresh EC2 instance, configures nginx + SSL, and associates the Elastic IP. Takes ~7 minutes end to end.

Requires `deploy.env` — copy `deploy.env.example` and fill in your values.

---

## Platform conventions

| Thing | Convention |
|---|---|
| API routes | Prefix with `/api/<appname>/` |
| Blueprint | Any name, auto-registered |
| Manifest | `backend/apps/<name>/manifest.json` |
| Frontend group | `frontend/src/routes/(<name>)/` |
| Salesforce | `from salesforce import sf` |
| Auth | Free — never implement it yourself |
| `/api/me` enrichment | Expose `enrich_me(email) -> dict` in `routes.py` |
