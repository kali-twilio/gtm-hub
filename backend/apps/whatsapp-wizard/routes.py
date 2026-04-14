from __future__ import annotations  # required — server runs Python 3.9

from flask import Blueprint, jsonify, session

bp = Blueprint("whatsapp_wizard", __name__)

# External URL where the WhatsApp Wizard Laravel app is hosted.
# Update this once deployed to HostGator.
_WIZARD_URL = "https://your-domain.com"


@bp.route("/api/whatsapp-wizard/info")
def info():
    """Return wizard URL and onboarding steps for the launcher page."""
    email = session.get("user_email")
    return jsonify({
        "user":       email,
        "wizard_url": _WIZARD_URL,
        "steps": [
            {"step": 1, "label": "Connect Twilio Account",        "description": "Validate your Account SID and Auth Token."},
            {"step": 2, "label": "Meta Embedded Signup",          "description": "Link your WhatsApp Business Account (WABA) via Facebook OAuth."},
            {"step": 3, "label": "Register Phone Number",         "description": "Activate a Twilio number for WhatsApp messaging."},
            {"step": 4, "label": "Business Profile & Templates",  "description": "Set your display name, logo, and submit message templates for Meta approval."},
        ],
    })
