#!/usr/bin/env python3
"""
Daily Briefing updater.

  python3 update.py fetch   -> downloads today's headlines and newest videos
                               into data/fetched.json, and lists the videos
                               that still need a summary.
  python3 update.py build   -> writes everything into the FEED object in
                               index.html (headlines + videos + summaries).

Summaries live in data/summaries.json, keyed by YouTube video id:
  { "VIDEO_ID": { "headline": "...", "summary": "para 1\n\npara 2 ...",
                  "basis": "description" | "transcript" } }
Each morning Claude reads data/fetched.json, writes summaries for any new
videos into that file, then runs `build`.

Only uses Python's standard library, so nothing extra needs installing.
"""
import json, re, sys, html, urllib.request, urllib.error
import xml.etree.ElementTree as ET
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parent
DATA = ROOT / "data"
INDEX = ROOT / "index.html"
FETCHED = DATA / "fetched.json"
SUMMARIES = DATA / "summaries.json"

UA = {"User-Agent": "Mozilla/5.0 (Macintosh) DailyBriefing/1.0"}

# ---------------------------------------------------------------- sources
WESTERN = [
    # BBC and DW: their official RSS feeds, in the outlets' own top-story order.
    {"name": "BBC News", "site": "https://www.bbc.com/news",
     "kind": "rss", "url": "https://feeds.bbci.co.uk/news/rss.xml"},
    # CNN stopped updating its RSS feeds in 2024, so we use CNN's official
    # Google-News sitemap instead (its newest news articles).
    {"name": "CNN", "site": "https://www.cnn.com",
     "kind": "cnn_sitemap", "url": "https://www.cnn.com/sitemap/news.xml"},
    {"name": "DW", "site": "https://www.dw.com/en",
     "kind": "rss", "url": "https://rss.dw.com/rdf/rss-en-top"},
]

BRICS = []  # outlets to be added later

CHANNELS = [
    {"name": "Judging Freedom",  "slug": "judging-freedom",  "id": "UCDkEYb-TXJVWLvOokshtlsw"},
    {"name": "Double Down News", "slug": "double-down-news", "id": "UCeRYN0tYBQVrC2cKsxJjdow"},
    {"name": "Glenn Diesen",     "slug": "glenn-diesen",     "id": "UCZFCDIHTe9HGxtIuVDpBz7g"},
    {"name": "Chris Hedges",     "slug": "chris-hedges",     "id": "UCEATT6H3U5lu20eKPuHVN8A"},
    {"name": "The Grayzone",     "slug": "the-grayzone",     "id": "UCEXR8pRTkE2vFeJePNe9UcQ"},
    {"name": "Tucker Carlson",   "slug": "tucker-carlson",   "id": "UCGttrUON87gWfU6dMWm1fcA"},
    {"name": "George Galloway",  "slug": "george-galloway",  "id": "UCf_HItERkRB3vnkWt2RSOLg"},
]

NS = {
    "atom": "http://www.w3.org/2005/Atom",
    "yt": "http://www.youtube.com/xml/schemas/2015",
    "media": "http://search.yahoo.com/mrss/",
    "rss1": "http://purl.org/rss/1.0/",
    "sm": "http://www.sitemaps.org/schemas/sitemap/0.9",
    "news": "http://www.google.com/schemas/sitemap-news/0.9",
}


# ---------------------------------------------------------------- helpers
def get(url, method="GET"):
    req = urllib.request.Request(url, headers=UA, method=method)
    with urllib.request.urlopen(req, timeout=30) as r:
        return r.read()


def clean(text):
    return re.sub(r"\s+", " ", html.unescape(text or "")).strip()


def rss_headlines(url, n=3):
    root = ET.fromstring(get(url))
    items = root.findall(".//item") or root.findall(".//rss1:item", NS)
    out = []
    for it in items:
        title = it.findtext("title") or it.findtext("rss1:title", namespaces=NS)
        link = it.findtext("link") or it.findtext("rss1:link", namespaces=NS)
        title, link = clean(title), clean(link)
        if not title or not link:
            continue
        # skip video/live/audio-only items so we keep real articles
        if re.search(r"/(videos?|av|live|audios?|sounds)/", link):
            continue
        # drop tracking codes like ?at_medium=RSS from BBC/DW links
        out.append({"title": title, "url": link.split("?")[0]})
        if len(out) == n:
            break
    return out


def cnn_headlines(url, n=3):
    root = ET.fromstring(get(url))
    rows = []
    for u in root.findall("sm:url", NS):
        loc = clean(u.findtext("sm:loc", namespaces=NS))
        title = clean(u.findtext("news:news/news:title", namespaces=NS))
        date = u.findtext("news:news/news:publication_date", namespaces=NS) or ""
        # keep news articles only: skip shopping, videos, live blogs, gallery pages
        if not title or re.search(r"/(cnn-underscored|videos?|live-news|gallery|travel|style)/", loc):
            continue
        rows.append((date, {"title": title, "url": loc}))
    rows.sort(key=lambda r: r[0], reverse=True)
    return [r[1] for r in rows[:n]]


