"""Real-world social signals for the digital twin: public Mastodon hashtag timelines
(traveler/resident posts) and Google News RSS (local reports), both keyless public feeds.

Each item is classified by keyword into weather-impact categories; the share of recent,
relevant items becomes a 0..1 `social_index` per place, which the twin uses as an
extra feature (people on the ground often report waterlogging or airport chaos before
official feeds do). Nothing is fabricated: with no network, the index is 0 and the feed
is empty, and the response says so.
"""
import html
import re
import time
import xml.etree.ElementTree as ET
from datetime import datetime, timedelta, timezone
from email.utils import parsedate_to_datetime

import httpx

CACHE_SECONDS = 600
RECENT_HOURS = 72
USER_AGENT = "TripRescue/1.0 (travel disruption digital twin; hackathon demo)"

CATEGORIES = {
    "flooding": ("flood", "waterlog", "water-log", "inundat", "submerged", "overflow"),
    "heavy_rain": ("heavy rain", "downpour", "cloudburst", "monsoon", "red alert", "orange alert", "rainfall", "rains"),
    "storm": ("cyclone", "storm", "thunder", "lightning", "gale", "squall"),
    "heat": ("heatwave", "heat wave", "scorching", "hottest", "heatstroke"),
    "transport_disruption": (
        "flight delay", "flights delayed", "diverted", "cancelled", "canceled", "airport", "traffic jam",
        "road closed", "landslide", "train delay", "stranded", "disrupt",
    ),
}
# a post/headline only counts if it is actually about weather - bare "storm" is excluded
# because it is common in political headlines ("... storm intensifies")
WEATHER_TERMS = (
    "rain", "flood", "cyclone", "monsoon", "heatwave", "heat wave", "weather", "waterlog",
    "thunderstorm", "dust storm", "storm warning", "imd", "downpour", "cloudburst",
)


def is_relevant(text: str, place: str) -> bool:
    t = text.lower()
    return place.lower() in t and any(w in t for w in WEATHER_TERMS)

_cache: dict[str, tuple[float, list[dict]]] = {}
_TAG_RE = re.compile(r"<[^>]+>")


def _clean(text: str) -> str:
    return re.sub(r"\s+", " ", html.unescape(_TAG_RE.sub(" ", text or ""))).strip()


def classify(text: str) -> list[str]:
    t = text.lower()
    return [cat for cat, words in CATEGORIES.items() if any(w in t for w in words)]


def _get(url: str, **params) -> httpx.Response | None:
    try:
        resp = httpx.get(url, params=params, headers={"User-Agent": USER_AGENT}, timeout=12, follow_redirects=True)
        resp.raise_for_status()
        return resp
    except Exception:
        return None


def _google_news(place: str) -> list[dict]:
    query = f"{place} (rain OR flood OR storm OR cyclone OR heatwave OR waterlogging OR \"flight delay\")"
    resp = _get("https://news.google.com/rss/search", q=query, hl="en-IN", gl="IN", ceid="IN:en")
    if resp is None:
        return []
    items = []
    try:
        root = ET.fromstring(resp.content)
    except ET.ParseError:
        return []
    for item in root.iter("item"):
        title = _clean(item.findtext("title", ""))
        try:
            published = parsedate_to_datetime(item.findtext("pubDate", "")).astimezone(timezone.utc)
        except Exception:
            continue
        items.append({
            "source": "Google News",
            "author": _clean(item.findtext("source", "")) or "news",
            "text": title,
            "url": item.findtext("link", ""),
            "published": published.isoformat(),
        })
    return items


def _mastodon(place: str) -> list[dict]:
    items = []
    for tag in {place.lower().replace(" ", ""), f"{place.lower().replace(' ', '')}rains"}:
        resp = _get(f"https://mastodon.social/api/v1/timelines/tag/{tag}", limit=40)
        if resp is None:
            continue
        for post in resp.json():
            text = _clean(post.get("content", ""))
            # hashtag timelines are mostly off-topic; the tag supplies the place, keep weather posts only
            if not is_relevant(f"{place} {text}", place):
                continue
            items.append({
                "source": "Mastodon",
                "author": "@" + (post.get("account") or {}).get("acct", "unknown"),
                "text": text[:280],
                "url": post.get("url", ""),
                "published": post.get("created_at", ""),
            })
    return items


def fetch_signals(place: str) -> dict:
    """Recent weather-relevant public posts/reports for `place`, classified, with a 0..1 index."""
    hit = _cache.get(place)
    if hit and time.time() - hit[0] < CACHE_SECONDS:
        items = hit[1]
    else:
        items = _google_news(place) + _mastodon(place)
        _cache[place] = (time.time(), items)

    cutoff = datetime.now(timezone.utc) - timedelta(hours=RECENT_HOURS)
    recent = []
    for it in items:
        try:
            ts = datetime.fromisoformat(it["published"].replace("Z", "+00:00"))
        except ValueError:
            continue
        if ts < cutoff:
            continue
        cats = classify(it["text"])
        if cats and is_relevant(it["text"] if it["source"] != "Mastodon" else f"{place} {it['text']}", place):
            recent.append({**it, "categories": cats})
    recent.sort(key=lambda x: x["published"], reverse=True)

    counts = {cat: sum(cat in it["categories"] for it in recent) for cat in CATEGORIES}
    # disruption-type reports weigh more than generic "it's raining" chatter; saturates at ~12
    weighted = counts["flooding"] * 2 + counts["transport_disruption"] * 2 + counts["storm"] * 1.5 + counts["heavy_rain"] + counts["heat"]
    index = min(1.0, weighted / 12.0)

    return {
        "place": place,
        "live": bool(items) or hit is not None,
        "window_hours": RECENT_HOURS,
        "social_index": round(index, 3),
        "category_counts": counts,
        "items": recent[:15],
    }
