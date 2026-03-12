"""Proxy helpers for HTTP and browser fetches."""


def normalize_proxy_urls(
    proxy_url: str | None = None,
    proxy_urls: list[str] | None = None,
) -> list[str]:
    """Normalize one or many proxy URLs into a clean list.

    Args:
        proxy_url: Optional single proxy URL.
        proxy_urls: Optional proxy URL list.

    Returns:
        Normalized proxy URL list.
    """
    values = []
    if proxy_url:
        values.append(proxy_url)
    if proxy_urls:
        values.extend(proxy_urls)
    return [value.strip() for value in values if value and value.strip()]


def pick_proxy(proxy_urls: list[str], index: int = 0) -> str | None:
    """Select a proxy URL by round-robin index.

    Args:
        proxy_urls: Available proxy URL list.
        index: Selection index.

    Returns:
        Selected proxy URL or ``None``.
    """
    if not proxy_urls:
        return None
    return proxy_urls[index % len(proxy_urls)]
