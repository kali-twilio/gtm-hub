from __future__ import annotations

import email as email_lib
import re
from datetime import datetime
from email import policy

from bs4 import BeautifulSoup


def parse_eml(raw_bytes: bytes) -> dict:
    """Parse a raw .eml file (bytes) and return headers + parsed body data."""
    msg = email_lib.message_from_bytes(raw_bytes, policy=policy.default)
    subject = msg.get("Subject", "")
    date_str = msg.get("Date", "")
    message_id = msg.get("Message-ID", "")

    html_body = _extract_html_body(msg)
    parsed = parse_gong_html(html_body, subject)

    return {
        "message_id": message_id,
        "subject": subject,
        "date": date_str,
        "parsed_data": parsed,
    }


def _extract_html_body(msg) -> str:
    """Walk a MIME message and return the HTML part."""
    if msg.get_content_type() == "text/html":
        return msg.get_content()
    for part in msg.walk():
        if part.get_content_type() == "text/html":
            return part.get_content()
    return ""


def parse_gong_html(html: str, subject: str = "") -> dict:
    """Parse a Gong notification HTML email body into structured data."""
    soup = BeautifulSoup(html, "lxml")

    company_name = _extract_company_name(soup, subject)
    call_date = _extract_call_date(soup)
    duration = _extract_duration(soup)
    key_points = _extract_numbered_section(soup, "Key points")
    next_steps = _extract_numbered_section(soup, "Next steps")
    twilio_participants, customer_participants = _extract_participants(soup)
    deals = _extract_deals(soup)

    return {
        "company_name": company_name,
        "call_date": call_date,
        "duration": duration,
        "key_points": key_points,
        "next_steps": next_steps,
        "twilio_participants": [{"name": p["name"], "title": p.get("title")} for p in twilio_participants],
        "customer_participants": [{"name": p["name"], "title": p.get("title")} for p in customer_participants],
        "associated_deals": [
            {"name": d["name"], "amount": d.get("amount"), "stage": d.get("stage"), "close_date": d.get("close_date")}
            for d in deals
        ],
    }


def _extract_company_name(soup: BeautifulSoup, subject: str) -> str:
    title_span = soup.find("span", class_="entity-title")
    if title_span:
        full = title_span.get_text(strip=True)
        return re.sub(r"\s*/\s*Twilio$", "", full)

    match = re.match(r"^(.+?)\s*/\s*Twilio:", subject)
    if match:
        return match.group(1).strip()

    return "Unknown"


def _extract_call_date(soup: BeautifulSoup) -> str | None:
    date_pattern = re.compile(
        r"(Jan|Feb|Mar|Apr|May|Jun|Jul|Aug|Sep|Oct|Nov|Dec)\s+\d{1,2},\s+\d{4}"
    )
    for span in soup.find_all("span"):
        text = span.get_text(strip=True)
        match = date_pattern.match(text)
        if match:
            return match.group(0)
    return None


def _extract_duration(soup: BeautifulSoup) -> str | None:
    duration_pattern = re.compile(r"(\d+)\s+minutes?")
    for span in soup.find_all("span"):
        text = span.get_text(strip=True)
        match = duration_pattern.match(text)
        if match:
            return text
    return None


def _extract_numbered_section(soup: BeautifulSoup, heading: str) -> list[str]:
    """Extract numbered list items following a section heading like 'Key points'."""
    items = []
    heading_td = None
    for td in soup.find_all("td"):
        if td.get_text(strip=True) == heading:
            heading_td = td
            break

    if not heading_td:
        return items

    heading_tr = heading_td.find_parent("tr")
    if not heading_tr:
        return items

    content_tr = heading_tr.find_next_sibling("tr")
    if not content_tr:
        return items

    for row in content_tr.find_all("tr"):
        cells = row.find_all("td")
        if len(cells) >= 3:
            number_cell = cells[0]
            text_cell = cells[2]
            num_text = number_cell.get_text(strip=True)
            if re.match(r"\d+\.", num_text):
                text = text_cell.get_text(strip=True)
                if text:
                    items.append(text)

    return items


def _extract_participants(soup: BeautifulSoup) -> tuple[list[dict], list[dict]]:
    """Extract Twilio and customer participants from the Participants section."""
    twilio: list[dict] = []
    customer: list[dict] = []

    participants_td = None
    for td in soup.find_all("td"):
        if td.get_text(strip=True) == "Participants":
            participants_td = td
            break

    if not participants_td:
        return twilio, customer

    participants_tr = participants_td.find_parent("tr")
    if not participants_tr:
        return twilio, customer

    data_tr = participants_tr.find_next_sibling("tr")
    if not data_tr:
        return twilio, customer

    data_td = data_tr.find("td")
    if not data_td:
        return twilio, customer

    html_text = str(data_td)
    parts = re.split(r'<span style="font-weight: 700;">', html_text)

    for part in parts[1:]:
        company_match = re.match(r"([^<]+)</span>", part)
        if not company_match:
            continue
        company = company_match.group(1).strip()
        is_twilio = company.lower() == "twilio"

        lines = part.split("<br")
        for line in lines:
            line_soup = BeautifulSoup(line, "lxml")
            spans = line_soup.find_all("span")
            name = None
            title = None
            for span in spans:
                text = span.get_text(strip=True)
                if not text:
                    continue
                style = span.get("style", "")
                if "636467" in style:
                    title = text
                elif "font-weight: 700" not in style and text != company:
                    name = re.sub(r"\s*\(host\)\s*$", "", text)
            if name:
                participant = {"name": name, "title": title}
                if is_twilio:
                    twilio.append(participant)
                else:
                    customer.append(participant)

    return twilio, customer


def _extract_deals(soup: BeautifulSoup) -> list[dict]:
    """Extract associated deals from the 'Associated deals' section."""
    deals: list[dict] = []

    deals_td = None
    for td in soup.find_all("td"):
        if td.get_text(strip=True) == "Associated deals":
            deals_td = td
            break

    if not deals_td:
        return deals

    deals_container = deals_td.find_parent("tr")
    if not deals_container:
        return deals

    deal_rows = deals_container.find_next_siblings("tr")
    for row in deal_rows:
        name_link = row.find("a", style=lambda s: s and "5B437A" in (s or ""))
        if not name_link:
            continue

        deal_name = name_link.get_text(strip=True)
        amount = None
        stage = None
        close_date = None

        for td in row.find_all("td"):
            text = td.get_text(strip=True)
            if text.startswith("Amount"):
                amount_match = re.search(r"\$[\d,]+(?:\.\d+)?", text)
                if amount_match:
                    amount = amount_match.group(0)
            elif text.startswith("Call stage"):
                stage = text.replace("Call stage:", "").replace("Call stage", "").strip()
            elif text.startswith("Close date"):
                close_date = text.replace("Close date:", "").replace("Close date", "").strip()

        deals.append({
            "name": deal_name,
            "amount": amount,
            "stage": stage,
            "close_date": close_date,
        })

    return deals


def parse_call_date(date_str: str | None) -> datetime | None:
    """Convert a date string like 'Apr 13, 2026' to a datetime object."""
    if not date_str:
        return None
    try:
        return datetime.strptime(date_str, "%b %d, %Y")
    except ValueError:
        return None
