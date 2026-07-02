"""
Setup Google Calendar OAuth — mode console (cocok untuk SSH)
"""
import sys
import json
from pathlib import Path

CRED_FILE = Path.home() / ".config" / "rav-spy" / "credentials.json"
TOKEN_FILE = Path.home() / ".config" / "rav-spy" / "calendar_token.json"
SCOPES = ["https://www.googleapis.com/auth/calendar.readonly"]

if not CRED_FILE.exists():
    print(f"File credentials.json tidak ditemukan di:")
    print(f"  {CRED_FILE}")
    print()
    print("Cara dapetin:")
    print("1. Buka https://console.cloud.google.com/")
    print("2. Buat project baru → Enable Google Calendar API")
    print("3. Credentials → Create Credentials → OAuth client ID")
    print("4. Pilih 'Desktop application', download JSON")
    print(f"5. Simpan sebagai: {CRED_FILE}")
    sys.exit(1)

try:
    from google.auth.transport.requests import Request
    from google.oauth2.credentials import Credentials
    from google_auth_oauthlib.flow import InstalledAppFlow
except ImportError:
    print("Install dulu: pip install google-api-python-client google-auth-httplib2 google-auth-oauthlib")
    sys.exit(1)

creds = None
if TOKEN_FILE.exists():
    creds = Credentials.from_authorized_user_file(str(TOKEN_FILE), SCOPES)

if creds and creds.valid:
    print("✅ Calendar sudah terautentikasi. Token valid.")
    sys.exit(0)

if creds and creds.expired and creds.refresh_token:
    creds.refresh(Request())
    with open(TOKEN_FILE, "w") as f:
        f.write(creds.to_json())
    print("✅ Token refresh berhasil.")
    sys.exit(0)

print("Memulai OAuth flow (mode console)...")
print()
flow = InstalledAppFlow.from_client_secrets_file(str(CRED_FILE), SCOPES)
creds = flow.run_console()
with open(TOKEN_FILE, "w") as f:
    f.write(creds.to_json())
print(f"\n✅ Berhasil! Token tersimpan di {TOKEN_FILE}")
