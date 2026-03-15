"""Cookie normalization and export helpers."""

from __future__ import annotations

from http.cookiejar import Cookie as HTTPCookie
from http.cookies import SimpleCookie
from typing import Any
from urllib.parse import urlparse

import nodriver.cdp.network as network_cdp
from curl_cffi.requests.cookies import Cookies as CurlCookies


CookiePayload = dict[str, Any]

COOKIE_SAME_SITE_MAP = {
    "strict": network_cdp.CookieSameSite.STRICT,
    "lax": network_cdp.CookieSameSite.LAX,
    "none": network_cdp.CookieSameSite.NONE,
}


def _bool_value(value: Any, default: bool = False) -> bool:
    if isinstance(value, bool):
        return value
    if value is None:
        return default
    if isinstance(value, str):
        normalized = value.strip().lower()
        if normalized in {"1", "true", "yes", "on"}:
            return True
        if normalized in {"0", "false", "no", "off"}:
            return False
    return bool(value)


def _optional_int(value: Any) -> int | None:
    if value in (None, ""):
        return None
    try:
        return int(value)
    except (TypeError, ValueError):
        raise ValueError(f"Invalid integer cookie field: {value}")


def _optional_float(value: Any) -> float | None:
    if value in (None, ""):
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        raise ValueError(f"Invalid numeric cookie field: {value}")


def normalize_same_site(value: Any) -> str | None:
    """Normalize a cookie SameSite value.

    Args:
        value: Raw SameSite value.

    Returns:
        Normalized SameSite string or ``None``.
    """
    if value in (None, ""):
        return None
    normalized = str(value).strip().lower()
    if normalized not in COOKIE_SAME_SITE_MAP:
        raise ValueError(f"Unsupported SameSite value: {value}")
    return normalized


def infer_cookie_url(cookie: CookiePayload, target_url: str | None = None) -> str | None:
    """Infer a cookie URL for browser cookie bootstrap.

    Args:
        cookie: Normalized cookie payload.
        target_url: Optional target navigation URL.

    Returns:
        Cookie URL or ``None`` when it cannot be inferred.
    """
    if cookie.get("url"):
        return cookie["url"]
    domain = cookie.get("domain")
    if domain:
        scheme = "https" if cookie.get("secure") else "http"
        path = cookie.get("path") or "/"
        return f"{scheme}://{str(domain).lstrip('.')}{path}"
    return target_url


def normalize_cookie_payloads(
    initial_cookies: list[dict[str, Any]] | dict[str, Any] | None = None,
) -> list[CookiePayload]:
    """Normalize user-supplied cookie payloads.

    Args:
        initial_cookies: Cookie mapping or list of cookie objects.

    Returns:
        Normalized cookie payload list.
    """
    if not initial_cookies:
        return []
    if isinstance(initial_cookies, dict):
        items = [{"name": name, "value": value} for name, value in initial_cookies.items()]
    elif isinstance(initial_cookies, list):
        items = initial_cookies
    else:
        raise ValueError("initial_cookies must be a list of cookie objects or a name/value mapping")

    normalized = []
    for item in items:
        if not isinstance(item, dict):
            raise ValueError(f"Invalid cookie payload: {item}")
        name = str(item.get("name", "")).strip()
        if not name:
            raise ValueError(f"Cookie name is required: {item}")
        value = str(item.get("value", ""))
        path = str(item.get("path") or "/")
        normalized.append(
            {
                "name": name,
                "value": value,
                "url": str(item["url"]).strip() if item.get("url") else None,
                "domain": str(item["domain"]).strip() if item.get("domain") else None,
                "path": path or "/",
                "secure": _bool_value(item.get("secure"), default=False),
                "http_only": _bool_value(item.get("http_only"), default=False),
                "same_site": normalize_same_site(item.get("same_site")),
                "expires": _optional_float(item.get("expires")),
            }
        )
    return normalized


def merge_cookie_sources(
    cookie_entries: list[str] | None = None,
    cookie_file_payload: list[dict[str, Any]] | dict[str, Any] | None = None,
) -> list[CookiePayload]:
    """Merge simple CLI cookie entries with structured cookie-file payloads.

    Args:
        cookie_entries: Repeated ``name=value`` entries.
        cookie_file_payload: Parsed JSON cookie payload.

    Returns:
        Normalized merged cookie payloads.
    """
    merged: list[dict[str, Any]] = []
    for entry in cookie_entries or []:
        name, separator, value = entry.partition("=")
        if not separator:
            raise ValueError(f"Invalid cookie entry: {entry}")
        merged.append({"name": name.strip(), "value": value.strip()})
    file_cookies = normalize_cookie_payloads(cookie_file_payload)
    merged.extend(file_cookies)
    return normalize_cookie_payloads(merged)


