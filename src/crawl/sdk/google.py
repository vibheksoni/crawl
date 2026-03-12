"""Google result parsing helpers."""

from bs4.element import Tag


def is_external_url(href: str) -> bool:
    """Check whether a Google result href points to an external destination.

    Args:
        href: Link URL to inspect.

    Returns:
        ``True`` when the href appears to be an external result URL.
    """
    if not href or href.startswith("#") or href.startswith("/"):
        return False
    blocked = [
        "/search?",
        "google.com/search",
        "webcache",
        "translate.google",
        "accounts.google",
        "support.google",
        "maps.google",
    ]
    return not any(value in href for value in blocked)


def find_container(link: Tag, max_depth: int = 8):
    """Walk up from a link element to locate its enclosing result container.

    Args:
        link: Link element inside a search result.
        max_depth: Maximum number of parent hops.

    Returns:
        The most likely result container element.
    """
    node = link
    for _ in range(max_depth):
        if not node.parent:
            break
        node = node.parent
        children = len(list(node.children))
        if children > 4:
            return node
    return link.parent


def extract_description(link: Tag) -> str:
    """Extract a result description by scanning parent containers.

    Args:
        link: Result heading link element.

    Returns:
        Description text when found.
    """
    node = link
    href = link.get("href", "")
    for _ in range(8):
        if not node.parent:
            break
        node = node.parent
        div_children = [child for child in node.children if hasattr(child, "name") and child.name == "div"]
        if len(div_children) >= 2:
            for div_child in div_children:
                if not div_child.find("a", href=href):
                    text = div_child.get_text(strip=True)
                    if len(text) > 10:
                        return text
            break
    return ""


def extract_sitelinks(link: Tag) -> list:
    """Extract sitelinks associated with a result.

    Args:
        link: Result heading link element.

    Returns:
        List of sitelink dictionaries.
    """
    sitelinks = []
    node = link
    for _ in range(10):
        if not node.parent:
            break
        node = node.parent
        table = node.find("table", attrs={"role": "group"})
        if table:
            for sitelink in table.find_all("a", href=True):
                href = sitelink["href"]
                title = sitelink.get_text(strip=True)
                if title and is_external_url(href):
                    sitelinks.append({"title": title, "link": href})
            break
    return sitelinks


def extract_organic_results(soup, max_results: int) -> list:
    """Extract organic Google results from parsed HTML.

    Args:
        soup: BeautifulSoup parsed HTML tree.
        max_results: Maximum number of results to return.

    Returns:
        List of result dictionaries.
    """
    results = []
    seen_urls = set()

    for link in soup.find_all("a", href=True):
        if len(results) >= max_results:
            break

        href = link.get("href", "")
        if not is_external_url(href):
            continue
        if href in seen_urls:
            continue

        heading = link.find(["h3", "h2", "h1"])
        if not heading:
            continue

        title = heading.get_text(strip=True)
        if not title or len(title) < 3:
            continue

        container = find_container(link)
        cite = container.find("cite")
        displayed_url = cite.get_text(strip=True) if cite else ""
        description = extract_description(link)
        sitelinks = extract_sitelinks(link)

        seen_urls.add(href)
        result = {
            "type": "organic",
            "title": title,
            "link": href,
            "displayed_url": displayed_url,
            "description": description,
        }
        if sitelinks:
            result["sitelinks"] = sitelinks
        results.append(result)

    return results


def extract_video_results(soup) -> list:
    """Extract YouTube and Vimeo search results.

    Args:
        soup: BeautifulSoup parsed HTML tree.

    Returns:
        List of video result dictionaries.
    """
    results = []
    seen_urls = set()

    for link in soup.find_all("a", href=True):
        href = link.get("href", "")
        if "youtube.com/watch" not in href and "vimeo.com" not in href:
            continue
        if "&t=" in href:
            continue
        if href in seen_urls:
            continue

        heading = link.find(["h3", "h2", "h1"])
        title = heading.get_text(strip=True) if heading else ""
        if not title or len(title) < 5:
            continue

        container = find_container(link)
        channel = ""
        date = ""
        for span in container.find_all("span"):
            text = span.get_text(strip=True)
            if not span.find("span") and 3 < len(text) < 60:
                if any(month in text for month in ["Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"]):
                    date = text
                elif not channel and text != title and "youtube" not in text.lower():
                    channel = text

        seen_urls.add(href)
        results.append(
            {
                "type": "video",
                "title": title,
                "link": href,
                "channel": channel,
                "date": date,
            }
        )

    return results


def extract_people_also_ask(soup) -> list:
    """Extract People Also Ask questions from a Google result page.

    Args:
        soup: BeautifulSoup parsed HTML tree.

    Returns:
        List of question strings.
    """
    questions = []
    for div in soup.find_all(attrs={"role": "heading"}):
        text = div.get_text(strip=True)
        if "People also ask" in text:
            parent = div.parent
            for _ in range(3):
                if parent.parent:
                    parent = parent.parent
            for span in parent.find_all("span"):
                question = span.get_text(strip=True)
                if not span.find("span") and 10 < len(question) < 150 and question.endswith("?"):
                    if question not in questions:
                        questions.append(question)
            break
    return questions


def extract_ai_overview(soup) -> str:
    """Extract AI Overview text from a Google result page.

    Args:
        soup: BeautifulSoup parsed HTML tree.

    Returns:
        AI Overview text or an empty string.
    """
    skip_phrases = [
        "An AI Overview is not available",
        "Can't generate an AI overview",
        "Try again later",
    ]
    cut_markers = [
        "Show all",
        "Dive deeper in AI Mode",
        "AI responses may include",
        "My Ad Center",
        "Share more feedback",
        "Report a problem",
        "Your feedback helps",
        "Positive feedback",
        "Negative feedback",
    ]

    for element in soup.find_all(["h1", "div"]):
        if element.get_text(strip=True) != "AI Overview":
            continue

        parent = element.parent
        for _ in range(3):
            if parent.parent:
                parent = parent.parent

        full_text = parent.get_text(separator="\n", strip=True)
        lines = full_text.split("\n")
        clean_lines = []
        for line in lines:
            line = line.strip()
            if not line or line == "AI Overview":
                continue
            if any(phrase in line for phrase in skip_phrases):
                continue
            clean_lines.append(line)

        result = "\n".join(clean_lines)
        for marker in cut_markers:
            index = result.find(marker)
            if index > 0:
                result = result[:index]

        result = result.strip()
        if len(result) > 50:
            return result
        break

    return ""
