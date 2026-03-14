"""Browser lifecycle helpers."""

import asyncio
import base64
import io
import json
from contextlib import asynccontextmanager, redirect_stdout
from pathlib import Path

import nodriver as uc
import nodriver.cdp.network as network_cdp
import nodriver.cdp.page as page_cdp
import nodriver.cdp.security as security_cdp
import nodriver.core.util as nodriver_util

from .consent import (
    CANDIDATE_SELECTOR,
    DIRECT_ACTION_SELECTORS,
    build_consent_context_text,
    build_overlay_removal_script,
    get_action_sequence,
    is_consent_context,
    score_consent_label,
)


def suppress_nodriver_cleanup_output() -> None:
    """Silence nodriver temp-profile cleanup prints that break JSON CLI output."""
    if getattr(nodriver_util, "__crawl_cleanup_print_suppressed__", False):
        return
    nodriver_util.print = lambda *args, **kwargs: None
    nodriver_util.__crawl_cleanup_print_suppressed__ = True


suppress_nodriver_cleanup_output()


def build_capture_script(
    capture_payloads: bool = False,
    max_payloads: int = 20,
    max_payload_bytes: int = 200000,
) -> str:
    """Build the browser-side network capture script.

    Args:
        capture_payloads: Whether fetch/XHR response payloads should be captured.
        max_payloads: Maximum API payload records to retain.
        max_payload_bytes: Maximum payload text length to retain per response.

    Returns:
        JavaScript source to inject into new documents.
    """
    capture_payloads_json = "true" if capture_payloads else "false"
    max_payloads = max(1, int(max_payloads))
    max_payload_bytes = max(256, int(max_payload_bytes))
    return f"""
(() => {{
  if (window.__crawlInstrumentationInstalled) {{
    return;
  }}
  window.__crawlInstrumentationInstalled = true;
  window.__crawlCapturedRequests = [];
  window.__crawlCapturedApiPayloads = [];
  window.__crawlCapturedApiPayloadKeys = [];
  window.__crawlCaptureConfig = {{
    capturePayloads: {capture_payloads_json},
    maxPayloads: {max_payloads},
    maxPayloadBytes: {max_payload_bytes}
  }};

  const pushRequest = entry => {{
    try {{
      window.__crawlCapturedRequests.push({{
        url: entry.url || "",
        method: entry.method || "GET",
        type: entry.type || "resource",
        body: entry.body || "",
        timestamp: Date.now()
      }});
    }} catch (_) {{}}
  }};

  const shouldCapturePayload = contentType => {{
    const value = String(contentType || "").toLowerCase();
    return value.includes("json") || value.includes("javascript") || value.includes("text/") || value.includes("xml");
  }};

  const pushPayload = entry => {{
    try {{
      const config = window.__crawlCaptureConfig || {{}};
      if (!config.capturePayloads) {{
        return;
      }}
      if (!entry.url) {{
        return;
      }}
      const contentType = String(entry.contentType || "").toLowerCase();
      if (!shouldCapturePayload(contentType)) {{
        return;
      }}
      if (window.__crawlCapturedApiPayloads.length >= (config.maxPayloads || 20)) {{
        return;
      }}
      const key = `${{entry.type || "api"}}|${{entry.method || "GET"}}|${{entry.url}}|${{entry.status || 0}}`;
      if (window.__crawlCapturedApiPayloadKeys.includes(key)) {{
        return;
      }}
      window.__crawlCapturedApiPayloadKeys.push(key);
      let text = typeof entry.text === "string" ? entry.text : "";
      const maxBytes = config.maxPayloadBytes || 200000;
      const truncated = text.length > maxBytes;
      if (truncated) {{
        text = text.slice(0, maxBytes);
      }}
      const payload = {{
        url: entry.url,
        method: entry.method || "GET",
        type: entry.type || "api",
        status: entry.status || 0,
        ok: !!entry.ok,
        content_type: contentType,
        body_length: typeof entry.text === "string" ? entry.text.length : text.length,
        truncated,
        timestamp: Date.now()
      }};
      if (contentType.includes("json")) {{
        try {{
          payload.body_json = JSON.parse(text);
        }} catch (_) {{
          payload.body_text = text;
        }}
      }} else {{
        payload.body_text = text;
      }}
      payload.body_preview = text.slice(0, 2000);
      window.__crawlCapturedApiPayloads.push(payload);
    }} catch (_) {{}}
  }};

  const originalFetch = window.fetch;
  if (originalFetch) {{
    window.fetch = async function(input, init) {{
      const method = (init && init.method) || "GET";
      const url = typeof input === "string" ? input : (input && input.url) || "";
      const body = init && typeof init.body === "string" ? init.body : "";
      pushRequest({{ url, method, type: "fetch", body }});
      const response = await originalFetch.apply(this, arguments);
      if ((window.__crawlCaptureConfig || {{}}).capturePayloads) {{
        try {{
          const clone = response.clone();
          const contentType = clone.headers.get("content-type") || "";
          if (shouldCapturePayload(contentType)) {{
            const text = await clone.text();
            pushPayload({{
              url: clone.url || url,
              method,
              type: "fetch",
              status: clone.status,
              ok: clone.ok,
              contentType,
              text
            }});
          }}
        }} catch (_) {{}}
      }}
      return response;
    }};
  }}

  const originalOpen = XMLHttpRequest.prototype.open;
  const originalSend = XMLHttpRequest.prototype.send;
  XMLHttpRequest.prototype.open = function(method, url) {{
    this.__crawlMethod = method || "GET";
    this.__crawlUrl = url || "";
    return originalOpen.apply(this, arguments);
  }};
  XMLHttpRequest.prototype.send = function(body) {{
    pushRequest({{
      url: this.__crawlUrl || "",
      method: this.__crawlMethod || "GET",
      type: "xhr",
      body: typeof body === "string" ? body : ""
    }});
    if ((window.__crawlCaptureConfig || {{}}).capturePayloads) {{
      this.addEventListener("loadend", () => {{
        try {{
          const contentType = this.getResponseHeader("content-type") || "";
          if (!shouldCapturePayload(contentType)) {{
            return;
          }}
          let text = "";
          if (this.responseType === "" || this.responseType === "text") {{
            text = typeof this.responseText === "string" ? this.responseText : "";
          }} else if (this.responseType === "json") {{
            text = JSON.stringify(this.response);
          }} else {{
            return;
          }}
          pushPayload({{
            url: this.responseURL || this.__crawlUrl || "",
            method: this.__crawlMethod || "GET",
            type: "xhr",
            status: this.status || 0,
            ok: (this.status || 0) >= 200 && (this.status || 0) < 400,
            contentType,
            text
          }});
        }} catch (_) {{}}
      }}, {{ once: true }});
    }}
    return originalSend.apply(this, arguments);
  }};
}})();
"""


