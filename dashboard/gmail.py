"""Minimal read-only Gmail API client using a refresh token."""
import os, time
from email.utils import parseaddr, parsedate_to_datetime
import requests

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
            "link": f"https://mail.google.com/mail/u/{self.index}/#all/{j['id']}",
        }
