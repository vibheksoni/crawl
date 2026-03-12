"""Browser lifecycle helpers."""

import asyncio
from contextlib import asynccontextmanager

import nodriver as uc


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


@asynccontextmanager
async def browser_session(headless: bool = False):
    """Start a nodriver browser session and guarantee cleanup.

    Args:
        headless: Whether to launch the browser headlessly.
    """
    browser = await uc.start(headless=headless)
    try:
        yield browser
    finally:
        await kill_browser(browser)
        await asyncio.sleep(0.5)
