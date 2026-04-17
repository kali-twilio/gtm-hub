"""
GTM Hub — Shared Salesforce client
-----------------------------------
All apps import this module to query Salesforce. Token refresh is handled
automatically — apps never deal with auth directly.

Usage:
    from salesforce import sf
    results = sf.query("SELECT Id, Name FROM Account LIMIT 10")
    record   = sf.get("/services/data/v59.0/sobjects/Account/001...")
"""

from __future__ import annotations
import os
import logging
from threading import Lock

import requests

log = logging.getLogger(__name__)

_SALESFORCE_API_VERSION = "v59.0"
_MAX_BATCH_SIZE = 2000   # Salesforce hard limit


class SalesforceClient:
    def __init__(self):
        self.instance_url   = os.environ.get("SALESFORCE_INSTANCE_URL", "").rstrip("/")
        self.client_id      = os.environ.get("SALESFORCE_CLIENT_ID")
        self.client_secret  = os.environ.get("SALESFORCE_CLIENT_SECRET")
        self.refresh_token  = os.environ.get("SALESFORCE_REFRESH_TOKEN")
        self._access_token  = os.environ.get("SALESFORCE_ACCESS_TOKEN")
        # Lock guards only the token refresh, not the full HTTP call,
        # so concurrent reads are never serialized against each other.
        self._refresh_lock  = Lock()

    @property
    def configured(self) -> bool:
        return bool(self.instance_url and self.client_id and
                    self.client_secret and self.refresh_token)

    def _refresh(self, stale_token: str | None = None):
        """Exchange the refresh token for a new access token.

        Pass stale_token (the token that got a 401) so that concurrent threads
        skip the refresh if another thread already replaced it.
        """
        with self._refresh_lock:
            if stale_token is not None and self._access_token != stale_token:
                return  # another thread already refreshed
            resp = requests.post(
                f"{self.instance_url}/services/oauth2/token",
                data={
                    "grant_type":    "refresh_token",
                    "client_id":     self.client_id,
                    "client_secret": self.client_secret,
                    "refresh_token": self.refresh_token,
                },
                timeout=10,
            )
            resp.raise_for_status()
            self._access_token = resp.json()["access_token"]
            log.info("Salesforce access token refreshed")

    def _headers(self) -> dict:
        return {
            "Authorization":   f"Bearer {self._access_token}",
            "Accept-Encoding": "gzip",   # compresses large payloads significantly
        }

    def get(self, path: str, **kwargs) -> dict:
        """Authenticated GET against the Salesforce REST API. Retries once on 401."""
        if not self.configured:
            raise RuntimeError("Salesforce is not configured — check environment variables.")
        for attempt in range(2):
            stale = self._access_token
            resp = requests.get(
                f"{self.instance_url}{path}",
                headers=self._headers(),
                timeout=30,
                **kwargs,
            )
            if resp.status_code == 401 and attempt == 0:
                self._refresh(stale)
                continue
            resp.raise_for_status()
            return resp.json()

    def query(self, soql: str, batch_size: int = _MAX_BATCH_SIZE, timeout: int = 30) -> list:
        """
        Run a SOQL query and return all records (handles pagination).

        batch_size defaults to 2000 (the Salesforce maximum) so most queries
        complete in a single round trip.  For very large result sets the pages
        are fetched sequentially — the Salesforce API does not support parallel
        page fetches on the same cursor.
        """
        opts = f"batchSize={batch_size}"
        path = f"/services/data/{_SALESFORCE_API_VERSION}/query"
        # Sforce-Query-Options must be merged into the headers dict, not passed
        # as a separate kwarg, so we build the full header dict here.
        hdrs = {**self._headers(), "Sforce-Query-Options": opts}

        if not self.configured:
            raise RuntimeError("Salesforce is not configured — check environment variables.")

        for attempt in range(2):
            stale = self._access_token
            resp = requests.get(
                f"{self.instance_url}{path}",
                headers=hdrs,
                params={"q": soql},
                timeout=timeout,
            )
            if resp.status_code == 401 and attempt == 0:
                self._refresh(stale)
                hdrs = {**self._headers(), "Sforce-Query-Options": opts}
                continue
            resp.raise_for_status()
            break

        data    = resp.json()
        records = data.get("records", [])

        while not data.get("done", True):
            resp    = requests.get(
                f"{self.instance_url}{data['nextRecordsUrl']}",
                headers=hdrs,
                timeout=timeout,
            )
            resp.raise_for_status()
            data    = resp.json()
            records.extend(data.get("records", []))

        return records

    def get_user_by_email(self, email: str) -> dict | None:
        """
        Return the Salesforce User record for a given email, or None if not found / SF unavailable.
        Used at login to determine role-based access level.
        """
        if not self.configured:
            return None
        try:
            safe = email.replace("'", "\\'")
            results = self.query(
                f"SELECT Id, Name, Email, Title, Department, Division, Manager.Name, UserRole.Name "
                f"FROM User "
                f"WHERE Email = '{safe}' AND IsActive = true "
                f"LIMIT 1"
            )
            return results[0] if results else None
        except Exception:
            log.warning("SF user lookup failed for %s", email, exc_info=True)
            return None


# Shared singleton — import this in any app
sf = SalesforceClient()
