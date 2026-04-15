"""
research.py — Web research functions for Customer Profiler

Scrapes company websites and searches for public information to enrich
the customer profile before Claude analysis.
"""

from __future__ import annotations

import re
import time
import json
from urllib.parse import urlparse, urljoin
from typing import Any

import requests
from bs4 import BeautifulSoup

HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/124.0.0.0 Safari/537.36"
    ),
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
    "Accept-Language": "en-US,en;q=0.5",
}

PHONE_RE = re.compile(
    r"""
    (?<!\d)                         # not preceded by digit
    (?:
        \+1[\s\-.]?                 # optional +1 country code
    )?
    (?:
        \(?\d{3}\)?[\s\-.]?         # area code
        \d{3}[\s\-.]?               # exchange
        \d{4}                       # subscriber
    )
    (?!\d)                          # not followed by digit
    """,
    re.VERBOSE,
)

TOLL_FREE_PREFIXES = {"800", "833", "844", "855", "866", "877", "888"}

SOCIAL_PATTERNS = {
    "linkedin": re.compile(r"linkedin\.com/company/[\w\-]+", re.I),
    "twitter":  re.compile(r"(?:twitter|x)\.com/[\w]+", re.I),
    "facebook": re.compile(r"facebook\.com/[\w.\-]+", re.I),
    "instagram": re.compile(r"instagram\.com/[\w.\-]+", re.I),
    "youtube":  re.compile(r"youtube\.com/(?:c/|channel/|@)[\w\-]+", re.I),
}

CHAT_SIGNALS = [
    "intercom", "drift", "zendesk", "freshdesk", "freshchat",
    "livechat", "tawk", "crisp", "hubspot chat", "tidio",
    "whatsapp", "wa.me", "twilio", "sendbird",
]

CONTACT_CENTER_SIGNALS = [
    "call center", "contact center", "customer support", "help desk",
    "genesys", "five9", "nice incontact", "avaya", "cisco uccx",
    "salesforce service cloud", "servicenow", "zendesk support",
]


def _safe_get(url: str, timeout: int = 8) -> requests.Response | None:
    try:
        resp = requests.get(url, headers=HEADERS, timeout=timeout, allow_redirects=True)
        resp.raise_for_status()
        return resp
    except Exception:
        return None


def fetch_website(url: str) -> dict[str, Any]:
    """
    Scrape a company homepage and extract structured info.
    Returns a dict with: title, description, phone_numbers, emails,
    social_links, chat_signals, contact_center_signals, raw_text.
    """
    if not url:
        return {}

    if not url.startswith(("http://", "https://")):
        url = "https://" + url

    resp = _safe_get(url)
    if not resp:
        # Retry with http
        resp = _safe_get(url.replace("https://", "http://"))
    if not resp:
        return {"error": f"Could not reach {url}"}

    soup = BeautifulSoup(resp.text, "lxml")

    # Remove script/style noise
    for tag in soup(["script", "style", "noscript"]):
        tag.decompose()

    raw_text = soup.get_text(separator=" ", strip=True)
    raw_text = re.sub(r"\s+", " ", raw_text)[:12000]  # cap for Claude context

    # Meta description
    meta_desc = ""
    for tag in soup.find_all("meta"):
        if tag.get("name", "").lower() in ("description", "og:description"):
            meta_desc = tag.get("content", "")
            break
        if tag.get("property", "").lower() == "og:description":
            meta_desc = tag.get("content", "")
            break

    title = soup.title.string.strip() if soup.title and soup.title.string else ""

    # Phone numbers
    phones_raw = PHONE_RE.findall(raw_text)
    phones = list(dict.fromkeys(phones_raw))[:10]  # dedupe, limit

    toll_free = [p for p in phones if any(
        re.search(r"\b" + pref + r"\b", p) for pref in TOLL_FREE_PREFIXES
    )]

    # Emails (limited scope — career/press emails often)
    emails = list(dict.fromkeys(
        re.findall(r"[\w.+\-]+@[\w.\-]+\.[a-z]{2,}", raw_text.lower())
    ))[:5]

    # Social links
    all_links = [a.get("href", "") for a in soup.find_all("a", href=True)]
    social = {}
    for platform, pattern in SOCIAL_PATTERNS.items():
        for link in all_links:
            m = pattern.search(link)
            if m:
                social[platform] = "https://" + m.group(0).lstrip("/")
                break

    # Chat / messaging signals
    page_lower = raw_text.lower() + " " + resp.text.lower()
    chat_detected = [s for s in CHAT_SIGNALS if s in page_lower]
    cc_detected = [s for s in CONTACT_CENTER_SIGNALS if s in page_lower]

    # WhatsApp Business detection
    has_whatsapp = bool(re.search(r"wa\.me|whatsapp\.com|whatsapp", page_lower))

    return {
        "url": url,
        "title": title,
        "description": meta_desc,
        "phone_numbers": phones,
        "toll_free_numbers": toll_free,
        "emails": emails,
        "social_links": social,
        "chat_tools_detected": list(dict.fromkeys(chat_detected)),
        "contact_center_signals": list(dict.fromkeys(cc_detected)),
        "has_whatsapp": has_whatsapp,
        "raw_text_snippet": raw_text[:3000],
    }


