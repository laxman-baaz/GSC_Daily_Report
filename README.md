# GSC Daily Report

A daily **Google Search Console briefing** emailed every morning. Fetches the last 7 days of Search
Analytics, compares to the prior week, and emails a short HTML report: headline metric deltas, top
gaining/losing queries, **striking-distance** terms (page-2 keywords worth pushing to page 1), and
**CTR opportunities** (top-10 rankings with weak click-through). Deterministic analysis; an LLM writes the
summary + prioritized actions.

## Setup

```bash
pip install -r requirements.txt
cp .env.example .env      # then fill in the values (see below)
```

Fill `.env`:

1. **`GSC_SITE_URL`** — in Search Console, check the property type: `sc-domain:baaz.pro` (Domain) or
   `https://baaz.pro/` (URL-prefix).
2. **Service account** — in Google Cloud, enable the *Google Search Console API*, create a service account
   + JSON key. Put the key path in `GOOGLE_APPLICATION_CREDENTIALS`, **or** copy `client_email` and
   `private_key` from the JSON into `GOOGLE_SERVICE_ACCOUNT_EMAIL` / `GOOGLE_SERVICE_ACCOUNT_PRIVATE_KEY`.
   Then in **Search Console → Settings → Users and permissions**, add that service-account email as a
   **Restricted** user.
3. **SMTP** — `SMTP_USER` = a sending inbox, `SMTP_PASS` = a Google **App Password** (Account → Security →
   2-Step Verification → App passwords). Set `REPORT_TO` to the recipient(s).

## Run

```bash
python -c "import gsc; print(gsc.check())"   # should print: OK — access to N property(ies)
python gsc_report.py                          # fetch + email the briefing now
```

## Schedule (GitHub Actions)

`.github/workflows/gsc-daily.yml` runs daily at **06:00 IST (00:30 UTC)** and can be triggered manually
from the Actions tab. Add each `.env` var as a **repo secret** (Settings → Secrets and variables →
Actions): `GOOGLE_API_KEY`, `GSC_SITE_URL`, `GOOGLE_SERVICE_ACCOUNT_EMAIL`,
`GOOGLE_SERVICE_ACCOUNT_PRIVATE_KEY` (paste the real multi-line key), `SMTP_HOST`, `SMTP_PORT`,
`SMTP_USER`, `SMTP_PASS`, `REPORT_TO`. Edit the cron (in UTC) to change the send time.
