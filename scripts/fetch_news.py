"""
Step 1: Fetch monitoring signals from both NewsAPI and official regulator sources.

The pipeline now treats official regulator / government pages as first-class inputs,
with news coverage as a second signal rather than the only discovery channel.
"""

from __future__ import annotations

import re
import requests
import xml.etree.ElementTree as ET
from datetime import datetime, timezone
from difflib import SequenceMatcher
from email.utils import parsedate_to_datetime
from html.parser import HTMLParser
from urllib.parse import urljoin, urlparse

from config import (
    NEWS_API_KEY,
    OPENAI_API_KEY,
    NEWS_API_BASE,
    NEWS_PAGE_SIZE,
    NEWS_KEYWORD_SETS,
    OFFICIAL_SOURCE_LIMIT,
    OFFICIAL_SOURCE_LINK_LIMIT,
    OFFICIAL_SOURCE_MIN_CANDIDATE_SCORE,
    SEEN_URLS_FILE,
    TRUSTED_NEWS_SOURCES,
    load_json,
    now_iso,
)
from source_registry import MonitoringSource, load_monitoring_sources


REQUEST_HEADERS = {
    "User-Agent": "GlobalTrustSafetyDashboardBot/1.0 (+https://github.com/patriciayyzhai/global-trust-safety-dashboard)"
}
DISCOVERY_KEYWORDS = (
    "age",
    "child",
    "children",
    "minor",
    "youth",
    "safety",
    "online",
    "platform",
    "social",
    "digital",
    "verification",
    "assurance",
    "regulat",
    "law",
    "bill",
    "act",
    "enforcement",
    "guidance",
    "consult",
    "media",
    "news",
    "press",
)
ARTICLE_PATH_HINTS = (
    "/news/",
    "/press/",
    "/media/",
    "/announcement",
    "/announcements/",
    "/consult",
    "/guidance",
    "/bill",
    "/legislation",
    "/services/",
)
GENERIC_TITLE_PATTERNS = (
    "newsroom",
    "media centre",
    "press corner",
    "updates",
    "announcements",
    "news / media",
    "photo gallery",
    "e-newsletter",
)
IGNORED_SUFFIXES = (
    ".jpg",
    ".jpeg",
    ".png",
    ".gif",
    ".svg",
    ".webp",
    ".zip",
    ".css",
    ".js",
    ".json",
)
META_DATE_PATTERNS = (
    r'property=["\']article:published_time["\'][^>]*content=["\']([^"\']+)["\']',
    r'property=["\']article:modified_time["\'][^>]*content=["\']([^"\']+)["\']',
    r'name=["\']pubdate["\'][^>]*content=["\']([^"\']+)["\']',
    r'name=["\']date["\'][^>]*content=["\']([^"\']+)["\']',
    r'"datePublished"\s*:\s*"([^"]+)"',
    r'"dateModified"\s*:\s*"([^"]+)"',
)


class FetchNewsError(RuntimeError):
    """Base error for monitoring fetch failures."""


class FetchNewsRequestError(FetchNewsError):
    """Raised when all configured fetch channels fail."""


class DiscoveryPageParser(HTMLParser):
    """Lightweight HTML parser for titles, feeds, and candidate article links."""

    def __init__(self) -> None:
        super().__init__()
        self.title = ""
        self.meta_description = ""
        self.feed_links: list[str] = []
        self.links: list[dict[str, str]] = []
        self._in_title = False
        self._current_anchor_href = ""
        self._current_anchor_text: list[str] = []

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        attr_map = {k.lower(): (v or "") for k, v in attrs}
        if tag.lower() == "title":
            self._in_title = True
            return
        if tag.lower() == "meta":
            name = attr_map.get("name", "").lower()
            prop = attr_map.get("property", "").lower()
            if name == "description" or prop == "og:description":
                self.meta_description = attr_map.get("content", "").strip()
            return
        if tag.lower() == "link":
            rel = attr_map.get("rel", "").lower()
            href = attr_map.get("href", "").strip()
            content_type = attr_map.get("type", "").lower()
            if href and "alternate" in rel and ("rss" in content_type or "atom" in content_type or href.endswith(".xml")):
                self.feed_links.append(href)
            return
        if tag.lower() == "a":
            self._current_anchor_href = attr_map.get("href", "").strip()
            self._current_anchor_text = []

    def handle_endtag(self, tag: str) -> None:
        if tag.lower() == "title":
            self._in_title = False
            return
        if tag.lower() == "a" and self._current_anchor_href:
            text = " ".join(" ".join(self._current_anchor_text).split())
            self.links.append({"href": self._current_anchor_href, "text": text})
            self._current_anchor_href = ""
            self._current_anchor_text = []

    def handle_data(self, data: str) -> None:
        if self._in_title:
            self.title += data
        if self._current_anchor_href:
            self._current_anchor_text.append(data)


