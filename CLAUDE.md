# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## What this is

A small, standalone **daily Google Search Console (GSC) briefing** tool. It fetches the last 7 days of
Search Analytics, compares them to the prior 7 days, computes deterministic movers/opportunities, has an
LLM write a short narrative + prioritized actions, renders an HTML email, and sends it. Designed to run
unattended once a day (GitHub Actions cron), but also runs locally with `python gsc_report.py`.

It was split out of the larger `seo_audit_rag` project so that audit tool stays clean — this folder has
**no dependency on that repo** (no Redis, no Chroma, no crawler).

## Commands

```bash
pip install -r requirements.txt

python -c "import gsc; print(gsc.check())"   # verify GSC auth + property access (no email sent)
python gsc_report.py                          # full run: fetch -> analyze -> narrate -> email
```

## Architecture (fetch → analyze → narrate → render → email)

The pipeline is a deliberate split: **deterministic data/analysis** vs **LLM prose**. The LLM only
narrates numbers it is handed; it never fetches or computes them.

1. **`gsc.py`** — GSC client. Auth via a **service account** (`_credentials()`): prefers a JSON key file
   (`GOOGLE_APPLICATION_CREDENTIALS`, or its alias `GSC_SERVICE_ACCOUNT_FILE`), else builds credentials from the discrete env vars
   `GOOGLE_SERVICE_ACCOUNT_EMAIL` + `GOOGLE_SERVICE_ACCOUNT_PRIVATE_KEY` (the key's `\n` escapes are
   un-escaped at load). `query(start, end, dimensions, row_limit)` returns rows of
   `{dim..., clicks, impressions, ctr, position}`. `check()` verifies auth + that `GSC_SITE_URL` is one of
   the account's properties. Scope is `webmasters.readonly`.

2. **`gsc_analysis.py`** — pure, testable functions over the row lists (no LLM, no network, reproducible):
   `windows(days, lag)` (current vs previous date ranges, offset by `lag` days for GSC's ~3-day data
   delay), `totals`, `compare` (headline metric deltas — clicks/impressions as % change, CTR as
   percentage-points, position as absolute where **lower is better**), `top_movers` (gainers/losers by a
   metric, joined on the dimension key), `striking_distance` (position 11–20 with real impressions →
   page-2 terms to push onto page 1), `ctr_opportunities` (top-10 rank but CTR < 2% → fix title/meta).

3. **`gsc_report.py`** — orchestration. `build_report(days=7, lag=3)` fetches current+previous by `query`
   and by `page`, runs the analysis, calls `_narrative()` (one `gemini-2.5-flash` call via
   `langchain_google_genai.ChatGoogleGenerativeAI` on Gemini's free tier, prompted to use ONLY the
   supplied numbers), and `render_html()` (metric cards + tables). `main()` emails it via `emailer`.
   Note: the LLM client is LangChain, not the raw provider SDK — hence the `langchain-google-genai`
   dependency. The Gemini API key is `GOOGLE_API_KEY` (from aistudio.google.com), which is **separate**
   from the `GOOGLE_*` service-account vars used for GSC auth.

4. **`emailer.py`** — minimal SMTP HTML sender (`SMTP_*` + `REPORT_TO`); Gmail/Workspace over STARTTLS.

5. **`.github/workflows/gsc-daily.yml`** — cron `'30 0 * * *'` (00:30 UTC = 06:00 IST) + manual
   `workflow_dispatch`. Installs `requirements.txt`, runs `python gsc_report.py`, with all secrets injected
   from **GitHub repo secrets** (same names as the env vars). To change the send time, edit the cron (UTC).
   **Caveat:** GitHub scheduled crons are best-effort — often minutes-to-an-hour late and occasionally
   skipped. For reliable on-time delivery, use the AWS path below.

6. **AWS deploy (`Dockerfile`, `lambda_function.py`, `deploy/`)** — the reliable alternative to the GitHub
   cron. `lambda_function.handler` runs the same `build_report → email` pipeline. `deploy/deploy.sh`
   (idempotent; run in **AWS CloudShell** — has docker + aws CLI) builds the container, pushes to ECR,
   creates the Lambda + IAM roles, seeds env vars from a local `secrets.env` (via
   `deploy/build_env_json.py`), and creates an **EventBridge Scheduler** rule firing `cron(0 6 * * ? *)` in
   **`Asia/Kolkata`** — native timezone, exact timing. Re-run the script to ship new code or rotate secrets.

## Config (.env locally / GitHub secrets in CI)

| Var | Purpose |
|---|---|
| `GOOGLE_API_KEY` | Gemini (free tier) LLM narrative — from aistudio.google.com, distinct from the service-account creds below |
| `GSC_SITE_URL` | `sc-domain:baaz.pro` (Domain property) **or** `https://baaz.pro/` (URL-prefix) — must match the property type exactly |
| `GOOGLE_APPLICATION_CREDENTIALS` | path to service-account JSON **(or use the two vars below)** |
| `GOOGLE_SERVICE_ACCOUNT_EMAIL` / `GOOGLE_SERVICE_ACCOUNT_PRIVATE_KEY` | discrete service-account creds |
| `SMTP_HOST` / `SMTP_PORT` / `SMTP_USER` / `SMTP_PASS` | email delivery (`SMTP_PASS` = Google **App Password**) |
| `REPORT_TO` | recipient(s), comma-separated |

## Gotchas

- **The service account must be added as a user in Search Console** (Settings → Users and permissions →
  Restricted). A valid key that isn't added returns an empty property list — `check()` reports
  "Authenticated, but <url> is not in this account's properties: []".
- **`GSC_SITE_URL` must match the property type exactly.** Domain vs URL-prefix are different properties;
  the wrong prefix authenticates but finds no data.
- **Private key newlines**: in `.env` the key is one line with literal `\n`; `gsc._credentials()` does
  `.replace("\\n", "\n")`. In GitHub secrets you can paste the real multi-line key directly.
- **GSC data lags ~3 days** — hence `lag=3` in `windows()`; "today" in the report is really 3 days ago.
- **Never commit `.env`** or any service-account `*.json` (both are in `.gitignore`).
- LLM narrative is grounded: the prompt forbids inventing numbers, and all figures come from
  `gsc_analysis` — keep that separation if you edit `_narrative`.
