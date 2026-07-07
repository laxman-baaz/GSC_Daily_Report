"""Daily Google Search Console report: fetch → analyze (deterministic) → narrate (LLM)
→ render HTML → email. Run directly (python gsc_report.py) or on a schedule (see README).

Env: GSC_SITE_URL, GOOGLE_* (service account), SMTP_* + REPORT_TO, GOOGLE_API_KEY (Gemini)."""
from langchain_google_genai import ChatGoogleGenerativeAI

import gsc
import gsc_analysis as ga


def _llm():
    return ChatGoogleGenerativeAI(model="gemini-2.5-flash", max_retries=5)


def _fmt_pct(v):
    return "n/a" if v is None else f"{v:+.1f}%"


def _narrative(metrics, q_gain, q_lose, striking, ctr_opp):
    data = (
        f"Clicks {metrics['clicks'][0]} ({_fmt_pct(metrics['clicks'][2])}), "
        f"Impressions {metrics['impressions'][0]} ({_fmt_pct(metrics['impressions'][2])}), "
        f"CTR {metrics['ctr'][0]*100:.2f}% ({metrics['ctr'][2]:+.2f}pp), "
        f"Avg position {metrics['position'][0]:.1f} ({metrics['position'][2]:+.1f}).\n"
        f"Top gaining queries: {[(d['query'], d['delta']) for d in q_gain[:5]]}\n"
        f"Top losing queries: {[(d['query'], d['delta']) for d in q_lose[:5]]}\n"
        f"Striking-distance (pos 11-20): {[(r['query'], round(r['position'],1), r['impressions']) for r in striking[:5]]}\n"
        f"CTR opportunities (top-10, low CTR): {[(r['query'], r['impressions'], round(r['ctr']*100,1)) for r in ctr_opp[:5]]}"
    )
    prompt = (
        "You are an SEO analyst writing a short daily Search Console briefing.\n"
        "Use ONLY the data below (don't invent numbers). Write:\n"
        "1) A 3-4 sentence summary of what changed and why it matters.\n"
        "2) 'TOP ACTIONS' — 3-5 specific, prioritized recommendations tied to the striking-distance and "
        "CTR opportunities (e.g. which query/page to improve and how). Be concise.\n\n"
        f"DATA:\n{data}"
    )
    return _llm().invoke(prompt).content


def _table(rows, cols, headers):
    th = "".join(f"<th style='text-align:left;padding:6px 10px;border-bottom:1px solid #ddd'>{h}</th>" for h in headers)
    trs = ""
    for r in rows:
        tds = "".join(f"<td style='padding:6px 10px;border-bottom:1px solid #f0f0f0'>{r.get(c, '')}</td>" for c in cols)
        trs += f"<tr>{tds}</tr>"
    return f"<table style='border-collapse:collapse;width:100%;font-size:13px'><tr>{th}</tr>{trs}</table>"


def _metric_card(label, val, delta_str, good):
    color = "#137333" if good else "#c5221f"
    return (f"<td style='padding:10px 14px;text-align:center'>"
            f"<div style='font-size:12px;color:#888'>{label}</div>"
            f"<div style='font-size:26px;font-weight:700'>{val}</div>"
            f"<div style='font-size:13px;color:{color}'>{delta_str}</div></td>")


def render_html(window, metrics, q_gain, q_lose, p_gain, p_lose, striking, ctr_opp, narrative):
    m = metrics
    cards = (
        _metric_card("Clicks", int(m["clicks"][0]), _fmt_pct(m["clicks"][2]), (m["clicks"][2] or 0) >= 0)
        + _metric_card("Impressions", int(m["impressions"][0]), _fmt_pct(m["impressions"][2]), (m["impressions"][2] or 0) >= 0)
        + _metric_card("CTR", f"{m['ctr'][0]*100:.2f}%", f"{m['ctr'][2]:+.2f}pp", m["ctr"][2] >= 0)
        + _metric_card("Avg position", f"{m['position'][0]:.1f}", f"{m['position'][2]:+.1f}", m["position"][2] <= 0)
    )
    q_gain_rows = [{"query": d["query"], "Δ clicks": f"+{d['delta']}"} for d in q_gain[:8]]
    q_lose_rows = [{"query": d["query"], "Δ clicks": d["delta"]} for d in q_lose[:8]]
    sd_rows = [{"query": r["query"], "pos": round(r["position"], 1), "impr": int(r["impressions"])} for r in striking]
    ctr_rows = [{"query": r["query"], "impr": int(r["impressions"]), "CTR": f"{r['ctr']*100:.1f}%",
                 "pos": round(r["position"], 1)} for r in ctr_opp]
    narrative_html = narrative.replace("\n", "<br>")
    return f"""<div style="font-family:Arial,sans-serif;max-width:720px;margin:auto;color:#202124">
      <h2>Search Console — daily briefing</h2>
      <p style="color:#888;font-size:13px">{window['cur'][0]} to {window['cur'][1]} vs {window['prev'][0]} to {window['prev'][1]}</p>
      <table style="width:100%;background:#f8f9fa;border-radius:8px;margin:8px 0"><tr>{cards}</tr></table>
      <div style="background:#f8f9fa;border-radius:8px;padding:14px;font-size:14px;line-height:1.5">{narrative_html}</div>
      <h3>Top gaining queries</h3>{_table(q_gain_rows, ['query','Δ clicks'], ['Query','Δ clicks'])}
      <h3>Top losing queries</h3>{_table(q_lose_rows, ['query','Δ clicks'], ['Query','Δ clicks'])}
      <h3>Striking distance (page-2 → push to page 1)</h3>{_table(sd_rows, ['query','pos','impr'], ['Query','Position','Impressions'])}
      <h3>CTR opportunities (top-10 rank, low CTR — fix title/meta)</h3>{_table(ctr_rows, ['query','impr','CTR','pos'], ['Query','Impressions','CTR','Position'])}
      <p style="color:#aaa;font-size:11px">Automated by SeoAeoGeoRAG. Data trails ~3 days (GSC lag).</p>
    </div>"""


def build_report(days=7, lag=3):
    w = ga.windows(days=days, lag=lag)
    cur_q = gsc.query(*w["cur"], dimensions=["query"], row_limit=1000)
    prev_q = gsc.query(*w["prev"], dimensions=["query"], row_limit=1000)
    cur_p = gsc.query(*w["cur"], dimensions=["page"], row_limit=1000)
    prev_p = gsc.query(*w["prev"], dimensions=["page"], row_limit=1000)

    metrics = ga.compare(cur_q, prev_q)
    q_gain, q_lose = ga.top_movers(cur_q, prev_q, "query", "clicks")
    p_gain, p_lose = ga.top_movers(cur_p, prev_p, "page", "clicks")
    striking = ga.striking_distance(cur_q)
    ctr_opp = ga.ctr_opportunities(cur_q)
    narrative = _narrative(metrics, q_gain, q_lose, striking, ctr_opp)
    return render_html(w, metrics, q_gain, q_lose, p_gain, p_lose, striking, ctr_opp, narrative), w


def main():
    import emailer
    html, w = build_report()
    to = emailer.send_email(f"SEO daily briefing — {w['cur'][1]}", html)
    print(f"Report emailed to {to}")


if __name__ == "__main__":
    main()
