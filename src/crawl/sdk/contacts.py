"""Contact and social handle extraction helpers."""

import re
from urllib.parse import urljoin
from urllib.parse import urlparse

from bs4 import BeautifulSoup

EMAIL_RE = re.compile(r"\b[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}\b")
PHONE_RE = re.compile(r"(?:(?:\+?\d[\d\s().-]{6,}\d))")
SOCIAL_PATTERNS = {
    "discord": ("discord.gg/", "discord.com/"),
    "facebook": ("facebook.com/", "fb.com/"),
    "github": ("github.com/",),
    "instagram": ("instagram.com/",),
    "linkedin": ("linkedin.com/",),
    "pinterest": ("pinterest.com/",),
    "tiktok": ("tiktok.com/",),
    "twitter": ("x.com/", "twitter.com/"),
    "youtube": ("youtube.com/", "youtu.be/"),
}


def normalize_phone(value: str) -> str:
    """Normalize a phone number candidate for dedupe.

    Args:
        value: Raw phone string.

    Returns:
        Normalized phone string.
    """
    compact = re.sub(r"[^\d+]+", "", value.strip())
    if compact.startswith("++"):
        compact = compact[1:]
    return compact


def extract_social_links(urls: list[str]) -> dict[str, list[str]]:
    """Group social links by provider.

    Args:
        urls: Candidate absolute URLs.

    Returns:
        Provider-to-links mapping.
    """
    grouped = {provider: [] for provider in SOCIAL_PATTERNS}
    for url in urls:
        lowered = url.lower()
        for provider, markers in SOCIAL_PATTERNS.items():
            if any(marker in lowered for marker in markers):
                if url not in grouped[provider]:
                    grouped[provider].append(url)
    return {provider: values for provider, values in grouped.items() if values}


def extract_contacts_from_html(html: str, page_url: str) -> dict:
    """Extract emails, phone numbers, and social links from HTML.

    Args:
        html: Raw page HTML.
        page_url: Base page URL.

    Returns:
        Contact extraction payload.
    """
    soup = BeautifulSoup(html, "html.parser")
    text = soup.get_text(" ", strip=True)
    links = []
    emails = set(EMAIL_RE.findall(text))
    phones = set()

    for anchor in soup.find_all("a", href=True):
        href = anchor.get("href", "").strip()
        if not href:
            continue

        absolute_url = urljoin(page_url, href)
        links.append(absolute_url)

        lowered = href.lower()
        if lowered.startswith("mailto:"):
            email_value = href.split(":", 1)[1].split("?", 1)[0].strip()
            if email_value:
                emails.add(email_value)
        if lowered.startswith("tel:"):
            phone_value = href.split(":", 1)[1].split("?", 1)[0].strip()
            normalized = normalize_phone(phone_value)
            if normalized:
                phones.add(normalized)

    for match in PHONE_RE.findall(text):
        normalized = normalize_phone(match)
        if len(re.sub(r"\D", "", normalized)) >= 7:
            phones.add(normalized)

    socials = extract_social_links(links)

    return {
        "emails": sorted(emails),
        "phones": sorted(phones),
        "socials": socials,
        "social_count": sum(len(values) for values in socials.values()),
        "link_count": len({url for url in links if urlparse(url).scheme in {"http", "https"}}),
    }
