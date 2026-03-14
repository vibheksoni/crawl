"""Consent banner and overlay handling helpers."""

import re

CONSENT_CONTEXT_RE = re.compile(r"cookie|consent|gdpr|privacy|notice|banner|modal|dialog|overlay|cmp", re.I)
CANDIDATE_SELECTOR = "button, a, [role='button'], input[type='button'], input[type='submit']"
DIRECT_ACTION_SELECTORS = {
    "reject": [
        "#onetrust-reject-all-handler",
        "#CybotCookiebotDialogBodyButtonDecline",
        "#didomi-notice-disagree-button",
        ".cky-btn-reject",
        "[data-cky-tag='reject-button']",
        "#cn-refuse-cookie",
        ".cn-refuse-cookie",
        ".osano-cm-deny",
        "button.osano-cm-deny-all",
        ".klaro .cm-btn-decline",
        ".iubenda-cs-reject-btn",
        "[data-testid='uc-deny-all-button']",
        "#uc-btn-deny-banner",
        ".fc-cta-do-not-consent",
        "[data-fc-action='reject']",
    ],
    "accept": [
        "#onetrust-accept-btn-handler",
        "#CybotCookiebotDialogBodyLevelButtonAccept",
        "#CybotCookiebotDialogBodyLevelButtonLevelOptinAllowAll",
        ".didomi-continue-without-agreeing",
        ".fc-cta-consent",
        ".osano-cm-accept-all",
        "[data-testid='uc-accept-all-button']",
        "#uc-btn-accept-banner",
        "[data-cookiefirst-action='accept']",
        "[data-cky-tag='accept-button']",
        ".cmplz-accept",
        "#cookiescript_accept",
        "#ccc-notify-accept",
        ".cookie-notice .cm-btn-success",
    ],
    "settings": [
        "#onetrust-pc-btn-handler",
        ".fc-button-label",
        "[data-testid='uc-manage-button']",
        "[data-testid='manage-preferences']",
        "#didomi-notice-learn-more-button",
        ".cmplz-manage-options",
        ".cookie-settings",
        ".manage-cookies",
    ],
    "close": [
        ".onetrust-close-btn-handler",
        "[aria-label*='close' i]",
        "[data-testid='close']",
        ".cookie-close",
        ".consent-close",
    ],
}
DIRECT_OVERLAY_SELECTORS = [
    "#onetrust-banner-sdk",
    "#CybotCookiebotDialog",
    "#didomi-host",
    ".osano-cm-dialog",
    ".fc-dialog-container",
    ".qc-cmp2-container",
    "[class*='cookie-banner']",
    "[class*='cookie-consent']",
    "[class*='consent-banner']",
    "[id*='cookie-banner']",
    "[id*='cookie-consent']",
    "[role='dialog'][class*='cookie' i]",
    "[role='dialog'][class*='consent' i]",
]
ACTION_PATTERNS = {
    "reject": [
        re.compile(pattern, re.I)
        for pattern in (
            r"^reject(\s+all)?$",
            r"^decline(\s+all)?$",
            r"^refuse(\s+all)?$",
            r"^deny(\s+all)?$",
            r"^disagree(\s+to\s+all)?$",
            r"^use\s+(necessary|essential)\s+cookies?\s+only$",
            r"^(do\s+)?not\s+(accept|allow|consent)$",
            r"^continue\s+without\s+(agreeing|accepting)$",
            r"^reject\s+all\s+and\s+close$",
            r"^ablehnen$",
            r"^alle\s+ablehnen$",
            r"^tout\s+refuser$",
            r"^refuser$",
            r"^rechazar$",
            r"^rechazar\s+todo$",
            r"^rifiuta$",
            r"^alles\s+afwijzen$",
        )
    ],
    "accept": [
        re.compile(pattern, re.I)
        for pattern in (
            r"^accept(\s+all)?$",
            r"^agree$",
            r"^allow(\s+all)?$",
            r"^consent$",
            r"^got\s+it$",
            r"^ok$",
            r"^i\s+agree$",
            r"^akzeptieren$",
            r"^alle\s+akzeptieren$",
            r"^tout\s+accepter$",
            r"^aceptar$",
            r"^aceptar\s+todo$",
            r"^accetta$",
        )
    ],
    "settings": [
        re.compile(pattern, re.I)
        for pattern in (
            r"^cookie\s*(settings|preferences|options)$",
            r"^manage\s*(cookies?|preferences|settings|options)$",
            r"^privacy\s*(settings|choices|preferences)$",
            r"^customi[sz]e$",
            r"^configure$",
            r"^more\s+options$",
        )
    ],
    "close": [
        re.compile(pattern, re.I)
        for pattern in (
            r"^close$",
            r"^dismiss$",
            r"^skip$",
            r"^continue$",
        )
    ],
}
ACTION_ORDER = {
    "auto": ["reject", "accept", "close"],
    "reject": ["reject", "settings", "reject", "close"],
    "accept": ["accept", "settings", "accept", "close"],
    "close": ["close"],
    "settings": ["settings"],
    "none": [],
}


