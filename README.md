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

## Calendar, filters and "read" (added)
- **Calendar:** needs the Gmail token for the personal account to also have the `calendar.readonly` scope, and the
  *Google Calendar API* enabled in the same Google Cloud project. Re-create `GMAIL_REFRESH_PERSONAL` in the OAuth Playground
  with both scopes (`.../auth/gmail.readonly` and `.../auth/calendar.readonly`). Blue = on your calendar;
  dashed amber = "potential" (Ticketmaster concerts + email events). Potential events have an "Add to Google Calendar" link.
- **Filter mode / read checkboxes / hidden senders** work immediately and are remembered on that device. To make them permanent
  and shared across devices: GitHub → Settings → Developer settings → Fine-grained tokens → this repo only, permission
  *Contents: Read and write*. Paste it under **⚙ Sync** on the page (once per device). Changes are committed to `state.json`
  (pushes that touch only that file don't trigger a rebuild) and the daily build also honors them. If the repo is public,
  `state.json` (filtered sender addresses) is visible to anyone.

## Layout and daily content
Top to bottom: Weather + 6:45 workout reminder, Calendar, Important mail (all three inboxes, news excluded), Read
(Morning Brew, World, Local, Indy restaurants, Baby; opening an item expands its card to full width), Events, Verse of the day,
"Lead her well".
- `dashboard/content.json`: the daily Bible verses (KJV), "lead her well" snippets and workout nudges. Edit or add your own; one of each is picked per day.
- `config.json`: `workout.leave_by`, `weather` coordinates, and the RSS feeds under `read.world`, `read.local` and `restaurants.feeds`
  (a feed that fails is skipped and noted at the bottom of the page).
- Weather is fetched live in the browser from Open-Meteo (no key needed).
- On Android, email links open the Gmail app (Settings → "Open email links in"). iPhone has no message deep link, so it uses the browser.

## 6am push notification (ntfy) and local races
- **Notification:** install the free **ntfy** app (Android/iOS), subscribe to a long random topic name of your choosing, and add the same string
  as the repo secret `NTFY_TOPIC`. The build finishes a bit before 6am and the notification is scheduled on ntfy's server for exactly 6:00
  Indianapolis time (sent immediately if the run is late). It only contains a generic "out the door by 6:45" nudge, never email or calendar text.
  Anyone who knows the topic name could read it or post to it, so keep it secret.
- **Races:** needs a free RunSignup API key and secret (runsignup.com → your account → API / Partner tools). Add them as secrets
  `RUNSIGNUP_API_KEY` and `RUNSIGNUP_API_SECRET`. Zip code, radius and months are under `races` in `config.json`.

## AI summaries (optional)
Add the repo secret `ANTHROPIC_API_KEY` (an API key from console.anthropic.com; billed separately from the Claude app, so set a spend limit there).
At build time the Read section's articles and the Morning Brew / Baby newsletters are summarized (model and item cap under `ai` in `config.json`).
Expanding an item shows the summary first, then the "Read the full article" link, then "Show full text". Personal and business mail is never sent to the API.