def is_api_resource_type(resource_type) -> bool:
    """Check whether a CDP resource type is API-like.

    Args:
        resource_type: CDP resource type enum or string.

    Returns:
        ``True`` for fetch/XHR style traffic.
    """
    return str(resource_type).lower().endswith(("fetch", "xhr"))


def is_api_content_type(content_type: str) -> bool:
    """Check whether a content type is worth capturing as an API payload.

    Args:
        content_type: Response content type.

    Returns:
        ``True`` for JSON/text/XML/script-like responses.
    """
    lowered = (content_type or "").lower()
    return any(token in lowered for token in ("json", "javascript", "text/", "xml"))


async def _finalize_api_payload_capture(page, request_id: str, request_id_raw) -> None:
    """Read and store a completed response body for a tracked API request.

    Args:
        page: Browser page/tab.
        request_id: CDP request identifier.
    """
    pending = getattr(page, "__crawl_api_pending", {})
    payloads = getattr(page, "__crawl_api_payloads", [])
    config = getattr(page, "__crawl_api_config", {})
    seen_keys = getattr(page, "__crawl_api_seen_keys", set())
    entry = pending.pop(request_id, None)
    if not entry:
        return
    if len(payloads) >= config.get("max_payloads", 20):
        return

    dedupe_key = "|".join(
        [
            entry.get("type", "api"),
            entry.get("method", "GET"),
            entry.get("url", ""),
            str(entry.get("status", 0)),
        ]
    )
    if dedupe_key in seen_keys:
        return

    try:
        body, base64encoded = await page.send(network_cdp.get_response_body(request_id_raw))
    except Exception:
        return

    if base64encoded:
        try:
            body_text = base64.b64decode(body).decode("utf-8", errors="replace")
        except Exception:
            return
    else:
        body_text = str(body or "")

    if not body_text:
        return
    content_type = entry.get("content_type", "")
    if not is_api_content_type(content_type):
        return

    max_payload_bytes = config.get("max_payload_bytes", 200000)
    truncated = len(body_text) > max_payload_bytes
    stored_text = body_text[:max_payload_bytes] if truncated else body_text
    payload = {
        **entry,
        "body_length": len(body_text),
        "truncated": truncated,
        "body_preview": stored_text[:2000],
    }
    if "json" in content_type.lower():
        try:
            payload["body_json"] = json.loads(stored_text)
        except json.JSONDecodeError:
            payload["body_text"] = stored_text
    else:
        payload["body_text"] = stored_text

    payloads.append(payload)
    seen_keys.add(dedupe_key)


