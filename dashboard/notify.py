"""Send the ~6am push notification through ntfy.sh. Contains NO email/calendar content, only a generic nudge.
Env: NTFY_TOPIC (secret, hard-to-guess), GITHUB_REPOSITORY. Delivery is scheduled for the configured local time."""
import datetime as dt, json, os, sys, time, urllib.request
from zoneinfo import ZoneInfo

CFG = json.load(open(os.path.join(os.path.dirname(__file__), "..", "config.json")))
CONTENT = json.load(open(os.path.join(os.path.dirname(__file__), "content.json")))


def build_message(now=None):
    tz = ZoneInfo(CFG["timezone"])
    now = now or dt.datetime.now(tz)
    lt = CFG["workout"]["leave_by"].lstrip("0")
    nudges = CONTENT["nudges"]
    why = nudges[now.timetuple().tm_yday % len(nudges)]
    repo = os.environ.get("GITHUB_REPOSITORY", "")
    owner, _, name = repo.partition("/")
    click = f"https://{owner}.github.io/{name}/" if repo else ""
    msg = {"topic": os.environ["NTFY_TOPIC"], "title": f"Good morning. Out the door by {lt}",
           "message": f"You'll have a better day if you leave at {lt}, not 7:30 or 8. {why} Dashboard is ready.",
           "tags": ["runner", "sunny"], "priority": 4}
    if click:
        msg["click"] = click
    target = now.replace(hour=CFG["notify"]["hour"], minute=CFG["notify"]["minute"], second=0, microsecond=0)
    if (target - now).total_seconds() > 30:
        msg["delay"] = str(int(target.timestamp()))  # ntfy accepts a unix timestamp; server holds it until then
    return msg


def main():
    if not os.environ.get("NTFY_TOPIC"):
        print("NTFY_TOPIC not set; skipping notification")
        return
    msg = build_message()
    req = urllib.request.Request("https://ntfy.sh/", data=json.dumps(msg).encode(), headers={"Content-Type": "application/json"})
    with urllib.request.urlopen(req, timeout=20) as r:
        print("ntfy:", r.status, "(scheduled)" if "delay" in msg else "(immediate)")


if __name__ == "__main__":
    main()
