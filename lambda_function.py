"""AWS Lambda entry point. EventBridge Scheduler invokes handler() once a day;
it runs the same build_report -> email pipeline used by the CLI (gsc_report.main)."""
import gsc_report
import emailer


def handler(event=None, context=None):
    html, w = gsc_report.build_report()
    to = emailer.send_email(f"SEO daily briefing — {w['cur'][1]}", html)
    print(f"Report emailed to {to}")
    return {"statusCode": 200, "window": w["cur"], "sentTo": to}