def normalize_consent_text(value: str) -> str:
    """Normalize consent button text for comparison.

    Args:
        value: Raw button or context text.

    Returns:
        Normalized label.
    """
    return re.sub(r"\s+", " ", value or "").strip().lower()


def build_consent_context_text(label: str, attrs: dict | None = None) -> str:
    """Build context text from a candidate label and element attributes.

    Args:
        label: Visible candidate label.
        attrs: Optional attribute mapping.

    Returns:
        Combined normalized context text.
    """
    attrs = attrs or {}
    context = " ".join(
        [
            label,
            str(attrs.get("id", "")),
            str(attrs.get("class", "")),
            str(attrs.get("aria-label", "")),
            str(attrs.get("title", "")),
        ]
    )
    return normalize_consent_text(context)


def is_consent_context(text: str) -> bool:
    """Check whether text looks related to consent or overlays.

    Args:
        text: Candidate context text.

    Returns:
        ``True`` when the text looks consent-related.
    """
    return bool(CONSENT_CONTEXT_RE.search(text or ""))


def score_consent_label(label: str, action: str) -> float:
    """Score a candidate label for a consent action.

    Args:
        label: Visible candidate label.
        action: Target action.

    Returns:
        Score for the action match.
    """
    normalized = normalize_consent_text(label)
    if not normalized:
        return 0.0
    score = 0.0
    for pattern in ACTION_PATTERNS.get(action, []):
        if pattern.search(normalized):
            score += 100.0
    if action == "reject" and "all" in normalized:
        score += 20.0
    if action == "accept" and "all" in normalized:
        score += 10.0
    if len(normalized) > 80:
        score -= 15.0
    return score


def get_action_sequence(mode: str) -> list[str]:
    """Resolve the ordered consent actions for a mode.

    Args:
        mode: Consent mode.

    Returns:
        Ordered action list.
    """
    return ACTION_ORDER.get(mode, ACTION_ORDER["none"])


def build_overlay_removal_script() -> str:
    """Build the DOM cleanup script used to remove stubborn overlays.

    Returns:
        JavaScript snippet that removes known consent overlays and restores scrolling.
    """
    selectors_json = json_list_literal(DIRECT_OVERLAY_SELECTORS)
    return f"""
(() => {{
  const selectors = {selectors_json};
  let removed = 0;
  for (const selector of selectors) {{
    for (const node of document.querySelectorAll(selector)) {{
      try {{
        node.remove();
        removed += 1;
      }} catch (_) {{}}
    }}
  }}
  for (const node of document.querySelectorAll('body, html')) {{
    try {{
      node.style.overflow = 'auto';
      node.style.position = '';
      node.style.pointerEvents = 'auto';
    }} catch (_) {{}}
  }}
  for (const node of Array.from(document.querySelectorAll('*'))) {{
    try {{
      const style = window.getComputedStyle(node);
      const text = ((node.textContent || '') + ' ' + (node.id || '') + ' ' + (node.className || '')).toLowerCase();
      if ((style.position === 'fixed' || style.position === 'sticky') &&
          Number.parseInt(style.zIndex || '0', 10) >= 1000 &&
          /cookie|consent|privacy|gdpr|overlay|modal|notice/.test(text)) {{
        node.remove();
        removed += 1;
      }}
    }} catch (_) {{}}
  }}
  return removed;
}})()
"""


def json_list_literal(values: list[str]) -> str:
    """Render a Python string list into a JavaScript array literal.

    Args:
        values: String list.

    Returns:
        JavaScript array literal string.
    """
    escaped = [value.replace("\\", "\\\\").replace("'", "\\'") for value in values]
    return "[" + ", ".join(f"'{value}'" for value in escaped) + "]"
