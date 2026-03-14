"""URL normalization helpers for crawl dedupe and canonicalization."""

import posixpath
import re
from urllib.parse import parse_qsl, quote, urlencode, urlparse, urlunparse

DEFAULT_PORTS = {"http": 80, "https": 443}
TRACKING_PARAM_PREFIXES = ("utm_", "mc_", "pk_", "vero_")
TRACKING_PARAM_NAMES = {
    "_ga",
    "_gl",
    "_hsenc",
    "_hsmi",
    "dm_i",
    "fbclid",
    "gclid",
    "gbraid",
    "hs_amp",
    "igshid",
    "mkt_tok",
    "msclkid",
    "oly_anon_id",
    "oly_enc_id",
    "rb_clickid",
    "s_cid",
    "wickedid",
    "wbraid",
    "yclid",
}
SESSION_PARAM_NAMES = {
    "jsessionid",
    "phpsessid",
    "session",
    "session_id",
    "sessionid",
}
MULTISLASH_RE = re.compile(r"/{2,}")


def normalize_query_param_name(name: str) -> str:
    """Normalize a query parameter name for comparison.

    Args:
        name: Raw parameter name.

    Returns:
        Lowercased normalized parameter name.
    """
    return (name or "").strip().lower()


def is_tracking_query_param(name: str) -> bool:
    """Check whether a query parameter is likely tracking-related.

    Args:
        name: Query parameter name.

    Returns:
        ``True`` when the parameter looks like tracking data.
    """
    normalized_name = normalize_query_param_name(name)
    if normalized_name in TRACKING_PARAM_NAMES or normalized_name in SESSION_PARAM_NAMES:
        return True
    return any(normalized_name.startswith(prefix) for prefix in TRACKING_PARAM_PREFIXES)


def normalize_netloc(parsed_url) -> str:
    """Normalize the network location of a parsed URL.

    Args:
        parsed_url: Parsed URL object.

    Returns:
        Normalized network location string.
    """
    host = (parsed_url.hostname or "").encode("idna").decode("ascii").lower()
    if not host:
        return ""

    username = parsed_url.username or ""
    password = parsed_url.password or ""
    port = parsed_url.port
    if port == DEFAULT_PORTS.get(parsed_url.scheme.lower()):
        port = None

    userinfo = ""
    if username:
        userinfo = username
        if password:
            userinfo = f"{userinfo}:{password}"
        userinfo = f"{userinfo}@"

    port_suffix = f":{port}" if port else ""
    return f"{userinfo}{host}{port_suffix}"


def normalize_path(path: str) -> str:
    """Normalize a URL path conservatively.

    Args:
        path: Raw path.

    Returns:
        Normalized path.
    """
    path = path or "/"
    path = MULTISLASH_RE.sub("/", path)
    trailing_slash = path.endswith("/")
    normalized = posixpath.normpath(path)
    if not normalized.startswith("/"):
        normalized = f"/{normalized}"
    if trailing_slash and not normalized.endswith("/"):
        normalized = f"{normalized}/"
    if normalized == "/.":
        normalized = "/"
    return quote(normalized, safe="/:@!$&'()*+,;=-._~")


def normalize_query(
    query: str,
    drop_tracking_params: bool = False,
    keep_blank_values: bool = False,
    sort_query_params: bool = True,
) -> str:
    """Normalize a URL query string.

    Args:
        query: Raw query string.
        drop_tracking_params: Whether to remove known tracking parameters.
        keep_blank_values: Whether blank values should be retained.
        sort_query_params: Whether parameters should be sorted.

    Returns:
        Normalized query string.
    """
    if not query:
        return ""

    query_items = []
    for key, value in parse_qsl(query, keep_blank_values=True):
        normalized_key = normalize_query_param_name(key)
        if drop_tracking_params and is_tracking_query_param(normalized_key):
            continue
        if not keep_blank_values and value == "":
            continue
        query_items.append((normalized_key, value))

    if sort_query_params:
        query_items.sort(key=lambda item: (item[0], item[1]))

    return urlencode(query_items, doseq=True)


def normalize_url(
    url: str,
    *,
    drop_tracking_params: bool = False,
    keep_blank_values: bool = False,
    keep_fragments: bool = False,
    sort_query_params: bool = True,
) -> str:
    """Normalize a URL for dedupe and canonical comparison.

    Args:
        url: URL to normalize.
        drop_tracking_params: Whether to remove tracking parameters.
        keep_blank_values: Whether blank query values should be retained.
        keep_fragments: Whether fragments should be preserved.
        sort_query_params: Whether query parameters should be sorted.

    Returns:
        Normalized absolute or relative URL.
    """
    parsed_url = urlparse((url or "").strip())
    scheme = parsed_url.scheme.lower()
    netloc = normalize_netloc(parsed_url)
    path = normalize_path(parsed_url.path)
    query = normalize_query(
        parsed_url.query,
        drop_tracking_params=drop_tracking_params,
        keep_blank_values=keep_blank_values,
        sort_query_params=sort_query_params,
    )
    fragment = parsed_url.fragment if keep_fragments else ""
    return urlunparse((scheme, netloc, path, "", query, fragment))


def get_url_dedupe_key(
    url: str,
    drop_tracking_params: bool = True,
) -> str:
    """Build a normalized dedupe key for a URL.

    Args:
        url: URL to normalize.
        drop_tracking_params: Whether tracking parameters should be removed.

    Returns:
        Normalized URL key.
    """
    return normalize_url(
        url,
        drop_tracking_params=drop_tracking_params,
        keep_blank_values=False,
        keep_fragments=False,
        sort_query_params=True,
    )


def get_canonical_dedupe_key(
    url: str,
    canonical_url: str | None = None,
    drop_tracking_params: bool = True,
) -> str:
    """Resolve the best dedupe key for a fetched page.

    Args:
        url: Effective fetched URL.
        canonical_url: Optional page-declared canonical URL.
        drop_tracking_params: Whether tracking parameters should be removed.

    Returns:
        Canonical dedupe key when trusted, otherwise the normalized page URL key.
    """
    page_key = get_url_dedupe_key(url, drop_tracking_params=drop_tracking_params)
    if not canonical_url:
        return page_key

    parsed_page = urlparse(page_key)
    canonical_key = get_url_dedupe_key(canonical_url, drop_tracking_params=drop_tracking_params)
    parsed_canonical = urlparse(canonical_key)
    page_host = parsed_page.netloc.removeprefix("www.")
    canonical_host = parsed_canonical.netloc.removeprefix("www.")
    if not page_host or page_host != canonical_host:
        return page_key
    return canonical_key
