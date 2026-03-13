"""Deterministic structured extraction helpers."""

from urllib.parse import urljoin

from bs4 import BeautifulSoup


def extract_field_value(scope, field: dict, page_url: str):
    """Extract a single field value from a scoped HTML node.

    Args:
        scope: BeautifulSoup scope element.
        field: Field extraction specification.
        page_url: Page URL for absolute-link resolution.

    Returns:
        Extracted value.
    """
    selector = field.get("selector")
    kind = field.get("type", "text")
    attribute = field.get("attribute")

    if kind == "constant":
        return field.get("value")

    if kind == "list_text":
        if not selector:
            return []
        return [item.get_text(" ", strip=True) for item in scope.select(selector) if item.get_text(" ", strip=True)]

    if kind == "list_attr":
        if not selector or not attribute:
            return []
        values = []
        for item in scope.select(selector):
            value = item.get(attribute)
            if value:
                values.append(urljoin(page_url, value) if field.get("absolute") else value)
        return values

    target = scope.select_one(selector) if selector else scope
    if target is None:
        return None

    if kind == "html":
        return str(target)
    if kind == "attribute":
        value = target.get(attribute) if attribute else None
        if value and field.get("absolute"):
            return urljoin(page_url, value)
        return value
    if kind == "exists":
        return True

    return target.get_text(" ", strip=True)


def extract_structured_data(html: str, page_url: str, schema: dict) -> dict | list[dict]:
    """Extract structured data from HTML using a CSS-selector schema.

    Args:
        html: Raw HTML content.
        page_url: Page URL for absolute-link resolution.
        schema: Extraction schema.

    Returns:
        Extracted object or list of objects.
    """
    soup = BeautifulSoup(html, "html.parser")
    base_selector = schema.get("baseSelector")
    fields = schema.get("fields", [])
    multiple = bool(base_selector) or schema.get("multiple", False)

    def build_item(scope) -> dict:
        item = {}
        for field in fields:
            name = field["name"]
            item[name] = extract_field_value(scope, field, page_url)
        return item

    if multiple:
        scopes = soup.select(base_selector) if base_selector else [soup]
        return [build_item(scope) for scope in scopes]

    return build_item(soup)
