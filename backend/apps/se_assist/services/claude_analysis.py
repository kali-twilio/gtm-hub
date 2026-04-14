from __future__ import annotations

import os

import anthropic

BEDROCK_MODEL = "global.anthropic.claude-opus-4-6-v1"
DIRECT_MODEL = "claude-opus-4-6"
INPUT_COST_PER_MTOK = 15.0
OUTPUT_COST_PER_MTOK = 75.0


def _get_client():
    """Return a Bedrock client if AWS region is set, otherwise direct Anthropic client."""
    aws_region = os.environ.get("AWS_REGION", "")
    if aws_region:
        return anthropic.AnthropicBedrock(aws_region=aws_region), BEDROCK_MODEL
    api_key = os.environ.get("ANTHROPIC_API_KEY", "")
    return anthropic.Anthropic(api_key=api_key), DIRECT_MODEL


def analyze_gong_email(parsed: dict, subject: str = "") -> dict:
    """Run Claude analysis on parsed Gong email data.

    Returns a dict with all analysis fields plus token/cost metadata.
    """
    client, model = _get_client()

    prompt = _build_prompt(parsed, subject)

    response = client.messages.create(
        model=model,
        max_tokens=4096,
        messages=[{"role": "user", "content": prompt}],
        system=SYSTEM_PROMPT,
    )

    content = response.content[0].text
    analysis = _parse_response(content)

    input_tokens = response.usage.input_tokens
    output_tokens = response.usage.output_tokens
    cost = (input_tokens * INPUT_COST_PER_MTOK + output_tokens * OUTPUT_COST_PER_MTOK) / 1_000_000

    return {
        "raw_response": {"content": content, "model": response.model},
        "model_used": response.model,
        "input_tokens": input_tokens,
        "output_tokens": output_tokens,
        "cost_usd": round(cost, 6),
        **analysis,
    }


SYSTEM_PROMPT = """You are a Twilio SE assistant. You write concise SFDC opportunity updates from Gong call summaries.

Rules:
- Be brief and direct. No filler, no fluff, no restating obvious context.
- No markdown formatting (no **, no *, no #). Plain text only — this goes into Salesforce.
- For bullet lists: write one plain text sentence per line, separated by a blank line between each. No dashes, no bullet characters. Just the text.
- Only mention pricing if it materially affects the deal (e.g. commitment thresholds, competitive pricing pressure). Skip specific per-unit rates.
- Focus on what matters for the next SE picking up this deal: what does the customer want, what did we recommend, what could go wrong, what happens next.

Example bullet format:
Customer wants to migrate SMS traffic from current vendor before September contract end

Twilio recommended sub-account architecture to isolate compliance across use cases

Respond with these exact section headers:

USE_CASE_CATEGORY: (one of: Alerts & Notifications, Identity & Verification, Asset Management, Promotions, Customer Loyalty, Lead Conversion, Contact Center, IVR & Bots, Field Service & Conversations, Other)

PRESALES_STAGE: (one of: 1 - Qualified, 2 - Discovery, 3 - Technical Evaluation, 4 - Technical Win Achieved, 5 - Technical Loss)

SFDC_USE_CASE_DESCRIPTION:
(1-2 sentences. What the customer wants to do with Twilio. Plain text, no formatting.)

SFDC_SOLUTIONS_NOTES:
(Plain text lines separated by blank lines. Products discussed, architecture decisions, competitive context, key deal dynamics, and next steps to move the deal forward. Up to 4 lines max — fewer is fine if the call doesn't warrant more.)

SFDC_TECHNICAL_RISKS:
(Plain text lines separated by blank lines. Migration risks, compliance issues, timeline concerns, blockers. Up to 3 lines max — fewer is fine if there are limited risks.)"""


