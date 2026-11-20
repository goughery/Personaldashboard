# Personal Dashboard

Daily-built, passphrase-encrypted static dashboard (works on any device). Sections: **Briefing**
(Morning Brew, baby development, Do317), **To-do** (scored important personal mail), **Business**
(support + Cascade Foundry inboxes), **Events** (Indy concerts + email events, 8 months), **Restaurants**.

Gmail is read with the read-only scope; nothing is sent or modified.

## Setup
1. Google Cloud: create a project, enable the Gmail API, create an OAuth *Desktop* client, add yourself as a test user
   (or publish the app, otherwise refresh tokens expire after 7 days). Download `client_secret.json`.
2. For each of the three mailboxes: `pip install -r requirements.txt && python auth_setup.py client_secret.json`
   and sign in as that mailbox. The two business inboxes are Google Workspace accounts if they're Gmail-backed;
   if one is just forwarded to Gmail, skip it and adjust `config.json`.
3. Free Ticketmaster key: developer.ticketmaster.com.
4. Repo → Settings → Secrets → Actions, add: `GOOGLE_CLIENT_ID`, `GOOGLE_CLIENT_SECRET`,
   `GMAIL_REFRESH_PERSONAL/SUPPORT/CASCADE`, `ADDR_PERSONAL/SUPPORT/CASCADE` (the mailbox addresses),
   `TICKETMASTER_API_KEY`, `DASHBOARD_PASSWORD` (passphrase you'll type on the page).
5. Settings → Pages → Source: GitHub Actions. Run the workflow once; it then rebuilds every morning (~5:30am ET).

Pages sites are public URLs, so the page is AES-GCM encrypted in the build and decrypted in your browser;
the workflow refuses to publish if it isn't encrypted. Use a long passphrase. The browser remembers it on
each device after the first unlock.

## Tuning
`config.json`: search queries, VIP names (Heather, Alex Moore), last name, scoring keywords, RSS feeds.
Scoring (`dashboard/scoring.py`): + replies to threads you sent, + people you've emailed in 90 days, + VIPs/family,
+ unread; − promotions, bulk (List-Unsubscribe), no-reply senders.
Preview locally: `python -m dashboard.build --demo` then open `site/index.html`.
