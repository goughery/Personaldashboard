"""Non-email sources: Ticketmaster concerts, restaurant RSS feeds."""
import datetime as dt, os, re, html
import xml.etree.ElementTree as ET
import requests


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


def restaurants(cfg):
    c = cfg["restaurants"]
    items, errs = [], []
    for url in c["feeds"]:
        try:
            r = requests.get(url, timeout=20, headers={"User-Agent": "personal-dashboard/1.0"})
            r.raise_for_status()
            root = ET.fromstring(r.content)
        except Exception as ex:
            errs.append(f"{url}: {ex}")
            continue
        for it in root.iter("item"):
            title = html.unescape(it.findtext("title", ""))
            desc = re.sub("<[^>]+>", "", html.unescape(it.findtext("description", "")))
            text = (title + " " + desc).lower()
            if not any(k in text for k in c["keywords"]):
                continue
            if not any(k in text for k in c["must_mention"]) and "eater.com" in url:
                continue
            items.append({"title": title, "summary": desc[:220], "url": it.findtext("link", ""),
                          "date": it.findtext("pubDate", ""), "source": root.findtext("channel/title", url)})
    return items[:20], "; ".join(errs) or None
