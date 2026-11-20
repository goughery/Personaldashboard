"""Collect data -> data.json structure. Usage: python -m dashboard.build [--demo]"""
import datetime as dt, json, os, re, sys, time
from . import scoring, sources

CFG = json.load(open(os.path.join(os.path.dirname(__file__), "..", "config.json")))
DATE_RX = re.compile(r"\b(Jan|Feb|Mar|Apr|May|Jun|Jul|Aug|Sep|Sept|Oct|Nov|Dec)[a-z]*\.?\s+(\d{1,2})(?:,?\s+(\d{4}))?", re.I)


def brief(m, g=None):
    body = ""
    if g is not None:
        try:
            body = g.body(m["id"])
        except Exception as ex:
            body = f"(could not load message: {ex})"
    return {"title": m["subject"], "from": m["from_name"], "url": m["link"],
            "snippet": m["snippet"][:160], "ts": m["ts"], "body": body}


def excluded(m, *groups):
    text = f'{m["from_name"]} {m["from_addr"]} {m["subject"]}'.lower()
    terms = list(CFG["exclude"]["all"])
    for gname in groups:
        terms += CFG["exclude"].get(gname, [])
    return any(t in text for t in terms)


def email_event_date(m):
    mt = DATE_RX.search(m["subject"] + " " + m["snippet"])
    if not mt:
        return ""
    mon = mt.group(1)[:3].title()
    day = int(mt.group(2))
    today = dt.date.today()
    year = int(mt.group(3)) if mt.group(3) else today.year
    try:
        d = dt.datetime.strptime(f"{mon} {day} {year}", "%b %d %Y").date()
        if not mt.group(3) and d < today:
            d = d.replace(year=year + 1)
        return d.isoformat()
    except ValueError:
        return ""


def build_live():
    from .gmail import Gmail
    accts, ctx_all = {}, {}
    for key, a in CFG["accounts"].items():
        tok = os.environ.get(a["token_env"])
        if not tok:
            print(f"skip {key}: no {a['token_env']}", file=sys.stderr)
            continue
        accts[key] = (Gmail(tok, a["gmail_index"]), os.environ.get(a["address_env"], "").lower())
    me = {addr for _, addr in accts.values() if addr}
    out = {"generated": time.time(), "briefing": {}, "events": [], "restaurants": [],
           "todos": [], "business": {}, "notes": []}

    def ctx_for(g):
        sent = g.search("in:sent newer_than:90d", limit=150)
        return {"me": me, "sent_threads": {m["thread"] for m in sent},
                "correspondents": {x.strip(" <>").split("<")[-1] for m in sent for x in m["to"].split(",") if "@" in x}}

    if "personal" in accts:
        g = accts["personal"][0]
        for k, q in CFG["briefing"].items():
            out["briefing"][k] = [brief(m, g) for m in g.search(q, 8) if not excluded(m)][:5]
        ctx = ctx_for(g)
        scored = []
        for m in g.search("in:inbox newer_than:14d", limit=100):
            if excluded(m):
                continue
            s, why = scoring.score(m, ctx, CFG)
            if s >= CFG["scoring"]["todo_min_score"]:
                scored.append((s, m, why))
        scored.sort(key=lambda t: (-t[0], -t[1]["ts"]))
        out["todos"] = [dict(brief(m, g), score=s, why=why) for s, m, why in scored[:CFG["scoring"]["max_items"]]]
        for m in g.search(CFG["events"]["email_query"], 25) + g.search("from:do317.com newer_than:30d", 25):
            if excluded(m, "events"):
                continue
            out["events"].append({"title": m["subject"], "date": email_event_date(m), "time": "",
                                  "venue": m["from_name"], "url": m["link"], "source": "Email",
                                  "body": brief(m, g)["body"]})
    for key in ("support", "cascade"):
        if key not in accts:
            continue
        g = accts[key][0]
        ctx = ctx_for(g)
        scored = []
        for m in g.search("in:inbox newer_than:14d", limit=100):
            if excluded(m, key):
                continue
            s, why = scoring.score(m, ctx, CFG, business=True)
            if s >= CFG["scoring"]["business_min_score"]:
                scored.append((s, m, why))
        scored.sort(key=lambda t: (-t[0], -t[1]["ts"]))
        out["business"][key] = {"label": CFG["accounts"][key]["label"],
                                "items": [dict(brief(m, g), score=s, why=why) for s, m, why in scored[:CFG["scoring"]["max_items"]]]}
    try:
        ev, note = sources.concerts(CFG)
        out["events"] += ev
        if note: out["notes"].append(note)
    except Exception as ex:
        out["notes"].append(f"Concerts failed: {ex}")
    rs, note = sources.restaurants(CFG)
    out["restaurants"] = rs
    if note: out["notes"].append(f"Restaurant feeds: {note}")
    today = dt.date.today().isoformat()
    horizon = (dt.date.today() + dt.timedelta(days=30 * CFG["events"]["months_ahead"])).isoformat()
    out["events"] = sorted((e for e in out["events"] if not e["date"] or today <= e["date"] <= horizon),
                           key=lambda e: e["date"] or "9999")
    return out


def build_demo():
    now = time.time(); d = dt.date.today()
    b = lambda t, f, s="": {"title": t, "from": f, "url": "#", "snippet": s, "ts": now - 3600, "body": "Full message text appears here when you expand an item.\n\nSecond paragraph."}
    return {"generated": now, "notes": ["Demo data"],
            "briefing": {"morning_brew": [b("☕ Today's Morning Brew", "Morning Brew", "Markets, tech and more")],
                         "baby": [b("Your baby this week: fingernails and hiccups", "BabyCenter")],
                         "do317": [b("This Weekend in Indy", "Do317", "Concerts, markets, brunch")]},
            "events": [{"title": "Sample Band Live", "date": (d + dt.timedelta(days=12)).isoformat(), "time": "20:00",
                        "venue": "The Vogue", "url": "#", "source": "Ticketmaster"},
                       {"title": "Holiday Market", "date": (d + dt.timedelta(days=30)).isoformat(), "time": "",
                        "venue": "Do317", "url": "#", "source": "Email"}],
            "restaurants": [{"title": "New pizza spot opens on Mass Ave", "summary": "Wood-fired and walkable.", "url": "#", "date": "", "source": "Indianapolis Monthly"}],
            "todos": [dict(b("Dinner Saturday?", "Heather", "Are we still on for…"), score=11, why=["Heather", "unread"]),
                      dict(b("Re: Q4 plan", "Alex Moore", "Looks good, one change"), score=10, why=["Alex Moore", "reply to you"])],
            "business": {"support": {"label": "StatementsToSheets Support", "items": [dict(b("Refund request", "Customer", "Charged twice"), score=6, why=["refund"])]},
                         "cascade": {"label": "Cascade Foundry", "items": []}}}


def main():
    data = build_demo() if "--demo" in sys.argv else build_live()
    from .render import render
    render(data, os.environ.get("DASHBOARD_PASSWORD"), "site")
    print("built site/index.html")


if __name__ == "__main__":
    main()
