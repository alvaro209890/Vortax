"""Extract RSS/Atom entries with dates instead of sending raw XML to the model."""
import html
import re
import xml.etree.ElementTree as ET


def feed_entries(raw: str, limit: int = 10) -> list[dict]:
    try:
        root = ET.fromstring(raw)
    except ET.ParseError:
        return []
    entries = root.findall(".//item") or root.findall(".//{http://www.w3.org/2005/Atom}entry")
    rows = []
    for item in entries[:limit]:
        def value(tag):
            return item.findtext(tag) or item.findtext("{http://www.w3.org/2005/Atom}" + tag) or ""
        link = value("link")
        if not link:
            node = item.find("{http://www.w3.org/2005/Atom}link")
            link = node.get("href", "") if node is not None else ""
        if not link.startswith(("http://", "https://")):
            continue
        description = html.unescape(re.sub(r"<[^>]+>", " ", value("description") or value("summary")))
        date = value("pubDate") or value("published") or value("updated")
        source = item.find("source")
        rows.append({"index": len(rows)+1, "title": html.unescape(value("title"))[:240],
                     "href": link, "snippet": (date + " · " + re.sub(r"\s+", " ", description))[:900], "published": date,
                     "publisher_url": source.get("url", "") if source is not None else ""})
    return rows


def feed_text(rows: list[dict]) -> str:
    return "\n\n".join(f"{r['title']}\nPublicado: {r['published']}\nFonte: {r['href']}\n{r['snippet']}" for r in rows)
