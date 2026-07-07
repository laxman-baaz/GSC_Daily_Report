"""Google Search Console client. Authenticates with a service account (the one already in .env)
and queries the Search Analytics API for clicks/impressions/CTR/position.

Setup (one-time):
  1. In Search Console → Settings → Users and permissions, add GOOGLE_SERVICE_ACCOUNT_EMAIL
     as a user (Restricted is enough).
  2. Set GSC_SITE_URL in .env — 'sc-domain:baaz.pro' (Domain property) or 'https://baaz.pro/'
     (URL-prefix property).
"""
import os

from dotenv import load_dotenv
from google.oauth2 import service_account
from googleapiclient.discovery import build

load_dotenv()

SCOPES = ["https://www.googleapis.com/auth/webmasters.readonly"]
_service = None


def _credentials():
    # Prefer a JSON key file if provided; else build from the discrete env vars in .env.
    key_file = os.getenv("GOOGLE_APPLICATION_CREDENTIALS") or os.getenv("GSC_SERVICE_ACCOUNT_FILE")
    if key_file and os.path.exists(key_file):
        return service_account.Credentials.from_service_account_file(key_file, scopes=SCOPES)

    email = os.getenv("GOOGLE_SERVICE_ACCOUNT_EMAIL")
    private_key = (os.getenv("GOOGLE_SERVICE_ACCOUNT_PRIVATE_KEY") or "").replace("\\n", "\n")
    if not (email and private_key):
        raise RuntimeError(
            "No GSC credentials. Set GOOGLE_APPLICATION_CREDENTIALS (path to key.json), or "
            "GOOGLE_SERVICE_ACCOUNT_EMAIL + GOOGLE_SERVICE_ACCOUNT_PRIVATE_KEY in .env.")
    info = {
        "type": "service_account",
        "client_email": email,
        "private_key": private_key,
        "token_uri": "https://oauth2.googleapis.com/token",
    }
    return service_account.Credentials.from_service_account_info(info, scopes=SCOPES)


def service():
    global _service
    if _service is None:
        _service = build("searchconsole", "v1", credentials=_credentials(), cache_discovery=False)
    return _service


def site_url():
    s = os.getenv("GSC_SITE_URL")
    if not s:
        raise RuntimeError("Set GSC_SITE_URL in .env (e.g. 'sc-domain:baaz.pro' or 'https://baaz.pro/').")
    return s


def query(start_date, end_date, dimensions=("query",), row_limit=1000, site=None):
    """Run a Search Analytics query. Returns a list of dicts:
    {dimensions..., clicks, impressions, ctr, position}. Dates are 'YYYY-MM-DD'."""
    body = {
        "startDate": start_date,
        "endDate": end_date,
        "dimensions": list(dimensions),
        "rowLimit": row_limit,
    }
    resp = service().searchanalytics().query(siteUrl=site or site_url(), body=body).execute()
    rows = []
    for r in resp.get("rows", []):
        row = {dim: r["keys"][i] for i, dim in enumerate(dimensions)}
        row.update(clicks=r.get("clicks", 0), impressions=r.get("impressions", 0),
                   ctr=r.get("ctr", 0.0), position=r.get("position", 0.0))
        rows.append(row)
    return rows


def check():
    """Verify auth + property access. Returns (ok, message)."""
    try:
        sites = service().sites().list().execute().get("siteEntry", [])
        urls = [s["siteUrl"] for s in sites]
        want = os.getenv("GSC_SITE_URL", "")
        if want and want not in urls:
            return False, f"Authenticated, but {want} is not in this account's properties: {urls}"
        return True, f"OK — access to {len(urls)} property(ies): {urls}"
    except Exception as e:
        return False, f"GSC auth/access failed: {e}"
