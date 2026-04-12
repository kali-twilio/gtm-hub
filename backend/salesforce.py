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

import os
import logging
from threading import Lock

import requests

log = logging.getLogger(__name__)

_SALESFORCE_API_VERSION = "v59.0"


class SalesforceClient:
    def __init__(self):
        self.instance_url   = os.environ.get("SALESFORCE_INSTANCE_URL", "").rstrip("/")
        self.client_id      = os.environ.get("SALESFORCE_CLIENT_ID")
        self.client_secret  = os.environ.get("SALESFORCE_CLIENT_SECRET")
        self.refresh_token  = os.environ.get("SALESFORCE_REFRESH_TOKEN")
        self._access_token  = os.environ.get("SALESFORCE_ACCESS_TOKEN")
        self._lock          = Lock()

    @property
    def configured(self) -> bool:
        return bool(self.instance_url and self.client_id and
                    self.client_secret and self.refresh_token)

    def _refresh(self):
        """Exchange the refresh token for a new access token."""
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

    def get(self, path: str, **kwargs) -> dict:
        """Authenticated GET against the Salesforce REST API. Retries once on 401."""
        if not self.configured:
            raise RuntimeError("Salesforce is not configured — check environment variables.")
        with self._lock:
            for attempt in range(2):
                resp = requests.get(
                    f"{self.instance_url}{path}",
                    headers={"Authorization": f"Bearer {self._access_token}"},
                    timeout=15,
                    **kwargs,
                )
                if resp.status_code == 401 and attempt == 0:
                    self._refresh()
                    continue
                resp.raise_for_status()
                return resp.json()

    def query(self, soql: str) -> list:
        """Run a SOQL query and return all records (handles pagination)."""
        path = f"/services/data/{_SALESFORCE_API_VERSION}/query"
        data = self.get(path, params={"q": soql})
        records = data.get("records", [])
        # Follow nextRecordsUrl if paginated
        while not data.get("done", True):
            data = self.get(data["nextRecordsUrl"])
            records.extend(data.get("records", []))
        return records


# Shared singleton — import this in any app
sf = SalesforceClient()
