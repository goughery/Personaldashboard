"""Collect data -> data.json structure. Usage: python -m dashboard.build [--demo]"""
import datetime as dt, html, json, os, re, sys, time
from . import scoring, sources, summarize

CFG = json.load(open(os.path.join(os.path.dirname(__file__), "..", "config.json")))
DATE_RX = re.compile(r"\b(Jan|Feb|Mar|Apr|May|Jun|Jul|Aug|Sep|Sept|Oct|Nov|Dec)[a-z]*\.?\s+(\d{1,2})(?:,?\s+(\d{4}))?", re.I)


STATE_PATH = os.path.join(os.path.dirname(__file__), "..", "state.json")
try:
    STATE = json.load(open(STATE_PATH))
except Exception:
    STATE = {}
STATE.setdefault("blocked", []); STATE.setdefault("read", {}); STATE.setdefault("gone", {})
BLOCKED = {x["a"].lower() for x in STATE["blocked"]}


def is_blocked(m):
    dom = "@" + m["from_addr"].split("@")[-1]
    return m["from_addr"] in BLOCKED or dom in BLOCKED or m["id"] in STATE["read"] or m["id"] in STATE["gone"]


def brief(m, g=None, rich=False):
    """rich=True also keeps the original HTML (newsletters), shown in a sandboxed frame."""
    body, htm = "", ""
    if g is not None:
        try:
            body, htm = g.body(m["id"])
        except Exception as ex:
            body = f"(could not load message: {ex})"
    out = {"id": m["id"], "addr": m["from_addr"],
           "title": html.unescape(m["subject"]), "from": m["from_name"], "url": m["link"],
           "snippet": html.unescape(m["snippet"])[:160], "ts": m["ts"], "body": body}
    if rich and htm:
        out["html"] = htm
    return out


def excluded(m, *groups):
    if is_blocked(m):
        return True
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


def base_out():
    content = json.load(open(os.path.join(os.path.dirname(__file__), "content.json")))
    return {"generated": time.time(), "events": [], "todos": [], "business": {}, "do317": [], "notes": [],
            "calendar": [], "races": [], "state": STATE, "repo": os.environ.get("GITHUB_REPOSITORY", ""),
            "weather": CFG["weather"], "workout": CFG["workout"], "content": content}


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
    out = base_out()
    out["read"] = {"brew": [], "baby": [], "world": [], "local": [], "restaurants": []}
    cal_key = CFG["calendar"]["account"]
    if cal_key in accts:
        try:
            from .gmail import calendar_events
            out["calendar"] = calendar_events(accts[cal_key][0], CFG["calendar"]["days_ahead"],
                                              CFG["calendar"]["exclude_calendars"])
        except Exception as ex:
            out["notes"].append(f"Calendar unavailable ({ex}). Re-create the Gmail token with the calendar.readonly scope and enable the Google Calendar API.")

    def ctx_for(g):
        sent = g.search("in:sent newer_than:90d", limit=150)
        return {"me": me, "sent_threads": {m["thread"] for m in sent},
                "correspondents": {x.strip(" <>").split("<")[-1] for m in sent for x in m["to"].split(",") if "@" in x}}

    if "personal" in accts:
        g = accts["personal"][0]
        for k, q in CFG["briefing"].items():
            got = [brief(m, g, rich=True) for m in g.search(q, 8) if not excluded(m)][:5]
            if k == "morning_brew":
                out["read"]["brew"] = got
            elif k == "baby":
                out["read"]["baby"] = got
            else:
                out["do317"] = got
        ctx = ctx_for(g)
        scored = []
        msgs = g.search("in:inbox newer_than:14d", limit=100)
        n_excl = 0
        for m in msgs:
            if excluded(m, "important"):
                n_excl += 1
                continue
            s, why = scoring.score(m, ctx, CFG)
            if s >= CFG["scoring"]["todo_min_score"]:
                scored.append((s, m, why))
        scored.sort(key=lambda t: (-t[0], -t[1]["ts"]))
        out["notes"].append(f"Mail scan, personal: {len(msgs)} inbox messages (14 days), {n_excl} excluded, {len(scored)} important; sent mail read: {len(ctx['sent_threads'])} threads.")
        out["todos"] = [dict(brief(m, g), score=s, why=why) for s, m, why in scored[:CFG["scoring"]["max_items"]]]
        for m in g.search(CFG["events"]["email_query"], 25) + g.search("from:do317.com newer_than:30d", 25):
            if excluded(m, "events"):
                continue
            out["events"].append({"id": m["id"], "addr": m["from_addr"], "title": m["subject"], "date": email_event_date(m), "time": "",
                                  "venue": m["from_name"], "url": m["link"], "source": "Email",
                                  **{k: v for k, v in brief(m, g, rich=True).items() if k in ("body", "html")}})
    for key in ("support", "cascade"):
        if key not in accts:
            continue
        g = accts[key][0]
        ctx = ctx_for(g)
        scored = []
        msgs = g.search("in:inbox newer_than:14d", limit=100)
        n_excl = 0
        for m in msgs:
            if excluded(m, key, "important"):
                n_excl += 1
                continue
            s, why = scoring.score(m, ctx, CFG, business=True)
            if s >= CFG["scoring"]["business_min_score"]:
                scored.append((s, m, why))
        scored.sort(key=lambda t: (-t[0], -t[1]["ts"]))
        out["notes"].append(f"Mail scan, {key}: {len(msgs)} inbox messages (14 days), {n_excl} excluded, {len(scored)} important.")
        out["business"][key] = {"label": CFG["accounts"][key]["label"],
                                "items": [dict(brief(m, g), score=s, why=why) for s, m, why in scored[:CFG["scoring"]["max_items"]]]}
    try:
        ev, note = sources.concerts(CFG)
        out["events"] += ev
        if note: out["notes"].append(note)
    except Exception as ex:
        out["notes"].append(f"Concerts failed: {ex}")
    rc = CFG["read"]
    for k in ("world", "local"):
        got, note = sources.news(rc[k], rc["per_feed"], rc["limit"])
        out["read"][k] = [r for r in got if "src:" + r["source"].lower() not in BLOCKED]
        if note: out["notes"].append(f"{k.title()} feeds: {note}")
    rs, note = sources.restaurants(CFG)
    out["read"]["restaurants"] = rs
    if note: out["notes"].append(f"Restaurant feeds: {note}")
    try:
        out["races"], note = sources.races(CFG)
        if note: out["notes"].append(note)
    except Exception as ex:
        out["notes"].append(f"Races failed: {ex}")
    out["races"] = [r for r in out["races"] if "race:" + r["title"].lower() not in BLOCKED]
    out["events"] = [e for e in out["events"] if e.get("addr") or "venue:" + (e.get("venue") or "").lower() not in BLOCKED]
    out["read"]["restaurants"] = [r for r in out["read"]["restaurants"] if "src:" + (r.get("source") or "").lower() not in BLOCKED]
    today = dt.date.today().isoformat()
    horizon = (dt.date.today() + dt.timedelta(days=30 * CFG["events"]["months_ahead"])).isoformat()
    out["events"] = sorted((e for e in out["events"] if not e["date"] or today <= e["date"] <= horizon),
                           key=lambda e: e["date"] or "9999")
    R = out["read"]
    note = summarize.add_summaries([*R["brew"], *R["baby"], *R["world"], *R["local"], *R["restaurants"]], CFG)
    if note: out["notes"].append(note)
    return out


