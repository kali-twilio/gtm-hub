"""
GTM Hub — Shared Gong API client
----------------------------------
All apps import this module to query Gong. Basic-auth credentials are injected
from environment variables — apps never handle auth directly.

Usage:
    from gong import gong
    calls   = gong.get("/v2/calls", params={"fromDateTime": "2024-01-01T00:00:00Z"})
    records = gong.get_all("/v2/calls", cursor_key="calls", params={...})
"""

from __future__ import annotations
import os
import logging

import requests
from requests.auth import HTTPBasicAuth

log = logging.getLogger(__name__)

_BASE_URL = "https://us-50596.api.gong.io"


class GongClient:
    def __init__(self):
        self.base_url   = os.environ.get("GONG_BASE_URL", _BASE_URL).rstrip("/")
        self.access_key = os.environ.get("GONG_ACCESS_KEY_ID")
        self.secret_key = os.environ.get("GONG_SECRET_KEY")

    @property
    def configured(self) -> bool:
        return bool(self.access_key and self.secret_key)

    def _auth(self) -> HTTPBasicAuth:
        return HTTPBasicAuth(self.access_key, self.secret_key)

    def get(self, path: str, params: dict | None = None, timeout: int = 30) -> dict:
        """Authenticated GET against the Gong REST API."""
        if not self.configured:
            raise RuntimeError("Gong is not configured — check GONG_ACCESS_KEY_ID and GONG_SECRET_KEY.")
        path = path if path.startswith("/") else f"/{path}"
        resp = requests.get(
            f"{self.base_url}{path}",
            auth=self._auth(),
            params=params,
            headers={"Accept": "application/json"},
            timeout=timeout,
        )
        resp.raise_for_status()
        return resp.json()

    def post(self, path: str, payload: dict | None = None, timeout: int = 30) -> dict:
        """Authenticated POST against the Gong REST API."""
        if not self.configured:
            raise RuntimeError("Gong is not configured — check GONG_ACCESS_KEY_ID and GONG_SECRET_KEY.")
        path = path if path.startswith("/") else f"/{path}"
        resp = requests.post(
            f"{self.base_url}{path}",
            auth=self._auth(),
            json=payload or {},
            headers={"Accept": "application/json", "Content-Type": "application/json"},
            timeout=timeout,
        )
        resp.raise_for_status()
        return resp.json()

    def get_all(self, path: str, cursor_key: str, params: dict | None = None, timeout: int = 30) -> list:
        """
        Paginate through a Gong list endpoint and return all records.

        Gong uses a `cursor` field in the response `requestEntailments` block.
        Pass cursor_key to identify which top-level array to accumulate
        (e.g. "calls", "users", "scorecards").
        """
        if not self.configured:
            raise RuntimeError("Gong is not configured — check GONG_ACCESS_KEY_ID and GONG_SECRET_KEY.")
        path = path if path.startswith("/") else f"/{path}"
        records: list = []
        cursor: str | None = None

        while True:
            p = dict(params or {})
            if cursor:
                p["cursor"] = cursor
            resp = requests.get(
                f"{self.base_url}{path}",
                auth=self._auth(),
                params=p,
                headers={"Accept": "application/json"},
                timeout=timeout,
            )
            resp.raise_for_status()
            data = resp.json()
            records.extend(data.get(cursor_key, []))
            cursor = (data.get("records") or {}).get("cursor")
            if not cursor:
                break

        return records


# Shared singleton — import this in any app
gong = GongClient()
