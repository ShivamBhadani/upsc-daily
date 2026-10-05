"""Current-affairs collection: RSS parsing plus best-effort full-text extraction.

Uses only the standard library XML parser plus requests/BeautifulSoup so no extra
feed dependency is needed.
"""

from __future__ import annotations

import re
import xml.etree.ElementTree as ET
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import date
from html import unescape
from typing import Callable

import requests
from bs4 import BeautifulSoup

from .config import Settings
from .models import Article

USER_AGENT = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/124.0 Safari/537.36"
)

NS = {
    "content": "http://purl.org/rss/1.0/modules/content/",
    "dc": "http://purl.org/dc/elements/1.1/",
    "atom": "http://www.w3.org/2005/Atom",
}

# Keyword map used to tag an article with a likely UPSC subject when the feed
# itself is a mixed one.
SUBJECT_HINTS: dict[str, tuple[str, ...]] = {
    "Polity & Governance": (
        "supreme court", "high court", "constitution", "parliament", "lok sabha",
        "rajya sabha", "bill", "ordinance", "article 3", "governor", "election commission",
        "cag", "judiciary", "federal", "panchayat", "amendment", "tribunal", "cbi",
    ),
    "Economy": (
        "rbi", "inflation", "gdp", "repo", "fiscal", "tax", "gst", "export", "import",
        "trade", "budget", "sebi", "rupee", "bond", "monetary", "npa", "msme", "fdi",
        "current account", "subsidy", "wpi", "cpi",
    ),
    "Environment & Ecology": (
        "climate", "emission", "biodiversity", "tiger", "wetland", "forest", "wildlife",
        "pollution", "unfccc", "cop", "ramsar", "carbon", "species", "sanctuary",
        "mangrove", "renewable", "solar", "biosphere", "ozone", "iucn",
    ),
    "Science & Technology": (
        "isro", "satellite", "vaccine", "drdo", "quantum", "semiconductor", "artificial intelligence",
        "genome", "crispr", "missile", "space", "nuclear", "telescope", "biotech",
        "5g", "6g", "cyber", "drone", "chandrayaan", "gaganyaan",
    ),
    "International Relations": (
        "bilateral", "summit", "united nations", "brics", "g20", "quad", "asean",
        "treaty", "diplomat", "wto", "imf", "world bank", "nato", "sco", "visit to",
        "foreign minister", "border", "indo-pacific",
    ),
    "Geography": (
        "monsoon", "cyclone", "earthquake", "river", "glacier", "volcan", "drought",
        "heatwave", "el nino", "la nina", "landslide", "strait", "plateau", "delta",
    ),
    "History, Art & Culture": (
        "heritage", "unesco", "temple", "dynasty", "archaeolog", "manuscript", "festival",
        "freedom struggle", "birth anniversary", "monument", "asi", "classical dance",
    ),
    "Social Issues & Schemes": (
        "scheme", "yojana", "mission", "welfare", "health", "education", "nep",
        "census", "poverty", "tribal", "women", "child", "malnutrition", "employment",
        "reservation", "disability", "ayushman",
    ),
}


def classify(text: str, fallback: str = "Mixed") -> str:
    """Tag text with the UPSC subject whose keywords appear most often."""
    low = text.lower()
    best, best_score = fallback, 0
    for subject, words in SUBJECT_HINTS.items():
        score = sum(1 for w in words if w in low)
        if score > best_score:
            best, best_score = subject, score
    return best if best_score else fallback


def _is_web_url(url: str) -> bool:
    """Accept only ordinary web links, and none carrying HTML metacharacters.

    A feed is third-party input: the link ends up in an href in the published
    paper, so a URL bearing quotes or angle brackets never enters the database.
    """
    if not url.lower().startswith(("http://", "https://")):
        return False
    return not any(c in url for c in "\"'<>` ")


def _clean(html: str) -> str:
    if not html:
        return ""
    text = BeautifulSoup(unescape(html), "html.parser").get_text(" ", strip=True)
    return re.sub(r"\s+", " ", text).strip()


def _first(elem: ET.Element, *paths: str) -> str:
    for p in paths:
        node = elem.find(p, NS)
        if node is not None:
            if node.text:
                return node.text
            href = node.get("href")
            if href:
                return href
    return ""


