"""Deterministic period-over-period analysis of GSC rows (clicks/impressions/ctr/position).
Pure functions over lists of dicts — no LLM, no network — so results are reproducible and testable."""
import datetime


def windows(days=7, lag=3):
    """Two comparable date windows, offset by `lag` days for GSC's data delay.
    Returns {'cur': (start, end), 'prev': (start, end)} as 'YYYY-MM-DD'."""
    end = datetime.date.today() - datetime.timedelta(days=lag)
    cur_start = end - datetime.timedelta(days=days - 1)
    prev_end = cur_start - datetime.timedelta(days=1)
    prev_start = prev_end - datetime.timedelta(days=days - 1)
    fmt = "%Y-%m-%d"
    return {"cur": (cur_start.strftime(fmt), end.strftime(fmt)),
            "prev": (prev_start.strftime(fmt), prev_end.strftime(fmt))}


def totals(rows):
    clicks = sum(r["clicks"] for r in rows)
    impr = sum(r["impressions"] for r in rows)
    ctr = (clicks / impr) if impr else 0.0
    pos = (sum(r["position"] * r["impressions"] for r in rows) / impr) if impr else 0.0
    return {"clicks": clicks, "impressions": impr, "ctr": ctr, "position": pos}


def _pct(cur, prev):
    return ((cur - prev) / prev * 100) if prev else None


def compare(cur_rows, prev_rows):
    """Headline metric deltas. Each value is (current, previous, delta)."""
    c, p = totals(cur_rows), totals(prev_rows)
    return {
        "clicks": (c["clicks"], p["clicks"], _pct(c["clicks"], p["clicks"])),           # % change
        "impressions": (c["impressions"], p["impressions"], _pct(c["impressions"], p["impressions"])),
        "ctr": (c["ctr"], p["ctr"], (c["ctr"] - p["ctr"]) * 100),                        # percentage-points
        "position": (c["position"], p["position"], c["position"] - p["position"]),       # lower is better
    }


def top_movers(cur_rows, prev_rows, dim="query", metric="clicks", n=10):
    """Biggest gainers and losers on `metric`, joined by dimension key."""
    cur = {r[dim]: r for r in cur_rows}
    prev = {r[dim]: r for r in prev_rows}
    deltas = []
    for k in set(cur) | set(prev):
        cv = cur.get(k, {}).get(metric, 0)
        pv = prev.get(k, {}).get(metric, 0)
        deltas.append({dim: k, "current": cv, "previous": pv, "delta": cv - pv})
    gainers = [d for d in sorted(deltas, key=lambda x: x["delta"], reverse=True)[:n] if d["delta"] > 0]
    losers = [d for d in sorted(deltas, key=lambda x: x["delta"])[:n] if d["delta"] < 0]
    return gainers, losers


# Impression floors are tuned for baaz.pro's current volume (~830 impressions/week).
# Raise these as traffic grows so the tables stay signal, not noise.
STRIKING_MIN_IMPRESSIONS = 3
CTR_OPP_MIN_IMPRESSIONS = 10


def striking_distance(rows, dim="query", n=15):
    """Position 11-20 with real impressions — page-2 terms to push onto page 1."""
    hits = [r for r in rows if 10.5 < r["position"] <= 20 and r["impressions"] >= STRIKING_MIN_IMPRESSIONS]
    return sorted(hits, key=lambda r: r["impressions"], reverse=True)[:n]


def ctr_opportunities(rows, dim="query", n=15):
    """High impressions + top-10 position but low CTR — improve titles/meta to earn the clicks."""
    hits = [r for r in rows if r["impressions"] >= CTR_OPP_MIN_IMPRESSIONS and r["position"] <= 10 and r["ctr"] < 0.02]
    return sorted(hits, key=lambda r: r["impressions"], reverse=True)[:n]