def normalize_url(url: str) -> str:
    """Normalize a URL for deduplication (strip trailing slash, lowercase)."""
    url = url.strip().lower()
    if url.endswith("/"):
        url = url[:-1]
    return url


def title_similarity(t1: str, t2: str) -> float:
    """Compute title similarity ratio (0-1)."""
    return SequenceMatcher(None, t1.lower(), t2.lower()).ratio()


def deduplicate(articles: list[dict], seen_urls: dict) -> list[dict]:
    """Deduplicate articles against seen URLs and within the current batch."""
    dedup_title_threshold = 0.85
    unique = []
    seen_titles = []

    for article in articles:
        url = article.get("url", "")
        title = article.get("title", "")

        if not url or not title:
            continue

        norm_url = normalize_url(url)
        if norm_url in seen_urls:
            continue

        if any(title_similarity(title, seen_title) > dedup_title_threshold for seen_title in seen_titles):
            continue

        seen_titles.append(title)
        unique.append(article)

    return unique


def build_article(
    *,
    title: str,
    url: str,
    source_name: str,
    description: str = "",
    published_at: str = "",
    monitoring_origin: str = "news_api",
) -> dict:
    """Build a unified article shape for downstream classification."""
    return {
        "title": title.strip(),
        "url": url.strip(),
        "description": description.strip(),
        "content": description.strip(),
        "publishedAt": published_at.strip(),
        "source": {
            "name": source_name,
            "kind": monitoring_origin,
        },
    }


def is_trusted_news_source(source_name: str) -> bool:
    """Restrict horizon scanning to reputable international news outlets."""
    source_name = (source_name or "").strip().lower()
    return any(candidate.lower() == source_name for candidate in TRUSTED_NEWS_SOURCES)


def fetch_news_for_keyword(keyword_set: str) -> list[dict]:
    """Fetch news articles from GNews search."""
    params = {
        "q": keyword_set,
        "lang": "en",
        "max": NEWS_PAGE_SIZE,
        "apikey": NEWS_API_KEY,
    }
    resp = requests.get(
        f"{NEWS_API_BASE}/search",
        params=params,
        timeout=30,
        headers=REQUEST_HEADERS,
    )
    resp.raise_for_status()
    data = resp.json()
    return data.get("articles", [])


def validate_news_api_key() -> None:
    """Check whether GNews is usable for this run."""
    key_len = len(NEWS_API_KEY) if NEWS_API_KEY else 0
    provider = "GNEWS_API_KEY" if NEWS_API_KEY else "GNEWS_API_KEY/NEWS_API_KEY"
    print(f"[fetch_news] {provider} present: {'YES' if key_len > 0 else 'NO'} (length={key_len})")
    print(f"[fetch_news] OPENAI_API_KEY present: {'YES' if OPENAI_API_KEY else 'NO'}")

    if not NEWS_API_KEY:
        print("[fetch_news] WARNING: GNEWS_API_KEY is not configured. Continuing with official sources only.")
        return

    print("[fetch_news] Validating key with GNews /search endpoint...")
    try:
        test_resp = requests.get(
            f"{NEWS_API_BASE}/search",
            params={"apikey": NEWS_API_KEY, "q": "technology", "lang": "en", "max": 1},
            timeout=15,
            headers=REQUEST_HEADERS,
        )
        if test_resp.status_code == 200:
            data = test_resp.json()
            print(f"[fetch_news] ✓ Key valid — search returned totalArticles={data.get('totalArticles', 0)}")
            return
        print(f"[fetch_news] WARNING: GNews returned HTTP {test_resp.status_code}; continuing with official sources.")
        try:
            print(f"[fetch_news] Response: {test_resp.text[:300]}")
        except Exception:
            pass
    except Exception as exc:
        print(f"[fetch_news] WARNING: Could not validate GNews ({type(exc).__name__}: {exc}). Continuing.")