def parse_feed(xml_text: str, feed_name: str, feed_subject: str, limit: int) -> list[Article]:
    """Parse an RSS 2.0 or Atom document into Article objects."""
    try:
        root = ET.fromstring(xml_text.encode("utf-8", "ignore"))
    except ET.ParseError:
        return []

    items = root.findall(".//item") or root.findall(".//atom:entry", NS)
    out: list[Article] = []
    for item in items[:limit]:
        title = _clean(_first(item, "title", "atom:title"))
        url = _first(item, "link", "atom:link", "guid").strip()
        if not title or not _is_web_url(url):
            continue
        summary = _clean(
            _first(item, "description", "content:encoded", "atom:summary", "atom:content")
        )
        published = _clean(_first(item, "pubDate", "dc:date", "atom:updated", "atom:published"))
        subject = feed_subject if feed_subject != "Mixed" else classify(f"{title} {summary}")
        out.append(
            Article(title=title, url=url, source=feed_name, published=published,
                    summary=summary, subject=subject)
        )
    return out


def fetch_body(url: str, timeout: int = 20) -> str:
    """Pull the readable paragraph text of an article page."""
    try:
        resp = requests.get(url, headers={"User-Agent": USER_AGENT}, timeout=timeout)
        resp.raise_for_status()
    except requests.RequestException:
        return ""

    soup = BeautifulSoup(resp.text, "html.parser")
    for tag in soup(["script", "style", "nav", "header", "footer", "aside", "form", "figure"]):
        tag.decompose()

    container = (
        soup.find("article")
        or soup.find(attrs={"itemprop": "articleBody"})
        or soup.find(class_=re.compile(r"(articlebodycontent|story[-_]?(body|content|details)|entry-content)", re.I))
        or soup
    )
    paras = [p.get_text(" ", strip=True) for p in container.find_all("p")]
    paras = [p for p in paras if len(p) > 60]
    return re.sub(r"\s+", " ", " ".join(paras))[:8000]


def _safe(progress: Callable[[str, int], None] | None) -> Callable[[str, int], None] | None:
    """Wrap a progress callback so a reporting failure cannot abort the collection."""
    if progress is None:
        return None

    def report(message: str, pct: int) -> None:
        try:
            progress(message, pct)
        except Exception:  # noqa: BLE001 - progress reporting is never worth a crash
            pass

    return report


class Collector:
    """Fetches every configured feed, optionally enriching items with full text."""

    def __init__(self, settings: Settings) -> None:
        self.settings = settings
        self.session = requests.Session()
        self.session.headers.update({"User-Agent": USER_AGENT})

    def collect(self, progress: Callable[[str, int], None] | None = None) -> list[Article]:
        progress = _safe(progress)
        feeds = self.settings.feeds
        articles: list[Article] = []
        total = max(len(feeds), 1)

        def grab(feed: dict[str, str]) -> list[Article]:
            try:
                r = self.session.get(feed["url"], timeout=self.settings.request_timeout)
                r.raise_for_status()
            except requests.RequestException:
                return []
            return parse_feed(
                r.text, feed.get("name", feed["url"]),
                feed.get("subject", "Mixed"), self.settings.articles_per_feed,
            )

        done = 0
        with ThreadPoolExecutor(max_workers=8) as pool:
            futures = {pool.submit(grab, f): f for f in feeds}
            for fut in as_completed(futures):
                feed = futures[fut]
                done += 1
                got = fut.result()
                articles.extend(got)
                if progress:
                    progress(f"{feed.get('name')} — {len(got)} items", int(done / total * 55))

        articles = self._dedupe(articles)

        if self.settings.fetch_full_text and articles:
            self._enrich(articles, progress)

        today = date.today().isoformat()
        for a in articles:
            a.fetched_on = today
        return articles

    def _enrich(self, articles: list[Article], progress: Callable[[str, int], None] | None) -> None:
        total = len(articles)
        done = 0
        with ThreadPoolExecutor(max_workers=8) as pool:
            futures = {
                pool.submit(fetch_body, a.url, self.settings.request_timeout): a
                for a in articles
            }
            for fut in as_completed(futures):
                art = futures[fut]
                done += 1
                try:
                    art.body = fut.result()
                except Exception:
                    art.body = ""
                if progress:
                    progress(f"Reading: {art.title[:60]}", 55 + int(done / max(total, 1) * 45))

    @staticmethod
    def _dedupe(articles: list[Article]) -> list[Article]:
        seen_urls: set[str] = set()
        seen_titles: set[str] = set()
        out: list[Article] = []
        for a in articles:
            key = re.sub(r"[^a-z0-9 ]", "", a.title.lower())[:80]
            if a.url in seen_urls or key in seen_titles:
                continue
            seen_urls.add(a.url)
            seen_titles.add(key)
            out.append(a)
        return out
