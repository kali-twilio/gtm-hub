"""
routes.py — Customer Profiler Flask Blueprint

POST /api/customer-profiler/analyze  — SSE stream: research + AI report
POST /api/customer-profiler/send     — Send report summary via SMS or WhatsApp
"""

from __future__ import annotations

import json
import os
import re
import textwrap
from flask import Blueprint, request, Response, stream_with_context, jsonify
from openai import OpenAI, AuthenticationError, RateLimitError, APIError
from twilio.rest import Client as TwilioClient
from twilio.base.exceptions import TwilioRestException

from .research import research_company

bp = Blueprint("customer_profiler", __name__)

_openai: OpenAI | None = None
_twilio: TwilioClient | None = None

def _get_openai() -> OpenAI:
    global _openai
    if _openai is None:
        _openai = OpenAI(api_key=os.environ.get("OPENAI_API_KEY"))
    return _openai

def _get_twilio() -> TwilioClient:
    global _twilio
    if _twilio is None:
        _twilio = TwilioClient(
            os.environ.get("TWILIO_ACCOUNT_SID"),
            os.environ.get("TWILIO_AUTH_TOKEN"),
        )
    return _twilio


# ── System prompt ─────────────────────────────────────────────────────────────

SYSTEM_PROMPT = textwrap.dedent("""\
    You are a senior Twilio Sales Intelligence Analyst. Your role is to help
    Twilio Digital Sales Representatives (DSRs) research prospects and build
    comprehensive, actionable customer profiles that drive revenue.

    ## Your Expertise
    You have deep knowledge of Twilio's full product portfolio:

    **Communications**
    - Programmable Voice (outbound/inbound calls, IVR, call recording, SIP Trunking)
    - Programmable Messaging (SMS, MMS, WhatsApp Business API, RCS)
    - WhatsApp Business API (customer notifications, support, marketing)
    - SendGrid Email API (transactional + marketing email)
    - Conversations API (unified multi-channel messaging)
    - Notify (push notifications)

    **Customer Experience**
    - Twilio Flex (cloud contact center platform — replaces legacy CCaaS)
    - Twilio Engage (omnichannel customer engagement + CDP)
    - Segment (Customer Data Platform — unify customer data)

    **Security & Trust**
    - Verify API (OTP/2FA, phone verification, TOTP, Silent Network Auth)
    - Lookup API (phone number intelligence, carrier, line type, spam risk)
    - Voice Intelligence (call transcription, sentiment, summarization)

    **Marketplace Opportunities**
    - Migration from on-premise PBX/contact center to cloud
    - WhatsApp channel activation for existing SMS/voice customers
    - Adding Verify for customer authentication flows
    - Replacing legacy email providers with SendGrid
    - Contact center modernization via Flex

    ## Your Output Philosophy
    - Be specific and actionable — vague insights waste a DSR's time
    - Prioritize opportunities by likelihood to close and potential deal size
    - Frame everything around the customer's business problems, not Twilio features
    - Identify the right buyer personas (VP Engineering, CTO, VP CX, CMO, etc.)
    - Surface quick wins and longer-term strategic plays separately
    - Note gaps in information and what the DSR should ask to fill them

    ## Formatting
    Use clear Markdown with emoji section headers. Be thorough but scannable.
    Use bullet points and tables where appropriate.
    Bold key insights and named products.
""")


# ── Prompt builder ────────────────────────────────────────────────────────────

