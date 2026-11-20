"""Heuristic importance scoring for email. Returns (score, reasons)."""
import re

def _promo(m):
    return any(l in m["labels"] for l in
               ("CATEGORY_PROMOTIONS", "CATEGORY_SOCIAL", "CATEGORY_FORUMS", "SPAM", "TRASH"))

def score(m, ctx, cfg, business=False):
    s, why = 0, []
    frm = f'{m["from_name"]} {m["from_addr"]}'.lower()
    if m["from_addr"] in ctx["me"]:
        return -99, []
    if "INBOX" not in m["labels"]:
        s -= 3
    if _promo(m):
        s -= 6
    if m["bulk"]:
        s -= 3
    if re.search(r"no-?reply|do-?not-?reply|notifications?@|newsletter|mailer", m["from_addr"]):
        s -= 3
    if "UNREAD" in m["labels"]:
        s += 1
    if m["thread"] in ctx["sent_threads"]:
        s += 4; why.append("reply to you")
    if m["from_addr"] in ctx["correspondents"]:
        s += 4; why.append("you've written them")
    for v in cfg["vips"]:
        if v["match"] in frm:
            s += 6; why.append(v["name"])
    last = cfg["last_name"]
    if last in m["from_name"].lower() or last in m["from_addr"].split("@")[0]:
        s += 5; why.append("family")
    if "IMPORTANT" in m["labels"] or "STARRED" in m["labels"]:
        s += 2
    if business:
        text = (m["subject"] + " " + m["snippet"]).lower()
        hits = [k for k in cfg["scoring"]["business_keywords"] if k in text]
        if hits:
            s += min(3, len(hits)); why.append(hits[0])
        if not m["bulk"] and "INBOX" in m["labels"]:
            s += 2
    return s, why
