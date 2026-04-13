# GTM Hub

Internal platform for Twilio Sales tools. Sign in with your `@twilio.com` Google account.

**Live at:** https://gtm-hub.duckdns.org

---

## What's here

```
backend/
├── app.py                  Platform: Google OAuth, /api/me, /api/apps
├── salesforce.py           Shared Salesforce client
└── apps/
    ├── _template/          Copy this to start a new app
    ├── scorecard/          SE Scorecard (CSV upload)
    └── se_scorecard_v2/    SE Scorecard V2 (live Salesforce)

frontend/
└── src/
    ├── lib/                Shared stores, API helpers, color tokens
    └── routes/
        ├── (launcher)/     Login page + app grid
        ├── (scorecard)/    SE Scorecard pages
        └── (se-scorecard-v2)/  SE Scorecard V2 pages

deploy.sh                   One-command deploy to EC2
deploy.env                  Secrets + config (gitignored)
```

---

## Security & Auth

### Authentication

- **Google OAuth 2.0** — users sign in with Google. The platform validates the returned identity token against Google's userinfo endpoint.
- **Domain restriction** — only `@twilio.com` accounts are accepted. Any other domain gets redirected with an error before a session is created.
- **OAuth state parameter** — a random state token is generated per login attempt and validated on callback. Mismatches are rejected, preventing CSRF attacks on the OAuth flow.
- **PKCE support** — code verifier is stored in session and passed on token exchange when supported by the flow.
- **Session-only auth** — identity is stored in a server-side signed session cookie. No JWTs, no client-side tokens.

### Session security

| Setting | Value | Why |
|---|---|---|
| `SESSION_COOKIE_SECURE` | `True` in production | Cookie only sent over HTTPS |
| `SESSION_COOKIE_HTTPONLY` | `True` | JavaScript cannot read the cookie |
| `SESSION_COOKIE_SAMESITE` | `Lax` | Blocks cross-site request forgery |
| `SECRET_KEY` | Required env var | Flask signs the session; crashes at startup if not set |

In local dev (`LOCAL_DEV=1`), `SECURE` is relaxed and `OAUTHLIB_INSECURE_TRANSPORT` is set so HTTP works. This flag is never present in production.

### Platform-level auth gate

Every `/api/*` route is protected automatically in `app.py`:

```python
@app.before_request
def enforce_auth():
    if request.path.startswith("/api/") and not session.get("user_email"):
        return jsonify({"error": "Unauthorized"}), 401
```

App builders never implement auth themselves — if a request reaches a blueprint route, the user is already authenticated.

### Response security headers (every response)

| Header | Value |
|---|---|
| `Cache-Control` | `no-store` — API responses never cached by browsers or proxies |
| `X-Content-Type-Options` | `nosniff` — browsers don't sniff MIME types |
| `X-Frame-Options` | `SAMEORIGIN` — prevents clickjacking in iframes |
| `Referrer-Policy` | `strict-origin-when-cross-origin` |
| `Content-Security-Policy` | `default-src 'self'` — scripts, styles, fonts, images, and connections scoped to origin only |
| `frame-ancestors` | `none` — blocks this app from being embedded anywhere |
| `Strict-Transport-Security` | `max-age=31536000; includeSubDomains` (production only) — HSTS, forces HTTPS for 1 year |

### Infrastructure security

- **HTTPS only** — Let's Encrypt SSL cert provisioned automatically on deploy. Nginx redirects all HTTP to HTTPS.
- **IMDSv2 required** — EC2 instance launched with `HttpTokens=required`. Blocks SSRF attacks that try to read instance metadata.
- **Least privilege processes** — gunicorn runs as `ec2-user`, nginx as `nginx`. Neither runs as root.
- **nginx server tokens off** — version number not exposed in response headers or error pages.
- **Request size limit** — `client_max_body_size 10M` in nginx, `MAX_CONTENT_LENGTH = 10MB` in Flask. Prevents oversized upload attacks.
- **Nginx security headers** — `Permissions-Policy: geolocation=(), microphone=(), camera=()` added at the proxy layer in addition to app-level headers.
- **SSL auto-renewal** — certbot renew runs via cron at midnight and noon daily. Certs expire every 90 days; renewal is automatic.
- **No SSH open** — the EC2 security group does not expose port 22. Access is via re-deploy only.

### Simulate endpoint (local dev only)

`/simulate?email=user@twilio.com` sets a session as that user without going through OAuth. Returns 404 in production (`LOCAL_DEV` is never set on the server).

---

## Adding a new app

Three files. No platform files change.

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

- `"status": "coming_soon"` — shows the card as disabled in the launcher
- Prefix the directory with `_` to hide it from the launcher entirely

### 2. `backend/apps/<yourapp>/routes.py`

```python
from __future__ import annotations  # required — server runs Python 3.9
from flask import Blueprint, jsonify, session

bp = Blueprint("myapp", __name__)

@bp.route("/api/myapp/data")
def get_data():
    email = session.get("user_email")  # always present — auth is guaranteed
    return jsonify({"user": email, "data": []})
```

- Prefix all routes with `/api/<yourapp>/` to avoid collisions
- Optionally expose `enrich_me(email: str) -> dict` to add fields to `/api/me`

### 3. `frontend/src/routes/(<yourapp>)/<yourapp>/+page.svelte`

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

The route group `(<yourapp>)` doesn't affect the URL. Add a `+layout.svelte` in the group folder for custom nav/chrome.

Copy the full starter from `backend/apps/_template/` and `frontend/src/routes/(template)/`.

---

## Using Salesforce

```python
from salesforce import sf

# SOQL query — returns all records, handles pagination automatically
opps = sf.query("SELECT Id, Name FROM Opportunity WHERE StageName = 'Closed Won'")

# Raw REST call
record = sf.get("/services/data/v59.0/sobjects/Account/001XXXXXXXXXXXXXXX")
```

Token refresh is automatic. Credentials come from `deploy.env` and are injected as environment variables — nothing to configure.

---

## Running locally

```bash
# Backend — source deploy.env but keep FRONTEND_URL pointed at local Vite
cd backend
set -a && source ../deploy.env && set +a
LOCAL_DEV=1 FRONTEND_URL="http://localhost:5173" python3 app.py
```

```bash
# Frontend
cd frontend && npm install && npm run dev
```

Frontend: `http://localhost:5173` · Backend: `http://localhost:5001`. Vite proxies `/api/*` to Flask.

> Restart Flask after any backend change — blueprints are discovered at startup only.

---

## Deploying

```bash
bash deploy.sh
```

Builds the frontend, uploads backend + frontend to S3, terminates the existing instance, launches a fresh AL2023 EC2 t3.micro, bootstraps nginx + gunicorn + SSL, and associates the Elastic IP. ~7 minutes end to end.

Requires `deploy.env` with all secrets populated.

---

## Platform conventions

| Thing | Convention |
|---|---|
| API routes | Prefix with `/api/<appname>/` |
| Blueprint | Any name — auto-registered from `apps/<name>/routes.py` |
| Hidden apps | Prefix directory with `_` |
| Auth | Never implement it — the platform handles it |
| `/api/me` enrichment | Expose `enrich_me(email) -> dict` in `routes.py` |
| Salesforce | `from salesforce import sf` |
| Python compat | Always add `from __future__ import annotations` (server is Python 3.9) |