def load_seen_urls() -> dict:
    """Load seen URL registry."""
    seen_data = load_json(SEEN_URLS_FILE) if SEEN_URLS_FILE.exists() else {
        "version": "1.0.0",
        "last_updated": now_iso(),
        "total_count": 0,
        "urls": {},
    }
    return seen_data.get("urls", {})


def fetch_response(url: str) -> requests.Response:
    """Fetch a URL with shared request settings."""
    response = requests.get(url, timeout=20, headers=REQUEST_HEADERS)
    response.raise_for_status()
    return response


def looks_like_feed(url: str, content_type: str, body: str) -> bool:
    """Heuristic to identify RSS/Atom responses."""
    content_type = (content_type or "").lower()
    return (
        "xml" in content_type
        or url.endswith(".xml")
        or body.lstrip().startswith("<?xml")
        or "<rss" in body[:500].lower()
        or "<feed" in body[:500].lower()
    )


def parse_timestamp(value: str) -> str:
    """Convert varied date strings into ISO 8601 when possible."""
    if not value:
        return ""
    raw = value.strip()
    try:
        dt = datetime.fromisoformat(raw.replace("Z", "+00:00"))
        return dt.astimezone(timezone.utc).isoformat()
    except ValueError:
        pass
    try:
        dt = parsedate_to_datetime(raw)
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
        return dt.astimezone(timezone.utc).isoformat()
    except Exception:
        return raw


def extract_published_at(body: str, headers: dict[str, str]) -> str:
    """Try to recover a published or modified timestamp from HTML or headers."""
    for pattern in META_DATE_PATTERNS:
        match = re.search(pattern, body, flags=re.IGNORECASE)
        if match:
            return parse_timestamp(match.group(1))
    last_modified = headers.get("Last-Modified") or headers.get("last-modified") or ""
    return parse_timestamp(last_modified)


def parse_feed_items(xml_text: str, source_name: str) -> list[dict]:
    """Parse RSS or Atom feed items into article records."""
    items: list[dict] = []
    try:
        root = ET.fromstring(xml_text)
    except ET.ParseError:
        return items

    for item in root.findall(".//item"):
        title = (item.findtext("title") or "").strip()
        link = (item.findtext("link") or "").strip()
        description = (item.findtext("description") or "").strip()
        published = parse_timestamp(item.findtext("pubDate") or "")
        if title and link:
            items.append(
                build_article(
                    title=title,
                    url=link,
                    description=description,
                    published_at=published,
                    source_name=source_name,
                    monitoring_origin="official_feed",
                )
            )

    atom_ns = {"atom": "http://www.w3.org/2005/Atom"}
    for entry in root.findall(".//atom:entry", atom_ns):
        title = (entry.findtext("atom:title", default="", namespaces=atom_ns) or "").strip()
        link = ""
        link_el = entry.find("atom:link", atom_ns)
        if link_el is not None:
            link = (link_el.attrib.get("href") or "").strip()
        description = (
            entry.findtext("atom:summary", default="", namespaces=atom_ns)
            or entry.findtext("atom:content", default="", namespaces=atom_ns)
            or ""
        ).strip()
        published = parse_timestamp(
            entry.findtext("atom:updated", default="", namespaces=atom_ns)
            or entry.findtext("atom:published", default="", namespaces=atom_ns)
            or ""
        )
        if title and link:
            items.append(
                build_article(
                    title=title,
                    url=link,
                    description=description,
                    published_at=published,
                    source_name=source_name,
                    monitoring_origin="official_feed",
                )
            )

    return items