def build_browser_cookie_params(
    cookies: list[CookiePayload],
    target_url: str | None = None,
) -> list[network_cdp.CookieParam]:
    """Build browser cookie params for CDP storage injection.

    Args:
        cookies: Normalized cookie payloads.
        target_url: Optional target URL used to infer cookie scope.

    Returns:
        Cookie params for browser injection.
    """
    params = []
    for cookie in cookies:
        cookie_url = infer_cookie_url(cookie, target_url=target_url)
        same_site = cookie.get("same_site")
        params.append(
            network_cdp.CookieParam(
                name=cookie["name"],
                value=cookie["value"],
                url=cookie_url,
                domain=cookie.get("domain"),
                path=cookie.get("path"),
                secure=cookie.get("secure"),
                http_only=cookie.get("http_only"),
                same_site=COOKIE_SAME_SITE_MAP[same_site] if same_site else None,
                expires=cookie.get("expires"),
            )
        )
    return params


def apply_initial_http_cookies(
    session_cookies: CurlCookies,
    cookies: list[CookiePayload],
    target_url: str,
) -> None:
    """Apply structured cookies to a curl_cffi cookie jar.

    Args:
        session_cookies: Target cookie jar.
        cookies: Normalized cookie payloads.
        target_url: Request URL used to infer cookie scope.
    """
    parsed_target = urlparse(target_url)
    for cookie in cookies:
        cookie_domain = cookie.get("domain")
        inferred_url = infer_cookie_url(cookie, target_url=target_url)
        parsed_cookie_url = urlparse(inferred_url) if inferred_url else parsed_target
        domain = cookie_domain or parsed_cookie_url.hostname or parsed_target.hostname or ""
        if not domain:
            raise ValueError(f"Unable to infer cookie domain for {cookie['name']}")
        session_cookies.set(
            cookie["name"],
            cookie["value"],
            domain=domain,
            path=cookie.get("path") or "/",
            secure=bool(cookie.get("secure")),
        )


def export_http_cookies(session_cookies: CurlCookies) -> list[CookiePayload]:
    """Export curl_cffi session cookies into normalized payloads.

    Args:
        session_cookies: Cookie jar to export.

    Returns:
        Exported cookie payload list.
    """
    exported = []
    seen = set()
    for cookie in session_cookies.jar:
        domain = (cookie.domain or "").lstrip(".") or None
        key = (cookie.name, domain, cookie.path or "/")
        if key in seen:
            continue
        seen.add(key)
        exported.append(
            {
                "name": cookie.name,
                "value": cookie.value or "",
                "domain": domain,
                "path": cookie.path or "/",
                "secure": bool(cookie.secure),
                "http_only": _bool_value(cookie._rest.get("HttpOnly"), default=False),
                "same_site": None,
                "expires": float(cookie.expires) if cookie.expires is not None else None,
            }
        )
    return exported


def export_browser_cookies(cookies: list[network_cdp.Cookie]) -> list[CookiePayload]:
    """Export browser cookies into normalized payloads.

    Args:
        cookies: Browser cookies from CDP.

    Returns:
        Exported cookie payload list.
    """
    exported = []
    seen = set()
    for cookie in cookies:
        domain = (cookie.domain or "").lstrip(".")
        key = (cookie.name, domain, cookie.path)
        if key in seen:
            continue
        seen.add(key)
        exported.append(
            {
                "name": cookie.name,
                "value": cookie.value,
                "domain": domain,
                "path": cookie.path,
                "secure": bool(cookie.secure),
                "http_only": bool(cookie.http_only),
                "same_site": cookie.same_site.value.lower() if cookie.same_site is not None else None,
                "expires": float(cookie.expires) if cookie.expires is not None else None,
            }
        )
    return exported


def parse_cookie_header_string(cookie_header: str) -> list[CookiePayload]:
    """Parse a Cookie header string into normalized cookie payloads.

    Args:
        cookie_header: Raw ``Cookie`` header string.

    Returns:
        Parsed cookie payloads.
    """
    cookie = SimpleCookie()
    cookie.load(cookie_header)
    return normalize_cookie_payloads(
        [{"name": morsel.key, "value": morsel.value} for morsel in cookie.values()]
    )


def export_http_cookiejar_cookie(cookie: HTTPCookie) -> CookiePayload:
    """Export a stdlib cookiejar cookie into normalized payload form.

    Args:
        cookie: Standard cookiejar cookie.

    Returns:
        Exported cookie payload.
    """
    return {
        "name": cookie.name,
        "value": cookie.value or "",
        "domain": cookie.domain or None,
        "path": cookie.path or "/",
        "secure": bool(cookie.secure),
        "http_only": _bool_value(cookie._rest.get("HttpOnly"), default=False),
        "same_site": None,
        "expires": float(cookie.expires) if cookie.expires is not None else None,
    }
