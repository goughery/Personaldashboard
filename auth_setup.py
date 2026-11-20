"""One-time, run on YOUR computer: prints a Gmail read-only refresh token for one account.
   python auth_setup.py client_secret.json   (sign in as the mailbox you want to connect)"""
import sys
from google_auth_oauthlib.flow import InstalledAppFlow
flow = InstalledAppFlow.from_client_secrets_file(sys.argv[1], ["https://www.googleapis.com/auth/gmail.readonly", "https://www.googleapis.com/auth/calendar.readonly"])
creds = flow.run_local_server(port=0, access_type="offline", prompt="consent")
print("\nREFRESH TOKEN (store as a GitHub secret):\n" + creds.refresh_token)