def is_short(video_id):
    """YouTube answers /shorts/<id> with 200 only for Shorts."""
    try:
        class NoRedirect(urllib.request.HTTPRedirectHandler):
            def redirect_request(self, *a, **k):
                return None
        opener = urllib.request.build_opener(NoRedirect)
        req = urllib.request.Request(f"https://www.youtube.com/shorts/{video_id}", headers=UA, method="HEAD")
        return opener.open(req, timeout=15).status == 200
    except urllib.error.HTTPError:
        return False
    except Exception:
        return False


def newest_video(channel_id):
    root = ET.fromstring(get(f"https://www.youtube.com/feeds/videos.xml?channel_id={channel_id}"))
    now = datetime.now(timezone.utc)
    entries = []
    for e in root.findall("atom:entry", NS):
        vid = e.findtext("yt:videoId", namespaces=NS)
        pub = e.findtext("atom:published", namespaces=NS)
        try:
            when = datetime.fromisoformat(pub)
        except Exception:
            continue
        if when > now:  # scheduled premiere, not out yet
            continue
        entries.append((when, vid, e))
    entries.sort(key=lambda x: x[0], reverse=True)  # the feed is not always in date order
    for when, vid, e in entries:
        if is_short(vid):
            continue
        return {
            "id": vid,
            "title": clean(e.findtext("atom:title", namespaces=NS)),
            "url": f"https://www.youtube.com/watch?v={vid}",
            "date": when.isoformat(),
            "description": (e.findtext("media:group/media:description", namespaces=NS) or "").strip(),
        }
    return None


def load_json(path, default):
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except FileNotFoundError:
        return default


# ---------------------------------------------------------------- commands
def fetch():
    DATA.mkdir(exist_ok=True)
    out = {"fetched": datetime.now(timezone.utc).isoformat(timespec="seconds"),
           "western": [], "videos": [], "errors": []}
    for s in WESTERN:
        try:
            hs = rss_headlines(s["url"]) if s["kind"] == "rss" else cnn_headlines(s["url"])
        except Exception as ex:
            hs = []
            out["errors"].append(f"{s['name']}: {ex}")
        out["western"].append({"name": s["name"], "site": s["site"], "headlines": hs})
    for c in CHANNELS:
        try:
            v = newest_video(c["id"])
        except Exception as ex:
            v = None
            out["errors"].append(f"{c['name']}: {ex}")
        out["videos"].append({"name": c["name"], "slug": c["slug"], "video": v})
    FETCHED.write_text(json.dumps(out, ensure_ascii=False, indent=2), encoding="utf-8")

    done = load_json(SUMMARIES, {})
    print(f"Saved {FETCHED.relative_to(ROOT)}")
    for w in out["western"]:
        print(f"  {w['name']}: {len(w['headlines'])} headlines")
    need = [v for v in out["videos"] if v["video"] and v["video"]["id"] not in done]
    print(f"Videos needing a summary: {len(need)}")
    for v in need:
        print(f"  {v['name']}: {v['video']['id']}  {v['video']['title']}")
    for e in out["errors"]:
        print("  ERROR", e)


def build():
    f = load_json(FETCHED, None)
    if f is None:
        sys.exit("Run `python3 update.py fetch` first.")
    summaries = load_json(SUMMARIES, {})
    indie = []
    for v in f["videos"]:
        vid = v["video"]
        videos = []
        if vid:
            s = summaries.get(vid["id"], {})
            videos.append({
                "title": s.get("headline") or vid["title"],
                "originalTitle": vid["title"],
                "date": vid["date"],
                "url": vid["url"],
                "summary": s.get("summary", ""),
                "basis": s.get("basis", ""),
            })
        indie.append({"name": v["name"], "slug": v["slug"], "videos": videos})

    feed = {
        "updated": datetime.now().astimezone().isoformat(timespec="seconds"),
        "sections": [
            {"id": "west", "title": "Western Mainstream Media",
             "note": "Top 3 headlines per outlet", "sources": f["western"]},
            {"id": "brics", "title": "BRICS Mainstream Media",
             "note": "Outlets to be added", "sources": BRICS},
            {"id": "indie", "title": "Alternative & Independent Media",
             "note": "Latest video from each channel", "sources": indie},
        ],
    }
    js = json.dumps(feed, ensure_ascii=False, indent=2).replace("</", "<\\/")
    page = INDEX.read_text(encoding="utf-8")
    new, n = re.subn(r"/\*FEED-START\*/.*?/\*FEED-END\*/",
                     lambda m: f"/*FEED-START*/\nconst FEED = {js};\n/*FEED-END*/",
                     page, flags=re.S)
    if n != 1:
        sys.exit("Could not find the FEED markers in index.html.")
    INDEX.write_text(new, encoding="utf-8")
    missing = [v["name"] for v in indie if v["videos"] and not v["videos"][0]["summary"]]
    print("index.html updated." + (f" Missing summaries: {', '.join(missing)}" if missing else ""))


if __name__ == "__main__":
    cmd = sys.argv[1] if len(sys.argv) > 1 else ""
    {"fetch": fetch, "build": build}.get(cmd, lambda: sys.exit(__doc__))()
