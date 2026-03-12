"""Browser lifecycle helpers."""

import asyncio
from contextlib import asynccontextmanager

import nodriver as uc
import nodriver.cdp.network as network_cdp
import nodriver.cdp.security as security_cdp


async def kill_browser(browser) -> None:
    """Close all tabs and stop a nodriver browser instance.

    Args:
        browser: Browser instance to stop.
    """
    try:
        for tab in browser.tabs:
            await tab.close()
        browser.stop()
    except Exception:
        pass


async def configure_page_request_settings(
    page,
    user_agent: str | None = None,
    headers: dict[str, str] | None = None,
    accept_invalid_certs: bool = False,
) -> None:
    """Configure browser-side request settings for a page.

    Args:
        page: Browser page/tab.
        user_agent: Optional user-agent override.
        headers: Optional extra headers.
        accept_invalid_certs: Whether to ignore certificate errors.
    """
    await page.send(network_cdp.enable())
    if accept_invalid_certs:
        await page.send(security_cdp.set_ignore_certificate_errors(True))
    if headers:
        await page.send(network_cdp.set_extra_http_headers(network_cdp.Headers.from_json(headers)))
    if user_agent:
        await page.send(network_cdp.set_user_agent_override(user_agent=user_agent))


@asynccontextmanager
async def browser_session(headless: bool = False, browser_args: list[str] | None = None):
    """Start a nodriver browser session and guarantee cleanup.

    Args:
        headless: Whether to launch the browser headlessly.
        browser_args: Optional browser launch arguments.
    """
    browser = await uc.start(headless=headless, browser_args=browser_args)
    try:
        yield browser
    finally:
        await kill_browser(browser)
        await asyncio.sleep(0.5)
