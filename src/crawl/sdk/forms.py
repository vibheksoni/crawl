"""Form extraction and fill helpers."""

from urllib.parse import urlencode, urljoin

from bs4 import BeautifulSoup


def normalize_form_method(method: str | None) -> str:
    """Normalize an HTML form method.

    Args:
        method: Raw method value.

    Returns:
        Uppercase HTTP method.
    """
    return (method or "GET").strip().upper() or "GET"


def normalize_form_action(action: str | None, page_url: str) -> str:
    """Normalize a form action against the page URL.

    Args:
        action: Raw action attribute.
        page_url: Page URL.

    Returns:
        Absolute action URL.
    """
    if not action:
        return page_url
    return urljoin(page_url, action)


def extract_form_fields(form) -> list[dict]:
    """Extract form fields from a form element.

    Args:
        form: BeautifulSoup form element.

    Returns:
        Field payload list.
    """
    fields = []
    for element in form.find_all(["input", "textarea", "select", "button"]):
        tag_name = element.name or ""
        field_type = element.get("type", "text") if tag_name == "input" else tag_name
        name = element.get("name") or element.get("id") or ""
        value = element.get("value", "")
        options = []

        if tag_name == "select":
            for option in element.find_all("option"):
                option_value = option.get("value", option.get_text(" ", strip=True))
                options.append(option_value)

        fields.append(
            {
                "tag": tag_name,
                "type": field_type,
                "name": name,
                "id": element.get("id", ""),
                "placeholder": element.get("placeholder", ""),
                "required": element.has_attr("required"),
                "value": value,
                "options": options,
            }
        )
    return fields


def suggest_field_value(field: dict) -> str:
    """Suggest a safe filler value for a form field.

    Args:
        field: Field payload.

    Returns:
        Suggested field value.
    """
    name = (field.get("name") or "").lower()
    field_type = (field.get("type") or "").lower()
    placeholder = (field.get("placeholder") or "").lower()
    combined = f"{name} {placeholder}"

    if field_type in {"hidden", "submit", "button", "reset", "image"}:
        return field.get("value", "")
    if field_type in {"checkbox", "radio"}:
        return field.get("value", "on") or "on"
    if field_type == "email" or "email" in combined:
        return "crawl@example.com"
    if field_type == "password" or "password" in combined:
        return "crawlP@ssw0rd!"
    if field_type in {"number", "range"} or "number" in combined:
        return "1"
    if field_type == "tel" or "phone" in combined or "telephone" in combined:
        return "5551234567"
    if "date" in combined:
        return "2026-03-13"
    if "url" in combined or "website" in combined:
        return "https://example.com"
    if "search" in combined:
        return "crawl"
    if field.get("options"):
        return field["options"][0]
    return "crawl"


def build_form_submission_preview(form: dict) -> dict:
    """Build a safe submission preview for a form.

    Args:
        form: Extracted form payload.

    Returns:
        Submission preview with suggested values.
    """
    values = {}
    for field in form.get("fields", []):
        field_name = field.get("name")
        if not field_name:
            continue
        suggested = suggest_field_value(field)
        if suggested != "":
            values[field_name] = suggested

    method = form["method"]
    action = form["action"]
    if method == "GET":
        query = urlencode(values, doseq=True)
        preview_url = f"{action}?{query}" if query else action
    else:
        preview_url = action

    return {
        "method": method,
        "action": action,
        "values": values,
        "preview_url": preview_url,
        "body": "" if method == "GET" else urlencode(values, doseq=True),
    }


def extract_forms(html: str, page_url: str, include_fill_suggestions: bool = False) -> list[dict]:
    """Extract forms from HTML.

    Args:
        html: Raw HTML content.
        page_url: Page URL.
        include_fill_suggestions: Whether to attach fill previews.

    Returns:
        Form payload list.
    """
    soup = BeautifulSoup(html, "html.parser")
    forms = []

    for index, form in enumerate(soup.find_all("form")):
        payload = {
            "index": index,
            "action": normalize_form_action(form.get("action"), page_url),
            "method": normalize_form_method(form.get("method")),
            "enctype": form.get("enctype", "application/x-www-form-urlencoded"),
            "fields": extract_form_fields(form),
        }
        if include_fill_suggestions:
            payload["fill_preview"] = build_form_submission_preview(payload)
        forms.append(payload)

    return forms