def _build_user_prompt(customer_data: dict, research: dict) -> str:
    lines: list[str] = ["# Customer Profile Research Request\n"]

    lines.append("## Information Provided by DSR\n")
    fields = [
        ("Company Name",             customer_data.get("company_name")),
        ("Website",                  customer_data.get("website_url")),
        ("Industry / Vertical",      customer_data.get("industry")),
        ("HQ Location",              customer_data.get("location")),
        ("Company Size",             customer_data.get("company_size")),
        ("Existing Twilio Products", customer_data.get("existing_twilio")),
        ("Known Phone Numbers",      customer_data.get("phone_numbers")),
        ("LinkedIn URL",             customer_data.get("linkedin_url")),
        ("Social Media",             customer_data.get("social_media")),
        ("DSR Notes",                customer_data.get("notes")),
    ]
    for label, value in fields:
        if value and str(value).strip():
            lines.append(f"- **{label}**: {value}")
    lines.append("")

    web = research.get("website_data", {})
    if web and not web.get("error"):
        lines.append("## Website Research Findings\n")
        if web.get("title"):
            lines.append(f"- **Page Title**: {web['title']}")
        if web.get("description"):
            lines.append(f"- **Meta Description**: {web['description']}")
        if web.get("phone_numbers"):
            lines.append(f"- **Phone Numbers Found**: {', '.join(web['phone_numbers'][:6])}")
        if web.get("toll_free_numbers"):
            lines.append(f"- **Toll-Free Numbers**: {', '.join(web['toll_free_numbers'])}")
        if web.get("emails"):
            lines.append(f"- **Emails Found**: {', '.join(web['emails'][:4])}")
        if web.get("social_links"):
            for platform, url in web["social_links"].items():
                lines.append(f"- **{platform.title()}**: {url}")
        if web.get("chat_tools_detected"):
            lines.append(f"- **Chat/Messaging Tools Detected**: {', '.join(web['chat_tools_detected'])}")
        if web.get("contact_center_signals"):
            lines.append(f"- **Contact Center Signals**: {', '.join(web['contact_center_signals'])}")
        if web.get("has_whatsapp"):
            lines.append("- **WhatsApp Presence**: Detected on website")
        if web.get("raw_text_snippet"):
            lines.append(f"\n**Website Content Snippet**:\n```\n{web['raw_text_snippet'][:1500]}\n```")
        lines.append("")

    linkedin = research.get("linkedin_data", {})
    if linkedin.get("url") or linkedin.get("snippet"):
        lines.append("## LinkedIn Data\n")
        if linkedin.get("url"):
            lines.append(f"- **LinkedIn URL**: {linkedin['url']}")
        if linkedin.get("snippet"):
            lines.append(f"- **LinkedIn Snippet**: {linkedin['snippet']}")
        lines.append("")

    search = research.get("search_results", [])
    if search:
        lines.append("## Web Search Results\n")
        for r in search[:8]:
            if r.get("title"):
                lines.append(f"**{r['title']}**")
                if r.get("url"):
                    lines.append(f"URL: {r['url']}")
                if r.get("snippet"):
                    lines.append(f"{r['snippet']}")
                lines.append("")

    lines.append("---\n")
    lines.append(
        "Please generate a comprehensive DSR intelligence report for this customer. "
        "Include all sections: Executive Summary, Company Overview, Communication Channels "
        "Analysis, Twilio Product Opportunities (prioritized), Sales Strategy & Approach, "
        "Key Discovery Questions, and Objection Handling. "
        "Be specific and actionable. Reference actual signals found in the research."
    )

    return "\n".join(lines)


# ── SSE helper ────────────────────────────────────────────────────────────────

def _sse(data: dict) -> str:
    return f"data: {json.dumps(data)}\n\n"


# ── Route ─────────────────────────────────────────────────────────────────────

