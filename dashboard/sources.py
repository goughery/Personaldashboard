"""Non-email sources: Ticketmaster concerts, restaurant RSS feeds."""
import datetime as dt, html, os, re
from email.utils import parsedate_to_datetime
import xml.etree.ElementTree as ET
import requests
from .gmail import html_to_text


def concerts(cfg):
    key = os.environ.get("TICKETMASTER_API_KEY")
    if not key:
        return [], "Set TICKETMASTER_API_KEY to list Indy concerts."
    e = cfg["events"]
    now = dt.datetime.utcnow().replace(microsecond=0)
    end = now + dt.timedelta(days=30 * e["months_ahead"])
    out, page = [], 0
    while page < 5:
        r = requests.get("https://app.ticketmaster.com/discovery/v2/events.json", params={
            "apikey": key, "city": e["ticketmaster_city"], "countryCode": "US",
            "classificationName": "music", "sort": "date,asc", "size": 200, "page": page,
            "startDateTime": now.isoformat() + "Z", "endDateTime": end.isoformat() + "Z",
        }, timeout=30)
        r.raise_for_status()
        j = r.json()
        for ev in j.get("_embedded", {}).get("events", []):
            d = ev["dates"]["start"]
            venue = (ev.get("_embedded", {}).get("venues") or [{}])[0].get("name", "")
            out.append({"title": ev["name"], "date": d.get("localDate", ""),
                        "time": d.get("localTime", ""), "venue": venue, "url": ev["url"],
                        "source": "Ticketmaster"})
        if page + 1 >= j.get("page", {}).get("totalPages", 1):
            break
        page += 1
    return out, None


ATOM = "{http://www.w3.org/2005/Atom}"
CONTENT = "{http://purl.org/rss/1.0/modules/content/}encoded"
DC_DATE = "{http://purl.org/dc/elements/1.1/}date"
UA = {"User-Agent": "personal-dashboard/1.0"}


def _clean(h, n):
    t = html_to_text(h or "")
    t = re.sub(r"[ \t\xa0]+", " ", t)
    t = re.sub(r"\n\s*\n\s*(\n\s*)+", "\n\n", t).strip()
    return t[:n] + ("…" if len(t) > n else "")


def _ts(s):
    if not s:
        return 0
    try:
        return parsedate_to_datetime(s).timestamp()
    except Exception:
        try:
            return dt.datetime.fromisoformat(s.replace("Z", "+00:00")).timestamp()
        except Exception:
            return 0


def fetch_feed(url, name=None):
    """Parse an RSS 2.0 or Atom feed -> list of {title, summary, text, url, ts, source}."""
    r = requests.get(url, timeout=20, headers=UA)
    r.raise_for_status()
    root = ET.fromstring(r.content)
    src = name or root.findtext("channel/title") or root.findtext(ATOM + "title") or url
    out = []
    for it in root.iter("item"):
        desc = it.findtext("description") or ""
        out.append({"title": html.unescape(it.findtext("title", "")).strip(), "url": (it.findtext("link") or "").strip(),
                    "summary": _clean(desc, 240), "text": _clean(it.findtext(CONTENT) or desc, 3500),
                    "ts": _ts(it.findtext("pubDate") or it.findtext(DC_DATE)), "source": src})
    for en in root.iter(ATOM + "entry"):
        href = ""
        for l in en.findall(ATOM + "link"):
            if l.get("rel", "alternate") == "alternate":
                href = l.get("href", "")
                break
        body = en.findtext(ATOM + "content") or en.findtext(ATOM + "summary") or ""
        out.append({"title": html.unescape(en.findtext(ATOM + "title", "")).strip(), "url": href,
                    "summary": _clean(en.findtext(ATOM + "summary") or body, 240), "text": _clean(body, 3500),
                    "ts": _ts(en.findtext(ATOM + "updated") or en.findtext(ATOM + "published")), "source": src})
    return out


def _feeds(spec):
    for f in spec:
        yield (f, None) if isinstance(f, str) else (f["url"], f.get("name"))


def news(feeds, per_feed=6, limit=14):
    """Newest items across feeds (max per_feed from each so one source can't dominate)."""
    items, errs = [], []
    for url, name in _feeds(feeds):
        try:
            got = sorted(fetch_feed(url, name), key=lambda x: -x["ts"])[:per_feed]
            items += got
        except Exception as ex:
            errs.append(f"{name or url}: {ex}")
    items.sort(key=lambda x: -x["ts"])
    return items[:limit], "; ".join(errs) or None


def restaurants(cfg):
    c = cfg["restaurants"]
    items, errs = [], []
    for url, name in _feeds(c["feeds"]):
        try:
            feed = fetch_feed(url, name)
        except Exception as ex:
            errs.append(f"{name or url}: {ex}")
            continue
        for it in feed:
            text = (it["title"] + " " + it["summary"]).lower()
            if not any(k in text for k in c["keywords"]):
                continue
            if "eater.com" in url and not any(k in text for k in c["must_mention"]):
                continue
            items.append(it)
    items.sort(key=lambda x: -x["ts"])
    return items[:c.get("max", 10)], "; ".join(errs) or None


def races(cfg):
    """Local races from RunSignup (needs a free API key+secret). Returns (items, note)."""
    key, sec = os.environ.get("RUNSIGNUP_API_KEY"), os.environ.get("RUNSIGNUP_API_SECRET")
    if not key or not sec:
        return [], "Set RUNSIGNUP_API_KEY and RUNSIGNUP_API_SECRET to list local races."
    c = cfg["races"]
    start = dt.date.today()
    end = start + dt.timedelta(days=30 * c["months_ahead"])
    out, page = [], 1
    while page <= 3:
        r = requests.get("https://runsignup.com/Rest/races", params={
            "format": "json", "api_key": key, "api_secret": sec, "events": "T", "race_headings": "F",
            "zipcode": c["zipcode"], "radius": c["radius_miles"], "start_date": start.isoformat(),
            "end_date": end.isoformat(), "page": page, "results_per_page": 100, "sort": "date ASC"}, timeout=30)
        r.raise_for_status()
        rows = r.json().get("races", [])
        for row in rows:
            x = row.get("race", row)
            evs = x.get("events") or []
            names = [e.get("name", "") for e in evs]
            if evs and all("virtual" in (e.get("name", "") + e.get("event_type", "")).lower() for e in evs):
                continue
            try:
                d = dt.datetime.strptime(x.get("next_date", ""), "%m/%d/%Y").date().isoformat()
            except ValueError:
                continue
            a = x.get("address", {})
            out.append({"title": x.get("name", "Race"), "date": d,
                        "where": ", ".join(p for p in (a.get("city"), a.get("state")) if p),
                        "events": [n for n in names if n][:5], "url": x.get("url", ""), "source": "RunSignup"})
        if len(rows) < 100:
            break
        page += 1
    out.sort(key=lambda r: r["date"])
    return out[:c["max"]], None