async def enable_api_payload_capture(
    page,
    max_api_payloads: int = 20,
    max_api_payload_bytes: int = 200000,
) -> None:
    """Enable Python-side CDP capture for fetch/XHR response bodies.

    Args:
        page: Browser page/tab.
        max_api_payloads: Maximum API payload records to retain.
        max_api_payload_bytes: Maximum payload text length to retain per response.
    """
    page.__crawl_api_payloads = []
    page.__crawl_api_pending = {}
    page.__crawl_api_seen_keys = set()
    page.__crawl_api_tasks = set()
    page.__crawl_api_config = {
        "max_payloads": max(1, max_api_payloads),
        "max_payload_bytes": max(256, max_api_payload_bytes),
    }

    async def response_received_handler(ev: network_cdp.ResponseReceived) -> None:
        if not is_api_resource_type(ev.type_):
            return
        content_type = ev.response.mime_type or ev.response.headers.get("content-type", "")
        if not is_api_content_type(content_type):
            return
        resource_type = getattr(ev.type_, "value", str(ev.type_)).lower()
        page.__crawl_api_pending[str(ev.request_id)] = {
            "url": ev.response.url,
            "method": "GET",
            "type": resource_type,
            "status": ev.response.status,
            "ok": 200 <= ev.response.status < 400,
            "content_type": content_type,
            "timestamp": int(float(ev.timestamp) * 1000),
        }

    async def loading_finished_handler(ev: network_cdp.LoadingFinished) -> None:
        request_id = str(ev.request_id)
        if request_id not in page.__crawl_api_pending:
            return
        task = asyncio.create_task(_finalize_api_payload_capture(page, request_id, ev.request_id))
        page.__crawl_api_tasks.add(task)
        task.add_done_callback(page.__crawl_api_tasks.discard)

    async def loading_failed_handler(ev: network_cdp.LoadingFailed) -> None:
        page.__crawl_api_pending.pop(str(ev.request_id), None)

    page.add_handler(network_cdp.ResponseReceived, response_received_handler)
    page.add_handler(network_cdp.LoadingFinished, loading_finished_handler)
    page.add_handler(network_cdp.LoadingFailed, loading_failed_handler)


async def kill_browser(browser) -> None:
    """Close all tabs and stop a nodriver browser instance.

    Args:
        browser: Browser instance to stop.
    """
    try:
        for tab in browser.tabs:
            await tab.close()
        with redirect_stdout(io.StringIO()):
            browser.stop()
            await asyncio.sleep(0.5)
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


async def enable_request_capture(
    page,
    capture_api_payloads: bool = False,
    max_api_payloads: int = 20,
    max_api_payload_bytes: int = 200000,
) -> None:
    """Install browser-side request capture hooks on new documents.

    Args:
        page: Browser page/tab.
        capture_api_payloads: Whether fetch/XHR response payloads should be captured.
        max_api_payloads: Maximum API payload records to retain.
        max_api_payload_bytes: Maximum payload text length to retain per response.
    """
    await page.send(
        page_cdp.add_script_to_evaluate_on_new_document(
            build_capture_script(
                capture_payloads=capture_api_payloads,
                max_payloads=max_api_payloads,
                max_payload_bytes=max_api_payload_bytes,
            ),
            run_immediately=True,
        )
    )
    if capture_api_payloads:
        await enable_api_payload_capture(
            page,
            max_api_payloads=max_api_payloads,
            max_api_payload_bytes=max_api_payload_bytes,
        )


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


async def collect_api_payload_capture(page) -> list[dict]:
    """Collect captured fetch/XHR response payloads from the page.

    Args:
        page: Browser page/tab.

    Returns:
        API payload capture list.
    """
    tasks = list(getattr(page, "__crawl_api_tasks", set()))
    if tasks:
        await asyncio.gather(*tasks, return_exceptions=True)
    if hasattr(page, "__crawl_api_payloads"):
        return list(getattr(page, "__crawl_api_payloads", []))
    expression = """
    (() => JSON.stringify(Array.isArray(window.__crawlCapturedApiPayloads) ? window.__crawlCapturedApiPayloads : []))()
    """
    payload = await page.evaluate(expression, return_by_value=True)
    if not payload:
        return []
    try:
        return json.loads(payload)
    except json.JSONDecodeError:
        return []


def get_element_text_candidates(element) -> list[str]:
    """Collect possible visible/action labels from an element.

    Args:
        element: Browser element wrapper.

    Returns:
        Candidate text values.
    """
    attrs = getattr(element, "attrs", {}) or {}
    return [
        getattr(element, "text_all", "") or "",
        attrs.get("value", "") or "",
        attrs.get("aria-label", "") or "",
        attrs.get("title", "") or "",
        attrs.get("name", "") or "",
    ]


