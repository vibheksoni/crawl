"""Browser lifecycle helpers."""

import asyncio
from contextlib import asynccontextmanager
from pathlib import Path

import nodriver as uc
import nodriver.cdp.network as network_cdp
import nodriver.cdp.page as page_cdp
import nodriver.cdp.security as security_cdp

REQUEST_CAPTURE_SCRIPT = """
(() => {
  if (window.__crawlInstrumentationInstalled) {
    return;
  }
  window.__crawlInstrumentationInstalled = true;
  window.__crawlCapturedRequests = [];

  const pushRequest = entry => {
    try {
      window.__crawlCapturedRequests.push({
        url: entry.url || "",
        method: entry.method || "GET",
        type: entry.type || "resource",
        body: entry.body || "",
        timestamp: Date.now()
      });
    } catch (_) {}
  };

  const originalFetch = window.fetch;
  if (originalFetch) {
    window.fetch = async function(input, init) {
      const method = (init && init.method) || "GET";
      const url = typeof input === "string" ? input : (input && input.url) || "";
      const body = init && typeof init.body === "string" ? init.body : "";
      pushRequest({ url, method, type: "fetch", body });
      return originalFetch.apply(this, arguments);
    };
  }

  const originalOpen = XMLHttpRequest.prototype.open;
  const originalSend = XMLHttpRequest.prototype.send;
  XMLHttpRequest.prototype.open = function(method, url) {
    this.__crawlMethod = method || "GET";
    this.__crawlUrl = url || "";
    return originalOpen.apply(this, arguments);
  };
  XMLHttpRequest.prototype.send = function(body) {
    pushRequest({
      url: this.__crawlUrl || "",
      method: this.__crawlMethod || "GET",
      type: "xhr",
      body: typeof body === "string" ? body : ""
    });
    return originalSend.apply(this, arguments);
  };
})();
"""


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
async def browser_session(
    headless: bool = False,
    browser_args: list[str] | None = None,
    session_dir: str | None = None,
):
    """Start a nodriver browser session and guarantee cleanup.

    Args:
        headless: Whether to launch the browser headlessly.
        browser_args: Optional browser launch arguments.
        session_dir: Optional persistent browser profile directory.
    """
    resolved_session_dir = None
    cookie_file = None
    if session_dir:
        resolved_session_dir = str(Path(session_dir).resolve())
        Path(resolved_session_dir).mkdir(parents=True, exist_ok=True)
        cookie_file = str(Path(resolved_session_dir) / ".cookies.dat")

    browser = await uc.start(headless=headless, browser_args=browser_args, user_data_dir=resolved_session_dir)
    try:
        if cookie_file and Path(cookie_file).exists():
            try:
                await browser.cookies.load(cookie_file)
            except Exception:
                pass
        yield browser
    finally:
        if cookie_file:
            try:
                await browser.cookies.save(cookie_file)
            except Exception:
                pass
        await kill_browser(browser)
        await asyncio.sleep(0.5)


async def enable_request_capture(page) -> None:
    """Install browser-side request capture hooks on new documents.

    Args:
        page: Browser page/tab.
    """
    await page.send(page_cdp.add_script_to_evaluate_on_new_document(REQUEST_CAPTURE_SCRIPT))


async def collect_request_capture(page) -> list[dict]:
    """Collect captured fetch/XHR/resource requests from the page.

    Args:
        page: Browser page/tab.

    Returns:
        Request payload list.
    """
    expression = """
    (() => {
      const captured = Array.isArray(window.__crawlCapturedRequests) ? window.__crawlCapturedRequests : [];
      const perf = (performance.getEntriesByType('resource') || []).map(entry => ({
        url: entry.name || "",
        method: "GET",
        type: entry.initiatorType || "resource",
        body: "",
        duration: entry.duration || 0
      }));
      return JSON.stringify([...captured, ...perf]);
    })()
    """
    payload = await page.evaluate(expression, return_by_value=True)
    if not payload:
        return []
    import json

    try:
        return json.loads(payload)
    except json.JSONDecodeError:
        return []


async def perform_basic_interactions(page, max_clicks: int = 3, delay_ms: int = 1000) -> list[str]:
    """Perform simple click-through interactions on common expand/load-more controls.

    Args:
        page: Browser page/tab.
        max_clicks: Maximum interactions to perform.
        delay_ms: Wait time after each click.

    Returns:
        List of clicked element labels.
    """
    import re

    patterns = [re.compile(pattern, re.IGNORECASE) for pattern in ("load more", "show more", "show all", "more results", "expand", "next")]
    clicked = []
    seen_labels = set()

    for element in await page.select_all("button, a, [role='button']", timeout=2):
        label = (getattr(element, "text_all", "") or "").strip()
        if not label or label in seen_labels:
            continue
        if not any(pattern.search(label) for pattern in patterns):
            continue
        seen_labels.add(label)
        try:
            await element.click()
            clicked.append(label)
            await page.sleep(delay_ms / 1000)
        except Exception:
            continue
        if len(clicked) >= max_clicks:
            break

    return clicked