def candidate_link_score(text: str, url: str) -> int:
    """Score candidate article links so regulator/news items rise to the top."""
    blob = f"{text} {url}".lower()
    score = sum(1 for keyword in DISCOVERY_KEYWORDS if keyword in blob)
    if any(token in blob for token in ARTICLE_PATH_HINTS):
        score += 3
    if re.search(r"/20\d{2}/|/20\d{2}-\d{2}-\d{2}/", blob):
        score += 2
    return score


def is_candidate_link(raw_href: str, base_host: str) -> bool:
    """Filter out off-topic or non-HTML candidate links."""
    href = (raw_href or "").strip()
    if not href or href.startswith("#") or href.startswith("mailto:") or href.startswith("javascript:"):
        return False
    parsed = urlparse(href)
    if parsed.scheme and parsed.scheme not in ("http", "https"):
        return False
    normalized = href.lower()
    if any(normalized.endswith(suffix) for suffix in IGNORED_SUFFIXES):
        return False
    if normalized.endswith(".pdf"):
        return True
    host = parsed.netloc.lower()
    if host and base_host not in host and host not in base_host:
        return False
    return True


def discover_feed_links(base_url: str, parser: DiscoveryPageParser) -> list[str]:
    """Resolve RSS / Atom alternate links from an HTML page."""
    urls = []
    seen = set()
    for href in parser.feed_links:
        absolute = urljoin(base_url, href)
        key = normalize_url(absolute)
        if key in seen:
            continue
        seen.add(key)
        urls.append(absolute)
    return urls


def discover_candidate_links(base_url: str, parser: DiscoveryPageParser) -> list[str]:
    """Resolve and rank candidate detail pages from an official source page."""
    base_host = urlparse(base_url).netloc.lower()
    scored: list[tuple[int, str]] = []
    seen = set()

    for link in parser.links:
        href = link.get("href", "")
        text = link.get("text", "")
        if not is_candidate_link(href, base_host):
            continue
        absolute = urljoin(base_url, href)
        key = normalize_url(absolute)
        if key in seen:
            continue
        seen.add(key)
        score = candidate_link_score(text, absolute)
        if score < OFFICIAL_SOURCE_MIN_CANDIDATE_SCORE:
            continue
        scored.append((score, absolute))

    scored.sort(key=lambda item: (-item[0], item[1]))
    return [url for _, url in scored[:OFFICIAL_SOURCE_LINK_LIMIT]]


def fetch_article_page(url: str, source_name: str, monitoring_origin: str) -> dict | None:
    """Fetch a detail page and convert it into an article-like record."""
    try:
        response = fetch_response(url)
    except Exception as exc:
        print(f"    [official] skipped {url} ({type(exc).__name__}: {exc})")
        return None

    content_type = response.headers.get("content-type", "")
    if "pdf" in content_type.lower() or url.lower().endswith(".pdf"):
        title = url.rsplit("/", 1)[-1] or source_name
        return build_article(
            title=title.replace("-", " "),
            url=url,
            description=f"Official PDF source from {source_name}",
            published_at=extract_published_at("", dict(response.headers)),
            source_name=source_name,
            monitoring_origin=monitoring_origin,
        )

    body = response.text
    parser = DiscoveryPageParser()
    parser.feed(body)
    title = " ".join(parser.title.split()) or source_name
    description = parser.meta_description or title
    published_at = extract_published_at(body, dict(response.headers))
    lowered_title = title.lower()
    lowered_description = description.lower()
    if any(pattern in lowered_title for pattern in GENERIC_TITLE_PATTERNS) and not any(
        keyword in lowered_description for keyword in DISCOVERY_KEYWORDS
    ):
        return None
    return build_article(
        title=title,
        url=url,
        description=description,
        published_at=published_at,
        source_name=source_name,
        monitoring_origin=monitoring_origin,
    )