async def click_browser_element(element) -> bool:
    """Click a browser element using the safest available fallback.

    Args:
        element: Browser element wrapper.

    Returns:
        ``True`` when the click succeeds.
    """
    try:
        await element.click()
        return True
    except Exception as error:
        message = str(error).lower()
        if "cannot find context with specified id" in message or "execution context was destroyed" in message:
            return True
        try:
            await element.mouse_click()
            return True
        except Exception as mouse_error:
            mouse_message = str(mouse_error).lower()
            if "cannot find context with specified id" in mouse_message or "execution context was destroyed" in mouse_message:
                return True
            return False


async def clear_consent_overlays(page) -> int:
    """Remove consent-related overlays and restore page scrolling.

    Args:
        page: Browser page/tab.

    Returns:
        Number of removed nodes reported by the page script.
    """
    try:
        removed = await page.evaluate(build_overlay_removal_script(), return_by_value=True)
    except Exception:
        return 0
    try:
        return int(removed or 0)
    except (TypeError, ValueError):
        return 0


async def find_direct_consent_candidate(page, action: str):
    """Find the first consent candidate using direct CMP selectors.

    Args:
        page: Browser page/tab.
        action: Consent action name.

    Returns:
        Matching element and selector, or ``(None, None)``.
    """
    selectors = DIRECT_ACTION_SELECTORS.get(action, [])
    if not selectors:
        return None, None
    selector_query = ", ".join(selectors)
    try:
        elements = await page.select_all(selector_query, timeout=0.25, include_frames=True)
    except Exception:
        return None, None
    if elements:
        return elements[0], selector_query
    return None, None


async def find_generic_consent_candidate(page, action: str):
    """Find the best consent button candidate using text/context heuristics.

    Args:
        page: Browser page/tab.
        action: Consent action name.

    Returns:
        Matching element and visible label, or ``(None, None)``.
    """
    try:
        elements = await page.select_all(CANDIDATE_SELECTOR, timeout=0.25, include_frames=True)
    except Exception:
        return None, None
    scored = []
    for element in elements:
        attrs = getattr(element, "attrs", {}) or {}
        labels = [label for label in get_element_text_candidates(element) if label]
        if not labels:
            continue
        label = max(labels, key=len)
        context_text = build_consent_context_text(label, attrs)
        score = score_consent_label(label, action)
        if score <= 0:
            continue
        if not is_consent_context(context_text) and score < 100:
            continue
        scored.append((score, len(label), element, label))

    if not scored:
        return None, None
    scored.sort(key=lambda item: (item[0], -item[1]), reverse=True)
    _, _, element, label = scored[0]
    return element, label


async def handle_consent_dialogs(
    page,
    consent_mode: str = "none",
    max_actions: int = 2,
    delay_ms: int = 700,
) -> list[dict]:
    """Dismiss or interact with cookie/consent dialogs and overlays.

    Args:
        page: Browser page/tab.
        consent_mode: Consent handling mode.
        max_actions: Maximum number of click/removal actions to perform.
        delay_ms: Delay between actions in milliseconds.

    Returns:
        List of performed consent/overlay actions.
    """
    actions = []
    if consent_mode == "none":
        return actions

    try:
        removed = await clear_consent_overlays(page)
        if removed:
            actions.append({"action": "remove_overlay", "removed": removed, "strategy": "dom"})
            if len(actions) >= max_actions:
                return actions

        for action in get_action_sequence(consent_mode):
            if len(actions) >= max_actions:
                break

            try:
                element, selector = await find_direct_consent_candidate(page, action)
                label = None
                strategy = "selector"
                if element is None:
                    element, label = await find_generic_consent_candidate(page, action)
                    strategy = "text"
                if element is None:
                    continue

                if label is None:
                    labels = [value for value in get_element_text_candidates(element) if value]
                    label = max(labels, key=len) if labels else action

                clicked = await click_browser_element(element)
                if not clicked:
                    continue
                actions.append(
                    {
                        "action": action,
                        "label": label,
                        "strategy": strategy,
                        "selector": selector,
                    }
                )
                await page.sleep(delay_ms / 1000)

                removed = await clear_consent_overlays(page)
                if removed and len(actions) < max_actions:
                    actions.append({"action": "remove_overlay", "removed": removed, "strategy": "dom"})
                if action != "settings":
                    break
            except Exception:
                continue
    except Exception:
        return actions[:max_actions]

    return actions[:max_actions]


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