def build_demo():
    out = base_out()
    now = time.time(); d = dt.date.today()
    b = lambda t, f, s="", **k: dict({"id": "id" + str(abs(hash(t))), "addr": f.lower().replace(" ", "") + "@example.com", "title": t, "from": f, "url": "#", "snippet": s, "ts": now - 3600, "body": "Full message text appears here when you expand an item.\n\nSecond paragraph."}, **k)
    iso = lambda n: (d + dt.timedelta(days=n)).isoformat()
    art = lambda t, src, s, **k: dict({"title": t, "source": src, "summary": s, "text": s + "\n\n" + s * 3, "url": "#", "ts": now - 7200}, **k)
    out["notes"] = ["Demo data"]
    out["calendar"] = [{"title": "Dentist", "start": iso(1) + "T09:00:00-05:00", "end": iso(1) + "T10:00:00-05:00", "allDay": False, "cal": "Personal", "color": "#4285f4", "url": "#", "loc": ""},
           {"title": "Heather's birthday", "start": iso(5), "end": iso(6), "allDay": True, "cal": "Family", "color": "#e67c73", "url": "#", "loc": ""},
           {"title": "Offsite", "start": iso(12), "end": iso(15), "allDay": True, "cal": "Work", "color": "#33b679", "url": "#", "loc": "Chicago"}]
    out["repo"] = "demo/demo"
    out["read"] = {
        "brew": [b("Today's Morning Brew", "Morning Brew", "Markets, tech and more", ai="• Markets steadied after a volatile week.\n• A new chip plant was announced in Ohio.\n• Three tips for a better morning.", html="<h2>Happy Friday</h2><p>Real <a href=\"https://example.com\">newsletter</a> layout.</p><script>alert(1)</script>")],
        "world": [art("Investigation: how a small fund moved millions", "ProPublica", "A long investigation.", ai="• A small fund routed millions through shell companies.\n• Regulators were warned twice and did not act.\n• The fund says it followed the rules."), art("Talks resume in Geneva", "BBC World", "Diplomats met on Friday.")],
        "local": [art("City council approves downtown plan", "Mirror Indy", "The vote was 6 to 3.")],
        "restaurants": [art("New pizza spot opens on Mass Ave", "Indianapolis Monthly", "Wood-fired and walkable.")],
        "baby": [b("Your baby this week: fingernails and hiccups", "BabyCenter")]}
    out["races"] = [{"title": "Monument Mile 5K", "date": iso(20), "where": "Indianapolis, IN", "events": ["5K", "Kids run"], "url": "#", "source": "RunSignup"},
                    {"title": "Indy Spring Triathlon", "date": iso(120), "where": "Carmel, IN", "events": ["Sprint", "Olympic"], "url": "#", "source": "RunSignup"}]
    out["do317"] = [b("This Weekend in Indy", "Do317", "Concerts, markets, brunch")]
    out["events"] = [{"title": "Sample Band Live", "date": iso(12), "time": "20:00", "venue": "The Vogue", "url": "#", "source": "Ticketmaster"},
                     {"title": "Holiday Market", "date": iso(30), "time": "", "venue": "Do317", "url": "#", "source": "Email"}]
    out["todos"] = [b("Dinner Saturday?", "Heather", "Are we still on for…", score=11, why=["Heather", "unread"]),
                    b("Re: Q4 plan", "Alex Moore", "Looks good, one change", score=10, why=["Alex Moore", "reply to you"])]
    out["business"] = {"support": {"label": "StatementsToSheets Support", "items": [b("Refund request", "Customer", "Charged twice", score=6, why=["refund"])]},
                       "cascade": {"label": "Cascade Foundry", "items": []}}
    return out


def main():
    data = build_demo() if "--demo" in sys.argv else build_live()
    from .render import render
    render(data, os.environ.get("DASHBOARD_PASSWORD"), "site")
    print("built site/index.html")


if __name__ == "__main__":
    main()