def analyze_transcript(company_name: str, transcript_text: str, call_date: str | None = None, duration: str | None = None) -> dict:
    """Run Claude analysis on a pasted Gong call transcript."""
    client, model = _get_client()

    parts = ["Analyze this Gong call transcript for a Salesforce opportunity update.\n"]
    parts.append(f"Company: {company_name}")
    if call_date:
        parts.append(f"Call Date: {call_date}")
    if duration:
        parts.append(f"Duration: {duration}")
    parts.append(f"\n--- TRANSCRIPT ---\n{transcript_text}")

    prompt = "\n".join(parts)

    response = client.messages.create(
        model=model,
        max_tokens=4096,
        messages=[{"role": "user", "content": prompt}],
        system=SYSTEM_PROMPT,
    )

    content = response.content[0].text
    analysis = _parse_response(content)

    input_tokens = response.usage.input_tokens
    output_tokens = response.usage.output_tokens
    cost = (input_tokens * INPUT_COST_PER_MTOK + output_tokens * OUTPUT_COST_PER_MTOK) / 1_000_000

    return {
        "raw_response": {"content": content, "model": response.model},
        "model_used": response.model,
        "input_tokens": input_tokens,
        "output_tokens": output_tokens,
        "cost_usd": round(cost, 6),
        **analysis,
    }


def _build_prompt(parsed: dict, subject: str) -> str:
    parts = ["Analyze this Gong call summary for a Salesforce opportunity update.\n"]

    if subject:
        parts.append(f"Call Subject: {subject}")
    parts.append(f"Company: {parsed.get('company_name', 'Unknown')}")
    if parsed.get("call_date"):
        parts.append(f"Call Date: {parsed['call_date']}")
    if parsed.get("duration"):
        parts.append(f"Duration: {parsed['duration']}")

    twilio_participants = parsed.get("twilio_participants", [])
    if twilio_participants:
        names = [f"{p['name']} ({p['title']})" if p.get("title") else p["name"] for p in twilio_participants]
        parts.append(f"Twilio Participants: {', '.join(names)}")

    customer_participants = parsed.get("customer_participants", [])
    if customer_participants:
        names = [f"{p['name']} ({p['title']})" if p.get("title") else p["name"] for p in customer_participants]
        parts.append(f"Customer Participants: {', '.join(names)}")

    for deal in parsed.get("associated_deals", []):
        deal_info = [f"Deal: {deal['name']}"]
        if deal.get("amount"):
            deal_info.append(f"Amount: {deal['amount']}")
        if deal.get("stage"):
            deal_info.append(f"Stage: {deal['stage']}")
        if deal.get("close_date"):
            deal_info.append(f"Close Date: {deal['close_date']}")
        parts.append(" | ".join(deal_info))

    key_points = parsed.get("key_points", [])
    if key_points:
        parts.append("\nKey Points:")
        for i, point in enumerate(key_points, 1):
            parts.append(f"  {i}. {point}")

    next_steps = parsed.get("next_steps", [])
    if next_steps:
        parts.append("\nNext Steps:")
        for i, step in enumerate(next_steps, 1):
            parts.append(f"  {i}. {step}")

    return "\n".join(parts)


def _parse_response(content: str) -> dict:
    """Parse Claude's structured response into individual fields."""
    sections = {
        "USE_CASE_CATEGORY": "use_case_category",
        "PRESALES_STAGE": "presales_stage",
        "SFDC_USE_CASE_DESCRIPTION": "sfdc_use_case_description",
        "SFDC_SOLUTIONS_NOTES": "sfdc_solutions_notes",
        "SFDC_TECHNICAL_RISKS": "sfdc_technical_risks",
    }

    result = {}
    lines = content.split("\n")
    current_key = None
    current_lines: list[str] = []

    for line in lines:
        matched = False
        for header, field in sections.items():
            if line.strip().startswith(header + ":"):
                if current_key:
                    result[current_key] = "\n".join(current_lines).strip()
                current_key = field
                value = line.strip()[len(header) + 1:].strip()
                current_lines = [value] if value else []
                matched = True
                break
        if not matched and current_key is not None:
            current_lines.append(line)

    if current_key:
        result[current_key] = "\n".join(current_lines).strip()

    return result
