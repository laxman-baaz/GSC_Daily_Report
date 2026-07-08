"""Turn a KEY=VALUE secrets file (same format as .env) into the JSON shape
`aws lambda ... --environment file://env.json` expects. Skips comments, blank
lines, and empty values. Usage: python build_env_json.py secrets.env env.json"""
import json
import sys

# Only these keys are shipped to Lambda (GOOGLE_APPLICATION_CREDENTIALS is a local
# file path and irrelevant in Lambda, so it's intentionally excluded).
ALLOWED = {
    "GOOGLE_API_KEY", "GSC_SITE_URL",
    "GOOGLE_SERVICE_ACCOUNT_EMAIL", "GOOGLE_SERVICE_ACCOUNT_PRIVATE_KEY",
    "SMTP_HOST", "SMTP_PORT", "SMTP_USER", "SMTP_PASS", "REPORT_TO",
}


def main(src, dst):
    variables = {}
    with open(src, encoding="utf-8") as f:
        for line in f:
            line = line.rstrip("\n")
            if not line or line.lstrip().startswith("#") or "=" not in line:
                continue
            key, val = line.split("=", 1)
            key, val = key.strip(), val.strip()
            if key in ALLOWED and val:
                variables[key] = val

    missing = ALLOWED - {"GOOGLE_APPLICATION_CREDENTIALS"} - set(variables)
    if missing:
        print(f"WARNING: missing keys (Lambda may fail): {sorted(missing)}", file=sys.stderr)

    with open(dst, "w", encoding="utf-8") as f:
        json.dump({"Variables": variables}, f)
    print(f"Wrote {dst} with {len(variables)} variables: {sorted(variables)}")


if __name__ == "__main__":
    main(sys.argv[1], sys.argv[2])
