"""Minimal read-only Gmail API client using a refresh token."""
import base64, html, os, re, time
from email.utils import parseaddr, parsedate_to_datetime
import requests
from urllib.parse import quote

TOKEN_URL = "https://oauth2.googleapis.com/token"
API = "https://gmail.googleapis.com/gmail/v1/users/me"
HEADERS = ["From", "To", "Subject", "Date", "List-Unsubscribe"]


class Gmail:
    def __init__(self, refresh_token, index=0):
        self.refresh_token, self.index = refresh_token, index
        self.s = requests.Session()
        self._tok, self._exp = None, 0

    def _auth(self):
        if time.time() > self._exp - 60:
            r = requests.post(TOKEN_URL, data={
                "client_id": os.environ["GOOGLE_CLIENT_ID"],
                "client_secret": os.environ["GOOGLE_CLIENT_SECRET"],
                "refresh_token": self.refresh_token,
                "grant_type": "refresh_token"}, timeout=30)
            r.raise_for_status()
            j = r.json()
            self._tok, self._exp = j["access_token"], time.time() + j["expires_in"]
        return {"Authorization": f"Bearer {self._tok}"}

    def _get(self, path, **params):
        r = self.s.get(f"{API}/{path}", headers=self._auth(), params=params, timeout=30)
        r.raise_for_status()
        return r.json()

    def search(self, q, limit=25):
        ids, token = [], None
        while len(ids) < limit:
            p = {"q": q, "maxResults": min(100, limit - len(ids))}
            if token:
                p["pageToken"] = token
            j = self._get("messages", **p)
            ids += [m["id"] for m in j.get("messages", [])]
            token = j.get("nextPageToken")
            if not token:
                break
        return [self.message(i) for i in ids]

    def message(self, mid):
        j = self._get(f"messages/{mid}", format="metadata", metadataHeaders=HEADERS)
        h = {x["name"].lower(): x["value"] for x in j["payload"]["headers"]}
        name, addr = parseaddr(h.get("from", ""))
        try:
            ts = parsedate_to_datetime(h["date"]).timestamp()
        except Exception:
            ts = int(j.get("internalDate", 0)) / 1000
        return {
            "id": j["id"], "thread": j["threadId"], "labels": j.get("labelIds", []),
            "from_name": name or addr, "from_addr": addr.lower(),
            "to": h.get("to", "").lower(), "subject": h.get("subject", "(no subject)"),
            "snippet": j.get("snippet", ""), "ts": ts, "bulk": "list-unsubscribe" in h,
            "link": f"https://mail.google.com/mail/u/{self.index}/#all/{j['threadId']}",
        }

    def body(self, mid, limit=6000, html_cap=150_000):
        """Return (clean_text, html_or_empty). Prefers the HTML part: many newsletters ship a junk plain part."""
        j = self._get(f"messages/{mid}", format="full")
        plain, htm = [], []
        def walk(p):
            data = p.get("body", {}).get("data")
            mt = p.get("mimeType", "")
            if data and mt in ("text/plain", "text/html"):
                t = base64.urlsafe_b64decode(data + "=" * (-len(data) % 4)).decode("utf-8", "replace")
                (plain if mt == "text/plain" else htm).append(t)
            for q in p.get("parts", []) or []:
                walk(q)
        walk(j["payload"])
        raw_html = "\n".join(htm)
        if raw_html:
            t = html_to_text(raw_html)
        else:
            t = "\n".join(plain)
        t = re.sub(r"[ \t\xa0]+", " ", t)
        t = re.sub(r"\n[ \t]*(\n[ \t]*)+", "\n\n", t).strip()
        t = t[:limit] + ("…" if len(t) > limit else "")
        return t, (raw_html if raw_html and len(raw_html) <= html_cap else "")


def html_to_text(h):
    h = re.sub(r"(?is)<(script|style|head)\b.*?</\1>", "", h)
    h = re.sub(r"(?is)<img\b[^>]*>", "", h)
    h = re.sub(r"(?i)<br\s*/?>|</(p|div|tr|li|h\d|table)>", "\n", h)
    h = re.sub(r"(?i)<li\b[^>]*>", "• ", h)
    h = re.sub(r"<[^>]+>", "", h)
    h = html.unescape(html.unescape(h))
    h = re.sub(r"https?://\S{60,}", "[link]", h)
    return h


CAL = "https://www.googleapis.com/calendar/v3"


def calendar_events(gm, days=245, exclude=()):
    """All events from the account's visible calendars, today .. +days. Needs calendar.readonly scope."""
    import datetime as dt
    now = dt.datetime.now(dt.timezone.utc)
    tmin = (now - dt.timedelta(days=1)).strftime("%Y-%m-%dT%H:%M:%SZ")
    tmax = (now + dt.timedelta(days=days)).strftime("%Y-%m-%dT%H:%M:%SZ")

    def cget(path, **params):
        r = gm.s.get(f"{CAL}/{path}", headers=gm._auth(), params=params, timeout=30)
        r.raise_for_status()
        return r.json()

    out = []
    for c in cget("users/me/calendarList").get("items", []):
        name = c.get("summaryOverride") or c.get("summary", "")
        if c.get("hidden") or c.get("selected") is False:
            continue
        if any(x.lower() in name.lower() for x in exclude):
            continue
        token = None
        while True:
            p = {"timeMin": tmin, "timeMax": tmax, "singleEvents": "true",
                 "orderBy": "startTime", "maxResults": 250}
            if token:
                p["pageToken"] = token
            j = cget(f"calendars/{quote(c['id'], safe='')}/events", **p)
            for e in j.get("items", []):
                if e.get("status") == "cancelled":
                    continue
                s, en = e.get("start", {}), e.get("end", {})
                out.append({"title": e.get("summary", "(busy)"),
                            "start": s.get("dateTime") or s.get("date"),
                            "end": en.get("dateTime") or en.get("date"),
                            "allDay": "date" in s, "cal": name,
                            "url": e.get("htmlLink", ""), "loc": e.get("location", "")})
            token = j.get("nextPageToken")
            if not token:
                break
    return out
