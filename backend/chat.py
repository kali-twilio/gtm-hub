"""Shared OpenAI agentic chat loop used by all app chat endpoints."""
from __future__ import annotations
import json
import logging
import os
import re as _re

import requests as http

from salesforce import sf

log = logging.getLogger(__name__)

_OPENAI_API_KEY = os.environ.get("OPENAI_API_KEY", "")
_OPENAI_MODEL   = os.environ.get("OPENAI_MODEL", "gpt-4o")
_SOQL_SELECT_RE = _re.compile(r"^\s*SELECT\b", _re.IGNORECASE)

SOQL_SCHEMA = """
Salesforce Opportunity fields available:
  Id, Name, CloseDate, StageName, ForecastCategoryName, Amount, Type
  Comms_Segment_Combined_iACV__c  (iACV — primary revenue metric)
  eARR_post_launch_No_Decimal__c, eARR_post_Launch__c  (eARR)
  Incremental_ACV__c, Current_eARR__c
  FY_16_Owner_Team__c
  Presales_Stage__c               ('4 - Technical Win Achieved' = TW)
  Technical_Lead__r.Name, Technical_Lead__r.Email, Technical_Lead__r.UserRole.Name
  Owner.Name, Owner.UserRole.Name
  Account.Name, Account.Owner.Name, Account.Website, Account.SE_Notes__c
  SE_Notes__c, SE_Notes_History__c, Sales_Engineer_Notes__c
  NextStep, LastActivityDate, RecordType.Name
  Renegotiated_Deal_SE_Involved__c
Standard date literals: TODAY, THIS_QUARTER, LAST_QUARTER, THIS_YEAR, LAST_N_DAYS:n
Limit results to 50 rows unless more are needed.
"""

SOQL_TOOL = [
    {
        "type": "function",
        "function": {
            "name": "run_soql",
            "description": (
                "Execute a SOQL SELECT query against the Twilio Salesforce org. "
                "Use this when pre-loaded context isn't sufficient — e.g. specific accounts, "
                "deal notes, pipeline queries, or cross-team comparisons. "
                "Only SELECT queries are permitted."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "soql": {"type": "string", "description": "A valid SOQL SELECT statement."}
                },
                "required": ["soql"],
            },
        },
    }
]


def execute_soql_safe(soql: str) -> str:
    """Run a SOQL query. Rejects anything that isn't a SELECT — no writes ever."""
    if not _SOQL_SELECT_RE.match(soql.strip()):
        return "Error: only SELECT queries are permitted. Write operations are not allowed."
    if not sf.configured:
        return "Error: Salesforce is not configured on this server."
    try:
        rows = sf.query(soql, timeout=30)
    except Exception as e:
        return f"Query error: {e}"
    if not rows:
        return "No records returned."
    lines = [str({k: v for k, v in row.items() if k != "attributes"}) for row in rows[:100]]
    return "\n".join(lines)


def run_chat(system_prompt: str, context: str, message: str) -> dict:
    """
    Agentic OpenAI loop with run_soql tool. Returns {answer} or {error}.
    Up to 3 tool-call rounds before forcing a final summary.
    """
    if not _OPENAI_API_KEY:
        return {"error": "AI chatbot is not configured (missing OPENAI_API_KEY)."}

    messages = [
        {"role": "system", "content": system_prompt},
        {"role": "user", "content": (
            f"Pre-loaded context:\n\n{context}\n\nQuestion: {message}"
            if context else f"Question: {message}"
        )},
    ]

    try:
        for _ in range(3):
            resp = http.post(
                "https://api.openai.com/v1/chat/completions",
                headers={"Authorization": f"Bearer {_OPENAI_API_KEY}", "Content-Type": "application/json"},
                json={
                    "model":       _OPENAI_MODEL,
                    "max_tokens":  1024,
                    "messages":    messages,
                    "tools":       SOQL_TOOL,
                    "tool_choice": "auto",
                },
                timeout=60,
            )
            resp.raise_for_status()
            choice = resp.json()["choices"][0]
            msg = choice["message"]
            messages.append(msg)

            if choice["finish_reason"] != "tool_calls":
                return {"answer": msg.get("content", "No response generated.")}

            for tc in msg.get("tool_calls", []):
                if tc["function"]["name"] == "run_soql":
                    try:
                        args   = json.loads(tc["function"]["arguments"])
                        result = execute_soql_safe(args.get("soql", ""))
                    except Exception as e:
                        result = f"Tool error: {e}"
                    messages.append({
                        "role":         "tool",
                        "tool_call_id": tc["id"],
                        "content":      result,
                    })

        messages.append({"role": "user", "content": "Please summarise what you found."})
        resp = http.post(
            "https://api.openai.com/v1/chat/completions",
            headers={"Authorization": f"Bearer {_OPENAI_API_KEY}", "Content-Type": "application/json"},
            json={"model": _OPENAI_MODEL, "max_tokens": 1024, "messages": messages},
            timeout=60,
        )
        resp.raise_for_status()
        return {"answer": resp.json()["choices"][0]["message"].get("content", "No response generated.")}

    except Exception as e:
        log.error("Chat error: %s", e, exc_info=True)
        if hasattr(e, "response") and e.response is not None:
            if e.response.status_code == 429:
                return {"error": "Rate limited by AI provider. Please wait a moment and try again."}
        return {"error": f"AI request failed: {type(e).__name__}. Please try again."}
