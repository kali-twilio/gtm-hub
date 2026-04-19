"""Shared Firestore client and suggestions helpers used across all apps."""
from __future__ import annotations
import logging
import os

log = logging.getLogger(__name__)

_FIRESTORE_PROJECT     = os.environ.get("FIRESTORE_PROJECT")
_FIRESTORE_CREDENTIALS = os.environ.get("FIRESTORE_CREDENTIALS_B64")
FIRESTORE_COLLECTION   = "gtm-hub-suggestions"
FIRESTORE_SMS_PENDING  = "sms-pending"
SUGGESTIONS_MAX        = 500

_firestore_client = None


def get_firestore():
    global _firestore_client
    if _firestore_client is not None:
        return _firestore_client
    try:
        from google.cloud import firestore
        from google.oauth2 import service_account
        if _FIRESTORE_CREDENTIALS:
            import base64, json
            info = json.loads(base64.b64decode(_FIRESTORE_CREDENTIALS).decode())
            creds = service_account.Credentials.from_service_account_info(
                info,
                scopes=["https://www.googleapis.com/auth/datastore"],
            )
            _firestore_client = firestore.Client(project=_FIRESTORE_PROJECT, credentials=creds)
        else:
            _firestore_client = firestore.Client(project=_FIRESTORE_PROJECT)
        return _firestore_client
    except Exception as e:
        log.error("Firestore init failed: %s", e)
        return None


def masked_email(email: str) -> str:
    return email.split("@")[0] if email else "anonymous"


def display_author(doc: dict) -> str:
    """Return display name: email prefix, Lookup name, or formatted phone."""
    source = doc.get("source", "web")
    if source in ("sms", "whatsapp"):
        phone = doc.get("phone", "")
        name = doc.get("caller_name")
        if name:
            return name
        if phone.startswith("+1") and len(phone) == 12:
            return f"({phone[2:5]}) {phone[5:8]}-{phone[8:]}"
        return phone or source.upper()
    return masked_email(doc.get("email", ""))