def search_duckduckgo(query: str, max_results: int = 6) -> list[dict[str, str]]:
    """
    Search DuckDuckGo HTML endpoint (no API key required).
    Returns list of {title, url, snippet}.
    """
    url = "https://html.duckduckgo.com/html/"
    try:
        resp = requests.post(
            url,
            data={"q": query, "b": "", "kl": "us-en"},
            headers=HEADERS,
            timeout=10,
        )
        resp.raise_for_status()
    except Exception:
        return []

    soup = BeautifulSoup(resp.text, "lxml")
    results = []

    for result in soup.select(".result__body")[:max_results]:
        title_el = result.select_one(".result__title")
        url_el = result.select_one(".result__url")
        snippet_el = result.select_one(".result__snippet")

        title = title_el.get_text(strip=True) if title_el else ""
        href = ""
        if title_el and title_el.find("a"):
            href = title_el.find("a").get("href", "")
            # DuckDuckGo wraps hrefs — extract real URL
            m = re.search(r"uddg=([^&]+)", href)
            if m:
                from urllib.parse import unquote
                href = unquote(m.group(1))
        snippet = snippet_el.get_text(strip=True) if snippet_el else ""

        if title:
            results.append({"title": title, "url": href, "snippet": snippet})

    return results


def research_company(customer_data: dict) -> dict:
    """
    Orchestrate all research for a given customer.
    Returns enriched data dict with progress messages.
    """
    company_name = customer_data.get("company_name", "").strip()
    website_url  = customer_data.get("website_url", "").strip()
    progress: list[str] = []

    result: dict[str, Any] = {
        "progress": progress,
        "website_data": {},
        "search_results": [],
        "linkedin_data": {},
    }

    # 1. Scrape website
    if website_url:
        progress.append(f"🌐 Scraping website: {website_url}")
        result["website_data"] = fetch_website(website_url)
        time.sleep(0.5)
    elif company_name:
        # Try to find official website via search
        progress.append(f"🔎 Searching for {company_name} official website...")
        hits = search_duckduckgo(f"{company_name} official website")
        if hits:
            candidate = hits[0]["url"]
            if candidate and "http" in candidate:
                result["website_data"] = fetch_website(candidate)
                result["website_data"]["discovered_url"] = candidate
                time.sleep(0.5)

    # 2. Company overview search
    if company_name:
        progress.append(f"📰 Searching for company news and profile...")
        queries = [
            f"{company_name} company overview employees revenue",
            f"{company_name} customer service contact center communication",
        ]
        for q in queries:
            hits = search_duckduckgo(q, max_results=4)
            result["search_results"].extend(hits)
            time.sleep(0.3)

    # 3. LinkedIn search
    if company_name:
        progress.append("🔗 Looking for LinkedIn company page...")
        linkedin_hits = search_duckduckgo(
            f"site:linkedin.com/company {company_name}", max_results=2
        )
        if linkedin_hits:
            result["linkedin_data"] = {
                "url": linkedin_hits[0].get("url", ""),
                "snippet": linkedin_hits[0].get("snippet", ""),
            }
        time.sleep(0.3)

    progress.append("✅ Research complete. Generating AI analysis...")
    return result