@bp.route("/api/customer-profiler/analyze", methods=["POST"])
def analyze():
    data = request.get_json(force=True, silent=True) or {}
    if not (data.get("company_name") or "").strip():
        return {"error": "company_name is required"}, 400

    def generate():
        # ── Phase 1: web research ──────────────────────────────────────────
        yield _sse({"type": "progress", "message": "🔍 Starting research..."})

        try:
            research = research_company(data)
        except Exception as exc:
            research = {"progress": [], "website_data": {}, "search_results": [], "linkedin_data": {}}
            yield _sse({"type": "progress", "message": f"⚠️ Research error: {exc} — proceeding with provided data only"})

        for msg in research.get("progress", []):
            yield _sse({"type": "progress", "message": msg})

        # ── Phase 2: OpenAI analysis ───────────────────────────────────────
        yield _sse({"type": "progress", "message": "🤖 Running AI analysis (this takes 20–40 seconds)..."})

        user_prompt = _build_user_prompt(data, research)

        try:
            client = _get_openai()
            stream = client.chat.completions.create(
                model="gpt-4o",
                messages=[
                    {"role": "system", "content": SYSTEM_PROMPT},
                    {"role": "user",   "content": user_prompt},
                ],
                stream=True,
            )
            for chunk in stream:
                text = chunk.choices[0].delta.content or ""
                if text:
                    yield _sse({"type": "delta", "text": text})

            yield _sse({"type": "done"})

        except AuthenticationError:
            yield _sse({"type": "error", "message": "Invalid OPENAI_API_KEY — check your .env file."})
        except RateLimitError:
            yield _sse({"type": "error", "message": "OpenAI rate limit hit. Wait a moment and try again."})
        except APIError as exc:
            yield _sse({"type": "error", "message": f"OpenAI API error: {exc}"})
        except Exception as exc:
            yield _sse({"type": "error", "message": f"Unexpected error: {exc}"})

    return Response(
        stream_with_context(generate()),
        content_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "X-Accel-Buffering": "no",
            "Connection": "keep-alive",
        },
    )


# ── /send — deliver report summary via SMS or WhatsApp ────────────────────────

def _make_summary(company_name: str, report_text: str, channel: str) -> str:
    """Use OpenAI to distill the full report into a channel-appropriate summary."""
    limit = "300 characters" if channel == "sms" else "800 characters"
    formatting = (
        "Plain text only, no markdown." if channel == "sms"
        else "You may use light WhatsApp formatting: *bold* for headers, bullet points with -."
    )

    resp = _get_openai().chat.completions.create(
        model="gpt-4o",
        messages=[
            {
                "role": "system",
                "content": (
                    f"You summarize sales intelligence reports into brief {channel.upper()} messages. "
                    f"Max {limit}. {formatting} "
                    "Include: company name, top 2 Twilio opportunities, and one recommended next action. "
                    "End with '— Twilio DSR Intel'."
                ),
            },
            {
                "role": "user",
                "content": f"Summarize this report for {company_name}:\n\n{report_text[:4000]}",
            },
        ],
        max_tokens=300,
    )
    return resp.choices[0].message.content.strip()


def _normalize_phone(number: str) -> str:
    """Strip spaces/dashes and ensure E.164 format."""
    cleaned = re.sub(r"[\s\-().]+", "", number)
    if not cleaned.startswith("+"):
        cleaned = "+" + cleaned
    return cleaned


@bp.route("/api/customer-profiler/send", methods=["POST"])
def send_report():
    data         = request.get_json(force=True, silent=True) or {}
    to_number    = (data.get("to") or "").strip()
    channel      = (data.get("channel") or "sms").lower()   # "sms" | "whatsapp"
    report_text  = (data.get("report_text") or "").strip()
    company_name = (data.get("company_name") or "Unknown Company").strip()

    if not to_number:
        return jsonify({"error": "to (phone number) is required"}), 400
    if not report_text:
        return jsonify({"error": "report_text is required"}), 400
    if channel not in ("sms", "whatsapp"):
        return jsonify({"error": "channel must be 'sms' or 'whatsapp'"}), 400

    try:
        summary = _make_summary(company_name, report_text, channel)
    except Exception as exc:
        return jsonify({"error": f"Failed to summarize report: {exc}"}), 500

    try:
        twilio  = _get_twilio()
        to_e164 = _normalize_phone(to_number)

        if channel == "whatsapp":
            from_addr = f"whatsapp:{os.environ.get('TWILIO_WHATSAPP_FROM', '+14155238886')}"
            to_addr   = f"whatsapp:{to_e164}"
        else:
            from_addr = os.environ.get("TWILIO_SMS_FROM", "")
            to_addr   = to_e164

        message = twilio.messages.create(
            body=summary,
            from_=from_addr,
            to=to_addr,
        )
        return jsonify({"ok": True, "sid": message.sid, "summary": summary})

    except TwilioRestException as exc:
        return jsonify({"error": str(exc)}), 500
    except Exception as exc:
        return jsonify({"error": f"Unexpected error: {exc}"}), 500