def fetch_official_source_articles(seen_urls: dict) -> list[dict]:
    """Fetch candidate monitoring items from official regulator / government sources."""
    sources = load_monitoring_sources(limit=OFFICIAL_SOURCE_LIMIT)
    print(f"[fetch_news] Official source registry: {len(sources)} sources")
    articles: list[dict] = []
    request_failures = 0

    for source in sources:
        print(f"[fetch_news] Official source: {source.label} ({source.url})")
        try:
            response = fetch_response(source.url)
        except Exception as exc:
            request_failures += 1
            print(f"  → ERROR ({type(exc).__name__}): {exc}")
            continue

        body = response.text
        content_type = response.headers.get("content-type", "")

        if looks_like_feed(source.url, content_type, body):
            feed_items = parse_feed_items(body, source.label)
            print(f"  → feed items: {len(feed_items)}")
            articles.extend(feed_items)
            continue

        parser = DiscoveryPageParser()
        parser.feed(body)

        feed_links = discover_feed_links(source.url, parser)
        feed_loaded = False
        for feed_url in feed_links[:1]:
            try:
                feed_resp = fetch_response(feed_url)
                feed_items = parse_feed_items(feed_resp.text, source.label)
                print(f"  → feed discovered: {feed_url} ({len(feed_items)} items)")
                articles.extend(feed_items)
                feed_loaded = True
                break
            except Exception as exc:
                print(f"  → feed discovery failed ({type(exc).__name__}): {exc}")

        if feed_loaded:
            continue

        candidate_urls = discover_candidate_links(source.url, parser)
        print(f"  → candidate links: {len(candidate_urls)}")
        for candidate_url in candidate_urls:
            if normalize_url(candidate_url) in seen_urls:
                continue
            article = fetch_article_page(
                candidate_url,
                source_name=source.label,
                monitoring_origin="official_page",
            )
            if article:
                articles.append(article)

        if (
            source.emit_landing_page
            and not source.discovery_only
            and not candidate_urls
            and normalize_url(source.url) not in seen_urls
        ):
            page_article = fetch_article_page(
                source.url,
                source_name=source.label,
                monitoring_origin="official_landing_page",
            )
            if page_article:
                articles.append(page_article)

    if request_failures == len(sources) and sources:
        raise FetchNewsRequestError("Every official source request failed.")
    return articles


def fetch_newsapi_articles() -> list[dict]:
    """Fetch headline-based secondary signals from NewsAPI when configured."""
    if not NEWS_API_KEY:
        return []

    articles = []
    for keyword_set in NEWS_KEYWORD_SETS:
        print(f"[fetch_news] NewsAPI query: {keyword_set}")
        try:
            batch = fetch_news_for_keyword(keyword_set)
            trusted_batch = [
                article for article in batch
                if is_trusted_news_source(article.get("source", {}).get("name", ""))
            ]
            dropped = len(batch) - len(trusted_batch)
            if dropped:
                print(f"  → filtered out {dropped} non-priority news sources")
            articles.extend(trusted_batch)
            print(f"  → {len(trusted_batch)} trusted-source articles")
        except Exception as exc:
            print(f"  → WARNING ({type(exc).__name__}): {exc}")
            response = getattr(exc, "response", None)
            if response is not None:
                try:
                    print(f"  → API response: {response.text[:300]}")
                except Exception:
                    pass
    return articles


def run() -> list[dict]:
    """Main entry point: fetch and deduplicate monitoring articles."""
    validate_news_api_key()
    seen_urls = load_seen_urls()

    official_articles = fetch_official_source_articles(seen_urls)
    news_articles = fetch_newsapi_articles()
    all_articles = official_articles + news_articles

    print(f"[fetch_news] Official articles fetched: {len(official_articles)}")
    print(f"[fetch_news] NewsAPI articles fetched: {len(news_articles)}")
    print(f"[fetch_news] Total raw articles: {len(all_articles)}")

    unique_articles = deduplicate(all_articles, seen_urls)
    print(f"[fetch_news] After dedup: {len(unique_articles)}")
    if not unique_articles:
        print("[fetch_news] No new unique articles survived deduplication.")

    return unique_articles


if __name__ == "__main__":
    articles = run()
    print(f"\nFetched {len(articles)} unique articles for classification")
    for article in articles[:10]:
        source_name = article.get("source", {}).get("name", "Unknown")
        print(f"  - [{source_name}] {article['title'][:90]}")
